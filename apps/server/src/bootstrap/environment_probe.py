from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

from bootstrap.dependency_probe import probe_core_tools
from bootstrap.headless_config import headless_config_path, read_headless_config
from bootstrap.secret_redaction import redact_bootstrap_text, redact_bootstrap_value
from config import APP_SUPPORT_ROOT, DEFAULT_BACKEND_PORT, REPO_ROOT, RUNTIME_ROOT, get_codex_home, load_launcher_config
from daemon_state import daemon_identity_snapshot, read_daemon_metadata, resolve_backend_binding


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


def _discover_install_candidates() -> list[dict[str, Any]]:
    candidates = [
        ("workspace_repo", REPO_ROOT),
        ("app_support_root", APP_SUPPORT_ROOT),
        ("codex_plugin_home", get_codex_home() / "plugins" / "mission-control"),
    ]
    if platform.system() == "Windows":
        candidates.append(("legacy_windows_appdata", Path.home() / "AppData" / "Local" / "MissionControl"))
    discovered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for kind, path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        text = str(resolved)
        if text in seen or not resolved.exists():
            continue
        seen.add(text)
        markers = {
            "server_runtime": (resolved / "apps" / "server" / "src" / "main.py").exists(),
            "launcher_script": (resolved / "scripts" / "start-mission-control-daemon.ps1").exists()
            or (resolved / "scripts" / "start-mission-control-daemon.sh").exists(),
            "plugin_manifest": (resolved / "plugin.json").exists() or (resolved / "plugins" / "mission-control" / "plugin.json").exists(),
        }
        markers["install_conflict"] = bool(markers["server_runtime"] and markers["launcher_script"])
        discovered.append(
            {
                "kind": kind,
                "path": _normalize_path_text(resolved),
                "markers": markers,
            }
        )
    return discovered


def probe_environment(
    *,
    workspace_path: str | None = None,
    install_path: str | None = None,
    runtime_path: str | None = None,
) -> dict[str, Any]:
    launcher_config = load_launcher_config()
    metadata = read_daemon_metadata()
    backend_binding = resolve_backend_binding()
    daemon_identity = daemon_identity_snapshot()
    runtime_root = Path(runtime_path).expanduser().resolve() if runtime_path else RUNTIME_ROOT
    install_root = Path(install_path).expanduser().resolve() if install_path else REPO_ROOT
    plugin_paths = _plugin_paths()
    skill_paths = _skill_paths()
    daemon_status = {
        "host": str(backend_binding["host"]),
        "port": int(backend_binding["port"]),
        "mode": str(backend_binding["mode"] or "unknown"),
        "binding_source": str(backend_binding["source"]),
        "metadata_present": bool(metadata),
        "metadata_status": str(metadata.get("status") or "unknown"),
        "pid_running": bool(metadata.get("pid_running")),
        "repo_root": _normalize_path_text(daemon_identity.get("repo_root") or REPO_ROOT),
        "runtime_root": _normalize_path_text(daemon_identity.get("runtime_root") or runtime_root),
        "launcher_root": _normalize_path_text(daemon_identity.get("launcher_root") or APP_SUPPORT_ROOT),
    }
    stored_headless = read_headless_config(runtime_path)
    mcp_status = {
        "transport": str((stored_headless or {}).get("mcp_transport") or "stdio"),
        "port": (stored_headless or {}).get("mcp_port"),
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
        "discovered_installs": _discover_install_candidates(),
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
