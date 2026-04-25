#!/usr/bin/env python3
"""chatgpt_exporter_to_bundle — Convert third-party "ChatGPT Exporter" JSON dumps
into a standard ChatGPT-export bundle that the engine's `import_chatgpt_export_corpus`
adapter can ingest.

Background
----------
chatgptexporter.com is a third-party browser extension that exports ChatGPT
conversations one-per-file as `ChatGPT-<title>.json`, in a flat schema:

    {
      "metadata": {
        "title": "Biology as Code",
        "user": {"name": "...", "email": "..."},
        "dates": {"created": "M/D/YYYY H:M:S", "updated": "...", "exported": "..."},
        "link": "https://chatgpt.com/c/<uuid>",
        "powered_by": "ChatGPT Exporter (https://www.chatgptexporter.com)"
      },
      "messages": [
        {"role": "user"|"assistant", "say": "<text>", "time": "<HH:MM>"}
      ]
    }

The engine's official adapter expects the standard ChatGPT-export bundle:

    bundle/
      conversations.json    # list of conversations with mapping/parent/children
      user.json

This script reads a directory of `ChatGPT-*.json` files, converts each to a
mapping-tree conversation, and emits a synthetic bundle dir.

Usage
-----
    python scripts/chatgpt_exporter_to_bundle.py <input-dir> <output-bundle-dir>

Then ingest with the standard adapter:
    cce provider import chatgpt <output-bundle-dir>
    # or:
    python -m conversation_corpus_engine.import_chatgpt_export_corpus \\
        <output-bundle-dir> --output-root <corpus-out>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# chatgpt-exporter date format example: "1/3/2026 7:53:47"
_DATE_FORMATS = (
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %I:%M:%S %p",
)


def _parse_date(s: str | None) -> float | None:
    """Parse chatgpt-exporter date string to epoch seconds. Tolerates None/empty."""
    if not s:
        return None
    s = s.strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return None


def _conv_id_from_link(link: str | None, fallback: str) -> str:
    """Extract chatgpt.com/c/<uuid> from link, else hash fallback."""
    if link:
        m = re.search(r"/c/([0-9a-f-]{8,})", link)
        if m:
            return m.group(1)
    return hashlib.sha1(fallback.encode("utf-8")).hexdigest()[:36]


def _normalize_role(role: str | None) -> str:
    """Map chatgpt-exporter roles to standard ChatGPT-export roles."""
    if not role:
        return "user"
    r = role.strip().lower()
    if r in ("user", "human", "you"):
        return "user"
    if r in ("assistant", "chatgpt", "ai"):
        return "assistant"
    if r in ("system",):
        return "system"
    return "user"  # safest default


def convert_one(exporter_doc: dict, fallback_id: str) -> dict:
    """Convert a single chatgpt-exporter doc to a standard ChatGPT-export conversation.

    Builds a linear mapping tree: root → message_1 → message_2 → ... where each
    message is a node with parent=previous and children=[next].
    """
    metadata = exporter_doc.get("metadata") or {}
    messages = exporter_doc.get("messages") or []

    title = (metadata.get("title") or "").strip() or "Untitled"
    link = metadata.get("link") or ""
    dates = metadata.get("dates") or {}
    created_epoch = _parse_date(dates.get("created"))
    updated_epoch = _parse_date(dates.get("updated")) or created_epoch
    conv_id = _conv_id_from_link(link, fallback_id)

    # Build mapping tree
    mapping: dict[str, dict[str, Any]] = {}
    root_id = f"client-created-root-{conv_id}"
    mapping[root_id] = {
        "id": root_id,
        "parent": None,
        "children": [],
        "message": None,
    }

    prev_id = root_id
    base_time = created_epoch or 0.0
    for i, msg in enumerate(messages, start=1):
        node_id = f"msg-{conv_id}-{i:04d}"
        role = _normalize_role(msg.get("role"))
        text = (msg.get("say") or "").strip()
        if not text:
            continue
        # Each message gets a synthetic create_time stepping forward 1 second.
        # Real exporter timestamps are clock-of-day strings without dates,
        # so we synthesize monotone times anchored at the conversation's
        # create_time. This preserves order, which is what walk_mapping_tree needs.
        create_time = base_time + i if base_time else float(i)
        mapping[node_id] = {
            "id": node_id,
            "parent": prev_id,
            "children": [],
            "message": {
                "id": node_id,
                "author": {"role": role},
                "create_time": create_time,
                "content": {"content_type": "text", "parts": [text]},
            },
        }
        # Link parent → this child
        mapping[prev_id]["children"].append(node_id)
        prev_id = node_id

    return {
        "title": title,
        "create_time": created_epoch,
        "update_time": updated_epoch,
        "conversation_id": conv_id,
        "mapping": mapping,
    }


def discover_input_files(input_path: Path) -> list[Path]:
    """Return sorted list of ChatGPT-*.json files in input_path."""
    if not input_path.is_dir():
        raise NotADirectoryError(f"input must be a directory: {input_path}")
    return sorted(input_path.glob("ChatGPT-*.json"))


def convert_directory(input_dir: Path, output_bundle: Path) -> dict:
    """Read all ChatGPT-*.json files in input_dir, write a standard bundle to output_bundle."""
    files = discover_input_files(input_dir)
    if not files:
        raise FileNotFoundError(f"no ChatGPT-*.json files found under {input_dir}")

    seen_ids: set[str] = set()
    conversations: list[dict] = []
    skipped_duplicate = 0
    skipped_empty = 0

    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  skip (invalid JSON): {path.name} — {exc}", file=sys.stderr)
            continue
        conv = convert_one(doc, fallback_id=path.stem)
        # Skip conversations with no extractable text (would be empty downstream)
        non_root_nodes = [n for n in conv["mapping"].values() if n["message"] is not None]
        if not non_root_nodes:
            skipped_empty += 1
            continue
        if conv["conversation_id"] in seen_ids:
            skipped_duplicate += 1
            continue
        seen_ids.add(conv["conversation_id"])
        conversations.append(conv)

    output_bundle.mkdir(parents=True, exist_ok=True)
    (output_bundle / "conversations.json").write_text(
        json.dumps(conversations, ensure_ascii=False), encoding="utf-8"
    )
    (output_bundle / "user.json").write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")

    return {
        "input_dir": str(input_dir),
        "output_bundle": str(output_bundle),
        "files_scanned": len(files),
        "conversations_written": len(conversations),
        "skipped_duplicate": skipped_duplicate,
        "skipped_empty": skipped_empty,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_dir", type=Path, help="Directory of ChatGPT-*.json files")
    parser.add_argument(
        "output_bundle",
        type=Path,
        help="Output bundle directory (will contain conversations.json + user.json)",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    try:
        result = convert_directory(args.input_dir, args.output_bundle)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Scanned: {result['files_scanned']} files")
        print(f"Wrote:   {result['conversations_written']} conversations")
        print(f"Skipped: {result['skipped_duplicate']} duplicate, {result['skipped_empty']} empty")
        print(f"Bundle:  {result['output_bundle']}")
        print()
        print("Next: cce provider import chatgpt {}".format(result["output_bundle"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
