from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

from bootstrap.dependency_probe import probe_core_tools
from bootstrap.headless_config import headless_config_path
from bootstrap.secret_redaction import redact_bootstrap_text, redact_bootstrap_value
from config import DEFAULT_BACKEND_PORT, REPO_ROOT, RUNTIME_ROOT, get_codex_home, load_launcher_config
from daemon_state import read_daemon_metadata


PLUGIN_ROOT = REPO_ROOT / "plugins" / "mission-control"
LOCAL_SKILLS_ROOT = REPO_ROOT / ".codex" / "skills"


def _normalize_path_text(value: str | Path) -> str:
    path_text = str(value)
    home = str(Path.home())
    if path_text.startswith(home):
        path_text = path_text.replace(home, "~", 1)
    return redact_bootstrap_text(path_text)


def summarize_path_entries(path_env: str | None = None, *, limit: int = 12) -> dict[str, Any]:
    raw_entries = [entry for entry in (path_env or os.environ.get("PATH", "")).split(os.pathsep) if entry]
    normalized = []
    seen: set[str] = set()
    for entry in raw_entries:
        text = _normalize_path_text(entry)
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return {
        "count": len(normalized),
        "entries": normalized[:limit],
        "omitted_count": max(len(normalized) - limit, 0),
    }


def _shell_name() -> str:
    shell = os.environ.get("SHELL") or os.environ.get("COMSPEC") or "unknown"
    return Path(shell).name or shell


def _plugin_paths() -> list[str]:
    paths = [PLUGIN_ROOT, REPO_ROOT / ".codex" / "plugins" / "mission-control", get_codex_home() / "plugins" / "mission-control"]
    unique: list[str] = []
    seen: set[str] = set()
    for path in paths:
        text = _normalize_path_text(path)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _skill_paths() -> list[str]:
    paths = [LOCAL_SKILLS_ROOT, PLUGIN_ROOT / "skills", get_codex_home() / "skills"]
    unique: list[str] = []
    seen: set[str] = set()
    for path in paths:
        text = _normalize_path_text(path)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def probe_environment(
    *,
    workspace_path: str | None = None,
    install_path: str | None = None,
    runtime_path: str | None = None,
) -> dict[str, Any]:
    launcher_config = load_launcher_config()
    metadata = read_daemon_metadata()
    runtime_root = Path(runtime_path).expanduser().resolve() if runtime_path else RUNTIME_ROOT
    install_root = Path(install_path).expanduser().resolve() if install_path else REPO_ROOT
    plugin_paths = _plugin_paths()
    skill_paths = _skill_paths()
    daemon_status = {
        "host": str(metadata.get("host") or launcher_config.get("host") or "127.0.0.1"),
        "port": int(metadata.get("port") or launcher_config.get("backendPort") or DEFAULT_BACKEND_PORT),
        "mode": str(metadata.get("mode") or "unknown"),
        "metadata_present": bool(metadata),
    }
    mcp_status = {
        "transport": "stdio",
        "example_config_path": _normalize_path_text(PLUGIN_ROOT / "mcp" / "mission-control-mcp.example.json"),
        "headless_config_path": _normalize_path_text(headless_config_path(runtime_path)),
    }
    payload = {
        "os": platform.system(),
        "architecture": platform.machine(),
        "shell": _shell_name(),
        "home_directory": _normalize_path_text(Path.home()),
        "workspace_path": _normalize_path_text(workspace_path) if workspace_path else None,
        "existing_install_path": _normalize_path_text(install_root),
        "runtime_path": _normalize_path_text(runtime_root),
        "path_entries_summary": summarize_path_entries(),
        "core_tools": probe_core_tools(),
        "plugin_paths": plugin_paths,
        "skill_paths": skill_paths,
        "daemon_status": daemon_status,
        "mcp_status": mcp_status,
        "mission_control": {
            "install_path": _normalize_path_text(install_root),
            "runtime_path": _normalize_path_text(runtime_root),
            "daemon_status": daemon_status,
            "mcp_status": mcp_status,
            "plugin_paths": plugin_paths,
            "skill_paths": skill_paths,
        },
    }
    return redact_bootstrap_value(payload)
