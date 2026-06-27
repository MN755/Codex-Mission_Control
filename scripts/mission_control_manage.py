from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import socket
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANAGED_BLOCK_START = "# >>> mission-control managed >>>"
MANAGED_BLOCK_END = "# <<< mission-control managed <<<"
DEFAULT_REPO_URL = "https://github.com/MN755/Codex-Mission_Control"
DEFAULT_MARKETPLACE_NAME = "local"
RECURSIVE_IMPROVEMENT_DIR_NAME = "recursive-improvement"
RECURSIVE_CODEX_AUTH_FILES = ("auth.json", ".credentials.json", "installation_id")
ORCHESTRATION_WATCH_DIR_NAME = "orchestration-watch"
ORCHESTRATION_DISPLAY_MIN_REFRESH_SECONDS = 0.5


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def looks_like_repo(path: Path) -> bool:
    return (path / "apps" / "server" / "src").exists() and (path / "README.md").exists()


def discover_repo_root() -> Path:
    candidate = Path(__file__).resolve().parents[1]
    if looks_like_repo(candidate):
        return candidate
    raise FileNotFoundError("Could not resolve the Mission Control repository root from the current script location.")


def resolve_repo_root(*, install_dir: str | None = None, repo_url: str = DEFAULT_REPO_URL) -> Path:
    if install_dir:
        target = Path(install_dir).expanduser().resolve()
        if looks_like_repo(target):
            return target
        if target.exists() and not looks_like_repo(target):
            raise FileNotFoundError(f"Install target '{target}' exists but does not look like a Mission Control checkout.")
        git = shutil.which("git")
        if not git:
            raise FileNotFoundError("git is required to clone Mission Control into a new install directory.")
        completed = subprocess.run(
            [git, "clone", repo_url, str(target)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            output = completed.stdout.strip() or completed.stderr.strip()
            raise RuntimeError(output or f"git clone failed with exit code {completed.returncode}.")
        if not looks_like_repo(target):
            raise FileNotFoundError(f"Cloned install target '{target}' is missing expected Mission Control files.")
        return target
    return discover_repo_root()


def resolve_codex_home(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return Path.home().joinpath(".codex").resolve()


def resolve_agents_home(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    env_home = os.environ.get("AGENTS_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return Path.home().joinpath(".agents").resolve()


def resolve_python_command(explicit: str | None = None) -> str:
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    executable = Path(sys.executable).resolve()
    if executable.exists():
        return str(executable)
    for name in ("python", "python3", "py"):
        command = shutil.which(name)
        if command:
            return command
    raise FileNotFoundError("Python was not found on PATH.")


def _posix_text(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _copy_tree(source: Path, destination: Path, *, dry_run: bool) -> int:
    if not source.exists():
        return 0
    if dry_run:
        return sum(1 for path in source.rglob("*") if path.is_file())
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return sum(1 for path in destination.rglob("*") if path.is_file())


def _plugin_source_root(repo_root: Path) -> Path:
    packaged = repo_root / "plugins" / "mission-control"
    return packaged if packaged.exists() else (repo_root / ".codex" / "plugins" / "mission-control")


def _read_plugin_manifest(plugin_root: Path) -> dict[str, Any]:
    codex_manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    catalog_manifest_path = plugin_root / "plugin.json"
    if not codex_manifest_path.exists():
        return {
            "status": "missing",
            "manifest_path": str(codex_manifest_path),
            "catalog_manifest_path": str(catalog_manifest_path),
            "codex_manifest_required": True,
        }
    manifest_path = codex_manifest_path
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid",
            "manifest_path": str(manifest_path),
            "catalog_manifest_path": str(catalog_manifest_path),
            "codex_manifest_required": True,
            "error": str(exc),
        }
    return {
        "status": "ready",
        "manifest_path": str(manifest_path),
        "catalog_manifest_path": str(catalog_manifest_path),
        "codex_manifest_required": True,
        "name": payload.get("name"),
        "display_name": payload.get("display_name") or ((payload.get("interface") or {}).get("displayName")) or payload.get("name"),
        "version": payload.get("version"),
    }


def _skill_source_root(repo_root: Path) -> Path:
    return repo_root / ".codex" / "skills"


def _plugin_cache_root(codex_home: Path, plugin_name: str) -> Path:
    return codex_home / "plugins" / "cache" / DEFAULT_MARKETPLACE_NAME / plugin_name


def sync_codex_plugin_cache(
    plugin_source: Path,
    codex_home: Path,
    plugin_manifest: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    plugin_name = str(plugin_manifest.get("name") or "mission-control")
    plugin_version = str(plugin_manifest.get("version") or "dev")
    cache_root = _plugin_cache_root(codex_home, plugin_name)
    cache_destination = cache_root / plugin_version
    stale_versions: list[str] = []
    plugin_source_exists = plugin_source.exists()

    if not plugin_source_exists or plugin_manifest.get("status") != "ready":
        return {
            "status": str(plugin_manifest.get("status") or ("missing" if not plugin_source_exists else "invalid")),
            "cache_root": str(cache_root),
            "cache_destination": str(cache_destination),
            "plugin_name": plugin_name,
            "plugin_version": plugin_version,
            "plugin_files_copied": 0,
            "stale_versions_removed": [],
            "plugin_source_exists": plugin_source_exists,
            "dry_run": dry_run,
        }

    if cache_root.exists():
        stale_versions = sorted(
            path.name for path in cache_root.iterdir() if path.is_dir() and path.name != plugin_version
        )

    plugin_files_copied = _copy_tree(plugin_source, cache_destination, dry_run=dry_run)
    if not dry_run and cache_root.exists():
        for version_dir in cache_root.iterdir():
            if version_dir.is_dir() and version_dir.name != plugin_version:
                shutil.rmtree(version_dir)

    return {
        "status": "ready",
        "cache_root": str(cache_root),
        "cache_destination": str(cache_destination),
        "plugin_name": plugin_name,
        "plugin_version": plugin_version,
        "plugin_files_copied": plugin_files_copied,
        "stale_versions_removed": stale_versions,
        "dry_run": dry_run,
    }


def _default_marketplace() -> dict[str, Any]:
    return {
        "name": DEFAULT_MARKETPLACE_NAME,
        "interface": {
            "displayName": "Local Plugins",
        },
        "plugins": [],
    }


def _marketplace_entry(plugin_name: str) -> dict[str, Any]:
    return {
        "name": plugin_name,
        "source": {
            "source": "local",
            "path": f"./plugins/{plugin_name}",
        },
        "policy": {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        },
        "category": "Coding",
    }


def sync_local_plugin_marketplace(
    repo_root: Path,
    agents_home: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    plugin_source = _plugin_source_root(repo_root)
    plugin_manifest = _read_plugin_manifest(plugin_source)
    plugin_source_exists = plugin_source.exists()
    plugin_name = plugin_manifest.get("name") or "mission-control"
    plugin_display_name = plugin_manifest.get("display_name") or "Mission Control"
    plugins_root = agents_home.parent / "plugins"
    plugin_destination = plugins_root / plugin_name
    marketplace_path = agents_home / "plugins" / "marketplace.json"
    if not plugin_source_exists or plugin_manifest.get("status") != "ready":
        return {
            "status": str(plugin_manifest.get("status") or ("missing" if not plugin_source_exists else "invalid")),
            "agents_home": str(agents_home),
            "plugins_root": str(plugins_root),
            "plugin_source": str(plugin_source),
            "plugin_source_exists": plugin_source_exists,
            "plugin_destination": str(plugin_destination),
            "plugin_destination_exists_after": plugin_destination.exists(),
            "plugin_manifest": plugin_manifest,
            "plugin_name": plugin_name,
            "plugin_display_name": plugin_display_name,
            "plugin_files_copied": 0,
            "marketplace_path": str(marketplace_path),
            "marketplace_path_exists": marketplace_path.exists(),
            "marketplace_name": DEFAULT_MARKETPLACE_NAME,
            "plugin_id": f"{plugin_name}@{DEFAULT_MARKETPLACE_NAME}",
            "entry_updated": False,
            "dry_run": dry_run,
        }
    existing: dict[str, Any]
    if marketplace_path.exists():
        try:
            existing = json.loads(marketplace_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = _default_marketplace()
    else:
        existing = _default_marketplace()

    marketplace_name = str(existing.get("name") or DEFAULT_MARKETPLACE_NAME)
    plugins = list(existing.get("plugins") or [])
    entry = _marketplace_entry(plugin_name)
    updated = False
    for index, current in enumerate(plugins):
        if current.get("name") == plugin_name:
            if current != entry:
                plugins[index] = entry
                updated = True
            break
    else:
        plugins.append(entry)
        updated = True

    existing["name"] = marketplace_name
    existing.setdefault("interface", {"displayName": "Local Plugins"})
    existing["plugins"] = plugins

    plugin_files_copied = _copy_tree(plugin_source, plugin_destination, dry_run=dry_run)
    if not dry_run:
        marketplace_path.parent.mkdir(parents=True, exist_ok=True)
        marketplace_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    plugin_id = f"{plugin_name}@{marketplace_name}"
    return {
        "status": "ready",
        "agents_home": str(agents_home),
        "plugins_root": str(plugins_root),
        "plugin_source": str(plugin_source),
        "plugin_source_exists": plugin_source_exists,
        "plugin_destination": str(plugin_destination),
        "plugin_destination_exists_after": dry_run or plugin_destination.exists(),
        "plugin_manifest": plugin_manifest,
        "plugin_name": plugin_name,
        "plugin_display_name": plugin_display_name,
        "plugin_files_copied": plugin_files_copied,
        "marketplace_path": str(marketplace_path),
        "marketplace_path_exists": dry_run or marketplace_path.exists(),
        "marketplace_name": marketplace_name,
        "plugin_id": plugin_id,
        "entry_updated": updated,
        "dry_run": dry_run,
    }


def remove_local_plugin_marketplace(
    agents_home: Path,
    *,
    plugin_name: str = "mission-control",
    dry_run: bool = False,
) -> dict[str, Any]:
    plugins_root = agents_home.parent / "plugins"
    plugin_path = plugins_root / plugin_name
    marketplace_path = agents_home / "plugins" / "marketplace.json"
    plugin_removed = False
    marketplace_changed = False
    marketplace_name = DEFAULT_MARKETPLACE_NAME

    if plugin_path.exists():
        plugin_removed = True
        if not dry_run:
            shutil.rmtree(plugin_path)

    if marketplace_path.exists():
        try:
            payload = json.loads(marketplace_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = _default_marketplace()
        marketplace_name = str(payload.get("name") or DEFAULT_MARKETPLACE_NAME)
        plugins = list(payload.get("plugins") or [])
        filtered = [entry for entry in plugins if entry.get("name") != plugin_name]
        marketplace_changed = len(filtered) != len(plugins)
        if marketplace_changed:
            payload["plugins"] = filtered
            if not dry_run:
                marketplace_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "status": "ready" if plugin_removed or marketplace_changed else "not_installed",
        "agents_home": str(agents_home),
        "plugins_root": str(plugins_root),
        "plugin_path": str(plugin_path),
        "plugin_removed": plugin_removed,
        "marketplace_path": str(marketplace_path),
        "marketplace_name": marketplace_name,
        "plugin_id": f"{plugin_name}@{marketplace_name}",
        "marketplace_changed": marketplace_changed,
        "dry_run": dry_run,
    }


def sync_codex_bundle(repo_root: Path, codex_home: Path, *, dry_run: bool = False) -> dict[str, Any]:
    plugin_source = _plugin_source_root(repo_root)
    plugin_destination = codex_home / "plugins" / "mission-control"
    skills_source_root = _skill_source_root(repo_root)
    skills_destination_root = codex_home / "skills"
    copied_skills: list[str] = []
    plugin_manifest = _read_plugin_manifest(plugin_source)
    plugin_source_exists = plugin_source.exists()

    if not plugin_source_exists or plugin_manifest.get("status") != "ready":
        cache_sync = sync_codex_plugin_cache(plugin_source, codex_home, plugin_manifest, dry_run=dry_run)
        return {
            "codex_home": str(codex_home),
            "plugin_source": str(plugin_source),
            "plugin_source_exists": plugin_source_exists,
            "plugin_destination": str(plugin_destination),
            "plugin_destination_exists_after": plugin_destination.exists(),
            "plugin_files_copied": 0,
            "plugin_manifest": plugin_manifest,
            "plugin_name": plugin_manifest.get("name") or "mission-control",
            "plugin_display_name": plugin_manifest.get("display_name") or "Mission Control",
            "cache_sync": cache_sync,
            "skills_copied": [],
            "skill_count": 0,
            "status": str(plugin_manifest.get("status") or ("missing" if not plugin_source_exists else "invalid")),
            "dry_run": dry_run,
        }

    plugin_files_copied = _copy_tree(plugin_source, plugin_destination, dry_run=dry_run)
    cache_sync = sync_codex_plugin_cache(plugin_source, codex_home, plugin_manifest, dry_run=dry_run)
    if skills_source_root.exists():
        for skill_dir in sorted(path for path in skills_source_root.iterdir() if path.is_dir() and path.name.startswith("mission-control")):
            copied_skills.append(skill_dir.name)
            _copy_tree(skill_dir, skills_destination_root / skill_dir.name, dry_run=dry_run)

    return {
        "codex_home": str(codex_home),
        "plugin_source": str(plugin_source),
        "plugin_source_exists": plugin_source_exists,
        "plugin_destination": str(plugin_destination),
        "plugin_destination_exists_after": dry_run or plugin_destination.exists(),
        "plugin_files_copied": plugin_files_copied,
        "plugin_manifest": plugin_manifest,
        "plugin_name": plugin_manifest.get("name") or "mission-control",
        "plugin_display_name": plugin_manifest.get("display_name") or "Mission Control",
        "cache_sync": cache_sync,
        "skills_copied": copied_skills,
        "skill_count": len(copied_skills),
        "status": "ready",
        "dry_run": dry_run,
    }


def reload_guidance(action: str) -> dict[str, Any]:
    if action == "codex-restart-smoke-status":
        return {
            "required": False,
            "codex": False,
            "claude": False,
            "message": "No app reload is required just to read the latest restart smoke results.",
        }
    requires_reload = action in {"install", "update"}
    if action == "codex-restart-smoke":
        return {
            "required": False,
            "codex": True,
            "claude": False,
            "message": "This workflow force-quits and relaunches Codex for you, then runs the Codex CLI smoke checks in the background.",
        }
    if action == "codex-smoke":
        return {
            "required": False,
            "codex": False,
            "claude": False,
            "message": "No app reload is required just to run the Codex CLI smoke test.",
        }
    if action == "recursive-improvement":
        return {
            "required": False,
            "codex": False,
            "claude": False,
            "message": "No app reload is required to run the recursive improvement workflow because it uses isolated shadow assets and live daemon APIs directly.",
        }
    return {
        "required": requires_reload,
        "codex": requires_reload,
        "claude": requires_reload,
        "message": (
            "Force-quit and reopen Codex and Claude Code before trying to use Mission Control so the updated plugin, MCP registration, and command assets are actually loaded."
            if requires_reload
            else "No app reload is required for uninstall, but already-open Codex or Claude chats may still show stale plugin or tool state until the app is reopened."
        ),
    }


def build_codex_mcp_block(
    repo_root: Path,
    python_command: str,
    *,
    backend_host: str = "127.0.0.1",
    backend_port: int = 8010,
    plugin_id: str | None = None,
) -> str:
    repo_text = _toml_escape(_posix_text(repo_root.resolve()))
    python_text = _toml_escape(_posix_text(Path(python_command).resolve() if Path(python_command).exists() else python_command))
    host_text = _toml_escape(backend_host)
    lines = [
        MANAGED_BLOCK_START,
        '[mcp_servers."mission-control"]',
        f'command = "{python_text}"',
        'args = ["scripts/serve-mission-control-mcp.py"]',
        f'cwd = "{repo_text}"',
        f'env = {{ MISSION_CONTROL_REPO_ROOT = "{repo_text}", MISSION_CONTROL_PYTHON = "{python_text}", MISSION_CONTROL_BACKEND_HOST = "{host_text}", MISSION_CONTROL_BACKEND_PORT = "{backend_port}" }}',
    ]
    if plugin_id:
        escaped_plugin_id = _toml_escape(plugin_id)
        lines.extend(
            [
                "",
                f'[plugins."{escaped_plugin_id}"]',
                "enabled = true",
            ]
        )
    lines.append(MANAGED_BLOCK_END)
    return "\n".join(lines)


def strip_mission_control_config(text: str) -> tuple[str, bool]:
    updated = text.replace("\r\n", "\n")
    changed = False
    managed_pattern = re.compile(
        rf"(?ms)^\s*{re.escape(MANAGED_BLOCK_START)}\n.*?^\s*{re.escape(MANAGED_BLOCK_END)}\s*\n?"
    )
    updated, managed_count = managed_pattern.subn("", updated)
    changed = changed or managed_count > 0

    server_pattern = re.compile(
        r'(?ms)^\[mcp_servers\."mission-control"\]\n(?:^(?!\[).*(?:\n|$))*'
    )
    updated, server_count = server_pattern.subn("", updated)
    changed = changed or server_count > 0

    updated = re.sub(r"\n{3,}", "\n\n", updated).strip()
    if updated:
        updated = f"{updated}\n"
    return updated, changed


def upsert_codex_config(
    codex_home: Path,
    repo_root: Path,
    python_command: str,
    *,
    backend_host: str = "127.0.0.1",
    backend_port: int = 8010,
    plugin_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    config_path = codex_home / "config.toml"
    existing = config_path.read_text(encoding="utf-8", errors="ignore") if config_path.exists() else ""
    stripped, removed = strip_mission_control_config(existing)
    block = build_codex_mcp_block(
        repo_root,
        python_command,
        backend_host=backend_host,
        backend_port=backend_port,
        plugin_id=plugin_id,
    )
    new_text = f"{stripped.rstrip()}\n\n{block}\n" if stripped.strip() else f"{block}\n"
    changed = new_text != existing.replace("\r\n", "\n")
    if not dry_run:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(new_text, encoding="utf-8")
    return {
        "config_path": str(config_path),
        "status": "updated" if changed or removed else "unchanged",
        "changed": changed or removed,
        "dry_run": dry_run,
        "managed_block_present": True,
    }


def remove_codex_config_registration(codex_home: Path, *, dry_run: bool = False) -> dict[str, Any]:
    config_path = codex_home / "config.toml"
    if not config_path.exists():
        return {
            "config_path": str(config_path),
            "status": "missing",
            "changed": False,
            "dry_run": dry_run,
        }
    existing = config_path.read_text(encoding="utf-8", errors="ignore")
    stripped, changed = strip_mission_control_config(existing)
    if changed and not dry_run:
        config_path.write_text(stripped, encoding="utf-8")
    return {
        "config_path": str(config_path),
        "status": "removed" if changed else "unchanged",
        "changed": changed,
        "dry_run": dry_run,
    }


def uninstall_codex_bundle(codex_home: Path, *, dry_run: bool = False) -> dict[str, Any]:
    plugin_path = codex_home / "plugins" / "mission-control"
    plugin_cache_root = _plugin_cache_root(codex_home, "mission-control")
    skills_root = codex_home / "skills"
    removed_skills: list[str] = []
    plugin_removed = False
    cache_removed = False

    if plugin_path.exists():
        plugin_removed = True
        if not dry_run:
            shutil.rmtree(plugin_path)
    if plugin_cache_root.exists():
        cache_removed = True
        if not dry_run:
            shutil.rmtree(plugin_cache_root)
    if skills_root.exists():
        for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir() and path.name.startswith("mission-control")):
            removed_skills.append(skill_dir.name)
            if not dry_run:
                shutil.rmtree(skill_dir)
    config_result = remove_codex_config_registration(codex_home, dry_run=dry_run)
    return {
        "codex_home": str(codex_home),
        "plugin_path": str(plugin_path),
        "plugin_removed": plugin_removed,
        "plugin_cache_root": str(plugin_cache_root),
        "plugin_cache_removed": cache_removed,
        "removed_skills": removed_skills,
        "removed_skill_count": len(removed_skills),
        "config": config_result,
        "status": "ready" if plugin_removed or cache_removed or removed_skills or config_result["changed"] else "not_installed",
        "dry_run": dry_run,
    }


def _probe_python_modules(python_command: str, modules: list[str], *, cwd: Path) -> dict[str, Any]:
    snippet = (
        "import importlib\n"
        f"modules = {modules!r}\n"
        "for name in modules:\n"
        "    importlib.import_module(name)\n"
    )
    command = [python_command, "-c", snippet]
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=30, check=False)
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part).strip()
        return {
            "ready": False,
            "command": command,
            "returncode": None,
            "timed_out": True,
            "output": output[-4000:],
        }
    output = completed.stdout.strip() or completed.stderr.strip()
    return {
        "ready": completed.returncode == 0,
        "command": command,
        "returncode": completed.returncode,
        "timed_out": False,
        "output": output[-4000:],
    }


def ensure_python_packages(repo_root: Path, python_command: str, *, dry_run: bool = False, skip: bool = False) -> list[dict[str, Any]]:
    steps = [
        (
            "backend",
            repo_root / "apps" / "server",
            [python_command, "-m", "pip", "install", "-e", ".[dev]"],
            ["fastapi", "uvicorn", "sqlalchemy", "pydantic", "httpx", "platformdirs", "webview"],
        ),
        (
            "mcp_server",
            repo_root / "apps" / "mcp-server",
            [python_command, "-m", "pip", "install", "-e", "."],
            ["httpx", "platformdirs"],
        ),
    ]
    results: list[dict[str, Any]] = []
    for name, cwd, command, probe_modules in steps:
        if skip:
            results.append({"name": name, "status": "skipped", "command": command, "cwd": str(cwd), "probe_modules": probe_modules})
            continue
        if dry_run:
            results.append({"name": name, "status": "dry_run", "command": command, "cwd": str(cwd), "probe_modules": probe_modules})
            continue
        probe = _probe_python_modules(python_command, probe_modules, cwd=cwd)
        if probe["ready"]:
            results.append(
                {
                    "name": name,
                    "status": "already_satisfied",
                    "command": command,
                    "cwd": str(cwd),
                    "probe_modules": probe_modules,
                    "probe_command": probe["command"],
                    "probe_returncode": probe["returncode"],
                }
            )
            continue
        try:
            completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=600, check=False)
        except subprocess.TimeoutExpired as exc:
            output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part).strip()
            results.append(
                {
                    "name": name,
                    "status": "failed_timeout",
                    "command": command,
                    "cwd": str(cwd),
                    "probe_modules": probe_modules,
                    "probe_command": probe["command"],
                    "probe_returncode": probe["returncode"],
                    "output": output[-4000:],
                    "returncode": None,
                    "timeout_seconds": 600,
                }
            )
            raise RuntimeError(f"{name} dependency installation timed out after 600 seconds.") from exc
        output = completed.stdout.strip() or completed.stderr.strip()
        results.append(
            {
                "name": name,
                "status": "ready" if completed.returncode == 0 else "failed",
                "command": command,
                "cwd": str(cwd),
                "probe_modules": probe_modules,
                "probe_command": probe["command"],
                "probe_returncode": probe["returncode"],
                "output": output[-4000:],
                "returncode": completed.returncode,
            }
        )
        if completed.returncode != 0:
            raise RuntimeError(output or f"{name} dependency installation failed with exit code {completed.returncode}.")
    return results


def run_bootstrap(
    repo_root: Path,
    python_command: str,
    *,
    action: str,
    dry_run: bool = False,
    daemon_host: str | None = None,
    daemon_port: int | None = None,
) -> dict[str, Any]:
    script = repo_root / "scripts" / "mission-control-bootstrap.py"
    command = [python_command, str(script), "--install-path", str(repo_root), "--headless-only", "--json"]
    if dry_run:
        command.append("--dry-run")
    elif action == "update":
        command.append("--repair")
    if daemon_host:
        command.extend(["--daemon-host", daemon_host])
    if daemon_port is not None:
        command.extend(["--daemon-port", str(daemon_port)])
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part).strip()
        return {
            "status": "degraded",
            "command": command,
            "returncode": None,
            "timed_out": True,
            "timeout_seconds": 120,
            "raw_output": output[-4000:],
            "codex_chat_markdown": "Mission Control bootstrap timed out before returning a health report.",
        }
    output = completed.stdout.strip() or completed.stderr.strip()
    payload: dict[str, Any]
    try:
        payload = json.loads(output) if output else {}
    except json.JSONDecodeError:
        payload = {
            "status": "failed" if completed.returncode != 0 else "degraded",
            "raw_output": output,
            "codex_chat_markdown": output,
        }
    payload["command"] = command
    payload["returncode"] = completed.returncode
    return payload


def run_stop_daemon(repo_root: Path, *, env: dict[str, str] | None = None) -> dict[str, Any]:
    script_path = repo_root / "scripts" / ("stop-mission-control-daemon.ps1" if os.name == "nt" else "stop-mission-control-daemon.sh")
    if not script_path.exists():
        return {"status": "missing", "message": f"Stop script not found: {script_path}"}
    if os.name == "nt":
        command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
    else:
        command = ["bash", str(script_path)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False, env=env)
    output = completed.stdout.strip() or completed.stderr.strip()
    return {
        "status": "ready" if completed.returncode == 0 else "degraded",
        "returncode": completed.returncode,
        "message": output or "Daemon stop completed.",
    }


def detect_claude_assets(repo_root: Path) -> dict[str, Any]:
    plugin_root = _plugin_source_root(repo_root)
    required = [
        repo_root / ".mcp.json",
        repo_root / "CLAUDE.md",
        repo_root / ".claude" / "commands" / "mission-control-install.md",
        repo_root / ".claude" / "commands" / "mission-control-update.md",
        repo_root / ".claude" / "commands" / "mission-control-uninstall.md",
        plugin_root / ".claude-plugin" / "plugin.json",
        plugin_root / "commands" / "mission-control.md",
        plugin_root / "commands" / "mission-control-feature-dev.md",
        plugin_root / "commands" / "mission-control-code-review.md",
        plugin_root / "commands" / "mission-control-modernize.md",
        plugin_root / "commands" / "mission-control-security-review.md",
        plugin_root / "agents" / "code-explorer.md",
        plugin_root / "agents" / "code-architect.md",
        plugin_root / "agents" / "code-reviewer.md",
        plugin_root / "agents" / "test-engineer.md",
        plugin_root / "agents" / "security-auditor.md",
    ]
    missing = [str(path.relative_to(repo_root)) for path in required if not path.exists()]
    command_root = plugin_root / "commands"
    agent_root = plugin_root / "agents"
    packaged_commands = sorted(path.stem for path in command_root.glob("*.md")) if command_root.exists() else []
    packaged_agents = sorted(path.stem for path in agent_root.glob("*.md")) if agent_root.exists() else []
    return {
        "status": "ready" if not missing else "degraded",
        "missing": missing,
        "slash_commands": [
            "/mission-control-install",
            "/mission-control-update",
            "/mission-control-uninstall",
        ],
        "plugin_manifest": str(plugin_root / ".claude-plugin" / "plugin.json"),
        "packaged_commands": packaged_commands,
        "packaged_agents": packaged_agents,
        "packaged_command_count": len(packaged_commands),
        "packaged_agent_count": len(packaged_agents),
    }


def _load_server_module(repo_root: Path, module_name: str) -> Any:
    src_root = repo_root / "apps" / "server" / "src"
    module_path = src_root / f"{module_name}.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Server module not found: {module_path}")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(module_name, module)
    existing_path = list(sys.path)
    try:
        sys.path.insert(0, str(src_root))
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = existing_path
    return module


def _safe_state(ok: bool) -> str:
    return "ready" if ok else "degraded"


def _url_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def _probe_backend_health(repo_root: Path) -> dict[str, Any]:
    import urllib.request

    try:
        daemon_state = _load_server_module(repo_root, "daemon_state")
        binding = daemon_state.resolve_backend_binding(prefer_live_metadata=False)
        host = str(binding.get("host") or "127.0.0.1")
        port = int(binding.get("port") or 8010)
    except Exception:
        host = "127.0.0.1"
        port = 8010
    url = f"http://{_url_host(host)}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=3.0) as response:
            body = response.read().decode("utf-8", errors="ignore")
            ready = response.status == 200 and '"ok"' in body
            return {
                "status": "ready" if ready else "degraded",
                "reachable": ready,
                "summary": f"Mission Control daemon health endpoint returned HTTP {response.status}.",
                "url": url,
            }
    except Exception as exc:
        return {
            "status": "degraded",
            "reachable": False,
            "summary": f"Mission Control daemon health endpoint was not reachable: {type(exc).__name__}: {exc}",
            "url": url,
        }


def _probe_mission_control_mcp_stdio(codex_status: dict[str, Any]) -> dict[str, Any]:
    mcp_state = dict(codex_status.get("mcp_state") or {}).get("mission_control") or {}
    live_entry = dict(mcp_state.get("live_entry") or {})
    transport = dict(live_entry.get("transport") or {})
    command = transport.get("command")
    args = [str(item) for item in list(transport.get("args") or [])]
    cwd = transport.get("cwd")
    if not command:
        return {
            "status": "degraded",
            "summary": "Mission Control MCP transport details were not available for a direct stdio handshake probe.",
            "callable": False,
            "tool_count": 0,
            "resource_template_count": 0,
            "prompt_count": 0,
        }
    env = os.environ.copy()
    for key, value in dict(transport.get("env") or {}).items():
        env[str(key)] = str(value)
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "clientInfo": {"name": "mission-control-manage", "version": "1"}, "capabilities": {}},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "resources/templates/list", "params": {}},
        {"jsonrpc": "2.0", "id": 4, "method": "prompts/list", "params": {}},
    ]
    payload = "\n".join(json.dumps(item, default=str) for item in requests) + "\n"
    try:
        completed = subprocess.run(
            [str(command), *args],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=cwd or None,
            env=env,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        return {
            "status": "degraded",
            "summary": f"Mission Control MCP stdio handshake could not be executed: {exc}",
            "callable": False,
            "tool_count": 0,
            "resource_template_count": 0,
            "prompt_count": 0,
        }
    raw_lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    responses: list[dict[str, Any]] = []
    for line in raw_lines:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            responses.append(parsed)
    by_id = {item.get("id"): item for item in responses if item.get("id") is not None}
    init_response = by_id.get(1) or {}
    tools_response = by_id.get(2) or {}
    resources_response = by_id.get(3) or {}
    prompts_response = by_id.get(4) or {}
    tools = list(((tools_response.get("result") or {}).get("tools")) or [])
    resource_templates = list(((resources_response.get("result") or {}).get("resourceTemplates")) or [])
    prompts = list(((prompts_response.get("result") or {}).get("prompts")) or [])
    callable_surface = bool(tools) and any(item.get("name") == "mission_control_get_status" for item in tools)
    init_ok = "result" in init_response and not init_response.get("error")
    if callable_surface and init_ok:
        return {
            "status": "ready",
            "summary": (
                f"Mission Control MCP stdio handshake succeeded with {len(tools)} tools, "
                f"{len(resource_templates)} resource templates, and {len(prompts)} prompts."
            ),
            "callable": True,
            "tool_count": len(tools),
            "resource_template_count": len(resource_templates),
            "prompt_count": len(prompts),
            "sample_tools": [str(item.get('name')) for item in tools[:5]],
            "returncode": completed.returncode,
        }
    stderr_summary = (completed.stderr or "").strip().splitlines()[:3]
    return {
        "status": "degraded",
        "summary": "Mission Control MCP stdio handshake did not return a callable tool surface.",
        "callable": False,
        "tool_count": len(tools),
        "resource_template_count": len(resource_templates),
        "prompt_count": len(prompts),
        "sample_tools": [str(item.get('name')) for item in tools[:5]],
        "returncode": completed.returncode,
        "stderr": stderr_summary,
        "stdout_lines": raw_lines[:6],
    }


def _codex_smoke_checks(codex_status: dict[str, Any], mcp_probe: dict[str, Any], backend_probe: dict[str, Any]) -> list[dict[str, Any]]:
    mcp_state = dict(codex_status.get("mcp_state") or {}).get("mission_control") or {}
    configured = bool(mcp_state.get("configured"))
    app_loaded = mcp_state.get("app_loaded")
    app_loaded_known = app_loaded is not None
    checks = [
        {
            "label": "Codex CLI detected",
            "state": _safe_state(bool(codex_status.get("cli_detected"))),
            "summary": "Codex CLI path was found." if codex_status.get("cli_detected") else "Codex CLI path was not found.",
        },
        {
            "label": "Codex CLI execution available",
            "state": _safe_state(bool(codex_status.get("cli_execution_available"))),
            "summary": (
                "Codex CLI can be executed from this runtime."
                if codex_status.get("cli_execution_available")
                else "Codex CLI path exists, but this runtime cannot execute it directly."
            ),
        },
        {
            "label": "Codex login detectable",
            "state": _safe_state(bool(codex_status.get("authenticated"))),
            "summary": str(codex_status.get("login_status") or "Login state unavailable."),
        },
        {
            "label": "Mission Control MCP configured",
            "state": _safe_state(configured),
            "summary": (
                "Mission Control MCP registration exists in Codex config."
                if configured
                else "Mission Control MCP registration was not found in Codex config."
            ),
        },
        {
            "label": "Mission Control MCP live discovery",
            "state": "ready" if app_loaded is True else "degraded",
            "summary": (
                "Mission Control was discovered in the live Codex MCP server list."
                if app_loaded is True
                else (
                    "Live MCP discovery is unavailable from this runtime, so only config-based verification was possible."
                    if not app_loaded_known
                    else "Mission Control is configured, but it was not discovered in the live Codex MCP server list."
                )
            ),
        },
        {
            "label": "Mission Control MCP callable handshake",
            "state": str(mcp_probe.get("status") or "degraded"),
            "summary": str(mcp_probe.get("summary") or "Mission Control MCP stdio handshake was not probed."),
        },
        {
            "label": "Mission Control daemon reachable",
            "state": str(backend_probe.get("status") or "degraded"),
            "summary": str(backend_probe.get("summary") or "Mission Control daemon health endpoint was not probed."),
        },
    ]
    return checks


def run_codex_smoke(
    repo_root: Path,
    python_command: str,
    *,
    bootstrap: dict[str, Any],
    require_authenticated: bool = True,
) -> dict[str, Any]:
    system_status = _load_server_module(repo_root, "system_status")
    codex_status = dict(system_status.detect_codex_status())
    mcp_probe = _probe_mission_control_mcp_stdio(codex_status)
    backend_probe = _probe_backend_health(repo_root)
    mission_control_state = dict((codex_status.get("mcp_state") or {}).get("mission_control") or {})
    mission_control_state["callable"] = bool(mcp_probe.get("callable"))
    mission_control_state["callable_probe"] = dict(mcp_probe)
    codex_status.setdefault("mcp_state", {})
    codex_status["mcp_state"]["mission_control"] = mission_control_state
    smoke_checks = _codex_smoke_checks(codex_status, mcp_probe, backend_probe)
    bootstrap_status = str(bootstrap.get("status") or "degraded")
    runnable = (
        bool(codex_status.get("cli_detected"))
        and bool(codex_status.get("cli_execution_available"))
        and (bool(codex_status.get("authenticated")) or not require_authenticated)
        and bool(((codex_status.get("mcp_state") or {}).get("mission_control") or {}).get("configured"))
        and bool(mcp_probe.get("callable"))
        and bool(backend_probe.get("reachable"))
    )
    reasons: list[str] = []
    if not codex_status.get("cli_detected"):
        reasons.append("Codex CLI was not detected.")
    elif not codex_status.get("cli_execution_available"):
        reasons.append("Codex CLI exists, but the current runtime cannot execute it directly.")
    if require_authenticated and not codex_status.get("authenticated"):
        reasons.append("Codex login status is not confirmed as authenticated.")
    mcp_state = ((codex_status.get("mcp_state") or {}).get("mission_control") or {})
    if not mcp_state.get("configured"):
        reasons.append("Mission Control MCP is not configured in Codex config.")
    if not mcp_probe.get("callable"):
        reasons.append(str(mcp_probe.get("summary") or "Mission Control MCP handshake did not expose callable tools."))
    if not backend_probe.get("reachable"):
        reasons.append(str(backend_probe.get("summary") or "Mission Control daemon health endpoint was not reachable."))
    if bootstrap_status not in {"ready", "degraded"}:
        reasons.append("Mission Control bootstrap did not complete cleanly.")
    smoke_status = "ready" if runnable else "degraded"
    recommended_command = f"{python_command} scripts/mission-control-manage.py codex-smoke --json"
    if not require_authenticated:
        recommended_command += " --allow-unauthenticated"
    return {
        "codex_status": codex_status,
        "mcp_stdio_probe": mcp_probe,
        "daemon_health_probe": backend_probe,
        "smoke_checks": smoke_checks,
        "smoke_runnable": runnable,
        "smoke_status": smoke_status,
        "smoke_reasons": reasons,
        "require_authenticated": require_authenticated,
        "recommended_command": recommended_command,
    }


def _sanitize_shadow_name(value: str | None) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "shadow").strip().lower()).strip("-")
    return candidate or "shadow"


