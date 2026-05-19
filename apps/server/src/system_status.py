from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from claude_cli_path import claude_command_path
from codex_cli_path import codex_command_path
from config import DEFAULT_BACKEND_PORT, RUNTIME_ROOT, get_codex_home, load_launcher_config
from daemon_state import resolve_backend_binding
from provider_support import normalize_provider, provider_label, supports_app_server, supports_builtin_auth, supports_reasoning_effort


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


def _detect_codex_environment() -> dict[str, Any]:
    codex_home = get_codex_home()
    config_path = codex_home / "config.toml"
    skills_root = codex_home / "skills"
    cli_path = codex_command_path()
    cli_ok, cli_output = _run_command([cli_path, "--version"]) if cli_path else (False, "")
    login_ok, login_output = _run_command([cli_path, "login", "status"]) if cli_path else (False, "")
    _, mcp_output = _run_command([cli_path, "mcp", "list", "--json"]) if cli_path else (False, "")
    _, app_help = _run_command([cli_path, "app-server", "--help"]) if cli_path else (False, "")

    configured_plugins: list[str] = []
    notes: list[str] = []
    if config_path.exists():
        config_text = config_path.read_text(encoding="utf-8", errors="ignore")
        configured_plugins = re.findall(r'\[plugins\."([^"]+)"\]', config_text)
        if 'sandbox_mode = "workspace-write"' in config_text:
            notes.append("User config defaults to workspace-write sandboxing.")
    else:
        notes.append("No user config.toml found.")

    local_skills: list[str] = []
    if skills_root.exists():
        for child in skills_root.iterdir():
            if child.is_dir():
                local_skills.append(child.name)

    mcp_servers: list[dict[str, Any]] = []
    if mcp_output:
        try:
            loaded = json.loads(mcp_output)
            if isinstance(loaded, list):
                mcp_servers = loaded
        except json.JSONDecodeError:
            notes.append("Could not parse MCP server list as JSON.")

    return {
        "cli_detected": cli_ok,
        "cli_path": cli_path,
        "cli_version": cli_output if cli_ok else None,
        "login_status": login_output or "Unavailable",
        "auth_mode": auth_mode_from_login_output(login_output),
        "authenticated": is_authenticated(login_ok, login_output),
        "app_server_supported": "Run the app server" in app_help or "[experimental]" in app_help,
        "configured_plugins": configured_plugins,
        "local_skills": sorted(local_skills),
        "mcp_servers": mcp_servers,
        "notes": notes,
    }


def detect_codex_status() -> dict[str, Any]:
    payload = _detect_codex_environment()
    payload.update(
        {
            "provider": "codex",
            "label": "Codex",
            "auth_status_detectable": True,
            "supports_model_override": True,
            "supports_reasoning_effort": True,
            "supports_app_server": payload["app_server_supported"],
            "supports_builtin_auth": True,
            "available_models": [],
            "notes": payload["notes"]
            + [
                "Model availability depends on the local Codex plan and current sign-in session.",
                "ChatGPT sign-in is recommended. API keys are optional and can use API billing.",
                f"Codex CLI path: {payload.get('cli_path') or 'not found'}.",
            ],
        }
    )
    return payload


def detect_claude_code_status() -> dict[str, Any]:
    cli_path = claude_command_path()
    cli_ok, cli_output = _run_command([cli_path, "--version"]) if cli_path else (False, "")
    notes = [
        "Claude Code login is managed by the local Claude Code CLI, not by Mission Control.",
        "Mission Control can pass per-run model overrides when the CLI supports them.",
        f"Claude CLI path: {cli_path or 'not found'}.",
    ]
    return {
        "provider": "claude_code",
        "label": "Claude Code",
        "cli_detected": cli_ok,
        "cli_path": cli_path,
        "cli_version": cli_output if cli_ok else None,
        "login_status": "Interactive Claude Code login is managed outside Mission Control.",
        "auth_mode": None,
        "authenticated": False,
        "auth_status_detectable": False,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": ["sonnet", "opus"] if cli_ok else [],
        "notes": notes,
    }


def detect_ollama_status(endpoint: str | None = None) -> dict[str, Any]:
    base = (endpoint or "http://localhost:11434").rstrip("/")
    summary = f"Ollama endpoint configured at {base}."
    reachable = False
    available_models: list[str] = []
    try:
        with urlopen(f"{base}/api/tags", timeout=3) as response:
            body = response.read().decode("utf-8", errors="ignore")
            payload = json.loads(body)
            models = payload.get("models") if isinstance(payload, dict) else []
            if isinstance(models, list):
                available_models = [str(item.get("name")) for item in models if isinstance(item, dict) and item.get("name")]
            reachable = response.status == 200
            summary = f"Ollama endpoint reachable at {base}."
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        summary = f"Ollama endpoint not reachable at {base}."
    return {
        "provider": "ollama",
        "label": "Ollama",
        "cli_detected": reachable,
        "cli_version": base,
        "login_status": summary,
        "auth_mode": "local",
        "authenticated": reachable,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": True,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": available_models,
        "notes": ["Ollama is local-first. Mission Control expects a local adapter or wrapper command for live execution."],
        "reachable": reachable,
        "summary": summary,
    }


