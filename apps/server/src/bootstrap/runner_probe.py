from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from bootstrap.dependency_probe import probe_command
from bootstrap.secret_redaction import redact_bootstrap_value
from errors import MissionControlError
from provider_adapter_recipes import resolve_adapter_recipe
from system_status import detect_claude_code_status, detect_codex_status, detect_custom_status, detect_ollama_status
from nvidia_support import detect_nvidia_dynamo_status


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
    error: MissionControlError | None = None,
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
            "code": error.code if error is not None else None,
            "severity": error.severity if error is not None else None,
            "breakpoint": error.breakpoint if error is not None else None,
            "retryable": bool(error.retryable) if error is not None else None,
            "user_action_required": bool(error.user_action_required) if error is not None else requires_user_action,
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
    path_text = status.get("cli_path") or command_info["path"]
    authenticated = bool(status.get("authenticated"))
    available = bool(path_text or status.get("cli_detected"))
    if not available:
        install_status = "missing"
        recommended_fix = "Install Codex CLI and sign in with the local ChatGPT or Codex session."
        error = MissionControlError(code="MC-CODEX-CLI-MISSING-001", breakpoint="codex_cli.detect", safe_details={"runner": "codex_cli"})
    elif authenticated:
        install_status = "ready"
        recommended_fix = None
        error = None
    else:
        install_status = "installed_needs_login"
        recommended_fix = "Run `codex login` or `codex login status` and complete the local sign-in flow."
        error = MissionControlError(code="MC-CODEX-LOGIN-UNKNOWN-001", breakpoint="codex_cli.login_status", severity="warning", safe_details={"runner": "codex_cli"})
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
        error=error,
        details={
            "login_status": status.get("login_status"),
            "auth_mode": status.get("auth_mode"),
            "mcp_server_count": len(list(status.get("mcp_servers", []))),
            "local_skills_count": len(list(status.get("local_skills", []))),
        },
    )


def probe_ollama(*, endpoint: str | None = None, adapter_command: str | None = None, adapter_args: list[str] | None = None) -> dict[str, Any]:
    status = detect_ollama_status(endpoint)
    recipe = resolve_adapter_recipe("ollama", adapter_command, adapter_args)
    effective_command = recipe.command if recipe else None
    effective_args = list(recipe.args) if recipe else []
    adapter_status = detect_custom_status(effective_command, effective_args)
    command_info = probe_command("ollama")
    path_text = command_info["path"]
    reachable = bool(status.get("reachable"))
    adapter_ready = bool(adapter_status.get("cli_detected"))
    adapter_configured = bool(effective_command)
    available = bool(path_text or reachable or adapter_ready)
    if not available:
        install_status = "missing"
        recommended_fix = "Install Ollama locally if you want a local model runner."
        error = MissionControlError(code="MC-OLLAMA-CLI-MISSING-001", breakpoint="ollama.detect", severity="warning", safe_details={"runner": "ollama"})
    elif reachable and adapter_ready:
        install_status = "ready"
        recommended_fix = None
        error = None
    elif reachable:
        install_status = "endpoint_ready_needs_adapter"
        recommended_fix = "Add a working local adapter command in Mission Control project settings before expecting live Ollama worker execution."
        error = MissionControlError(code="MC-RUNNER-NONE-AVAILABLE-001", breakpoint="runner.select", severity="warning", safe_details={"runner": "ollama", "endpoint_reachable": True})
    else:
        install_status = "installed_not_running"
        recommended_fix = "Start the local Ollama server with `ollama serve` and keep a working local adapter command configured."
        error = MissionControlError(code="MC-OLLAMA-SERVER-OFFLINE-001", breakpoint="ollama.server_check", severity="warning", safe_details={"runner": "ollama"})
    return _probe(
        runner_id="ollama",
        label="Ollama",
        available=available,
        configured=reachable and adapter_ready,
        auth_status="not_required",
        install_status=install_status,
        command_path_text=path_text,
        version=command_info["version"],
        safe_default=reachable and adapter_ready,
        requires_user_action=bool(path_text and (not reachable or not adapter_ready)) or adapter_configured,
        recommended_fix=recommended_fix,
        error=error,
        models=[str(item) for item in list(status.get("available_models", []))],
        details={
            "endpoint": status.get("cli_version"),
            "reachable": reachable,
            "summary": status.get("summary"),
            "adapter_command": effective_command,
            "adapter_args": effective_args,
            "adapter_recipe_source": recipe.source if recipe else "none",
            "adapter_ready": adapter_ready,
            "adapter_configured": adapter_configured,
        },
    )