def _path_text(value: Path | str) -> str:
    return str(Path(value).expanduser().resolve())


def _paths_equal(left: Path | str, right: Path | str) -> bool:
    return _path_text(left).casefold() == _path_text(right).casefold()


def _path_contains(parent: Path | str, child: Path | str) -> bool:
    parent_path = Path(parent).expanduser().resolve()
    child_path = Path(child).expanduser().resolve()
    return child_path == parent_path or parent_path in child_path.parents


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.35)
        try:
            return probe.connect_ex((host, port)) == 0
        except OSError:
            return False


def _controller_binding(repo_root: Path) -> dict[str, Any]:
    daemon_state = _load_server_module(repo_root, "daemon_state")
    binding = daemon_state.resolve_backend_binding(prefer_live_metadata=False)
    token = daemon_state.read_daemon_token()
    host = str(binding.get("host") or "127.0.0.1")
    port = int(binding.get("port") or 8010)
    return {
        "host": host,
        "port": port,
        "mode": str(binding.get("mode") or "web"),
        "base_url": f"http://{_url_host(host)}:{port}",
        "token": token,
    }


def build_recursive_improvement_profile(
    repo_root: Path,
    *,
    shadow_name: str,
    backend_port: int | None = None,
) -> dict[str, Any]:
    controller = _controller_binding(repo_root)
    safe_name = _sanitize_shadow_name(shadow_name)
    shadow_root = (repo_root / ".runtime" / RECURSIVE_IMPROVEMENT_DIR_NAME / safe_name).resolve()
    controller_port = int(controller["port"])
    preferred_port = int(backend_port or (controller_port + 100))
    target_port = preferred_port
    while target_port == controller_port or _port_in_use("127.0.0.1", target_port):
        target_port += 1
    return {
        "shadow_name": safe_name,
        "shadow_root": str(shadow_root),
        "profile_path": str(shadow_root / "profile.json"),
        "target_repo_root": str(shadow_root / "repo"),
        "target_runtime_root": str(shadow_root / "runtime"),
        "target_app_home": str(shadow_root / "app-home"),
        "target_codex_home": str(shadow_root / "codex-home"),
        "target_agents_home": str(shadow_root / "agents-home"),
        "target_launcher_dir": str(shadow_root / "launcher"),
        "target_launcher_config": str(shadow_root / "mission-control.shadow.config.json"),
        "target_backend_host": "127.0.0.1",
        "target_backend_port": target_port,
        "target_transcript_path": str(shadow_root / "target-transcript.md"),
        "controller_transcript_path": str(shadow_root / "controller-transcript.md"),
        "target_install_report_path": str(shadow_root / "target-install.json"),
        "target_smoke_report_path": str(shadow_root / "target-smoke.json"),
        "controller_report_path": str(shadow_root / "controller-run.json"),
        "controller_identity_path": str(shadow_root / "controller-identity.json"),
        "target_identity_path": str(shadow_root / "target-identity.json"),
        "controller_repo_root": str(repo_root.resolve()),
        "controller_base_url": str(controller["base_url"]),
        "controller_host": str(controller["host"]),
        "controller_port": controller_port,
        "created_at": utc_now().isoformat(),
    }


