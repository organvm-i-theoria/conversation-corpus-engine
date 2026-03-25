"""Policy-driven auto-triage for the federated review queue."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .answering import STOP_WORDS, tokenize, write_json, write_markdown
from .federated_canon import (
    FEDERATED_REVIEW_TYPES,
    add_decision_record,
    append_federated_review_history,
    load_federated_decisions,
    load_federated_review_queue,
    save_federated_decisions,
    save_federated_review_queue,
)

NOISE_ENTITY_IDS = {
    "entity-0-1",
    "entity-1-0",
    "entity-0",
    "entity-1",
    "entity-2",
    "entity-3",
    "entity-none",
    "entity-null",
    "entity-true",
    "entity-false",
}

PLACEHOLDER_LABELS = {
    "both",
    "default",
    "general",
    "missing",
    "misc",
    "none",
    "other",
    "primary",
    "remaining",
    "supplement",
    "unknown",
}

HEADING_LIKE_LABELS = {
    "appendix",
    "appendices",
    "chapter",
    "chapters",
    "checklist",
    "conclusion",
    "extension",
    "introduction",
    "overview",
    "section",
    "sections",
    "summary",
}

STANDARD_ENTITY_ALIAS_REVIEW_CAMPAIGN_SCENARIOS = [
    {
        "label": "likely_front",
        "description": "Front-window likely-reject sample",
        "relation_filters": ["disjoint"],
        "review_buckets": ["likely-reject"],
        "sample_groups": 12,
        "sample_batches": 5,
        "batch_offset": 0,
    },
    {
        "label": "likely_mid",
        "description": "Mid-window likely-reject sample",
        "relation_filters": ["disjoint"],
        "review_buckets": ["likely-reject"],
        "sample_groups": 12,
        "sample_batches": 5,
        "batch_offset": 5,
    },
    {
        "label": "likely_late",
        "description": "Late-window likely-reject sample",
        "relation_filters": ["disjoint"],
        "review_buckets": ["likely-reject"],
        "sample_groups": 12,
        "sample_batches": 5,
        "batch_offset": 10,
    },
    {
        "label": "needs_context",
        "description": "Front-window needs-context sample",
        "relation_filters": ["disjoint"],
        "review_buckets": ["needs-context"],
        "sample_groups": 8,
        "sample_batches": 10,
        "batch_offset": 0,
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def report_date() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def report_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d-%H%M%S-%f")


def _strip_uuid_suffix(local_id: str) -> str:
    """Strip the trailing 8-hex-char UUID suffix from a slugified ID.

    e.g. 'family-divine-comedy-f22e2b8d' → 'family-divine-comedy'
    """
    if len(local_id) < 10:
        return local_id
    parts = local_id.rsplit("-", 1)
    if len(parts) == 2 and len(parts[1]) == 8:
        try:
            int(parts[1], 16)
            return parts[0]
        except ValueError:
            pass
    return local_id


def extract_local_ids(subject_ids: list[str]) -> list[tuple[str, str]]:
    """Split subject_ids into (corpus_id, local_id) pairs."""
    pairs: list[tuple[str, str]] = []
    for sid in subject_ids:
        if ":" in sid:
            corpus, local = sid.split(":", 1)
            pairs.append((corpus, local))
        else:
            pairs.append(("", sid))
    return pairs


def _split_review_title(title: str) -> tuple[str, str]:
    left, sep, right = (title or "").partition(" <> ")
    if not sep:
        return "", ""
    return left.strip(), right.strip()


def _meaningful_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in STOP_WORDS]


def _normalize_label(text: str) -> str:
    return " ".join(tokenize((text or "").replace("-", " ").replace("_", " ")))


def _token_overlap_metrics(left: str, right: str) -> dict[str, float | int]:
    left_tokens = set(_meaningful_tokens(left))
    right_tokens = set(_meaningful_tokens(right))
    if not left_tokens or not right_tokens:
        return {"jaccard": 0.0, "overlap_count": 0, "subset_ratio": 0.0}
    overlap = left_tokens & right_tokens
    union = left_tokens | right_tokens
    shorter = min(len(left_tokens), len(right_tokens))
    return {
        "jaccard": round(len(overlap) / len(union), 4),
        "overlap_count": len(overlap),
        "subset_ratio": round(len(overlap) / shorter, 4) if shorter else 0.0,
    }


def _semantic_title_policy(
    item: dict[str, Any],
    *,
    policy: str,
    note: str,
    min_overlap: int,
    min_jaccard: float,
    min_subset_ratio: float,
    min_shorter_tokens: int,
) -> dict[str, Any] | None:
    left_title, right_title = _split_review_title(item.get("title", ""))
    if not left_title or not right_title:
        return None
    left_tokens = _meaningful_tokens(left_title)
    right_tokens = _meaningful_tokens(right_title)
    if min(len(left_tokens), len(right_tokens)) < min_shorter_tokens:
        return None
    metrics = _token_overlap_metrics(left_title, right_title)
    if (
        metrics["overlap_count"] >= min_overlap
        and (
            metrics["jaccard"] >= min_jaccard
            or metrics["subset_ratio"] >= min_subset_ratio
            or left_title.lower() == right_title.lower()
        )
    ):
        return {
            "decision": "accepted",
            "note": note,
            "policy": policy,
            "canonical_subject": item.get("suggested_canonical_subject") or "",
        }
    return None


def _generic_singleton_entity_policy(item: dict[str, Any]) -> dict[str, Any] | None:
    left_title, right_title = _split_review_title(item.get("title", ""))
    if not left_title or not right_title:
        return None
    left_tokens = _meaningful_tokens(left_title)
    right_tokens = _meaningful_tokens(right_title)
    if {len(left_tokens), len(right_tokens)} != {1, max(len(left_tokens), len(right_tokens))}:
        return None
    if min(len(left_tokens), len(right_tokens)) != 1 or max(len(left_tokens), len(right_tokens)) < 3:
        return None
    short_tokens = set(left_tokens if len(left_tokens) < len(right_tokens) else right_tokens)
    long_tokens = set(right_tokens if len(left_tokens) < len(right_tokens) else left_tokens)
    if short_tokens and short_tokens <= long_tokens:
        return {
            "decision": "rejected",
            "note": "Auto-triage: one-word entity label is only a generic subset of a longer phrase",
            "policy": "generic-singleton-entity",
            "canonical_subject": "",
        }
    return None


def _humanize_local_id(local_id: str) -> str:
    cleaned = local_id
    for prefix in ("entity-", "family-", "action-", "question-"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    return " ".join(cleaned.replace("-", " ").split()).strip()


def _entity_alias_anchor(
    item: dict[str, Any], left_label: str, right_label: str, subject_ids: list[str]
) -> str:
    suggested = _normalize_label(str(item.get("suggested_canonical_subject") or ""))
    if suggested:
        return suggested
    labels = [label for label in (_normalize_label(left_label), _normalize_label(right_label)) if label]
    if labels:
        return min(labels, key=lambda value: (len(_meaningful_tokens(value)), len(value), value))
    local_ids = [local for _, local in extract_local_ids(subject_ids)]
    if local_ids:
        fallback = min(local_ids, key=len)
        return _normalize_label(_humanize_local_id(fallback))
    return "unlabeled"


def _entity_alias_relation(left_label: str, right_label: str) -> str:
    left_normalized = _normalize_label(left_label)
    right_normalized = _normalize_label(right_label)
    if not left_normalized or not right_normalized:
        return "unlabeled"
    if left_normalized == right_normalized:
        return "exact-match"
    metrics = _token_overlap_metrics(left_normalized, right_normalized)
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return "substring"
    if metrics["overlap_count"] >= 2 and (
        metrics["jaccard"] >= 0.5 or metrics["subset_ratio"] >= 1.0
    ):
        return "high-overlap"
    if metrics["overlap_count"] >= 1:
        return "partial-overlap"
    return "disjoint"


def _entity_alias_review_hint(
    *,
    relation: str,
    score: float,
    overlap_count: int,
) -> str:
    if relation == "exact-match":
        return "Labels match exactly; confirm whether this remained open only because of prior boundary rules."
    if relation in {"substring", "high-overlap"}:
        return "Strong lexical overlap; review whether the longer label is a true alias or a broader concept."
    if relation == "partial-overlap":
        return "Some lexical overlap exists; verify whether shared terms indicate the same entity or a topical neighbor."
    if overlap_count == 0 and score >= 0.9:
        return "Queue score is high despite disjoint labels; inspect upstream context before accepting."
    return "Lexical evidence is weak; this likely needs rejection unless external context clearly links the entities."


def _entity_alias_label_signals(label: str) -> list[str]:
    normalized = _normalize_label(label)
    compact = normalized.replace(" ", "")
    tokens = _meaningful_tokens(label)
    signals: list[str] = []
    if not normalized:
        return signals
    if normalized in PLACEHOLDER_LABELS:
        signals.append("placeholder-like-label")
    if normalized in HEADING_LIKE_LABELS:
        signals.append("heading-like-label")
    if compact.isdigit() or (compact.isalnum() and any(char.isdigit() for char in compact) and len(compact) <= 6):
        signals.append("numeric-or-code-label")
    if len(tokens) <= 1 and compact.isalpha() and len(compact) <= 3:
        signals.append("short-fragment-label")
    return signals


def _entity_alias_assist_entry(item: dict[str, Any]) -> dict[str, Any]:
    left_label, right_label = _split_review_title(item.get("title", ""))
    subject_ids = item.get("subject_ids") or []
    local_ids = [local for _, local in extract_local_ids(subject_ids)]
    if not left_label and local_ids:
        left_label = _humanize_local_id(local_ids[0])
    if not right_label and len(local_ids) > 1:
        right_label = _humanize_local_id(local_ids[1])
    anchor = _entity_alias_anchor(item, left_label, right_label, subject_ids)
    relation = _entity_alias_relation(left_label, right_label)
    metrics = _token_overlap_metrics(left_label, right_label)
    source_pair = " <> ".join(sorted(item.get("source_corpora") or []))
    score = float(item.get("score") or 0.0)
    label_signals = sorted(
        {
            signal
            for label in (left_label, right_label)
            for signal in _entity_alias_label_signals(label)
        }
    )
    return {
        "review_id": item.get("review_id", ""),
        "title": item.get("title") or f"{left_label} <> {right_label}",
        "score": score,
        "priority": item.get("priority") or "unknown",
        "anchor": anchor or "unlabeled",
        "labels": [left_label, right_label],
        "relation": relation,
        "token_metrics": metrics,
        "source_pair": source_pair,
        "source_corpora": item.get("source_corpora") or [],
        "subject_ids": subject_ids,
        "suggested_canonical_subject": item.get("suggested_canonical_subject") or "",
        "label_signals": label_signals,
        "review_hint": _entity_alias_review_hint(
            relation=relation,
            score=score,
            overlap_count=int(metrics["overlap_count"]),
        ),
        "rationale": item.get("rationale") or "",
    }


def _entity_alias_counts(entries: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    relation_counts: dict[str, int] = {}
    source_pair_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    for entry in entries:
        relation = entry["relation"]
        relation_counts[relation] = relation_counts.get(relation, 0) + 1
        source_pair = entry["source_pair"]
        source_pair_counts[source_pair] = source_pair_counts.get(source_pair, 0) + 1
        priority = entry["priority"]
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
    return relation_counts, source_pair_counts, priority_counts


def _entity_alias_group_guidance(group: dict[str, Any]) -> tuple[str, list[str], list[str], dict[str, int]]:
    entries = list(group.get("items") or [])
    disjoint_count = sum(1 for entry in entries if entry.get("relation") == "disjoint")
    exactish_count = sum(
        1
        for entry in entries
        if entry.get("relation") in {"exact-match", "substring", "high-overlap"}
    )
    zero_overlap_count = sum(
        1 for entry in entries if int((entry.get("token_metrics") or {}).get("overlap_count", 0)) == 0
    )
    high_score_count = sum(1 for entry in entries if float(entry.get("score") or 0.0) >= 0.9)
    low_specificity_entry_count = sum(1 for entry in entries if entry.get("label_signals"))
    signal_flags: list[str] = []
    if low_specificity_entry_count:
        signal_flags.append("has-low-specificity-labels")
    if high_score_count and disjoint_count:
        signal_flags.append("has-high-score-disjoint-pairs")
    if zero_overlap_count == len(entries) and entries:
        signal_flags.append("all-zero-overlap")

    if exactish_count == len(entries) and entries:
        bucket = "alias-check"
    elif disjoint_count == len(entries) and zero_overlap_count == len(entries) and high_score_count:
        bucket = "needs-context"
    elif disjoint_count == len(entries) and zero_overlap_count == len(entries):
        bucket = "likely-reject"
    else:
        bucket = "mixed-review"

    checklist: list[str] = []
    if bucket == "alias-check":
        checklist.append("Check whether the longer label is a true alias rather than a broader concept.")
        checklist.append("Accept only if the shared terms point to the same named thing, not a topical family.")
    elif bucket == "needs-context":
        checklist.append("Inspect the highest-scoring pair before rejecting; upstream signal is stronger than lexical overlap.")
        checklist.append("Reject only if the pair still reads like neighboring topics rather than the same entity.")
    elif bucket == "likely-reject":
        checklist.append("Reject unless external context ties these labels to the same entity.")
        checklist.append("Spot-check the top-scoring pair before closing the whole group.")
    else:
        checklist.append("Review the highest-scoring pair first and decide whether the shared terms imply identity or only topical overlap.")
        checklist.append("Use the remaining pairs to confirm the group-level pattern before resolving in bulk.")

    if low_specificity_entry_count:
        checklist.append("Verify labels are not headings, placeholders, fragments, or extraction residue.")

    signal_counts = {
        "disjoint_count": disjoint_count,
        "zero_overlap_count": zero_overlap_count,
        "high_score_count": high_score_count,
        "low_specificity_entry_count": low_specificity_entry_count,
    }
    return bucket, checklist, signal_flags, signal_counts


def _copy_entity_alias_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        **group,
        "relation_counts": dict(group.get("relation_counts") or {}),
        "source_pair_counts": dict(group.get("source_pair_counts") or {}),
        "labels": list(group.get("labels") or []),
        "checklist": list(group.get("checklist") or []),
        "signal_flags": list(group.get("signal_flags") or []),
        "signal_counts": dict(group.get("signal_counts") or {}),
        "example_review_ids": list(group.get("example_review_ids") or []),
        "items": [dict(item) for item in group.get("items") or []],
    }


def _rebuild_entity_alias_review_assist_payload(
    payload: dict[str, Any],
    *,
    groups: list[dict[str, Any]],
    batches: list[dict[str, Any]],
    group_filters: dict[str, Any] | None = None,
    sample: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entries = [item for group in groups for item in group.get("items") or []]
    relation_counts, source_pair_counts, priority_counts = _entity_alias_counts(entries)
    rebuilt = {
        **payload,
        "open_count": len(entries),
        "group_count": len(groups),
        "batch_count": len(batches),
        "relation_counts": relation_counts,
        "source_pair_counts": source_pair_counts,
        "priority_counts": priority_counts,
        "groups": groups,
        "batches": batches,
    }
    if group_filters is not None:
        rebuilt["group_filters"] = group_filters
    if sample is not None:
        rebuilt["sample"] = sample
    return rebuilt


def build_entity_alias_review_assist(
    project_root: Path,
    *,
    batch_size: int = 25,
    relation_filters: list[str] | None = None,
    source_pair: str | None = None,
    anchor_contains: str | None = None,
) -> dict[str, Any]:
    queue = load_federated_review_queue(project_root)
    queue_open_items = [
        item
        for item in queue.get("items", [])
        if item.get("status") == "open" and item.get("review_type") == "entity-alias"
    ]
    entries = [_entity_alias_assist_entry(item) for item in queue_open_items]
    normalized_relations = sorted({value for value in relation_filters or [] if value})
    normalized_anchor = " ".join((anchor_contains or "").strip().lower().split())
    if normalized_relations:
        relation_set = set(normalized_relations)
        entries = [entry for entry in entries if entry["relation"] in relation_set]
    if source_pair:
        entries = [entry for entry in entries if entry["source_pair"] == source_pair]
    if normalized_anchor:
        entries = [entry for entry in entries if normalized_anchor in entry["anchor"]]
    entries.sort(
        key=lambda entry: (
            entry["anchor"],
            -entry["score"],
            entry["relation"],
            entry["title"],
            entry["review_id"],
        )
    )

    relation_counts, source_pair_counts, priority_counts = _entity_alias_counts(entries)
    group_map: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_source_pair = entry["source_pair"]

        group = group_map.setdefault(
            entry["anchor"],
            {
                "anchor": entry["anchor"],
                "item_count": 0,
                "max_score": 0.0,
                "relation_counts": {},
                "source_pair_counts": {},
                "labels": set(),
                "items": [],
            },
        )
        group["item_count"] += 1
        group["max_score"] = max(group["max_score"], entry["score"])
        group["relation_counts"][entry["relation"]] = (
            group["relation_counts"].get(entry["relation"], 0) + 1
        )
        group["source_pair_counts"][entry_source_pair] = (
            group["source_pair_counts"].get(entry_source_pair, 0) + 1
        )
        for label in entry["labels"]:
            if label:
                group["labels"].add(label)
        group["items"].append(entry)

    groups: list[dict[str, Any]] = []
    for group in group_map.values():
        group["labels"] = sorted(group["labels"])
        group["items"].sort(key=lambda entry: (-entry["score"], entry["relation"], entry["title"]))
        bucket, checklist, signal_flags, signal_counts = _entity_alias_group_guidance(group)
        group["review_bucket"] = bucket
        group["checklist"] = checklist
        group["signal_flags"] = signal_flags
        group["signal_counts"] = signal_counts
        group["example_review_ids"] = [entry["review_id"] for entry in group["items"][:3]]
        groups.append(group)
    groups.sort(key=lambda group: (-group["item_count"], group["anchor"]))

    batches: list[dict[str, Any]] = []
    requested_batch_size = max(batch_size, 1)
    current_groups: list[dict[str, Any]] = []
    current_item_count = 0
    for group in groups:
        if current_groups and current_item_count + group["item_count"] > requested_batch_size:
            batches.append(
                {
                    "batch_id": f"entity-alias-batch-{len(batches) + 1:03d}",
                    "group_count": len(current_groups),
                    "item_count": current_item_count,
                    "anchors": [item["anchor"] for item in current_groups],
                    "groups": current_groups,
                }
            )
            current_groups = []
            current_item_count = 0
        current_groups.append(group)
        current_item_count += group["item_count"]
    if current_groups:
        batches.append(
            {
                "batch_id": f"entity-alias-batch-{len(batches) + 1:03d}",
                "group_count": len(current_groups),
                "item_count": current_item_count,
                "anchors": [item["anchor"] for item in current_groups],
                "groups": current_groups,
            }
        )

    return {
        "generated_at": now_iso(),
        "review_type": "entity-alias",
        "queue_open_count": len(queue_open_items),
        "filtered_open_count": len(entries),
        "open_count": len(entries),
        "group_count": len(groups),
        "batch_count": len(batches),
        "batch_size": requested_batch_size,
        "filters": {
            "relations": normalized_relations,
            "source_pair": source_pair or "",
            "anchor_contains": normalized_anchor,
        },
        "relation_counts": relation_counts,
        "source_pair_counts": source_pair_counts,
        "priority_counts": priority_counts,
        "groups": groups,
        "batches": batches,
    }


def select_entity_alias_review_assist_batch(
    payload: dict[str, Any],
    batch_id: str,
) -> dict[str, Any]:
    batches = payload.get("batches") or []
    for index, batch in enumerate(batches, start=1):
        if batch.get("batch_id") != batch_id:
            continue
        groups = [_copy_entity_alias_group(group) for group in batch.get("groups") or []]
        entries = [item for group in groups for item in group["items"]]
        relation_counts, source_pair_counts, priority_counts = _entity_alias_counts(entries)
        selected_batch = {
            "batch_id": batch["batch_id"],
            "group_count": batch["group_count"],
            "item_count": batch["item_count"],
            "anchors": list(batch.get("anchors") or []),
            "groups": groups,
        }
        return {
            **payload,
            "open_count": len(entries),
            "group_count": len(groups),
            "batch_count": 1,
            "relation_counts": relation_counts,
            "source_pair_counts": source_pair_counts,
            "priority_counts": priority_counts,
            "groups": groups,
            "batches": [selected_batch],
            "selection": {
                "batch_id": batch_id,
                "batch_index": index,
                "available_batch_count": len(batches),
                "available_open_count": payload.get("open_count", len(entries)),
                "available_group_count": payload.get("group_count", len(groups)),
            },
        }
    available = ", ".join(batch.get("batch_id", "") for batch in batches[:10] if batch.get("batch_id"))
    if len(batches) > 10:
        available = f"{available}, ..."
    raise ValueError(f"Unknown review-assist batch: {batch_id}. Available batches: {available or 'none'}")


def filter_entity_alias_review_assist_groups(
    payload: dict[str, Any],
    *,
    review_bucket_filters: list[str] | None = None,
) -> dict[str, Any]:
    normalized_buckets = sorted({value for value in review_bucket_filters or [] if value})
    if not normalized_buckets:
        return payload

    bucket_set = set(normalized_buckets)
    groups = [
        _copy_entity_alias_group(group)
        for group in payload.get("groups") or []
        if group.get("review_bucket") in bucket_set
    ]
    group_anchors = {group["anchor"] for group in groups}
    batches: list[dict[str, Any]] = []
    for batch in payload.get("batches") or []:
        batch_groups = [
            _copy_entity_alias_group(group)
            for group in batch.get("groups") or []
            if group.get("anchor") in group_anchors and group.get("review_bucket") in bucket_set
        ]
        if not batch_groups:
            continue
        batches.append(
            {
                "batch_id": batch["batch_id"],
                "group_count": len(batch_groups),
                "item_count": sum(group["item_count"] for group in batch_groups),
                "anchors": [group["anchor"] for group in batch_groups],
                "groups": batch_groups,
            }
        )

    existing_filters = dict(payload.get("group_filters") or {})
    existing_filters["review_buckets"] = normalized_buckets
    return _rebuild_entity_alias_review_assist_payload(
        payload,
        groups=groups,
        batches=batches,
        group_filters=existing_filters,
    )


def sample_entity_alias_review_assist_groups(
    payload: dict[str, Any],
    *,
    sample_groups: int,
    sample_batches: int | None = None,
    batch_offset: int = 0,
) -> dict[str, Any]:
    requested_groups = max(int(sample_groups), 1)
    candidate_batches = list(payload.get("batches") or [])
    requested_batch_offset = max(int(batch_offset), 0)
    if requested_batch_offset:
        candidate_batches = candidate_batches[requested_batch_offset:]
    requested_batch_limit = max(int(sample_batches), 1) if sample_batches else None
    if requested_batch_limit is not None:
        candidate_batches = candidate_batches[:requested_batch_limit]

    batch_queues = [
        {
            "batch_id": batch["batch_id"],
            "groups": [_copy_entity_alias_group(group) for group in batch.get("groups") or []],
        }
        for batch in candidate_batches
    ]
    sampled_by_batch: dict[str, list[dict[str, Any]]] = {batch["batch_id"]: [] for batch in candidate_batches}
    sampled_groups_list: list[dict[str, Any]] = []
    while len(sampled_groups_list) < requested_groups and any(batch["groups"] for batch in batch_queues):
        for batch in batch_queues:
            if len(sampled_groups_list) >= requested_groups:
                break
            if not batch["groups"]:
                continue
            group = batch["groups"].pop(0)
            sampled_groups_list.append(group)
            sampled_by_batch[batch["batch_id"]].append(group)

    sampled_batches: list[dict[str, Any]] = []
    for batch in candidate_batches:
        batch_groups = sampled_by_batch[batch["batch_id"]]
        if not batch_groups:
            continue
        sampled_batches.append(
            {
                "batch_id": batch["batch_id"],
                "group_count": len(batch_groups),
                "item_count": sum(group["item_count"] for group in batch_groups),
                "anchors": [group["anchor"] for group in batch_groups],
                "groups": batch_groups,
            }
        )

    sample_metadata = {
        "requested_group_count": requested_groups,
        "selected_group_count": len(sampled_groups_list),
        "requested_batch_offset": requested_batch_offset,
        "requested_batch_limit": requested_batch_limit or 0,
        "candidate_group_count": sum(len(batch.get("groups") or []) for batch in candidate_batches),
        "candidate_batch_count": len(candidate_batches),
    }
    return _rebuild_entity_alias_review_assist_payload(
        payload,
        groups=sampled_groups_list,
        batches=sampled_batches,
        sample=sample_metadata,
    )


def render_entity_alias_review_assist(
    payload: dict[str, Any],
    *,
    group_limit: int = 10,
) -> str:
    filters = payload.get("filters") or {}
    group_filters = payload.get("group_filters") or {}
    selection = payload.get("selection") or {}
    sample = payload.get("sample") or {}
    queue_open_count = payload.get("queue_open_count", payload["open_count"])
    filtered_open_count = payload.get("filtered_open_count", payload["open_count"])
    if selection.get("batch_id"):
        headline = (
            f"Entity-alias review assist: {payload['open_count']} items "
            f"(from {filtered_open_count} filtered / {queue_open_count} open)"
        )
    else:
        headline = f"Entity-alias review assist: {payload['open_count']} items (from {queue_open_count} open)"
    lines = [
        headline,
        f"Groups: {payload['group_count']}  Batches: {payload['batch_count']}  Batch size: {payload['batch_size']}",
    ]
    if selection.get("batch_id"):
        lines.append(
            "Selected batch: "
            f"{selection['batch_id']} ({selection['batch_index']}/{selection['available_batch_count']})"
        )
    if sample.get("selected_group_count"):
        lines.append(
            "Sample: "
            f"{sample['selected_group_count']} groups "
            f"(from {sample['candidate_group_count']} candidate groups across {sample['candidate_batch_count']} batches)"
        )
    filter_parts = []
    if filters.get("relations"):
        filter_parts.append(f"relations={','.join(filters['relations'])}")
    if filters.get("source_pair"):
        filter_parts.append(f"source_pair={filters['source_pair']}")
    if filters.get("anchor_contains"):
        filter_parts.append(f"anchor_contains={filters['anchor_contains']}")
    if group_filters.get("review_buckets"):
        filter_parts.append(f"buckets={','.join(group_filters['review_buckets'])}")
    if filter_parts:
        lines.append("Filters: " + "  ".join(filter_parts))
    if payload.get("relation_counts"):
        relation_summary = ", ".join(
            f"{relation}={count}"
            for relation, count in sorted(
                payload["relation_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Relations: {relation_summary}")
    if payload.get("source_pair_counts"):
        top_pairs = sorted(
            payload["source_pair_counts"].items(), key=lambda item: (-item[1], item[0])
        )[:3]
        lines.append(
            "Top source pairs: "
            + ", ".join(f"{pair}={count}" for pair, count in top_pairs if pair)
        )
    lines.append("")

    for batch in payload.get("batches", []):
        lines.append(
            f"{batch['batch_id']}  items={batch['item_count']}  groups={batch['group_count']}"
        )
        lines.append(f"  anchors: {', '.join(batch['anchors'])}")
        lines.append("")

    displayed_groups = payload.get("groups", [])[: max(group_limit, 0)]
    if displayed_groups:
        lines.append("Top groups:")
        for group in displayed_groups:
            top_relations = ", ".join(
                f"{relation}={count}"
                for relation, count in sorted(
                    group["relation_counts"].items(), key=lambda item: (-item[1], item[0])
                )
            )
            lines.append(
                f"- {group['anchor']}  items={group['item_count']}  max_score={group['max_score']:.2f}  relations={top_relations}"
            )
            if group.get("review_bucket"):
                lines.append(f"  bucket: {group['review_bucket']}")
            if group.get("signal_flags"):
                lines.append(f"  flags: {', '.join(group['signal_flags'][:4])}")
            if group["labels"]:
                lines.append(f"  labels: {', '.join(group['labels'][:5])}")
            if group["items"]:
                example = group["items"][0]
                lines.append(
                    f"  example: {example['title']} [{example['relation']}]"
                )
                lines.append(f"  hint: {example['review_hint']}")
            for action in (group.get("checklist") or [])[:3]:
                lines.append(f"  review: {action}")
        if len(payload.get("groups", [])) > len(displayed_groups):
            lines.append(f"... {len(payload['groups']) - len(displayed_groups)} more groups")
    else:
        lines.append("No open entity-alias items.")
    return "\n".join(lines).rstrip()


def review_assist_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-latest.json"


def review_assist_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-latest.md"


def review_assist_batch_json_path(project_root: Path, batch_id: str) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-{batch_id}.json"


def review_assist_batch_markdown_path(project_root: Path, batch_id: str) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-{batch_id}.md"


def review_assist_batch_checklist_path(project_root: Path, batch_id: str) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-{batch_id}-checklist.md"


def review_assist_sample_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-sample-latest.json"


def review_assist_sample_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-sample-latest.md"


def review_assist_sample_session_json_path(project_root: Path, stamp: str | None = None) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-sample-{stamp or report_stamp()}.json"


def review_assist_sample_session_markdown_path(project_root: Path, stamp: str | None = None) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-sample-{stamp or report_stamp()}.md"


def review_assist_sample_summary_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-sample-summary-latest.json"


def review_assist_sample_summary_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-sample-summary-latest.md"


def review_assist_sample_summary_session_json_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-sample-summary-{stamp or report_stamp()}.json"


def review_assist_sample_summary_session_markdown_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-sample-summary-{stamp or report_stamp()}.md"


def review_assist_sample_proposal_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-sample-proposal-latest.json"


def review_assist_sample_proposal_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-sample-proposal-latest.md"


def review_assist_sample_proposal_session_json_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-sample-proposal-{stamp or report_stamp()}.json"


def review_assist_sample_proposal_session_markdown_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-sample-proposal-{stamp or report_stamp()}.md"


def review_assist_sample_compare_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-sample-compare-latest.json"


def review_assist_sample_compare_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-sample-compare-latest.md"


def review_assist_sample_compare_session_json_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-sample-compare-{stamp or report_stamp()}.json"


def review_assist_sample_compare_session_markdown_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-sample-compare-{stamp or report_stamp()}.md"


def review_assist_campaign_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-campaign-latest.json"


def review_assist_campaign_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-campaign-latest.md"


def review_assist_campaign_session_json_path(project_root: Path, stamp: str | None = None) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-campaign-{stamp or report_stamp()}.json"


def review_assist_campaign_session_markdown_path(project_root: Path, stamp: str | None = None) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-campaign-{stamp or report_stamp()}.md"


def review_assist_campaign_index_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-campaign-index-latest.json"


def review_assist_campaign_index_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-campaign-index-latest.md"


def review_assist_campaign_index_session_json_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-campaign-index-{stamp or report_stamp()}.json"


def review_assist_campaign_index_session_markdown_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-campaign-index-{stamp or report_stamp()}.md"


def review_assist_rollup_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-rollup-latest.json"


def review_assist_rollup_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-rollup-latest.md"


def review_assist_rollup_session_json_path(project_root: Path, stamp: str | None = None) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-rollup-{stamp or report_stamp()}.json"


def review_assist_rollup_session_markdown_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-rollup-{stamp or report_stamp()}.md"


def review_assist_reject_stage_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-reject-stage-latest.json"


def review_assist_reject_stage_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-reject-stage-latest.md"


def review_assist_reject_stage_session_json_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-reject-stage-{stamp or report_stamp()}.json"


def review_assist_reject_stage_session_markdown_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-reject-stage-{stamp or report_stamp()}.md"


def review_assist_packet_hydrate_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-packet-hydrate-latest.json"


def review_assist_packet_hydrate_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-packet-hydrate-latest.md"


def review_assist_packet_hydrate_session_json_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-packet-hydrate-{stamp or report_stamp()}.json"


def review_assist_packet_hydrate_session_markdown_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-packet-hydrate-{stamp or report_stamp()}.md"


def review_assist_scoreboard_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-scoreboard-latest.json"


def review_assist_scoreboard_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-scoreboard-latest.md"


def review_assist_scoreboard_session_json_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-scoreboard-{stamp or report_stamp()}.json"


def review_assist_scoreboard_session_markdown_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-scoreboard-{stamp or report_stamp()}.md"


def review_assist_apply_plan_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-apply-plan-latest.json"


def review_assist_apply_plan_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "review-assist-apply-plan-latest.md"


def review_assist_apply_plan_session_json_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-apply-plan-{stamp or report_stamp()}.json"


def review_assist_apply_plan_session_markdown_path(
    project_root: Path, stamp: str | None = None
) -> Path:
    return project_root.resolve() / "reports" / f"review-assist-apply-plan-{stamp or report_stamp()}.md"


def review_assist_report_path(
    project_root: Path,
    date_str: str | None = None,
    *,
    batch_id: str | None = None,
) -> Path:
    suffix = f"-{batch_id}" if batch_id else ""
    return project_root.resolve() / "reports" / f"review-assist-{date_str or report_date()}{suffix}.md"


def render_entity_alias_review_checklist(payload: dict[str, Any]) -> str:
    selection = payload.get("selection") or {}
    batch_label = str(selection.get("batch_id") or "full-review")
    queue_open_count = payload.get("queue_open_count", payload.get("open_count", 0))
    filtered_open_count = payload.get("filtered_open_count", payload.get("open_count", 0))
    lines = [
        f"# Entity-alias review checklist: {batch_label}",
        "",
        f"- Items: {payload.get('open_count', 0)}",
        f"- Groups: {payload.get('group_count', 0)}",
        f"- Scope: {filtered_open_count} filtered / {queue_open_count} open",
    ]
    if selection.get("batch_id"):
        lines.append(
            f"- Selected batch: {selection['batch_id']} ({selection['batch_index']}/{selection['available_batch_count']})"
        )
    lines.append("")
    for index, group in enumerate(payload.get("groups", []), start=1):
        lines.append(f"## {index}. {group['anchor']}")
        lines.append(f"- Bucket: {group.get('review_bucket', 'manual-review')}")
        if group.get("signal_flags"):
            lines.append(f"- Flags: {', '.join(group['signal_flags'])}")
        if group.get("labels"):
            lines.append(f"- Labels: {', '.join(group['labels'][:6])}")
        if group.get("example_review_ids"):
            lines.append(f"- Review IDs: {', '.join(group['example_review_ids'])}")
        if group.get("items"):
            example = group["items"][0]
            lines.append(
                f"- Example: {example['title']} [{example['relation']}] score={float(example.get('score') or 0.0):.2f}"
            )
        for action in group.get("checklist") or []:
            lines.append(f"- Review: {action}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_entity_alias_review_sample(payload: dict[str, Any]) -> str:
    sample = payload.get("sample") or {}
    selection = payload.get("selection") or {}
    group_filters = payload.get("group_filters") or {}
    queue_open_count = payload.get("queue_open_count", payload.get("open_count", 0))
    filtered_open_count = payload.get("filtered_open_count", payload.get("open_count", 0))
    lines = [
        "# Entity-alias review sample",
        "",
        f"- Items: {payload.get('open_count', 0)}",
        f"- Groups: {payload.get('group_count', 0)}",
        f"- Scope: {filtered_open_count} filtered / {queue_open_count} open",
        f"- Candidate groups: {sample.get('candidate_group_count', payload.get('group_count', 0))}",
        f"- Candidate batches: {sample.get('candidate_batch_count', payload.get('batch_count', 0))}",
        f"- Sampled groups: {sample.get('selected_group_count', payload.get('group_count', 0))}",
    ]
    if sample.get("requested_batch_offset"):
        lines.append(f"- Batch offset: {sample['requested_batch_offset']}")
    if group_filters.get("review_buckets"):
        lines.append(f"- Buckets: {', '.join(group_filters['review_buckets'])}")
    if selection.get("batch_id"):
        lines.append(
            f"- Selected batch: {selection['batch_id']} ({selection['batch_index']}/{selection['available_batch_count']})"
        )
    lines.append("")
    for index, group in enumerate(payload.get("groups") or [], start=1):
        example = (group.get("items") or [{}])[0]
        lines.append(f"## Sample {index}: {group['anchor']}")
        lines.append(f"- Bucket: {group.get('review_bucket', 'manual-review')}")
        if group.get("signal_flags"):
            lines.append(f"- Flags: {', '.join(group['signal_flags'])}")
        if group.get("labels"):
            lines.append(f"- Labels: {', '.join(group['labels'][:6])}")
        if group.get("example_review_ids"):
            lines.append(f"- Review IDs: {', '.join(group['example_review_ids'])}")
        if example:
            lines.append(
                f"- Example: {example.get('title', '')} [{example.get('relation', '')}] score={float(example.get('score') or 0.0):.2f}"
            )
        lines.append("- Proposed outcome: reject")
        lines.append("- Manual outcome: ")
        lines.append("- Notes: ")
        for action in group.get("checklist") or []:
            lines.append(f"- Review: {action}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _normalize_sample_manual_outcome(value: str) -> str:
    normalized = " ".join((value or "").strip().lower().split())
    if not normalized:
        return ""
    outcome_map = {
        "rejected": "reject",
        "reject": "reject",
        "accepted": "keep",
        "accept": "keep",
        "keep": "keep",
        "false-positive": "keep",
        "false positive": "keep",
        "needs-context": "needs-context",
        "needs context": "needs-context",
        "defer": "needs-context",
        "deferred": "needs-context",
        "pending": "pending",
        "skip": "pending",
    }
    for prefix, outcome in outcome_map.items():
        if normalized == prefix or normalized.startswith(prefix + " ") or normalized.startswith(prefix + ":"):
            return outcome
    return normalized


def parse_entity_alias_review_sample_text(text: str, *, source_path: str) -> dict[str, Any]:
    lines = text.splitlines()
    metadata: dict[str, str] = {}
    samples: list[dict[str, Any]] = []
    current_sample: dict[str, Any] | None = None

    def _finalize_sample(sample: dict[str, Any] | None) -> None:
        if sample is None:
            return
        raw_outcome = sample.get("manual_outcome_raw", "")
        sample["manual_outcome"] = _normalize_sample_manual_outcome(raw_outcome)
        samples.append(sample)

    for raw_line in lines:
        line = raw_line.rstrip()
        if line.startswith("## Sample "):
            _finalize_sample(current_sample)
            _, _, header = line.partition(":")
            current_sample = {
                "anchor": header.strip(),
                "checklist": [],
            }
            continue

        if line.startswith("- ") and ": " in line:
            key, value = line[2:].split(": ", 1)
            normalized_key = key.strip().lower().replace(" ", "_")
            if current_sample is None:
                metadata[normalized_key] = value.strip()
                continue
            if key.strip() == "Review":
                current_sample.setdefault("checklist", []).append(value.strip())
                continue
            if key.strip() == "Manual outcome":
                current_sample["manual_outcome_raw"] = value.strip()
                continue
            if key.strip() in {"Flags", "Labels", "Review IDs"}:
                current_sample[normalized_key] = [part.strip() for part in value.split(",") if part.strip()]
                continue
            current_sample[normalized_key] = value.strip()
            continue

    _finalize_sample(current_sample)
    return {
        "path": source_path,
        "metadata": metadata,
        "samples": samples,
    }


def parse_entity_alias_review_sample_markdown(path: Path) -> dict[str, Any]:
    return parse_entity_alias_review_sample_text(
        path.read_text(encoding="utf-8"),
        source_path=str(path.resolve()),
    )


def hydrate_entity_alias_review_sample_packet(path: Path) -> dict[str, Any]:
    parsed = parse_entity_alias_review_sample_markdown(path)
    summary = _summarize_entity_alias_review_sample_parsed(parsed)
    samples: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_review_ids: dict[str, int] = {}
    seen_keys: dict[str, int] = {}
    allowed_manual_outcomes = {"", "reject", "keep", "needs-context", "pending"}
    allowed_proposed_outcomes = {"", "reject", "keep", "needs-context"}
    adjudication_records: list[dict[str, Any]] = []

    for sample_index, sample in enumerate(parsed["samples"], start=1):
        anchor = str(sample.get("anchor") or "").strip()
        bucket = str(sample.get("bucket") or "").strip()
        proposed_outcome = str(sample.get("proposed_outcome") or "").strip().lower()
        manual_outcome_raw = str(sample.get("manual_outcome_raw") or "").strip()
        manual_outcome = str(sample.get("manual_outcome") or "").strip()
        review_ids = [value for value in sample.get("review_ids") or [] if value]
        packet_key = _review_sample_key(sample)

        if not anchor:
            errors.append(
                {
                    "type": "missing-anchor",
                    "sample_index": sample_index,
                    "message": "Sample is missing an anchor heading.",
                }
            )
        if not bucket:
            warnings.append(
                {
                    "type": "missing-bucket",
                    "sample_index": sample_index,
                    "anchor": anchor,
                    "message": "Sample is missing an explicit bucket value.",
                }
            )
        if proposed_outcome not in allowed_proposed_outcomes:
            errors.append(
                {
                    "type": "invalid-proposed-outcome",
                    "sample_index": sample_index,
                    "anchor": anchor,
                    "message": f"Unsupported proposed outcome: {proposed_outcome or '<blank>'}.",
                }
            )
        if manual_outcome not in allowed_manual_outcomes:
            errors.append(
                {
                    "type": "invalid-manual-outcome",
                    "sample_index": sample_index,
                    "anchor": anchor,
                    "message": f"Unsupported manual outcome: {manual_outcome_raw or '<blank>'}.",
                }
            )
        if not review_ids:
            warnings.append(
                {
                    "type": "missing-review-ids",
                    "sample_index": sample_index,
                    "anchor": anchor,
                    "message": "Sample has no review IDs; future staging will not be able to target queue items safely.",
                }
            )
        for review_id in review_ids:
            if review_id in seen_review_ids:
                errors.append(
                    {
                        "type": "duplicate-review-id",
                        "sample_index": sample_index,
                        "anchor": anchor,
                        "message": f"Review ID {review_id} is duplicated in samples {seen_review_ids[review_id]} and {sample_index}.",
                    }
                )
            else:
                seen_review_ids[review_id] = sample_index
        if packet_key:
            if packet_key in seen_keys:
                warnings.append(
                    {
                        "type": "duplicate-packet-key",
                        "sample_index": sample_index,
                        "anchor": anchor,
                        "message": f"Sample key duplicates sample {seen_keys[packet_key]}; downstream grouping may collapse these records.",
                    }
                )
            else:
                seen_keys[packet_key] = sample_index
        if manual_outcome in {"reject", "keep", "needs-context"}:
            adjudication_records.append(
                {
                    "sample_index": sample_index,
                    "anchor": anchor,
                    "bucket": bucket or "manual-review",
                    "review_ids": review_ids,
                    "proposed_outcome": proposed_outcome,
                    "manual_outcome": manual_outcome,
                    "notes": sample.get("notes", ""),
                }
            )

        samples.append(
            {
                **sample,
                "sample_index": sample_index,
                "packet_key": packet_key,
                "review_ids": review_ids,
                "bucket": bucket or "manual-review",
                "proposed_outcome": proposed_outcome,
                "manual_outcome_raw": manual_outcome_raw,
                "manual_outcome": manual_outcome,
            }
        )

    return {
        "generated_at": now_iso(),
        "source_path": parsed["path"],
        "metadata": parsed["metadata"],
        "packet_id": _sample_packet_id_from_path(Path(parsed["path"])) or "",
        **summary,
        "valid": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "unique_review_id_count": len(seen_review_ids),
        "adjudication_record_count": len(adjudication_records),
        "adjudication_records": adjudication_records,
        "samples": samples,
    }


def _summarize_entity_alias_review_sample_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    samples = parsed["samples"]
    outcome_counts: dict[str, int] = {}
    bucket_counts: dict[str, int] = {}
    bucket_outcomes: dict[str, dict[str, int]] = {}
    adjudicated_count = 0
    decisive_count = 0
    confirmed_reject_count = 0
    false_positive_count = 0
    needs_context_count = 0
    pending_count = 0

    for sample in samples:
        bucket = sample.get("bucket", "manual-review") or "manual-review"
        outcome = sample.get("manual_outcome", "")
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if outcome:
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
            bucket_entry = bucket_outcomes.setdefault(bucket, {})
            bucket_entry[outcome] = bucket_entry.get(outcome, 0) + 1
            adjudicated_count += 1
        if outcome == "reject":
            decisive_count += 1
            confirmed_reject_count += 1
        elif outcome == "keep":
            decisive_count += 1
            false_positive_count += 1
        elif outcome == "needs-context":
            needs_context_count += 1
        else:
            pending_count += 1

    total_samples = len(samples)
    completion_rate = round(adjudicated_count / total_samples, 4) if total_samples else 0.0
    reject_precision = round(confirmed_reject_count / decisive_count, 4) if decisive_count else None
    bucket_summary: dict[str, dict[str, Any]] = {}
    for bucket, count in bucket_counts.items():
        outcomes = bucket_outcomes.get(bucket, {})
        bucket_decisive = outcomes.get("reject", 0) + outcomes.get("keep", 0)
        bucket_summary[bucket] = {
            "group_count": count,
            "outcome_counts": outcomes,
            "reject_precision": round(outcomes.get("reject", 0) / bucket_decisive, 4)
            if bucket_decisive
            else None,
        }

    return {
        "generated_at": now_iso(),
        "source_path": parsed["path"],
        "metadata": parsed["metadata"],
        "total_samples": total_samples,
        "adjudicated_count": adjudicated_count,
        "decisive_count": decisive_count,
        "confirmed_reject_count": confirmed_reject_count,
        "false_positive_count": false_positive_count,
        "needs_context_count": needs_context_count,
        "pending_count": pending_count,
        "completion_rate": completion_rate,
        "reject_precision": reject_precision,
        "bucket_counts": bucket_counts,
        "outcome_counts": outcome_counts,
        "bucket_summary": bucket_summary,
        "samples": samples,
    }


def summarize_entity_alias_review_sample(path: Path) -> dict[str, Any]:
    parsed = parse_entity_alias_review_sample_markdown(path)
    return _summarize_entity_alias_review_sample_parsed(parsed)


def _assistant_outcome_for_review_sample(sample: dict[str, Any]) -> tuple[str, str, list[str]]:
    bucket = sample.get("bucket", "manual-review") or "manual-review"
    flags = set(sample.get("flags") or [])
    reasons: list[str] = []
    if bucket == "likely-reject":
        reasons.append("Group is already classified as likely-reject.")
        if "all-zero-overlap" in flags:
            reasons.append("Lexical overlap is absent across the sampled pairs.")
        if "has-low-specificity-labels" in flags:
            reasons.append("At least one label looks like a heading, fragment, placeholder, or extraction residue.")
        if "has-high-score-disjoint-pairs" in flags:
            reasons.append("Queue score is still high, so contextual inspection remains warranted.")
            return "needs-context", "medium", reasons
        confidence = "high" if "all-zero-overlap" in flags else "medium"
        return "reject", confidence, reasons
    if bucket == "needs-context":
        reasons.append("Group bucket explicitly requires contextual inspection before rejection.")
        return "needs-context", "medium", reasons
    if bucket == "alias-check":
        reasons.append("Lexical overlap is strong enough that rejection is not the safe default.")
        return "keep", "medium", reasons
    reasons.append("Mixed signals remain; default to contextual review rather than automatic rejection.")
    return "needs-context", "low", reasons


def _propose_entity_alias_review_sample_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    outcome_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    for sample in parsed["samples"]:
        assistant_outcome, confidence, rationale = _assistant_outcome_for_review_sample(sample)
        proposed = {
            **sample,
            "assistant_outcome": assistant_outcome,
            "assistant_confidence": confidence,
            "assistant_rationale": rationale,
        }
        samples.append(proposed)
        outcome_counts[assistant_outcome] = outcome_counts.get(assistant_outcome, 0) + 1
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1
    return {
        "generated_at": now_iso(),
        "source_path": parsed["path"],
        "metadata": parsed["metadata"],
        "total_samples": len(samples),
        "assistant_outcome_counts": outcome_counts,
        "assistant_confidence_counts": confidence_counts,
        "samples": samples,
    }


def propose_entity_alias_review_sample(path: Path) -> dict[str, Any]:
    parsed = parse_entity_alias_review_sample_markdown(path)
    return _propose_entity_alias_review_sample_parsed(parsed)


def _review_sample_key(sample: dict[str, Any]) -> str:
    review_ids = [value for value in sample.get("review_ids") or [] if value]
    if review_ids:
        return "|".join(review_ids)
    return str(sample.get("anchor") or "")


def load_entity_alias_review_sample_proposal(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "samples" not in payload:
        raise ValueError(f"Invalid review sample proposal payload: {path}")
    return payload


def _compare_entity_alias_review_sample_summary_to_proposal(
    sample_summary: dict[str, Any],
    proposal_payload: dict[str, Any],
    *,
    sample_path: str,
    proposal_path: str,
) -> dict[str, Any]:
    sample_map = {_review_sample_key(sample): sample for sample in sample_summary.get("samples", [])}
    proposal_map = {_review_sample_key(sample): sample for sample in proposal_payload.get("samples", [])}

    matched_keys = [key for key in sample_map if key in proposal_map]
    unmatched_manual = [sample_map[key].get("anchor", key) for key in sample_map if key not in proposal_map]
    unmatched_proposal = [proposal_map[key].get("anchor", key) for key in proposal_map if key not in sample_map]

    adjudicated_count = 0
    comparable_count = 0
    agreement_count = 0
    disagreement_count = 0
    proposal_reject_count = 0
    proposal_keep_count = 0
    proposal_needs_context_count = 0
    proposal_reject_hits = 0
    proposal_reject_false_positives = 0
    disagreements: list[dict[str, Any]] = []
    confidence_summary: dict[str, dict[str, int | float | None]] = {}

    for key in matched_keys:
        manual = sample_map[key]
        proposal = proposal_map[key]
        manual_outcome = manual.get("manual_outcome", "")
        assistant_outcome = proposal.get("assistant_outcome", "")
        confidence = proposal.get("assistant_confidence", "unknown") or "unknown"
        summary = confidence_summary.setdefault(
            confidence,
            {
                "count": 0,
                "adjudicated_count": 0,
                "agreement_count": 0,
                "disagreement_count": 0,
                "proposal_reject_count": 0,
                "proposal_reject_hits": 0,
                "proposal_reject_false_positives": 0,
                "reject_precision": None,
            },
        )
        summary["count"] = int(summary["count"]) + 1

        if assistant_outcome == "reject":
            proposal_reject_count += 1
            summary["proposal_reject_count"] = int(summary["proposal_reject_count"]) + 1
        elif assistant_outcome == "keep":
            proposal_keep_count += 1
        elif assistant_outcome == "needs-context":
            proposal_needs_context_count += 1

        if not manual_outcome:
            continue
        adjudicated_count += 1
        summary["adjudicated_count"] = int(summary["adjudicated_count"]) + 1
        if manual_outcome not in {"reject", "keep", "needs-context"}:
            continue
        comparable_count += 1
        if assistant_outcome == manual_outcome:
            agreement_count += 1
            summary["agreement_count"] = int(summary["agreement_count"]) + 1
        else:
            disagreement_count += 1
            summary["disagreement_count"] = int(summary["disagreement_count"]) + 1
            disagreements.append(
                {
                    "anchor": manual.get("anchor", ""),
                    "manual_outcome": manual_outcome,
                    "assistant_outcome": assistant_outcome,
                    "assistant_confidence": confidence,
                    "notes": manual.get("notes", ""),
                    "assistant_rationale": proposal.get("assistant_rationale") or [],
                }
            )
        if assistant_outcome == "reject":
            if manual_outcome == "reject":
                proposal_reject_hits += 1
                summary["proposal_reject_hits"] = int(summary["proposal_reject_hits"]) + 1
            elif manual_outcome == "keep":
                proposal_reject_false_positives += 1
                summary["proposal_reject_false_positives"] = int(
                    summary["proposal_reject_false_positives"]
                ) + 1

    for summary in confidence_summary.values():
        reject_count = int(summary["proposal_reject_hits"]) + int(
            summary["proposal_reject_false_positives"]
        )
        hits = int(summary["proposal_reject_hits"])
        summary["reject_precision"] = round(hits / reject_count, 4) if reject_count else None

    agreement_rate = round(agreement_count / comparable_count, 4) if comparable_count else None
    reject_denominator = proposal_reject_hits + proposal_reject_false_positives
    reject_precision = round(proposal_reject_hits / reject_denominator, 4) if reject_denominator else None
    return {
        "generated_at": now_iso(),
        "sample_path": sample_path,
        "proposal_path": proposal_path,
        "total_manual_samples": len(sample_map),
        "total_proposal_samples": len(proposal_map),
        "matched_samples": len(matched_keys),
        "unmatched_manual_samples": unmatched_manual,
        "unmatched_proposal_samples": unmatched_proposal,
        "adjudicated_count": adjudicated_count,
        "comparable_count": comparable_count,
        "agreement_count": agreement_count,
        "disagreement_count": disagreement_count,
        "agreement_rate": agreement_rate,
        "proposal_reject_count": proposal_reject_count,
        "proposal_keep_count": proposal_keep_count,
        "proposal_needs_context_count": proposal_needs_context_count,
        "proposal_reject_hits": proposal_reject_hits,
        "proposal_reject_false_positives": proposal_reject_false_positives,
        "proposal_reject_precision": reject_precision,
        "confidence_summary": confidence_summary,
        "disagreements": disagreements,
    }


def compare_entity_alias_review_sample_to_proposal(sample_path: Path, proposal_path: Path) -> dict[str, Any]:
    sample_summary = summarize_entity_alias_review_sample(sample_path)
    proposal_payload = load_entity_alias_review_sample_proposal(proposal_path)
    return _compare_entity_alias_review_sample_summary_to_proposal(
        sample_summary,
        proposal_payload,
        sample_path=str(sample_path.resolve()),
        proposal_path=str(proposal_path.resolve()),
    )


def render_entity_alias_review_sample_summary(payload: dict[str, Any]) -> str:
    precision = payload.get("reject_precision")
    precision_text = "n/a" if precision is None else f"{precision:.2%}"
    lines = [
        "Entity-alias review sample summary",
        f"Source: {payload['source_path']}",
        f"Samples: {payload['total_samples']}  Adjudicated: {payload['adjudicated_count']}  Decisive: {payload['decisive_count']}",
        f"Reject precision: {precision_text}",
        f"Confirmed rejects: {payload['confirmed_reject_count']}  False positives: {payload['false_positive_count']}  Needs context: {payload['needs_context_count']}  Pending: {payload['pending_count']}",
    ]
    metadata = payload.get("metadata") or {}
    if metadata:
        parts = []
        if metadata.get("scope"):
            parts.append(f"scope={metadata['scope']}")
        if metadata.get("buckets"):
            parts.append(f"buckets={metadata['buckets']}")
        if metadata.get("sampled_groups"):
            parts.append(f"sampled_groups={metadata['sampled_groups']}")
        if parts:
            lines.append("Packet: " + "  ".join(parts))
    if payload.get("bucket_summary"):
        bucket_line = ", ".join(
            f"{bucket}={summary['group_count']}"
            for bucket, summary in sorted(
                payload["bucket_summary"].items(), key=lambda item: (-item[1]["group_count"], item[0])
            )
        )
        lines.append(f"Buckets: {bucket_line}")
    lines.append("")
    for sample in payload.get("samples", [])[:10]:
        outcome = sample.get("manual_outcome") or "pending"
        lines.append(
            f"- {sample.get('anchor', 'unknown')}  bucket={sample.get('bucket', 'manual-review')}  proposed={sample.get('proposed_outcome', 'reject')}  manual={outcome}"
        )
        if sample.get("notes"):
            lines.append(f"  notes: {sample['notes']}")
    remaining = len(payload.get("samples", [])) - min(len(payload.get("samples", [])), 10)
    if remaining > 0:
        lines.append(f"... {remaining} more samples")
    return "\n".join(lines).rstrip()


def render_entity_alias_review_sample_proposal(payload: dict[str, Any]) -> str:
    lines = [
        "Entity-alias review sample proposal",
        f"Source: {payload['source_path']}",
        f"Samples: {payload['total_samples']}",
    ]
    metadata = payload.get("metadata") or {}
    if metadata:
        parts = []
        if metadata.get("scope"):
            parts.append(f"scope={metadata['scope']}")
        if metadata.get("buckets"):
            parts.append(f"buckets={metadata['buckets']}")
        if metadata.get("sampled_groups"):
            parts.append(f"sampled_groups={metadata['sampled_groups']}")
        if parts:
            lines.append("Packet: " + "  ".join(parts))
    if payload.get("assistant_outcome_counts"):
        outcome_line = ", ".join(
            f"{outcome}={count}"
            for outcome, count in sorted(
                payload["assistant_outcome_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Assistant outcomes: {outcome_line}")
    if payload.get("assistant_confidence_counts"):
        confidence_line = ", ".join(
            f"{level}={count}"
            for level, count in sorted(
                payload["assistant_confidence_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Assistant confidence: {confidence_line}")
    lines.append("")
    for sample in payload.get("samples", []):
        lines.append(
            f"- {sample.get('anchor', 'unknown')}  bucket={sample.get('bucket', 'manual-review')}  assistant={sample.get('assistant_outcome', 'needs-context')}  confidence={sample.get('assistant_confidence', 'low')}"
        )
        if sample.get("manual_outcome"):
            lines.append(f"  manual: {sample['manual_outcome']}")
        for reason in sample.get("assistant_rationale") or []:
            lines.append(f"  rationale: {reason}")
        if sample.get("notes"):
            lines.append(f"  notes: {sample['notes']}")
    return "\n".join(lines).rstrip()


def render_entity_alias_review_sample_comparison(payload: dict[str, Any]) -> str:
    precision = payload.get("proposal_reject_precision")
    precision_text = "n/a" if precision is None else f"{precision:.2%}"
    agreement = payload.get("agreement_rate")
    agreement_text = "n/a" if agreement is None else f"{agreement:.2%}"
    lines = [
        "Entity-alias review sample comparison",
        f"Sample: {payload['sample_path']}",
        f"Proposal: {payload['proposal_path']}",
        f"Matched: {payload['matched_samples']}  Adjudicated: {payload['adjudicated_count']}  Comparable: {payload['comparable_count']}",
        f"Agreement: {payload['agreement_count']}  Disagreement: {payload['disagreement_count']}  Agreement rate: {agreement_text}",
        f"Proposal reject precision: {precision_text}",
        f"Proposal rejects: {payload['proposal_reject_count']}  Hits: {payload['proposal_reject_hits']}  False positives: {payload['proposal_reject_false_positives']}",
    ]
    if payload.get("confidence_summary"):
        confidence_line = ", ".join(
            f"{level}={summary['count']}"
            for level, summary in sorted(
                payload["confidence_summary"].items(), key=lambda item: (-int(item[1]["count"]), item[0])
            )
        )
        lines.append(f"Confidence: {confidence_line}")
    if payload.get("disagreements"):
        lines.append("")
        lines.append("Disagreements:")
        for item in payload["disagreements"][:10]:
            lines.append(
                f"- {item['anchor']}  manual={item['manual_outcome']}  assistant={item['assistant_outcome']}  confidence={item['assistant_confidence']}"
            )
            if item.get("notes"):
                lines.append(f"  notes: {item['notes']}")
            for reason in item.get("assistant_rationale") or []:
                lines.append(f"  rationale: {reason}")
        if len(payload["disagreements"]) > 10:
            lines.append(f"... {len(payload['disagreements']) - 10} more disagreements")
    return "\n".join(lines).rstrip()


def write_entity_alias_review_sample_artifacts(
    project_root: Path,
    payload: dict[str, Any],
    *,
    write_latest: bool = True,
    stamp: str | None = None,
) -> dict[str, str]:
    latest_json = review_assist_sample_latest_json_path(project_root)
    latest_markdown = review_assist_sample_latest_markdown_path(project_root)
    stamp = stamp or report_stamp()
    session_json = review_assist_sample_session_json_path(project_root, stamp)
    session_markdown = review_assist_sample_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_review_sample(payload)
    if write_latest:
        write_json(latest_json, payload)
        write_markdown(latest_markdown, rendered)
    write_json(session_json, payload)
    write_markdown(session_markdown, rendered)
    artifacts = {
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
    }
    if write_latest:
        artifacts["latest_json_path"] = str(latest_json)
        artifacts["latest_markdown_path"] = str(latest_markdown)
    return artifacts


def write_entity_alias_review_sample_summary_artifacts(
    project_root: Path,
    payload: dict[str, Any],
    *,
    write_latest: bool = True,
    stamp: str | None = None,
) -> dict[str, str]:
    latest_json = review_assist_sample_summary_latest_json_path(project_root)
    latest_markdown = review_assist_sample_summary_latest_markdown_path(project_root)
    stamp = stamp or report_stamp()
    session_json = review_assist_sample_summary_session_json_path(project_root, stamp)
    session_markdown = review_assist_sample_summary_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_review_sample_summary(payload)
    if write_latest:
        write_json(latest_json, payload)
        write_markdown(latest_markdown, rendered)
    write_json(session_json, payload)
    write_markdown(session_markdown, rendered)
    artifacts = {
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
    }
    if write_latest:
        artifacts["latest_json_path"] = str(latest_json)
        artifacts["latest_markdown_path"] = str(latest_markdown)
    return artifacts


def write_entity_alias_review_sample_proposal_artifacts(
    project_root: Path,
    payload: dict[str, Any],
    *,
    write_latest: bool = True,
    stamp: str | None = None,
) -> dict[str, str]:
    latest_json = review_assist_sample_proposal_latest_json_path(project_root)
    latest_markdown = review_assist_sample_proposal_latest_markdown_path(project_root)
    stamp = stamp or report_stamp()
    session_json = review_assist_sample_proposal_session_json_path(project_root, stamp)
    session_markdown = review_assist_sample_proposal_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_review_sample_proposal(payload)
    if write_latest:
        write_json(latest_json, payload)
        write_markdown(latest_markdown, rendered)
    write_json(session_json, payload)
    write_markdown(session_markdown, rendered)
    artifacts = {
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
    }
    if write_latest:
        artifacts["latest_json_path"] = str(latest_json)
        artifacts["latest_markdown_path"] = str(latest_markdown)
    return artifacts


def write_entity_alias_review_sample_comparison_artifacts(
    project_root: Path,
    payload: dict[str, Any],
    *,
    write_latest: bool = True,
    stamp: str | None = None,
) -> dict[str, str]:
    latest_json = review_assist_sample_compare_latest_json_path(project_root)
    latest_markdown = review_assist_sample_compare_latest_markdown_path(project_root)
    stamp = stamp or report_stamp()
    session_json = review_assist_sample_compare_session_json_path(project_root, stamp)
    session_markdown = review_assist_sample_compare_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_review_sample_comparison(payload)
    if write_latest:
        write_json(latest_json, payload)
        write_markdown(latest_markdown, rendered)
    write_json(session_json, payload)
    write_markdown(session_markdown, rendered)
    artifacts = {
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
    }
    if write_latest:
        artifacts["latest_json_path"] = str(latest_json)
        artifacts["latest_markdown_path"] = str(latest_markdown)
    return artifacts


def _campaign_scenarios(
    *,
    scenario_labels: list[str] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if scenarios is not None:
        return [{**scenario} for scenario in scenarios]
    catalog = {entry["label"]: {**entry} for entry in STANDARD_ENTITY_ALIAS_REVIEW_CAMPAIGN_SCENARIOS}
    if not scenario_labels:
        return list(catalog.values())
    unknown = [label for label in scenario_labels if label not in catalog]
    if unknown:
        available = ", ".join(sorted(catalog))
        raise ValueError(f"Unknown review campaign scenario(s): {', '.join(sorted(set(unknown)))}. Available scenarios: {available}")
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label in scenario_labels:
        if label in seen:
            continue
        selected.append(catalog[label])
        seen.add(label)
    return selected


def _merge_count_maps(*mappings: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for mapping in mappings:
        for key, value in mapping.items():
            merged[key] = merged.get(key, 0) + int(value)
    return merged


def _load_json_artifact(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object payload: {path}")
    return payload


def _sample_packet_id_from_path(path: Path) -> str | None:
    name = path.name
    prefix = "review-assist-sample-"
    if not name.startswith(prefix) or not name.endswith(".md"):
        return None
    suffix = name[len(prefix) : -3]
    if not suffix or suffix == "latest":
        return None
    if suffix.startswith("summary-") or suffix.startswith("proposal-") or suffix.startswith("compare-"):
        return None
    return suffix


def _campaign_id_from_path(path: Path) -> str | None:
    name = path.name
    prefix = "review-assist-campaign-"
    if not name.startswith(prefix) or not name.endswith(".json"):
        return None
    suffix = name[len(prefix) : -5]
    if not suffix or suffix == "latest":
        return None
    if suffix.startswith("index-"):
        return None
    return suffix


def _packet_scenario_label(packet_id: str) -> str:
    for scenario in STANDARD_ENTITY_ALIAS_REVIEW_CAMPAIGN_SCENARIOS:
        label = str(scenario["label"])
        if packet_id.endswith(f"-{label}"):
            return label
    return ""


def _review_packet_status(*, total_samples: int, adjudicated_count: int) -> str:
    if total_samples <= 0:
        return "empty"
    if adjudicated_count <= 0:
        return "pending"
    if adjudicated_count >= total_samples:
        return "complete"
    return "partial"


def _select_review_packets(
    packets: list[dict[str, Any]],
    *,
    packet_statuses: list[str] | None = None,
    scenario_labels: list[str] | None = None,
    packet_ids: list[str] | None = None,
    campaign_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    status_set = {value for value in packet_statuses or [] if value}
    scenario_set = {value for value in scenario_labels or [] if value}
    packet_id_set = {value for value in packet_ids or [] if value}
    campaign_id_set = {value for value in campaign_ids or [] if value}
    selected: list[dict[str, Any]] = []
    for packet in packets:
        if status_set and packet.get("status") not in status_set:
            continue
        if scenario_set and packet.get("scenario_label") not in scenario_set:
            continue
        if packet_id_set and packet.get("packet_id") not in packet_id_set:
            continue
        if campaign_id_set and not campaign_id_set.intersection(packet.get("campaign_ids") or []):
            continue
        selected.append(packet)
    return selected


def _proposal_artifacts_by_sample_path(reports_root: Path) -> dict[str, dict[str, Any]]:
    proposals: dict[str, dict[str, Any]] = {}
    for proposal_path in sorted(reports_root.glob("review-assist-sample-proposal-*.json")):
        if proposal_path.name == "review-assist-sample-proposal-latest.json":
            continue
        payload = _load_json_artifact(proposal_path)
        source_path = str(payload.get("source_path") or "").strip()
        if not source_path:
            continue
        key = str(Path(source_path).resolve())
        existing = proposals.get(key)
        if existing is None or Path(existing["artifact_path"]).name < proposal_path.name:
            proposals[key] = {
                "artifact_path": str(proposal_path.resolve()),
                "payload": payload,
            }
    return proposals


def _comparison_artifacts_by_sample_path(reports_root: Path) -> dict[str, dict[str, Any]]:
    comparisons: dict[str, dict[str, Any]] = {}
    for compare_path in sorted(reports_root.glob("review-assist-sample-compare-*.json")):
        if compare_path.name == "review-assist-sample-compare-latest.json":
            continue
        payload = _load_json_artifact(compare_path)
        sample_path = str(payload.get("sample_path") or "").strip()
        if not sample_path:
            continue
        key = str(Path(sample_path).resolve())
        existing = comparisons.get(key)
        if existing is None or Path(existing["artifact_path"]).name < compare_path.name:
            comparisons[key] = {
                "artifact_path": str(compare_path.resolve()),
                "payload": payload,
            }
    return comparisons


def build_entity_alias_review_campaign(
    project_root: Path,
    *,
    batch_size: int = 25,
    scenario_labels: list[str] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selected_scenarios = _campaign_scenarios(
        scenario_labels=scenario_labels,
        scenarios=scenarios,
    )
    scenario_payloads: list[dict[str, Any]] = []
    aggregated_summary_counts: dict[str, int] = {}
    aggregated_outcome_counts: dict[str, int] = {}
    aggregated_confidence_counts: dict[str, int] = {}
    sampled_group_count = 0
    sampled_item_count = 0
    adjudicated_count = 0
    proposal_reject_count = 0
    proposal_reject_hits = 0
    proposal_reject_false_positives = 0

    for scenario in selected_scenarios:
        assist_payload = build_entity_alias_review_assist(
            project_root,
            batch_size=batch_size,
            relation_filters=scenario.get("relation_filters"),
            source_pair=scenario.get("source_pair"),
            anchor_contains=scenario.get("anchor_contains"),
        )
        if scenario.get("batch_id"):
            assist_payload = select_entity_alias_review_assist_batch(
                assist_payload,
                str(scenario["batch_id"]),
            )
        filtered_payload = filter_entity_alias_review_assist_groups(
            assist_payload,
            review_bucket_filters=scenario.get("review_buckets"),
        )
        sample_payload = sample_entity_alias_review_assist_groups(
            filtered_payload,
            sample_groups=int(scenario.get("sample_groups") or 1),
            sample_batches=(
                int(scenario["sample_batches"])
                if scenario.get("sample_batches") is not None
                else None
            ),
            batch_offset=int(scenario.get("batch_offset") or 0),
        )
        sample_path = f"campaign:{scenario['label']}:sample"
        proposal_path = f"campaign:{scenario['label']}:proposal"
        parsed_sample = parse_entity_alias_review_sample_text(
            render_entity_alias_review_sample(sample_payload),
            source_path=sample_path,
        )
        summary_payload = _summarize_entity_alias_review_sample_parsed(parsed_sample)
        proposal_payload = _propose_entity_alias_review_sample_parsed(parsed_sample)
        comparison_payload = _compare_entity_alias_review_sample_summary_to_proposal(
            summary_payload,
            proposal_payload,
            sample_path=sample_path,
            proposal_path=proposal_path,
        )
        scenario_payload = {
            **scenario,
            "sample_payload": sample_payload,
            "summary_payload": summary_payload,
            "proposal_payload": proposal_payload,
            "comparison_payload": comparison_payload,
        }
        scenario_payloads.append(scenario_payload)
        sampled_group_count += summary_payload.get("total_samples", 0)
        sampled_item_count += sample_payload.get("open_count", 0)
        adjudicated_count += comparison_payload.get("adjudicated_count", 0)
        proposal_reject_count += comparison_payload.get("proposal_reject_count", 0)
        proposal_reject_hits += comparison_payload.get("proposal_reject_hits", 0)
        proposal_reject_false_positives += comparison_payload.get(
            "proposal_reject_false_positives", 0
        )
        aggregated_summary_counts = _merge_count_maps(
            aggregated_summary_counts,
            summary_payload.get("bucket_counts") or {},
        )
        aggregated_outcome_counts = _merge_count_maps(
            aggregated_outcome_counts,
            proposal_payload.get("assistant_outcome_counts") or {},
        )
        aggregated_confidence_counts = _merge_count_maps(
            aggregated_confidence_counts,
            proposal_payload.get("assistant_confidence_counts") or {},
        )

    reject_denominator = proposal_reject_hits + proposal_reject_false_positives
    return {
        "generated_at": now_iso(),
        "project_root": str(project_root.resolve()),
        "batch_size": batch_size,
        "available_scenarios": [entry["label"] for entry in STANDARD_ENTITY_ALIAS_REVIEW_CAMPAIGN_SCENARIOS],
        "selected_scenarios": [scenario["label"] for scenario in selected_scenarios],
        "scenario_count": len(scenario_payloads),
        "sampled_group_count": sampled_group_count,
        "sampled_item_count": sampled_item_count,
        "adjudicated_count": adjudicated_count,
        "assistant_outcome_counts": aggregated_outcome_counts,
        "assistant_confidence_counts": aggregated_confidence_counts,
        "bucket_counts": aggregated_summary_counts,
        "proposal_reject_count": proposal_reject_count,
        "proposal_reject_hits": proposal_reject_hits,
        "proposal_reject_false_positives": proposal_reject_false_positives,
        "proposal_reject_precision": round(proposal_reject_hits / reject_denominator, 4)
        if reject_denominator
        else None,
        "scenarios": scenario_payloads,
    }


def render_entity_alias_review_campaign(payload: dict[str, Any]) -> str:
    precision = payload.get("proposal_reject_precision")
    precision_text = "n/a" if precision is None else f"{precision:.2%}"
    lines = [
        "Entity-alias review campaign",
        f"Project: {payload['project_root']}",
        f"Scenarios: {payload['scenario_count']}  Batch size: {payload['batch_size']}",
        f"Sampled groups: {payload['sampled_group_count']}  Sampled items: {payload['sampled_item_count']}  Adjudicated: {payload['adjudicated_count']}",
        f"Proposal reject precision: {precision_text}",
    ]
    if payload.get("assistant_outcome_counts"):
        outcome_line = ", ".join(
            f"{outcome}={count}"
            for outcome, count in sorted(
                payload["assistant_outcome_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Assistant outcomes: {outcome_line}")
    if payload.get("assistant_confidence_counts"):
        confidence_line = ", ".join(
            f"{level}={count}"
            for level, count in sorted(
                payload["assistant_confidence_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Assistant confidence: {confidence_line}")
    lines.append("")
    for scenario in payload.get("scenarios", []):
        sample_payload = scenario.get("sample_payload") or {}
        sample_meta = sample_payload.get("sample") or {}
        summary_payload = scenario.get("summary_payload") or {}
        proposal_payload = scenario.get("proposal_payload") or {}
        comparison_payload = scenario.get("comparison_payload") or {}
        scenario_precision = comparison_payload.get("proposal_reject_precision")
        scenario_precision_text = "n/a" if scenario_precision is None else f"{scenario_precision:.2%}"
        lines.append(f"- {scenario['label']}: {scenario.get('description', '')}")
        lines.append(
            "  sample: "
            f"groups={summary_payload.get('total_samples', 0)} "
            f"items={sample_payload.get('open_count', 0)} "
            f"candidate_groups={sample_meta.get('candidate_group_count', 0)} "
            f"candidate_batches={sample_meta.get('candidate_batch_count', 0)} "
            f"batch_offset={sample_meta.get('requested_batch_offset', 0)}"
        )
        if proposal_payload.get("assistant_outcome_counts"):
            outcome_line = ", ".join(
                f"{outcome}={count}"
                for outcome, count in sorted(
                    proposal_payload["assistant_outcome_counts"].items(),
                    key=lambda item: (-item[1], item[0]),
                )
            )
            lines.append(f"  assistant: {outcome_line}")
        lines.append(
            "  compare: "
            f"adjudicated={comparison_payload.get('adjudicated_count', 0)} "
            f"agreement={comparison_payload.get('agreement_count', 0)} "
            f"disagreement={comparison_payload.get('disagreement_count', 0)} "
            f"reject_precision={scenario_precision_text}"
        )
        if scenario.get("artifacts"):
            lines.append(f"  sample_artifact: {scenario['artifacts']['sample']['session_markdown_path']}")
            lines.append(f"  proposal_artifact: {scenario['artifacts']['proposal']['session_markdown_path']}")
            lines.append(f"  compare_artifact: {scenario['artifacts']['comparison']['session_markdown_path']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def write_entity_alias_review_campaign_artifacts(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    stamp = report_stamp()
    scenario_artifacts: dict[str, dict[str, dict[str, str]]] = {}
    persisted_scenarios: list[dict[str, Any]] = []
    for scenario in payload.get("scenarios", []):
        scenario_stamp = f"{stamp}-{scenario['label']}"
        artifacts = {
            "sample": write_entity_alias_review_sample_artifacts(
                project_root,
                scenario["sample_payload"],
                write_latest=False,
                stamp=scenario_stamp,
            ),
            "summary": write_entity_alias_review_sample_summary_artifacts(
                project_root,
                scenario["summary_payload"],
                write_latest=False,
                stamp=scenario_stamp,
            ),
            "proposal": write_entity_alias_review_sample_proposal_artifacts(
                project_root,
                scenario["proposal_payload"],
                write_latest=False,
                stamp=scenario_stamp,
            ),
            "comparison": write_entity_alias_review_sample_comparison_artifacts(
                project_root,
                scenario["comparison_payload"],
                write_latest=False,
                stamp=scenario_stamp,
            ),
        }
        scenario_artifacts[scenario["label"]] = artifacts
        persisted_scenarios.append({**scenario, "artifacts": artifacts})

    persisted_payload = {
        **payload,
        "scenarios": persisted_scenarios,
    }
    latest_json = review_assist_campaign_latest_json_path(project_root)
    latest_markdown = review_assist_campaign_latest_markdown_path(project_root)
    session_json = review_assist_campaign_session_json_path(project_root, stamp)
    session_markdown = review_assist_campaign_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_review_campaign(persisted_payload)
    write_json(latest_json, persisted_payload)
    write_markdown(latest_markdown, rendered)
    write_json(session_json, persisted_payload)
    write_markdown(session_markdown, rendered)
    return {
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_markdown),
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
        "scenario_artifacts": scenario_artifacts,
    }


def build_entity_alias_review_campaign_index(project_root: Path) -> dict[str, Any]:
    reports_root = project_root.resolve() / "reports"
    proposal_artifacts = _proposal_artifacts_by_sample_path(reports_root)
    comparison_artifacts = _comparison_artifacts_by_sample_path(reports_root)
    packet_records: list[dict[str, Any]] = []
    packet_by_sample_path: dict[str, dict[str, Any]] = {}
    packet_status_counts: dict[str, int] = {}
    scenario_counts: dict[str, int] = {}
    proposal_packet_count = 0
    comparison_packet_count = 0
    adjudicated_count = 0
    total_samples = 0
    invalid_packet_count = 0

    for sample_path in sorted(reports_root.glob("review-assist-sample-*.md")):
        packet_id = _sample_packet_id_from_path(sample_path)
        if not packet_id:
            continue
        hydration_payload = hydrate_entity_alias_review_sample_packet(sample_path)
        sample_key = str(sample_path.resolve())
        proposal_entry = proposal_artifacts.get(sample_key)
        comparison_entry = comparison_artifacts.get(sample_key)
        scenario_label = _packet_scenario_label(packet_id)
        packet_status = _review_packet_status(
            total_samples=hydration_payload.get("total_samples", 0),
            adjudicated_count=hydration_payload.get("adjudicated_count", 0),
        )
        packet_record = {
            "packet_id": packet_id,
            "sample_path": sample_key,
            "proposal_path": proposal_entry["artifact_path"] if proposal_entry is not None else None,
            "compare_path": comparison_entry["artifact_path"] if comparison_entry is not None else None,
            "scenario_label": scenario_label,
            "status": packet_status,
            "total_samples": hydration_payload.get("total_samples", 0),
            "adjudicated_count": hydration_payload.get("adjudicated_count", 0),
            "pending_count": hydration_payload.get("pending_count", 0),
            "bucket_counts": hydration_payload.get("bucket_counts") or {},
            "manual_reject_precision": hydration_payload.get("reject_precision"),
            "proposal_reject_precision": (
                comparison_entry["payload"].get("proposal_reject_precision")
                if comparison_entry is not None
                else None
            ),
            "campaign_ids": [],
            "metadata": hydration_payload.get("metadata") or {},
            "valid": hydration_payload.get("valid", True),
            "error_count": hydration_payload.get("error_count", 0),
            "warning_count": hydration_payload.get("warning_count", 0),
            "unique_review_id_count": hydration_payload.get("unique_review_id_count", 0),
            "hydration": hydration_payload,
        }
        packet_records.append(packet_record)
        packet_by_sample_path[packet_record["sample_path"]] = packet_record
        packet_status_counts[packet_status] = packet_status_counts.get(packet_status, 0) + 1
        if scenario_label:
            scenario_counts[scenario_label] = scenario_counts.get(scenario_label, 0) + 1
        if proposal_entry is not None:
            proposal_packet_count += 1
        if comparison_entry is not None:
            comparison_packet_count += 1
        adjudicated_count += packet_record["adjudicated_count"]
        total_samples += packet_record["total_samples"]
        if not packet_record["valid"]:
            invalid_packet_count += 1

    campaign_records: list[dict[str, Any]] = []
    campaign_status_counts: dict[str, int] = {}
    for campaign_path in sorted(reports_root.glob("review-assist-campaign-*.json")):
        campaign_id = _campaign_id_from_path(campaign_path)
        if not campaign_id:
            continue
        payload = _load_json_artifact(campaign_path)
        packet_ids: list[str] = []
        packet_paths: list[str] = []
        for scenario in payload.get("scenarios", []):
            sample_path = (
                ((scenario.get("artifacts") or {}).get("sample") or {}).get("session_markdown_path")
            )
            if not sample_path:
                continue
            packet_paths.append(sample_path)
            packet_id = _sample_packet_id_from_path(Path(sample_path))
            if packet_id:
                packet_ids.append(packet_id)
            packet_record = packet_by_sample_path.get(str(Path(sample_path).resolve()))
            if packet_record is not None:
                packet_record["campaign_ids"].append(campaign_id)
        campaign_status = _review_packet_status(
            total_samples=payload.get("sampled_group_count", 0),
            adjudicated_count=payload.get("adjudicated_count", 0),
        )
        campaign_records.append(
            {
                "campaign_id": campaign_id,
                "campaign_path": str(campaign_path.resolve()),
                "status": campaign_status,
                "selected_scenarios": payload.get("selected_scenarios") or [],
                "scenario_count": payload.get("scenario_count", 0),
                "sampled_group_count": payload.get("sampled_group_count", 0),
                "sampled_item_count": payload.get("sampled_item_count", 0),
                "adjudicated_count": payload.get("adjudicated_count", 0),
                "proposal_reject_precision": payload.get("proposal_reject_precision"),
                "packet_ids": packet_ids,
                "packet_paths": packet_paths,
            }
        )
        campaign_status_counts[campaign_status] = campaign_status_counts.get(campaign_status, 0) + 1

    for packet in packet_records:
        packet["campaign_ids"] = sorted(set(packet["campaign_ids"]))

    return {
        "generated_at": now_iso(),
        "project_root": str(project_root.resolve()),
        "reports_root": str(reports_root),
        "packet_count": len(packet_records),
        "campaign_count": len(campaign_records),
        "packet_status_counts": packet_status_counts,
        "campaign_status_counts": campaign_status_counts,
        "scenario_counts": scenario_counts,
        "proposal_packet_count": proposal_packet_count,
        "comparison_packet_count": comparison_packet_count,
        "invalid_packet_count": invalid_packet_count,
        "total_samples": total_samples,
        "adjudicated_count": adjudicated_count,
        "pending_count": total_samples - adjudicated_count,
        "packets": packet_records,
        "campaigns": campaign_records,
    }


def render_entity_alias_review_campaign_index(payload: dict[str, Any]) -> str:
    lines = [
        "Entity-alias review campaign index",
        f"Project: {payload['project_root']}",
        f"Campaigns: {payload['campaign_count']}  Packets: {payload['packet_count']}",
        f"Samples: {payload['total_samples']}  Adjudicated: {payload['adjudicated_count']}  Pending: {payload['pending_count']}",
    ]
    if payload.get("packet_status_counts"):
        status_line = ", ".join(
            f"{status}={count}"
            for status, count in sorted(
                payload["packet_status_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Packet status: {status_line}")
    if payload.get("campaign_status_counts"):
        status_line = ", ".join(
            f"{status}={count}"
            for status, count in sorted(
                payload["campaign_status_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Campaign status: {status_line}")
    if payload.get("scenario_counts"):
        scenario_line = ", ".join(
            f"{label}={count}"
            for label, count in sorted(
                payload["scenario_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Scenarios: {scenario_line}")
    lines.append("")
    if payload.get("campaigns"):
        lines.append("Campaigns:")
        for campaign in payload["campaigns"][:10]:
            precision = campaign.get("proposal_reject_precision")
            precision_text = "n/a" if precision is None else f"{precision:.2%}"
            lines.append(
                f"- {campaign['campaign_id']}  status={campaign['status']}  scenarios={campaign['scenario_count']}  sampled_groups={campaign['sampled_group_count']}  adjudicated={campaign['adjudicated_count']}  reject_precision={precision_text}"
            )
        if len(payload["campaigns"]) > 10:
            lines.append(f"... {len(payload['campaigns']) - 10} more campaigns")
        lines.append("")
    if payload.get("packets"):
        lines.append("Packets:")
        for packet in payload["packets"][:12]:
            lines.append(
                f"- {packet['packet_id']}  status={packet['status']}  samples={packet['total_samples']}  adjudicated={packet['adjudicated_count']}  scenario={packet.get('scenario_label') or 'legacy'}"
            )
            if packet.get("campaign_ids"):
                lines.append(f"  campaigns: {', '.join(packet['campaign_ids'])}")
            lines.append(f"  sample: {packet['sample_path']}")
        if len(payload["packets"]) > 12:
            lines.append(f"... {len(payload['packets']) - 12} more packets")
    return "\n".join(lines).rstrip()


def write_entity_alias_review_campaign_index_artifacts(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    latest_json = review_assist_campaign_index_latest_json_path(project_root)
    latest_markdown = review_assist_campaign_index_latest_markdown_path(project_root)
    stamp = report_stamp()
    session_json = review_assist_campaign_index_session_json_path(project_root, stamp)
    session_markdown = review_assist_campaign_index_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_review_campaign_index(payload)
    write_json(latest_json, payload)
    write_markdown(latest_markdown, rendered)
    write_json(session_json, payload)
    write_markdown(session_markdown, rendered)
    return {
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_markdown),
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
    }


def render_entity_alias_review_packet_hydration(payload: dict[str, Any]) -> str:
    lines = [
        "Entity-alias review packet hydration",
        f"Source: {payload['source_path']}",
        f"Packet ID: {payload.get('packet_id') or 'unknown'}",
        f"Valid: {payload['valid']}  Errors: {payload['error_count']}  Warnings: {payload['warning_count']}",
        f"Samples: {payload['total_samples']}  Adjudicated: {payload['adjudication_record_count']}  Pending: {payload['pending_count']}",
    ]
    if payload.get("errors"):
        lines.append("Errors:")
        for issue in payload["errors"]:
            lines.append(
                f"- sample {issue.get('sample_index', '?')}: {issue['type']}  {issue['message']}"
            )
    if payload.get("warnings"):
        lines.append("Warnings:")
        for issue in payload["warnings"][:10]:
            lines.append(
                f"- sample {issue.get('sample_index', '?')}: {issue['type']}  {issue['message']}"
            )
        if len(payload["warnings"]) > 10:
            lines.append(f"... {len(payload['warnings']) - 10} more warnings")
    lines.append("")
    for sample in payload.get("samples", [])[:12]:
        lines.append(
            f"- sample {sample['sample_index']}  anchor={sample.get('anchor', '')}  bucket={sample.get('bucket', 'manual-review')}  manual={sample.get('manual_outcome') or 'pending'}"
        )
        if sample.get("review_ids"):
            lines.append(f"  review_ids: {', '.join(sample['review_ids'])}")
    remaining = len(payload.get("samples", [])) - min(len(payload.get("samples", [])), 12)
    if remaining > 0:
        lines.append(f"... {remaining} more samples")
    return "\n".join(lines).rstrip()


def write_entity_alias_review_packet_hydration_artifacts(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    latest_json = review_assist_packet_hydrate_latest_json_path(project_root)
    latest_markdown = review_assist_packet_hydrate_latest_markdown_path(project_root)
    stamp = report_stamp()
    session_json = review_assist_packet_hydrate_session_json_path(project_root, stamp)
    session_markdown = review_assist_packet_hydrate_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_review_packet_hydration(payload)
    write_json(latest_json, payload)
    write_markdown(latest_markdown, rendered)
    write_json(session_json, payload)
    write_markdown(session_markdown, rendered)
    return {
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_markdown),
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
    }


def build_entity_alias_review_rollup(
    project_root: Path,
    *,
    packet_statuses: list[str] | None = None,
    scenario_labels: list[str] | None = None,
    packet_ids: list[str] | None = None,
    campaign_ids: list[str] | None = None,
) -> dict[str, Any]:
    index_payload = build_entity_alias_review_campaign_index(project_root)
    selected_packets = _select_review_packets(
        index_payload.get("packets") or [],
        packet_statuses=packet_statuses,
        scenario_labels=scenario_labels,
        packet_ids=packet_ids,
        campaign_ids=campaign_ids,
    )
    compared_packets = [packet for packet in selected_packets if packet.get("compare_path")]
    selected_status_counts: dict[str, int] = {}
    selected_scenario_counts: dict[str, int] = {}
    confidence_summary: dict[str, dict[str, int | float | None]] = {}
    matched_samples = 0
    adjudicated_count = 0
    comparable_count = 0
    agreement_count = 0
    disagreement_count = 0
    proposal_reject_count = 0
    proposal_keep_count = 0
    proposal_needs_context_count = 0
    proposal_reject_hits = 0
    proposal_reject_false_positives = 0

    for packet in selected_packets:
        selected_status_counts[packet["status"]] = selected_status_counts.get(packet["status"], 0) + 1
        scenario_label = packet.get("scenario_label") or "legacy"
        selected_scenario_counts[scenario_label] = selected_scenario_counts.get(scenario_label, 0) + 1

    for packet in compared_packets:
        comparison_payload = _load_json_artifact(Path(packet["compare_path"]))
        matched_samples += int(comparison_payload.get("matched_samples") or 0)
        adjudicated_count += int(comparison_payload.get("adjudicated_count") or 0)
        comparable_count += int(comparison_payload.get("comparable_count") or 0)
        agreement_count += int(comparison_payload.get("agreement_count") or 0)
        disagreement_count += int(comparison_payload.get("disagreement_count") or 0)
        proposal_reject_count += int(comparison_payload.get("proposal_reject_count") or 0)
        proposal_keep_count += int(comparison_payload.get("proposal_keep_count") or 0)
        proposal_needs_context_count += int(comparison_payload.get("proposal_needs_context_count") or 0)
        proposal_reject_hits += int(comparison_payload.get("proposal_reject_hits") or 0)
        proposal_reject_false_positives += int(
            comparison_payload.get("proposal_reject_false_positives") or 0
        )
        for level, level_summary in (comparison_payload.get("confidence_summary") or {}).items():
            aggregate = confidence_summary.setdefault(
                level,
                {
                    "count": 0,
                    "adjudicated_count": 0,
                    "agreement_count": 0,
                    "disagreement_count": 0,
                    "proposal_reject_count": 0,
                    "proposal_reject_hits": 0,
                    "proposal_reject_false_positives": 0,
                    "reject_precision": None,
                },
            )
            for key in (
                "count",
                "adjudicated_count",
                "agreement_count",
                "disagreement_count",
                "proposal_reject_count",
                "proposal_reject_hits",
                "proposal_reject_false_positives",
            ):
                aggregate[key] = int(aggregate[key]) + int(level_summary.get(key) or 0)

    for level_summary in confidence_summary.values():
        reject_count = int(level_summary["proposal_reject_hits"]) + int(
            level_summary["proposal_reject_false_positives"]
        )
        level_summary["reject_precision"] = (
            round(int(level_summary["proposal_reject_hits"]) / reject_count, 4)
            if reject_count
            else None
        )

    agreement_rate = round(agreement_count / comparable_count, 4) if comparable_count else None
    reject_denominator = proposal_reject_hits + proposal_reject_false_positives
    reject_precision = round(proposal_reject_hits / reject_denominator, 4) if reject_denominator else None
    return {
        "generated_at": now_iso(),
        "project_root": str(project_root.resolve()),
        "filters": {
            "packet_statuses": sorted({value for value in packet_statuses or [] if value}),
            "scenario_labels": sorted({value for value in scenario_labels or [] if value}),
            "packet_ids": sorted({value for value in packet_ids or [] if value}),
            "campaign_ids": sorted({value for value in campaign_ids or [] if value}),
        },
        "indexed_packet_count": index_payload.get("packet_count", 0),
        "selected_packet_count": len(selected_packets),
        "compared_packet_count": len(compared_packets),
        "selected_status_counts": selected_status_counts,
        "selected_scenario_counts": selected_scenario_counts,
        "matched_samples": matched_samples,
        "adjudicated_count": adjudicated_count,
        "comparable_count": comparable_count,
        "agreement_count": agreement_count,
        "disagreement_count": disagreement_count,
        "agreement_rate": agreement_rate,
        "proposal_reject_count": proposal_reject_count,
        "proposal_keep_count": proposal_keep_count,
        "proposal_needs_context_count": proposal_needs_context_count,
        "proposal_reject_hits": proposal_reject_hits,
        "proposal_reject_false_positives": proposal_reject_false_positives,
        "proposal_reject_precision": reject_precision,
        "confidence_summary": confidence_summary,
        "packets": selected_packets,
    }


def render_entity_alias_review_rollup(payload: dict[str, Any]) -> str:
    agreement = payload.get("agreement_rate")
    agreement_text = "n/a" if agreement is None else f"{agreement:.2%}"
    precision = payload.get("proposal_reject_precision")
    precision_text = "n/a" if precision is None else f"{precision:.2%}"
    lines = [
        "Entity-alias review rollup",
        f"Project: {payload['project_root']}",
        f"Indexed packets: {payload['indexed_packet_count']}  Selected: {payload['selected_packet_count']}  Compared: {payload['compared_packet_count']}",
        f"Matched samples: {payload['matched_samples']}  Adjudicated: {payload['adjudicated_count']}  Comparable: {payload['comparable_count']}",
        f"Agreement: {payload['agreement_count']}  Disagreement: {payload['disagreement_count']}  Agreement rate: {agreement_text}",
        f"Proposal reject precision: {precision_text}",
    ]
    filters = payload.get("filters") or {}
    filter_parts = []
    for key in ("packet_statuses", "scenario_labels", "packet_ids", "campaign_ids"):
        values = filters.get(key) or []
        if values:
            filter_parts.append(f"{key}={','.join(values)}")
    if filter_parts:
        lines.append("Filters: " + "  ".join(filter_parts))
    if payload.get("selected_status_counts"):
        status_line = ", ".join(
            f"{status}={count}"
            for status, count in sorted(
                payload["selected_status_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Statuses: {status_line}")
    if payload.get("selected_scenario_counts"):
        scenario_line = ", ".join(
            f"{label}={count}"
            for label, count in sorted(
                payload["selected_scenario_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Scenarios: {scenario_line}")
    if payload.get("confidence_summary"):
        confidence_line = ", ".join(
            f"{level}={summary['count']}"
            for level, summary in sorted(
                payload["confidence_summary"].items(), key=lambda item: (-int(item[1]["count"]), item[0])
            )
        )
        lines.append(f"Confidence: {confidence_line}")
    lines.append("")
    for packet in payload.get("packets", [])[:12]:
        lines.append(
            f"- {packet['packet_id']}  status={packet['status']}  samples={packet['total_samples']}  adjudicated={packet['adjudicated_count']}  scenario={packet.get('scenario_label') or 'legacy'}"
        )
        if packet.get("compare_path"):
            lines.append(f"  compare: {packet['compare_path']}")
    remaining = len(payload.get("packets", [])) - min(len(payload.get("packets", [])), 12)
    if remaining > 0:
        lines.append(f"... {remaining} more packets")
    return "\n".join(lines).rstrip()


def write_entity_alias_review_rollup_artifacts(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    latest_json = review_assist_rollup_latest_json_path(project_root)
    latest_markdown = review_assist_rollup_latest_markdown_path(project_root)
    stamp = report_stamp()
    session_json = review_assist_rollup_session_json_path(project_root, stamp)
    session_markdown = review_assist_rollup_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_review_rollup(payload)
    write_json(latest_json, payload)
    write_markdown(latest_markdown, rendered)
    write_json(session_json, payload)
    write_markdown(session_markdown, rendered)
    return {
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_markdown),
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
    }


def build_entity_alias_reject_stage(
    project_root: Path,
    *,
    packet_statuses: list[str] | None = None,
    scenario_labels: list[str] | None = None,
    packet_ids: list[str] | None = None,
    campaign_ids: list[str] | None = None,
    min_reject_precision: float = 0.95,
    min_adjudicated: int = 20,
) -> dict[str, Any]:
    rollup_payload = build_entity_alias_review_rollup(
        project_root,
        packet_statuses=packet_statuses,
        scenario_labels=scenario_labels,
        packet_ids=packet_ids,
        campaign_ids=campaign_ids,
    )
    blocked_reasons: list[str] = []
    precision = rollup_payload.get("proposal_reject_precision")
    adjudicated_count = int(rollup_payload.get("adjudicated_count") or 0)
    if adjudicated_count < min_adjudicated:
        blocked_reasons.append(
            f"Need at least {min_adjudicated} adjudicated samples; found {adjudicated_count}."
        )
    if precision is None:
        blocked_reasons.append("Proposal reject precision is not yet measurable for the selected packets.")
    elif precision < min_reject_precision:
        blocked_reasons.append(
            f"Proposal reject precision {precision:.2%} is below the required {min_reject_precision:.2%}."
        )

    candidates: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for packet in rollup_payload.get("packets", []):
        proposal_map: dict[str, dict[str, Any]] = {}
        proposal_path = packet.get("proposal_path")
        if proposal_path:
            proposal_payload = load_entity_alias_review_sample_proposal(Path(proposal_path))
            proposal_map = {
                _review_sample_key(sample): sample for sample in proposal_payload.get("samples", [])
            }
        parsed_sample = parse_entity_alias_review_sample_markdown(Path(packet["sample_path"]))
        for sample in parsed_sample.get("samples", []):
            if sample.get("manual_outcome") != "reject":
                continue
            review_ids = [value for value in sample.get("review_ids") or [] if value]
            key = "|".join(review_ids) if review_ids else str(sample.get("anchor") or "")
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            proposal = proposal_map.get(_review_sample_key(sample), {})
            candidates.append(
                {
                    "candidate_id": f"reject-stage-{len(candidates) + 1:03d}",
                    "packet_id": packet["packet_id"],
                    "campaign_ids": packet.get("campaign_ids") or [],
                    "anchor": sample.get("anchor", ""),
                    "review_ids": review_ids,
                    "manual_outcome": sample.get("manual_outcome", ""),
                    "manual_notes": sample.get("notes", ""),
                    "assistant_outcome": proposal.get("assistant_outcome", ""),
                    "assistant_confidence": proposal.get("assistant_confidence", ""),
                    "assistant_rationale": proposal.get("assistant_rationale") or [],
                    "planned_action": {
                        "decision": "rejected",
                        "review_ids": review_ids,
                        "source_packet": packet["sample_path"],
                    },
                    "revert_plan": {
                        "mode": "discard-stage-only",
                        "applied": False,
                        "note": "No queue mutation has occurred; discarding the stage artifact is sufficient.",
                    },
                }
            )

    stage_status = "blocked" if blocked_reasons else "ready"
    if not candidates:
        stage_status = "blocked" if blocked_reasons else "ready-empty"
    return {
        "generated_at": now_iso(),
        "project_root": str(project_root.resolve()),
        "stage_status": stage_status,
        "ready_to_apply": not blocked_reasons and bool(candidates),
        "applied": False,
        "discardable": True,
        "thresholds": {
            "min_reject_precision": min_reject_precision,
            "min_adjudicated": min_adjudicated,
        },
        "blocked_reasons": blocked_reasons,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "rollup": rollup_payload,
    }


def render_entity_alias_reject_stage(payload: dict[str, Any]) -> str:
    precision = payload.get("rollup", {}).get("proposal_reject_precision")
    precision_text = "n/a" if precision is None else f"{precision:.2%}"
    lines = [
        "Entity-alias reject stage",
        f"Project: {payload['project_root']}",
        f"Stage status: {payload['stage_status']}  Ready to apply: {payload['ready_to_apply']}",
        f"Candidates: {payload['candidate_count']}",
        f"Rollup adjudicated: {payload['rollup'].get('adjudicated_count', 0)}  Reject precision: {precision_text}",
        "Thresholds: "
        f"min_reject_precision={payload['thresholds']['min_reject_precision']:.2%}  "
        f"min_adjudicated={payload['thresholds']['min_adjudicated']}",
    ]
    if payload.get("blocked_reasons"):
        lines.append("Blocked:")
        for reason in payload["blocked_reasons"]:
            lines.append(f"- {reason}")
    lines.append("")
    for candidate in payload.get("candidates", [])[:12]:
        lines.append(
            f"- {candidate['candidate_id']}  packet={candidate['packet_id']}  anchor={candidate['anchor']}  review_ids={','.join(candidate['review_ids']) or 'none'}"
        )
        if candidate.get("assistant_outcome"):
            lines.append(
                f"  assistant: {candidate['assistant_outcome']}  confidence={candidate.get('assistant_confidence') or 'n/a'}"
            )
        if candidate.get("manual_notes"):
            lines.append(f"  notes: {candidate['manual_notes']}")
    remaining = len(payload.get("candidates", [])) - min(len(payload.get("candidates", [])), 12)
    if remaining > 0:
        lines.append(f"... {remaining} more candidates")
    return "\n".join(lines).rstrip()


def write_entity_alias_reject_stage_artifacts(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    latest_json = review_assist_reject_stage_latest_json_path(project_root)
    latest_markdown = review_assist_reject_stage_latest_markdown_path(project_root)
    stamp = report_stamp()
    session_json = review_assist_reject_stage_session_json_path(project_root, stamp)
    session_markdown = review_assist_reject_stage_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_reject_stage(payload)
    write_json(latest_json, payload)
    write_markdown(latest_markdown, rendered)
    write_json(session_json, payload)
    write_markdown(session_markdown, rendered)
    return {
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_markdown),
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
    }


def build_entity_alias_review_scoreboard(
    project_root: Path,
    *,
    min_reject_precision: float = 0.95,
    min_adjudicated: int = 20,
) -> dict[str, Any]:
    index_payload = build_entity_alias_review_campaign_index(project_root)
    rollup_payload = build_entity_alias_review_rollup(project_root)
    current_adjudicated = int(rollup_payload.get("adjudicated_count") or 0)
    remaining_to_threshold = max(0, min_adjudicated - current_adjudicated)
    ranked_packets: list[dict[str, Any]] = []
    for packet in index_payload.get("packets", []):
        if packet.get("status") == "complete":
            continue
        pending_samples = int(packet.get("pending_count") or 0)
        has_proposal = bool(packet.get("proposal_path"))
        has_compare = bool(packet.get("compare_path"))
        has_campaign = bool(packet.get("campaign_ids"))
        valid = bool(packet.get("valid", True))
        priority_score = pending_samples * 10
        if has_proposal:
            priority_score += 30
        if has_compare:
            priority_score += 15
        if has_campaign:
            priority_score += 10
        if packet.get("scenario_label"):
            priority_score += 10
        if not valid:
            priority_score -= 50
        if remaining_to_threshold and pending_samples >= remaining_to_threshold:
            priority_bucket = "unlock-threshold-now"
        elif has_proposal or has_compare:
            priority_bucket = "precision-ready"
        elif has_campaign:
            priority_bucket = "campaign-backlog"
        else:
            priority_bucket = "legacy-backfill"
        ranked_packets.append(
            {
                "packet_id": packet["packet_id"],
                "sample_path": packet["sample_path"],
                "status": packet["status"],
                "scenario_label": packet.get("scenario_label") or "legacy",
                "campaign_ids": packet.get("campaign_ids") or [],
                "pending_samples": pending_samples,
                "adjudicated_count": packet.get("adjudicated_count", 0),
                "has_proposal": has_proposal,
                "has_compare": has_compare,
                "valid": valid,
                "error_count": packet.get("error_count", 0),
                "warning_count": packet.get("warning_count", 0),
                "priority_bucket": priority_bucket,
                "priority_score": priority_score,
                "remaining_to_threshold_after_completion": max(0, remaining_to_threshold - pending_samples),
            }
        )
    ranked_packets.sort(
        key=lambda item: (
            -int(item["priority_score"]),
            int(item["remaining_to_threshold_after_completion"]),
            item["packet_id"],
        )
    )
    bucket_counts: dict[str, int] = {}
    for packet in ranked_packets:
        bucket = str(packet["priority_bucket"])
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    return {
        "generated_at": now_iso(),
        "project_root": str(project_root.resolve()),
        "thresholds": {
            "min_reject_precision": min_reject_precision,
            "min_adjudicated": min_adjudicated,
        },
        "current_adjudicated": current_adjudicated,
        "remaining_to_threshold": remaining_to_threshold,
        "current_reject_precision": rollup_payload.get("proposal_reject_precision"),
        "packet_count": len(index_payload.get("packets", [])),
        "candidate_packet_count": len(ranked_packets),
        "priority_bucket_counts": bucket_counts,
        "packets": ranked_packets,
    }


def render_entity_alias_review_scoreboard(payload: dict[str, Any]) -> str:
    precision = payload.get("current_reject_precision")
    precision_text = "n/a" if precision is None else f"{precision:.2%}"
    lines = [
        "Entity-alias review completion scoreboard",
        f"Project: {payload['project_root']}",
        f"Current adjudicated: {payload['current_adjudicated']}  Remaining to threshold: {payload['remaining_to_threshold']}",
        f"Current reject precision: {precision_text}",
    ]
    if payload.get("priority_bucket_counts"):
        bucket_line = ", ".join(
            f"{bucket}={count}"
            for bucket, count in sorted(
                payload["priority_bucket_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.append(f"Buckets: {bucket_line}")
    lines.append("")
    for packet in payload.get("packets", [])[:15]:
        lines.append(
            f"- {packet['packet_id']}  bucket={packet['priority_bucket']}  score={packet['priority_score']}  pending={packet['pending_samples']}  valid={packet['valid']}"
        )
        lines.append(
            f"  scenario={packet['scenario_label']}  compare={packet['has_compare']}  proposal={packet['has_proposal']}  threshold_gap_after={packet['remaining_to_threshold_after_completion']}"
        )
    remaining = len(payload.get("packets", [])) - min(len(payload.get("packets", [])), 15)
    if remaining > 0:
        lines.append(f"... {remaining} more packets")
    return "\n".join(lines).rstrip()


def write_entity_alias_review_scoreboard_artifacts(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    latest_json = review_assist_scoreboard_latest_json_path(project_root)
    latest_markdown = review_assist_scoreboard_latest_markdown_path(project_root)
    stamp = report_stamp()
    session_json = review_assist_scoreboard_session_json_path(project_root, stamp)
    session_markdown = review_assist_scoreboard_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_review_scoreboard(payload)
    write_json(latest_json, payload)
    write_markdown(latest_markdown, rendered)
    write_json(session_json, payload)
    write_markdown(session_markdown, rendered)
    return {
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_markdown),
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
    }


def build_entity_alias_review_apply_plan(
    project_root: Path,
    *,
    packet_statuses: list[str] | None = None,
    scenario_labels: list[str] | None = None,
    packet_ids: list[str] | None = None,
    campaign_ids: list[str] | None = None,
    min_reject_precision: float = 0.95,
    min_adjudicated: int = 20,
) -> dict[str, Any]:
    stage_payload = build_entity_alias_reject_stage(
        project_root,
        packet_statuses=packet_statuses,
        scenario_labels=scenario_labels,
        packet_ids=packet_ids,
        campaign_ids=campaign_ids,
        min_reject_precision=min_reject_precision,
        min_adjudicated=min_adjudicated,
    )
    project_root = project_root.resolve()
    snapshot_contract = {
        "required": True,
        "enabled": False,
        "pre_apply_snapshots": [
            {
                "label": "review-queue",
                "source_path": str(project_root / "state" / "federated-review-queue.json"),
                "planned_snapshot_path": str(
                    project_root / "reports" / "review-assist-apply-plan-pre-apply-queue.json"
                ),
            },
            {
                "label": "review-decisions",
                "source_path": str(project_root / "state" / "federated-canonical-decisions.json"),
                "planned_snapshot_path": str(
                    project_root / "reports" / "review-assist-apply-plan-pre-apply-decisions.json"
                ),
            },
            {
                "label": "review-history",
                "source_path": str(project_root / "state" / "federated-review-history.json"),
                "planned_snapshot_path": str(
                    project_root / "reports" / "review-assist-apply-plan-pre-apply-history.json"
                ),
            },
        ],
        "rollback_contract": {
            "mode": "restore-snapshots-before-rebuild",
            "targets": ["review-queue", "review-decisions", "review-history"],
            "post_restore_steps": [
                "restore state files from snapshots",
                "rebuild federation artifacts",
                "verify queue/history counts match the snapshot baseline",
            ],
        },
    }
    blocked_reasons = list(stage_payload.get("blocked_reasons") or [])
    if blocked_reasons:
        blocked_reasons.insert(0, "Apply plan remains disabled until reject-stage becomes ready.")
    return {
        "generated_at": now_iso(),
        "project_root": str(project_root),
        "apply_status": "disabled" if blocked_reasons else "preview-only",
        "enabled": False,
        "ready_to_apply": False,
        "blocked_reasons": blocked_reasons,
        "candidate_count": stage_payload.get("candidate_count", 0),
        "planned_actions": [
            candidate.get("planned_action") for candidate in stage_payload.get("candidates", [])
        ],
        "snapshot_contract": snapshot_contract,
        "stage": stage_payload,
    }


def render_entity_alias_review_apply_plan(payload: dict[str, Any]) -> str:
    lines = [
        "Entity-alias review apply plan",
        f"Project: {payload['project_root']}",
        f"Apply status: {payload['apply_status']}  Enabled: {payload['enabled']}",
        f"Candidates: {payload['candidate_count']}",
    ]
    if payload.get("blocked_reasons"):
        lines.append("Blocked:")
        for reason in payload["blocked_reasons"]:
            lines.append(f"- {reason}")
    lines.append("Snapshots:")
    for entry in payload.get("snapshot_contract", {}).get("pre_apply_snapshots", []):
        lines.append(f"- {entry['label']}: {entry['source_path']} -> {entry['planned_snapshot_path']}")
    lines.append("Rollback:")
    for step in payload.get("snapshot_contract", {}).get("rollback_contract", {}).get(
        "post_restore_steps", []
    ):
        lines.append(f"- {step}")
    return "\n".join(lines).rstrip()


def write_entity_alias_review_apply_plan_artifacts(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    latest_json = review_assist_apply_plan_latest_json_path(project_root)
    latest_markdown = review_assist_apply_plan_latest_markdown_path(project_root)
    stamp = report_stamp()
    session_json = review_assist_apply_plan_session_json_path(project_root, stamp)
    session_markdown = review_assist_apply_plan_session_markdown_path(project_root, stamp)
    rendered = render_entity_alias_review_apply_plan(payload)
    write_json(latest_json, payload)
    write_markdown(latest_markdown, rendered)
    write_json(session_json, payload)
    write_markdown(session_markdown, rendered)
    return {
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_markdown),
        "session_json_path": str(session_json),
        "session_markdown_path": str(session_markdown),
    }


def write_entity_alias_review_assist_artifacts(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    selection = payload.get("selection") or {}
    batch_id = str(selection.get("batch_id") or "")
    rendered = render_entity_alias_review_assist(payload)
    if batch_id:
        batch_json = review_assist_batch_json_path(project_root, batch_id)
        batch_markdown = review_assist_batch_markdown_path(project_root, batch_id)
        batch_checklist = review_assist_batch_checklist_path(project_root, batch_id)
        batch_report = review_assist_report_path(project_root, batch_id=batch_id)
        write_json(batch_json, payload)
        write_markdown(batch_markdown, rendered)
        write_markdown(batch_checklist, render_entity_alias_review_checklist(payload))
        write_markdown(batch_report, rendered)
        return {
            "batch_json_path": str(batch_json),
            "batch_markdown_path": str(batch_markdown),
            "batch_checklist_path": str(batch_checklist),
            "batch_report_path": str(batch_report),
        }

    latest_json = review_assist_latest_json_path(project_root)
    latest_markdown = review_assist_latest_markdown_path(project_root)
    dated_markdown = review_assist_report_path(project_root)
    write_json(latest_json, payload)
    write_markdown(latest_markdown, rendered)
    write_markdown(dated_markdown, rendered)
    return {
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_markdown),
        "report_path": str(dated_markdown),
    }


def classify_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Classify a single review item into a triage decision.

    Returns a dict with keys: decision, note, policy, canonical_subject
    or None if no policy matches (requires human review).
    """
    review_type = item.get("review_type", "")
    subject_ids = item.get("subject_ids", [])
    if not subject_ids:
        return None

    parsed = extract_local_ids(subject_ids)
    corpora = {corpus for corpus, _ in parsed}
    local_ids = [local for _, local in parsed]

    # Policy: exact-cross-corpus — same local ID across different corpora
    if len(corpora) >= 2 and len(set(local_ids)) == 1:
        canonical = item.get("suggested_canonical_subject") or local_ids[0]
        return {
            "decision": "accepted",
            "note": f"Auto-triage: exact cross-corpus match ({len(corpora)} corpora)",
            "policy": "exact-cross-corpus",
            "canonical_subject": canonical,
        }

    # Policy: slug-match — same title slug, different UUID suffixes across corpora
    if review_type in {"family-merge", "action-merge", "unresolved-merge"} and len(corpora) >= 2:
        slugs = [_strip_uuid_suffix(lid) for lid in local_ids]
        if len(set(slugs)) == 1 and slugs[0]:
            canonical = item.get("suggested_canonical_subject") or local_ids[0]
            return {
                "decision": "accepted",
                "note": f"Auto-triage: same title slug across {len(corpora)} corpora (UUID suffix differs)",
                "policy": "slug-match",
                "canonical_subject": canonical,
            }

    if review_type == "entity-alias" and len(corpora) >= 2:
        semantic_match = _semantic_title_policy(
            item,
            policy="entity-title-overlap",
            note="Auto-triage: entity labels have strong token overlap across corpora",
            min_overlap=2,
            min_jaccard=0.5,
            min_subset_ratio=1.0,
            min_shorter_tokens=2,
        )
        if semantic_match:
            return semantic_match

    if review_type == "family-merge" and len(corpora) >= 2:
        semantic_match = _semantic_title_policy(
            item,
            policy="family-title-overlap",
            note="Auto-triage: family titles have strong token overlap across corpora",
            min_overlap=2,
            min_jaccard=0.6,
            min_subset_ratio=1.0,
            min_shorter_tokens=2,
        )
        if semantic_match:
            return semantic_match

    if review_type == "action-merge" and len(corpora) >= 2:
        semantic_match = _semantic_title_policy(
            item,
            policy="action-title-overlap",
            note="Auto-triage: canonical actions substantially overlap across corpora",
            min_overlap=2,
            min_jaccard=0.6,
            min_subset_ratio=1.0,
            min_shorter_tokens=2,
        )
        if semantic_match:
            return semantic_match

    if review_type == "unresolved-merge" and len(corpora) >= 2:
        semantic_match = _semantic_title_policy(
            item,
            policy="unresolved-title-overlap",
            note="Auto-triage: canonical questions substantially overlap across corpora",
            min_overlap=2,
            min_jaccard=0.6,
            min_subset_ratio=1.0,
            min_shorter_tokens=2,
        )
        if semantic_match:
            return semantic_match

    # Policy: prefix-entity-alias — one entity ID is a prefix of the other (cross-corpus only)
    if review_type == "entity-alias" and len(local_ids) >= 2 and len(corpora) >= 2:
        sorted_ids = sorted(local_ids, key=len)
        if sorted_ids[-1].startswith(sorted_ids[0]) and len(sorted_ids[0]) >= 10:
            canonical = item.get("suggested_canonical_subject") or sorted_ids[-1]
            return {
                "decision": "accepted",
                "note": "Auto-triage: entity ID prefix match (shorter is subset of longer)",
                "policy": "prefix-entity-alias",
                "canonical_subject": canonical,
            }

    # Policy: noise-entity — reject aliases involving noise tokens
    if review_type == "entity-alias":
        if any(lid in NOISE_ENTITY_IDS for lid in local_ids):
            return {
                "decision": "rejected",
                "note": "Auto-triage: noise entity token (numeric/null/boolean)",
                "policy": "noise-entity",
                "canonical_subject": "",
            }
        # Reject if any local ID is very short (< 4 chars after entity- prefix)
        short_ids = [lid for lid in local_ids if len(lid.replace("entity-", "")) < 3]
        if short_ids:
            return {
                "decision": "rejected",
                "note": "Auto-triage: entity ID too short to be meaningful",
                "policy": "short-entity",
                "canonical_subject": "",
            }
        generic_singleton = _generic_singleton_entity_policy(item)
        if generic_singleton:
            return generic_singleton

    # Policy: contradiction-defer — contradictions need human judgment
    if review_type == "contradiction":
        return {
            "decision": "deferred",
            "note": "Auto-triage: contradictions require human review",
            "policy": "contradiction-defer",
            "canonical_subject": "",
        }

    return None


