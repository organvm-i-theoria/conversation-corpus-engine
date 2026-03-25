from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.governance_policy import (  # noqa: E402
    DEFAULT_PROMOTION_POLICY,
    build_policy_calibration,
    load_or_create_promotion_policy,
    normalize_promotion_policy,
    policy_calibration_path,
    policy_with_overrides,
    promotion_policy_path,
    save_promotion_policy,
)


def test_normalize_promotion_policy_merges_defaults_without_mutating_input() -> None:
    payload = {
        "mode": "manual-review",
        "thresholds": {
            "max_warn_corpora": 0.5,
        },
    }

    normalized = normalize_promotion_policy(payload)

    assert normalized["mode"] == "manual-review"
    assert normalized["thresholds"]["max_warn_corpora"] == 0.5
    assert (
        normalized["thresholds"]["min_registered_active_corpora"]
        == DEFAULT_PROMOTION_POLICY["thresholds"]["min_registered_active_corpora"]
    )
    assert payload == {
        "mode": "manual-review",
        "thresholds": {
            "max_warn_corpora": 0.5,
        },
    }


def test_load_or_create_promotion_policy_writes_default_file(tmp_path: Path) -> None:
    project_root = tmp_path / "project"

    policy = load_or_create_promotion_policy(project_root)
    stored = json.loads(promotion_policy_path(project_root).read_text(encoding="utf-8"))

    assert policy == normalize_promotion_policy(DEFAULT_PROMOTION_POLICY)
    assert stored["thresholds"]["max_fail_corpora"] == 0.0


def test_save_promotion_policy_persists_updated_at_and_defaults(tmp_path: Path) -> None:
    project_root = tmp_path / "project"

    result = save_promotion_policy(
        project_root,
        {"thresholds": {"max_stale_corpora": 2.0}, "mode": "custom"},
    )
    stored = json.loads(promotion_policy_path(project_root).read_text(encoding="utf-8"))

    assert result["mode"] == "custom"
    assert result["thresholds"]["max_stale_corpora"] == 2.0
    assert result["updated_at"]
    assert stored == result


def test_policy_with_overrides_switches_to_candidate_preview(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    save_promotion_policy(project_root, {"mode": "review-governed"})

    result = policy_with_overrides(project_root, {"max_warn_corpora": 1.0})

    assert result["mode"] == "candidate-preview"
    assert result["thresholds"]["max_warn_corpora"] == 1.0
    assert result["thresholds"]["max_fail_corpora"] == 0.0


def test_build_policy_calibration_derives_learning_state_and_writes_file(tmp_path: Path) -> None:
    project_root = tmp_path / "project"

    ready = build_policy_calibration(
        project_root,
        replay_payload={
            "evaluation": {"overall_state": "pass"},
            "summary": {
                "active_corpus_count": 3,
                "manual_pass_rate": 0.9,
                "fail_corpus_count": 0,
                "warn_corpus_count": 0,
                "stale_corpus_count": 1,
            },
        },
    )
    observe = build_policy_calibration(
        project_root,
        replay_payload={"evaluation": {"overall_state": "warn"}, "summary": {}},
    )
    blocked = build_policy_calibration(project_root, replay_payload={"evaluation": {}})
    stored = json.loads(policy_calibration_path(project_root).read_text(encoding="utf-8"))

    assert ready["policy_learning"] == {"state": "ready", "reason": "pass"}
    assert ready["summary"]["active_corpus_count"] == 3
    assert ready["summary"]["stale_corpus_count"] == 1
    assert observe["policy_learning"] == {"state": "observe", "reason": "warn"}
    assert blocked["policy_learning"] == {"state": "blocked", "reason": "unknown"}
    assert stored == blocked
