from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .answering import load_json, write_json, write_markdown
from .paths import resolve_workspace_path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_policy_dir(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "source-policies"


def source_policy_path(project_root: Path, provider: str) -> Path:
    return source_policy_dir(project_root) / f"{provider}.json"


def source_policy_history_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "source-policy-history.json"


def source_policy_report_path(project_root: Path, provider: str) -> Path:
    return project_root.resolve() / "reports" / f"{provider}-source-policy-latest.md"


def normalize_source_policy(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(payload or {})
    for field in ("primary_root", "fallback_root"):
        value = normalized.get(field)
        if value:
            normalized[field] = str(resolve_workspace_path(value))
    return normalized


def load_source_policy(project_root: Path, provider: str) -> dict[str, Any]:
    return normalize_source_policy(load_json(source_policy_path(project_root, provider), default={}))


def append_source_policy_history(project_root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    history = load_json(
        source_policy_history_path(project_root),
        default={"generated_at": None, "count": 0, "items": []},
    ) or {"generated_at": None, "count": 0, "items": []}
    history.setdefault("items", []).append(entry)
    history["generated_at"] = entry.get("generated_at")
    history["count"] = len(history["items"])
    history["latest"] = history["items"][-1] if history["items"] else None
    write_json(source_policy_history_path(project_root), history)
    return history


def render_source_policy_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload.get('provider', 'unknown').title()} Source Policy",
        "",
        f"- Generated: {payload.get('generated_at') or 'n/a'}",
        f"- Decision: {payload.get('decision') or 'manual'}",
        f"- Primary corpus id: {payload.get('primary_corpus_id') or 'n/a'}",
        f"- Primary root: {payload.get('primary_root') or 'n/a'}",
        f"- Fallback corpus id: {payload.get('fallback_corpus_id') or 'n/a'}",
        f"- Fallback root: {payload.get('fallback_root') or 'n/a'}",
    ]
    if payload.get("note"):
        lines.extend(["", "## Note", "", payload["note"]])
    return "\n".join(lines)


def write_source_policy_payload(
    project_root: Path,
    provider: str,
    payload: dict[str, Any],
    *,
    append_history: bool = False,
) -> dict[str, Any]:
    normalized = normalize_source_policy(payload)
    normalized["provider"] = provider
    write_json(source_policy_path(project_root, provider), normalized)
    write_markdown(
        source_policy_report_path(project_root, provider), render_source_policy_markdown(normalized)
    )
    if append_history:
        append_source_policy_history(
            project_root,
            {
                "generated_at": normalized.get("generated_at"),
                "provider": provider,
                "decision": normalized.get("decision"),
                "primary_corpus_id": normalized.get("primary_corpus_id"),
                "primary_root": normalized.get("primary_root"),
                "fallback_corpus_id": normalized.get("fallback_corpus_id"),
                "fallback_root": normalized.get("fallback_root"),
                "note": normalized.get("note", ""),
            },
        )
    return normalized


def set_source_policy(
    project_root: Path,
    provider: str,
    *,
    primary_root: Path,
    primary_corpus_id: str,
    fallback_root: Path | None = None,
    fallback_corpus_id: str | None = None,
    decision: str = "manual",
    note: str = "",
) -> dict[str, Any]:
    primary_root = resolve_workspace_path(primary_root)
    fallback_root = resolve_workspace_path(fallback_root) if fallback_root is not None else None
    payload = {
        "provider": provider,
        "generated_at": now_iso(),
        "decision": decision,
        "primary_root": str(primary_root),
        "primary_corpus_id": primary_corpus_id,
        "fallback_root": str(fallback_root) if fallback_root is not None else None,
        "fallback_corpus_id": fallback_corpus_id,
        "note": note,
    }
    return write_source_policy_payload(project_root, provider, payload, append_history=True)
