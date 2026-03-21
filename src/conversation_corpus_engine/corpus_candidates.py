from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .answering import load_json, write_json, write_markdown
from .corpus_diff import build_corpus_diff_payload, render_corpus_diff
from .federation import (
    FEDERATION_CONTRACT,
    build_federation,
    list_registered_corpora,
    upsert_corpus,
)
from .provider_catalog import get_provider_config
from .source_policy import load_source_policy, set_source_policy


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def corpus_candidates_dir(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "corpus-candidates"


def corpus_candidate_history_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "corpus-candidate-history.json"


def corpus_candidate_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "corpus-candidate-latest.json"


def corpus_candidate_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "corpus-candidate-latest.md"


def corpus_candidate_review_history_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "corpus-candidate-review-history.json"


def corpus_promotion_history_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "corpus-promotion-history.json"


def corpus_promotion_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "corpus-promotion-latest.json"


def corpus_promotion_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "corpus-promotion-latest.md"


def corpus_rollback_history_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "corpus-rollback-history.json"


def corpus_live_pointer_path(project_root: Path) -> Path:
    return project_root.resolve() / "state" / "corpus-live-pointer.json"


def corpus_diff_latest_json_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "corpus-diff-latest.json"


def corpus_diff_latest_markdown_path(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "corpus-diff-latest.md"


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


def render_corpus_candidate(manifest: dict[str, Any]) -> str:
    diff_summary = manifest.get("diff_summary") or {}
    lines = [
        "# Corpus Candidate",
        "",
        f"- Candidate id: `{manifest.get('candidate_id') or 'n/a'}`",
        f"- Generated: {manifest.get('generated_at') or 'n/a'}",
        f"- Status: {manifest.get('status') or 'n/a'}",
        f"- Provider: {manifest.get('provider') or 'n/a'}",
        f"- Live corpus id: `{manifest.get('live_corpus_id') or 'n/a'}`",
        f"- Live root: {manifest.get('live_root') or 'n/a'}",
        f"- Candidate root: {manifest.get('candidate_root') or 'n/a'}",
        f"- Recommendation: {manifest.get('recommendation_state') or 'n/a'}",
        f"- Structural changes: {diff_summary.get('structural_change_count', 0)}",
        f"- Changed representative queries: {diff_summary.get('changed_query_count', 0)}",
    ]
    if manifest.get("note"):
        lines.extend(["", "## Note", "", manifest["note"]])
    return "\n".join(lines)


def render_corpus_promotion(payload: dict[str, Any]) -> str:
    lines = [
        "# Corpus Promotion",
        "",
        f"- Candidate id: `{payload.get('candidate_id') or 'n/a'}`",
        f"- Promoted at: {payload.get('promoted_at') or 'n/a'}",
        f"- Provider: {payload.get('provider') or 'n/a'}",
        f"- Live corpus id: `{payload.get('live_corpus_id') or 'n/a'}`",
        f"- Previous root: {payload.get('previous_root') or 'n/a'}",
        f"- Promoted root: {payload.get('promoted_root') or 'n/a'}",
        f"- Source policy synced: {'yes' if payload.get('source_policy_sync') else 'no'}",
    ]
    return "\n".join(lines)


def resolve_live_entry(
    project_root: Path,
    *,
    live_corpus_id: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    registry = list_registered_corpora(resolved_project_root, active_only=True)
    registry_by_id = {item["corpus_id"]: item for item in registry}

    if live_corpus_id:
        entry = registry_by_id.get(live_corpus_id)
        if entry:
            return entry
        raise ValueError(f"No active corpus is registered with id: {live_corpus_id}")

    if provider:
        policy = load_source_policy(resolved_project_root, provider)
        config = get_provider_config(provider)
        candidate_ids: list[str] = []
        for value in (
            policy.get("primary_corpus_id"),
            policy.get("fallback_corpus_id"),
            config.get("default_corpus_id"),
            config.get("fallback_corpus_id"),
        ):
            if value and value not in candidate_ids:
                candidate_ids.append(value)
        for corpus_id in candidate_ids:
            entry = registry_by_id.get(corpus_id)
            if entry:
                return entry
        raise ValueError(f"No active corpus is registered for provider: {provider}")

    defaults = [entry for entry in registry if entry.get("default")]
    if defaults:
        return defaults[0]
    if len(registry) == 1:
        return registry[0]
    raise ValueError(
        "A live corpus id or provider is required when multiple active corpora are registered."
    )


def write_candidate_artifacts(
    project_root: Path,
    candidate_id: str,
    manifest: dict[str, Any],
    diff_payload: dict[str, Any],
) -> dict[str, str]:
    candidate_dir = corpus_candidates_dir(project_root) / candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = candidate_dir / "manifest.json"
    diff_json_path = candidate_dir / "diff.json"
    diff_markdown_path = candidate_dir / "diff.md"
    memo_path = candidate_dir / "memo.md"
    write_json(manifest_path, manifest)
    write_json(diff_json_path, diff_payload)
    write_markdown(diff_markdown_path, render_corpus_diff(diff_payload))
    write_markdown(memo_path, render_corpus_candidate(manifest))
    write_json(corpus_candidate_latest_json_path(project_root), manifest)
    write_markdown(
        corpus_candidate_latest_markdown_path(project_root), render_corpus_candidate(manifest)
    )
    write_json(corpus_diff_latest_json_path(project_root), diff_payload)
    write_markdown(corpus_diff_latest_markdown_path(project_root), render_corpus_diff(diff_payload))
    return {
        "manifest_path": str(manifest_path),
        "diff_json_path": str(diff_json_path),
        "diff_markdown_path": str(diff_markdown_path),
        "memo_path": str(memo_path),
    }


def stage_corpus_candidate(
    project_root: Path,
    *,
    candidate_root: Path,
    live_corpus_id: str | None = None,
    provider: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    resolved_candidate_root = candidate_root.resolve()
    if not resolved_candidate_root.exists():
        raise FileNotFoundError(f"Candidate root does not exist: {resolved_candidate_root}")

    live_entry = resolve_live_entry(
        resolved_project_root,
        live_corpus_id=live_corpus_id,
        provider=provider,
    )
    if Path(live_entry["root"]).resolve() == resolved_candidate_root:
        raise ValueError(
            "Candidate root matches the current live root; stage a distinct corpus build."
        )

    candidate_id = f"corpus-{timestamp_slug()}"
    diff_payload = build_corpus_diff_payload(
        live_entry,
        resolved_candidate_root,
        provider=provider,
    )
    manifest = {
        "candidate_id": candidate_id,
        "generated_at": now_iso(),
        "status": "staged",
        "project_root": str(resolved_project_root),
        "provider": provider,
        "live_corpus_id": live_entry["corpus_id"],
        "live_name": live_entry["name"],
        "live_root": str(Path(live_entry["root"]).resolve()),
        "candidate_root": str(resolved_candidate_root),
        "note": note,
        "recommendation_state": (diff_payload.get("evaluation") or {}).get("overall_state"),
        "diff_summary": diff_payload.get("summary") or {},
        "diff_evaluation": diff_payload.get("evaluation") or {},
    }
    artifact_paths = write_candidate_artifacts(
        resolved_project_root, candidate_id, manifest, diff_payload
    )
    manifest.update(artifact_paths)
    write_json(Path(artifact_paths["manifest_path"]), manifest)
    write_json(corpus_candidate_latest_json_path(resolved_project_root), manifest)
    append_history(
        corpus_candidate_history_path(resolved_project_root),
        {
            "generated_at": manifest["generated_at"],
            "candidate_id": candidate_id,
            "provider": provider,
            "live_corpus_id": live_entry["corpus_id"],
            "candidate_root": str(resolved_candidate_root),
            "status": manifest["status"],
            "recommendation_state": manifest["recommendation_state"],
        },
    )
    return manifest


def load_corpus_candidate_manifest(
    project_root: Path, candidate_id: str = "latest"
) -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    if candidate_id == "latest":
        payload = (
            load_json(corpus_candidate_latest_json_path(resolved_project_root), default={}) or {}
        )
        if payload:
            return payload
        raise ValueError("No staged corpus candidate is available.")
    payload = (
        load_json(
            corpus_candidates_dir(resolved_project_root) / candidate_id / "manifest.json",
            default={},
        )
        or {}
    )
    if not payload:
        raise ValueError(f"No staged corpus candidate exists for id: {candidate_id}")
    return payload


def review_corpus_candidate(
    project_root: Path,
    candidate_id: str,
    *,
    decision: str,
    note: str = "",
) -> dict[str, Any]:
    if decision not in {"approve", "reject"}:
        raise ValueError(f"Unsupported corpus candidate decision: {decision}")
    resolved_project_root = project_root.resolve()
    manifest = load_corpus_candidate_manifest(resolved_project_root, candidate_id=candidate_id)
    manifest["status"] = "approved" if decision == "approve" else "rejected"
    manifest["review"] = {
        "recorded_at": now_iso(),
        "decision": decision,
        "note": note,
    }
    write_json(
        corpus_candidates_dir(resolved_project_root) / manifest["candidate_id"] / "manifest.json",
        manifest,
    )
    write_json(corpus_candidate_latest_json_path(resolved_project_root), manifest)
    write_markdown(
        corpus_candidate_latest_markdown_path(resolved_project_root),
        render_corpus_candidate(manifest),
    )
    append_history(
        corpus_candidate_review_history_path(resolved_project_root),
        {
            "recorded_at": manifest["review"]["recorded_at"],
            "candidate_id": manifest["candidate_id"],
            "provider": manifest.get("provider"),
            "live_corpus_id": manifest.get("live_corpus_id"),
            "decision": decision,
            "note": note,
        },
    )
    return manifest


def sync_provider_source_policy(
    project_root: Path,
    *,
    provider: str | None,
    live_corpus_id: str,
    promoted_root: Path,
    note: str = "",
) -> dict[str, Any] | None:
    if not provider:
        return None
    current_policy = load_source_policy(project_root, provider)
    if not current_policy:
        return None

    primary_corpus_id = current_policy.get("primary_corpus_id")
    fallback_corpus_id = current_policy.get("fallback_corpus_id")
    changed = live_corpus_id in {primary_corpus_id, fallback_corpus_id}
    if not changed:
        return None

    primary_root = (
        promoted_root
        if primary_corpus_id == live_corpus_id
        else Path(current_policy["primary_root"])
    )
    fallback_root_value = current_policy.get("fallback_root")
    fallback_root = None
    if fallback_corpus_id:
        if fallback_corpus_id == live_corpus_id:
            fallback_root = promoted_root
        elif fallback_root_value:
            fallback_root = Path(fallback_root_value)
    updated_policy = set_source_policy(
        project_root,
        provider,
        primary_root=primary_root,
        primary_corpus_id=primary_corpus_id,
        fallback_root=fallback_root,
        fallback_corpus_id=fallback_corpus_id,
        decision="promotion-sync",
        note=note or "Synced provider authority after corpus promotion.",
    )
    return {
        "previous": current_policy,
        "current": updated_policy,
    }


def restore_provider_source_policy(
    project_root: Path,
    *,
    provider: str | None,
    policy_payload: dict[str, Any] | None,
    note: str = "",
) -> dict[str, Any] | None:
    if not provider or not policy_payload:
        return None
    primary_root = policy_payload.get("primary_root")
    primary_corpus_id = policy_payload.get("primary_corpus_id")
    if not primary_root or not primary_corpus_id:
        return None
    fallback_root_value = policy_payload.get("fallback_root")
    return set_source_policy(
        project_root,
        provider,
        primary_root=Path(primary_root),
        primary_corpus_id=primary_corpus_id,
        fallback_root=Path(fallback_root_value) if fallback_root_value else None,
        fallback_corpus_id=policy_payload.get("fallback_corpus_id"),
        decision=policy_payload.get("decision") or "rollback-sync",
        note=note or policy_payload.get("note", ""),
    )


def promote_corpus_candidate(
    project_root: Path, candidate_id: str, *, note: str = ""
) -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    manifest = load_corpus_candidate_manifest(resolved_project_root, candidate_id=candidate_id)
    if manifest.get("status") != "approved":
        raise ValueError(
            f"Corpus candidate {candidate_id} must be approved before it can be promoted."
        )

    live_entry = resolve_live_entry(
        resolved_project_root,
        live_corpus_id=manifest["live_corpus_id"],
    )
    previous_live_entry = deepcopy(live_entry)
    promoted_root = Path(manifest["candidate_root"]).resolve()
    promoted_entry = upsert_corpus(
        resolved_project_root,
        promoted_root,
        corpus_id=live_entry["corpus_id"],
        name=live_entry["name"],
        contract=live_entry.get("contract", FEDERATION_CONTRACT),
        status=live_entry.get("status", "active"),
        make_default=bool(live_entry.get("default")),
    )
    policy_sync = sync_provider_source_policy(
        resolved_project_root,
        provider=manifest.get("provider"),
        live_corpus_id=live_entry["corpus_id"],
        promoted_root=promoted_root,
        note=note,
    )
    federation_result = build_federation(resolved_project_root)
    promoted_at = now_iso()
    write_json(
        corpus_live_pointer_path(resolved_project_root),
        {
            "event": "promote",
            "candidate_id": manifest["candidate_id"],
            "promoted_at": promoted_at,
            "live_corpus_id": live_entry["corpus_id"],
            "promoted_root": str(promoted_root),
        },
    )
    manifest["status"] = "promoted"
    manifest["promotion"] = {
        "promoted_at": promoted_at,
        "note": note,
        "promoted_root": str(promoted_root),
    }
    write_json(
        corpus_candidates_dir(resolved_project_root) / manifest["candidate_id"] / "manifest.json",
        manifest,
    )
    write_json(corpus_candidate_latest_json_path(resolved_project_root), manifest)
    write_markdown(
        corpus_candidate_latest_markdown_path(resolved_project_root),
        render_corpus_candidate(manifest),
    )

    payload = {
        "candidate_id": manifest["candidate_id"],
        "promoted_at": promoted_at,
        "provider": manifest.get("provider"),
        "live_corpus_id": live_entry["corpus_id"],
        "previous_root": previous_live_entry["root"],
        "promoted_root": str(promoted_root),
        "note": note,
        "source_policy_sync": bool(policy_sync),
        "federation_summary_path": federation_result.get("summary_markdown_path"),
    }
    write_json(corpus_promotion_latest_json_path(resolved_project_root), payload)
    write_markdown(
        corpus_promotion_latest_markdown_path(resolved_project_root),
        render_corpus_promotion(payload),
    )
    append_history(
        corpus_promotion_history_path(resolved_project_root),
        {
            "recorded_at": promoted_at,
            "candidate_id": manifest["candidate_id"],
            "provider": manifest.get("provider"),
            "note": note,
            "previous_live_entry": previous_live_entry,
            "promoted_entry": promoted_entry,
            "previous_source_policy": (policy_sync or {}).get("previous"),
            "current_source_policy": (policy_sync or {}).get("current"),
        },
    )
    return payload


def rollback_corpus_promotion(
    project_root: Path, *, target: str = "previous", note: str = ""
) -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    history = load_json(
        corpus_promotion_history_path(resolved_project_root),
        default={"items": []},
    ) or {"items": []}
    items = history.get("items") or []
    if not items:
        raise ValueError("No promoted corpus history is available for rollback.")
    if target == "previous":
        entry = items[-1]
    else:
        entry = next((item for item in reversed(items) if item.get("candidate_id") == target), None)
        if entry is None:
            raise ValueError(f"No promoted corpus history exists for target: {target}")

    previous_live_entry = deepcopy(entry.get("previous_live_entry") or {})
    if not previous_live_entry:
        raise ValueError("Rollback history is missing the previous live entry payload.")

    restored_entry = upsert_corpus(
        resolved_project_root,
        Path(previous_live_entry["root"]).resolve(),
        corpus_id=previous_live_entry["corpus_id"],
        name=previous_live_entry["name"],
        contract=previous_live_entry.get("contract", FEDERATION_CONTRACT),
        status=previous_live_entry.get("status", "active"),
        make_default=bool(previous_live_entry.get("default")),
    )
    restored_policy = restore_provider_source_policy(
        resolved_project_root,
        provider=entry.get("provider"),
        policy_payload=entry.get("previous_source_policy") or {},
        note=note,
    )
    federation_result = build_federation(resolved_project_root)
    recorded_at = now_iso()
    write_json(
        corpus_live_pointer_path(resolved_project_root),
        {
            "event": "rollback",
            "recorded_at": recorded_at,
            "source_candidate_id": entry.get("candidate_id"),
            "live_corpus_id": previous_live_entry["corpus_id"],
            "restored_root": previous_live_entry["root"],
        },
    )
    manifest = load_corpus_candidate_manifest(
        resolved_project_root, candidate_id=entry["candidate_id"]
    )
    manifest["status"] = "rolled-back"
    manifest["rollback"] = {
        "recorded_at": recorded_at,
        "note": note,
        "restored_root": previous_live_entry["root"],
    }
    write_json(
        corpus_candidates_dir(resolved_project_root) / manifest["candidate_id"] / "manifest.json",
        manifest,
    )
    write_json(corpus_candidate_latest_json_path(resolved_project_root), manifest)
    write_markdown(
        corpus_candidate_latest_markdown_path(resolved_project_root),
        render_corpus_candidate(manifest),
    )

    payload = {
        "recorded_at": recorded_at,
        "target": target,
        "source_candidate_id": entry.get("candidate_id"),
        "provider": entry.get("provider"),
        "note": note,
        "restored_entry": restored_entry,
        "restored_source_policy": restored_policy,
        "federation_summary_path": federation_result.get("summary_markdown_path"),
    }
    append_history(corpus_rollback_history_path(resolved_project_root), payload)
    return payload
