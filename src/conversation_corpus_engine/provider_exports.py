from __future__ import annotations

from pathlib import Path

IGNORED_NAMES = {".DS_Store", "Thumbs.db"}
IGNORED_PARTS = {"__MACOSX", "__pycache__", "node_modules", ".git", ".venv"}
SUPPORTED_EXPORT_SUFFIXES = {".json", ".md", ".markdown", ".txt", ".html", ".htm", ".csv", ".zip"}


def visible_entries(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [
        item
        for item in sorted(root.iterdir())
        if item.name not in IGNORED_NAMES and not item.name.startswith(".")
    ]


def collect_supported_export_files(source_path: Path) -> list[Path]:
    source_path = source_path.resolve()
    if not source_path.exists():
        return []
    if source_path.is_file():
        return [source_path] if source_path.suffix.lower() in SUPPORTED_EXPORT_SUFFIXES else []

    files: list[Path] = []
    for path in sorted(source_path.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_path)
        if any(part.startswith(".") or part in IGNORED_PARTS for part in relative.parts):
            continue
        if path.name in IGNORED_NAMES:
            continue
        if path.suffix.lower() in SUPPORTED_EXPORT_SUFFIXES:
            files.append(path.resolve())
    return files


def path_has_supported_export_content(path: Path) -> bool:
    path = path.resolve()
    if not path.exists():
        return False
    if path.is_file():
        return path.suffix.lower() in SUPPORTED_EXPORT_SUFFIXES
    return bool(collect_supported_export_files(path))


def looks_like_claude_bundle(path: Path) -> bool:
    return path.is_dir() and (path / "conversations.json").exists() and (path / "users.json").exists()


def resolve_document_export_source_path(upload_root: Path, *, provider: str) -> Path:
    upload_root = upload_root.resolve()
    if path_has_supported_export_content(upload_root):
        return upload_root

    entries = visible_entries(upload_root)
    if not entries:
        raise FileNotFoundError(
            f"No {provider.title()} upload was found in {upload_root}. Put the raw export file or folder there first.",
        )

    eligible = [item.resolve() for item in entries if path_has_supported_export_content(item)]
    if len(eligible) == 1:
        return eligible[0]
    if len(eligible) > 1:
        raise FileNotFoundError(
            f"Multiple {provider.title()} export candidates were found in {upload_root}. Leave only one bundle or one extracted export there at a time.",
        )
    if len(entries) == 1:
        raise FileNotFoundError(
            f"The {provider.title()} upload at {entries[0]} is not a supported export shape yet. "
            "Supported inputs are extracted folders or files ending in .md, .markdown, .txt, .html, .htm, .json, .csv, or .zip.",
        )
    raise FileNotFoundError(
        f"{provider.title()} upload inbox {upload_root} contains multiple visible entries but no single supported export source could be selected.",
    )


def resolve_claude_source_path(upload_root: Path) -> Path:
    upload_root = upload_root.resolve()
    if looks_like_claude_bundle(upload_root):
        return upload_root
    entries = visible_entries(upload_root)
    if not entries:
        raise FileNotFoundError(
            f"No Claude upload was found in {upload_root}. Put the raw Claude export file or folder there first.",
        )
    bundle_dirs = [item.resolve() for item in entries if looks_like_claude_bundle(item)]
    if len(bundle_dirs) == 1:
        return bundle_dirs[0]
    if len(bundle_dirs) > 1:
        raise FileNotFoundError(
            f"Multiple Claude export bundles were found in {upload_root}. Leave only one extracted Claude export folder there at a time.",
        )
    if len(entries) == 1:
        return entries[0].resolve()
    raise FileNotFoundError(
        f"Claude upload inbox {upload_root} contains multiple visible entries but no single extracted Claude export folder could be selected.",
    )
