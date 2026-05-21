from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mission_control_manage import main, resolve_codex_home, uninstall_codex_bundle

uninstall_plugin_bundle = uninstall_codex_bundle

__all__ = ["main", "resolve_codex_home", "uninstall_codex_bundle", "uninstall_plugin_bundle"]


if __name__ == "__main__":
    raise SystemExit(main(["uninstall", *sys.argv[1:]]))
