from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .answering import load_json, write_json, write_markdown
from .corpus_candidates import (
    corpus_candidate_latest_json_path,
    corpus_live_pointer_path,
    corpus_promotion_latest_json_path,
)
from .federated_canon import load_federated_review_queue
from .federation import (
    federation_report_path,
    load_corpus_surface,
    load_registry,
    registry_path,
)
from .governance_candidates import (
    policy_application_latest_json_path,
    policy_candidate_latest_json_path,
    policy_live_pointer_path,
)
from .governance_policy import load_or_create_promotion_policy, promotion_policy_path
from .governance_replay import policy_replay_latest_json_path
from .paths import REPO_ROOT
from .provider_catalog import (
    PROVIDER_CONFIG,
    default_source_drop_root,
    get_provider_config,
    provider_corpus_targets,
)
from .provider_readiness import build_provider_readiness
from .provider_refresh import provider_refresh_latest_json_path
from .schema_validation import list_schemas, validate_payload
from .source_policy import load_source_policy, source_policy_path

SURFACE_MANIFEST_CONTRACT = "conversation-corpus-engine-surface-manifest-v1"
MCP_CONTEXT_CONTRACT = "conversation-corpus-engine-mcp-context-v1"
SURFACE_BUNDLE_CONTRACT = "conversation-corpus-engine-surface-bundle-v1"
SURFACE_CONTRACT_VERSION = 1

