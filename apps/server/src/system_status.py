from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from config import DEFAULT_BACKEND_PORT, RUNTIME_ROOT, load_launcher_config, get_codex_home


def _run_command(args: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    output = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode == 0, output


def auth_mode_from_login_output(login_output: str) -> str | None:
    lowered = login_output.lower()
    if "chatgpt" in lowered:
        return "chatgpt"
    if "api key" in lowered or "api-key" in lowered:
        return "api_key"
    if "logged in" in lowered:
        return "other"
    return None


def is_authenticated(login_ok: bool, login_output: str) -> bool:
    lowered = login_output.lower()
    if "not logged in" in lowered or "log in to codex" in lowered:
        return False
    if auth_mode_from_login_output(login_output):
        return True
    return login_ok and "logged in" in lowered


def detect_codex_status() -> dict:
    codex_home = get_codex_home()
    config_path = codex_home / "config.toml"
    skills_root = codex_home / "skills"
    launcher_config = load_launcher_config()

    cli_ok, cli_output = _run_command(["codex", "--version"])
    login_ok, login_output = _run_command(["codex", "login", "status"])
    _, mcp_output = _run_command(["codex", "mcp", "list", "--json"])
    _, app_help = _run_command(["codex", "app-server", "--help"])

    configured_plugins: list[str] = []
    notes: list[str] = []
    if config_path.exists():
        config_text = config_path.read_text(encoding="utf-8", errors="ignore")
        configured_plugins = re.findall(r'\[plugins\."([^"]+)"\]', config_text)
        if "sandbox_mode = \"workspace-write\"" in config_text:
            notes.append("User config defaults to workspace-write sandboxing.")
    else:
        notes.append("No user config.toml found.")

    local_skills: list[str] = []
    if skills_root.exists():
        for child in skills_root.iterdir():
            if child.is_dir():
                local_skills.append(child.name)

    mcp_servers = []
    if mcp_output:
        try:
            mcp_servers = json.loads(mcp_output)
        except json.JSONDecodeError:
            notes.append("Could not parse MCP server list as JSON.")

    auth_mode = auth_mode_from_login_output(login_output)
    authenticated = is_authenticated(login_ok, login_output)

    notes.append("Model availability depends on the local Codex plan and current sign-in session.")
    notes.append("ChatGPT sign-in is recommended. API keys are optional and can use API billing.")

    return {
        "cli_detected": cli_ok,
        "cli_version": cli_output if cli_ok else None,
        "login_status": login_output or "Unavailable",
        "auth_mode": auth_mode,
        "authenticated": authenticated,
        "app_server_supported": "Run the app server" in app_help or "[experimental]" in app_help,
        "app_server_handshake_status": "not_checked",
        "app_server_transport": "stdio_jsonrpc",
        "effective_runner_mode": "auto",
        "dry_run_available": True,
        "runtime_directory": str(RUNTIME_ROOT),
        "backend_port": int(launcher_config.get("backendPort", DEFAULT_BACKEND_PORT)),
        "frontend_port": int(launcher_config["frontendPort"]) if launcher_config.get("frontendPort") is not None else None,
        "active_runs": [],
        "current_settings_summary": None,
        "selected_manager_model": None,
        "selected_default_worker_model": None,
        "available_models": [],
        "mcp_servers": mcp_servers,
        "configured_plugins": configured_plugins,
        "local_skills": sorted(local_skills),
        "current_auth_job": None,
        "notes": notes,
    }
