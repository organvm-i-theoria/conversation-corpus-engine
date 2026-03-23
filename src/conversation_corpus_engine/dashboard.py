from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .answering import load_json
from .federation import list_registered_corpora
from .provider_catalog import PROVIDER_CONFIG, default_source_drop_root
from .provider_readiness import build_provider_readiness


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def corpus_gate_summary(project_root: Path) -> list[dict[str, Any]]:
    """Summarize evaluation gate state for each registered corpus."""
    entries = list_registered_corpora(project_root)
    results: list[dict[str, Any]] = []
    for entry in entries:
        root = Path(entry.get("root", ""))
        gates_path = root / "corpus" / "regression-gates.json"
        gates = load_json(gates_path, default=None)
        results.append(
            {
                "corpus_id": entry.get("corpus_id", "?"),
                "name": entry.get("name", "?"),
                "default": entry.get("default", False),
                "root": str(root),
                "overall_state": (gates or {}).get("overall_state", "unknown"),
                "source_reliability": (gates or {}).get("source_reliability_state", "unknown"),
                "gate_count": len((gates or {}).get("gates", [])),
                "pass_count": sum(
                    1 for g in (gates or {}).get("gates", []) if g.get("state") == "pass"
                ),
                "fail_count": sum(
                    1 for g in (gates or {}).get("gates", []) if g.get("state") == "fail"
                ),
                "warn_count": sum(
                    1 for g in (gates or {}).get("gates", []) if g.get("state") == "warn"
                ),
            }
        )
    return results


def federation_summary(project_root: Path) -> dict[str, Any]:
    """Summarize federation state."""
    fed_dir = project_root / "federation"
    registry = load_json(fed_dir / "registry.json", default={"corpora": []})
    corpora_summary = load_json(fed_dir / "corpora-summary.json", default=[])
    if isinstance(corpora_summary, list):
        family_count = sum(c.get("family_count", 0) for c in corpora_summary)
        entity_count = sum(c.get("entity_count", 0) for c in corpora_summary)
        action_count = sum(c.get("action_count", 0) for c in corpora_summary)
    else:
        family_count = corpora_summary.get("total_families", 0)
        entity_count = corpora_summary.get("total_entities", 0)
        action_count = corpora_summary.get("total_actions", 0)
    conflict = load_json(fed_dir / "conflict-report.json", default={})
    return {
        "corpus_count": len(registry.get("corpora", [])),
        "family_count": family_count,
        "entity_count": entity_count,
        "action_count": action_count,
        "conflict_count": len(conflict.get("conflicts", [])),
    }


def review_queue_summary(project_root: Path) -> dict[str, Any]:
    """Summarize federated review queue state."""
    queue = load_json(
        project_root / "state" / "federated-review-queue.json",
        default={"items": []},
    )
    items = queue.get("items", [])
    open_items = [i for i in items if i.get("status") == "open"]
    return {
        "total": len(items),
        "open": len(open_items),
        "resolved": len(items) - len(open_items),
    }


def build_dashboard(
    project_root: Path,
    source_drop_root: Path | None = None,
) -> dict[str, Any]:
    """Build the full dashboard payload."""
    sdr = source_drop_root or default_source_drop_root(project_root)
    return {
        "generated_at": now_iso(),
        "provider_count": len(PROVIDER_CONFIG),
        "corpora": corpus_gate_summary(project_root),
        "federation": federation_summary(project_root),
        "review_queue": review_queue_summary(project_root),
        "readiness": build_provider_readiness(project_root, sdr),
    }


STATE_SYMBOLS = {"pass": "+", "warn": "~", "fail": "!", "unknown": "?"}


def render_dashboard_text(payload: dict[str, Any]) -> str:
    """Render the dashboard as formatted text."""
    lines: list[str] = []
    lines.append("=== CCE Dashboard ===")
    lines.append(f"Generated: {payload['generated_at']}")
    lines.append(f"Providers: {payload['provider_count']}")
    lines.append("")

    lines.append("--- Corpora ---")
    corpora = payload.get("corpora", [])
    if not corpora:
        lines.append("  (none registered)")
    for c in corpora:
        marker = "*" if c.get("default") else " "
        sym = STATE_SYMBOLS.get(c.get("overall_state", "?"), "?")
        gates = (
            f"{c['pass_count']}P/{c['warn_count']}W/{c['fail_count']}F"
            if c["gate_count"]
            else "no gates"
        )
        lines.append(f" {marker}[{sym}] {c['corpus_id']} ({gates}) src={c['source_reliability']}")
    lines.append("")

    fed = payload.get("federation", {})
    lines.append("--- Federation ---")
    lines.append(
        f"  Corpora: {fed.get('corpus_count', 0)} | "
        f"Families: {fed.get('family_count', 0)} | "
        f"Entities: {fed.get('entity_count', 0)} | "
        f"Actions: {fed.get('action_count', 0)}"
    )
    conflicts = fed.get("conflict_count", 0)
    if conflicts:
        lines.append(f"  Conflicts: {conflicts}")
    lines.append("")

    rq = payload.get("review_queue", {})
    lines.append("--- Review Queue ---")
    lines.append(f"  Open: {rq.get('open', 0)} | Resolved: {rq.get('resolved', 0)}")
    lines.append("")

    readiness = payload.get("readiness", {})
    providers = readiness.get("providers", [])
    if providers:
        lines.append("--- Provider Readiness ---")
        items = (
            providers.items()
            if isinstance(providers, dict)
            else ((p.get("provider", "?"), p) for p in providers)
        )
        for name, info in sorted(items, key=lambda x: x[0]):
            state = info.get("readiness_state", "unknown")
            sym = STATE_SYMBOLS.get(state, "?")
            corpus_id = info.get("target_corpus_id") or info.get("corpus_id") or "-"
            lines.append(f"  [{sym}] {name:12s} {state:20s} corpus={corpus_id}")

    return "\n".join(lines)
