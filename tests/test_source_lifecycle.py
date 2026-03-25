from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conversation_corpus_engine.source_lifecycle import (
    build_source_signature,
    build_source_snapshot,
    collect_source_files,
    compute_source_freshness,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_collect_source_files_for_markdown_document_respects_top_level_scope(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "markdown"
    (source_root / "top.md").parent.mkdir(parents=True, exist_ok=True)
    (source_root / "top.md").write_text("# top\n", encoding="utf-8")
    (source_root / "nested" / "deep.md").parent.mkdir(parents=True, exist_ok=True)
    (source_root / "nested" / "deep.md").write_text("# deep\n", encoding="utf-8")

    top_level = collect_source_files(source_root, "markdown-document", "top-level")
    recursive = collect_source_files(source_root, "markdown-document", "recursive")

    assert top_level == [(source_root / "top.md").resolve()]
    assert recursive == [
        (source_root / "nested" / "deep.md").resolve(),
        (source_root / "top.md").resolve(),
    ]


def test_collect_source_files_for_markdown_transcript_includes_attachments(tmp_path: Path) -> None:
    transcript = tmp_path / "session.md"
    transcript.write_text("# Session\n", encoding="utf-8")
    attachments = tmp_path / "Attachments"
    attachments.mkdir()
    (attachments / "image.png").write_bytes(b"png-bytes")

    files = collect_source_files(transcript, "markdown-transcript", None)

    assert files == [
        (attachments / "image.png").resolve(),
        transcript.resolve(),
    ]


def test_collect_source_files_for_claude_local_session_tracks_only_supported_paths(
    tmp_path: Path,
) -> None:
    local_root = tmp_path / "claude-local"
    (local_root / "Cookies").parent.mkdir(parents=True, exist_ok=True)
    (local_root / "Cookies").write_text("cookies", encoding="utf-8")
    (local_root / "Local Storage" / "leveldb" / "0001.log").parent.mkdir(
        parents=True, exist_ok=True
    )
    (local_root / "Local Storage" / "leveldb" / "0001.log").write_text(
        "leveldb", encoding="utf-8"
    )
    (
        local_root / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb" / "LOG"
    ).parent.mkdir(parents=True, exist_ok=True)
    (
        local_root / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb" / "LOG"
    ).write_text("indexeddb", encoding="utf-8")
    (local_root / "random" / "ignore.txt").parent.mkdir(parents=True, exist_ok=True)
    (local_root / "random" / "ignore.txt").write_text("ignore", encoding="utf-8")

    files = collect_source_files(local_root, "claude-local-session", "local-session")

    assert files == [
        (local_root / "Cookies").resolve(),
        (local_root / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb" / "LOG").resolve(),
        (local_root / "Local Storage" / "leveldb" / "0001.log").resolve(),
    ]


def test_build_source_signature_handles_supported_export_adapters_and_unsupported_types(
    tmp_path: Path,
) -> None:
    export_root = tmp_path / "exports"
    (export_root / "notes.md").parent.mkdir(parents=True, exist_ok=True)
    (export_root / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (export_root / "nested" / "events.json").parent.mkdir(parents=True, exist_ok=True)
    (export_root / "nested" / "events.json").write_text("{}", encoding="utf-8")
    (export_root / ".git" / "ignored.md").parent.mkdir(parents=True, exist_ok=True)
    (export_root / ".git" / "ignored.md").write_text("ignored", encoding="utf-8")

    supported = build_source_signature(export_root, "perplexity-export", "export-bundle")
    unsupported = build_source_signature(export_root / "missing", "unknown-adapter", None)

    assert supported["supported"] is True
    assert supported["exists"] is True
    assert supported["file_count"] == 2
    assert [entry["relative_path"] for entry in supported["files"]] == [
        "nested/events.json",
        "notes.md",
    ]
    assert supported["signature_fingerprint"]

    assert unsupported["supported"] is False
    assert unsupported["exists"] is False
    assert unsupported["file_count"] == 0


def test_compute_source_freshness_returns_not_applicable_for_non_refreshable_corpus(
    tmp_path: Path,
) -> None:
    corpus_root = tmp_path / "corpus-root"
    _write_json(
        corpus_root / "corpus" / "contract.json",
        {
            "adapter_type": "manual-export",
            "name": "Manual Corpus",
        },
    )

    freshness = compute_source_freshness(corpus_root)

    assert freshness["state"] == "not_applicable"
    assert freshness["needs_refresh"] is False
    assert freshness["can_refresh"] is False


def test_compute_source_freshness_reports_missing_snapshot_then_fresh_then_stale(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_file = source_root / "session.md"
    source_file.write_text("# Session\n\nAlpha registry doctrine.\n", encoding="utf-8")

    corpus_root = tmp_path / "corpus-root"
    _write_json(
        corpus_root / "corpus" / "contract.json",
        {
            "adapter_type": "markdown-document",
            "source_input": str(source_root.resolve()),
            "collection_scope": "recursive",
        },
    )

    missing_snapshot = compute_source_freshness(corpus_root)
    snapshot = build_source_snapshot(source_root, "markdown-document", "recursive")
    _write_json(corpus_root / "corpus" / "source-snapshot.json", snapshot)
    fresh = compute_source_freshness(corpus_root)
    source_file.write_text("# Session\n\nAlpha registry doctrine changed.\n", encoding="utf-8")
    stale = compute_source_freshness(corpus_root)

    assert missing_snapshot["state"] == "missing_snapshot"
    assert missing_snapshot["needs_refresh"] is True
    assert snapshot["content_fingerprint"]
    assert snapshot["fingerprint"] == snapshot["content_fingerprint"]
    assert snapshot["files"][0]["sha256"]

    assert fresh["state"] == "fresh"
    assert fresh["needs_refresh"] is False
    assert fresh["stored_signature_fingerprint"] == fresh["current_signature_fingerprint"]

    assert stale["state"] == "stale"
    assert stale["needs_refresh"] is True
    assert stale["stored_signature_fingerprint"] != stale["current_signature_fingerprint"]


def test_compute_source_freshness_reports_missing_source_when_contract_path_is_gone(
    tmp_path: Path,
) -> None:
    missing_source = tmp_path / "missing-source"
    corpus_root = tmp_path / "corpus-root"
    _write_json(
        corpus_root / "corpus" / "contract.json",
        {
            "adapter_type": "markdown-document",
            "source_input": str(missing_source.resolve()),
            "collection_scope": "recursive",
            "source_signature_fingerprint": "stale-fingerprint",
        },
    )

    freshness = compute_source_freshness(corpus_root)

    assert freshness["state"] == "missing_source"
    assert freshness["needs_refresh"] is False
    assert freshness["can_refresh"] is False
    assert freshness["stored_signature_fingerprint"] == "stale-fingerprint"
