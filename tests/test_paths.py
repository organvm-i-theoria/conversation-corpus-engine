from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine import paths as module  # noqa: E402


def test_default_project_root_prefers_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "project-root"
    monkeypatch.setenv("CCE_PROJECT_ROOT", str(override))

    assert module.default_project_root() == override.resolve()


def test_default_project_root_falls_back_to_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CCE_PROJECT_ROOT", raising=False)

    assert module.default_project_root() == module.REPO_ROOT