CLI_SURFACES = [
    {
        "command": "cce schema validate corpus-contract --path /path/to/corpus/contract.json",
        "purpose": "Validate canonical artifacts before promotion or export.",
        "audience": "engine",
    },
    {
        "command": "cce provider refresh --provider perplexity --project-root /path/to/project --source-drop-root /path/to/source-drop",
        "purpose": "Import, evaluate, and stage provider refresh candidates.",
        "audience": "engine",
    },
    {
        "command": "cce candidate promote --project-root /path/to/project --candidate-id latest",
        "purpose": "Promote reviewed corpus candidates into the live registry.",
        "audience": "engine",
    },
    {
        "command": "cce policy apply --project-root /path/to/project --candidate-id latest",
        "purpose": "Apply reviewed promotion-policy candidates.",
        "audience": "engine",
    },
    {
        "command": "cce surface bundle --project-root /path/to/project --source-drop-root /path/to/source-drop",
        "purpose": "Export Meta/MCP-facing manifests from the governed project state.",
        "audience": "mcp",
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def surface_reports_dir(project_root: Path) -> Path:
    return project_root.resolve() / "reports" / "surfaces"


def surface_manifest_json_path(project_root: Path) -> Path:
    return surface_reports_dir(project_root) / "surface-manifest.json"


def surface_manifest_markdown_path(project_root: Path) -> Path:
    return surface_reports_dir(project_root) / "surface-manifest.md"


def mcp_context_json_path(project_root: Path) -> Path:
    return surface_reports_dir(project_root) / "mcp-context.json"


def mcp_context_markdown_path(project_root: Path) -> Path:
    return surface_reports_dir(project_root) / "mcp-context.md"


def surface_bundle_json_path(project_root: Path) -> Path:
    return surface_reports_dir(project_root) / "surface-bundle.json"


def surface_bundle_markdown_path(project_root: Path) -> Path:
    return surface_reports_dir(project_root) / "surface-bundle.md"


def optional_json(path: Path) -> Any:
    return load_json(path, default=None)


def registry_snapshot(project_root: Path) -> dict[str, Any]:
    registry = load_registry(project_root)
    entries = registry.get("corpora", [])
    surfaces = [load_corpus_surface(entry) for entry in entries]
    summaries = [surface["summary"] for surface in surfaces]
    active_summaries = [item for item in summaries if item.get("status", "active") == "active"]
    default_entry = next(
        (
            entry
            for entry in entries
            if entry.get("status", "active") == "active" and entry.get("default")
        ),
        None,
    )
    return {
        "registry": registry,
        "summaries": summaries,
        "active_summaries": active_summaries,
        "default_corpus_id": default_entry.get("corpus_id") if default_entry else None,
    }


def provider_manifest_rows(
    project_root: Path,
    source_drop_root: Path,
    *,
    readiness_payload: dict[str, Any],
    registry_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    readiness_by_provider = {
        item["provider"]: item for item in readiness_payload.get("providers") or []
    }
    rows: list[dict[str, Any]] = []
    for provider in sorted(PROVIDER_CONFIG):
        config = get_provider_config(provider)
        readiness_item = readiness_by_provider.get(provider) or {}
        targets = provider_corpus_targets(
            project_root,
            provider,
            source_drop_root,
            registry=registry_entries,
        )
        rows.append(
            {
                "provider": provider,
                "display_name": config["display_name"],
                "adapter_type": config["adapter_type"],
                "discovery_mode": config["discovery_mode"],
                "calibration_only": bool(config.get("calibration_only", False)),
                "selected_targets": [
                    {
                        "role": target["role"],
                        "corpus_id": target["corpus_id"],
                        "root": target["root"],
                        "selected": bool(target.get("selected")),
                    }
                    for target in targets
                ],
                "source_policy": load_source_policy(project_root, provider) or None,
                "readiness_status": readiness_item.get("overall_state", "unknown"),
                "next_command": readiness_item.get("next_command", "ready"),
                "notes": config.get("notes", []),
            },
        )
    return rows


def mcp_provider_rows(readiness_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in readiness_payload.get("providers") or []:
        rows.append(
            {
                "provider": item["provider"],
                "display_name": item["display_name"],
                "overall_state": item["overall_state"],
                "next_command": item["next_command"],
                "selected_target": item["selected_target"],
                "targets": item["targets"],
                "policy": item.get("policy"),
                "discovery": item["discovery"],
                "notes": item.get("notes", []),
            },
        )
    return rows


def latest_provider_refreshes(project_root: Path) -> dict[str, Any]:
    return {
        provider: optional_json(provider_refresh_latest_json_path(project_root, provider))
        for provider in sorted(PROVIDER_CONFIG)
    }


def render_surface_manifest(payload: dict[str, Any]) -> str:
    registry = payload.get("registry") or {}
    lines = [
        "# Surface Manifest",
        "",
        f"- Generated: {payload.get('generated_at') or 'n/a'}",
        f"- Package: {((payload.get('engine') or {}).get('package')) or 'n/a'}",
        f"- Version: {((payload.get('engine') or {}).get('version')) or 'n/a'}",
        f"- Project root: {((payload.get('project') or {}).get('project_root')) or 'n/a'}",
        f"- Source-drop root: {((payload.get('project') or {}).get('source_drop_root')) or 'n/a'}",
        f"- Registered corpora: {registry.get('corpus_count', 0)}",
        f"- Active corpora: {registry.get('active_corpus_count', 0)}",
        f"- Providers: {len(payload.get('providers') or [])}",
        "",
        "## Registry",
        "",
    ]
    for item in registry.get("corpora") or []:
        lines.append(
            f"- {item['corpus_id']}: status={item.get('status')} gate={item.get('evaluation_overall_state') or 'n/a'} freshness={item.get('source_freshness_state') or 'n/a'}",
        )
    lines.extend(["", "## Providers", ""])
    for item in payload.get("providers") or []:
        lines.append(
            f"- {item['provider']}: readiness={item.get('readiness_status')} next={item.get('next_command')}",
        )
    return "\n".join(lines)


def render_mcp_context(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# MCP Context",
        "",
        f"- Generated: {payload.get('generated_at') or 'n/a'}",
        f"- Active corpora: {summary.get('active_corpus_count', 0)}",
        f"- Providers: {summary.get('provider_count', 0)}",
        f"- Healthy providers: {summary.get('healthy_provider_count', 0)}",
        f"- Refresh recommended: {summary.get('refresh_recommended_count', 0)}",
        f"- Open review items: {summary.get('open_review_count', 0)}",
        "",
        "## Provider States",
        "",
    ]
    for item in payload.get("providers") or []:
        lines.append(
            f"- {item['provider']}: {item.get('overall_state')} next={item.get('next_command')}",
        )
    return "\n".join(lines)


def render_surface_bundle(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Surface Bundle",
        "",
        f"- Generated: {payload.get('generated_at') or 'n/a'}",
        f"- Overall valid: {'yes' if summary.get('valid') else 'no'}",
        f"- Error count: {summary.get('error_count', 0)}",
        f"- Manifest path: {((payload.get('manifest') or {}).get('path')) or 'n/a'}",
        f"- Context path: {((payload.get('context') or {}).get('path')) or 'n/a'}",
        "",
        "## Validation",
        "",
        f"- Surface manifest: {'pass' if (payload.get('manifest') or {}).get('valid') else 'fail'}",
        f"- MCP context: {'pass' if (payload.get('context') or {}).get('valid') else 'fail'}",
        f"- Bundle envelope: {'pass' if (payload.get('bundle_validation') or {}).get('valid') else 'fail'}",
    ]
    return "\n".join(lines)


def build_surface_manifest(
    project_root: Path,
    *,
    source_drop_root: Path | None = None,
) -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    resolved_source_drop_root = (
        source_drop_root or default_source_drop_root(resolved_project_root)
    ).resolve()
    snapshot = registry_snapshot(resolved_project_root)
    readiness_payload = build_provider_readiness(
        resolved_project_root,
        resolved_source_drop_root,
    )
    registry = snapshot["registry"]
    return {
        "contract_name": SURFACE_MANIFEST_CONTRACT,
        "contract_version": SURFACE_CONTRACT_VERSION,
        "generated_at": now_iso(),
        "engine": {
            "package": "conversation-corpus-engine",
            "version": __version__,
            "repo_root": str(REPO_ROOT.resolve()),
        },
        "project": {
            "project_root": str(resolved_project_root),
            "source_drop_root": str(resolved_source_drop_root),
            "organ": "ORGAN-I",
            "system_role": "conversation-corpus-engine",
        },
        "schemas": list_schemas(),
        "cli_surfaces": CLI_SURFACES,
        "registry": {
            "registry_version": registry.get("registry_version", 1),
            "corpus_count": len(registry.get("corpora") or []),
            "active_corpus_count": len(snapshot["active_summaries"]),
            "default_corpus_id": snapshot["default_corpus_id"],
            "corpora": snapshot["summaries"],
        },
        "providers": provider_manifest_rows(
            resolved_project_root,
            resolved_source_drop_root,
            readiness_payload=readiness_payload,
            registry_entries=registry.get("corpora") or [],
        ),
        "artifacts": {
            "registry_path": str(registry_path(resolved_project_root)),
            "promotion_policy_path": str(promotion_policy_path(resolved_project_root)),
            "federation_summary_path": str(federation_report_path(resolved_project_root)),
            "policy_replay_latest_json_path": str(
                policy_replay_latest_json_path(resolved_project_root)
            ),
            "policy_candidate_latest_json_path": str(
                policy_candidate_latest_json_path(resolved_project_root)
            ),
            "policy_application_latest_json_path": str(
                policy_application_latest_json_path(resolved_project_root)
            ),
            "corpus_candidate_latest_json_path": str(
                corpus_candidate_latest_json_path(resolved_project_root)
            ),
            "corpus_promotion_latest_json_path": str(
                corpus_promotion_latest_json_path(resolved_project_root)
            ),
            "corpus_live_pointer_path": str(corpus_live_pointer_path(resolved_project_root)),
            "source_policy_paths": {
                provider: str(source_policy_path(resolved_project_root, provider))
                for provider in sorted(PROVIDER_CONFIG)
            },
            "provider_refresh_latest_json_paths": {
                provider: str(provider_refresh_latest_json_path(resolved_project_root, provider))
                for provider in sorted(PROVIDER_CONFIG)
            },
        },
    }


def build_mcp_context_payload(
    project_root: Path,
    *,
    source_drop_root: Path | None = None,
) -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    resolved_source_drop_root = (
        source_drop_root or default_source_drop_root(resolved_project_root)
    ).resolve()
    snapshot = registry_snapshot(resolved_project_root)
    readiness_payload = build_provider_readiness(
        resolved_project_root,
        resolved_source_drop_root,
    )
    open_review_items = [
        item
        for item in (load_federated_review_queue(resolved_project_root).get("items") or [])
        if item.get("status") == "open"
    ]
    providers = mcp_provider_rows(readiness_payload)
    healthy_provider_count = sum(
        1 for item in providers if item.get("overall_state") == "healthy-federation"
    )
    refresh_recommended_count = sum(
        1 for item in providers if "cce provider refresh" in (item.get("next_command") or "")
    )
    return {
        "contract_name": MCP_CONTEXT_CONTRACT,
        "contract_version": SURFACE_CONTRACT_VERSION,
        "generated_at": now_iso(),
        "project_root": str(resolved_project_root),
        "source_drop_root": str(resolved_source_drop_root),
        "summary": {
            "registered_corpus_count": len(snapshot["registry"].get("corpora") or []),
            "active_corpus_count": len(snapshot["active_summaries"]),
            "provider_count": len(providers),
            "healthy_provider_count": healthy_provider_count,
            "refresh_recommended_count": refresh_recommended_count,
            "open_review_count": len(open_review_items),
        },
        "registry": {
            "default_corpus_id": snapshot["default_corpus_id"],
            "corpora": snapshot["summaries"],
        },
        "providers": providers,
        "governance": {
            "promotion_policy": load_or_create_promotion_policy(resolved_project_root),
            "latest_policy_replay": optional_json(
                policy_replay_latest_json_path(resolved_project_root)
            ),
            "latest_policy_candidate": optional_json(
                policy_candidate_latest_json_path(resolved_project_root)
            ),
            "latest_policy_application": optional_json(
                policy_application_latest_json_path(resolved_project_root)
            ),
            "latest_corpus_candidate": optional_json(
                corpus_candidate_latest_json_path(resolved_project_root)
            ),
            "latest_corpus_promotion": optional_json(
                corpus_promotion_latest_json_path(resolved_project_root)
            ),
        },
        "latest_events": {
            "latest_corpus_live_pointer": optional_json(
                corpus_live_pointer_path(resolved_project_root)
            ),
            "latest_policy_live_pointer": optional_json(
                policy_live_pointer_path(resolved_project_root)
            ),
            "latest_provider_refreshes": latest_provider_refreshes(resolved_project_root),
        },
        "review_queue": {
            "open_count": len(open_review_items),
            "items": open_review_items[:25],
        },
        "schema_catalog": list_schemas(),
    }


def write_surface_manifest_artifacts(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    json_path = surface_manifest_json_path(project_root)
    markdown_path = surface_manifest_markdown_path(project_root)
    write_json(json_path, payload)
    write_markdown(markdown_path, render_surface_manifest(payload))
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def write_mcp_context_artifacts(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, str]:
    json_path = mcp_context_json_path(project_root)
    markdown_path = mcp_context_markdown_path(project_root)
    write_json(json_path, payload)
    write_markdown(markdown_path, render_mcp_context(payload))
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def export_surface_bundle(
    project_root: Path,
    *,
    source_drop_root: Path | None = None,
) -> dict[str, Any]:
    resolved_project_root = project_root.resolve()
    resolved_source_drop_root = (
        source_drop_root or default_source_drop_root(resolved_project_root)
    ).resolve()
    manifest_payload = build_surface_manifest(
        resolved_project_root,
        source_drop_root=resolved_source_drop_root,
    )
    context_payload = build_mcp_context_payload(
        resolved_project_root,
        source_drop_root=resolved_source_drop_root,
    )
    manifest_paths = write_surface_manifest_artifacts(resolved_project_root, manifest_payload)
    context_paths = write_mcp_context_artifacts(resolved_project_root, context_payload)
    manifest_validation = validate_payload("surface-manifest", manifest_payload)
    context_validation = validate_payload("mcp-context", context_payload)
    bundle = {
        "contract_name": SURFACE_BUNDLE_CONTRACT,
        "contract_version": SURFACE_CONTRACT_VERSION,
        "generated_at": now_iso(),
        "project_root": str(resolved_project_root),
        "source_drop_root": str(resolved_source_drop_root),
        "summary": {
            "valid": manifest_validation["valid"] and context_validation["valid"],
            "error_count": manifest_validation["error_count"] + context_validation["error_count"],
        },
        "manifest": {
            "schema_name": "surface-manifest",
            "path": manifest_paths["json_path"],
            "markdown_path": manifest_paths["markdown_path"],
            "valid": manifest_validation["valid"],
            "error_count": manifest_validation["error_count"],
            "errors": manifest_validation["errors"],
        },
        "context": {
            "schema_name": "mcp-context",
            "path": context_paths["json_path"],
            "markdown_path": context_paths["markdown_path"],
            "valid": context_validation["valid"],
            "error_count": context_validation["error_count"],
            "errors": context_validation["errors"],
        },
    }
    bundle["bundle_validation"] = {
        "schema": "surface-bundle",
        "schema_path": "",
        "valid": False,
        "error_count": 0,
        "errors": [],
    }
    bundle_validation = validate_payload("surface-bundle", bundle)
    bundle["bundle_validation"] = bundle_validation
    write_json(surface_bundle_json_path(resolved_project_root), bundle)
    write_markdown(
        surface_bundle_markdown_path(resolved_project_root), render_surface_bundle(bundle)
    )
    return bundle