def probe_claude_cli() -> dict[str, Any]:
    status = detect_claude_code_status()
    command_info = probe_command("claude")
    path_text = status.get("cli_path") or command_info["path"]
    available = bool(path_text or status.get("cli_detected"))
    execution_available = bool(status.get("cli_execution_available"))
    configured = execution_available
    install_status = "missing"
    recommended_fix = "Install Claude CLI if you want Mission Control to use it."
    if available:
        if execution_available:
            install_status = "ready_auth_unknown"
            recommended_fix = "Claude CLI is executable. If live runs fail, verify the interactive Claude auth state in the host environment and then retry."
            error = MissionControlError(
                code="MC-CLAUDE-AUTH-UNKNOWN-001",
                breakpoint="claude_cli.auth_status",
                severity="warning",
                safe_details={"runner": "claude_cli"},
            )
        else:
            install_status = "needs_setup"
            recommended_fix = "Finish Claude CLI setup outside Mission Control, or set MISSION_CONTROL_CLAUDE_PATH / CLAUDE_CLI_PATH if the executable is installed in a non-standard location."
            error = MissionControlError(
                code="MC-CLAUDE-AUTH-UNKNOWN-001",
                breakpoint="claude_cli.auth_status",
                severity="warning",
                safe_details={"runner": "claude_cli"},
            )
    else:
        error = MissionControlError(code="MC-CLAUDE-CLI-MISSING-001", breakpoint="claude_cli.detect", severity="warning", safe_details={"runner": "claude_cli"})
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
        requires_user_action=available and not execution_available,
        recommended_fix=recommended_fix,
        error=error,
        models=[str(item) for item in list(status.get("available_models", []))],
        details={"login_status": status.get("login_status"), "cli_execution_available": execution_available},
    )


def probe_nvidia_dynamo(*, endpoint: str | None = None, adapter_command: str | None = None, adapter_args: list[str] | None = None) -> dict[str, Any]:
    status = detect_nvidia_dynamo_status(endpoint)
    recipe = resolve_adapter_recipe("nvidia_dynamo", adapter_command, adapter_args)
    effective_command = recipe.command if recipe else None
    effective_args = list(recipe.args) if recipe else []
    adapter_status = detect_custom_status(effective_command, effective_args)
    adapter_ready = bool(adapter_status.get("cli_detected"))
    adapter_configured = bool(effective_command)
    reachable = bool(status.get("reachable"))
    auth_required = bool(status.get("auth_required"))
    api_key_configured = bool(status.get("api_key_configured"))
    available = reachable or adapter_ready or adapter_configured or bool(status.get("endpoint_configured"))
    if reachable and adapter_ready and (not auth_required or api_key_configured):
        install_status = "ready"
        recommended_fix = None
        error = None
    elif reachable and adapter_ready and auth_required and not api_key_configured:
        install_status = "auth_required"
        recommended_fix = "Set NVIDIA_DYNAMO_API_KEY or MISSION_CONTROL_NVIDIA_DYNAMO_API_KEY before routing Mission Control workers into this Dynamo frontend."
        error = MissionControlError(code="MC-API-KEY-MISSING-001", breakpoint="api_provider.auth_check", severity="warning", safe_details={"runner": "nvidia_dynamo"})
    elif reachable:
        install_status = "endpoint_ready_needs_adapter"
        recommended_fix = "Keep the Dynamo frontend reachable and make sure the Mission Control API adapter recipe remains executable."
        error = MissionControlError(code="MC-RUNNER-NONE-AVAILABLE-001", breakpoint="runner.select", severity="warning", safe_details={"runner": "nvidia_dynamo"})
    else:
        install_status = "not_configured" if not status.get("endpoint_configured") else "installed_not_running"
        recommended_fix = "Expose an NVIDIA Dynamo OpenAI-compatible frontend and keep the Mission Control adapter recipe available before selecting this provider."
        error = MissionControlError(code="MC-RUNNER-NONE-AVAILABLE-001", breakpoint="runner.select", severity="warning", safe_details={"runner": "nvidia_dynamo"})
    return _probe(
        runner_id="nvidia_dynamo",
        label="NVIDIA Dynamo",
        available=available,
        configured=reachable and adapter_ready and (not auth_required or api_key_configured),
        auth_status="authenticated" if api_key_configured else "unauthenticated" if auth_required else "optional",
        install_status=install_status,
        safe_default=False,
        requires_user_action=not (reachable and adapter_ready),
        recommended_fix=recommended_fix,
        billing_warning="NVIDIA Dynamo may run on metered or shared GPU infrastructure depending on deployment.",
        error=error,
        models=[str(item) for item in list(status.get("available_models", []))],
        details={
            "endpoint": status.get("endpoint"),
            "reachable": reachable,
            "summary": status.get("summary"),
            "adapter_command": effective_command,
            "adapter_args": effective_args,
            "adapter_recipe_source": recipe.source if recipe else "none",
            "adapter_ready": adapter_ready,
            "adapter_configured": adapter_configured,
            "api_key_configured": api_key_configured,
            "auth_required": auth_required,
        },
    )


