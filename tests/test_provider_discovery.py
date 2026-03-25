from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine import provider_catalog  # noqa: E402
from conversation_corpus_engine.provider_discovery import (  # noqa: E402
    discover_provider_uploads,
    render_provider_discovery_text,
    summarize_provider,
)


def test_summarize_provider_marks_ready_and_local_source_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "source-drop" / "perplexity" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "export.md").write_text("# export\n", encoding="utf-8")
    local_root = tmp_path / "local-perplexity"
    local_root.mkdir()

    monkeypatch.setitem(
        provider_catalog.PROVIDER_CONFIG["perplexity"],
        "local_source_root",
        str(local_root),
    )

    summary = summarize_provider("perplexity", tmp_path / "source-drop")

    assert summary["upload_state"] == "ready"
    assert summary["detected_source_path"] == str(inbox.resolve())
    assert summary["local_source_state"] == "present"


def test_summarize_provider_marks_multiple_ready_for_chatgpt(tmp_path: Path) -> None:
    inbox = tmp_path / "source-drop" / "chatgpt" / "inbox"
    first = inbox / "first"
    second = inbox / "second"
    first.mkdir(parents=True, exist_ok=True)
    second.mkdir(parents=True, exist_ok=True)
    for bundle in (first, second):
        (bundle / "conversations.json").write_text("[]", encoding="utf-8")
        (bundle / "user.json").write_text("{}", encoding="utf-8")

    summary = summarize_provider("chatgpt", tmp_path / "source-drop")

    assert summary["upload_state"] == "multiple-ready"
    assert summary["detected_source_path"] is None


def test_summarize_provider_marks_multiple_ready_for_document_exports(tmp_path: Path) -> None:
    inbox = tmp_path / "source-drop" / "perplexity" / "inbox"
    first = inbox / "first"
    second = inbox / "second"
    first.mkdir(parents=True, exist_ok=True)
    second.mkdir(parents=True, exist_ok=True)
    (first / "export.md").write_text("# first\n", encoding="utf-8")
    (second / "export.md").write_text("# second\n", encoding="utf-8")

    summary = summarize_provider("perplexity", tmp_path / "source-drop")

    assert summary["upload_state"] == "multiple-ready"
    assert summary["detected_source_path"] is None


def test_discover_provider_uploads_counts_ready_and_present_unresolved(tmp_path: Path) -> None:
    ready_inbox = tmp_path / "source-drop" / "perplexity" / "inbox"
    unresolved_inbox = tmp_path / "source-drop" / "gemini" / "inbox"
    ready_inbox.mkdir(parents=True, exist_ok=True)
    unresolved_inbox.mkdir(parents=True, exist_ok=True)
    (ready_inbox / "export.md").write_text("# export\n", encoding="utf-8")
    (unresolved_inbox / "blob.bin").write_bytes(b"bin")

    payload = discover_provider_uploads(tmp_path / "project", tmp_path / "source-drop")

    assert payload["counts"]["ready_uploads"] == 1
    assert payload["counts"]["present_unresolved"] == 1


def test_render_provider_discovery_text_includes_detected_and_local_source() -> None:
    payload = {
        "source_drop_root": "/tmp/source-drop",
        "generated_at": "2026-03-25T00:00:00+00:00",
        "counts": {"providers": 1},
        "providers": [
            {
                "provider": "claude",
                "adapter_state": "supported",
                "upload_state": "ready",
                "inbox_root": "/tmp/source-drop/claude/inbox",
                "detected_source_path": "/tmp/source-drop/claude/inbox/export",
                "local_source_root": "/tmp/local-claude",
                "local_source_state": "present",
                "visible_entries": ["export"],
            }
        ],
    }

    text = render_provider_discovery_text(payload)

    assert "claude  adapter=supported  upload_state=ready" in text
    assert "detected_source: /tmp/source-drop/claude/inbox/export" in text
    assert "local_source: /tmp/local-claude (present)" in text
    assert "entries: export" in text
