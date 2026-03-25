from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.provider_exports import (  # noqa: E402
    collect_supported_export_files,
    resolve_chatgpt_source_path,
    resolve_claude_source_path,
    resolve_document_export_source_path,
    visible_entries,
)


def test_visible_entries_ignores_hidden_and_system_names(tmp_path: Path) -> None:
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".DS_Store").write_text("", encoding="utf-8")
    (tmp_path / "export.zip").write_text("zip", encoding="utf-8")
    (tmp_path / "visible").mkdir()

    assert [entry.name for entry in visible_entries(tmp_path)] == ["export.zip", "visible"]


def test_collect_supported_export_files_skips_ignored_locations(tmp_path: Path) -> None:
    kept_root = tmp_path / "export.md"
    kept_nested = tmp_path / "nested" / "notes.txt"
    ignored_git = tmp_path / ".git" / "ignored.json"
    ignored_modules = tmp_path / "node_modules" / "ignored.csv"
    ignored_hidden = tmp_path / ".cache" / "hidden.md"
    unsupported = tmp_path / "image.png"

    kept_root.write_text("# export\n", encoding="utf-8")
    kept_nested.parent.mkdir(parents=True, exist_ok=True)
    kept_nested.write_text("notes\n", encoding="utf-8")
    ignored_git.parent.mkdir(parents=True, exist_ok=True)
    ignored_git.write_text("{}", encoding="utf-8")
    ignored_modules.parent.mkdir(parents=True, exist_ok=True)
    ignored_modules.write_text("a,b\n", encoding="utf-8")
    ignored_hidden.parent.mkdir(parents=True, exist_ok=True)
    ignored_hidden.write_text("hidden\n", encoding="utf-8")
    unsupported.write_text("png\n", encoding="utf-8")

    assert collect_supported_export_files(tmp_path) == [kept_root.resolve(), kept_nested.resolve()]


def test_resolve_document_export_source_path_selects_single_eligible_child(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "export.md").write_text("# export\n", encoding="utf-8")

    assert resolve_document_export_source_path(tmp_path, provider="perplexity") == bundle.resolve()


def test_resolve_document_export_source_path_rejects_multiple_eligible_children(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "export.md").write_text("# first\n", encoding="utf-8")
    (second / "export.md").write_text("# second\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Multiple Perplexity export candidates"):
        resolve_document_export_source_path(tmp_path, provider="perplexity")


def test_resolve_chatgpt_source_path_finds_nested_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "chatgpt-export"
    bundle.mkdir()
    (bundle / "conversations.json").write_text("[]", encoding="utf-8")
    (bundle / "user.json").write_text("{}", encoding="utf-8")

    assert resolve_chatgpt_source_path(tmp_path) == bundle.resolve()


def test_resolve_claude_source_path_finds_nested_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "claude-export"
    bundle.mkdir()
    (bundle / "conversations.json").write_text("[]", encoding="utf-8")
    (bundle / "users.json").write_text("[]", encoding="utf-8")

    assert resolve_claude_source_path(tmp_path) == bundle.resolve()