def build_triage_plan(project_root: Path) -> dict[str, Any]:
    """Classify all open review items and return a triage plan."""
    queue = load_federated_review_queue(project_root)
    open_items = [i for i in queue.get("items", []) if i.get("status") == "open"]

    plan: dict[str, list[dict[str, Any]]] = {
        "accepted": [],
        "rejected": [],
        "deferred": [],
        "manual": [],
    }
    policy_counts: dict[str, int] = {}

    for item in open_items:
        result = classify_item(item)
        if result:
            decision = result["decision"]
            policy = result["policy"]
            plan[decision].append(
                {
                    "review_id": item["review_id"],
                    "review_type": item["review_type"],
                    "policy": policy,
                    "decision": decision,
                    "note": result["note"],
                    "canonical_subject": result["canonical_subject"],
                }
            )
            policy_counts[policy] = policy_counts.get(policy, 0) + 1
        else:
            plan["manual"].append(
                {
                    "review_id": item["review_id"],
                    "review_type": item["review_type"],
                }
            )

    return {
        "generated_at": now_iso(),
        "total_open": len(open_items),
        "auto_resolvable": len(plan["accepted"]) + len(plan["rejected"]) + len(plan["deferred"]),
        "requires_manual": len(plan["manual"]),
        "policy_counts": policy_counts,
        "summary": {
            "accepted": len(plan["accepted"]),
            "rejected": len(plan["rejected"]),
            "deferred": len(plan["deferred"]),
            "manual": len(plan["manual"]),
        },
        "plan": plan,
    }


