from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from platformdirs import user_data_dir


APP_NAME = "Codex Mission Control"
APP_AUTHOR = "OpenAI"
APP_DIR = Path(__file__).resolve().parents[1]
IS_FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", APP_DIR))
DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8010
DEFAULT_FRONTEND_PORT = 5173
DEFAULT_LAUNCHER_CONFIG = {
    "host": DEFAULT_BACKEND_HOST,
    "backendPort": DEFAULT_BACKEND_PORT,
    "frontendPort": DEFAULT_FRONTEND_PORT,
    "autoOpenBrowser": True,
    "launcherLogDir": ".runtime/launcher",
}


def _discover_source_repo_root() -> Path | None:
    explicit = os.environ.get("MISSION_CONTROL_REPO_ROOT")
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if (candidate / "apps" / "server" / "src" / "main.py").exists() and (candidate / "README.md").exists():
            return candidate
    for parent in APP_DIR.parents:
        if (parent / "apps" / "server" / "src").exists() and (parent / "README.md").exists():
            return parent
    return None


def _default_app_support_root() -> Path:
    explicit = os.environ.get("MISSION_CONTROL_APP_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(user_data_dir(APP_NAME, APP_AUTHOR)).resolve()


SOURCE_REPO_ROOT = _discover_source_repo_root()
APP_SUPPORT_ROOT = _default_app_support_root()
RUNNING_FROM_SOURCE = SOURCE_REPO_ROOT is not None and not IS_FROZEN
REPO_ROOT = SOURCE_REPO_ROOT or BUNDLE_ROOT
SCRIPTS_ROOT = (SOURCE_REPO_ROOT / "scripts") if SOURCE_REPO_ROOT else (BUNDLE_ROOT / "scripts")
WORKSPACE_ROOT = (SOURCE_REPO_ROOT / "workspace") if RUNNING_FROM_SOURCE else (APP_SUPPORT_ROOT / "workspace")
RUNTIME_ROOT = Path(
    os.environ.get("MISSION_CONTROL_RUNTIME_ROOT")
    or ((APP_DIR / ".runtime") if RUNNING_FROM_SOURCE else (APP_SUPPORT_ROOT / "runtime"))
).resolve()
RUNTIME_LOGS_ROOT = RUNTIME_ROOT / "logs"
WORKTREE_ROOT = RUNTIME_ROOT / "worktrees"


def _resolve_launcher_config_path() -> Path:
    explicit = os.environ.get("MISSION_CONTROL_LAUNCHER_CONFIG")
    if explicit:
        return Path(explicit).expanduser().resolve()
    bundled_launcher_config = SCRIPTS_ROOT / "mission-control.config.json"
    if SOURCE_REPO_ROOT:
        return (SOURCE_REPO_ROOT / "scripts" / "mission-control.config.json").resolve()
    if bundled_launcher_config.exists():
        return bundled_launcher_config.resolve()
    return (APP_SUPPORT_ROOT / "mission-control.config.json").resolve()


def _read_launcher_config_file() -> dict[str, object]:
    path = _resolve_launcher_config_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _resolve_launcher_root() -> Path:
    explicit = os.environ.get("MISSION_CONTROL_LAUNCHER_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    launcher_dir = str(_read_launcher_config_file().get("launcherLogDir") or DEFAULT_LAUNCHER_CONFIG["launcherLogDir"])
    launcher_path = Path(launcher_dir)
    if launcher_path.is_absolute():
        return launcher_path.resolve()
    if SOURCE_REPO_ROOT:
        return (SOURCE_REPO_ROOT / launcher_path).resolve()
    return (APP_SUPPORT_ROOT / launcher_path).resolve()


LAUNCHER_CONFIG_PATH = _resolve_launcher_config_path()
LAUNCHER_ROOT = _resolve_launcher_root()
DB_PATH = RUNTIME_ROOT / "mission_control.sqlite3"
DAEMON_METADATA_PATH = LAUNCHER_ROOT / "daemon.json"
DAEMON_TOKEN_PATH = RUNTIME_ROOT / "daemon.token"
DEFAULT_DB_URL = f"sqlite:///{DB_PATH.as_posix()}"
DEFAULT_RUNNER_MODE = "auto"
DEFAULT_MANAGER_MODE = "auto"
DEFAULT_SANDBOX = "workspace-write"
DEFAULT_APPROVAL_POLICY = "on-request"
DEFAULT_CLI_MODEL = "gpt-5.4"
DEFAULT_REASONING_EFFORT = "medium"


def frontend_dist_root() -> Path:
    explicit = os.environ.get("MISSION_CONTROL_FRONTEND_DIST")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if SOURCE_REPO_ROOT is not None:
        return (SOURCE_REPO_ROOT / "apps" / "dashboard" / "dist").resolve()
    return (BUNDLE_ROOT / "frontend_dist").resolve()

def ensure_runtime_dirs() -> None:
    paths = [WORKSPACE_ROOT, RUNTIME_ROOT, RUNTIME_LOGS_ROOT, WORKTREE_ROOT, LAUNCHER_ROOT]
    if not RUNNING_FROM_SOURCE:
        paths.insert(0, APP_SUPPORT_ROOT)
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def get_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def load_launcher_config() -> dict:
    config = DEFAULT_LAUNCHER_CONFIG.copy()
    config.update(_read_launcher_config_file())
    return config
