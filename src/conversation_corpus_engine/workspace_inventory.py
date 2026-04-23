from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .paths import default_workspace_root, resolve_workspace_path

ENGAGEMENT_ID_PATTERN = re.compile(
    r"^engagement_id:\s*[\"']?(ENG-[A-Za-z0-9-]+)[\"']?\s*$",
    re.MULTILINE,
)


def commerce_meta_root() -> Path | None:
    workspace_root = default_workspace_root()
    for candidate in (
        workspace_root / "organvm-iii-ergon" / "commerce--meta",
        workspace_root / "commerce--meta",
    ):
        resolved = resolve_workspace_path(candidate)
        if resolved.exists():
            return resolved
    return None


def engagement_record_id(path: Path) -> str | None:
    match = ENGAGEMENT_ID_PATTERN.search(path.read_text(encoding="utf-8"))
    return match.group(1).upper() if match else None


def find_commerce_engagement_records(
    engagement_ids: Iterable[str] | None = None,
) -> dict[str, Path]:
    root = commerce_meta_root()
    if root is None:
        return {}

    requested = {item.upper() for item in engagement_ids or [] if item}
    records: dict[str, Path] = {}
    for path in sorted((root / "engagements").rglob("*.yaml")):
        record_id = engagement_record_id(path)
        if not record_id:
            continue
        if requested and record_id not in requested:
            continue
        records[record_id] = path.resolve()
    return records


def find_commerce_engagement_record(engagement_id: str) -> Path | None:
    return find_commerce_engagement_records([engagement_id]).get(engagement_id.upper())