def validate_recursive_improvement_profile(profile: dict[str, Any]) -> None:
    controller_repo = Path(str(profile["controller_repo_root"])).resolve()
    target_repo = Path(str(profile["target_repo_root"])).resolve()
    target_runtime = Path(str(profile["target_runtime_root"])).resolve()
    target_launcher = Path(str(profile["target_launcher_dir"])).resolve()
    shadow_root = Path(str(profile["shadow_root"])).resolve()
    controller_port = int(profile["controller_port"])
    target_port = int(profile["target_backend_port"])
    if _paths_equal(controller_repo, target_repo):
        raise ValueError("Shadow target repo cannot be the same path as the controller repo.")
    if not _path_contains(shadow_root, target_repo):
        raise ValueError("Shadow target repo must live inside the dedicated recursive improvement root.")
    if not _path_contains(shadow_root, target_runtime):
        raise ValueError("Shadow runtime root must live inside the dedicated recursive improvement root.")
    if not _path_contains(shadow_root, target_launcher):
        raise ValueError("Shadow launcher root must live inside the dedicated recursive improvement root.")
    if controller_port == target_port:
        raise ValueError("Shadow backend port must differ from the controller backend port.")


def _shadow_copy_ignore(_dir: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    ignored_names = {
        ".runtime",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "htmlcov",
        ".coverage",
        ".venv",
        "venv",
    }
    for name in names:
        if name in ignored_names or name.endswith((".pyc", ".pyo", ".pyd", ".egg-info")):
            ignored.add(name)
    return ignored


def _mirror_codex_auth_assets(
    source_codex_home: Path,
    target_codex_home: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    source = source_codex_home.expanduser().resolve()
    target = target_codex_home.expanduser().resolve()
    copied: list[str] = []
    missing: list[str] = []
    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)
    for name in RECURSIVE_CODEX_AUTH_FILES:
        source_path = source / name
        if not source_path.exists():
            missing.append(name)
            continue
        copied.append(name)
        if dry_run:
            continue
        shutil.copy2(source_path, target / name)
    return {
        "status": "ready" if copied else "missing",
        "source_codex_home": str(source),
        "target_codex_home": str(target),
        "copied_files": copied,
        "missing_files": missing,
        "dry_run": dry_run,
    }


def _preferred_shadow_branch_name(source_repo_root: Path) -> str | None:
    git_head = source_repo_root / ".git" / "HEAD"
    try:
        if git_head.exists():
            content = git_head.read_text(encoding="utf-8").strip()
            if content.startswith("ref: refs/heads/"):
                branch = content.removeprefix("ref: refs/heads/").strip()
                return branch or None
    except OSError:
        return None
    return None


def _run_shadow_git_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _ensure_shadow_git_repository(
    source_repo_root: Path,
    target_repo: Path,
    *,
    dry_run: bool = False,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    git_dir = target_repo / ".git"
    if git_dir.exists():
        return {
            "status": "ready",
            "git_dir": str(git_dir),
            "already_present": True,
            "initialized": False,
            "dry_run": dry_run,
        }

    git = shutil.which("git") or shutil.which("git.exe")
    branch = _preferred_shadow_branch_name(source_repo_root)
    init_command = [git, "init"] if git else []
    if git and branch:
        init_command = [git, "init", "-b", branch]

    if dry_run:
        return {
            "status": "ready" if git else "missing",
            "git_dir": str(git_dir),
            "already_present": False,
            "initialized": False,
            "dry_run": True,
            "git_command": git,
            "init_command": init_command,
            "branch": branch,
        }

    if not git:
        return {
            "status": "missing",
            "git_dir": str(git_dir),
            "already_present": False,
            "initialized": False,
            "dry_run": False,
            "reason": "git_not_found",
        }

    completed = _run_shadow_git_command(init_command, cwd=target_repo, env=env)
    output = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0 and branch:
        fallback_command = [git, "init"]
        completed = _run_shadow_git_command(fallback_command, cwd=target_repo, env=env)
        output = completed.stdout.strip() or completed.stderr.strip()
        init_command = fallback_command
    if completed.returncode != 0:
        return {
            "status": "failed",
            "git_dir": str(git_dir),
            "already_present": False,
            "initialized": False,
            "dry_run": False,
            "git_command": git,
            "init_command": init_command,
            "branch": branch,
            "returncode": completed.returncode,
            "output": output[-4000:],
        }

    if not git_dir.exists():
        return {
            "status": "failed",
            "git_dir": str(git_dir),
            "already_present": False,
            "initialized": False,
            "dry_run": False,
            "git_command": git,
            "init_command": init_command,
            "branch": branch,
            "returncode": completed.returncode,
            "output": (output or "git init completed without creating a .git directory.")[-4000:],
        }

    return {
        "status": "ready",
        "git_dir": str(git_dir),
        "already_present": False,
        "initialized": True,
        "dry_run": False,
        "git_command": git,
        "init_command": init_command,
        "branch": branch,
        "returncode": completed.returncode,
        "output": output[-4000:],
    }


def prepare_recursive_improvement_shadow(
    repo_root: Path,
    profile: dict[str, Any],
    *,
    dry_run: bool = False,
    recreate: bool = False,
    source_codex_home: Path | None = None,
) -> dict[str, Any]:
    validate_recursive_improvement_profile(profile)
    shadow_root = Path(str(profile["shadow_root"])).resolve()
    target_repo = Path(str(profile["target_repo_root"])).resolve()
    target_codex_home = Path(str(profile["target_codex_home"])).resolve()
    launcher_config_path = Path(str(profile["target_launcher_config"])).resolve()
    source_auth_home = (source_codex_home or resolve_codex_home()).expanduser().resolve()
    target_repo_exists_before = target_repo.exists()
    if recreate and shadow_root.exists() and not dry_run:
        if target_repo.exists():
            run_stop_daemon(target_repo, env=_shadow_env(profile))
        _force_stop_shadow_daemon(profile)
        shutil.rmtree(shadow_root)
    launcher_payload = {
        "host": "127.0.0.1",
        "backendPort": int(profile["target_backend_port"]),
        "frontendPort": 5173,
        "autoOpenBrowser": False,
        "launcherLogDir": str(Path(str(profile["target_launcher_dir"])).resolve()),
    }
    auth_mirror = _mirror_codex_auth_assets(source_auth_home, target_codex_home, dry_run=dry_run)
    if not dry_run:
        shadow_root.mkdir(parents=True, exist_ok=True)
        if not target_repo.exists():
            shutil.copytree(repo_root, target_repo, ignore=_shadow_copy_ignore)
    git_repo = _ensure_shadow_git_repository(repo_root, target_repo, dry_run=dry_run, env=_shadow_env(profile))
    if not dry_run:
        launcher_config_path.write_text(json.dumps(launcher_payload, indent=2), encoding="utf-8")
        Path(str(profile["profile_path"])).write_text(json.dumps(profile, indent=2, default=str), encoding="utf-8")
    return {
        "status": "ready" if str(git_repo.get("status") or "ready") == "ready" else "degraded",
        "shadow_root": str(shadow_root),
        "target_repo_root": str(target_repo),
        "target_repo_exists_before": target_repo_exists_before,
        "target_repo_created": not target_repo_exists_before,
        "git_repository": git_repo,
        "launcher_config_path": str(launcher_config_path),
        "launcher_config": launcher_payload,
        "auth_mirror": auth_mirror,
        "profile_path": str(profile["profile_path"]),
        "dry_run": dry_run,
    }


def _shadow_env(profile: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    env["MISSION_CONTROL_APP_HOME"] = str(profile["target_app_home"])
    env["MISSION_CONTROL_RUNTIME_ROOT"] = str(profile["target_runtime_root"])
    env["MISSION_CONTROL_LAUNCHER_DIR"] = str(profile["target_launcher_dir"])
    env["MISSION_CONTROL_LAUNCHER_CONFIG"] = str(profile["target_launcher_config"])
    env["MISSION_CONTROL_BACKEND_HOST"] = str(profile["target_backend_host"])
    env["MISSION_CONTROL_BACKEND_PORT"] = str(profile["target_backend_port"])
    env["CODEX_HOME"] = str(profile["target_codex_home"])
    env["AGENTS_HOME"] = str(profile["target_agents_home"])
    return env


def _force_stop_shadow_daemon(profile: dict[str, Any]) -> None:
    metadata_path = Path(str(profile["target_launcher_dir"])).resolve() / "daemon.json"
    if not metadata_path.exists():
        return
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    try:
        pid = int(metadata.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, timeout=30, check=False)
        else:
            os.kill(pid, 15)
    except OSError:
        return
    time.sleep(1.0)


def _run_json_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 240,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = completed.stdout.strip() or completed.stderr.strip()
    try:
        payload = json.loads(output) if output else {}
    except json.JSONDecodeError:
        payload = {
            "status": "failed" if completed.returncode else "degraded",
            "raw_output": output,
        }
    payload["command"] = command
    payload["returncode"] = completed.returncode
    return payload


def _write_artifact(path: str | Path, payload: Any) -> None:
    artifact_path = Path(path).expanduser().resolve()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        artifact_path.write_text(payload, encoding="utf-8")
        return
    artifact_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _read_artifact(path: str | Path) -> dict[str, Any] | None:
    artifact_path = Path(path).expanduser().resolve()
    if not artifact_path.exists():
        return None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _orchestration_watch_state_path(repo_root: Path, project_id: int, orchestration_id: int) -> Path:
    return (
        repo_root
        / ".runtime"
        / ORCHESTRATION_WATCH_DIR_NAME
        / f"project-{project_id}-orchestration-{orchestration_id}.json"
    )


def _event_preview(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "unknown").replace("_", " ")
    payload = dict(event.get("payload_json") or {})
    reason = str(payload.get("reason") or "").strip()
    status = str(payload.get("status") or payload.get("orchestration_status") or "").strip()
    parts = [event_type]
    if reason:
        parts.append(f"reason={reason}")
    if status:
        parts.append(f"status={status}")
    return " | ".join(parts)


def _serialize_active_agents(active_agents: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for agent in list(active_agents or []):
        serialized.append(
            {
                "id": agent.get("id"),
                "name": agent.get("name"),
                "status": agent.get("status"),
                "mission": agent.get("mission"),
                "runner_type": agent.get("runner_type"),
                "active_model": agent.get("active_model"),
                "active_reasoning_effort": agent.get("active_reasoning_effort"),
                "current_action": agent.get("current_action"),
                "current_task_title": agent.get("current_task_title"),
            }
        )
    return serialized


def _serialize_manager(manager: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(manager or {})
    if not payload:
        return {}
    return {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "status": payload.get("status"),
        "mission": payload.get("mission"),
        "runner_type": payload.get("runner_type"),
        "active_model": payload.get("active_model"),
        "active_reasoning_effort": payload.get("active_reasoning_effort"),
        "current_action": payload.get("current_action"),
        "current_task_title": payload.get("current_task_title"),
    }


def _orchestration_watch_updates(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    if not previous:
        return ["No previous snapshot existed. Saved the first baseline for future update checks."]

    updates: list[str] = []
    labels = {
        "orchestration_status": "Orchestration status",
        "manager_status": "Manager status",
        "handoff_status": "Handoff status",
        "pending_decisions_count": "Pending decisions",
        "active_agent_count": "Active agents",
    }
    for key, label in labels.items():
        if previous.get(key) != current.get(key):
            updates.append(f"{label} changed: {previous.get(key)!r} -> {current.get(key)!r}")

    if previous.get("active_agents") != current.get("active_agents"):
        before = ", ".join(str(item.get("name")) for item in list(previous.get("active_agents") or [])) or "none"
        after = ", ".join(str(item.get("name")) for item in list(current.get("active_agents") or [])) or "none"
        updates.append(f"Active agent roster changed: {before} -> {after}")

    previous_event_id = int(previous.get("latest_event_id") or 0)
    latest_event_id = int(current.get("latest_event_id") or 0)
    if latest_event_id > previous_event_id:
        new_events = [item for item in list(current.get("recent_events") or []) if int(item.get("id") or 0) > previous_event_id]
        preview = ", ".join(_event_preview(item) for item in new_events[:3]) or "new events recorded"
        updates.append(f"{len(new_events)} new orchestration event(s): {preview}")

    return updates


def _run_orchestration_watch(
    *,
    repo_root: Path,
    project_id: int | None,
    orchestration_id: int | None,
    workspace_path: str | None,
    attach_policy: str,
    event_window: str,
    save_state: bool,
    state_file: str | None,
) -> dict[str, Any]:
    controller = _controller_binding(repo_root)
    token = str(controller.get("token") or "").strip()
    if not token:
        raise RuntimeError("Controller daemon token is missing. Start or repair the daemon before checking orchestration updates.")
    base_url = str(controller["base_url"])
    headers = {"X-Mission-Control-Token": token}

    resume_payload = None
    if workspace_path:
        resume_payload = _http_json(
            "POST",
            f"{base_url}/api/mission-control/resume-workspace",
            headers=headers,
            payload={
                "workspace_path": workspace_path.replace("\\", "/"),
                "attach_policy": attach_policy,
            },
            timeout=60.0,
        )
        project_payload = dict(resume_payload.get("project") or {})
        orchestration_payload = dict(resume_payload.get("orchestration") or {})
        if project_id is None and project_payload.get("id") is not None:
            project_id = int(project_payload["id"])
        if orchestration_id is None and orchestration_payload.get("id") is not None:
            orchestration_id = int(orchestration_payload["id"])

    if project_id is None or orchestration_id is None:
        raise RuntimeError("orchestration-watch needs --project-id and --orchestration-id, or a --workspace-path that resolves to an orchestration.")

    warnings: list[str] = []

    def safe_request(
        label: str,
        method: str,
        url: str,
        *,
        default: Any,
        timeout: float = 8.0,
    ) -> Any:
        try:
            return _http_json(method, url, headers=headers, timeout=timeout)
        except Exception as exc:
            warnings.append(f"{label} request failed: {exc}")
            return default

    default_status = {
        "project_name": (dict(resume_payload.get("project") or {}).get("name") if isinstance(resume_payload, dict) else None) or project_id,
        "orchestration_status": "unknown",
        "manager_status": "Mission Control status request failed.",
        "active_agents": [],
    }
    status = safe_request(
        "status",
        "GET",
        f"{base_url}/api/projects/{project_id}/orchestrations/{orchestration_id}/status",
        default=default_status,
    )
    status_summary = safe_request(
        "status-summary",
        "GET",
        f"{base_url}/api/orchestrations/{orchestration_id}/status-summary?project_id={project_id}",
        default={"fallback_markdown": ""},
    )
    handoff_summary = safe_request(
        "handoff-summary",
        "GET",
        f"{base_url}/api/orchestrations/{orchestration_id}/handoff-summary?project_id={project_id}",
        default={"fallback_markdown": "", "machine_payload_json": {}},
    )
    event_digest = safe_request(
        "event-digest",
        "GET",
        f"{base_url}/api/orchestrations/{orchestration_id}/event-digest?window={event_window}&project_id={project_id}",
        default={"fallback_markdown": ""},
    )
    pending_decisions = safe_request(
        "pending-decisions",
        "GET",
        f"{base_url}/api/orchestrations/{orchestration_id}/pending-decisions?project_id={project_id}",
        default=[],
    ) or []
    events = safe_request(
        "events",
        "GET",
        f"{base_url}/api/orchestrations/{orchestration_id}/events?project_id={project_id}",
        default=[],
    ) or []

    handoff_payload = dict(handoff_summary.get("machine_payload_json") or {})
    active_agents = _serialize_active_agents(status.get("active_agents"))
    manager = _serialize_manager(status.get("manager"))
    latest_event_id = max((int(item.get("id") or 0) for item in list(events)), default=0)
    snapshot = {
        "checked_at": utc_now().isoformat(),
        "project_id": project_id,
        "project_name": status.get("project_name"),
        "orchestration_id": orchestration_id,
        "orchestration_status": status.get("orchestration_status"),
        "manager_status": status.get("manager_status"),
        "manager": manager,
        "handoff_status": handoff_payload.get("status"),
        "pending_decisions_count": len(list(pending_decisions)),
        "active_agent_count": len(active_agents),
        "active_agents": active_agents,
        "latest_event_id": latest_event_id,
        "recent_events": list(events)[-8:],
    }

    resolved_state_path = Path(state_file).expanduser().resolve() if state_file else _orchestration_watch_state_path(repo_root, project_id, orchestration_id)
    previous_snapshot = _read_artifact(resolved_state_path) if save_state else None
    updates = _orchestration_watch_updates(previous_snapshot, snapshot)
    if save_state:
        _write_artifact(resolved_state_path, snapshot)

    recommended_command = (
        f"python scripts/mission-control-manage.py orchestration-watch --project-id {project_id} "
        f"--orchestration-id {orchestration_id}"
    )
    return {
        "status": "degraded" if warnings else "ready",
        "base_url": base_url,
        "project_id": project_id,
        "project_name": status.get("project_name"),
        "orchestration_id": orchestration_id,
        "workspace_path": workspace_path,
        "attach_policy": attach_policy,
        "event_window": event_window,
        "resume_lookup": resume_payload,
        "status_payload": status,
        "manager": manager,
        "status_summary": status_summary,
        "handoff_summary": handoff_summary,
        "event_digest": event_digest,
        "pending_decisions": pending_decisions,
        "events": list(events)[-8:],
        "updates": updates,
        "warnings": warnings,
        "checked_at": snapshot["checked_at"],
        "snapshot_path": str(resolved_state_path),
        "snapshot_saved": save_state,
        "recommended_command": recommended_command,
    }


def _ansi(text: str, code: str, *, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _display_terminal_width() -> int:
    columns = shutil.get_terminal_size((120, 40)).columns
    return max(88, min(columns, 140))


def _display_trim(text: str, width: int) -> str:
    compact = " ".join(str(text or "").split())
    if width <= 3:
        return compact[:width]
    if len(compact) <= width:
        return compact
    return compact[: width - 3] + "..."


def _display_wrap(prefix: str, text: str, width: int) -> list[str]:
    content = " ".join(str(text or "").split())
    if not content:
        return [prefix.rstrip()]
    available = max(10, width - len(prefix))
    wrapped = textwrap.wrap(content, width=available, break_long_words=True, break_on_hyphens=False) or [content]
    lines = [prefix + wrapped[0]]
    indent = " " * len(prefix)
    lines.extend(indent + item for item in wrapped[1:])
    return lines


def _display_section(title: str, lines: list[str], width: int, *, ansi: bool) -> list[str]:
    section_header = _ansi(f"[ {title} ]", "1;36", enabled=ansi)
    output = [section_header]
    if not lines:
        output.append("  (no data)")
    else:
        for line in lines:
            output.extend(_display_wrap("  ", line, width))
    output.append("")
    return output


def _display_visible_len(text: str) -> int:
    return len(re.sub(r"\x1b\[[0-9;]*m", "", str(text or "")))


def _display_pad_visible(text: str, width: int) -> str:
    visible = _display_visible_len(text)
    if visible >= width:
        return text
    return text + (" " * (width - visible))


def _display_join_columns(left: list[str], right: list[str], width: int, *, gap: int = 4) -> list[str]:
    if not right:
        return left
    right_width = max(_display_visible_len(line) for line in right)
    right_width = max(16, min(right_width, width // 2))
    left_width = width - right_width - gap
    if left_width < 32:
        return left + [""] + right
    row_count = max(len(left), len(right))
    left_rows = left + [""] * (row_count - len(left))
    right_rows = right + [""] * (row_count - len(right))
    merged: list[str] = []
    for left_row, right_row in zip(left_rows, right_rows):
        merged.append(_display_pad_visible(_display_trim(left_row, left_width), left_width) + (" " * gap) + right_row)
    return merged


def _status_color(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"running", "ready", "completed", "working", "done", "healthy", "active"}:
        return "1;32"
    if normalized in {"idle", "waiting", "waiting_for_user", "waiting_on_paths", "paused", "needs_review", "degraded"}:
        return "1;33"
    if normalized in {"failed", "broken", "stopped", "stuck", "blocked", "error"}:
        return "1;31"
    if normalized in {"planning", "queued", "not_ready"}:
        return "1;36"
    return "0"


def _status_badge(status: str | None, *, ansi: bool) -> str:
    label = str(status or "unknown").strip() or "unknown"
    return _ansi(label, _status_color(label), enabled=ansi)


def _mission_control_logo_lines(*, ansi: bool) -> list[str]:
    logo = [
        r" __  __  ____ ",
        r"|  \/  |/ ___|",
        r"| |\/| | |    ",
        r"| |  | | |___ ",
        r"|_|  |_|\____|",
        r"MISSION CONTROL",
    ]
    if not ansi:
        return logo
    return [_ansi(line, "1;35", enabled=True) for line in logo]


def _display_card_lines(title: str, lines: list[str], width: int, *, ansi: bool) -> list[str]:
    inner_width = max(24, width - 4)
    border = "+" + ("-" * (inner_width + 2)) + "+"
    title_text = f" {title} "
    title_visible = min(len(title_text), inner_width)
    title_line = "|" + title_text[:title_visible].ljust(inner_width + 2, "-") + "|"
    output = [border, _ansi(title_line, "1;36", enabled=ansi)]
    content_lines = lines or ["(no data)"]
    for content in content_lines:
        compact = " ".join(str(content or "").split())
        wrapped = textwrap.wrap(compact, width=inner_width, break_long_words=True, break_on_hyphens=False) or [""]
        for wrapped_line in wrapped:
            output.append("| " + _display_pad_visible(wrapped_line, inner_width) + " |")
    output.append(border)
    return output


def _event_preview_display(event: dict[str, Any]) -> str:
    event_id = event.get("id")
    event_type = str(event.get("event_type") or event.get("type") or "event")
    summary = _event_preview(event)
    if summary == event_type:
        return f"#{event_id} {event_type}"
    return f"#{event_id} {summary}"


def _manager_focus_lines(payload: dict[str, Any]) -> list[str]:
    status_payload = dict(payload.get("status_payload") or {})
    status_summary = dict(payload.get("status_summary") or {})
    machine_payload = dict(status_summary.get("machine_payload_json") or {})
    lines: list[str] = []
    manager_status = str(status_payload.get("manager_status") or payload.get("manager_status") or "").strip()
    if manager_status:
        lines.append(f"Status: {manager_status}")
    next_step = str(machine_payload.get("next_expected_step") or status_payload.get("next_expected_action") or "").strip()
    if next_step:
        lines.append(f"Next: {next_step}")
    for item in list(machine_payload.get("current_work") or [])[:4]:
        compact = " ".join(str(item or "").split())
        if compact:
            lines.append(f"Focus: {compact}")
    blockers = list(machine_payload.get("current_blockers") or status_payload.get("current_blockers") or [])[:2]
    for blocker in blockers:
        compact = " ".join(str(blocker or "").split())
        if compact:
            lines.append(f"Blocker: {compact}")
    return lines


def _agent_focus(agent: dict[str, Any]) -> str:
    return str(
        agent.get("current_action")
        or agent.get("current_task_title")
        or agent.get("mission")
        or agent.get("status")
        or "No active focus recorded."
    )


def _manager_identity(manager: dict[str, Any]) -> str:
    name = str(manager.get("name") or "Manager")
    runner = str(manager.get("runner_type") or "unknown")
    model = str(manager.get("active_model") or "unknown")
    status = str(manager.get("status") or "unknown")
    return f"{name} | runner={runner} | model={model} | status={status}"


def _agent_identity(agent: dict[str, Any]) -> str:
    name = str(agent.get("name") or f"Agent {agent.get('id') or '?'}")
    runner = str(agent.get("runner_type") or "unknown")
    model = str(agent.get("active_model") or "unknown")
    status = str(agent.get("status") or "unknown")
    return f"{name} | runner={runner} | model={model} | status={status}"


def _manager_card_lines(payload: dict[str, Any], manager: dict[str, Any], *, ansi: bool) -> list[str]:
    name = str(manager.get("name") or "Mission Control Manager")
    runner = str(manager.get("runner_type") or "unknown")
    model = str(manager.get("active_model") or "unknown")
    status = str(manager.get("status") or "unknown")
    lines = [
        f"Manager: {name}",
        f"Runner: {runner} | Model: {model} | Status: {_status_badge(status, ansi=ansi)}",
    ]
    for item in _manager_focus_lines(payload)[:5]:
        lines.append(item)
    return lines


def _agent_card_lines(agent: dict[str, Any], *, ansi: bool) -> list[str]:
    name = str(agent.get("name") or f"Agent {agent.get('id') or '?'}")
    runner = str(agent.get("runner_type") or "unknown")
    model = str(agent.get("active_model") or "unknown")
    status = str(agent.get("status") or "unknown")
    lines = [
        f"Agent: {name}",
        f"Runner: {runner} | Model: {model} | Status: {_status_badge(status, ansi=ansi)}",
    ]
    task_title = str(agent.get("current_task_title") or "").strip()
    if task_title:
        lines.append(f"Current task: {task_title}")
    lines.append(f"Focus: {_agent_focus(agent)}")
    mission = str(agent.get("mission") or "").strip()
    if mission and mission.lower() not in str(_agent_focus(agent)).lower():
        lines.append(f"Mission: {mission}")
    return lines


def _build_orchestration_display_frame(
    payload: dict[str, Any],
    *,
    frame_index: int = 0,
    ansi: bool = True,
    runtime: dict[str, Any] | None = None,
) -> str:
    width = _display_terminal_width()
    spinner = "|/-\\"[frame_index % 4]
    status_payload = dict(payload.get("status_payload") or {})
    manager = dict(payload.get("manager") or status_payload.get("manager") or {})
    status_summary = dict(payload.get("status_summary") or {})
    handoff_summary = dict(payload.get("handoff_summary") or {})
    handoff_machine = dict(handoff_summary.get("machine_payload_json") or {})
    pending = list(payload.get("pending_decisions") or [])
    active_agents = list(status_payload.get("active_agents") or [])
    events = list(payload.get("events") or [])
    warnings = list(payload.get("warnings") or [])
    current_status = str(status_payload.get("orchestration_status") or payload.get("status") or "unknown")
    handoff_status = str(handoff_machine.get("status") or "unknown")
    checked_at = str(payload.get("checked_at") or utc_now().isoformat())
    runtime = dict(runtime or {})
    header_status = _ansi(current_status.upper(), _status_color(current_status), enabled=ansi)
    handoff_badge = _ansi(handoff_status.upper(), _status_color(handoff_status), enabled=ansi)
    data_age_seconds = runtime.get("data_age_seconds")
    cadence = runtime.get("refresh_seconds")
    fetch_state = "polling" if runtime.get("fetch_in_progress") else "idle"
    fetch_count = runtime.get("fetch_count")
    cadence_text = f"{float(cadence):0.1f}s" if cadence is not None else "n/a"
    render_summary = (
        f"Updated: {checked_at} | Status: {header_status} | Pending decisions: {len(pending)} | Active agents: {len(active_agents)} | Handoff: {handoff_badge}"
    )
    if data_age_seconds is not None:
        render_summary += f" | Data age: {float(data_age_seconds):0.1f}s"

    header_left = [
        f"{spinner} MISSION CONTROL LIVE",
        f"Project: {payload.get('project_name') or payload.get('project_id')}",
        f"Orchestration: {payload.get('orchestration_id')} | Status: {header_status}",
        f"Pending decisions: {len(pending)} | Active agents: {len(active_agents)} | Handoff: {handoff_badge}",
    ]
    if data_age_seconds is not None:
        header_left.append(f"Snapshot age: {float(data_age_seconds):0.1f}s | Updated: {checked_at}")
    else:
        header_left.append(f"Updated: {checked_at}")
    header_left.append(f"Workspace: {payload.get('workspace_path') or 'n/a'}")
    header_left.append(f"Event window: {payload.get('event_window')}")

    lines = [_ansi("=" * width, "2", enabled=ansi)]
    lines.extend(_display_join_columns(header_left, _mission_control_logo_lines(ansi=ansi), width))
    lines.extend(
        [
            _ansi("=" * width, "2", enabled=ansi),
            _display_trim(render_summary, width),
            "",
            _ansi("[ Manager ]", "1;36", enabled=ansi),
        ]
    )
    lines.extend(_display_card_lines("Manager Bridge", _manager_card_lines(payload, manager, ansi=ansi), width, ansi=ansi))
    lines.append("")

    lines.append(_ansi("[ Agents ]", "1;36", enabled=ansi))
    if not active_agents:
        lines.extend(_display_card_lines("Agent Lane", ["No active worker agents were returned."], width, ansi=ansi))
    else:
        for agent in active_agents[:8]:
            agent_title = str(agent.get("name") or f"Agent {agent.get('id') or '?'}")
            lines.extend(_display_card_lines(agent_title, _agent_card_lines(agent, ansi=ansi), width, ansi=ansi))
            lines.append("")

    event_lines = [_event_preview_display(event) for event in events[-6:]]
    if not event_lines:
        event_lines = ["No recent orchestration events were returned."]
    lines.extend(_display_section("Event Pulse", event_lines, width, ansi=ansi))

    meta_lines = [
        f"Repeat command: {payload.get('recommended_command')}",
        f"Snapshot file: {payload.get('snapshot_path') if payload.get('snapshot_saved') else 'not saved'}",
        f"Render cadence: {cadence_text} | Fetch state: {fetch_state} | Fetch count: {fetch_count or 0}",
    ]
    if runtime.get("last_fetch_duration_seconds") is not None:
        meta_lines.append(f"Last fetch duration: {float(runtime['last_fetch_duration_seconds']):0.2f}s")
    if runtime.get("last_error"):
        meta_lines.append(f"Last fetch error: {runtime['last_error']}")
    for warning in warnings[:3]:
        meta_lines.append(f"Warning: {warning}")
    lines.extend(_display_section("Runtime Notes", meta_lines, width, ansi=ansi))

    lines.append(_ansi(_display_trim("Press Ctrl+C to stop the live display.", width), "2", enabled=ansi))
    return "\n".join(lines)


def _build_orchestration_display_waiting_frame(
    *,
    project_id: int | None,
    orchestration_id: int | None,
    workspace_path: str | None,
    refresh_seconds: float,
    frame_index: int,
    ansi: bool,
    last_error: str | None = None,
    fetch_count: int = 0,
) -> str:
    width = _display_terminal_width()
    spinner = "|/-\\"[frame_index % 4]
    header_left = [
        f"{spinner} MISSION CONTROL LIVE",
        "Waiting for first daemon snapshot",
        f"Project: {project_id or 'unknown'}",
        f"Orchestration: {orchestration_id or '?'}",
        f"Render cadence: {refresh_seconds:0.1f}s | Fetch count: {fetch_count}",
        f"Workspace: {workspace_path or 'n/a'}",
    ]
    lines = [_ansi("=" * width, "2", enabled=ansi)]
    lines.extend(_display_join_columns(header_left, _mission_control_logo_lines(ansi=ansi), width))
    lines.extend([_ansi("=" * width, "2", enabled=ansi), ""])
    waiting_lines = [
        "Mission Control is polling the daemon for the first live status snapshot.",
        f"Completed fetch attempts: {fetch_count}",
    ]
    if last_error:
        waiting_lines.append(f"Last fetch error: {last_error}")
    lines.extend(_display_section("Waiting", waiting_lines, width, ansi=ansi))
    lines.append(_ansi(_display_trim("Press Ctrl+C to stop the live display.", width), "2", enabled=ansi))
    return "\n".join(lines)


def _run_orchestration_display(
    *,
    repo_root: Path,
    project_id: int | None,
    orchestration_id: int | None,
    workspace_path: str | None,
    attach_policy: str,
    event_window: str,
    save_state: bool,
    state_file: str | None,
    frame_index: int,
    ansi: bool,
) -> dict[str, Any]:
    payload = _run_orchestration_watch(
        repo_root=repo_root,
        project_id=project_id,
        orchestration_id=orchestration_id,
        workspace_path=workspace_path,
        attach_policy=attach_policy,
        event_window=event_window,
        save_state=save_state,
        state_file=state_file,
    )
    payload["display_frame"] = _build_orchestration_display_frame(payload, frame_index=frame_index, ansi=ansi)
    payload["display_command"] = (
        f"python scripts/mission-control-manage.py orchestration-display --project-id {payload.get('project_id')} "
        f"--orchestration-id {payload.get('orchestration_id')}"
    )
    return payload


def _invoke_shadow_manage_action(
    profile: dict[str, Any],
    python_command: str,
    *,
    action: str,
    skip_python_setup: bool,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    repo_root = Path(str(profile["target_repo_root"])).resolve()
    command = [
        python_command,
        str(repo_root / "scripts" / "mission-control-manage.py"),
        action,
        "--install-dir",
        str(repo_root),
        "--codex-home",
        str(profile["target_codex_home"]),
        "--agents-home",
        str(profile["target_agents_home"]),
        "--python-command",
        python_command,
        "--daemon-port",
        str(profile["target_backend_port"]),
        "--json",
    ]
    if skip_python_setup:
        command.append("--skip-python-setup")
    if extra_args:
        command.extend(extra_args)
    timeout = 900 if action in {"install", "update"} else 360
    return _run_json_command(command, cwd=repo_root, env=_shadow_env(profile), timeout=timeout)


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> Any:
    import urllib.error
    import urllib.request

    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"{method.upper()} {url} failed with HTTP {exc.code}: {detail}") from exc
    if not body.strip():
        return None
    return json.loads(body)


def _daemon_identity_snapshot(base_url: str, token: str) -> dict[str, Any]:
    return _http_json("GET", f"{base_url}/api/diagnostics/identity", headers={"X-Mission-Control-Token": token})


def _run_headless_happy_path(
    *,
    base_url: str,
    token: str,
    workspace_path: str,
    task_request: str,
    transcript_path: str,
    project_name: str,
    mode: str = "dry_run",
) -> dict[str, Any]:
    headers = {"X-Mission-Control-Token": token}
    sections: list[str] = []
    decision_attempts = 0
    max_decision_loops = 5

    def add_section(title: str, content: str) -> None:
        sections.append("\n".join([f"## {title}", "", "```text", content, "```"]))

    def answer_pending_decision(decision: dict[str, Any]) -> str:
        nonlocal answered_option_id, decision_attempts
        decision_id = int(decision["id"])
        bridge_message = _http_json(
            "GET",
            f"{base_url}/api/decisions/{decision_id}/bridge-message?project_id={project_id}",
            headers=headers,
            timeout=60.0,
        )
        add_section("PENDING DECISION", str(bridge_message["fallback_markdown"]))
        recommended_option = decision.get("recommended_option")
        selected = next((item for item in list(decision.get("options") or []) if item.get("id") == recommended_option), None)
        if selected is None:
            selected = (list(decision.get("options") or []) or [{"id": "approve_once", "label": "Approve once"}])[0]
        answered_option_id = str(selected["id"])
        answered = _http_json(
            "POST",
            f"{base_url}/api/decisions/{decision_id}/answer?project_id={project_id}",
            headers=headers,
            timeout=120.0,
            payload={"option_id": answered_option_id, "selected_text": selected.get("label")},
        )
        decision_attempts += 1
        return str(answered["next_status_summary"]["fallback_markdown"])

    attach = _http_json(
        "POST",
        f"{base_url}/api/headless/attach-workspace",
        headers=headers,
        timeout=90.0,
        payload={
            "workspace_path": workspace_path.replace("\\", "/"),
            "project_name": project_name,
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    project_id = int(attach["project"]["id"])
    add_section("ATTACH WORKSPACE", json.dumps(attach, indent=2))
    requested_mode = str(mode or "dry_run").strip().lower()

    if requested_mode != "dry_run" and str(attach.get("source_type") or "") == "existing_folder":
        interview = _http_json(
            "POST",
            f"{base_url}/api/projects/{project_id}/import/interview-choice",
            headers=headers,
            timeout=60.0,
            payload={"choice": "skip"},
        )
        add_section("IMPORT INTERVIEW", json.dumps(interview, indent=2))

        safety = _http_json(
            "PATCH",
            f"{base_url}/api/projects/{project_id}/import-safety",
            headers=headers,
            timeout=60.0,
            payload={
                "write_permission_status": "write_allowed",
                "require_snapshot_before_edits": False,
                "require_approval_for_dependency_changes": True,
                "require_approval_for_test_commands": False,
                "require_approval_for_build_commands": False,
                "require_approval_for_formatting": False,
                "require_approval_for_package_file_changes": True,
                "destructive_commands_blocked": True,
            },
        )
        add_section("IMPORT SAFETY", json.dumps(safety, indent=2))

        settings = _http_json(
            "PUT",
            f"{base_url}/api/projects/{project_id}/settings",
            headers=headers,
            timeout=60.0,
            payload={
                "provider": "codex",
                "runner_mode": "cli",
                "sandbox_mode": "workspace-write",
                "approval_policy": "on-request",
            },
        )
        add_section("PROJECT SETTINGS", json.dumps(settings, indent=2))

    start = _http_json(
        "POST",
        f"{base_url}/api/headless/start-task",
        headers=headers,
        timeout=180.0,
        payload={
            "project_id": project_id,
            "user_request": task_request,
            "strategy": "balanced",
            "mode": mode,
            "interview_mode": "skip",
            "attach_policy": "reuse_existing",
        },
    )
    orchestration = dict(start["orchestration"])
    orchestration_id = int(orchestration["id"])
    add_section("START TASK", json.dumps(orchestration, indent=2))
    add_section("STATUS SUMMARY", str(start["status_summary"]["fallback_markdown"]))
    actual_mode = str(start.get("mode_used") or orchestration.get("mode") or "").strip().lower()
    orchestration_metadata = dict(orchestration.get("metadata_json") or {})
    simulated = bool(orchestration_metadata.get("simulated"))
    real_runner_failure_reason = None
    if requested_mode != "dry_run":
        if actual_mode != requested_mode:
            real_runner_failure_reason = (
                f"Expected Mission Control to use {requested_mode}, but it resolved to {actual_mode or 'unknown'}."
            )
        elif simulated:
            real_runner_failure_reason = "Mission Control reported a simulated orchestration for a live Codex CLI request."

    pending = list(start.get("pending_decisions") or [])
    final_status_summary = str(start["status_summary"]["fallback_markdown"])
    answered_option_id = None
    for _ in range(max_decision_loops):
        if not pending:
            break
        decision = next((item for item in pending if item.get("decision_type") == "command_approval"), pending[0])
        final_status_summary = answer_pending_decision(decision)
        add_section("NEXT STATUS", final_status_summary)
        pending = list(
            _http_json(
                "GET",
                f"{base_url}/api/orchestrations/{orchestration_id}/pending-decisions?project_id={project_id}",
                headers=headers,
                timeout=60.0,
            )
            or []
        )

    final_orchestration = dict(orchestration)
    completed = False
    for _ in range(180):
        final_orchestration = dict(
            _http_json(
                "GET",
                f"{base_url}/api/orchestrations/{orchestration_id}?project_id={project_id}",
                headers=headers,
                timeout=60.0,
            )
        )
        status_summary = _http_json(
            "GET",
            f"{base_url}/api/orchestrations/{orchestration_id}/status-summary?project_id={project_id}",
            headers=headers,
            timeout=60.0,
        )
        final_status_summary = str(status_summary["fallback_markdown"])
        pending = list(
            _http_json(
                "GET",
                f"{base_url}/api/orchestrations/{orchestration_id}/pending-decisions?project_id={project_id}",
                headers=headers,
                timeout=60.0,
            )
            or []
        )
        if pending:
            if decision_attempts >= max_decision_loops:
                break
            decision = next((item for item in pending if item.get("decision_type") == "command_approval"), pending[0])
            final_status_summary = answer_pending_decision(decision)
            add_section("NEXT STATUS", final_status_summary)
            time.sleep(1.0)
            continue
        if str(final_orchestration.get("status") or "").strip().lower() == "completed":
            completed = True
            break
        time.sleep(1.0)

    digest = _http_json(
        "GET",
        f"{base_url}/api/orchestrations/{orchestration_id}/event-digest?window=since_orchestration_start&project_id={project_id}",
        headers=headers,
        timeout=90.0,
    )
    add_section("EVENT DIGEST", str(digest["fallback_markdown"]))

    handoff = _http_json(
        "GET",
        f"{base_url}/api/orchestrations/{orchestration_id}/handoff-summary?project_id={project_id}",
        headers=headers,
        timeout=90.0,
    )
    add_section("HANDOFF SUMMARY", str(handoff["fallback_markdown"]))
    digest_markdown = str(digest.get("fallback_markdown") or "")
    handoff_markdown = str(handoff.get("fallback_markdown") or "")
    if requested_mode != "dry_run" and real_runner_failure_reason is None:
        lowered_evidence = "\n".join(
            [
                str(final_status_summary or ""),
                digest_markdown,
                handoff_markdown,
            ]
        ).lower()
        if "dry-run orchestration" in lowered_evidence or "dry run validation simulated" in lowered_evidence or "based on simulated execution" in lowered_evidence:
            real_runner_failure_reason = "Mission Control produced simulated dry-run evidence during a live Codex CLI request."

    audit_log = _http_json("GET", f"{base_url}/api/projects/{project_id}/security/audit-log", headers=headers, timeout=60.0)
    audit_preview = "\n".join(
        f"{entry['created_at']} | {entry['decision']} | {entry['action_type']} | {entry['action_summary']}"
        for entry in list(audit_log or [])[:5]
    ) or "No approval audit entries were recorded."
    add_section("APPROVAL AUDIT LOG", audit_preview)

    transcript = "\n\n".join(
        [
            "# Headless Terminal Transcript",
            "",
            f"Generated at: {utc_now().isoformat()}",
            f"Workspace path: {workspace_path}",
            f"Task request: {task_request}",
            "",
            *sections,
        ]
    )
    _write_artifact(transcript_path, transcript)
    return {
        "status": (
            "ready"
            if (completed or mode == "dry_run") and not pending and real_runner_failure_reason is None
            else "degraded"
        ),
        "base_url": base_url,
        "project_id": project_id,
        "orchestration_id": orchestration_id,
        "attach_outcome": attach.get("attach_outcome"),
        "answered_option_id": answered_option_id,
        "audit_entry_count": len(list(audit_log or [])),
        "handoff_message_type": handoff.get("message_type"),
        "transcript_path": transcript_path,
        "project_name": attach.get("project_name") or project_name,
        "status_summary_markdown": final_status_summary,
        "final_orchestration_status": final_orchestration.get("status"),
        "pending_decision_count": len(pending),
        "mode_used": mode,
        "resolved_mode": actual_mode or None,
        "simulated": simulated,
        "real_runner_verified": real_runner_failure_reason is None if requested_mode != "dry_run" else True,
        "real_runner_failure_reason": real_runner_failure_reason,
    }


def run_recursive_improvement_workflow(
    *,
    repo_root: Path,
    python_command: str,
    shadow_name: str,
    backend_port: int | None,
    skip_python_setup: bool,
    recreate_shadow: bool,
    controller_mode: str,
    controller_task_request: str | None,
) -> dict[str, Any]:
    profile = build_recursive_improvement_profile(repo_root, shadow_name=shadow_name, backend_port=backend_port)
    try:
        prepare = prepare_recursive_improvement_shadow(
            repo_root,
            profile,
            recreate=recreate_shadow,
            dry_run=False,
            source_codex_home=resolve_codex_home(),
        )
    except PermissionError:
        fallback_name = f"{shadow_name}-{utc_now().strftime('%Y%m%d-%H%M%S')}"
        profile = build_recursive_improvement_profile(repo_root, shadow_name=fallback_name, backend_port=backend_port)
        prepare = prepare_recursive_improvement_shadow(
            repo_root,
            profile,
            recreate=False,
            dry_run=False,
            source_codex_home=resolve_codex_home(),
        )
        prepare["recreate_fallback"] = True

    install = _invoke_shadow_manage_action(
        profile,
        python_command,
        action="install",
        skip_python_setup=True,
    )
    _write_artifact(profile["target_install_report_path"], install)

    smoke = _invoke_shadow_manage_action(
        profile,
        python_command,
        action="codex-smoke",
        skip_python_setup=True,
    )
    _write_artifact(profile["target_smoke_report_path"], smoke)

    controller = _controller_binding(repo_root)
    if not controller.get("token"):
        raise RuntimeError("Controller daemon token is missing. Start or repair the controller daemon before running recursive improvement.")
    controller_identity = _daemon_identity_snapshot(str(controller["base_url"]), str(controller["token"]))
    _write_artifact(profile["controller_identity_path"], controller_identity)

    target_token_path = Path(str(profile["target_runtime_root"])) / "daemon.token"
    if not target_token_path.exists():
        raise RuntimeError("Shadow target daemon token was not created. The target install did not produce a runnable daemon.")
    target_token = target_token_path.read_text(encoding="utf-8").strip()
    target_base_url = f"http://{_url_host(str(profile['target_backend_host']))}:{int(profile['target_backend_port'])}"
    target_identity = _daemon_identity_snapshot(target_base_url, target_token)
    _write_artifact(profile["target_identity_path"], target_identity)

    if not bool(smoke.get("smoke_runnable")) or not bool((smoke.get("codex_status") or {}).get("authenticated")):
        raise RuntimeError("Recursive improvement shadow is not ready for authenticated Codex CLI execution.")

    default_request = (
        "Use Mission Control for this repo with real Codex CLI agents, surface the necessary approval flow, and produce a handoff plus approval log for recursive improvement."
    )
    task_request = controller_task_request or default_request
    target_happy_path = _run_headless_happy_path(
        base_url=target_base_url,
        token=target_token,
        workspace_path=str(profile["target_repo_root"]),
        task_request=task_request,
        transcript_path=str(profile["target_transcript_path"]),
        project_name=f"mission-control-target-{profile['shadow_name']}",
        mode="codex_cli",
    )
    controller_happy_path = _run_headless_happy_path(
        base_url=str(controller["base_url"]),
        token=str(controller["token"]),
        workspace_path=str(profile["target_repo_root"]),
        task_request=task_request,
        transcript_path=str(profile["controller_transcript_path"]),
        project_name=f"mission-control-controller-{profile['shadow_name']}",
        mode=controller_mode,
    )
    _write_artifact(profile["controller_report_path"], controller_happy_path)

    isolated = (
        str(controller_identity.get("repo_root") or "").casefold() != str(target_identity.get("repo_root") or "").casefold()
        and int(controller_identity.get("port") or 0) != int(target_identity.get("port") or 0)
    )
    status = "ready"
    for step in (install, smoke, target_happy_path, controller_happy_path):
        if str(step.get("status") or "degraded") not in {"ready", "degraded"}:
            status = "failed"
            break
        if str(step.get("status") or "degraded") == "degraded":
            status = "degraded"
    if not isolated:
        status = "failed"

    return {
        "status": status,
        "shadow_profile": profile,
        "shadow_prepare": prepare,
        "shadow_install": install,
        "shadow_smoke": smoke,
        "controller_identity": controller_identity,
        "target_identity": target_identity,
        "target_happy_path": target_happy_path,
        "controller_happy_path": controller_happy_path,
        "collision_guard": {
            "isolated": isolated,
            "controller_repo_root": controller_identity.get("repo_root"),
            "target_repo_root": target_identity.get("repo_root"),
            "controller_port": controller_identity.get("port"),
            "target_port": target_identity.get("port"),
        },
    }


def launch_codex_restart_smoke(
    repo_root: Path,
    python_command: str,
    *,
    launch_wait_seconds: int = 25,
) -> dict[str, Any]:
    script_path = repo_root / "scripts" / "restart-codex-and-smoke.ps1"
    if not script_path.exists():
        raise FileNotFoundError(f"Restart script not found: {script_path}")
    job_root = repo_root / ".runtime" / "codex-restart-smoke"
    job_root.mkdir(parents=True, exist_ok=True)
    results_path = job_root / "latest.json"
    log_path = job_root / "latest.log"
    powershell = shutil.which("powershell.exe") or "powershell.exe"
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-RepoRoot",
        str(repo_root),
        "-PythonCommand",
        python_command,
        "-ResultsPath",
        str(results_path),
        "-LogPath",
        str(log_path),
        "-LaunchWaitSeconds",
        str(launch_wait_seconds),
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = 0x00000008 | 0x00000200 | 0x08000000
    process = subprocess.Popen(
        command,
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )
    return {
        "status": "launched",
        "launcher_pid": process.pid,
        "script_path": str(script_path),
        "results_path": str(results_path),
        "log_path": str(log_path),
        "launch_wait_seconds": launch_wait_seconds,
        "recommended_resume_minutes": max(2, int((launch_wait_seconds + 95) / 60) + 1),
        "command": command,
    }


def load_codex_restart_smoke_status(repo_root: Path) -> dict[str, Any]:
    results_path = repo_root / ".runtime" / "codex-restart-smoke" / "latest.json"
    log_path = repo_root / ".runtime" / "codex-restart-smoke" / "latest.log"
    if not results_path.exists():
        return {
            "status": "missing",
            "results_path": str(results_path),
            "log_path": str(log_path),
            "summary": "No restart smoke result artifact exists yet.",
        }
    try:
        payload = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "failed",
            "results_path": str(results_path),
            "log_path": str(log_path),
            "summary": f"Restart smoke artifact could not be parsed: {exc}",
        }

    smoke = payload.get("smoke") if isinstance(payload, dict) else None
    smoke_status = None
    if isinstance(smoke, dict):
        smoke_status = smoke.get("status")
    return {
        "status": str(payload.get("status") or smoke_status or "unknown"),
        "results_path": str(results_path),
        "log_path": str(log_path),
        "artifact": payload,
        "summary": (
            f"Restart smoke completed with status {payload.get('status') or smoke_status or 'unknown'}."
            if isinstance(payload, dict)
            else "Restart smoke artifact loaded."
        ),
    }


def _install_or_update(
    *,
    action: str,
    repo_root: Path,
    codex_home: Path,
    agents_home: Path,
    python_command: str,
    dry_run: bool,
    skip_python_setup: bool,
    skip_codex_sync: bool,
    daemon_host: str | None,
    daemon_port: int | None,
) -> dict[str, Any]:
    dependency_setup = ensure_python_packages(repo_root, python_command, dry_run=dry_run, skip=skip_python_setup)
    marketplace_result = {"status": "skipped"} if skip_codex_sync else sync_local_plugin_marketplace(repo_root, agents_home, dry_run=dry_run)
    sync_result = {"status": "skipped"} if skip_codex_sync else sync_codex_bundle(repo_root, codex_home, dry_run=dry_run)
    config_result = {"status": "skipped"} if skip_codex_sync else upsert_codex_config(
        codex_home,
        repo_root,
        python_command,
        backend_host=daemon_host or "127.0.0.1",
        backend_port=daemon_port or 8010,
        plugin_id=marketplace_result.get("plugin_id"),
        dry_run=dry_run,
    )
    bootstrap_result = run_bootstrap(
        repo_root,
        python_command,
        action=action,
        dry_run=dry_run,
        daemon_host=daemon_host,
        daemon_port=daemon_port,
    )
    return {
        "dependency_setup": dependency_setup,
        "marketplace_sync": marketplace_result,
        "codex_sync": sync_result,
        "codex_config": config_result,
        "bootstrap": bootstrap_result,
    }


def _normalize_workflow_status(raw_status: Any) -> str:
    status = str(raw_status or "degraded")
    if status == "skipped":
        return "skipped"
    if status in {"failed", "error", "invalid"}:
        return "failed"
    if status in {"degraded", "missing"}:
        return "degraded"
    return "ready"


def _combine_management_status(*steps: dict[str, Any]) -> str:
    statuses = [_normalize_workflow_status(step.get("status")) for step in steps if isinstance(step, dict)]
    active_statuses = [status for status in statuses if status != "skipped"]
    if not active_statuses:
        return "ready"
    if any(status == "failed" for status in active_statuses):
        return "failed"
    if any(status == "degraded" for status in active_statuses):
        return "degraded"
    return "ready"


def _build_markdown(action: str, payload: dict[str, Any]) -> str:
    reload_info = payload.get("reload_guidance") or {}
    marketplace_sync = payload.get("marketplace_sync") or {}
    codex_sync = payload.get("codex_sync") or {}
    codex_config = payload.get("codex_config") or {}
    claude_assets = payload.get("claude_assets") or {}
    bootstrap = payload.get("bootstrap") or {}
    install_report = bootstrap.get("install_report", bootstrap)
    plugin_display_name = codex_sync.get("plugin_display_name") or marketplace_sync.get("plugin_display_name") or "Mission Control"
    plugin_id = marketplace_sync.get("plugin_id", "mission-control@local")
    lines = [
        "## Mission Control Workflow",
        "",
        f"**Action:** {action}",
        f"**Repo root:** {payload['repo_root']}",
        f"**Codex home:** {payload['codex_home']}",
        f"**Status:** {payload['status']}",
        "",
        "### Chat commands",
        "- Codex: `python scripts/mission-control-manage.py install`",
        "- Update: `python scripts/mission-control-manage.py update`",
        "- Uninstall: `python scripts/mission-control-manage.py uninstall`",
        "- Codex smoke: `python scripts/mission-control-manage.py codex-smoke --json`",
        "- Recursive improvement: `python scripts/mission-control-manage.py recursive-improvement --json`",
        "- Codex restart smoke: `python scripts/mission-control-manage.py codex-restart-smoke --json`",
        "- Claude: `/mission-control-install`, `/mission-control-update`, `/mission-control-uninstall`",
    ]
    if action in {"install", "update"}:
        lines.extend(
            [
                "",
                "### Setup",
                f"- Local plugin marketplace: {marketplace_sync.get('status')}",
                f"- Plugin sync: {codex_sync.get('status')}",
                f"- Codex plugin: {plugin_display_name} ({codex_sync.get('plugin_name', 'mission-control')})",
                f"- Plugin id: {plugin_id}",
                f"- Codex MCP registration: {codex_config.get('status')}",
                f"- Claude assets: {claude_assets.get('status')}",
                f"- Claude plugin commands: {claude_assets.get('packaged_command_count', 0)}",
                f"- Claude plugin agents: {claude_assets.get('packaged_agent_count', 0)}",
                f"- Bootstrap: {bootstrap.get('status')}",
            ]
        )
        if install_report.get("configured_runners"):
            lines.append(f"- Ready runners: {', '.join(install_report['configured_runners'])}")
        if install_report.get("unavailable_runners"):
            lines.append(f"- Needs user action: {', '.join(install_report['unavailable_runners'])}")
        if install_report.get("active_repo_root"):
            lines.append(f"- Active backend repo root: {install_report['active_repo_root']}")
        readiness_matrix = list(install_report.get("readiness_matrix") or [])
        if readiness_matrix:
            lines.extend(["", "### Operational readiness"])
            lines.extend(
                f"- {item.get('label')}: {item.get('state')} - {item.get('summary')}"
                for item in readiness_matrix
            )
        if install_report.get("user_actions_required"):
            lines.extend(["", "### User actions required", *[f"- {item}" for item in install_report["user_actions_required"]]])
        lines.extend(
            [
                "",
                "### Before use",
                f"- {reload_info.get('message')}",
                f"- After the reload, Codex should show `{plugin_display_name}` as an available plugin instead of only exposing loose Mission Control skills.",
            ]
        )
        lines.extend(
            [
                "",
                "### After reload verify",
                f"- Open the Codex plugin picker and confirm `{plugin_display_name}` appears as the plugin entry, not just `mission-control*` skills.",
                f"- In Claude Code, approve the project MCP server from `.mcp.json` if Claude prompts for it, then rerun the Mission Control command.",
                f"- If Codex still does not show `{plugin_display_name}`, rerun `python scripts/mission-control-manage.py update` and restart Codex again before blaming the plugin bundle.",
                f"- If the bridge still looks degraded, run `python scripts/mission-control-manage.py update --json` and inspect the bootstrap and runner sections instead of guessing.",
                "",
                "### Installed bridge assets",
                f"- Local marketplace path: {(marketplace_sync.get('marketplace_path') or 'not written')}",
                f"- Local plugin staging path: {(marketplace_sync.get('plugin_destination') or 'not staged')}",
                f"- Codex plugin bundle path: {(codex_sync.get('plugin_destination') or 'not synced')}",
                f"- Codex config path: {(codex_config.get('config_path') or 'not managed')}",
            ]
        )
    elif action == "codex-smoke":
        codex_status = payload.get("codex_status") or {}
        smoke_checks = list(payload.get("smoke_checks") or [])
        reasons = list(payload.get("smoke_reasons") or [])
        require_authenticated = bool(payload.get("require_authenticated", True))
        lines.extend(
            [
                "",
                "### Codex CLI smoke",
                f"- Bootstrap: {(payload.get('bootstrap') or {}).get('status')}",
                f"- Codex CLI path: {codex_status.get('cli_path') or 'not found'}",
                f"- CLI execution available: {'yes' if codex_status.get('cli_execution_available') else 'no'}",
                f"- Authenticated: {'yes' if codex_status.get('authenticated') else 'no'}",
                f"- Authentication required: {'yes' if require_authenticated else 'no'}",
                f"- Recommended repeat command: `{payload.get('recommended_command')}`",
            ]
        )
        if smoke_checks:
            lines.extend(["", "### Checks"])
            lines.extend(
                f"- {item.get('label')}: {item.get('state')} - {item.get('summary')}"
                for item in smoke_checks
            )
        if reasons:
            lines.extend(["", "### Why this is still degraded"])
            lines.extend(f"- {reason}" for reason in reasons)
        lines.extend(
            [
                "",
                "### What this proves",
                "- Mission Control can verify Codex CLI presence, auth posture, MCP registration, and runtime executability in one pass.",
                "- If `CLI execution available` is `no`, this is a runtime limitation of the current host session, not silent guesswork.",
                "- Rerun this command after a Codex reinstall, app reload, or environment change instead of hand-checking five different places like a caveman with a checklist.",
            ]
        )
    elif action == "codex-restart-smoke":
        restart_smoke = payload.get("restart_smoke") or {}
        lines.extend(
            [
                "",
                "### Restart job launched",
                f"- Launcher PID: {restart_smoke.get('launcher_pid')}",
                f"- Results path: {restart_smoke.get('results_path')}",
                f"- Log path: {restart_smoke.get('log_path')}",
                f"- Launch wait seconds: {restart_smoke.get('launch_wait_seconds')}",
                f"- Suggested resume minutes: {restart_smoke.get('recommended_resume_minutes')}",
                "",
                "### What happens next",
                "- Codex will be force-quit.",
                "- Codex will be relaunched by the local CLI.",
                "- After the launch wait, Mission Control will run the Codex CLI smoke test and write the JSON result artifact.",
                "",
                "### Resume",
                f"- Read the results file at `{restart_smoke.get('results_path')}` after the restart window, or wake this thread back up and I can continue from there.",
                "- If you want me to survive the app restart, pair this command with a heartbeat on this thread so I wake back up after the wait window instead of dying with dignity in silence.",
            ]
        )
    elif action == "codex-restart-smoke-status":
        restart_status = payload.get("restart_smoke_status") or {}
        artifact = restart_status.get("artifact") or {}
        smoke = artifact.get("smoke") if isinstance(artifact, dict) else {}
        smoke = smoke if isinstance(smoke, dict) else {}
        smoke_checks = list((smoke or {}).get("smoke_checks") or [])
        lines.extend(
            [
                "",
                "### Restart smoke status",
                f"- Status: {restart_status.get('status')}",
                f"- Summary: {restart_status.get('summary')}",
                f"- Results path: {restart_status.get('results_path')}",
                f"- Log path: {restart_status.get('log_path')}",
            ]
        )
        if smoke_checks:
            lines.extend(["", "### Checks"])
            lines.extend(
                f"- {item.get('label')}: {item.get('state')} - {item.get('summary')}"
                for item in smoke_checks
            )
        if smoke.get("smoke_reasons"):
            lines.extend(["", "### Remaining issues"])
            lines.extend(f"- {reason}" for reason in smoke["smoke_reasons"])
    elif action == "recursive-improvement":
        profile = payload.get("shadow_profile") or {}
        collision_guard = payload.get("collision_guard") or {}
        target_identity = payload.get("target_identity") or {}
        controller_identity = payload.get("controller_identity") or {}
        lines.extend(
            [
                "",
                "### Recursive improvement shadow",
                f"- Shadow name: {profile.get('shadow_name')}",
                f"- Shadow repo: {profile.get('target_repo_root')}",
                f"- Shadow runtime: {profile.get('target_runtime_root')}",
                f"- Shadow port: {profile.get('target_backend_port')}",
                f"- Isolation check: {'passed' if collision_guard.get('isolated') else 'failed'}",
                "",
                "### Target instance",
                f"- Install status: {(payload.get('shadow_install') or {}).get('status')}",
                f"- Smoke status: {(payload.get('shadow_smoke') or {}).get('status')}",
                f"- Target identity repo: {target_identity.get('repo_root')}",
                f"- Target identity port: {target_identity.get('port')}",
                "",
                "### Controller loop",
                f"- Controller identity repo: {controller_identity.get('repo_root')}",
                f"- Controller identity port: {controller_identity.get('port')}",
                f"- Target self-run transcript: {(payload.get('target_happy_path') or {}).get('transcript_path')}",
                f"- Controller-on-target transcript: {(payload.get('controller_happy_path') or {}).get('transcript_path')}",
                "",
                "### What this proves",
                "- Mission Control can stand up an isolated recursive-improvement copy without sharing daemon port or runtime metadata.",
                "- The target instance can attach its own repo copy, surface an approval, and produce a handoff plus approval log.",
                "- The controller instance can run the same headless loop against that target repo copy as a real case-study lane.",
            ]
        )
    elif action == "orchestration-watch":
        status_payload = payload.get("status_payload") or {}
        handoff_payload = (payload.get("handoff_summary") or {}).get("machine_payload_json") or {}
        updates = list(payload.get("updates") or [])
        pending = list(payload.get("pending_decisions") or [])
        events = list(payload.get("events") or [])
        lines.extend(
            [
                "",
                "### Orchestration watch",
                f"- Project: {payload.get('project_name') or payload.get('project_id')}",
                f"- Orchestration: {payload.get('orchestration_id')}",
                f"- Status: {status_payload.get('orchestration_status')}",
                f"- Manager: {status_payload.get('manager_status')}",
                f"- Handoff: {handoff_payload.get('status') or 'unknown'}",
                f"- Pending decisions: {len(pending)}",
                f"- Active agents: {len(list(status_payload.get('active_agents') or []))}",
                f"- Snapshot path: {payload.get('snapshot_path') if payload.get('snapshot_saved') else 'not saved'}",
                f"- Repeat command: `{payload.get('recommended_command')}`",
            ]
        )
        if updates:
            lines.extend(["", "### What changed"])
            lines.extend(f"- {item}" for item in updates)
        warnings = list(payload.get("warnings") or [])
        if warnings:
            lines.extend(["", "### Partial failures"])
            lines.extend(f"- {item}" for item in warnings)
        if events:
            lines.extend(["", "### Recent events"])
            lines.extend(f"- #{item.get('id')}: {_event_preview(item)}" for item in events[-5:])
        status_markdown = str((payload.get("status_summary") or {}).get("fallback_markdown") or "").strip()
        handoff_markdown = str((payload.get("handoff_summary") or {}).get("fallback_markdown") or "").strip()
        if status_markdown:
            lines.extend(["", "### Status summary", status_markdown])
        if handoff_markdown:
            lines.extend(["", "### Handoff summary", handoff_markdown])
    elif action == "orchestration-display":
        status_payload = payload.get("status_payload") or {}
        manager = payload.get("manager") or status_payload.get("manager") or {}
        lines.extend(
            [
                "",
                "### Live orchestration display",
                f"- Project: {payload.get('project_name') or payload.get('project_id')}",
                f"- Orchestration: {payload.get('orchestration_id')}",
                f"- Status: {status_payload.get('orchestration_status')}",
                f"- Manager runner: {manager.get('runner_type') or 'unknown'}",
                f"- Manager model: {manager.get('active_model') or 'unknown'}",
                f"- Active agents: {len(list(status_payload.get('active_agents') or []))}",
                f"- Launch command: `{payload.get('display_command')}`",
                "- The live terminal frame uses real daemon status, manager focus, worker focus, and recent event data.",
            ]
        )
        warnings = list(payload.get("warnings") or [])
        if warnings:
            lines.extend(["", "### Partial failures"])
            lines.extend(f"- {item}" for item in warnings)
    else:
        uninstall_result = payload.get("uninstall") or {}
        lines.extend(
            [
                "",
                "### Cleanup",
                f"- Plugin removed: {'yes' if uninstall_result.get('plugin_removed') else 'no'}",
                f"- Skills removed: {uninstall_result.get('removed_skill_count', 0)}",
                f"- Codex config cleanup: {(uninstall_result.get('config') or {}).get('status')}",
                f"- Local marketplace cleanup: {(payload.get('marketplace_cleanup') or {}).get('status')}",
            ]
        )
        if payload.get("stop_daemon"):
            lines.append(f"- Daemon stop: {payload['stop_daemon'].get('status')}")
        lines.extend(
            [
                "",
                "### After uninstall",
                f"- {reload_info.get('message')}",
                "- If Codex or Claude still shows Mission Control in the current session, force-quit and reopen the app to clear stale cached plugin or MCP state.",
            ]
        )
    return "\n".join(lines)


def run_management_workflow(
    *,
    action: str,
    repo_url: str = DEFAULT_REPO_URL,
    install_dir: str | None = None,
    codex_home_override: str | None = None,
    agents_home_override: str | None = None,
    python_command_override: str | None = None,
    dry_run: bool = False,
    skip_python_setup: bool = False,
    skip_codex_sync: bool = False,
    stop_daemon: bool = True,
    daemon_host: str | None = None,
    daemon_port: int | None = None,
    launch_wait_seconds: int = 25,
    shadow_name: str = "recursive-shadow",
    recreate_shadow: bool = False,
    controller_mode: str = "auto",
    controller_task_request: str | None = None,
    allow_unauthenticated: bool = False,
    project_id: int | None = None,
    orchestration_id: int | None = None,
    workspace_path: str | None = None,
    attach_policy: str = "reuse_existing",
    event_window: str = "since_orchestration_start",
    save_state: bool = True,
    state_file: str | None = None,
    display_ansi: bool = True,
    display_frame_index: int = 0,
) -> dict[str, Any]:
    repo_root = resolve_repo_root(install_dir=install_dir, repo_url=repo_url)
    codex_home = resolve_codex_home(codex_home_override)
    agents_home = resolve_agents_home(agents_home_override)
    python_command = resolve_python_command(python_command_override)
    payload: dict[str, Any] = {
        "action": action,
        "repo_root": str(repo_root),
        "codex_home": str(codex_home),
        "agents_home": str(agents_home),
        "python_command": python_command,
        "dry_run": dry_run,
        "reload_guidance": reload_guidance(action),
    }

    if action in {"install", "update"}:
        payload.update(
            _install_or_update(
                action=action,
                repo_root=repo_root,
                codex_home=codex_home,
                agents_home=agents_home,
                python_command=python_command,
                dry_run=dry_run,
                skip_python_setup=skip_python_setup,
                skip_codex_sync=skip_codex_sync,
                daemon_host=daemon_host,
                daemon_port=daemon_port,
            )
        )
        payload["claude_assets"] = detect_claude_assets(repo_root)
        payload["status"] = _combine_management_status(
            payload.get("bootstrap") or {},
            payload.get("marketplace_sync") or {},
            payload.get("codex_sync") or {},
            payload.get("codex_config") or {},
            payload.get("claude_assets") or {},
        )
    elif action == "codex-smoke":
        bootstrap = run_bootstrap(
            repo_root,
            python_command,
            action="update",
            dry_run=dry_run,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
        )
        payload["bootstrap"] = bootstrap
        payload["claude_assets"] = detect_claude_assets(repo_root)
        payload.update(
            run_codex_smoke(
                repo_root,
                python_command,
                bootstrap=bootstrap,
                require_authenticated=not allow_unauthenticated,
            )
        )
        payload["status"] = payload.get("smoke_status", "degraded")
    elif action == "codex-restart-smoke":
        launched = launch_codex_restart_smoke(
            repo_root,
            python_command,
            launch_wait_seconds=launch_wait_seconds,
        )
        payload["restart_smoke"] = launched
        payload["status"] = "ready"
    elif action == "codex-restart-smoke-status":
        restart_status = load_codex_restart_smoke_status(repo_root)
        payload["restart_smoke_status"] = restart_status
        payload["status"] = str(restart_status.get("status") or "unknown")
    elif action == "recursive-improvement":
        payload.update(
            run_recursive_improvement_workflow(
                repo_root=repo_root,
                python_command=python_command,
                shadow_name=shadow_name,
                backend_port=daemon_port,
                skip_python_setup=skip_python_setup,
                recreate_shadow=recreate_shadow,
                controller_mode=controller_mode,
                controller_task_request=controller_task_request,
            )
        )
    elif action == "orchestration-watch":
        payload.update(
            _run_orchestration_watch(
                repo_root=repo_root,
                project_id=project_id,
                orchestration_id=orchestration_id,
                workspace_path=workspace_path,
                attach_policy=attach_policy,
                event_window=event_window,
                save_state=save_state,
                state_file=state_file,
            )
        )
    elif action == "orchestration-display":
        payload.update(
            _run_orchestration_display(
                repo_root=repo_root,
                project_id=project_id,
                orchestration_id=orchestration_id,
                workspace_path=workspace_path,
                attach_policy=attach_policy,
                event_window=event_window,
                save_state=save_state,
                state_file=state_file,
                frame_index=display_frame_index,
                ansi=display_ansi,
            )
        )
    elif action == "uninstall":
        if stop_daemon and not dry_run:
            payload["stop_daemon"] = run_stop_daemon(repo_root)
        payload["uninstall"] = uninstall_codex_bundle(codex_home, dry_run=dry_run)
        payload["marketplace_cleanup"] = remove_local_plugin_marketplace(agents_home, dry_run=dry_run)
        payload["claude_assets"] = detect_claude_assets(repo_root)
        payload["status"] = "ready"
    else:
        raise ValueError(f"Unsupported action: {action}")

    payload["codex_chat_markdown"] = _build_markdown(action, payload)
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install, update, uninstall, or smoke-test Mission Control bridge assets.")
    parser.add_argument("action", choices=["install", "update", "uninstall", "codex-smoke", "codex-restart-smoke", "codex-restart-smoke-status", "recursive-improvement", "orchestration-watch", "orchestration-display"])
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--install-dir", default=None)
    parser.add_argument("--codex-home", default=None)
    parser.add_argument("--agents-home", default=None)
    parser.add_argument("--python-command", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-python-setup", action="store_true")
    parser.add_argument("--skip-codex-sync", action="store_true")
    parser.add_argument("--no-stop-daemon", action="store_true")
    parser.add_argument("--daemon-host", default=None)
    parser.add_argument("--daemon-port", type=int, default=None)
    parser.add_argument("--launch-wait-seconds", type=int, default=25)
    parser.add_argument("--shadow-name", default="recursive-shadow")
    parser.add_argument("--recreate-shadow", action="store_true")
    parser.add_argument("--controller-mode", choices=["dry_run", "auto"], default="auto")
    parser.add_argument("--controller-task-request", default=None)
    parser.add_argument("--allow-unauthenticated", action="store_true")
    parser.add_argument("--project-id", type=int, default=None)
    parser.add_argument("--orchestration-id", type=int, default=None)
    parser.add_argument("--workspace-path", default=None)
    parser.add_argument("--attach-policy", choices=["reuse_existing", "create_new"], default="reuse_existing")
    parser.add_argument("--event-window", choices=["last_5_minutes", "last_15_minutes", "since_last_user_interaction", "since_orchestration_start"], default="since_orchestration_start")
    parser.add_argument("--no-save-state", action="store_true")
    parser.add_argument("--state-file", default=None)
    parser.add_argument("--refresh-seconds", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--no-ansi", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _run_orchestration_display_cli(args: argparse.Namespace) -> int:
    frame_index = 0
    max_frames = args.max_frames if args.max_frames and args.max_frames > 0 else None
    refresh_seconds = max(float(args.refresh_seconds), ORCHESTRATION_DISPLAY_MIN_REFRESH_SECONDS)
    save_state = False
    workflow_kwargs = dict(
        action="orchestration-display",
        repo_url=args.repo_url,
        install_dir=args.install_dir,
        codex_home_override=args.codex_home,
        agents_home_override=args.agents_home,
        python_command_override=args.python_command,
        dry_run=args.dry_run,
        skip_python_setup=args.skip_python_setup,
        skip_codex_sync=args.skip_codex_sync,
        stop_daemon=not args.no_stop_daemon,
        daemon_host=args.daemon_host,
        daemon_port=args.daemon_port,
        launch_wait_seconds=args.launch_wait_seconds,
        shadow_name=args.shadow_name,
        recreate_shadow=args.recreate_shadow,
        controller_mode=args.controller_mode,
        controller_task_request=args.controller_task_request,
        allow_unauthenticated=args.allow_unauthenticated,
        project_id=args.project_id,
        orchestration_id=args.orchestration_id,
        workspace_path=args.workspace_path,
        attach_policy=args.attach_policy,
        event_window=args.event_window,
        save_state=save_state,
        state_file=args.state_file,
        display_ansi=not args.no_ansi,
        display_frame_index=0,
    )
    try:
        if args.once:
            payload = run_management_workflow(**workflow_kwargs)
            frame = str(
                _build_orchestration_display_frame(
                    payload,
                    frame_index=0,
                    ansi=not args.no_ansi,
                    runtime={
                        "refresh_seconds": refresh_seconds,
                        "fetch_in_progress": False,
                        "fetch_count": 1,
                        "last_fetch_duration_seconds": None,
                        "data_age_seconds": 0.0,
                    },
                )
            )
            sys.stdout.write(frame + "\n")
            sys.stdout.flush()
            return 0 if payload.get("status") in {"ready", "degraded"} else 1

        stop_event = threading.Event()
        state: dict[str, Any] = {
            "payload": None,
            "last_error": None,
            "fetch_in_progress": False,
            "fetch_count": 0,
            "last_fetch_started_at": None,
            "last_fetch_finished_at": None,
            "last_fetch_duration_seconds": None,
        }
        state_lock = threading.Lock()

        def fetch_loop() -> None:
            next_fetch_at = time.perf_counter()
            while not stop_event.is_set():
                started_at = utc_now().isoformat()
                started_perf = time.perf_counter()
                with state_lock:
                    state["fetch_in_progress"] = True
                    state["last_fetch_started_at"] = started_at
                payload: dict[str, Any] | None = None
                error: str | None = None
                try:
                    payload = run_management_workflow(**workflow_kwargs)
                except Exception as exc:
                    error = str(exc)
                finished_at = utc_now().isoformat()
                duration = time.perf_counter() - started_perf
                with state_lock:
                    if payload is not None:
                        state["payload"] = payload
                    state["last_error"] = error
                    state["fetch_in_progress"] = False
                    state["fetch_count"] = int(state.get("fetch_count") or 0) + 1
                    state["last_fetch_finished_at"] = finished_at
                    state["last_fetch_duration_seconds"] = duration
                next_fetch_at += refresh_seconds
                delay = next_fetch_at - time.perf_counter()
                if delay < 0:
                    next_fetch_at = time.perf_counter()
                    delay = 0
                if stop_event.wait(delay):
                    return

        worker = threading.Thread(target=fetch_loop, name="mission-control-display-fetch", daemon=True)
        worker.start()

        next_render_at = time.perf_counter()
        while True:
            with state_lock:
                payload = state.get("payload")
                last_error = state.get("last_error")
                fetch_in_progress = bool(state.get("fetch_in_progress"))
                fetch_count = int(state.get("fetch_count") or 0)
                last_fetch_duration_seconds = state.get("last_fetch_duration_seconds")
            runtime = {
                "refresh_seconds": refresh_seconds,
                "fetch_in_progress": fetch_in_progress,
                "fetch_count": fetch_count,
                "last_fetch_duration_seconds": last_fetch_duration_seconds,
                "last_error": last_error,
                "data_age_seconds": None,
            }
            frame: str
            if payload is not None:
                checked_at_text = str(payload.get("checked_at") or "").strip()
                if checked_at_text:
                    try:
                        checked_at = datetime.fromisoformat(checked_at_text)
                        runtime["data_age_seconds"] = max(0.0, (utc_now() - checked_at).total_seconds())
                    except ValueError:
                        runtime["data_age_seconds"] = None
                frame = _build_orchestration_display_frame(
                    payload,
                    frame_index=frame_index,
                    ansi=not args.no_ansi,
                    runtime=runtime,
                )
            else:
                frame = _build_orchestration_display_waiting_frame(
                    project_id=args.project_id,
                    orchestration_id=args.orchestration_id,
                    workspace_path=args.workspace_path,
                    refresh_seconds=refresh_seconds,
                    frame_index=frame_index,
                    ansi=not args.no_ansi,
                    last_error=str(last_error) if last_error else None,
                    fetch_count=fetch_count,
                )
            if not args.no_ansi:
                sys.stdout.write("\x1b[2J\x1b[H")
            elif frame_index:
                sys.stdout.write("\n" + ("-" * 100) + "\n")
            sys.stdout.write(frame + "\n")
            sys.stdout.flush()
            if payload is not None and payload.get("status") not in {"ready", "degraded"}:
                return 1
            frame_index += 1
            if max_frames is not None and frame_index >= max_frames:
                return 0
            next_render_at += refresh_seconds
            delay = next_render_at - time.perf_counter()
            if delay < 0:
                next_render_at = time.perf_counter()
                delay = 0
            if stop_event.wait(delay):
                return 0
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        sys.stdout.flush()
        return 0
    finally:
        if 'stop_event' in locals():
            stop_event.set()
        if 'worker' in locals():
            worker.join(timeout=1.0)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.action == "orchestration-display" and not args.json:
        return _run_orchestration_display_cli(args)
    payload = run_management_workflow(
        action=args.action,
        repo_url=args.repo_url,
        install_dir=args.install_dir,
        codex_home_override=args.codex_home,
        agents_home_override=args.agents_home,
        python_command_override=args.python_command,
        dry_run=args.dry_run,
        skip_python_setup=args.skip_python_setup,
        skip_codex_sync=args.skip_codex_sync,
        stop_daemon=not args.no_stop_daemon,
        daemon_host=args.daemon_host,
        daemon_port=args.daemon_port,
        launch_wait_seconds=args.launch_wait_seconds,
        shadow_name=args.shadow_name,
        recreate_shadow=args.recreate_shadow,
        controller_mode=args.controller_mode,
        controller_task_request=args.controller_task_request,
        allow_unauthenticated=args.allow_unauthenticated,
        project_id=args.project_id,
        orchestration_id=args.orchestration_id,
        workspace_path=args.workspace_path,
        attach_policy=args.attach_policy,
        event_window=args.event_window,
        save_state=not args.no_save_state,
        state_file=args.state_file,
        display_ansi=not args.no_ansi,
        display_frame_index=0,
    )
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(payload["codex_chat_markdown"])
    acceptable_statuses = {"ready", "degraded"}
    if args.action == "codex-restart-smoke-status":
        acceptable_statuses.add("missing")
    return 0 if payload["status"] in acceptable_statuses else 1


if __name__ == "__main__":
    raise SystemExit(main())
