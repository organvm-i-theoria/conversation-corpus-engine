from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine import paths as module  # noqa: E402
from conversation_corpus_engine.federation import validate_corpus_root  # noqa: E402


def test_default_project_root_prefers_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "project-root"
    monkeypatch.setenv("CCE_PROJECT_ROOT", str(override))

    assert module.default_project_root() == override.resolve()


def test_default_project_root_falls_back_to_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CCE_PROJECT_ROOT", raising=False)

    assert module.default_project_root() == module.REPO_ROOT


def _seed_minimal_corpus(root: Path) -> None:
    corpus_dir = root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for relative, payload in {
        "threads-index.json": [],
        "semantic-v3-index.json": {"threads": []},
        "pairs-index.json": [],
        "doctrine-briefs.json": [],
        "family-dossiers.json": [],
        "contract.json": {
            "contract_name": "conversation-corpus-engine-v1",
            "contract_version": 1,
        },
    }.items():
        (corpus_dir / relative).write_text(json.dumps(payload), encoding="utf-8")


def test_resolve_workspace_path_recovers_theoria_repo_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_root = tmp_path / "Workspace"
    actual_root = workspace_root / "organvm" / "conversation-corpus-engine"
    stale_root = workspace_root / "organvm-i-theoria" / "conversation-corpus-engine"
    _seed_minimal_corpus(actual_root)
    monkeypatch.setenv("CCE_WORKSPACE_ROOT", str(workspace_root))

    assert module.resolve_workspace_path(stale_root) == actual_root.resolve()
    assert validate_corpus_root(stale_root)["valid"] is True


def test_resolve_workspace_path_maps_victoroff_group_to_padavano(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_root = tmp_path / "Workspace"
    actual_root = workspace_root / "4444J99" / "padavano"
    stale_root = workspace_root / "victoroff-group"
    actual_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CCE_WORKSPACE_ROOT", str(workspace_root))

    assert module.resolve_workspace_path(stale_root) == actual_root.resolve()
