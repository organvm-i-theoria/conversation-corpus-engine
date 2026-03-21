from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .provider_catalog import PROVIDER_CONFIG, get_provider_config
from .provider_exports import (
    looks_like_claude_bundle,
    path_has_supported_export_content,
    visible_entries,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def summarize_provider(provider: str, source_drop_root: Path) -> dict[str, Any]:
    config = get_provider_config(provider)
    inbox_root = (source_drop_root / config["inbox_rel"]).resolve()
    entries = visible_entries(inbox_root)
    detector = looks_like_claude_bundle if config["discovery_mode"] == "claude-bundle" else path_has_supported_export_content
    detected_source_path = None
    upload_state = "empty"
    local_source_root = config.get("local_source_root")
    local_source_state = None

    if local_source_root:
        local_source_state = "present" if Path(local_source_root).exists() else "missing"

    if detector(inbox_root):
        detected_source_path = str(inbox_root)
        upload_state = "ready"
    else:
        ready_entries = [entry.resolve() for entry in entries if detector(entry)]
        if len(ready_entries) == 1:
            detected_source_path = str(ready_entries[0])
            upload_state = "ready"
        elif len(ready_entries) > 1:
            upload_state = "multiple-ready"
        elif entries:
            upload_state = "present-unresolved"

    return {
        "provider": provider,
        "display_name": config["display_name"],
        "adapter_state": config["adapter_state"],
        "adapter_type": config["adapter_type"],
        "inbox_root": str(inbox_root),
        "visible_entries": [entry.name for entry in entries],
        "upload_count": len(entries),
        "upload_state": upload_state,
        "detected_source_path": detected_source_path,
        "local_source_root": local_source_root,
        "local_source_state": local_source_state,
        "calibration_only": config.get("calibration_only", False),
    }


def discover_provider_uploads(project_root: Path, source_drop_root: Path) -> dict[str, Any]:
    source_drop_root = source_drop_root.resolve()
    providers = [summarize_provider(provider, source_drop_root) for provider in PROVIDER_CONFIG]
    return {
        "generated_at": now_iso(),
        "project_root": str(project_root.resolve()),
        "source_drop_root": str(source_drop_root),
        "counts": {
            "providers": len(providers),
            "supported": sum(1 for item in providers if item["adapter_state"] == "supported"),
            "ready_uploads": sum(1 for item in providers if item["upload_state"] == "ready"),
            "present_unresolved": sum(1 for item in providers if item["upload_state"] == "present-unresolved"),
            "multiple_ready": sum(1 for item in providers if item["upload_state"] == "multiple-ready"),
        },
        "providers": providers,
    }


def render_provider_discovery_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Source-drop root: {payload['source_drop_root']}",
        f"Generated: {payload['generated_at']}",
        f"Providers: {payload['counts']['providers']}",
        "",
    ]
    for item in payload["providers"]:
        lines.append(f"{item['provider']}  adapter={item['adapter_state']}  upload_state={item['upload_state']}")
        lines.append(f"  inbox: {item['inbox_root']}")
        if item.get("detected_source_path"):
            lines.append(f"  detected_source: {item['detected_source_path']}")
        if item.get("local_source_root"):
            lines.append(f"  local_source: {item['local_source_root']} ({item.get('local_source_state')})")
        if item.get("visible_entries"):
            lines.append(f"  entries: {', '.join(item['visible_entries'])}")
        lines.append("")
    return "\n".join(lines).rstrip()