def detect_env_api_status(provider: str, *, env_key: str, label: str) -> dict[str, Any]:
    configured = bool(os.environ.get(env_key))
    return {
        "provider": provider,
        "label": label,
        "cli_detected": configured,
        "cli_version": env_key if configured else None,
        "login_status": f"{env_key} {'is configured' if configured else 'is not configured in the current environment.'}",
        "auth_mode": "api_key" if configured else None,
        "authenticated": configured,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": ["API providers are supported without storing keys inside Mission Control."],
    }


def detect_custom_status(adapter_command: str | None = None, adapter_args: list[str] | None = None) -> dict[str, Any]:
    command = (adapter_command or "").strip()
    detected = bool(command and shutil.which(command))
    notes = [
        "Mission Control does not manage authentication for custom providers.",
        "Custom providers run through local adapter commands rather than direct built-in integrations.",
    ]
    version = " ".join([command, *(adapter_args or [])]).strip() if command else None
    return {
        "provider": "custom",
        "label": "Custom provider",
        "cli_detected": detected,
        "cli_version": version if detected else None,
        "login_status": "Adapter-defined authentication",
        "auth_mode": None,
        "authenticated": False,
        "auth_status_detectable": False,
        "supports_model_override": True,
        "supports_reasoning_effort": True,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": notes,
    }


def detect_provider_statuses(adapter_command: str | None = None, ollama_endpoint: str | None = None, adapter_args: list[str] | None = None) -> list[dict[str, Any]]:
    return [
        detect_codex_status(),
        detect_ollama_status(ollama_endpoint),
        detect_env_api_status("openai_api", env_key="OPENAI_API_KEY", label="OpenAI API"),
        detect_env_api_status("anthropic_api", env_key="ANTHROPIC_API_KEY", label="Anthropic API"),
        detect_env_api_status("xai_api", env_key="XAI_API_KEY", label="xAI API"),
        detect_claude_code_status(),
        detect_custom_status(adapter_command, adapter_args),
    ]


def detect_system_status(*, selected_provider: str = "codex", adapter_command: str | None = None, ollama_endpoint: str | None = None, adapter_args: list[str] | None = None) -> dict[str, Any]:
    normalized_provider = normalize_provider(selected_provider)
    launcher_config = load_launcher_config()
    backend_binding = resolve_backend_binding()
    provider_statuses = detect_provider_statuses(adapter_command, ollama_endpoint, adapter_args)
    provider_lookup = {entry["provider"]: entry for entry in provider_statuses}
    selected = provider_lookup.get(normalized_provider, provider_lookup["codex"])
    codex = provider_lookup["codex"]
    notes = list(dict.fromkeys(selected.get("notes", []) + codex.get("notes", [])))
    return {
        "selected_provider": normalized_provider,
        "selected_provider_label": provider_label(normalized_provider),
        "cli_detected": selected["cli_detected"],
        "cli_version": selected["cli_version"],
        "login_status": selected["login_status"],
        "auth_mode": selected["auth_mode"],
        "authenticated": selected["authenticated"],
        "app_server_supported": bool(supports_app_server(normalized_provider)),
        "app_server_handshake_status": "unsupported" if normalized_provider != "codex" else "not_checked",
        "app_server_transport": "stdio_jsonrpc" if normalized_provider == "codex" else "unsupported",
        "effective_runner_mode": "auto",
        "dry_run_available": True,
        "runtime_directory": str(RUNTIME_ROOT),
        "backend_host": str(backend_binding["host"]),
        "backend_port": int(backend_binding["port"]),
        "configured_backend_port": int(launcher_config["backendPort"]) if launcher_config.get("backendPort") is not None else None,
        "backend_binding_source": str(backend_binding["source"]),
        "frontend_port": int(launcher_config["frontendPort"]) if launcher_config.get("frontendPort") is not None else None,
        "active_runs": [],
        "current_settings_summary": None,
        "selected_manager_model": None,
        "selected_default_worker_model": None,
        "available_models": list(selected.get("available_models", [])),
        "provider_statuses": provider_statuses,
        "mcp_servers": list(codex.get("mcp_servers", [])),
        "configured_plugins": list(codex.get("configured_plugins", [])),
        "local_skills": list(codex.get("local_skills", [])),
        "current_auth_job": None,
        "notes": notes + [f"Backend binding source: {backend_binding['source']}."],
    }
