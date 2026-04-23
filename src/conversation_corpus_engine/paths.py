from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PACKAGE_ROOT.parent
REPO_ROOT = SRC_ROOT.parent
WORKSPACE_ROOT_ENV = "CCE_WORKSPACE_ROOT"
WORKSPACE_REPO_ALIASES = {
    "victoroff-group": "padavano",
}


def default_project_root() -> Path:
    override = os.environ.get("CCE_PROJECT_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT


def default_workspace_root() -> Path:
    override = os.environ.get(WORKSPACE_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "Workspace").resolve()


@lru_cache(maxsize=256)
def _workspace_repo_roots(workspace_root: str, repo_name: str) -> tuple[str, ...]:
    root = Path(workspace_root)
    if not repo_name or not root.exists():
        return ()

    matches: list[Path] = []
    direct = root / repo_name
    if direct.exists():
        matches.append(direct.resolve())

    for child in sorted(root.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        nested = child / repo_name
        if nested.exists():
            matches.append(nested.resolve())

    unique: list[str] = []
    seen: set[str] = set()
    for match in matches:
        text = str(match)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return tuple(unique)


def resolve_workspace_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if candidate.exists():
        return candidate

    workspace_root = default_workspace_root()
    try:
        relative = candidate.relative_to(workspace_root)
    except ValueError:
        return candidate

    repo_options: list[tuple[str, Path]] = []
    if len(relative.parts) >= 1:
        repo_options.append((relative.parts[0], Path(*relative.parts[1:])))
    if len(relative.parts) >= 2:
        repo_options.append((relative.parts[1], Path(*relative.parts[2:])))

    seen: set[tuple[str, str]] = set()
    for repo_name, remainder in repo_options:
        option_key = (repo_name, str(remainder))
        if option_key in seen:
            continue
        seen.add(option_key)
        lookup_names = [repo_name]
        aliased = WORKSPACE_REPO_ALIASES.get(repo_name)
        if aliased and aliased not in lookup_names:
            lookup_names.append(aliased)
        for lookup_name in lookup_names:
            matches = [Path(item) for item in _workspace_repo_roots(str(workspace_root), lookup_name)]
            if len(matches) != 1:
                continue
            relocated = (matches[0] / remainder).resolve()
            if relocated.exists():
                return relocated
            if not remainder.parts:
                return matches[0]
    return candidate
