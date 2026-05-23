from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


MANAGED_BLOCK_START = "# >>> mission-control managed >>>"
MANAGED_BLOCK_END = "# <<< mission-control managed <<<"
DEFAULT_REPO_URL = "https://github.com/MN755/Codex-Mission_Control"
DEFAULT_MARKETPLACE_NAME = "local"


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
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    if not manifest_path.exists():
        manifest_path = plugin_root / "plugin.json"
    if not manifest_path.exists():
        return {
            "status": "missing",
            "manifest_path": str(manifest_path),
        }
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid",
            "manifest_path": str(manifest_path),
            "error": str(exc),
        }
    return {
        "status": "ready",
        "manifest_path": str(manifest_path),
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
    plugin_name = plugin_manifest.get("name") or "mission-control"
    plugin_display_name = plugin_manifest.get("display_name") or "Mission Control"
    plugins_root = agents_home.parent / "plugins"
    plugin_destination = plugins_root / plugin_name
    marketplace_path = agents_home / "plugins" / "marketplace.json"
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
        "plugin_destination": str(plugin_destination),
        "plugin_manifest": plugin_manifest,
        "plugin_name": plugin_name,
        "plugin_display_name": plugin_display_name,
        "plugin_files_copied": plugin_files_copied,
        "marketplace_path": str(marketplace_path),
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

    plugin_files_copied = _copy_tree(plugin_source, plugin_destination, dry_run=dry_run)
    cache_sync = sync_codex_plugin_cache(plugin_source, codex_home, plugin_manifest, dry_run=dry_run)
    if skills_source_root.exists():
        for skill_dir in sorted(path for path in skills_source_root.iterdir() if path.is_dir() and path.name.startswith("mission-control")):
            copied_skills.append(skill_dir.name)
            _copy_tree(skill_dir, skills_destination_root / skill_dir.name, dry_run=dry_run)

    return {
        "codex_home": str(codex_home),
        "plugin_source": str(plugin_source),
        "plugin_destination": str(plugin_destination),
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


def ensure_python_packages(repo_root: Path, python_command: str, *, dry_run: bool = False, skip: bool = False) -> list[dict[str, Any]]:
    steps = [
        ("backend", repo_root / "apps" / "server", [python_command, "-m", "pip", "install", "-e", ".[dev]"]),
        ("mcp_server", repo_root / "apps" / "mcp-server", [python_command, "-m", "pip", "install", "-e", "."]),
    ]
    results: list[dict[str, Any]] = []
    for name, cwd, command in steps:
        if skip:
            results.append({"name": name, "status": "skipped", "command": command, "cwd": str(cwd)})
            continue
        if dry_run:
            results.append({"name": name, "status": "dry_run", "command": command, "cwd": str(cwd)})
            continue
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=600, check=False)
        output = completed.stdout.strip() or completed.stderr.strip()
        results.append(
            {
                "name": name,
                "status": "ready" if completed.returncode == 0 else "failed",
                "command": command,
                "cwd": str(cwd),
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


def run_stop_daemon(repo_root: Path) -> dict[str, Any]:
    script_path = repo_root / "scripts" / ("stop-mission-control-daemon.ps1" if os.name == "nt" else "stop-mission-control-daemon.sh")
    if not script_path.exists():
        return {"status": "missing", "message": f"Stop script not found: {script_path}"}
    if os.name == "nt":
        command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
    else:
        command = ["bash", str(script_path)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
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


def run_codex_smoke(repo_root: Path, python_command: str, *, bootstrap: dict[str, Any]) -> dict[str, Any]:
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
        and bool(codex_status.get("authenticated"))
        and bool(((codex_status.get("mcp_state") or {}).get("mission_control") or {}).get("configured"))
        and bool(mcp_probe.get("callable"))
        and bool(backend_probe.get("reachable"))
    )
    reasons: list[str] = []
    if not codex_status.get("cli_detected"):
        reasons.append("Codex CLI was not detected.")
    elif not codex_status.get("cli_execution_available"):
        reasons.append("Codex CLI exists, but the current runtime cannot execute it directly.")
    if not codex_status.get("authenticated"):
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
    return {
        "codex_status": codex_status,
        "mcp_stdio_probe": mcp_probe,
        "daemon_health_probe": backend_probe,
        "smoke_checks": smoke_checks,
        "smoke_runnable": runnable,
        "smoke_status": smoke_status,
        "smoke_reasons": reasons,
        "recommended_command": f"{python_command} scripts/mission-control-manage.py codex-smoke --json",
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
        lines.extend(
            [
                "",
                "### Codex CLI smoke",
                f"- Bootstrap: {(payload.get('bootstrap') or {}).get('status')}",
                f"- Codex CLI path: {codex_status.get('cli_path') or 'not found'}",
                f"- CLI execution available: {'yes' if codex_status.get('cli_execution_available') else 'no'}",
                f"- Authenticated: {'yes' if codex_status.get('authenticated') else 'no'}",
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
        bootstrap = payload.get("bootstrap") or {}
        status = str(bootstrap.get("status") or "degraded")
        if status not in {"ready", "degraded"}:
            status = "failed"
        payload["status"] = status
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
        payload.update(run_codex_smoke(repo_root, python_command, bootstrap=bootstrap))
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
    parser.add_argument("action", choices=["install", "update", "uninstall", "codex-smoke", "codex-restart-smoke", "codex-restart-smoke-status"])
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
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
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