def _api_probe(runner_id: str, label: str, env_key: str, *, adapter_command: str | None = None, adapter_args: list[str] | None = None) -> dict[str, Any]:
    configured_in_env = bool(os.environ.get(env_key))
    recipe = resolve_adapter_recipe(runner_id, adapter_command, adapter_args)
    effective_command = recipe.command if recipe else None
    effective_args = list(recipe.args) if recipe else []
    adapter_status = detect_custom_status(effective_command, effective_args)
    adapter_ready = bool(adapter_status.get("cli_detected"))
    adapter_configured = bool(effective_command)
    recommended_fix = (
        "API-backed runner is available through external secure environment configuration. Keep it opt-in because it may incur billing."
        if configured_in_env and adapter_ready
        else "Set both the external API credentials and a working local adapter command before enabling this API-backed runner."
    )
    error = MissionControlError(
        code="MC-API-BILLING-WARNING-001" if configured_in_env and adapter_ready else "MC-API-KEY-MISSING-001",
        breakpoint="api_provider.auth_check" if not configured_in_env else "runner.select",
        severity="warning",
        safe_details={"runner": runner_id, "env_var": env_key},
    )
    return _probe(
        runner_id=runner_id,
        label=label,
        available=configured_in_env or adapter_ready or adapter_configured,
        configured=configured_in_env and adapter_ready,
        auth_status="authenticated" if configured_in_env else "unauthenticated",
        install_status="external_configured" if configured_in_env and adapter_ready else "needs_adapter" if configured_in_env else "not_configured",
        safe_default=False,
        requires_user_action=configured_in_env or adapter_configured,
        recommended_fix=recommended_fix,
        billing_warning=f"{label} may incur API billing.",
        error=error,
        details={
            "env_var": env_key,
            "secure_storage_supported": False,
            "adapter_ready": adapter_ready,
            "adapter_configured": adapter_configured,
            "adapter_command": effective_command,
            "adapter_args": effective_args,
            "adapter_recipe_source": recipe.source if recipe else "none",
        },
    )


def probe_runners(
    *,
    ollama_endpoint: str | None = None,
    nvidia_dynamo_endpoint: str | None = None,
    adapter_command: str | None = None,
    adapter_args: list[str] | None = None,
) -> list[dict[str, Any]]:
    probes = [
        probe_dry_run(),
        probe_codex_cli(),
        probe_ollama(endpoint=ollama_endpoint, adapter_command=adapter_command, adapter_args=adapter_args),
        probe_nvidia_dynamo(endpoint=nvidia_dynamo_endpoint, adapter_command=adapter_command, adapter_args=adapter_args),
        probe_claude_cli(),
    ]
    probes.extend(_api_probe(*runner, adapter_command=adapter_command, adapter_args=adapter_args) for runner in API_RUNNERS)
    return probes


def summarize_runner_status(
    *,
    ollama_endpoint: str | None = None,
    nvidia_dynamo_endpoint: str | None = None,
    adapter_command: str | None = None,
    adapter_args: list[str] | None = None,
) -> dict[str, Any]:
    probes = probe_runners(
        ollama_endpoint=ollama_endpoint,
        nvidia_dynamo_endpoint=nvidia_dynamo_endpoint,
        adapter_command=adapter_command,
        adapter_args=adapter_args,
    )
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
