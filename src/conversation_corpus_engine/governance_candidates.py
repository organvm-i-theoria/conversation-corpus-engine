from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .answering import load_json, write_json, write_markdown
from .governance_policy import (
    build_policy_calibration,
    load_or_create_promotion_policy,
    policy_calibration_path,
    promotion_policy_path,
    save_promotion_policy,
)
from .governance_replay import build_policy_replay_payload


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def policy_candidates_dir(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "policy-candidates"


def policy_candidate_history_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "policy-candidate-history.json"


def policy_candidate_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "policy-candidate-latest.json"


def policy_candidate_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "policy-candidate-latest.md"


def policy_review_history_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "policy-review-history.json"


def policy_application_history_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "policy-application-history.json"


def policy_live_pointer_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "policy-live-pointer.json"


def policy_rollback_history_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "policy-rollback-history.json"


def policy_diff_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "policy-diff-latest.json"


def policy_diff_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "policy-diff-latest.md"


def policy_application_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "policy-application-latest.json"


def policy_application_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "policy-application-latest.md"


def append_history(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    payload = load_json(path, default={"generated_at": None, "count": 0, "items": []}) or {
        "generated_at": None,
        "count": 0,
        "items": [],
    }
    payload.setdefault("items", []).append(entry)
    payload["generated_at"] = entry.get("recorded_at") or entry.get("generated_at")
    payload["count"] = len(payload["items"])
    payload["latest"] = payload["items"][-1] if payload["items"] else None
    write_json(path, payload)
    return payload


def build_policy_candidate_diff(live_policy: dict[str, Any], threshold_overrides: dict[str, float]) -> dict[str, Any]:
    current_thresholds = dict((live_policy.get("thresholds") or {}))
    proposed_thresholds = dict(current_thresholds)
    changed_thresholds: list[dict[str, Any]] = []
    for key, value in threshold_overrides.items():
        previous = current_thresholds.get(key)
        proposed_thresholds[key] = value
        delta = None
        if isinstance(previous, (int, float)):
            delta = round(float(value) - float(previous), 4)
        changed_thresholds.append(
            {
                "key": key,
                "from": previous,
                "to": value,
                "delta": delta,
            },
        )
    return {
        "live_policy_version": live_policy.get("version"),
        "live_mode": live_policy.get("mode"),
        "changed_threshold_count": len(changed_thresholds),
        "changed_thresholds": changed_thresholds,
        "proposed_thresholds": proposed_thresholds,
    }


def render_policy_candidate(manifest: dict[str, Any]) -> str:
    replay = manifest.get("replay_summary") or {}
    lines = [
        "# Policy Candidate",
        "",
        f"- Candidate id: `{manifest.get('candidate_id') or 'n/a'}`",
        f"- Generated: {manifest.get('generated_at') or 'n/a'}",
        f"- Status: {manifest.get('status') or 'n/a'}",
        f"- Threshold overrides: `{manifest.get('threshold_overrides') or {}}`",
        f"- Replay candidate count: {replay.get('candidate_count', 0)}",
        f"- Replay fail corpora: {replay.get('fail_corpus_count', 0)}",
        f"- Replay warn corpora: {replay.get('warn_corpus_count', 0)}",
        f"- Replay stale corpora: {replay.get('stale_corpus_count', 0)}",
        f"- Replay manual pass rate: {replay.get('manual_pass_rate', 'n/a')}",
        f"- Policy overall state: {manifest.get('policy_overall_state') or 'n/a'}",
    ]
    if manifest.get("note"):
        lines.extend(["", "## Note", "", manifest["note"]])
    return "\n".join(lines)


def render_policy_diff(payload: dict[str, Any]) -> str:
    lines = [
        "# Policy Diff",
        "",
        f"- Candidate id: `{payload.get('candidate_id') or 'n/a'}`",
        f"- Generated: {payload.get('generated_at') or 'n/a'}",
        f"- Changed threshold count: {payload.get('changed_threshold_count', 0)}",
        "",
        "## Threshold Changes",
        "",
    ]
    for item in payload.get("changed_thresholds") or []:
        lines.append(
            f"- `{item['key']}`: {item.get('from')} -> {item.get('to')} (delta={item.get('delta')})",
        )
    if not payload.get("changed_thresholds"):
        lines.append("No threshold changes.")
    return "\n".join(lines)


def render_policy_application(payload: dict[str, Any]) -> str:
    replay = payload.get("post_apply_replay") or {}
    replay_summary = replay.get("summary") or {}
    lines = [
        "# Policy Application",
        "",
        f"- Candidate id: `{payload.get('candidate_id') or 'n/a'}`",
        f"- Applied at: {payload.get('applied_at') or 'n/a'}",
        f"- Threshold overrides: `{payload.get('threshold_overrides') or {}}`",
        f"- Replay fail corpora: {replay_summary.get('fail_corpus_count', 0)}",
        f"- Replay warn corpora: {replay_summary.get('warn_corpus_count', 0)}",
        f"- Replay stale corpora: {replay_summary.get('stale_corpus_count', 0)}",
        f"- Replay manual pass rate: {replay_summary.get('manual_pass_rate', 'n/a')}",
        f"- Replay overall state: {(replay.get('evaluation') or {}).get('overall_state') or 'n/a'}",
    ]
    return "\n".join(lines)


def stage_policy_candidate(
    project_root: Path,
    *,
    threshold_overrides: dict[str, float],
    note: str = "",
) -> dict[str, Any]:
    if not threshold_overrides:
        raise ValueError("Policy candidate staging requires at least one threshold override.")
    resolved_project_root = project_root.resolve()
    candidate_id = f"policy-{timestamp_slug()}"
    candidate_dir = policy_candidates_dir(resolved_project_root) / candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    replay_payload = build_policy_replay_payload(
        resolved_project_root,
        threshold_overrides=threshold_overrides,
    )
    live_policy = load_or_create_promotion_policy(resolved_project_root)
    diff = build_policy_candidate_diff(live_policy, threshold_overrides)
    manifest = {
        "candidate_id": candidate_id,
        "generated_at": now_iso(),
        "status": "staged",
        "project_root": str(resolved_project_root),
        "candidate_root": str(candidate_dir),
        "threshold_overrides": dict(threshold_overrides),
        "note": note,
        "base_policy": {
            "version": live_policy.get("version"),
            "mode": live_policy.get("mode"),
            "thresholds": dict(live_policy.get("thresholds") or {}),
        },
        "diff": diff,
        "replay_summary": replay_payload.get("summary") or {},
        "policy_overall_state": (replay_payload.get("evaluation") or {}).get("overall_state"),
    }
    write_json(candidate_dir / "manifest.json", manifest)
    write_json(candidate_dir / "replay.json", replay_payload)
    write_markdown(candidate_dir / "memo.md", render_policy_candidate(manifest))
    write_json(policy_candidate_latest_json_path(resolved_project_root), manifest)
    write_markdown(policy_candidate_latest_markdown_path(resolved_project_root), render_policy_candidate(manifest))
    append_history(
        policy_candidate_history_path(resolved_project_root),
        {
            "generated_at": manifest["generated_at"],
            "candidate_id": candidate_id,
            "threshold_overrides": dict(threshold_overrides),
            "status": manifest["status"],
            "policy_overall_state": manifest["policy_overall_state"],
        },
    )
    manifest["replay_path"] = str(candidate_dir / "replay.json")
    manifest["memo_path"] = str(candidate_dir / "memo.md")
    return manifest


def load_policy_candidate_manifest(project_root: Path, candidate_id: str = "latest") -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    if candidate_id == "latest":
        payload = load_json(policy_candidate_latest_json_path(resolved_project_root), default={}) or {}
        if payload:
            return payload
        raise ValueError("No staged policy candidate is available.")
    payload = load_json(
        policy_candidates_dir(resolved_project_root) / candidate_id / "manifest.json",
        default={},
    ) or {}
    if not payload:
        raise ValueError(f"No staged policy candidate exists for id: {candidate_id}")
    return payload


def review_policy_candidate(
    project_root: Path,
    candidate_id: str,
    *,
    decision: str,
    note: str = "",
) -> dict[str, Any]:
    if decision not in {"approve", "reject"}:
        raise ValueError(f"Unsupported policy candidate decision: {decision}")
    resolved_project_root = project_root.resolve()
    manifest = load_policy_candidate_manifest(resolved_project_root, candidate_id=candidate_id)
    manifest["status"] = "approved" if decision == "approve" else "rejected"
    manifest["review"] = {
        "recorded_at": now_iso(),
        "decision": decision,
        "note": note,
    }
    write_json(
        policy_candidates_dir(resolved_project_root) / manifest["candidate_id"] / "manifest.json",
        manifest,
    )
    write_json(policy_candidate_latest_json_path(resolved_project_root), manifest)
    write_markdown(policy_candidate_latest_markdown_path(resolved_project_root), render_policy_candidate(manifest))
    append_history(
        policy_review_history_path(resolved_project_root),
        {
            "recorded_at": manifest["review"]["recorded_at"],
            "candidate_id": manifest["candidate_id"],
            "decision": decision,
            "note": note,
            "threshold_overrides": manifest.get("threshold_overrides") or {},
        },
    )
    return manifest


def apply_policy_candidate(project_root: Path, candidate_id: str, *, note: str = "") -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    manifest = load_policy_candidate_manifest(resolved_project_root, candidate_id=candidate_id)
    if manifest.get("status") != "approved":
        raise ValueError(f"Policy candidate {candidate_id} must be approved before it can be applied.")

    live_policy = load_or_create_promotion_policy(resolved_project_root)
    threshold_overrides = dict(manifest.get("threshold_overrides") or {})
    diff = build_policy_candidate_diff(live_policy, threshold_overrides)
    proposed_policy = deepcopy(live_policy)
    proposed_policy["thresholds"].update(threshold_overrides)
    proposed_policy["version"] = int(proposed_policy.get("version", 1)) + 1
    save_promotion_policy(resolved_project_root, proposed_policy)

    replay_payload = build_policy_replay_payload(resolved_project_root)
    build_policy_calibration(
        resolved_project_root,
        replay_payload=replay_payload,
        policy=proposed_policy,
    )
    applied_at = now_iso()
    write_json(
        policy_live_pointer_path(resolved_project_root),
        {
            "event": "apply",
            "candidate_id": manifest["candidate_id"],
            "applied_at": applied_at,
            "policy_path": str(promotion_policy_path(resolved_project_root)),
            "threshold_overrides": threshold_overrides,
        },
    )
    manifest["status"] = "applied"
    manifest["application"] = {
        "applied_at": applied_at,
        "note": note,
        "threshold_overrides": threshold_overrides,
    }
    write_json(
        policy_candidates_dir(resolved_project_root) / manifest["candidate_id"] / "manifest.json",
        manifest,
    )
    write_json(policy_candidate_latest_json_path(resolved_project_root), manifest)
    write_markdown(policy_candidate_latest_markdown_path(resolved_project_root), render_policy_candidate(manifest))

    diff_payload = {
        "candidate_id": manifest["candidate_id"],
        "generated_at": applied_at,
        **diff,
    }
    write_json(policy_diff_latest_json_path(resolved_project_root), diff_payload)
    write_markdown(policy_diff_latest_markdown_path(resolved_project_root), render_policy_diff(diff_payload))

    payload = {
        "candidate_id": manifest["candidate_id"],
        "applied_at": applied_at,
        "note": note,
        "threshold_overrides": threshold_overrides,
        "diff": diff,
        "post_apply_replay": replay_payload,
        "policy_calibration_path": str(policy_calibration_path(resolved_project_root)),
    }
    write_json(policy_application_latest_json_path(resolved_project_root), payload)
    write_markdown(policy_application_latest_markdown_path(resolved_project_root), render_policy_application(payload))
    append_history(
        policy_application_history_path(resolved_project_root),
        {
            "recorded_at": applied_at,
            "candidate_id": manifest["candidate_id"],
            "note": note,
            "threshold_overrides": threshold_overrides,
            "previous_policy": live_policy,
            "applied_policy": proposed_policy,
            "diff": diff,
        },
    )
    return payload


def rollback_policy_application(project_root: Path, *, target: str = "previous", note: str = "") -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    history = load_json(
        policy_application_history_path(resolved_project_root),
        default={"items": []},
    ) or {"items": []}
    items = history.get("items") or []
    if not items:
        raise ValueError("No applied policy history is available for rollback.")
    if target == "previous":
        entry = items[-1]
    else:
        entry = next((item for item in reversed(items) if item.get("candidate_id") == target), None)
        if entry is None:
            raise ValueError(f"No applied policy history exists for target: {target}")

    restored_policy = deepcopy(entry.get("previous_policy") or {})
    save_promotion_policy(resolved_project_root, restored_policy)
    replay_payload = build_policy_replay_payload(resolved_project_root)
    build_policy_calibration(
        resolved_project_root,
        replay_payload=replay_payload,
        policy=restored_policy,
    )
    recorded_at = now_iso()
    payload = {
        "recorded_at": recorded_at,
        "target": target,
        "source_candidate_id": entry.get("candidate_id"),
        "note": note,
        "restored_policy": restored_policy,
    }
    write_json(
        policy_live_pointer_path(resolved_project_root),
        {
            "event": "rollback",
            "recorded_at": recorded_at,
            "source_candidate_id": entry.get("candidate_id"),
            "target": target,
            "policy_path": str(promotion_policy_path(resolved_project_root)),
        },
    )
    append_history(policy_rollback_history_path(resolved_project_root), payload)
    return payload
