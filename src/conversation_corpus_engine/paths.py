from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PACKAGE_ROOT.parent
REPO_ROOT = SRC_ROOT.parent


def default_project_root() -> Path:
    override = os.environ.get("CCE_PROJECT_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT
