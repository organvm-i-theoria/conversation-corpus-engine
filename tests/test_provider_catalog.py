from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.provider_catalog import (  # noqa: E402
    conventional_corpus_root,
    default_source_drop_root,
    get_provider_config,
    provider_bootstrap_report_path,
    provider_corpus_targets,
)
from conversation_corpus_engine.source_policy import set_source_policy  # noqa: E402


def seed_contract(root: Path, *, adapter_type: str = "chatgpt-history") -> None:
    corpus_dir = root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    (corpus_dir / "contract.json").write_text(
        json.dumps(
            {
                "contract_name": "conversation-corpus-engine-v1",
                "contract_version": 1,
                "adapter_type": adapter_type,
                "name": "Seed Corpus",
            }
        ),
        encoding="utf-8",
    )


def test_default_source_drop_root_prefers_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "override-source-drop"
    monkeypatch.setenv("CCE_SOURCE_DROP_ROOT", str(override))

    assert default_source_drop_root(tmp_path / "project") == override.resolve()


def test_default_source_drop_root_uses_project_parent_when_no_override(tmp_path: Path) -> None:
    project_root = tmp_path / "project"

    assert default_source_drop_root(project_root) == (tmp_path / "source-drop").resolve()


def test_get_provider_config_rejects_unknown_provider() -> None:
    with pytest.raises(KeyError, match="Unknown provider: unknown"):
        get_provider_config("unknown")


def test_provider_bootstrap_report_path_uses_reports_directory(tmp_path: Path) -> None:
    assert provider_bootstrap_report_path(tmp_path / "project", "claude") == (
        tmp_path / "project" / "reports" / "claude-evaluation-bootstrap-latest.md"
    ).resolve()


def test_conventional_corpus_root_uses_source_drop_parent(tmp_path: Path) -> None:
    source_drop_root = tmp_path / "source-drop"

    assert conventional_corpus_root(source_drop_root, "chatgpt-history") == (
        tmp_path / "chatgpt-history"
    ).resolve()


def test_provider_corpus_targets_prefers_viable_fallback_when_primary_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    source_drop_root = tmp_path / "source-drop"
    fallback_root = tmp_path / "chatgpt-history"
    seed_contract(fallback_root)

    targets = provider_corpus_targets(
        project_root,
        "chatgpt",
        source_drop_root,
        registry=[
            {
                "corpus_id": "chatgpt-history",
                "root": str(fallback_root),
            }
        ],
    )

    assert [target["role"] for target in targets] == ["primary", "fallback"]
    assert targets[0]["selected"] is False
    assert targets[1]["selected"] is True
    assert targets[1]["corpus_id"] == "chatgpt-history"


def test_provider_corpus_targets_respects_explicit_primary_policy(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    source_drop_root = tmp_path / "source-drop"
    primary_root = tmp_path / "explicit-primary"
    fallback_root = tmp_path / "chatgpt-history"
    seed_contract(fallback_root)
    set_source_policy(
        project_root,
        "chatgpt",
        primary_root=primary_root,
        primary_corpus_id="chatgpt-history-memory",
        fallback_root=fallback_root,
        fallback_corpus_id="chatgpt-history",
        note="Keep the explicit primary selected until manually changed.",
    )

    targets = provider_corpus_targets(project_root, "chatgpt", source_drop_root)

    assert [target["role"] for target in targets] == ["primary", "fallback"]
    assert targets[0]["selected"] is True
    assert targets[1]["selected"] is False
