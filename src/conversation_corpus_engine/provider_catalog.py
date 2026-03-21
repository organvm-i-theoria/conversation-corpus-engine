from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .source_policy import load_source_policy

DEFAULT_SOURCE_DROP_ENV = "CCE_SOURCE_DROP_ROOT"

PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "chatgpt": {
        "display_name": "ChatGPT",
        "adapter_state": "supported",
        "adapter_type": "chatgpt-export",
        "discovery_mode": "chatgpt-bundle",
        "inbox_rel": "chatgpt/inbox",
        "default_corpus_id": "chatgpt-history-memory",
        "default_corpus_name": "ChatGPT History Memory",
        "calibration_only": True,
    },
    "claude": {
        "display_name": "Claude",
        "adapter_state": "supported",
        "adapter_type": "claude-export",
        "discovery_mode": "claude-bundle",
        "inbox_rel": "claude/inbox",
        "default_corpus_id": "claude-local-session-memory",
        "default_corpus_name": "Claude Local Session Memory",
        "fallback_corpus_id": "claude-history-memory",
        "fallback_corpus_name": "Claude History Memory",
        "local_source_root": "/Users/4jp/Library/Application Support/Claude",
        "calibration_only": True,
    },
    "gemini": {
        "display_name": "Gemini",
        "adapter_state": "supported",
        "adapter_type": "gemini-export",
        "discovery_mode": "document-export",
        "inbox_rel": "gemini/inbox",
        "default_corpus_id": "gemini-history-memory",
        "default_corpus_name": "Gemini History Memory",
        "calibration_only": True,
    },
    "grok": {
        "display_name": "Grok",
        "adapter_state": "supported",
        "adapter_type": "grok-export",
        "discovery_mode": "document-export",
        "inbox_rel": "grok/inbox",
        "default_corpus_id": "grok-history-memory",
        "default_corpus_name": "Grok History Memory",
        "calibration_only": True,
    },
    "perplexity": {
        "display_name": "Perplexity",
        "adapter_state": "supported",
        "adapter_type": "perplexity-export",
        "discovery_mode": "document-export",
        "inbox_rel": "perplexity/inbox",
        "default_corpus_id": "perplexity-history-memory",
        "default_corpus_name": "Perplexity History Memory",
        "local_source_root": "/Users/4jp/Library/Containers/ai.perplexity.mac",
        "calibration_only": True,
    },
    "copilot": {
        "display_name": "Copilot",
        "adapter_state": "supported",
        "adapter_type": "copilot-export",
        "discovery_mode": "document-export",
        "inbox_rel": "copilot/inbox",
        "default_corpus_id": "copilot-history-memory",
        "default_corpus_name": "Copilot History Memory",
        "local_source_root": "/Users/4jp/Library/Containers/com.microsoft.copilot-mac",
        "calibration_only": True,
        "notes": [
            "Current Copilot ingestion targets exported conversation bundles, not IDE extension traces.",
        ],
    },
}


def default_source_drop_root(project_root: Path | None = None) -> Path:
    override = os.environ.get(DEFAULT_SOURCE_DROP_ENV)
    if override:
        return Path(override).expanduser().resolve()
    base_root = (project_root or Path.cwd()).resolve()
    return (base_root.parent / "source-drop").resolve()


def get_provider_config(provider: str) -> dict[str, Any]:
    try:
        return PROVIDER_CONFIG[provider]
    except KeyError as exc:
        raise KeyError(f"Unknown provider: {provider}") from exc


def conventional_corpus_root(source_drop_root: Path, corpus_id: str) -> Path:
    return (source_drop_root.resolve().parent / corpus_id).resolve()


def provider_bootstrap_report_path(project_root: Path, provider: str) -> Path:
    return project_root.resolve() / "reports" / f"{provider}-evaluation-bootstrap-latest.md"


def provider_corpus_targets(
    project_root: Path,
    provider: str,
    source_drop_root: Path,
    *,
    registry: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    config = get_provider_config(provider)
    registry_by_id = {item["corpus_id"]: item for item in registry or []}
    policy = load_source_policy(project_root, provider)
    targets: list[dict[str, Any]] = []

    primary_corpus_id = policy.get("primary_corpus_id") or config["default_corpus_id"]
    primary_corpus_name = config["default_corpus_name"]
    primary_root = (
        policy.get("primary_root")
        or registry_by_id.get(primary_corpus_id, {}).get("root")
        or conventional_corpus_root(
            source_drop_root,
            primary_corpus_id,
        )
    )
    if primary_root:
        targets.append(
            {
                "role": "primary",
                "selected": True,
                "corpus_id": primary_corpus_id,
                "corpus_name": primary_corpus_name,
                "root": str(Path(primary_root).resolve()),
                "policy": policy or None,
            },
        )

    fallback_corpus_id = policy.get("fallback_corpus_id") or config.get("fallback_corpus_id")
    fallback_corpus_name = config.get("fallback_corpus_name")
    fallback_root = policy.get("fallback_root")
    if fallback_corpus_id and not fallback_root:
        fallback_root = registry_by_id.get(fallback_corpus_id, {}).get(
            "root"
        ) or conventional_corpus_root(
            source_drop_root,
            fallback_corpus_id,
        )
    if fallback_root and fallback_corpus_id:
        targets.append(
            {
                "role": "fallback",
                "selected": False,
                "corpus_id": fallback_corpus_id,
                "corpus_name": fallback_corpus_name or fallback_corpus_id,
                "root": str(Path(fallback_root).resolve()),
                "policy": policy or None,
            },
        )
    if targets:
        return targets
    return []
