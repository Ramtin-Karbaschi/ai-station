"""Resolve the AI Station project tree for gateway and UI processes.

Production installs live at /opt/ai-station. CI checkouts, developer clones,
and Windows+WSL copies may live elsewhere. Prefer an explicit environment
override, then a real installed catalog, then the repository that contains
this module.
"""

from __future__ import annotations

import os
from pathlib import Path

INSTALLED_ROOT = Path("/opt/ai-station")
CATALOG_MARKER = Path("config/model-catalog.json")


def project_dir() -> Path:
    env = os.getenv("AI_STATION_PROJECT_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if (INSTALLED_ROOT / CATALOG_MARKER).is_file():
        return INSTALLED_ROOT.resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / CATALOG_MARKER).is_file():
            return parent
    return INSTALLED_ROOT


PROJECT_DIR = project_dir()
