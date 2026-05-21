from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from claude_cli_path import claude_command_path
from codex_cli_path import codex_command_path
from config import LAUNCHER_ROOT, REPO_ROOT, RUNTIME_ROOT, get_codex_home, load_launcher_config
from daemon_state import daemon_identity_snapshot, resolve_backend_binding
from provider_support import normalize_provider, provider_label, supports_app_server

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ should provide tomllib
    tomllib = None  # type: ignore[assignment]


def _run_command(args: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    output = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode == 0, output


def _path_exists(path_text: str | None) -> bool:
    return bool(path_text and Path(path_text).exists())


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


def _parse_configured_plugins(config_text: str) -> list[str]:
    return re.findall(r'\[plugins\."([^"]+)"\]', config_text)


def _parse_configured_mcp_servers(config_text: str) -> list[dict[str, Any]]:
    if tomllib is not None:
        try:
            loaded = tomllib.loads(config_text)
        except Exception:
            loaded = {}
        raw_servers = loaded.get("mcp_servers") if isinstance(loaded, dict) else {}
        if isinstance(raw_servers, dict):
            servers: list[dict[str, Any]] = []
            for name, value in raw_servers.items():
                entry: dict[str, Any] = {"name": str(name)}
                if isinstance(value, dict):
                    for key in ("command", "status", "transport", "cwd"):
                        if key in value:
                            entry[key] = value[key]
                servers.append(entry)
            return servers
    names: list[str] = []
    for match in re.finditer(r'\[mcp_servers\.(?:"([^"]+)"|([^\]\r\n]+))\]', config_text):
        raw_name = match.group(1) or match.group(2) or ""
        name = raw_name.strip().strip('"').strip("'")
        if name:
            names.append(name)
    return [{"name": name} for name in names]


def _find_mission_control_mcp_server(servers: list[dict[str, Any]]) -> dict[str, Any] | None:
    for server in servers:
        haystacks = [
            str(server.get("name") or ""),
            str(server.get("id") or ""),
            str(server.get("command") or ""),
            str(server.get("display_name") or ""),
            str(server.get("server") or ""),
        ]
        if any("mission-control" in value.lower() or "mission_control" in value.lower() for value in haystacks):
            return server
    return None


def _mission_control_mcp_state(
    *,
    live_servers: list[dict[str, Any]],
    configured_servers: list[dict[str, Any]],
    live_discovery_available: bool,
) -> dict[str, Any]:
    configured_entry = _find_mission_control_mcp_server(configured_servers)
    live_entry = _find_mission_control_mcp_server(live_servers)
    if live_entry is not None:
        summary = "Mission Control is configured and was discovered in the live Codex MCP server list."
    elif configured_entry is not None and not live_discovery_available:
        summary = "Mission Control is configured in Codex config, but live MCP loading could not be inspected from this runtime."
    elif configured_entry is not None:
        summary = "Mission Control is configured in Codex config, but it was not discovered in the live Codex MCP server list."
    else:
        summary = "Mission Control is not configured in the detected Codex MCP server config."
    return {
        "mission_control": {
            "configured": configured_entry is not None,
            "configured_entry": configured_entry,
            "app_loaded": live_entry is not None if live_discovery_available else None,
            "live_entry": live_entry,
            "callable": None,
            "discovery_source": "cli" if live_entry is not None else ("config_toml" if configured_entry is not None else "none"),
            "summary": summary,
        }
    }


def _detect_codex_environment() -> dict[str, Any]:
    codex_home = get_codex_home()
    config_path = codex_home / "config.toml"
    skills_root = codex_home / "skills"
    cli_path = codex_command_path()
    cli_path_exists = _path_exists(cli_path)
    cli_ok, cli_output = _run_command([cli_path, "--version"]) if cli_path else (False, "")
    login_ok, login_output = _run_command([cli_path, "login", "status"]) if cli_path else (False, "")
    mcp_ok, mcp_output = _run_command([cli_path, "mcp", "list", "--json"]) if cli_path else (False, "")
    app_help_ok, app_help = _run_command([cli_path, "app-server", "--help"]) if cli_path else (False, "")

    configured_plugins: list[str] = []
    configured_mcp_servers: list[dict[str, Any]] = []
    notes: list[str] = []
    if config_path.exists():
        config_text = config_path.read_text(encoding="utf-8", errors="ignore")
        configured_plugins = _parse_configured_plugins(config_text)
        configured_mcp_servers = _parse_configured_mcp_servers(config_text)
        if 'sandbox_mode = "workspace-write"' in config_text:
            notes.append("User config defaults to workspace-write sandboxing.")
    else:
        notes.append("No user config.toml found.")

    local_skills: list[str] = []
    if skills_root.exists():
        for child in skills_root.iterdir():
            if child.is_dir():
                local_skills.append(child.name)

    live_mcp_servers: list[dict[str, Any]] = []
    if mcp_output:
        try:
            loaded = json.loads(mcp_output)
            if isinstance(loaded, list):
                live_mcp_servers = loaded
        except json.JSONDecodeError:
            notes.append("Could not parse MCP server list as JSON.")
    elif configured_mcp_servers and not mcp_ok:
        notes.append("Codex MCP runtime discovery was unavailable, so configured MCP servers were inferred from config.toml.")

    live_discovery_available = mcp_ok
    if cli_path_exists and not cli_ok:
        notes.append("Codex CLI path was found, but direct CLI execution is unavailable from this runtime.")

    login_status = login_output or "Unavailable"
    if cli_path_exists and not login_output:
        login_status = "CLI path found, but login status could not be queried from this runtime."

    return {
        "cli_detected": cli_ok or cli_path_exists,
        "cli_path": cli_path,
        "cli_path_exists": cli_path_exists,
        "cli_execution_available": cli_ok,
        "cli_version": cli_output if cli_ok else None,
        "login_status": login_status,
        "auth_mode": auth_mode_from_login_output(login_output),
        "authenticated": is_authenticated(login_ok, login_output),
        "app_server_supported": ("Run the app server" in app_help or "[experimental]" in app_help) if app_help_ok else False,
        "configured_plugins": configured_plugins,
        "configured_mcp_servers": configured_mcp_servers,
        "local_skills": sorted(local_skills),
        "mcp_servers": live_mcp_servers,
        "mcp_state": _mission_control_mcp_state(
            live_servers=live_mcp_servers,
            configured_servers=configured_mcp_servers,
            live_discovery_available=live_discovery_available,
        ),
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
    cli_path_exists = _path_exists(cli_path)
    cli_ok, cli_output = _run_command([cli_path, "--version"]) if cli_path else (False, "")
    notes = [
        "Claude Code login is managed by the local Claude Code CLI, not by Mission Control.",
        "Mission Control can pass per-run model overrides when the CLI supports them.",
        f"Claude CLI path: {cli_path or 'not found'}.",
    ]
    return {
        "provider": "claude_code",
        "label": "Claude Code",
        "cli_detected": cli_ok or cli_path_exists,
        "cli_path": cli_path,
        "cli_path_exists": cli_path_exists,
        "cli_execution_available": cli_ok,
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
        "cli_path": None,
        "cli_path_exists": reachable,
        "cli_execution_available": reachable,
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
        "cli_path": env_key if configured else None,
        "cli_path_exists": configured,
        "cli_execution_available": configured,
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
        "cli_path": command or None,
        "cli_path_exists": detected,
        "cli_execution_available": detected,
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


def _recommended_local_coding_models(available_models: list[str] | None = None) -> list[str]:
    candidates = [str(item) for item in (available_models or []) if str(item).strip()]
    preferred_order = [
        "gpt-oss:20b",
        "codestral",
        "qwen2.5-coder:14b",
        "qwen2.5-coder:7b",
        "deepseek-coder",
        "codellama:13b",
        "deepseek-r1:8b",
        "gemma3:12b",
    ]
    matches: list[str] = []
    lowered = [(item, item.lower()) for item in candidates]
    for preferred in preferred_order:
        for original, text in lowered:
            if preferred in text and original not in matches:
                matches.append(original)
    return matches[:4]


def assess_model_advisories(
    *,
    provider: str,
    manager_model: str | None = None,
    worker_model: str | None = None,
    available_models: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_provider = normalize_provider(provider)
    advisories: list[dict[str, Any]] = []

    def add(role: str, model: str, severity: str, summary: str, recommendation: str | None = None) -> None:
        advisories.append(
            {
                "role": role,
                "provider": normalized_provider,
                "model": model,
                "severity": severity,
                "summary": summary,
                "recommendation": recommendation,
            }
        )

    for role, raw_model in (("manager", manager_model), ("worker", worker_model)):
        model = str(raw_model or "").strip()
        if not model:
            continue
        lowered = model.lower()
        if normalized_provider == "ollama":
            stronger_local = _recommended_local_coding_models(available_models)
            stronger_text = ", ".join(stronger_local) if stronger_local else "qwen2.5-coder:14b, codestral, gpt-oss:20b, or gemma3:12b"
            if any(token in lowered for token in ("qwen2.5:7b", "llama3", "gemma3:latest", "deepseek-r1:latest", "deepseek-r1:8b")):
                add(
                    role,
                    model,
                    "warning",
                    f"{role.title()} model `{model}` is a weaker local model and often underperforms on code-edit turns or valid `edits[]` generation.",
                    f"Prefer a stronger local coding model such as {stronger_text}.",
                )
            elif any(token in lowered for token in ("qwen2.5-coder:7b", "codellama", "gemma3")):
                add(
                    role,
                    model,
                    "info",
                    f"{role.title()} model `{model}` is usable but may still struggle on multi-step patch generation.",
                    f"If Mission Control stalls on edit quality, upgrade to {stronger_text}.",
                )
        elif normalized_provider == "codex":
            if "mini" in lowered:
                add(
                    role,
                    model,
                    "info",
                    f"{role.title()} model `{model}` is a compact Codex model. It is fine for lighter coordination but weaker for harder code planning or patch generation.",
                    "Use a stronger Codex model for deeper planning or code-edit turns when quality matters more than speed.",
                )
        elif normalized_provider == "claude_code":
            if "haiku" in lowered:
                add(
                    role,
                    model,
                    "warning",
                    f"{role.title()} model `{model}` is a lighter Claude model and may underperform on deeper coding or orchestration work.",
                    "Prefer Sonnet or Opus for harder Mission Control runs.",
                )
    return advisories


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


def detect_system_status(
    *,
    selected_provider: str = "codex",
    adapter_command: str | None = None,
    ollama_endpoint: str | None = None,
    adapter_args: list[str] | None = None,
) -> dict[str, Any]:
    normalized_provider = normalize_provider(selected_provider)
    launcher_config = load_launcher_config()
    backend_binding = resolve_backend_binding()
    daemon_identity = daemon_identity_snapshot()
    provider_statuses = detect_provider_statuses(adapter_command, ollama_endpoint, adapter_args)
    provider_lookup = {entry["provider"]: entry for entry in provider_statuses}
    selected = provider_lookup.get(normalized_provider, provider_lookup["codex"])
    codex = provider_lookup["codex"]
    advisories = assess_model_advisories(
        provider=normalized_provider,
        available_models=list(selected.get("available_models", [])),
    )
    notes = list(dict.fromkeys(selected.get("notes", []) + codex.get("notes", [])))
    return {
        "selected_provider": normalized_provider,
        "selected_provider_label": provider_label(normalized_provider),
        "cli_detected": selected["cli_detected"],
        "cli_path": selected.get("cli_path"),
        "cli_path_exists": bool(selected.get("cli_path_exists")),
        "cli_execution_available": bool(selected.get("cli_execution_available")),
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
        "repo_root": str(REPO_ROOT),
        "launcher_root": str(LAUNCHER_ROOT),
        "plugin_source_root": str((REPO_ROOT / "plugins" / "mission-control").resolve()),
        "backend_host": str(backend_binding["host"]),
        "backend_port": int(backend_binding["port"]),
        "backend_base_url": f"http://{backend_binding['host']}:{int(backend_binding['port'])}",
        "configured_backend_port": int(launcher_config["backendPort"]) if launcher_config.get("backendPort") is not None else None,
        "backend_binding_source": str(backend_binding["source"]),
        "frontend_port": int(launcher_config["frontendPort"]) if launcher_config.get("frontendPort") is not None else None,
        "active_runs": [],
        "current_settings_summary": None,
        "selected_manager_model": None,
        "selected_default_worker_model": None,
        "available_models": list(selected.get("available_models", [])),
        "model_advisories": advisories,
        "provider_statuses": provider_statuses,
        "mcp_servers": list(codex.get("mcp_servers", [])),
        "configured_mcp_servers": list(codex.get("configured_mcp_servers", [])),
        "mcp_state": dict(codex.get("mcp_state", {})),
        "configured_plugins": list(codex.get("configured_plugins", [])),
        "local_skills": list(codex.get("local_skills", [])),
        "current_auth_job": None,
        "notes": notes
        + [
            f"Backend binding source: {backend_binding['source']}.",
            f"Active repo root: {daemon_identity['repo_root']}.",
            f"Launcher root: {daemon_identity['launcher_root']}.",
        ],
    }
