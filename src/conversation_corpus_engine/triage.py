"""Policy-driven auto-triage for the federated review queue."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    # Policy: prefix-entity-alias — one entity ID is a prefix of the other
    if review_type == "entity-alias" and len(local_ids) >= 2:
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
    items_by_id = {i["review_id"]: i for i in queue.get("items", [])}

    resolved_count = 0
    errors: list[str] = []

    for decision_type in ("accepted", "rejected", "deferred"):
        for entry in plan.get("plan", {}).get(decision_type, []):
            review_id = entry["review_id"]
            item = items_by_id.get(review_id)
            if not item or item.get("status") != "open":
                errors.append(f"Skipped {review_id}: not open")
                continue

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
                and item.get("review_type") in FEDERATED_REVIEW_TYPES
            ):
                add_decision_record(
                    decisions,
                    item["review_type"],
                    item.get("subject_ids") or [],
                    decision=entry["decision"],
                    canonical_subject=entry.get("canonical_subject"),
                    review_id=review_id,
                )

            resolved_count += 1

    save_federated_review_queue(project_root, queue)
    save_federated_decisions(project_root, decisions)

    remaining_open = sum(1 for i in queue.get("items", []) if i.get("status") == "open")
    return {
        "resolved": resolved_count,
        "errors": errors,
        "remaining_open": remaining_open,
    }
