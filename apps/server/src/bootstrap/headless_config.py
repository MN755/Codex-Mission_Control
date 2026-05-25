from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bootstrap.secret_redaction import redact_bootstrap_value, redaction_status
from config import DEFAULT_BACKEND_HOST, DEFAULT_BACKEND_PORT, REPO_ROOT, RUNTIME_ROOT, get_codex_home


HEADLESS_DIR_NAME = "headless"
HEADLESS_FILE_NAME = "headless.json"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
SUPPORTED_MCP_TRANSPORTS = {"stdio", "disabled"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def headless_root(runtime_path: str | None = None) -> Path:
    runtime_root = Path(runtime_path).expanduser().resolve() if runtime_path else RUNTIME_ROOT
    return runtime_root / HEADLESS_DIR_NAME


def headless_config_path(runtime_path: str | None = None) -> Path:
    return headless_root(runtime_path) / HEADLESS_FILE_NAME


def is_local_host(host: str | None) -> bool:
    return bool(host and host.strip().lower() in LOCAL_HOSTS)


def normalize_local_host(host: str | None) -> str:
    candidate = (host or "").strip()
    return candidate if is_local_host(candidate) else DEFAULT_BACKEND_HOST


def normalize_transport(value: str | None) -> str:
    transport = (value or "stdio").strip().lower()
    return transport if transport in SUPPORTED_MCP_TRANSPORTS else "stdio"


def read_headless_config(runtime_path: str | None = None) -> dict[str, Any] | None:
    path = headless_config_path(runtime_path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def write_headless_config(payload: dict[str, Any], runtime_path: str | None = None) -> dict[str, Any]:
    path = headless_config_path(runtime_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def plugin_paths(install_root: str | Path | None = None) -> list[str]:
    base_root = Path(install_root).expanduser().resolve() if install_root else REPO_ROOT
    paths = [
        (base_root / "plugins" / "mission-control").resolve(),
        (base_root / ".codex" / "plugins" / "mission-control").resolve(),
        (get_codex_home() / "plugins" / "mission-control").resolve(),
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for path in paths:
        text = str(path)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def skills_paths(install_root: str | Path | None = None) -> list[str]:
    base_root = Path(install_root).expanduser().resolve() if install_root else REPO_ROOT
    paths = [
        (base_root / ".codex" / "skills").resolve(),
        (base_root / "plugins" / "mission-control" / "skills").resolve(),
        (get_codex_home() / "skills").resolve(),
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for path in paths:
        text = str(path)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def default_runner_policy() -> dict[str, Any]:
    return {
        "prefer_local_runners": True,
        "fallback_runner": "dry_run",
        "allow_api_runners_without_external_config": False,
        "require_user_approval_for_new_tools": True,
    }


def default_model_policy() -> dict[str, Any]:
    return {
        "codex_cli": "session_default",
        "ollama": "local_default",
        "claude_cli": "provider_default",
        "dry_run": "deterministic",
    }


def safe_mode_defaults() -> dict[str, Any]:
    return {
        "require_all_command_approvals": True,
        "block_destructive_actions": True,
        "disable_deployment_tools": True,
        "disable_external_account_tools_until_approved": True,
        "pause_dynamic_spawning_by_default": False,
    }


def runner_configs_from_probes(probes: list[dict[str, Any]]) -> dict[str, Any]:
    configs: dict[str, Any] = {}
    for probe in probes:
        configs[probe["runner_id"]] = {
            "enabled": bool(probe["configured"] or probe["runner_id"] == "dry_run"),
            "safe_default": bool(probe.get("safe_default")),
            "auth_status": probe.get("auth_status"),
            "install_status": probe.get("install_status"),
            "command_path": probe.get("command_path"),
            "models": list(probe.get("models", [])),
            "billing_warning": probe.get("billing_warning"),
        }
    return redact_bootstrap_value(configs)


def build_headless_config(
    *,
    probes: list[dict[str, Any]],
    install_path: str | None,
    runtime_path: str | None,
    daemon_host: str | None,
    daemon_port: int | None,
    mcp_transport: str | None,
    mcp_port: int | None,
    headless_only: bool,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    existing = existing or {}
    install_root = str((Path(install_path).expanduser().resolve() if install_path else REPO_ROOT))
    runtime_root = str((Path(runtime_path).expanduser().resolve() if runtime_path else RUNTIME_ROOT))
    transport = normalize_transport(mcp_transport or str(existing.get("mcp_transport") or "stdio"))
    runner_configs = runner_configs_from_probes(probes)
    payload = {
        "config_path": str(headless_config_path(runtime_path)),
        "install_id": existing.get("install_id") or uuid.uuid4().hex,
        "install_path": install_root,
        "runtime_path": runtime_root,
        "headless_only": bool(headless_only),
        "dashboard_enabled": False,
        "daemon_host": normalize_local_host(daemon_host or str(existing.get("daemon_host") or DEFAULT_BACKEND_HOST)),
        "daemon_port": int(daemon_port or existing.get("daemon_port") or DEFAULT_BACKEND_PORT),
        "mcp_transport": transport,
        "mcp_port": None,
        "enabled_runners": [probe["runner_id"] for probe in probes if probe["configured"] or probe["runner_id"] == "dry_run"],
        "runner_configs": runner_configs,
        "default_runner_policy": default_runner_policy(),
        "default_model_policy": default_model_policy(),
        "safe_mode_defaults": safe_mode_defaults(),
        "plugin_paths": plugin_paths(install_root),
        "skills_paths": skills_paths(install_root),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "redaction_status": redaction_status(runner_configs),
    }
    return redact_bootstrap_value(payload)
