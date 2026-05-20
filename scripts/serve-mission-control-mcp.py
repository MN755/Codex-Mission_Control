from __future__ import annotations

import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _configure_imports(root: Path) -> None:
    mcp_src = root / "apps" / "mcp-server" / "src"
    if str(mcp_src) not in sys.path:
        sys.path.insert(0, str(mcp_src))


def main() -> None:
    root = _repo_root()
    _configure_imports(root)
    from mission_control_mcp_server.__main__ import main as mcp_main

    mcp_main()


if __name__ == "__main__":
    main()