def execute_triage_plan(
    project_root: Path,
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Execute a triage plan, resolving all auto-classified items."""
    queue = load_federated_review_queue(project_root)
    decisions = load_federated_decisions(project_root)
    items_by_id: dict[str, list[dict[str, Any]]] = {}
    for item in queue.get("items", []):
        items_by_id.setdefault(item["review_id"], []).append(item)

    resolved_count = 0
    errors: list[str] = []
    processed_review_ids: set[str] = set()

    for decision_type in ("accepted", "rejected", "deferred"):
        for entry in plan.get("plan", {}).get(decision_type, []):
            review_id = entry["review_id"]
            if review_id in processed_review_ids:
                continue
            matching_items = items_by_id.get(review_id, [])
            open_items = [item for item in matching_items if item.get("status") == "open"]
            if not open_items:
                errors.append(f"Skipped {review_id}: not open")
                continue
            processed_review_ids.add(review_id)

            for item in open_items:
                item["status"] = entry["decision"]
                item["decision_note"] = entry["note"]
                item["canonical_subject"] = (
                    entry.get("canonical_subject")
                    or item.get("canonical_subject")
                    or item.get("suggested_canonical_subject")
                    or ""
                )
                item["resolved_at"] = now_iso()
                item["updated_at"] = item["resolved_at"]
                item["triage_policy"] = entry.get("policy", "")

                append_federated_review_history(
                    project_root,
                    item,
                    decision=entry["decision"],
                    note=entry["note"],
                    canonical_subject=entry.get("canonical_subject"),
                )

            if (
                entry["decision"] in {"accepted", "rejected"}
                and open_items[0].get("review_type") in FEDERATED_REVIEW_TYPES
            ):
                add_decision_record(
                    decisions,
                    open_items[0]["review_type"],
                    open_items[0].get("subject_ids") or [],
                    decision=entry["decision"],
                    canonical_subject=entry.get("canonical_subject"),
                    review_id=review_id,
                )

            resolved_count += len(open_items)

    save_federated_review_queue(project_root, queue)
    save_federated_decisions(project_root, decisions)

    remaining_open = sum(1 for i in queue.get("items", []) if i.get("status") == "open")
    return {
        "resolved": resolved_count,
        "errors": errors,
        "remaining_open": remaining_open,
    }
