from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .answering import load_json, write_json

DEFAULT_PROMOTION_POLICY = {
    "version": 1,
    "mode": "review-governed",
    "thresholds": {
        "max_fail_corpora": 0.0,
        "max_warn_corpora": 0.0,
        "max_stale_corpora": 0.0,
        "max_missing_contract_corpora": 0.0,
        "min_manual_pass_rate": 1.0,
        "min_registered_active_corpora": 1.0,
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def promotion_policy_path(project_root: Path) -> Path:
    return project_root.resolve() / "promotion-policy.json"


def policy_calibration_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "policy-calibration.json"


def normalize_promotion_policy(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = deepcopy(DEFAULT_PROMOTION_POLICY)
    if payload:
        normalized.update({key: value for key, value in payload.items() if key != "thresholds"})
        normalized["thresholds"].update(payload.get("thresholds") or {})
    normalized.setdefault("version", DEFAULT_PROMOTION_POLICY["version"])
    normalized.setdefault("mode", DEFAULT_PROMOTION_POLICY["mode"])
    normalized.setdefault("thresholds", deepcopy(DEFAULT_PROMOTION_POLICY["thresholds"]))
    for key, value in DEFAULT_PROMOTION_POLICY["thresholds"].items():
        normalized["thresholds"].setdefault(key, value)
    return normalized


def load_or_create_promotion_policy(project_root: Path) -> dict[str, Any]:
    path = promotion_policy_path(project_root)
    if not path.exists():
        write_json(path, normalize_promotion_policy(None))
    return normalize_promotion_policy(load_json(path, default=None))


def save_promotion_policy(project_root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_promotion_policy(policy)
    normalized["updated_at"] = now_iso()
    write_json(promotion_policy_path(project_root), normalized)
    return normalized


def policy_with_overrides(project_root: Path, threshold_overrides: dict[str, float] | None = None) -> dict[str, Any]:
    policy = load_or_create_promotion_policy(project_root)
    if threshold_overrides:
        policy = normalize_promotion_policy(policy)
        policy["thresholds"].update(threshold_overrides)
        policy["mode"] = "candidate-preview"
    return policy


def build_policy_calibration(
    project_root: Path,
    *,
    replay_payload: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    replay_summary = (replay_payload or {}).get("summary") or {}
    overall_state = ((replay_payload or {}).get("evaluation") or {}).get("overall_state")
    if overall_state == "pass":
        learning_state = "ready"
    elif overall_state == "warn":
        learning_state = "observe"
    else:
        learning_state = "blocked"
    payload = {
        "generated_at": now_iso(),
        "policy": normalize_promotion_policy(policy or load_or_create_promotion_policy(project_root)),
        "policy_learning": {
            "state": learning_state,
            "reason": overall_state or "unknown",
        },
        "summary": {
            "active_corpus_count": replay_summary.get("active_corpus_count", 0),
            "manual_pass_rate": replay_summary.get("manual_pass_rate"),
            "fail_corpus_count": replay_summary.get("fail_corpus_count", 0),
            "warn_corpus_count": replay_summary.get("warn_corpus_count", 0),
            "stale_corpus_count": replay_summary.get("stale_corpus_count", 0),
        },
    }
    write_json(policy_calibration_path(project_root), payload)
    return payload
