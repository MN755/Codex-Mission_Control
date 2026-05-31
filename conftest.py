from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PREFERRED_SRC_PATHS = [
    ROOT / "apps" / "server" / "src",
    ROOT / "apps" / "mcp-server" / "src",
]


def _prefer_workspace_sources() -> None:
    preferred = [str(path) for path in PREFERRED_SRC_PATHS if path.exists()]
    if not preferred:
        return
    current_paths = [entry for entry in sys.path if entry not in preferred]
    sys.path[:] = preferred + current_paths


_prefer_workspace_sources()
