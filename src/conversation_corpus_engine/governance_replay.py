from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .answering import load_json, write_json, write_markdown
from .federation import list_registered_corpora, load_corpus_surface
from .governance_policy import build_policy_calibration, policy_with_overrides


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def report_date() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def policy_replay_history_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "policy-replay-history.json"


def policy_replay_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "policy-replay-latest.json"


def policy_replay_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "policy-replay-latest.md"


def policy_replay_report_path(project_root: Path, date_str: str | None = None) -> Path:
    return project_root.resolve() / "reports" / f"policy-replay-{date_str or report_date()}.md"


def append_policy_replay_history(project_root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    history = load_json(
        policy_replay_history_path(project_root),
        default={"generated_at": None, "count": 0, "items": []},
    ) or {"generated_at": None, "count": 0, "items": []}
    history.setdefault("items", []).append(entry)
    history["generated_at"] = entry.get("generated_at")
    history["count"] = len(history["items"])
    history["latest"] = history["items"][-1] if history["items"] else None
    write_json(policy_replay_history_path(project_root), history)
    return history


def compare_threshold(metric: float | None, threshold: float, *, direction: str) -> str:
    if metric is None:
        return "skip"
    if direction == "max":
        return "pass" if metric <= threshold else "fail"
    return "pass" if metric >= threshold else "fail"


def build_policy_replay_payload(
    project_root: Path,
    *,
    threshold_overrides: dict[str, float] | None = None,
) -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    policy = policy_with_overrides(resolved_project_root, threshold_overrides=threshold_overrides)
    corpora = list_registered_corpora(resolved_project_root, active_only=True)
    surfaces = [load_corpus_surface(entry) for entry in corpora]
    cases: list[dict[str, Any]] = []
    fail_corpus_count = 0
    warn_corpus_count = 0
    stale_corpus_count = 0
    missing_contract_corpus_count = 0
    manual_pass_count = 0

    for surface in surfaces:
        summary = surface["summary"]
        evaluation_state = summary.get("evaluation_overall_state")
        freshness_state = summary.get("source_freshness_state")
        valid_contract = bool(summary.get("valid_contract"))
        gate_fail = evaluation_state == "fail"
        gate_warn = evaluation_state == "warn"
        stale = freshness_state not in {"fresh", "not_applicable"}
        manual_pass = evaluation_state == "pass"

        if gate_fail:
            fail_corpus_count += 1
        if gate_warn:
            warn_corpus_count += 1
        if stale:
            stale_corpus_count += 1
        if not valid_contract:
            missing_contract_corpus_count += 1
        if manual_pass:
            manual_pass_count += 1

        case = {
            "corpus_id": summary["corpus_id"],
            "name": summary["name"],
            "root": summary["root"],
            "evaluation_overall_state": evaluation_state,
            "source_reliability_state": summary.get("source_reliability_state"),
            "source_freshness_state": freshness_state,
            "source_freshness_note": summary.get("source_freshness_note"),
            "source_needs_refresh": bool(summary.get("source_needs_refresh")),
            "valid_contract": valid_contract,
            "missing_files": summary.get("missing_files") or [],
            "review_required": gate_fail or gate_warn or stale or not valid_contract,
            "comparison": {
                "gate_fail": gate_fail,
                "gate_warn": gate_warn,
                "stale_source": stale,
                "missing_contract": not valid_contract,
                "manual_pass": manual_pass,
            },
        }
        cases.append(case)

    active_corpus_count = len(cases)
    manual_pass_rate = (
        round(manual_pass_count / active_corpus_count, 4) if active_corpus_count else None
    )
    thresholds = dict(policy.get("thresholds") or {})
    metrics = {
        "fail_corpus_count": float(fail_corpus_count),
        "warn_corpus_count": float(warn_corpus_count),
        "stale_corpus_count": float(stale_corpus_count),
        "missing_contract_corpus_count": float(missing_contract_corpus_count),
        "manual_pass_rate": manual_pass_rate,
        "active_corpus_count": float(active_corpus_count),
    }
    threshold_rules = [
        ("max_fail_corpora", "fail_corpus_count", "max"),
        ("max_warn_corpora", "warn_corpus_count", "max"),
        ("max_stale_corpora", "stale_corpus_count", "max"),
        ("max_missing_contract_corpora", "missing_contract_corpus_count", "max"),
        ("min_manual_pass_rate", "manual_pass_rate", "min"),
        ("min_registered_active_corpora", "active_corpus_count", "min"),
    ]
    gates: list[dict[str, Any]] = []
    overall_state = "pass"
    for threshold_key, metric_key, direction in threshold_rules:
        threshold_value = float(thresholds[threshold_key])
        metric_value = metrics.get(metric_key)
        state = compare_threshold(metric_value, threshold_value, direction=direction)
        if state == "fail":
            overall_state = "fail"
        gates.append(
            {
                "threshold": threshold_key,
                "metric": metric_key,
                "direction": direction,
                "threshold_value": threshold_value,
                "metric_value": metric_value,
                "state": state,
            },
        )

    summary = {
        "candidate_count": active_corpus_count,
        "active_corpus_count": active_corpus_count,
        "fail_corpus_count": fail_corpus_count,
        "warn_corpus_count": warn_corpus_count,
        "stale_corpus_count": stale_corpus_count,
        "missing_contract_corpus_count": missing_contract_corpus_count,
        "manual_pass_count": manual_pass_count,
        "manual_pass_rate": manual_pass_rate,
        "review_required_count": sum(1 for item in cases if item["review_required"]),
    }
    evaluation = {
        "generated_at": now_iso(),
        "overall_state": overall_state,
        "gates": gates,
    }
    return {
        "generated_at": now_iso(),
        "project_root": str(resolved_project_root),
        "policy": policy,
        "summary": summary,
        "evaluation": evaluation,
        "cases": cases,
    }


def render_policy_replay(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    evaluation = payload.get("evaluation") or {}
    lines = [
        "# Policy Replay",
        "",
        f"- Generated: {payload.get('generated_at') or 'n/a'}",
        f"- Active corpora: {summary.get('active_corpus_count', 0)}",
        f"- Fail corpora: {summary.get('fail_corpus_count', 0)}",
        f"- Warn corpora: {summary.get('warn_corpus_count', 0)}",
        f"- Stale corpora: {summary.get('stale_corpus_count', 0)}",
        f"- Missing contract corpora: {summary.get('missing_contract_corpus_count', 0)}",
        f"- Manual pass rate: {summary.get('manual_pass_rate', 'n/a')}",
        f"- Overall state: {evaluation.get('overall_state') or 'n/a'}",
        "",
        "## Gates",
        "",
    ]
    for item in evaluation.get("gates", []):
        lines.append(
            f"- {item['threshold']}: {item['state']} metric={item['metric_value']} threshold={item['threshold_value']}",
        )
    lines.extend(["", "## Corpora", ""])
    for item in payload.get("cases", []):
        lines.append(
            f"- {item['corpus_id']}: gate={item.get('evaluation_overall_state') or 'n/a'} "
            f"freshness={item.get('source_freshness_state') or 'n/a'} "
            f"review_required={'yes' if item.get('review_required') else 'no'}",
        )
    return "\n".join(lines)


def write_policy_replay_artifacts(project_root: Path, payload: dict[str, Any]) -> dict[str, str]:
    latest_json = policy_replay_latest_json_path(project_root)
    latest_md = policy_replay_latest_markdown_path(project_root)
    dated_md = policy_replay_report_path(project_root)
    write_json(latest_json, payload)
    render = render_policy_replay(payload)
    write_markdown(latest_md, render)
    write_markdown(dated_md, render)
    append_policy_replay_history(
        project_root,
        {
            "generated_at": payload.get("generated_at"),
            "summary": payload.get("summary") or {},
            "evaluation": payload.get("evaluation") or {},
            "thresholds": (payload.get("policy") or {}).get("thresholds") or {},
        },
    )
    build_policy_calibration(
        project_root,
        replay_payload=payload,
        policy=payload.get("policy") or {},
    )
    return {
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "report_path": str(dated_md),
    }
