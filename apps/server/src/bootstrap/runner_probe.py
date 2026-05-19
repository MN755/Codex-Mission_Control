from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from bootstrap.dependency_probe import probe_command
from bootstrap.secret_redaction import redact_bootstrap_value
from system_status import detect_claude_code_status, detect_codex_status, detect_ollama_status


API_RUNNERS: list[tuple[str, str, str]] = [
    ("openai_api", "OpenAI API", "OPENAI_API_KEY"),
    ("anthropic_api", "Anthropic API", "ANTHROPIC_API_KEY"),
    ("xai_api", "xAI API", "XAI_API_KEY"),
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _probe(
    *,
    runner_id: str,
    label: str,
    available: bool,
    configured: bool,
    auth_status: str,
    install_status: str,
    command_path_text: str | None = None,
    version: str | None = None,
    safe_default: bool = False,
    requires_user_action: bool = False,
    recommended_fix: str | None = None,
    billing_warning: str | None = None,
    models: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return redact_bootstrap_value(
        {
            "runner_id": runner_id,
            "label": label,
            "available": available,
            "configured": configured,
            "auth_status": auth_status,
            "install_status": install_status,
            "command_path": command_path_text,
            "version": version,
            "safe_default": safe_default,
            "requires_user_action": requires_user_action,
            "recommended_fix": recommended_fix,
            "billing_warning": billing_warning,
            "models": list(models or []),
            "details_json": dict(details or {}),
            "checked_at": _utc_now(),
        }
    )


def probe_dry_run() -> dict[str, Any]:
    return _probe(
        runner_id="dry_run",
        label="Dry-run",
        available=True,
        configured=True,
        auth_status="not_required",
        install_status="ready",
        safe_default=True,
        details={"execution_mode": "simulated"},
    )


def probe_codex_cli() -> dict[str, Any]:
    status = detect_codex_status()
    command_info = probe_command("codex")
    path_text = command_info["path"]
    authenticated = bool(status.get("authenticated"))
    available = bool(path_text or status.get("cli_detected"))
    if not available:
        install_status = "missing"
        recommended_fix = "Install Codex CLI and sign in with the local ChatGPT or Codex session."
    elif authenticated:
        install_status = "ready"
        recommended_fix = None
    else:
        install_status = "installed_needs_login"
        recommended_fix = "Run `codex login` or `codex login status` and complete the local sign-in flow."
    return _probe(
        runner_id="codex_cli",
        label="Codex CLI",
        available=available,
        configured=available and authenticated,
        auth_status="authenticated" if authenticated else "unauthenticated",
        install_status=install_status,
        command_path_text=path_text,
        version=status.get("cli_version") or command_info["version"],
        safe_default=available and authenticated,
        requires_user_action=not (available and authenticated),
        recommended_fix=recommended_fix,
        details={
            "login_status": status.get("login_status"),
            "auth_mode": status.get("auth_mode"),
            "mcp_server_count": len(list(status.get("mcp_servers", []))),
            "local_skills_count": len(list(status.get("local_skills", []))),
        },
    )


def probe_ollama(*, endpoint: str | None = None) -> dict[str, Any]:
    status = detect_ollama_status(endpoint)
    command_info = probe_command("ollama")
    path_text = command_info["path"]
    reachable = bool(status.get("reachable"))
    available = bool(path_text or reachable)
    if not available:
        install_status = "missing"
        recommended_fix = "Install Ollama locally if you want a local model runner."
    elif reachable:
        install_status = "ready"
        recommended_fix = None
    else:
        install_status = "installed_not_running"
        recommended_fix = "Start the local Ollama server with `ollama serve` before enabling the runner."
    return _probe(
        runner_id="ollama",
        label="Ollama",
        available=available,
        configured=reachable,
        auth_status="not_required",
        install_status=install_status,
        command_path_text=path_text,
        version=command_info["version"],
        safe_default=reachable,
        requires_user_action=bool(path_text and not reachable),
        recommended_fix=recommended_fix,
        models=[str(item) for item in list(status.get("available_models", []))],
        details={
            "endpoint": status.get("cli_version"),
            "reachable": reachable,
            "summary": status.get("summary"),
        },
    )


def probe_claude_cli() -> dict[str, Any]:
    status = detect_claude_code_status()
    command_info = probe_command("claude")
    path_text = command_info["path"]
    available = bool(path_text or status.get("cli_detected"))
    configured = False
    install_status = "missing"
    recommended_fix = "Install Claude CLI if you want Mission Control to use it."
    if available:
        install_status = "needs_setup"
        recommended_fix = "Finish Claude CLI authentication outside Mission Control, then rerun autowire."
    return _probe(
        runner_id="claude_cli",
        label="Claude CLI",
        available=available,
        configured=configured,
        auth_status="unknown" if available else "unauthenticated",
        install_status=install_status,
        command_path_text=path_text,
        version=status.get("cli_version") or command_info["version"],
        safe_default=False,
        requires_user_action=available,
        recommended_fix=recommended_fix,
        models=[str(item) for item in list(status.get("available_models", []))],
        details={"login_status": status.get("login_status")},
    )


def _api_probe(runner_id: str, label: str, env_key: str) -> dict[str, Any]:
    configured_in_env = bool(os.environ.get(env_key))
    recommended_fix = (
        "API-backed runner is available through external secure environment configuration. Keep it opt-in because it may incur billing."
        if configured_in_env
        else f"Set {env_key} in a secure external environment if you explicitly want this API-backed runner."
    )
    return _probe(
        runner_id=runner_id,
        label=label,
        available=configured_in_env,
        configured=configured_in_env,
        auth_status="authenticated" if configured_in_env else "unauthenticated",
        install_status="external_configured" if configured_in_env else "not_configured",
        safe_default=False,
        requires_user_action=False,
        recommended_fix=recommended_fix,
        billing_warning=f"{label} may incur API billing.",
        details={"env_var": env_key, "secure_storage_supported": False},
    )


def probe_custom_api() -> dict[str, Any]:
    base_url = os.environ.get("MISSION_CONTROL_CUSTOM_API_BASE_URL") or os.environ.get("CUSTOM_API_BASE_URL")
    key_present = bool(os.environ.get("MISSION_CONTROL_CUSTOM_API_KEY") or os.environ.get("CUSTOM_API_KEY"))
    available = bool(base_url)
    configured = bool(base_url and key_present)
    auth_status = "authenticated" if configured else ("unknown" if available else "unauthenticated")
    return _probe(
        runner_id="custom_api",
        label="Custom API",
        available=available,
        configured=configured,
        auth_status=auth_status,
        install_status="external_configured" if configured else ("needs_credentials" if available else "not_configured"),
        safe_default=False,
        requires_user_action=available and not configured,
        recommended_fix="Provide a stable external adapter or secure environment config before enabling this custom API runner."
        if available
        else "Set a custom API base URL and adapter outside Mission Control if you intentionally need one.",
        billing_warning="Custom API runners may incur third-party billing.",
        details={"base_url_present": available, "secure_storage_supported": False},
    )


def probe_runners(*, ollama_endpoint: str | None = None) -> list[dict[str, Any]]:
    probes = [
        probe_dry_run(),
        probe_codex_cli(),
        probe_ollama(endpoint=ollama_endpoint),
        probe_claude_cli(),
    ]
    probes.extend(_api_probe(*runner) for runner in API_RUNNERS)
    probes.append(probe_custom_api())
    return probes


def summarize_runner_status(*, ollama_endpoint: str | None = None) -> dict[str, Any]:
    probes = probe_runners(ollama_endpoint=ollama_endpoint)
    enabled = [probe["runner_id"] for probe in probes if probe["configured"] or probe["runner_id"] == "dry_run"]
    safe_defaults = [probe["runner_id"] for probe in probes if probe["safe_default"]]
    live_ready = [probe["runner_id"] for probe in probes if probe["runner_id"] != "dry_run" and probe["configured"]]
    if live_ready:
        status = "ready"
    elif enabled:
        status = "degraded"
    else:
        status = "failed"
    return {
        "status": status,
        "runners": probes,
        "enabled_runners": enabled,
        "safe_defaults": safe_defaults,
        "checked_at": _utc_now(),
    }
