#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import time
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .answering import slugify, tokenize, write_json, write_markdown
from .source_lifecycle import build_source_snapshot

DEFAULT_OUTPUT_ROOT = Path.cwd() / "chatgpt-history-memory"
CONTRACT_NAME = "conversation-corpus-engine-v1"
CONTRACT_VERSION = 1
REQUIRED_BUNDLE_FILES = ("conversations.json", "user.json")
STOP_WORDS = {
    "a",
    "about",
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "can",
    "could",
    "do",
    "for",
    "from",
    "get",
    "going",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "just",
    "like",
    "make",
    "maybe",
    "more",
    "need",
    "not",
    "of",
    "on",
    "or",
    "our",
    "out",
    "say",
    "should",
    "so",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "they",
    "this",
    "to",
    "want",
    "we",
    "what",
    "where",
    "will",
    "with",
    "you",
    "your",
}
ACTION_MARKERS = (
    "need to",
    "needs to",
    "should",
    "will",
    "want to",
    "implement",
    "add",
    "build",
    "develop",
    "next step",
    "recommend",
)
UNRESOLVED_MARKERS = (
    "maybe",
    "perhaps",
    "unclear",
    "unknown",
    "whether",
    "what if",
    "which option",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def epoch_to_iso(epoch: float | None) -> str:
    if epoch is None:
        return now_iso()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a ChatGPT JSON export bundle into a federation-compatible memory corpus."
    )
    parser.add_argument("input_path", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--name")
    parser.add_argument("--corpus-id")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_bundle_root(input_path: Path) -> Path:
    input_path = input_path.resolve()
    if input_path.is_file():
        if input_path.name == "conversations.json":
            bundle_root = input_path.parent
        else:
            raise ValueError(
                f"Expected a ChatGPT export directory or conversations.json file, got {input_path}"
            )
    else:
        bundle_root = input_path
    missing = [name for name in REQUIRED_BUNDLE_FILES if not (bundle_root / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"ChatGPT export bundle at {bundle_root} is missing required files: {', '.join(missing)}"
        )
    return bundle_root


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split()).strip()


def shorten(text: str, limit: int = 320) -> str:
    cleaned = normalize_whitespace(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def split_sentences(text: str) -> list[str]:
    rough = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue
        rough.extend(
            part.strip()
            for part in stripped_line.replace("?", "?\n")
            .replace("!", "!\n")
            .replace(".", ".\n")
            .splitlines()
        )
    return [normalize_whitespace(item) for item in rough if normalize_whitespace(item)]


def top_keywords(text: str, *, limit: int = 12) -> list[str]:
    counts = Counter(
        token for token in tokenize(text) if token not in STOP_WORDS and len(token) > 2
    )
    return [token for token, _ in counts.most_common(limit)]


def vector_terms(text: str, *, limit: int = 18) -> dict[str, float]:
    counts = Counter(
        token for token in tokenize(text) if token not in STOP_WORDS and len(token) > 2
    )
    if not counts:
        return {}
    highest = max(counts.values())
    return {
        token: round(count / highest, 4)  # allow-secret
        for token, count in counts.most_common(limit)
    }


def dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = normalize_whitespace(value)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(cleaned)
    return ordered


def extract_actions(sentences: list[str]) -> list[str]:
    candidates = []
    for sentence in sentences:
        lowered = sentence.lower()
        if len(sentence) < 24 or len(sentence) > 220:
            continue
        if any(marker in lowered for marker in ACTION_MARKERS):
            candidates.append(shorten(sentence, 180))
    return dedupe_preserve(candidates)[:6]


def extract_unresolved(sentences: list[str]) -> list[str]:
    candidates = []
    for sentence in sentences:
        lowered = sentence.lower()
        if len(sentence) < 24 or len(sentence) > 220:
            continue
        if sentence.endswith("?") or any(marker in lowered for marker in UNRESOLVED_MARKERS):
            candidates.append(shorten(sentence, 180))
    return dedupe_preserve(candidates)[:5]


SKIP_CONTENT_TYPES = {"user_editable_context", "model_editable_context", "thoughts"}


def extract_node_text(node: dict[str, Any]) -> str:
    """Extract text from a ChatGPT mapping node's message content.

    Handles text, code, execution_output, multimodal_text, and tool content types.
    """
    message = node.get("message")
    if not message:
        return ""
    content = message.get("content") or {}
    content_type = content.get("content_type") or "text"
    role = ((message.get("author") or {}).get("role") or "").lower()

    if content_type in SKIP_CONTENT_TYPES:
        return ""

    parts = content.get("parts") or []
    segments: list[str] = []

    if content_type == "multimodal_text":
        for part in parts:
            if isinstance(part, str):
                cleaned = normalize_whitespace(part)
                if cleaned:
                    segments.append(cleaned)
            elif isinstance(part, dict):
                part_type = part.get("content_type", "")
                if part_type == "text":
                    cleaned = normalize_whitespace(str(part.get("text", "")))
                    if cleaned:
                        segments.append(cleaned)
                elif part_type == "image_asset_pointer":
                    w, h = part.get("width"), part.get("height")
                    size = f"{w}x{h}" if w and h else "unknown"
                    segments.append(f"[Image: {size}]")
    elif content_type == "code":
        raw_text = content.get("text") or " ".join(p for p in parts if isinstance(p, str))
        lang = content.get("language") or "text"
        if raw_text.strip():
            segments.append(f"```{lang}\n{raw_text.strip()}\n```")
    elif content_type == "execution_output":
        raw_text = content.get("text") or " ".join(p for p in parts if isinstance(p, str))
        if raw_text.strip():
            text = raw_text.strip()
            if len(text) > 500:
                text = text[:497] + "..."
            segments.append(f"[Execution output: {text}]")
    else:
        for part in parts:
            if isinstance(part, str):
                cleaned = normalize_whitespace(part)
                if cleaned:
                    segments.append(cleaned)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                cleaned = normalize_whitespace(part["text"])
                if cleaned:
                    segments.append(cleaned)

    if role == "tool" and not segments:
        text_field = content.get("text")
        if isinstance(text_field, str) and text_field.strip():
            text = text_field.strip()
            if len(text) > 500:
                text = text[:497] + "..."
            segments.append(f"[Tool output: {text}]")

    return normalize_whitespace(" ".join(segments))


def walk_mapping_tree(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """Walk the ChatGPT mapping tree in order, returning non-system message nodes.

    Iterative DFS — long conversations create deep linear chains that overflow
    Python's default recursion limit. ChatGPT exports with multi-thousand-message
    threads were crashing with RecursionError before this change.
    """
    roots = [node_id for node_id, node in mapping.items() if not node.get("parent")]

    ordered: list[dict[str, Any]] = []

    for root_id in roots:
        stack = [root_id]
        while stack:
            node_id = stack.pop()
            node = mapping.get(node_id)
            if node is None:
                continue
            message = node.get("message")
            if message is not None:
                role = (message.get("author") or {}).get("role", "")
                if role != "system":
                    ordered.append(node)
            children = node.get("children") or []
            for child_id in reversed(children):
                stack.append(child_id)

    # Sort by create_time if available to ensure proper order
    def node_create_time(node: dict[str, Any]) -> float:
        message = node.get("message") or {}
        return message.get("create_time") or 0.0

    ordered.sort(key=node_create_time)
    return ordered


def infer_title_chatgpt(
    conversation: dict[str, Any], nodes: list[dict[str, Any]], fallback_index: int
) -> str:
    title = conversation.get("title")
    if isinstance(title, str) and normalize_whitespace(title):
        return normalize_whitespace(title)
    # Fall back to first user message text
    for node in nodes:
        message = node.get("message") or {}
        role = (message.get("author") or {}).get("role", "")
        if role == "user":
            text = extract_node_text(node)
            if text:
                return shorten(text, 120)
    return f"ChatGPT Conversation {fallback_index:04d}"


def build_pairs_chatgpt(
    nodes: list[dict[str, Any]], thread_uid: str, family_id: str
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    current_prompt = ""
    current_response_parts: list[str] = []
    current_title = ""
    pair_index = 0

    for node in nodes:
        message = node.get("message") or {}
        role = (message.get("author") or {}).get("role", "").lower()
        text = extract_node_text(node)
        if not text:
            continue
        if role == "user":
            if current_prompt or current_response_parts:
                pair_index += 1
                response_text = normalize_whitespace(" ".join(current_response_parts))
                summary = shorten(f"User: {current_prompt} Assistant: {response_text}", 240)
                pair_id = f"{thread_uid}-pair-{pair_index:03d}"
                pairs.append(
                    {
                        "pair_id": pair_id,
                        "thread_uid": thread_uid,
                        "title": current_title
                        or shorten(current_prompt, 80)
                        or f"ChatGPT Pair {pair_index:03d}",
                        "summary": summary,
                        "search_text": f"{pair_id} {current_prompt} {response_text}",
                        "themes": top_keywords(f"{current_prompt} {response_text}", limit=8),
                        "entities": [],
                        "family_ids": [family_id],
                        "vector_terms": vector_terms(f"{current_prompt} {response_text}"),
                    },
                )
            current_prompt = text
            current_title = shorten(text, 80)
            current_response_parts = []
        elif role == "assistant":
            if not current_prompt:
                current_prompt = "[assistant-led]"
                current_title = "Assistant-Led Turn"
            current_response_parts.append(text)

    if current_prompt or current_response_parts:
        pair_index += 1
        response_text = normalize_whitespace(" ".join(current_response_parts))
        summary = shorten(f"User: {current_prompt} Assistant: {response_text}", 240)
        pair_id = f"{thread_uid}-pair-{pair_index:03d}"
        pairs.append(
            {
                "pair_id": pair_id,
                "thread_uid": thread_uid,
                "title": current_title or f"ChatGPT Pair {pair_index:03d}",
                "summary": summary,
                "search_text": f"{pair_id} {current_prompt} {response_text}",
                "themes": top_keywords(f"{current_prompt} {response_text}", limit=8),
                "entities": [],
                "family_ids": [family_id],
                "vector_terms": vector_terms(f"{current_prompt} {response_text}"),
            },
        )
    return pairs


def build_entities(title: str, keywords: list[str]) -> list[dict[str, str]]:
    entities = [{"canonical_label": title, "entity_type": "conversation"}]
    for keyword in keywords[:3]:
        entities.append(
            {"canonical_label": keyword.replace("-", " ").title(), "entity_type": "concept"}
        )
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for entity in entities:
        label = normalize_whitespace(entity["canonical_label"])
        lowered = label.lower()
        if not label or lowered in seen:
            continue
        seen.add(lowered)
        result.append({"canonical_label": label, "entity_type": entity["entity_type"]})
    return result


def build_thread_audit(
    mapping: dict[str, Any],
    nodes: list[dict[str, Any]],
    extracted_texts: list[str],
    pairs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build per-thread audit statistics: role/content_type counts, retention, quality flags."""
    raw_role_counts: Counter[str] = Counter()
    raw_content_type_counts: Counter[str] = Counter()
    for node in mapping.values():
        message = node.get("message") or {}
        role = ((message.get("author") or {}).get("role")) or "none"
        ct = (message.get("content") or {}).get("content_type") or "none"
        raw_role_counts[role] += 1
        raw_content_type_counts[ct] += 1

    path_role_counts: Counter[str] = Counter()
    skipped_count = 0
    empty_render_count = 0
    for node in nodes:
        message = node.get("message") or {}
        role = ((message.get("author") or {}).get("role")) or "none"
        path_role_counts[role] += 1
        text = extract_node_text(node)
        if not text:
            skipped_count += 1
            ct = (message.get("content") or {}).get("content_type") or "none"
            if ct not in SKIP_CONTENT_TYPES and role != "system":
                empty_render_count += 1

    retained = len(extracted_texts)
    retention_ratio = round(retained / len(nodes), 4) if nodes else 0.0

    flags: list[str] = []
    if retention_ratio < 0.65 and len(nodes) > 4:
        flags.append("low_retention")
    if empty_render_count > 5:
        flags.append("high_empty_render")
    if any(not p.get("summary", "").strip() for p in pairs):
        flags.append("pair_without_response")

    return {
        "mapping_node_count": len(mapping),
        "path_node_count": len(nodes),
        "retained_count": retained,
        "skipped_count": skipped_count,
        "empty_render_count": empty_render_count,
        "retention_ratio": retention_ratio,
        "raw_role_counts": dict(raw_role_counts),
        "raw_content_type_counts": dict(raw_content_type_counts),
        "path_role_counts": dict(path_role_counts),
        "quality_flags": flags,
    }


def _trigram_fingerprint(text: str) -> frozenset[str]:
    """Build character trigram set from tokenized text for fast similarity screening."""
    tokens = [t for t in tokenize(text.lower()) if t not in STOP_WORDS and len(t) > 2]
    trigrams: set[str] = set()
    for token in tokens:
        for k in range(len(token) - 2):
            trigrams.add(token[k : k + 3])
    return frozenset(trigrams)


def detect_near_duplicates(
    threads: list[dict[str, Any]],
    first_prompts: dict[str, str],
    *,
    threshold: float = 0.92,
    throttle: float = 0.0,
) -> list[dict[str, Any]]:
    """Detect near-duplicate threads by comparing first user prompts.

    Uses a trigram Jaccard pre-filter to avoid expensive SequenceMatcher calls
    on clearly dissimilar pairs. The Jaccard threshold (0.35) is conservative —
    any pair with SequenceMatcher ratio >= 0.92 will pass the pre-filter.
    """
    candidates: list[dict[str, Any]] = []
    uid_to_index = {t["thread_uid"]: idx for idx, t in enumerate(threads)}
    uids = [t["thread_uid"] for t in threads]

    # Pre-compute fingerprints for eligible prompts
    fingerprints: dict[str, frozenset[str]] = {}
    for uid in uids:
        prompt = first_prompts.get(uid, "")
        if len(prompt) >= 20:
            fingerprints[uid] = _trigram_fingerprint(prompt[:500])

    eligible = [uid for uid in uids if uid in fingerprints]

    for i in range(len(eligible)):
        fp_a = fingerprints[eligible[i]]
        prompt_a = first_prompts[eligible[i]][:500]
        if throttle > 0 and i % 50 == 0:
            time.sleep(throttle)
        for j in range(i + 1, len(eligible)):
            fp_b = fingerprints[eligible[j]]
            # Fast Jaccard pre-filter (frozenset ops, microseconds per pair)
            union_size = len(fp_a | fp_b)
            if union_size == 0:
                continue
            if len(fp_a & fp_b) / union_size < 0.35:
                continue
            # Expensive comparison only for plausible candidates
            prompt_b = first_prompts[eligible[j]][:500]
            ratio = SequenceMatcher(None, prompt_a, prompt_b).ratio()
            if ratio >= threshold:
                candidates.append(
                    {
                        "thread_uids": [eligible[i], eligible[j]],
                        "similarity": round(ratio, 4),
                        "titles": [
                            threads[uid_to_index[eligible[i]]].get("title_normalized", ""),
                            threads[uid_to_index[eligible[j]]].get("title_normalized", ""),
                        ],
                    }
                )
    return candidates


def copy_bundle_files(bundle_root: Path, output_root: Path) -> list[str]:
    copied: list[str] = []
    source_root = output_root / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(bundle_root.rglob("*.json")):
        relative = path.relative_to(bundle_root)
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied.append(str(destination))
    return copied


def import_chatgpt_export_corpus(
    input_path: Path,
    output_root: Path,
    *,
    corpus_id: str | None = None,
    name: str | None = None,
    throttle: float = 0.0,
) -> dict[str, Any]:
    bundle_root = resolve_bundle_root(input_path)
    conversations = load_json_file(bundle_root / "conversations.json", default=[])
    user = load_json_file(bundle_root / "user.json", default={})

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "corpus").mkdir(parents=True, exist_ok=True)

    copied_sources = copy_bundle_files(bundle_root, output_root)

    threads: list[dict[str, Any]] = []
    semantic_threads: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    doctrine_briefs: list[dict[str, Any]] = []
    family_dossiers: list[dict[str, Any]] = []
    canonical_families: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    import_manifest: list[dict[str, Any]] = []
    entity_map: dict[str, dict[str, Any]] = {}
    thread_audits: list[dict[str, Any]] = []
    first_prompts: dict[str, str] = {}

    imported_conversation_count = 0
    empty_conversation_count = 0

    for index, conversation in enumerate(conversations, start=1):
        mapping = conversation.get("mapping") or {}
        nodes = walk_mapping_tree(mapping)

        # Extract text from all non-system nodes
        extracted_texts = [extract_node_text(node) for node in nodes]
        extracted_texts = [t for t in extracted_texts if t]

        if not extracted_texts:
            empty_conversation_count += 1
            continue

        imported_conversation_count += 1
        title = infer_title_chatgpt(conversation, nodes, index)
        conversation_uuid = conversation.get("conversation_id") or f"chatgpt-{index:04d}"
        slug = slugify(f"{title}-{conversation_uuid[:8]}", limit=96)
        family_id = f"family-{slug}"
        thread_uid = f"thread-{slug}"
        combined_text = "\n".join(extracted_texts)
        sentences = split_sentences(combined_text)
        keywords = top_keywords(combined_text)
        vectors = vector_terms(combined_text)
        action_items_text = extract_actions(sentences)
        unresolved_items_text = extract_unresolved(sentences)
        summary = shorten(" ".join(sentences[:3]) or combined_text or title, 320)
        update_time = epoch_to_iso(
            conversation.get("update_time") or conversation.get("create_time")
        )
        key_entities = build_entities(title, keywords)
        semantic_entities = [entity["canonical_label"] for entity in key_entities]
        pair_items = build_pairs_chatgpt(nodes, thread_uid, family_id)
        for pair in pair_items:
            pair["entities"] = semantic_entities
        pairs.extend(pair_items)

        audit = build_thread_audit(mapping, nodes, extracted_texts, pair_items)
        audit["thread_uid"] = thread_uid
        thread_audits.append(audit)

        first_user = next(
            (
                extract_node_text(n)
                for n in nodes
                if ((n.get("message") or {}).get("author") or {}).get("role") == "user"
                and extract_node_text(n)
            ),
            "",
        )
        first_prompts[thread_uid] = first_user

        action_items = [
            {
                "action_key": f"action-{slugify(action, limit=64)}",
                "canonical_action": action,
                "status": "open",
                "family_ids": [family_id],
                "thread_uids": [thread_uid],
                "occurrence_count": 1,
            }
            for action in action_items_text
        ]
        unresolved_items = [
            {
                "question_key": f"question-{slugify(question, limit=64)}",
                "canonical_question": question,
                "why_unresolved": "Imported ChatGPT export conversation still implies an open question or unresolved branch.",
                "family_ids": [family_id],
                "thread_uids": [thread_uid],
                "occurrence_count": 1,
            }
            for question in unresolved_items_text
        ]

        tags = dedupe_preserve(["chatgpt-export", "json-export", "calibration-import"])
        threads.append(
            {
                "thread_uid": thread_uid,
                "conversation_id": conversation_uuid,
                "title_normalized": title,
                "title_raw": title,
                "answer_state": "imported_chatgpt_export",
                "tags": tags,
                "semantic_tags": ["chatgpt-thread"],
                "keywords": keywords,
                "semantic_themes": keywords[:6],
                "semantic_v2_themes": keywords[:8],
                "semantic_v3_themes": keywords[:8],
                "semantic_v3_entities": semantic_entities,
                "semantic_summary": summary,
                "semantic_v2_summary": summary,
                "semantic_v3_summary": f"{title} imported ChatGPT conversation centered on {', '.join(keywords[:4])}.",
                "action_count": len(action_items),
                "unresolved_question_count": len(unresolved_items),
                "audit_flags": audit.get("quality_flags", []),
                "thread_path": str(output_root / "source" / "conversations.json"),
                "family_ids": [family_id],
                "update_time_iso": update_time,
            },
        )
        semantic_threads.append(
            {
                "thread_uid": thread_uid,
                "title": title,
                "summary": summary,
                "search_text": f"{title} {combined_text}",
                "family_ids": [family_id],
                "vector_terms": vectors,
            },
        )
        doctrine_briefs.append(
            {
                "family_id": family_id,
                "canonical_title": title,
                "canonical_thread_uid": thread_uid,
                "member_count": 1,
                "stable_themes": keywords[:8],
                "brief_text": f"{title} currently centers on {', '.join(keywords[:4])}. Imported from ChatGPT export {bundle_root.name}.",
                "search_text": f"{title} {' '.join(keywords[:10])} {combined_text}",
                "vector_terms": vectors,
            },
        )
        family_dossiers.append(
            {
                "family_id": family_id,
                "canonical_title": title,
                "canonical_thread_uid": thread_uid,
                "member_count": 1,
                "stable_themes": keywords[:8],
                "doctrine_summary": f"{title} imported ChatGPT conversation summary: {summary}",
                "search_text": f"{title} doctrine {' '.join(keywords[:10])} {combined_text}",
                "actions": [
                    {"action_key": item["action_key"], "canonical_action": item["canonical_action"]}
                    for item in action_items
                ],
                "unresolved": [
                    {
                        "question_key": item["question_key"],
                        "canonical_question": item["canonical_question"],
                    }
                    for item in unresolved_items
                ],
                "key_entities": key_entities,
                "vector_terms": vectors,
            },
        )
        canonical_families.append(
            {
                "canonical_family_id": family_id,
                "canonical_title": title,
                "canonical_thread_uid": thread_uid,
                "thread_uids": [thread_uid],
            },
        )
        actions.extend(action_items)
        unresolved.extend(unresolved_items)
        for entity in key_entities:
            key = entity["canonical_label"].lower()
            existing = entity_map.setdefault(
                key,
                {
                    "canonical_entity_id": f"entity-{slugify(entity['canonical_label'], limit=64)}",
                    "canonical_label": entity["canonical_label"],
                    "entity_type": entity["entity_type"],
                    "aliases": [],
                },
            )
            existing["aliases"] = dedupe_preserve(existing.get("aliases", []) + [title])
        import_manifest.append(
            {
                "conversation_uuid": conversation_uuid,
                "thread_uid": thread_uid,
                "family_id": family_id,
                "pair_count": len(pair_items),
                "title": title,
            },
        )

    entities = list(entity_map.values())
    entity_aliases = [
        {"canonical_label": entity["canonical_label"], "labels": entity.get("aliases", [])}
        for entity in entities
        if entity.get("aliases")
    ]

    near_duplicates = detect_near_duplicates(threads, first_prompts, throttle=throttle)

    corpus_dir = output_root / "corpus"
    source_snapshot = build_source_snapshot(bundle_root, "chatgpt-export", "bundle-json")
    write_json(corpus_dir / "threads-index.json", threads)
    write_json(corpus_dir / "semantic-v3-index.json", {"threads": semantic_threads})
    write_json(corpus_dir / "pairs-index.json", pairs)
    write_json(corpus_dir / "doctrine-briefs.json", doctrine_briefs)
    write_json(corpus_dir / "family-dossiers.json", family_dossiers)
    write_json(corpus_dir / "canonical-families.json", canonical_families)
    write_json(corpus_dir / "action-ledger.json", actions)
    write_json(corpus_dir / "unresolved-ledger.json", unresolved)
    write_json(corpus_dir / "canonical-entities.json", entities)
    write_json(corpus_dir / "entity-aliases.json", entity_aliases)
    write_json(corpus_dir / "doctrine-timeline.json", [])
    write_json(corpus_dir / "import-audit.json", thread_audits)
    if near_duplicates:
        write_json(corpus_dir / "near-duplicates.json", near_duplicates)
    write_json(corpus_dir / "source-snapshot.json", source_snapshot)
    write_json(
        corpus_dir / "contract.json",
        {
            "contract_name": CONTRACT_NAME,
            "contract_version": CONTRACT_VERSION,
            "adapter_type": "chatgpt-export",
            "corpus_id": slugify(corpus_id or output_root.name),
            "name": name or output_root.name,
            "generated_at": now_iso(),
            "required_files": [
                "corpus/threads-index.json",
                "corpus/semantic-v3-index.json",
                "corpus/pairs-index.json",
                "corpus/doctrine-briefs.json",
                "corpus/family-dossiers.json",
            ],
            "counts": {
                "threads": len(threads),
                "families": len(canonical_families),
                "pairs": len(pairs),
                "actions": len(actions),
                "unresolved": len(unresolved),
                "entities": len(entities),
                "users": 1 if user else 0,
                "empty_conversations": empty_conversation_count,
                "near_duplicates": len(near_duplicates),
                "flagged_threads": sum(1 for a in thread_audits if a.get("quality_flags")),
            },
            "source_input": str(bundle_root),
            "collection_scope": "bundle-json",
            "source_snapshot_path": "corpus/source-snapshot.json",
            "source_signature_fingerprint": source_snapshot.get("signature_fingerprint"),
            "source_content_fingerprint": source_snapshot.get("content_fingerprint"),
            "source_file_count": source_snapshot.get("file_count"),
            "source_total_bytes": source_snapshot.get("total_bytes"),
            "source_latest_mtime_ns": source_snapshot.get("latest_mtime_ns"),
        },
    )
    write_json(
        corpus_dir / "evaluation-summary.json",
        {
            "generated_at": now_iso(),
            "fixture_sources": {"manual": {"source": "unavailable", "count": 0}},
            "regression_gates": {"overall_state": "warn", "source_reliability_state": "warn"},
            "notes": ["Imported ChatGPT export corpus has not been manually evaluated."],
        },
    )
    write_json(
        corpus_dir / "regression-gates.json",
        {
            "generated_at": now_iso(),
            "overall_state": "warn",
            "source_reliability_state": "warn",
            "source_notes": ["Imported ChatGPT export corpus has not been manually evaluated."],
            "gates": [],
        },
    )
    write_json(output_root / "import-manifest.json", import_manifest)
    write_markdown(
        output_root / "README.md",
        "\n".join(
            [
                "# ChatGPT History Memory Corpus",
                "",
                f"- Generated: {now_iso()}",
                f"- Source input: {bundle_root}",
                f"- Imported conversations: {imported_conversation_count}",
                f"- Empty conversations skipped: {empty_conversation_count}",
                f"- Pair count: {len(pairs)}",
                f"- Action count: {len(actions)}",
                f"- Unresolved count: {len(unresolved)}",
                f"- Copied source files: {len(copied_sources)}",
                f"- Contract manifest: {corpus_dir / 'contract.json'}",
                "",
                "This corpus is federation-compatible but unevaluated. Its regression gate state is intentionally `warn` until manual fixtures are added.",
            ],
        ),
    )

    resolved_corpus_id = corpus_id or output_root.name
    return {
        "corpus_id": slugify(resolved_corpus_id),
        "name": name or output_root.name,
        "output_root": str(output_root),
        "thread_count": len(threads),
        "pair_count": len(pairs),
        "action_count": len(actions),
        "unresolved_count": len(unresolved),
        "empty_conversation_count": empty_conversation_count,
        "near_duplicate_count": len(near_duplicates),
        "flagged_thread_count": sum(1 for a in thread_audits if a.get("quality_flags")),
        "manifest_path": str(output_root / "import-manifest.json"),
        "readme_path": str(output_root / "README.md"),
    }


def main() -> int:
    args = parse_args()
    result = import_chatgpt_export_corpus(
        args.input_path,
        args.output_root,
        corpus_id=args.corpus_id,
        name=args.name,
    )
    print(json.dumps(result, indent=2) if args.json else json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
