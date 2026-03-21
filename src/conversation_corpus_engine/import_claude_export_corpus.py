#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .answering import slugify, tokenize, write_json, write_markdown
from .source_lifecycle import build_source_snapshot

DEFAULT_OUTPUT_ROOT = Path.cwd() / "claude-history-memory"
CONTRACT_NAME = "conversation-corpus-engine-v1"
CONTRACT_VERSION = 1
REQUIRED_BUNDLE_FILES = ("conversations.json", "users.json")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a Claude JSON export bundle into a federation-compatible memory corpus."
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
                f"Expected a Claude export directory or conversations.json file, got {input_path}"
            )
    else:
        bundle_root = input_path
    missing = [name for name in REQUIRED_BUNDLE_FILES if not (bundle_root / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Claude export bundle at {bundle_root} is missing required files: {', '.join(missing)}"
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


def infer_title(conversation: dict[str, Any], fallback_index: int) -> str:
    for candidate in (
        conversation.get("name"),
        conversation.get("summary"),
    ):
        if isinstance(candidate, str) and normalize_whitespace(candidate):
            return normalize_whitespace(candidate)
    messages = conversation.get("chat_messages") or []
    for message in messages:
        extracted = extract_message_text(message)
        if extracted:
            return shorten(extracted, 120)
    return f"Claude Conversation {fallback_index:04d}"


def summarize_tool_use(item: dict[str, Any]) -> str:
    name = item.get("name") or "tool"
    payload = item.get("input") or {}
    title = payload.get("title") or payload.get("id") or payload.get("type")
    if title:
        return f"[tool_use:{name}:{title}]"
    return f"[tool_use:{name}]"


def summarize_tool_result(item: dict[str, Any]) -> str:
    name = item.get("name") or "tool"
    content = item.get("content") or []
    text_items = []
    for subitem in content:
        if subitem.get("type") == "text":
            value = normalize_whitespace(subitem.get("text") or "")
            if value and value.upper() != "OK":
                text_items.append(value)
    if text_items:
        return shorten(f"[tool_result:{name}] " + " ".join(text_items), 200)
    if item.get("is_error"):
        return f"[tool_result:{name}:error]"
    return f"[tool_result:{name}]"


def extract_message_text(message: dict[str, Any]) -> str:
    segments: list[str] = []
    raw_text = normalize_whitespace(message.get("text") or "")
    if raw_text:
        segments.append(raw_text)
    for item in message.get("content") or []:
        item_type = item.get("type")
        if item_type == "text":
            value = normalize_whitespace(item.get("text") or "")
            if value and value not in segments:
                segments.append(value)
        elif item_type == "tool_use":
            segments.append(summarize_tool_use(item))
        elif item_type == "tool_result":
            segments.append(summarize_tool_result(item))
    for attachment in message.get("attachments") or []:
        name = attachment.get("file_name") or attachment.get("name")
        if name:
            segments.append(f"[attachment:{name}]")
    for file_entry in message.get("files") or []:
        name = file_entry.get("file_name") or file_entry.get("name")
        if name:
            segments.append(f"[file:{name}]")
    return normalize_whitespace(" ".join(segment for segment in segments if segment))


def timestamp_for_message(message: dict[str, Any]) -> str:
    return message.get("created_at") or message.get("updated_at") or now_iso()


def sorted_messages(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(conversation.get("chat_messages") or [], key=timestamp_for_message)


def build_pairs(
    messages: list[dict[str, Any]], thread_uid: str, family_id: str
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    current_prompt = ""
    current_response_parts: list[str] = []
    current_title = ""
    pair_index = 0

    for message in messages:
        sender = (message.get("sender") or "").lower()
        text = extract_message_text(message)
        if not text:
            continue
        if sender == "human":
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
                        or f"Claude Pair {pair_index:03d}",
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
        else:
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
                "title": current_title or f"Claude Pair {pair_index:03d}",
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


def import_claude_export_corpus(
    input_path: Path,
    output_root: Path,
    *,
    corpus_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    bundle_root = resolve_bundle_root(input_path)
    conversations = load_json_file(bundle_root / "conversations.json", default=[])
    projects = load_json_file(bundle_root / "projects.json", default=[])
    memories = load_json_file(bundle_root / "memories.json", default=[])
    users = load_json_file(bundle_root / "users.json", default=[])

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

    imported_conversation_count = 0
    empty_conversation_count = 0
    for index, conversation in enumerate(conversations, start=1):
        messages = sorted_messages(conversation)
        extracted_messages = [extract_message_text(message) for message in messages]
        extracted_messages = [text for text in extracted_messages if text]
        if not extracted_messages:
            empty_conversation_count += 1
            continue

        imported_conversation_count += 1
        title = infer_title(conversation, index)
        conversation_uuid = conversation.get("uuid") or f"claude-{index:04d}"
        slug = slugify(f"{title}-{conversation_uuid[:8]}", limit=96)
        family_id = f"family-{slug}"
        thread_uid = f"thread-{slug}"
        combined_text = "\n".join(extracted_messages)
        sentences = split_sentences(combined_text)
        keywords = top_keywords(combined_text)
        vectors = vector_terms(combined_text)
        action_items_text = extract_actions(sentences)
        unresolved_items_text = extract_unresolved(sentences)
        summary = shorten(" ".join(sentences[:3]) or combined_text or title, 320)
        update_time = conversation.get("updated_at") or conversation.get("created_at") or now_iso()
        key_entities = build_entities(title, keywords)
        semantic_entities = [entity["canonical_label"] for entity in key_entities]
        pair_items = build_pairs(messages, thread_uid, family_id)
        for pair in pair_items:
            pair["entities"] = semantic_entities
        pairs.extend(pair_items)

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
                "why_unresolved": "Imported Claude export conversation still implies an open question or unresolved branch.",
                "family_ids": [family_id],
                "thread_uids": [thread_uid],
                "occurrence_count": 1,
            }
            for question in unresolved_items_text
        ]

        tags = dedupe_preserve(["claude-export", "json-export", "calibration-import"])
        threads.append(
            {
                "thread_uid": thread_uid,
                "conversation_id": conversation_uuid,
                "title_normalized": title,
                "title_raw": title,
                "answer_state": "imported_claude_export",
                "tags": tags,
                "semantic_tags": ["claude-thread"],
                "keywords": keywords,
                "semantic_themes": keywords[:6],
                "semantic_v2_themes": keywords[:8],
                "semantic_v3_themes": keywords[:8],
                "semantic_v3_entities": semantic_entities,
                "semantic_summary": summary,
                "semantic_v2_summary": summary,
                "semantic_v3_summary": f"{title} imported Claude conversation centered on {', '.join(keywords[:4])}.",
                "action_count": len(action_items),
                "unresolved_question_count": len(unresolved_items),
                "audit_flags": [],
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
                "brief_text": f"{title} currently centers on {', '.join(keywords[:4])}. Imported from Claude export {bundle_root.name}.",
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
                "doctrine_summary": f"{title} imported Claude conversation summary: {summary}",
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

    corpus_dir = output_root / "corpus"
    source_snapshot = build_source_snapshot(bundle_root, "claude-export", "bundle-json")
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
    write_json(corpus_dir / "source-snapshot.json", source_snapshot)
    write_json(
        corpus_dir / "contract.json",
        {
            "contract_name": CONTRACT_NAME,
            "contract_version": CONTRACT_VERSION,
            "adapter_type": "claude-export",
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
                "projects": len(projects),
                "memories": len(memories),
                "users": len(users),
                "empty_conversations": empty_conversation_count,
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
            "notes": ["Imported Claude export corpus has not been manually evaluated."],
        },
    )
    write_json(
        corpus_dir / "regression-gates.json",
        {
            "generated_at": now_iso(),
            "overall_state": "warn",
            "source_reliability_state": "warn",
            "source_notes": ["Imported Claude export corpus has not been manually evaluated."],
            "gates": [],
        },
    )
    write_json(output_root / "import-manifest.json", import_manifest)
    write_markdown(
        output_root / "README.md",
        "\n".join(
            [
                "# Claude History Memory Corpus",
                "",
                f"- Generated: {now_iso()}",
                f"- Source input: {bundle_root}",
                f"- Imported conversations: {imported_conversation_count}",
                f"- Empty conversations skipped: {empty_conversation_count}",
                f"- Pair count: {len(pairs)}",
                f"- Action count: {len(actions)}",
                f"- Unresolved count: {len(unresolved)}",
                f"- Projects observed: {len(projects)}",
                f"- Memories observed: {len(memories)}",
                f"- Users observed: {len(users)}",
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
        "manifest_path": str(output_root / "import-manifest.json"),
        "readme_path": str(output_root / "README.md"),
    }


def main() -> int:
    args = parse_args()
    result = import_claude_export_corpus(
        args.input_path,
        args.output_root,
        corpus_id=args.corpus_id,
        name=args.name,
    )
    print(json.dumps(result, indent=2) if args.json else json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
