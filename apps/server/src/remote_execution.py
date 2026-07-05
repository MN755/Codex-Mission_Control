from __future__ import annotations

import json
import shlex
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from integration_registry import AUTHORITATIVE_CONNECTION_SOURCES, list_connections, normalize_integration_registry
from result_normalization import classify_evidence_artifacts


REMOTE_EXECUTION_REGISTRY_VERSION = 1
SUPPORTED_TRANSPORTS = {"ssh", "lan_ssh", "tailscale_ssh"}
SUPPORTED_SHELL_FAMILIES = {"posix", "powershell"}
SUPPORTED_OS_FAMILIES = {"windows", "linux", "macos", "unknown"}
SUPPORTED_RUNNER_FAMILIES = {
    "external_adapter",
    "local_runner",
    "plain_ssh_runner",
    "tailscale_ssh_runner",
    "windows_agent_runner",
    "macos_agent_runner",
    "lan_appliance_runner",
    "codex_cli",
    "claude_code_cli",
}
SUPPORTED_TRUST_LEVELS = {"trusted", "limited", "quarantined"}


def _normalized_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalized_str_list(values: Iterable[Any] | None) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        normalized = _normalized_text(value)
        if normalized is not None and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _normalized_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _normalized_int(value: Any, *, default: int | None = None, minimum: int | None = None) -> int | None:
    if value in {None, ""}:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return minimum
    return parsed


def _normalized_transport(value: Any) -> str:
    normalized = (_normalized_text(value) or "ssh").lower()
    return normalized if normalized in SUPPORTED_TRANSPORTS else "ssh"


def _normalized_shell_family(value: Any, *, os_family: str) -> str:
    normalized = (_normalized_text(value) or ("powershell" if os_family == "windows" else "posix")).lower()
    return normalized if normalized in SUPPORTED_SHELL_FAMILIES else ("powershell" if os_family == "windows" else "posix")


def _normalized_os_family(value: Any) -> str:
    normalized = (_normalized_text(value) or "unknown").lower()
    if normalized in {"darwin", "mac"}:
        normalized = "macos"
    return normalized if normalized in SUPPORTED_OS_FAMILIES else "unknown"


def _normalized_trust_level(value: Any) -> str:
    normalized = (_normalized_text(value) or "limited").lower()
    return normalized if normalized in SUPPORTED_TRUST_LEVELS else "limited"


def _normalized_runner_families(values: Iterable[Any] | None) -> list[str]:
    families = [item for item in _normalized_str_list(values) if item in SUPPORTED_RUNNER_FAMILIES]
    return families or ["external_adapter"]


def empty_remote_execution_registry() -> dict[str, Any]:
    return {"version": REMOTE_EXECUTION_REGISTRY_VERSION, "targets": []}


def normalize_remote_execution_registry(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw_targets = list((payload or {}).get("targets") or [])
    normalized_targets = [_normalize_remote_target(item) for item in raw_targets if isinstance(item, dict)]
    return {
        "version": REMOTE_EXECUTION_REGISTRY_VERSION,
        "targets": sorted(normalized_targets, key=lambda item: (str(item.get("label") or "").lower(), str(item.get("id") or "").lower())),
    }


def empty_remote_execution_policy() -> dict[str, Any]:
    return {
        "enabled": False,
        "preferred_target_id": None,
        "required_runner_family": "external_adapter",
        "required_tags": [],
        "required_capabilities": [],
        "allowed_trust_levels": [],
        "required_toolchains": [],
        "required_command_families": [],
        "required_result_formats": [],
        "allowed_transports": [],
        "allowed_os_families": [],
        "require_write_access": True,
        "fallback_to_local": True,
        "require_target_workspace_root": False,
        "artifact_sync_enabled": True,
        "artifact_required": False,
        "artifact_path_allowlist": [],
        "required_connector_families": [],
        "allow_host_integrated_connectors": True,
        "require_connector_authority": False,
        "require_probe_ready": False,
        "require_session_recording": False,
        "required_repo_roots": [],
        "required_path_prefixes": [],
        "minimum_command_runtime_seconds": None,
        "minimum_file_transfer_quota_mb": None,
    }


def empty_device_broker_request() -> dict[str, Any]:
    return {
        "request_id": None,
        "intent": None,
        "preferred_target_id": None,
        "required_runner_families": [],
        "required_os_families": [],
        "required_architectures": [],
        "require_gpu": False,
        "required_gpu_models": [],
        "required_toolchains": [],
        "required_installed_runtimes": [],
        "required_command_families": [],
        "required_result_formats": [],
        "required_connector_families": [],
        "required_capabilities": [],
        "required_tags": [],
        "allowed_trust_levels": [],
        "allowed_transports": [],
        "require_write_access": True,
        "require_probe_ready": True,
        "require_session_recording": False,
        "require_target_workspace_root": False,
        "required_repo_roots": [],
        "required_path_prefixes": [],
        "minimum_command_runtime_seconds": None,
        "minimum_file_transfer_quota_mb": None,
        "dry_run": True,
    }


def normalize_remote_execution_policy(payload: dict[str, Any] | None) -> dict[str, Any]:
    base = empty_remote_execution_policy()
    raw = dict(payload or {})
    base["enabled"] = _normalized_bool(raw.get("enabled"), default=base["enabled"])
    base["preferred_target_id"] = _normalized_text(raw.get("preferred_target_id"))
    required_runner_family = _normalized_text(raw.get("required_runner_family")) or "external_adapter"
    base["required_runner_family"] = required_runner_family if required_runner_family in SUPPORTED_RUNNER_FAMILIES else "external_adapter"
    base["required_tags"] = _normalized_str_list(raw.get("required_tags"))
    base["required_capabilities"] = _normalized_str_list(raw.get("required_capabilities"))
    base["allowed_trust_levels"] = [item for item in _normalized_str_list(raw.get("allowed_trust_levels")) if item in SUPPORTED_TRUST_LEVELS]
    base["required_toolchains"] = _normalized_str_list(raw.get("required_toolchains"))
    base["required_command_families"] = _normalized_str_list(raw.get("required_command_families"))
    base["required_result_formats"] = _normalized_str_list(raw.get("required_result_formats"))
    base["allowed_transports"] = [item for item in _normalized_str_list(raw.get("allowed_transports")) if item in SUPPORTED_TRANSPORTS]
    base["allowed_os_families"] = [_normalized_os_family(item) for item in raw.get("allowed_os_families") or [] if _normalized_os_family(item) != "unknown"]
    base["require_write_access"] = _normalized_bool(raw.get("require_write_access"), default=True)
    base["fallback_to_local"] = _normalized_bool(raw.get("fallback_to_local"), default=True)
    base["require_target_workspace_root"] = _normalized_bool(raw.get("require_target_workspace_root"), default=False)
    base["artifact_sync_enabled"] = _normalized_bool(raw.get("artifact_sync_enabled"), default=True)
    base["artifact_required"] = _normalized_bool(raw.get("artifact_required"), default=False)
    base["artifact_path_allowlist"] = _normalized_str_list(raw.get("artifact_path_allowlist"))
    base["required_connector_families"] = _normalized_str_list(raw.get("required_connector_families"))
    base["allow_host_integrated_connectors"] = _normalized_bool(raw.get("allow_host_integrated_connectors"), default=True)
    base["require_connector_authority"] = _normalized_bool(raw.get("require_connector_authority"), default=False)
    base["require_probe_ready"] = _normalized_bool(raw.get("require_probe_ready"), default=False)
    base["require_session_recording"] = _normalized_bool(raw.get("require_session_recording"), default=False)
    base["required_repo_roots"] = _normalized_str_list(raw.get("required_repo_roots"))
    base["required_path_prefixes"] = _normalized_str_list(raw.get("required_path_prefixes"))
    base["minimum_command_runtime_seconds"] = _normalized_int(raw.get("minimum_command_runtime_seconds"), default=None, minimum=1)
    base["minimum_file_transfer_quota_mb"] = _normalized_int(raw.get("minimum_file_transfer_quota_mb"), default=None, minimum=1)
    return base


def normalize_device_broker_request(
    payload: dict[str, Any] | None,
    *,
    policy_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = empty_device_broker_request()
    raw = dict(payload or {})
    policy = normalize_remote_execution_policy(policy_payload)

    def _list_value(key: str, fallback: Iterable[Any]) -> list[str]:
        return _normalized_str_list(raw.get(key) if key in raw else fallback)

    base["request_id"] = _normalized_text(raw.get("request_id"))
    base["intent"] = _normalized_text(raw.get("intent"))
    base["preferred_target_id"] = _normalized_text(raw.get("preferred_target_id")) or _normalized_text(
        policy.get("preferred_target_id")
    )
    base["required_runner_families"] = [
        item
        for item in _list_value(
            "required_runner_families",
            [policy.get("required_runner_family")] if policy.get("required_runner_family") else [],
        )
        if item in SUPPORTED_RUNNER_FAMILIES
    ]
    base["required_os_families"] = [
        item
        for item in (_normalized_os_family(value) for value in (raw.get("required_os_families") or []))
        if item != "unknown"
    ]
    base["required_architectures"] = _list_value("required_architectures", [])
    base["require_gpu"] = _normalized_bool(raw.get("require_gpu"), default=False)
    base["required_gpu_models"] = _list_value("required_gpu_models", [])
    base["required_toolchains"] = _list_value("required_toolchains", policy.get("required_toolchains"))
    base["required_installed_runtimes"] = _list_value("required_installed_runtimes", [])
    base["required_command_families"] = _list_value("required_command_families", policy.get("required_command_families"))
    base["required_result_formats"] = _list_value("required_result_formats", policy.get("required_result_formats"))
    base["required_connector_families"] = _list_value(
        "required_connector_families",
        policy.get("required_connector_families"),
    )
    base["required_capabilities"] = _list_value("required_capabilities", policy.get("required_capabilities"))
    base["required_tags"] = _list_value("required_tags", policy.get("required_tags"))
    base["allowed_trust_levels"] = [
        item
        for item in _list_value("allowed_trust_levels", policy.get("allowed_trust_levels"))
        if item in SUPPORTED_TRUST_LEVELS
    ]
    base["allowed_transports"] = [
        item
        for item in _list_value("allowed_transports", policy.get("allowed_transports"))
        if item in SUPPORTED_TRANSPORTS
    ]
    base["require_write_access"] = _normalized_bool(
        raw.get("require_write_access"),
        default=bool(policy.get("require_write_access", True)),
    )
    base["require_probe_ready"] = _normalized_bool(
        raw.get("require_probe_ready"),
        default=bool(policy.get("require_probe_ready", False)) or True,
    )
    base["require_session_recording"] = _normalized_bool(
        raw.get("require_session_recording"),
        default=bool(policy.get("require_session_recording", False)),
    )
    base["require_target_workspace_root"] = _normalized_bool(
        raw.get("require_target_workspace_root"),
        default=bool(policy.get("require_target_workspace_root", False)),
    )
    base["required_repo_roots"] = _list_value("required_repo_roots", policy.get("required_repo_roots"))
    base["required_path_prefixes"] = _list_value("required_path_prefixes", policy.get("required_path_prefixes"))
    base["minimum_command_runtime_seconds"] = _normalized_int(
        raw.get("minimum_command_runtime_seconds")
        if "minimum_command_runtime_seconds" in raw
        else policy.get("minimum_command_runtime_seconds"),
        default=None,
        minimum=1,
    )
    base["minimum_file_transfer_quota_mb"] = _normalized_int(
        raw.get("minimum_file_transfer_quota_mb")
        if "minimum_file_transfer_quota_mb" in raw
        else policy.get("minimum_file_transfer_quota_mb"),
        default=None,
        minimum=1,
    )
    base["dry_run"] = _normalized_bool(raw.get("dry_run"), default=True)
    return base


def _normalize_remote_target(payload: dict[str, Any]) -> dict[str, Any]:
    os_family = _normalized_os_family(payload.get("os_family"))
    label = _normalized_text(payload.get("label")) or "Remote Target"
    host = _normalized_text(payload.get("host")) or "unknown-host"
    transport = _normalized_transport(payload.get("transport"))
    target_id = _normalized_text(payload.get("id")) or _slugify_remote_target_id(label=label, host=host)
    ssh_user = _normalized_text(payload.get("ssh_user"))
    ssh_port = _normalized_int(payload.get("ssh_port"), default=22, minimum=1)
    workspace_root = _normalized_text(payload.get("workspace_root"))
    runner_command = _normalized_text(payload.get("runner_command")) or _normalized_text(payload.get("adapter_command"))
    runner_args = _normalized_str_list(payload.get("runner_args")) or _normalized_str_list(payload.get("adapter_args"))
    adapter_command = _normalized_text(payload.get("adapter_command")) or runner_command
    adapter_args = _normalized_str_list(payload.get("adapter_args")) or list(runner_args)
    tags = _normalized_str_list(payload.get("tags"))
    capabilities = _normalized_str_list(payload.get("capabilities"))
    runner_families = _normalized_runner_families(payload.get("runner_families"))
    trust_level = _normalized_trust_level(payload.get("trust_level"))
    enabled = _normalized_bool(payload.get("enabled"), default=True)
    allow_write = _normalized_bool(payload.get("allow_write"), default=True)
    shell_family = _normalized_shell_family(payload.get("shell_family"), os_family=os_family)
    description = _normalized_text(payload.get("description"))
    last_probe_status = _normalized_text(payload.get("last_probe_status")) or "unknown"
    last_seen_at = _normalized_text(payload.get("last_seen_at"))
    notes = _normalized_str_list(payload.get("notes"))
    artifact_roots = _normalized_str_list(payload.get("artifact_roots"))
    connector_families = _normalized_str_list(payload.get("connector_families"))
    toolchains = _normalized_str_list(payload.get("toolchains"))
    installed_runtimes = _normalized_str_list(payload.get("installed_runtimes"))
    command_families = _normalized_str_list(payload.get("command_families"))
    result_formats = _normalized_str_list(payload.get("result_formats"))
    allowed_repo_roots = _normalized_str_list(payload.get("allowed_repo_roots"))
    allowed_path_prefixes = _normalized_str_list(payload.get("allowed_path_prefixes"))
    return {
        "id": target_id,
        "label": label,
        "description": description,
        "transport": transport,
        "host": host,
        "ssh_user": ssh_user,
        "ssh_port": ssh_port,
        "os_family": os_family,
        "shell_family": shell_family,
        "architecture": _normalized_text(payload.get("architecture")) or "unknown",
        "workspace_root": workspace_root,
        "runner_command": runner_command,
        "runner_args": runner_args,
        "adapter_command": adapter_command,
        "adapter_args": adapter_args,
        "tags": tags,
        "capabilities": capabilities,
        "runner_families": runner_families,
        "trust_level": trust_level,
        "enabled": enabled,
        "allow_write": allow_write,
        "gpu": _normalized_text(payload.get("gpu")),
        "toolchains": toolchains,
        "installed_runtimes": installed_runtimes,
        "command_families": command_families,
        "result_formats": result_formats,
        "session_recording_enabled": _normalized_bool(payload.get("session_recording_enabled"), default=False),
        "max_command_runtime_seconds": _normalized_int(payload.get("max_command_runtime_seconds"), default=None, minimum=1),
        "file_transfer_quota_mb": _normalized_int(payload.get("file_transfer_quota_mb"), default=None, minimum=1),
        "allowed_repo_roots": allowed_repo_roots,
        "allowed_path_prefixes": allowed_path_prefixes,
        "artifact_roots": artifact_roots,
        "connector_families": connector_families,
        "last_probe_status": last_probe_status,
        "last_seen_at": last_seen_at,
        "notes": notes,
    }


def _slugify_remote_target_id(*, label: str, host: str) -> str:
    source = f"{label}-{host}".lower()
    slug = "".join(ch if ch.isalnum() else "-" for ch in source).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "remote-target"


def list_remote_targets(registry_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list(normalize_remote_execution_registry(registry_payload).get("targets") or [])


def get_remote_target(registry_payload: dict[str, Any] | None, target_id: str) -> dict[str, Any] | None:
    normalized_id = _normalized_text(target_id)
    if normalized_id is None:
        return None
    return next((item for item in list_remote_targets(registry_payload) if item["id"] == normalized_id), None)


def upsert_remote_target(registry_payload: dict[str, Any] | None, target_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = normalize_remote_execution_registry(registry_payload)
    target = _normalize_remote_target(target_payload)
    targets = [item for item in normalized["targets"] if item["id"] != target["id"]]
    targets.append(target)
    updated = normalize_remote_execution_registry({"version": REMOTE_EXECUTION_REGISTRY_VERSION, "targets": targets})
    return updated, target


def delete_remote_target(registry_payload: dict[str, Any] | None, target_id: str) -> tuple[dict[str, Any], bool]:
    normalized_id = _normalized_text(target_id)
    if normalized_id is None:
        return normalize_remote_execution_registry(registry_payload), False
    normalized = normalize_remote_execution_registry(registry_payload)
    targets = [item for item in normalized["targets"] if item["id"] != normalized_id]
    removed = len(targets) != len(normalized["targets"])
    return normalize_remote_execution_registry({"version": REMOTE_EXECUTION_REGISTRY_VERSION, "targets": targets}), removed


def remote_transport_client_available(transport: str) -> bool:
    normalized = _normalized_transport(transport)
    if normalized in {"ssh", "lan_ssh"}:
        return shutil.which("ssh") is not None
    if normalized == "tailscale_ssh":
        return shutil.which("tailscale") is not None
    return False


def summarize_remote_execution_registry(registry_payload: dict[str, Any] | None) -> dict[str, Any]:
    targets = list_remote_targets(registry_payload)
    enabled = [item for item in targets if item.get("enabled")]
    unknown_probe = [item for item in enabled if item.get("last_probe_status") == "unknown"]
    failed_probe = [item for item in enabled if item.get("last_probe_status") == "failed"]
    ready = [
        item
        for item in enabled
        if item.get("last_probe_status") in {"ready", "reachable"} and remote_transport_client_available(str(item.get("transport") or "ssh"))
    ]
    return {
        "target_count": len(targets),
        "enabled_target_count": len(enabled),
        "ready_target_count": len(ready),
        "unknown_probe_target_count": len(unknown_probe),
        "failed_probe_target_count": len(failed_probe),
        "transport_counts": _count_values(item.get("transport") for item in targets),
        "os_family_counts": _count_values(item.get("os_family") for item in targets),
        "runner_family_counts": _count_values(family for item in targets for family in list(item.get("runner_families") or [])),
        "ready_target_ids": [str(item.get("id")) for item in ready],
    }


def build_remote_capability_index(registry_payload: dict[str, Any] | None) -> dict[str, Any]:
    targets = list_remote_targets(registry_payload)
    rows: list[dict[str, Any]] = []
    for target in targets:
        transport = str(target.get("transport") or "ssh")
        probe_status = str(target.get("last_probe_status") or "unknown")
        rows.append(
            {
                "target_id": str(target.get("id") or ""),
                "label": str(target.get("label") or ""),
                "transport": transport,
                "host": str(target.get("host") or ""),
                "os_family": str(target.get("os_family") or "unknown"),
                "architecture": str(target.get("architecture") or "unknown"),
                "gpu": _normalized_text(target.get("gpu")),
                "trust_level": str(target.get("trust_level") or "limited"),
                "workspace_root": _normalized_text(target.get("workspace_root")),
                "capabilities": _normalized_str_list(target.get("capabilities")),
                "tags": _normalized_str_list(target.get("tags")),
                "runner_families": _normalized_str_list(target.get("runner_families")),
                "runner_command": _normalized_text(target.get("runner_command"))
                or _normalized_text(target.get("adapter_command")),
                "runner_args": _normalized_str_list(target.get("runner_args"))
                or _normalized_str_list(target.get("adapter_args")),
                "adapter_command": _normalized_text(target.get("adapter_command")),
                "toolchains": _normalized_str_list(target.get("toolchains")),
                "installed_runtimes": _normalized_str_list(target.get("installed_runtimes")),
                "command_families": _normalized_str_list(target.get("command_families")),
                "result_formats": _normalized_str_list(target.get("result_formats")),
                "connector_families": _normalized_str_list(target.get("connector_families")),
                "artifact_roots": _normalized_str_list(target.get("artifact_roots")),
                "allowed_repo_roots": _normalized_str_list(target.get("allowed_repo_roots")),
                "allowed_path_prefixes": _normalized_str_list(target.get("allowed_path_prefixes")),
                "session_recording_enabled": bool(target.get("session_recording_enabled")),
                "max_command_runtime_seconds": _normalized_int(
                    target.get("max_command_runtime_seconds"),
                    default=None,
                    minimum=1,
                ),
                "file_transfer_quota_mb": _normalized_int(
                    target.get("file_transfer_quota_mb"),
                    default=None,
                    minimum=1,
                ),
                "probe_status": probe_status,
                "ready": probe_status in {"ready", "reachable"} and remote_transport_client_available(transport),
            }
        )
    rows.sort(key=lambda item: (str(item.get("label") or "").lower(), str(item.get("target_id") or "").lower()))
    return {
        "target_count": len(rows),
        "ready_target_count": len([item for item in rows if item.get("ready")]),
        "toolchain_counts": _count_values(toolchain for item in rows for toolchain in list(item.get("toolchains") or [])),
        "installed_runtime_counts": _count_values(
            runtime for item in rows for runtime in list(item.get("installed_runtimes") or [])
        ),
        "command_family_counts": _count_values(family for item in rows for family in list(item.get("command_families") or [])),
        "result_format_counts": _count_values(fmt for item in rows for fmt in list(item.get("result_formats") or [])),
        "gpu_counts": _count_values(item.get("gpu") for item in rows),
        "trust_level_counts": _count_values(item.get("trust_level") for item in rows),
        "connector_family_counts": _count_values(family for item in rows for family in list(item.get("connector_families") or [])),
        "targets": rows,
    }


def _count_values(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        normalized = _normalized_text(value)
        if normalized is None:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    return counts


def _missing_required_values(required: Iterable[Any], available: Iterable[Any]) -> list[str]:
    available_set = {item for item in _normalized_str_list(available)}
    missing: list[str] = []
    for value in required:
        normalized = _normalized_text(value)
        if normalized is None or normalized in available_set or normalized in missing:
            continue
        missing.append(normalized)
    return missing


def _broker_candidate_requirement_gaps(
    *,
    request: dict[str, Any],
    target: dict[str, Any],
    transport: str,
    probe_status: str,
    ready: bool,
    target_repo_roots: list[str],
    target_path_prefixes: list[str],
    target_toolchains: set[str],
    target_installed_runtimes: set[str],
    target_command_families: set[str],
    target_result_formats: set[str],
    target_connector_families: set[str],
    target_capabilities: set[str],
    target_tags: set[str],
    target_runner_families: set[str],
    target_command_runtime_seconds: int | None,
    target_file_transfer_quota_mb: int | None,
) -> dict[str, Any]:
    gaps: dict[str, Any] = {}

    missing_runner_families = _missing_required_values(request["required_runner_families"], target_runner_families)
    if missing_runner_families:
        gaps["runner_families"] = missing_runner_families
    if request["required_os_families"]:
        target_os_family = str(target.get("os_family") or "unknown")
        if target_os_family not in set(request["required_os_families"]):
            gaps["os_families"] = _normalized_str_list(request["required_os_families"])
    if request["required_architectures"]:
        target_architecture = str(target.get("architecture") or "unknown")
        if target_architecture not in set(request["required_architectures"]):
            gaps["architectures"] = _normalized_str_list(request["required_architectures"])
    if request["require_gpu"] and not (_normalized_text(target.get("gpu")) or "gpu" in target_capabilities):
        gaps["gpu"] = ["required"]
    if request["required_gpu_models"]:
        target_gpu = str(target.get("gpu") or "").strip().lower()
        missing_gpu_models = [model for model in request["required_gpu_models"] if model not in target_gpu]
        if missing_gpu_models:
            gaps["gpu_models"] = _missing_required_values(missing_gpu_models, [])

    missing_toolchains = _missing_required_values(request["required_toolchains"], target_toolchains)
    if missing_toolchains:
        gaps["toolchains"] = missing_toolchains
    missing_installed_runtimes = _missing_required_values(
        request["required_installed_runtimes"],
        target_installed_runtimes,
    )
    if missing_installed_runtimes:
        gaps["installed_runtimes"] = missing_installed_runtimes
    missing_command_families = _missing_required_values(request["required_command_families"], target_command_families)
    if missing_command_families:
        gaps["command_families"] = missing_command_families
    missing_result_formats = _missing_required_values(request["required_result_formats"], target_result_formats)
    if missing_result_formats:
        gaps["result_formats"] = missing_result_formats
    missing_connector_families = _missing_required_values(
        request["required_connector_families"],
        target_connector_families,
    )
    if missing_connector_families:
        gaps["connector_families"] = missing_connector_families
    missing_capabilities = _missing_required_values(request["required_capabilities"], target_capabilities)
    if missing_capabilities:
        gaps["capabilities"] = missing_capabilities
    missing_tags = _missing_required_values(request["required_tags"], target_tags)
    if missing_tags:
        gaps["tags"] = missing_tags

    allowed_trust_levels = set(request["allowed_trust_levels"])
    if allowed_trust_levels:
        target_trust_level = str(target.get("trust_level") or "limited")
        if target_trust_level not in allowed_trust_levels:
            gaps["trust_levels"] = _normalized_str_list(request["allowed_trust_levels"])
    allowed_transports = set(request["allowed_transports"])
    if allowed_transports and transport not in allowed_transports:
        gaps["transports"] = _normalized_str_list(request["allowed_transports"])
    if request["require_write_access"] and not bool(target.get("allow_write")):
        gaps["write_access"] = ["required"]
    if request["require_session_recording"] and not bool(target.get("session_recording_enabled")):
        gaps["session_recording"] = ["required"]
    if request["require_target_workspace_root"] and not _normalized_text(target.get("workspace_root")):
        gaps["workspace_root"] = ["required"]
    if request["required_repo_roots"] and not _required_prefixes_satisfied(
        request["required_repo_roots"],
        target_repo_roots,
    ):
        gaps["repo_roots"] = _normalized_str_list(request["required_repo_roots"])
    if request["required_path_prefixes"] and not _required_prefixes_satisfied(
        request["required_path_prefixes"],
        target_path_prefixes,
    ):
        gaps["path_prefixes"] = _normalized_str_list(request["required_path_prefixes"])
    if request["minimum_command_runtime_seconds"] is not None and (
        target_command_runtime_seconds is None
        or target_command_runtime_seconds < request["minimum_command_runtime_seconds"]
    ):
        gaps["command_runtime_seconds"] = {
            "required": int(request["minimum_command_runtime_seconds"]),
            "available": target_command_runtime_seconds,
        }
    if request["minimum_file_transfer_quota_mb"] is not None and (
        target_file_transfer_quota_mb is None
        or target_file_transfer_quota_mb < request["minimum_file_transfer_quota_mb"]
    ):
        gaps["file_transfer_quota_mb"] = {
            "required": int(request["minimum_file_transfer_quota_mb"]),
            "available": target_file_transfer_quota_mb,
        }
    if not remote_transport_client_available(transport):
        gaps["transport_client"] = [transport]
    if probe_status == "failed":
        gaps["probe_status"] = ["failed"]
    elif request["require_probe_ready"] and not ready:
        gaps["probe_status"] = [probe_status or "unknown"]

    return gaps


def _build_device_broker_availability_diagnostics(
    *,
    request: dict[str, Any],
    candidates: list[dict[str, Any]],
    blocking_reasons: list[str],
    eligible_target_count: int,
    ready_candidate_count: int,
) -> dict[str, Any]:
    rejection_reason_counts = _count_values(
        reason
        for candidate in candidates
        for reason in list(candidate.get("rejected_reasons") or [])
    )
    requirement_gap_counts: dict[str, dict[str, int]] = {}
    for candidate in candidates:
        for gap_name, gap_value in dict(candidate.get("requirement_gaps") or {}).items():
            normalized_gap_values: list[str] = []
            if isinstance(gap_value, dict):
                required_value = _normalized_text(gap_value.get("required"))
                available_value = _normalized_text(gap_value.get("available"))
                if required_value is not None:
                    normalized_gap_values.append(f"required:{required_value}")
                if available_value is not None:
                    normalized_gap_values.append(f"available:{available_value}")
            elif isinstance(gap_value, Iterable) and not isinstance(gap_value, (str, bytes)):
                normalized_gap_values.extend(_normalized_str_list(gap_value))
            else:
                normalized = _normalized_text(gap_value)
                if normalized is not None:
                    normalized_gap_values.append(normalized)
            if not normalized_gap_values:
                continue
            bucket = requirement_gap_counts.setdefault(str(gap_name), {})
            for value in normalized_gap_values:
                bucket[value] = bucket.get(value, 0) + 1

    top_rejections = sorted(
        rejection_reason_counts.items(),
        key=lambda item: (-int(item[1]), item[0]),
    )[:3]
    if not candidates:
        summary = "No indexed device broker targets are available, so the request cannot be routed yet."
    elif "no_eligible_device_broker_targets" in blocking_reasons:
        top_summary = ", ".join(f"{reason} ({count})" for reason, count in top_rejections) or "no detailed blockers recorded"
        summary = (
            f"No eligible device broker targets matched `{request.get('intent') or 'device broker request'}`. "
            f"Top blockers: {top_summary}."
        )
    elif "selected_target_probe_unverified" in blocking_reasons:
        summary = (
            f"A broker target matched `{request.get('intent') or 'device broker request'}`, "
            "but its transport or probe status is still unverified."
        )
    else:
        summary = (
            f"Broker evaluated `{request.get('intent') or 'device broker request'}` with "
            f"{eligible_target_count} eligible target(s) and {ready_candidate_count} ready candidate(s)."
        )

    notes: list[str] = []
    if "missing_required_toolchains" in rejection_reason_counts:
        notes.append("Required toolchains are missing on the indexed fleet; add them to a host or relax the request.")
    if "missing_required_installed_runtimes" in rejection_reason_counts:
        notes.append("Installed runtime requirements are stricter than what the indexed hosts advertise.")
    if "local_transport_client_missing" in rejection_reason_counts:
        notes.append("Mission Control lacks a local transport client for at least one candidate transport.")
    if "target_probe_not_ready" in rejection_reason_counts or "target_probe_failed" in rejection_reason_counts:
        notes.append("At least one candidate host exists but is not probe-ready yet, so broker execution stays governed instead of YOLO-routing.")

    return {
        "summary": summary,
        "blocking_reasons": list(blocking_reasons),
        "rejection_reason_counts": rejection_reason_counts,
        "requirement_gap_counts": requirement_gap_counts,
        "candidate_count": len(candidates),
        "eligible_target_count": eligible_target_count,
        "ready_candidate_count": ready_candidate_count,
        "notes": notes,
    }


def resolve_device_broker_request(
    registry_payload: dict[str, Any] | None,
    request_payload: dict[str, Any] | None,
    *,
    policy_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = normalize_remote_execution_registry(registry_payload)
    request = normalize_device_broker_request(request_payload, policy_payload=policy_payload)
    index = build_remote_capability_index(registry)

    required_runner_families = set(request["required_runner_families"])
    required_os_families = set(request["required_os_families"])
    required_architectures = set(request["required_architectures"])
    required_gpu_models = [item.lower() for item in request["required_gpu_models"]]
    required_toolchains = set(request["required_toolchains"])
    required_installed_runtimes = set(request["required_installed_runtimes"])
    required_command_families = set(request["required_command_families"])
    required_result_formats = set(request["required_result_formats"])
    required_connector_families = set(request["required_connector_families"])
    required_capabilities = set(request["required_capabilities"])
    required_tags = set(request["required_tags"])
    allowed_trust_levels = set(request["allowed_trust_levels"])
    allowed_transports = set(request["allowed_transports"])

    candidates: list[dict[str, Any]] = []
    eligible_targets: list[dict[str, Any]] = []
    ready_candidates: list[dict[str, Any]] = []
    selected_target: dict[str, Any] | None = None
    selected_score: int | None = None

    for target in list(registry.get("targets") or []):
        reasons: list[str] = []
        target_id = str(target.get("id") or "").strip()
        target_gpu = str(target.get("gpu") or "").strip().lower()
        target_toolchains = set(_normalized_str_list(target.get("toolchains")))
        target_installed_runtimes = set(_normalized_str_list(target.get("installed_runtimes")))
        target_command_families = set(_normalized_str_list(target.get("command_families")))
        target_result_formats = set(_normalized_str_list(target.get("result_formats")))
        target_connector_families = set(_normalized_str_list(target.get("connector_families")))
        target_capabilities = set(_normalized_str_list(target.get("capabilities")))
        target_tags = set(_normalized_str_list(target.get("tags")))
        target_runner_families = set(_normalized_str_list(target.get("runner_families")))
        target_repo_roots = _normalized_str_list(target.get("allowed_repo_roots"))
        target_path_prefixes = _normalized_str_list(target.get("allowed_path_prefixes"))
        transport = str(target.get("transport") or "ssh")
        probe_status = str(target.get("last_probe_status") or "unknown")
        ready = probe_status in {"ready", "reachable"} and remote_transport_client_available(transport)
        target_command_runtime_seconds = _normalized_int(target.get("max_command_runtime_seconds"), default=None, minimum=1)
        target_file_transfer_quota_mb = _normalized_int(target.get("file_transfer_quota_mb"), default=None, minimum=1)

        if not target.get("enabled"):
            reasons.append("target_disabled")
        if required_runner_families and not required_runner_families.intersection(target_runner_families):
            reasons.append("missing_required_runner_families")
        if (
            "external_adapter" in required_runner_families
            and "external_adapter" in target_runner_families
            and not (
                _normalized_text(target.get("runner_command"))
                or _normalized_text(target.get("adapter_command"))
            )
        ):
            reasons.append("remote_adapter_command_missing")
        if required_os_families and str(target.get("os_family") or "unknown") not in required_os_families:
            reasons.append("os_family_not_allowed")
        if required_architectures and str(target.get("architecture") or "unknown") not in required_architectures:
            reasons.append("architecture_not_allowed")
        if request["require_gpu"] and not (target_gpu or "gpu" in target_capabilities):
            reasons.append("gpu_required")
        if required_gpu_models and not any(model in target_gpu for model in required_gpu_models):
            reasons.append("gpu_model_not_allowed")
        if required_toolchains and not required_toolchains.issubset(target_toolchains):
            reasons.append("missing_required_toolchains")
        if required_installed_runtimes and not required_installed_runtimes.issubset(target_installed_runtimes):
            reasons.append("missing_required_installed_runtimes")
        if required_command_families and not required_command_families.issubset(target_command_families):
            reasons.append("missing_required_command_families")
        if required_result_formats and not required_result_formats.issubset(target_result_formats):
            reasons.append("missing_required_result_formats")
        if required_connector_families and not required_connector_families.issubset(target_connector_families):
            reasons.append("missing_required_connector_families")
        if required_capabilities and not required_capabilities.issubset(target_capabilities):
            reasons.append("missing_required_capabilities")
        if required_tags and not required_tags.issubset(target_tags):
            reasons.append("missing_required_tags")
        if allowed_trust_levels and str(target.get("trust_level") or "limited") not in allowed_trust_levels:
            reasons.append("trust_level_not_allowed")
        if allowed_transports and transport not in allowed_transports:
            reasons.append("transport_not_allowed")
        if request["require_write_access"] and not bool(target.get("allow_write")):
            reasons.append("write_not_allowed")
        if request["require_session_recording"] and not bool(target.get("session_recording_enabled")):
            reasons.append("session_recording_required")
        if request["require_target_workspace_root"] and not _normalized_text(target.get("workspace_root")):
            reasons.append("target_workspace_root_missing")
        if request["required_repo_roots"] and not _required_prefixes_satisfied(
            request["required_repo_roots"],
            target_repo_roots,
        ):
            reasons.append("required_repo_roots_missing")
        if request["required_path_prefixes"] and not _required_prefixes_satisfied(
            request["required_path_prefixes"],
            target_path_prefixes,
        ):
            reasons.append("required_path_prefixes_missing")
        if request["minimum_command_runtime_seconds"] is not None and (
            target_command_runtime_seconds is None
            or target_command_runtime_seconds < request["minimum_command_runtime_seconds"]
        ):
            reasons.append("command_runtime_too_small")
        if request["minimum_file_transfer_quota_mb"] is not None and (
            target_file_transfer_quota_mb is None
            or target_file_transfer_quota_mb < request["minimum_file_transfer_quota_mb"]
        ):
            reasons.append("file_transfer_quota_too_small")
        if not remote_transport_client_available(transport):
            reasons.append("local_transport_client_missing")
        if probe_status == "failed":
            reasons.append("target_probe_failed")
        if request["require_probe_ready"] and not ready:
            reasons.append("target_probe_not_ready")

        score = 0
        if target_id and target_id == request.get("preferred_target_id"):
            score += 120
        score += 30 if str(target.get("trust_level") or "") == "trusted" else 0
        score += 15 if ready else 0
        score += 8 if transport == "tailscale_ssh" else 0
        score += len(required_capabilities.intersection(target_capabilities)) * 4
        score += len(required_toolchains.intersection(target_toolchains)) * 4
        score += len(required_installed_runtimes.intersection(target_installed_runtimes)) * 4
        score += len(required_command_families.intersection(target_command_families)) * 3
        score += len(required_result_formats.intersection(target_result_formats)) * 2
        score += len(required_runner_families.intersection(target_runner_families)) * 3

        status = "blocked" if reasons else ("ready" if ready else "partial")
        candidate = {
            "target_id": target_id,
            "label": str(target.get("label") or target_id),
            "transport": transport,
            "host": str(target.get("host") or ""),
            "os_family": str(target.get("os_family") or "unknown"),
            "architecture": str(target.get("architecture") or "unknown"),
            "gpu": _normalized_text(target.get("gpu")),
            "trust_level": str(target.get("trust_level") or "limited"),
            "ready": ready,
            "selected": False,
            "status": status,
            "score": score,
            "runner_families": _normalized_str_list(target.get("runner_families")),
            "capabilities": _normalized_str_list(target.get("capabilities")),
            "tags": _normalized_str_list(target.get("tags")),
            "runner_command": _normalized_text(target.get("runner_command"))
            or _normalized_text(target.get("adapter_command")),
            "runner_args": _normalized_str_list(target.get("runner_args"))
            or _normalized_str_list(target.get("adapter_args")),
            "adapter_command": _normalized_text(target.get("adapter_command")),
            "toolchains": _normalized_str_list(target.get("toolchains")),
            "installed_runtimes": _normalized_str_list(target.get("installed_runtimes")),
            "command_families": _normalized_str_list(target.get("command_families")),
            "result_formats": _normalized_str_list(target.get("result_formats")),
            "connector_families": _normalized_str_list(target.get("connector_families")),
            "session_recording_enabled": bool(target.get("session_recording_enabled")),
            "max_command_runtime_seconds": target_command_runtime_seconds,
            "file_transfer_quota_mb": target_file_transfer_quota_mb,
            "rejected_reasons": reasons,
            "requirement_gaps": _broker_candidate_requirement_gaps(
                request=request,
                target=target,
                transport=transport,
                probe_status=probe_status,
                ready=ready,
                target_repo_roots=target_repo_roots,
                target_path_prefixes=target_path_prefixes,
                target_toolchains=target_toolchains,
                target_installed_runtimes=target_installed_runtimes,
                target_command_families=target_command_families,
                target_result_formats=target_result_formats,
                target_connector_families=target_connector_families,
                target_capabilities=target_capabilities,
                target_tags=target_tags,
                target_runner_families=target_runner_families,
                target_command_runtime_seconds=target_command_runtime_seconds,
                target_file_transfer_quota_mb=target_file_transfer_quota_mb,
            ),
            "notes": [],
        }
        if not reasons:
            eligible_targets.append(target)
            if ready:
                ready_candidates.append(target)
            if selected_target is None or selected_score is None or score > selected_score:
                selected_target = target
                selected_score = score
        candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            {"ready": 0, "partial": 1, "blocked": 2}.get(str(item.get("status") or ""), 3),
            -int(item.get("score") or 0),
            str(item.get("label") or "").lower(),
            str(item.get("target_id") or "").lower(),
        )
    )
    selected_target_id = str(selected_target.get("id") or "").strip() or None if selected_target is not None else None
    if selected_target_id is not None:
        for candidate in candidates:
            if str(candidate.get("target_id") or "").strip() == selected_target_id:
                candidate["selected"] = True
                candidate["notes"] = _dedupe_preserving_order(
                    list(candidate.get("notes") or [])
                    + ["Selected broker target for the current request contract."]
                )
                break
    ready_candidate_ids = [
        str(target.get("id") or "")
        for target in ready_candidates
        if str(target.get("id") or "").strip()
    ]
    recommended_target_ids = [
        str(candidate.get("target_id") or "")
        for candidate in candidates
        if str(candidate.get("status") or "") in {"ready", "partial"} and str(candidate.get("target_id") or "").strip()
    ][:8]
    blocking_reasons: list[str] = []
    if selected_target is None:
        blocking_reasons.append("no_eligible_device_broker_targets")
    elif not (
        str(selected_target.get("last_probe_status") or "unknown") in {"ready", "reachable"}
        and remote_transport_client_available(str(selected_target.get("transport") or "ssh"))
    ):
        blocking_reasons.append("selected_target_probe_unverified")

    resolution_status = "blocked"
    if selected_target is not None and not blocking_reasons:
        resolution_status = "ready"
    elif selected_target is not None or eligible_targets or ready_candidates:
        resolution_status = "partial"

    intent_label = request.get("intent") or "device broker request"
    summary = (
        f"Resolved `{intent_label}` to target `{selected_target_id or 'none'}` with status `{resolution_status}`; "
        f"{len(eligible_targets)} eligible target(s) and {len(ready_candidates)} ready candidate(s) were found."
    )
    availability_diagnostics = _build_device_broker_availability_diagnostics(
        request=request,
        candidates=candidates,
        blocking_reasons=blocking_reasons,
        eligible_target_count=len(eligible_targets),
        ready_candidate_count=len(ready_candidates),
    )
    return {
        "request": request,
        "summary": summary,
        "resolution_status": resolution_status,
        "target_count": int(index.get("target_count") or 0),
        "ready_target_count": int(index.get("ready_target_count") or 0),
        "eligible_target_count": len(eligible_targets),
        "ready_candidate_count": len(ready_candidates),
        "ready_candidate_ids": ready_candidate_ids,
        "recommended_target_ids": recommended_target_ids,
        "selected_target": selected_target,
        "selected_target_id": selected_target_id,
        "selected_target_probe_status": (
            str(selected_target.get("last_probe_status") or "unknown") if selected_target is not None else "unknown"
        ),
        "selected_target_status": (
            "ready"
            if selected_target is not None
            and str(selected_target.get("last_probe_status") or "unknown") in {"ready", "reachable"}
            and remote_transport_client_available(str(selected_target.get("transport") or "ssh"))
            else "partial"
            if selected_target is not None
            else "not_applicable"
        ),
        "blocking_reasons": blocking_reasons,
        "candidates": candidates,
        "capability_index": index,
        "availability_diagnostics": availability_diagnostics,
    }


def select_remote_target(
    registry_payload: dict[str, Any] | None,
    policy_payload: dict[str, Any] | None,
    *,
    required_runner_family: str | None = None,
    require_write_access: bool | None = None,
) -> dict[str, Any]:
    registry = normalize_remote_execution_registry(registry_payload)
    policy = normalize_remote_execution_policy(policy_payload)
    runner_family = required_runner_family or policy["required_runner_family"]
    require_write = policy["require_write_access"] if require_write_access is None else bool(require_write_access)
    blocking_reasons: list[str] = []
    if not policy["enabled"]:
        blocking_reasons.append("remote_execution_disabled")
    if runner_family not in SUPPORTED_RUNNER_FAMILIES:
        blocking_reasons.append("unsupported_runner_family")
    resolution = resolve_device_broker_request(
        registry,
        {
            "preferred_target_id": policy.get("preferred_target_id"),
            "required_runner_families": [runner_family],
            "required_os_families": list(policy.get("allowed_os_families") or []),
            "required_toolchains": list(policy.get("required_toolchains") or []),
            "required_command_families": list(policy.get("required_command_families") or []),
            "required_result_formats": list(policy.get("required_result_formats") or []),
            "required_connector_families": list(policy.get("required_connector_families") or []),
            "required_capabilities": list(policy.get("required_capabilities") or []),
            "required_tags": list(policy.get("required_tags") or []),
            "allowed_trust_levels": list(policy.get("allowed_trust_levels") or []),
            "allowed_transports": list(policy.get("allowed_transports") or []),
            "require_write_access": require_write,
            "require_probe_ready": bool(policy.get("require_probe_ready")),
            "require_target_workspace_root": bool(policy.get("require_target_workspace_root")),
        },
    )
    selected = resolution.get("selected_target") if isinstance(resolution.get("selected_target"), dict) else None
    if selected is None and policy["enabled"]:
        if "no_eligible_device_broker_targets" in list(resolution.get("blocking_reasons") or []):
            blocking_reasons.append("no_eligible_remote_targets")
    elif selected is not None and "selected_target_probe_unverified" in list(resolution.get("blocking_reasons") or []):
        blocking_reasons.append("selected_target_probe_unverified")
    return {
        "policy": policy,
        "registry_summary": summarize_remote_execution_registry(registry),
        "required_runner_family": runner_family,
        "require_write_access": require_write,
        "eligible_target_count": int(resolution.get("eligible_target_count") or 0),
        "ready_candidate_count": int(resolution.get("ready_candidate_count") or 0),
        "ready_candidate_ids": [str(item) for item in list(resolution.get("ready_candidate_ids") or []) if str(item).strip()],
        "selected_target": selected,
        "selected_target_id": selected.get("id") if selected else None,
        "selected_target_probe_status": str(selected.get("last_probe_status") or "unknown") if selected else "unknown",
        "preflight_ready": bool(selected is not None and not blocking_reasons),
        "blocking_reasons": blocking_reasons,
        "availability_diagnostics": dict(resolution.get("availability_diagnostics") or {}),
        "candidates": [
            {
                "target_id": str(item.get("target_id") or ""),
                "label": str(item.get("label") or ""),
                "score": int(item.get("score") or 0),
                "rejected_reasons": list(item.get("rejected_reasons") or []),
                "requirement_gaps": dict(item.get("requirement_gaps") or {}),
                "transport": item.get("transport"),
                "os_family": item.get("os_family"),
                "trust_level": item.get("trust_level"),
                "toolchains": list(item.get("toolchains") or []),
                "command_families": list(item.get("command_families") or []),
            }
            for item in list(resolution.get("candidates") or [])
        ],
    }


def build_remote_execution_contract(
    registry_payload: dict[str, Any] | None,
    policy_payload: dict[str, Any] | None,
    *,
    integration_registry_payload: dict[str, Any] | None = None,
    workspace_tooling_payload: dict[str, Any] | None = None,
    required_runner_family: str | None = None,
    require_write_access: bool | None = None,
) -> dict[str, Any]:
    selection = select_remote_target(
        registry_payload,
        policy_payload,
        required_runner_family=required_runner_family,
        require_write_access=require_write_access,
    )
    selected_target = selection.get("selected_target") if isinstance(selection.get("selected_target"), dict) else None
    policy = normalize_remote_execution_policy(selection.get("policy"))
    artifact_contract = build_remote_artifact_contract(
        selected_target=selected_target,
        policy_payload=policy,
        workspace_tooling_payload=workspace_tooling_payload,
    )
    connector_contract = build_remote_connector_contract(
        selected_target=selected_target,
        policy_payload=policy,
        integration_registry_payload=integration_registry_payload,
    )
    broker_contract = build_remote_broker_contract(
        selected_target=selected_target,
        policy_payload=policy,
    )
    result_contract = build_remote_result_contract(
        selected_target=selected_target,
        policy_payload=policy,
        workspace_tooling_payload=workspace_tooling_payload,
        artifact_contract=artifact_contract,
        broker_contract=broker_contract,
    )
    blocking_reasons = list(selection.get("blocking_reasons") or [])
    if not artifact_contract["preflight_ready"]:
        blocking_reasons.extend(
            reason for reason in artifact_contract.get("blocking_reasons", []) if reason not in blocking_reasons
        )
    if not connector_contract["preflight_ready"]:
        blocking_reasons.extend(
            reason for reason in connector_contract.get("blocking_reasons", []) if reason not in blocking_reasons
        )
    if not broker_contract["preflight_ready"]:
        blocking_reasons.extend(
            reason for reason in broker_contract.get("blocking_reasons", []) if reason not in blocking_reasons
        )
    if not result_contract["preflight_ready"]:
        blocking_reasons.extend(
            reason for reason in result_contract.get("blocking_reasons", []) if reason not in blocking_reasons
        )
    return {
        **selection,
        "preflight_ready": bool(selection.get("selected_target") and not blocking_reasons),
        "blocking_reasons": blocking_reasons,
        "artifact_contract": artifact_contract,
        "connector_contract": connector_contract,
        "broker_contract": broker_contract,
        "result_contract": result_contract,
    }


def build_remote_artifact_contract(
    *,
    selected_target: dict[str, Any] | None,
    policy_payload: dict[str, Any] | None,
    workspace_tooling_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    policy = normalize_remote_execution_policy(policy_payload)
    tooling = dict(workspace_tooling_payload or {})
    artifact_paths = _normalized_str_list(tooling.get("artifact_paths"))
    artifact_allowlist = _normalized_str_list(policy.get("artifact_path_allowlist"))
    if artifact_allowlist:
        artifact_paths = [
            path for path in artifact_paths if any(_path_matches_prefix(path, prefix) for prefix in artifact_allowlist)
        ]
    artifact_roots = _normalized_str_list((selected_target or {}).get("artifact_roots"))
    workspace_root = _normalized_text((selected_target or {}).get("workspace_root"))
    selected_artifact_root = artifact_roots[0] if artifact_roots else None
    remote_workspace_artifact_paths = [
        _join_remote_path(workspace_root, path) for path in artifact_paths if workspace_root is not None
    ]
    sync_enabled = bool(policy.get("artifact_sync_enabled", True) and selected_target)
    required = bool(policy.get("artifact_required", False))
    blocking_reasons: list[str] = []
    if required and not artifact_paths:
        blocking_reasons.append("artifact_required_but_none_detected")
    if sync_enabled and artifact_paths and not (workspace_root or selected_artifact_root):
        blocking_reasons.append("remote_artifact_root_unresolved")
    notes = [
        f"Detected {len(artifact_paths)} local artifact path(s) from workspace tooling.",
        "Remote artifact sync is described as contract metadata first; execution lanes can use it without inventing their own artifact rules.",
    ]
    if artifact_allowlist:
        notes.append(f"Artifact allowlist trimmed the contract to {len(artifact_paths)} path(s).")
    if selected_artifact_root:
        notes.append(f"Primary remote artifact root: {selected_artifact_root}.")
    elif workspace_root:
        notes.append("Remote workspace root is available, so workspace-relative artifact paths can be reconstructed remotely.")
    else:
        notes.append("No remote artifact root or workspace root is registered on the selected target yet.")
    return {
        "sync_enabled": sync_enabled,
        "required": required,
        "artifact_path_allowlist": artifact_allowlist,
        "artifact_kind_summaries": _normalized_str_list(tooling.get("artifact_kind_summaries")),
        "local_artifact_paths": artifact_paths[:8],
        "local_artifact_path_count": len(artifact_paths),
        "artifact_inspection_commands": _normalized_str_list(tooling.get("artifact_inspection_commands"))[:8],
        "target_artifact_roots": artifact_roots,
        "selected_artifact_root": selected_artifact_root,
        "remote_workspace_root": workspace_root,
        "remote_workspace_artifact_paths": remote_workspace_artifact_paths[:8],
        "preflight_ready": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "notes": notes,
    }


def _remote_session_recording_basename(target_id: Any) -> str:
    normalized = _normalized_text(target_id) or "remote-target"
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in normalized).strip("-_.")
    if not safe:
        safe = "remote-target"
    return f"{safe}.cast"


def build_remote_session_recording_contract(
    *,
    selected_target: dict[str, Any] | None,
    policy_payload: dict[str, Any] | None,
    artifact_contract: dict[str, Any] | None = None,
    broker_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = normalize_remote_execution_policy(policy_payload)
    target = dict(selected_target or {})
    artifact = dict(artifact_contract or {})
    broker = dict(broker_contract or {})
    session_recording_required = bool(policy.get("require_session_recording")) or bool(
        broker.get("require_session_recording")
    )
    session_recording_enabled = bool(broker.get("session_recording_enabled")) or bool(
        target.get("session_recording_enabled")
    )
    if not session_recording_required and not session_recording_enabled:
        return {
            "session_recording_required": False,
            "session_recording_enabled": False,
            "artifact_format": None,
            "artifact_paths": [],
            "remote_artifact_paths": [],
            "primary_artifact_path": None,
            "primary_remote_artifact_path": None,
        }

    basename = _remote_session_recording_basename(target.get("id"))
    artifact_relative_path = f"artifacts/remote-execution-governance/session-recordings/{basename}"
    selected_artifact_root = _normalized_text(artifact.get("selected_artifact_root"))
    remote_workspace_root = _normalized_text(artifact.get("remote_workspace_root")) or _normalized_text(
        target.get("workspace_root")
    )
    remote_artifact_paths: list[str] = []
    if selected_artifact_root:
        remote_artifact_paths.append(
            _join_remote_path(selected_artifact_root, f"remote-execution-governance/session-recordings/{basename}")
        )
    elif remote_workspace_root:
        remote_artifact_paths.append(_join_remote_path(remote_workspace_root, artifact_relative_path))

    return {
        "session_recording_required": session_recording_required,
        "session_recording_enabled": session_recording_enabled,
        "artifact_format": "asciinema_cast",
        "artifact_paths": [artifact_relative_path],
        "remote_artifact_paths": _dedupe_preserving_order(remote_artifact_paths),
        "primary_artifact_path": artifact_relative_path,
        "primary_remote_artifact_path": remote_artifact_paths[0] if remote_artifact_paths else None,
    }


def build_remote_connector_contract(
    *,
    selected_target: dict[str, Any] | None,
    policy_payload: dict[str, Any] | None,
    integration_registry_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    policy = normalize_remote_execution_policy(policy_payload)
    registry = normalize_integration_registry(integration_registry_payload, {})
    target_connector_families = set(_normalized_str_list((selected_target or {}).get("connector_families")))
    required_families = _normalized_str_list(policy.get("required_connector_families"))
    allow_host_integrated = bool(policy.get("allow_host_integrated_connectors", True))
    require_authority = bool(policy.get("require_connector_authority", False))
    available: list[dict[str, Any]] = []
    for connection in list_connections(registry):
        family = _normalized_text(connection.get("family"))
        if family is None:
            continue
        if target_connector_families and family not in target_connector_families:
            continue
        if str(connection.get("status") or "disconnected") == "disconnected":
            continue
        if not allow_host_integrated and bool(connection.get("host_imported")):
            continue
        authoritative = str(connection.get("connection_source") or "") in AUTHORITATIVE_CONNECTION_SOURCES
        if require_authority and not authoritative:
            continue
        available.append(
            {
                "family": family,
                "status": str(connection.get("status") or "unknown"),
                "providers": _normalized_str_list(connection.get("providers")),
                "connection_source": _normalized_text(connection.get("connection_source")) or "unknown",
                "host_imported": bool(connection.get("host_imported")),
                "authoritative": authoritative,
                "notes": _normalized_str_list(connection.get("notes")),
            }
        )
    available_families = {item["family"] for item in available}
    missing_required = [family for family in required_families if family not in available_families]
    blocking_reasons: list[str] = []
    if missing_required:
        blocking_reasons.append("required_remote_connectors_missing")
    notes = [
        f"{len(available)} connector family lane(s) are usable for the selected remote target.",
        "Connector gating is resolved against Mission Control's integration registry instead of letting remote workers hallucinate external access.",
    ]
    if target_connector_families:
        notes.append(f"Selected target allows {len(target_connector_families)} connector family lane(s).")
    if require_authority:
        notes.append("Only authoritative Mission Control connector lanes are considered ready.")
    if not allow_host_integrated:
        notes.append("Host-imported connector hints are excluded from this remote lane.")
    return {
        "required_connector_families": required_families,
        "target_connector_families": sorted(target_connector_families),
        "allow_host_integrated_connectors": allow_host_integrated,
        "require_connector_authority": require_authority,
        "available_families": sorted(available_families),
        "available_connector_count": len(available),
        "missing_required_families": missing_required,
        "connections": available[:12],
        "preflight_ready": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "notes": notes,
    }


def build_remote_broker_contract(
    *,
    selected_target: dict[str, Any] | None,
    policy_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    policy = normalize_remote_execution_policy(policy_payload)
    target = dict(selected_target or {})
    required_toolchains = _normalized_str_list(policy.get("required_toolchains"))
    required_command_families = _normalized_str_list(policy.get("required_command_families"))
    required_result_formats = _normalized_str_list(policy.get("required_result_formats"))
    required_repo_roots = _normalized_str_list(policy.get("required_repo_roots"))
    required_path_prefixes = _normalized_str_list(policy.get("required_path_prefixes"))
    target_toolchains = _normalized_str_list(target.get("toolchains"))
    target_command_families = _normalized_str_list(target.get("command_families"))
    target_result_formats = _normalized_str_list(target.get("result_formats"))
    target_repo_roots = _normalized_str_list(target.get("allowed_repo_roots"))
    target_path_prefixes = _normalized_str_list(target.get("allowed_path_prefixes"))
    minimum_command_runtime_seconds = _normalized_int(policy.get("minimum_command_runtime_seconds"), default=None, minimum=1)
    minimum_file_transfer_quota_mb = _normalized_int(policy.get("minimum_file_transfer_quota_mb"), default=None, minimum=1)
    target_command_runtime_seconds = _normalized_int(target.get("max_command_runtime_seconds"), default=None, minimum=1)
    target_file_transfer_quota_mb = _normalized_int(target.get("file_transfer_quota_mb"), default=None, minimum=1)
    blocking_reasons: list[str] = []
    if selected_target:
        if required_toolchains and not set(required_toolchains).issubset(set(target_toolchains)):
            blocking_reasons.append("broker_toolchains_missing")
        if required_command_families and not set(required_command_families).issubset(set(target_command_families)):
            blocking_reasons.append("broker_command_families_missing")
        if required_result_formats and not set(required_result_formats).issubset(set(target_result_formats)):
            blocking_reasons.append("broker_result_formats_missing")
        if policy.get("require_session_recording") and not bool(target.get("session_recording_enabled")):
            blocking_reasons.append("broker_session_recording_required")
        if policy.get("require_target_workspace_root") and not _normalized_text(target.get("workspace_root")):
            blocking_reasons.append("broker_workspace_root_required")
        if required_repo_roots and not _required_prefixes_satisfied(required_repo_roots, target_repo_roots):
            blocking_reasons.append("broker_repo_roots_missing")
        if required_path_prefixes and not _required_prefixes_satisfied(required_path_prefixes, target_path_prefixes):
            blocking_reasons.append("broker_path_prefixes_missing")
        if minimum_command_runtime_seconds is not None and (
            target_command_runtime_seconds is None or target_command_runtime_seconds < minimum_command_runtime_seconds
        ):
            blocking_reasons.append("broker_command_runtime_too_small")
        if minimum_file_transfer_quota_mb is not None and (
            target_file_transfer_quota_mb is None or target_file_transfer_quota_mb < minimum_file_transfer_quota_mb
        ):
            blocking_reasons.append("broker_file_transfer_quota_too_small")
    notes = [
        "Broker policy turns remote execution into an explicit contract instead of letting workers freestyle their way into random hosts.",
    ]
    if target:
        notes.append(
            f"Selected target exposes {len(target_toolchains)} toolchain(s), {len(target_command_families)} command family lane(s), and {len(target_result_formats)} result format(s)."
        )
    else:
        notes.append("No remote target is selected, so broker capability checks remain descriptive only.")
    if required_repo_roots or required_path_prefixes:
        notes.append("Repo-root and path-prefix requirements narrow the remote write surface before any adapter turn starts.")
    if minimum_command_runtime_seconds is not None or minimum_file_transfer_quota_mb is not None:
        notes.append("Runtime and transfer quotas are enforced as broker preflight metadata instead of tribal knowledge.")
    return {
        "allowed_trust_levels": _normalized_str_list(policy.get("allowed_trust_levels")),
        "required_toolchains": required_toolchains,
        "required_command_families": required_command_families,
        "required_result_formats": required_result_formats,
        "require_session_recording": bool(policy.get("require_session_recording")),
        "require_target_workspace_root": bool(policy.get("require_target_workspace_root")),
        "required_repo_roots": required_repo_roots,
        "required_path_prefixes": required_path_prefixes,
        "minimum_command_runtime_seconds": minimum_command_runtime_seconds,
        "minimum_file_transfer_quota_mb": minimum_file_transfer_quota_mb,
        "target_gpu": _normalized_text(target.get("gpu")),
        "target_toolchains": target_toolchains,
        "target_command_families": target_command_families,
        "target_result_formats": target_result_formats,
        "session_recording_enabled": bool(target.get("session_recording_enabled")),
        "target_command_runtime_seconds": target_command_runtime_seconds,
        "target_file_transfer_quota_mb": target_file_transfer_quota_mb,
        "target_repo_roots": target_repo_roots,
        "target_path_prefixes": target_path_prefixes,
        "preflight_ready": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "notes": notes,
    }


def _normalized_adapter_contracts(payload: Iterable[dict[str, Any] | Any] | None) -> list[dict[str, Any]]:
    normalized_contracts: list[dict[str, Any]] = []
    seen_contract_ids: set[str] = set()
    for item in payload or []:
        contract = dict(item or {}) if isinstance(item, dict) else {}
        contract_id = _normalized_text(contract.get("contract_id"))
        if contract_id is None or contract_id in seen_contract_ids:
            continue
        seen_contract_ids.add(contract_id)
        normalized_contracts.append(contract)
    return normalized_contracts


def build_remote_result_contract(
    *,
    selected_target: dict[str, Any] | None,
    policy_payload: dict[str, Any] | None,
    workspace_tooling_payload: dict[str, Any] | None,
    artifact_contract: dict[str, Any] | None = None,
    broker_contract: dict[str, Any] | None = None,
    adapter_contracts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    policy = normalize_remote_execution_policy(policy_payload)
    target = dict(selected_target or {})
    tooling = dict(workspace_tooling_payload or {})
    required_result_formats = _normalized_str_list(policy.get("required_result_formats"))
    required_command_families = _normalized_str_list(policy.get("required_command_families"))
    required_toolchains = _normalized_str_list(policy.get("required_toolchains"))
    target_result_formats = _normalized_str_list(target.get("result_formats"))
    target_command_families = _normalized_str_list(target.get("command_families"))
    target_toolchains = _normalized_str_list(target.get("toolchains"))
    normalized_adapter_contracts = _normalized_adapter_contracts(adapter_contracts)
    adapter_contract_ids = _normalized_str_list(
        [contract.get("contract_id") for contract in normalized_adapter_contracts]
    )
    adapter_required_command_families = _normalized_str_list(
        [
            family
            for contract in normalized_adapter_contracts
            for family in list(contract.get("required_command_families") or [])
        ]
    )
    adapter_expected_result_formats = _normalized_str_list(
        [
            result_format
            for contract in normalized_adapter_contracts
            for result_format in list(contract.get("expected_result_formats") or [])
        ]
    )
    adapter_required_tool_families = _normalized_str_list(
        [
            tool_family
            for contract in normalized_adapter_contracts
            for tool_family in list(contract.get("required_tool_families") or [])
        ]
    )
    adapter_expected_evidence_categories = _normalized_str_list(
        [
            category
            for contract in normalized_adapter_contracts
            for category in list(contract.get("expected_evidence_categories") or [])
        ]
    )
    validation_evidence_targets = _normalized_str_list(tooling.get("validation_evidence_targets"))
    artifact_paths = _normalized_str_list(tooling.get("artifact_paths"))
    execution_entrypoints = _normalized_str_list(tooling.get("execution_entrypoints"))
    signal_sources = validation_evidence_targets + artifact_paths + execution_entrypoints
    evidence_inventory = classify_evidence_artifacts(signal_sources)
    session_recording_contract = build_remote_session_recording_contract(
        selected_target=target or None,
        policy_payload=policy,
        artifact_contract=artifact_contract,
        broker_contract=broker_contract,
    )

    effective_required_result_formats = _dedupe_preserving_order(
        required_result_formats + adapter_expected_result_formats
    )
    effective_required_command_families = _dedupe_preserving_order(
        required_command_families + adapter_required_command_families
    )

    expected_evidence_categories = ["logs"]
    if any(
        fmt in {"junit_xml", "xcresult", "json"}
        for fmt in effective_required_result_formats + target_result_formats
    ):
        expected_evidence_categories.append("coverage")
    if any(
        family in {"browser", "playwright"}
        for family in effective_required_command_families + target_command_families
    ):
        expected_evidence_categories.extend(["screenshots", "traces"])
    if any(
        family in {"unity_batchmode", "unreal_commandlet"}
        for family in effective_required_command_families + target_command_families
    ):
        expected_evidence_categories.extend(["screenshots"])
    if any(
        token in family
        for family in effective_required_command_families + target_command_families
        for token in ("benchmark", "perf", "profile")
    ):
        expected_evidence_categories.append("performance")
    expected_evidence_categories = _dedupe_preserving_order(
        expected_evidence_categories + adapter_expected_evidence_categories
    )

    missing_required_result_formats = [fmt for fmt in required_result_formats if fmt not in set(target_result_formats)]
    missing_required_command_families = [
        family for family in required_command_families if family not in set(target_command_families)
    ]
    missing_required_toolchains = [
        toolchain for toolchain in required_toolchains if toolchain not in set(target_toolchains)
    ]
    blocking_reasons: list[str] = []
    if missing_required_result_formats:
        blocking_reasons.append("remote_result_formats_missing")
    if missing_required_command_families:
        blocking_reasons.append("remote_result_command_families_missing")
    if missing_required_toolchains:
        blocking_reasons.append("remote_result_toolchains_missing")

    notes = [
        "Remote execution now carries a normalized result contract instead of treating output shape as tribal knowledge.",
        f"Observed {len(signal_sources)} workspace signal source(s) for remote evidence planning.",
    ]
    if adapter_contract_ids:
        notes.append(
            f"Folded {len(adapter_contract_ids)} platform adapter contract(s) into the remote result expectations."
        )
    if expected_evidence_categories:
        notes.append(
            f"Expected normalized evidence categories: {', '.join(expected_evidence_categories)}."
        )
    if evidence_inventory.get("categories_present"):
        notes.append(
            f"Current workspace evidence signals already cover {len(list(evidence_inventory.get('categories_present') or []))} category lane(s)."
        )

    return {
        "required_result_formats": required_result_formats,
        "effective_required_result_formats": effective_required_result_formats,
        "required_command_families": required_command_families,
        "effective_required_command_families": effective_required_command_families,
        "required_toolchains": required_toolchains,
        "target_result_formats": target_result_formats,
        "target_command_families": target_command_families,
        "target_toolchains": target_toolchains,
        "adapter_contract_ids": adapter_contract_ids,
        "adapter_contract_count": len(adapter_contract_ids),
        "adapter_required_command_families": adapter_required_command_families,
        "adapter_expected_result_formats": adapter_expected_result_formats,
        "adapter_required_tool_families": adapter_required_tool_families,
        "adapter_expected_evidence_categories": adapter_expected_evidence_categories,
        "missing_required_result_formats": missing_required_result_formats,
        "missing_required_command_families": missing_required_command_families,
        "missing_required_toolchains": missing_required_toolchains,
        "expected_evidence_categories": expected_evidence_categories,
        "observed_evidence_categories": list(evidence_inventory.get("categories_present") or []),
        "evidence_category_paths": dict(evidence_inventory.get("categories") or {}),
        "validation_evidence_targets": validation_evidence_targets[:12],
        "artifact_paths": artifact_paths[:12],
        "execution_entrypoints": execution_entrypoints[:12],
        "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
        "session_recording_artifact_format": session_recording_contract.get("artifact_format"),
        "session_recording_artifact_paths": list(session_recording_contract.get("artifact_paths") or []),
        "remote_session_recording_artifact_paths": list(session_recording_contract.get("remote_artifact_paths") or []),
        "primary_session_recording_artifact_path": session_recording_contract.get("primary_artifact_path"),
        "primary_remote_session_recording_artifact_path": session_recording_contract.get(
            "primary_remote_artifact_path"
        ),
        "preflight_ready": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "notes": notes,
    }


def _path_matches_prefix(path: str, prefix: str) -> bool:
    normalized_path = path.replace("\\", "/").strip("/")
    normalized_prefix = prefix.replace("\\", "/").strip("/")
    return normalized_path == normalized_prefix or normalized_path.startswith(f"{normalized_prefix}/")


def _required_prefixes_satisfied(required_prefixes: list[str], available_prefixes: list[str]) -> bool:
    for required in required_prefixes:
        if not any(_path_matches_prefix(required, available) or _path_matches_prefix(available, required) for available in available_prefixes):
            return False
    return True


def _looks_absolute_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return normalized.startswith("/") or (len(normalized) > 2 and normalized[1] == ":" and normalized[2] == "/")


def _relative_workspace_path(path: Any, workspace_path: str | None) -> str | None:
    normalized = _normalized_text(path)
    if normalized is None:
        return None
    normalized = normalized.replace("\\", "/")
    if normalized in {".", "./"}:
        return "."
    workspace_root = _normalized_text(workspace_path)
    if workspace_root:
        normalized_workspace = workspace_root.replace("\\", "/").rstrip("/")
        lowered_path = normalized.lower()
        lowered_workspace = normalized_workspace.lower()
        if lowered_path == lowered_workspace:
            return "."
        prefix = f"{lowered_workspace}/"
        if lowered_path.startswith(prefix):
            normalized = normalized[len(normalized_workspace) + 1 :]
    if _looks_absolute_path(normalized):
        return None
    normalized = normalized.lstrip("/")
    return normalized or "."


def _dedupe_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = _normalized_text(value)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _workspace_file_size_bytes(workspace_path: str | None, relative_path: str | None) -> int | None:
    root_text = _normalized_text(workspace_path)
    relative_text = _normalized_text(relative_path)
    if root_text is None or relative_text is None:
        return None
    try:
        workspace_root = Path(root_text).expanduser().resolve()
        candidate = (workspace_root / relative_text.replace("/", "\\")).resolve()
        candidate.relative_to(workspace_root)
    except (OSError, RuntimeError, ValueError):
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    try:
        return int(candidate.stat().st_size)
    except OSError:
        return None


def _bytes_to_megabytes(value: int | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / float(1024 * 1024), 4)


def _remote_path_uses_prefix(path: str | None, prefix: str | None) -> bool:
    normalized_path = _normalized_text(path)
    normalized_prefix = _normalized_text(prefix)
    if normalized_path is None or normalized_prefix is None:
        return False
    normalized_path = normalized_path.replace("\\", "/").rstrip("/")
    normalized_prefix = normalized_prefix.replace("\\", "/").rstrip("/")
    return normalized_path == normalized_prefix or normalized_path.startswith(f"{normalized_prefix}/")


def _resolve_remote_path_strategy(remote_path: str | None, artifact_contract: dict[str, Any] | None) -> str:
    normalized_remote_path = _normalized_text(remote_path)
    if normalized_remote_path is None:
        return "local_only"
    artifact = dict(artifact_contract or {})
    if _remote_path_uses_prefix(normalized_remote_path, artifact.get("selected_artifact_root")):
        return "remote_artifact_root"
    if _remote_path_uses_prefix(normalized_remote_path, artifact.get("remote_workspace_root")):
        return "workspace_relative_sync"
    return "explicit_remote_path"


def _build_remote_transfer_estimate(
    *,
    workspace_path: str | None,
    artifact_contract: dict[str, Any] | None,
    result_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    artifact = dict(artifact_contract or {})
    result = dict(result_contract or {})
    outbound_paths = _normalized_str_list(artifact.get("local_artifact_paths"))
    outbound_estimates: list[dict[str, Any]] = []
    unknown_outbound_paths: list[str] = []
    estimated_outbound_transfer_bytes = 0
    for relative_path in outbound_paths:
        size_bytes = _workspace_file_size_bytes(workspace_path, relative_path)
        if size_bytes is None:
            unknown_outbound_paths.append(relative_path)
            continue
        estimated_outbound_transfer_bytes += size_bytes
        outbound_estimates.append({"path": relative_path, "bytes": size_bytes})

    declared_result_artifact_paths = _dedupe_preserving_order(
        [str(item) for item in list(result.get("session_recording_artifact_paths") or []) if str(item).strip()]
        + ([str(result.get("normalized_summary_artifact")).strip()] if _normalized_text(result.get("normalized_summary_artifact")) else [])
    )
    known_result_transfer_bytes = 0
    known_result_transfer_paths: list[dict[str, Any]] = []
    unknown_result_paths: list[str] = []
    for relative_path in declared_result_artifact_paths:
        size_bytes = _workspace_file_size_bytes(workspace_path, relative_path)
        if size_bytes is None:
            unknown_result_paths.append(relative_path)
            continue
        known_result_transfer_bytes += size_bytes
        known_result_transfer_paths.append({"path": relative_path, "bytes": size_bytes})

    estimated_total_known_transfer_bytes = estimated_outbound_transfer_bytes + known_result_transfer_bytes
    return {
        "estimated_outbound_transfer_bytes": estimated_outbound_transfer_bytes,
        "estimated_outbound_transfer_mb": _bytes_to_megabytes(estimated_outbound_transfer_bytes),
        "estimated_outbound_transfer_path_count": len(outbound_paths),
        "estimated_outbound_known_path_count": len(outbound_estimates),
        "estimated_outbound_unknown_paths": unknown_outbound_paths,
        "outbound_transfer_estimates": outbound_estimates,
        "declared_result_artifact_paths": declared_result_artifact_paths,
        "declared_result_artifact_count": len(declared_result_artifact_paths),
        "known_result_transfer_bytes": known_result_transfer_bytes,
        "known_result_transfer_mb": _bytes_to_megabytes(known_result_transfer_bytes),
        "known_result_transfer_paths": known_result_transfer_paths,
        "unknown_result_transfer_paths": unknown_result_paths,
        "estimated_total_known_transfer_bytes": estimated_total_known_transfer_bytes,
        "estimated_total_known_transfer_mb": _bytes_to_megabytes(estimated_total_known_transfer_bytes),
    }


def build_remote_result_collection_contract(
    *,
    workspace_path: str | None,
    artifact_contract: dict[str, Any] | None,
    result_contract: dict[str, Any] | None,
    broker_contract: dict[str, Any] | None = None,
    adapter_contracts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    artifact = dict(artifact_contract or {})
    result = dict(result_contract or {})
    broker = dict(broker_contract or {})
    normalized_adapter_contracts = [
        dict(item)
        for item in list(adapter_contracts or [])
        if isinstance(item, dict)
    ]
    selected_adapter_contract_ids = _normalized_str_list(
        [item.get("contract_id") for item in normalized_adapter_contracts]
    )
    selected_adapter_shipping_modes = _dedupe_preserving_order(
        [
            str(mode)
            for item in normalized_adapter_contracts
            for mode in list(item.get("artifact_shipping_modes") or [])
            if str(mode).strip()
        ]
    )
    common_adapter_shipping_modes = list(selected_adapter_shipping_modes)
    if normalized_adapter_contracts:
        common_adapter_shipping_modes = _normalized_str_list(
            normalized_adapter_contracts[0].get("artifact_shipping_modes")
        )
        for item in normalized_adapter_contracts[1:]:
            item_modes = set(_normalized_str_list(item.get("artifact_shipping_modes")))
            common_adapter_shipping_modes = [
                mode for mode in common_adapter_shipping_modes if mode in item_modes
            ]
    supported_brokered_collection_contract_ids = _normalized_str_list(
        [
            item.get("contract_id")
            for item in normalized_adapter_contracts
            if bool(item.get("supports_brokered_result_collection"))
        ]
    )
    unsupported_brokered_collection_contract_ids = _normalized_str_list(
        [
            item.get("contract_id")
            for item in normalized_adapter_contracts
            if not bool(item.get("supports_brokered_result_collection"))
        ]
    )
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str]] = set()

    def _append_item(
        *,
        local_path: str | None,
        remote_path: str | None,
        collection_stage: str,
        source_kind: str,
        required: bool,
        collection_mode: str,
    ) -> None:
        normalized_local_path = _normalized_text(local_path)
        if normalized_local_path is None:
            return
        normalized_remote_path = _normalized_text(remote_path)
        key = (normalized_local_path, normalized_remote_path, collection_stage)
        if key in seen:
            return
        seen.add(key)
        size_bytes = _workspace_file_size_bytes(workspace_path, normalized_local_path)
        remote_path_strategy = _resolve_remote_path_strategy(normalized_remote_path, artifact)
        collection_transport = (
            "brokered_sync"
            if normalized_remote_path is not None
            else "local_generated"
            if collection_mode == "local_generated_artifact"
            else "local_only"
        )
        path_sandbox_source = (
            "selected_artifact_root"
            if remote_path_strategy == "remote_artifact_root"
            else "remote_workspace_root"
            if remote_path_strategy == "workspace_relative_sync"
            else "explicit_remote_path"
            if normalized_remote_path is not None
            else "workspace_relative"
        )
        items.append(
            {
                "local_path": normalized_local_path,
                "remote_path": normalized_remote_path,
                "collection_stage": collection_stage,
                "source_kind": source_kind,
                "required": required,
                "collection_mode": collection_mode,
                "collection_transport": collection_transport,
                "remote_path_strategy": remote_path_strategy,
                "path_sandbox_source": path_sandbox_source,
                "adapter_contract_ids": list(selected_adapter_contract_ids),
                "brokered_collection_supported": (
                    normalized_remote_path is None
                    or not normalized_adapter_contracts
                    or bool(
                        len(supported_brokered_collection_contract_ids)
                        == len(selected_adapter_contract_ids)
                    )
                ),
                "bytes_at_dispatch": size_bytes,
                "present_at_dispatch": size_bytes is not None,
            }
        )

    local_artifact_paths = _normalized_str_list(artifact.get("local_artifact_paths"))
    remote_artifact_paths = _normalized_str_list(artifact.get("remote_workspace_artifact_paths"))
    for index, local_path in enumerate(local_artifact_paths):
        _append_item(
            local_path=local_path,
            remote_path=remote_artifact_paths[index] if index < len(remote_artifact_paths) else None,
            collection_stage="remote_workspace_artifact",
            source_kind="workspace_artifact",
            required=bool(artifact.get("required")),
            collection_mode="pull_remote_artifact",
        )

    local_recording_paths = _normalized_str_list(result.get("session_recording_artifact_paths"))
    remote_recording_paths = _normalized_str_list(result.get("remote_session_recording_artifact_paths"))
    for index, local_path in enumerate(local_recording_paths):
        _append_item(
            local_path=local_path,
            remote_path=remote_recording_paths[index] if index < len(remote_recording_paths) else None,
            collection_stage="remote_session_recording",
            source_kind="session_recording",
            required=bool(broker.get("require_session_recording")),
            collection_mode="pull_remote_artifact",
        )

    normalized_summary_artifact = _normalized_text(result.get("normalized_summary_artifact"))
    if normalized_summary_artifact is not None:
        _append_item(
            local_path=normalized_summary_artifact,
            remote_path=None,
            collection_stage="normalized_summary",
            source_kind="normalized_summary",
            required=True,
            collection_mode="local_generated_artifact",
        )

    remote_collectible_items = [item for item in items if item.get("remote_path")]
    required_items = [item for item in items if bool(item.get("required"))]
    present_at_dispatch_items = [item for item in items if bool(item.get("present_at_dispatch"))]
    collection_transport_modes = _dedupe_preserving_order(
        [str(item.get("collection_transport") or "") for item in items if str(item.get("collection_transport") or "").strip()]
    )
    missing_at_dispatch_paths = [
        str(item.get("local_path") or "").strip()
        for item in items
        if not bool(item.get("present_at_dispatch")) and str(item.get("local_path") or "").strip()
    ]
    blocking_reasons: list[str] = []
    if remote_collectible_items and normalized_adapter_contracts and unsupported_brokered_collection_contract_ids:
        blocking_reasons.append("selected_adapter_contract_missing_brokered_result_collection_support")
    if (
        remote_collectible_items
        and normalized_adapter_contracts
        and "brokered_sync" not in set(common_adapter_shipping_modes)
    ):
        blocking_reasons.append("selected_adapter_contract_missing_brokered_sync_mode")
    contract_status = (
        "blocked"
        if blocking_reasons
        else "ready"
        if remote_collectible_items
        else "local_only"
        if items
        else "not_applicable"
    )
    notes = [
        "Result collection is now governed as an explicit contract so post-run artifact pickup does not depend on adapter folklore.",
        f"Declared {len(items)} result collection item(s), including {len(remote_collectible_items)} remote-collectible artifact lane(s).",
    ]
    if required_items:
        notes.append(f"{len(required_items)} declared result item(s) are marked required by broker or result policy.")
    if normalized_adapter_contracts:
        notes.append(
            f"Selected adapter contracts advertise {len(selected_adapter_shipping_modes)} artifact shipping mode(s) for brokered result collection."
        )
    if unsupported_brokered_collection_contract_ids:
        notes.append(
            f"{len(unsupported_brokered_collection_contract_ids)} selected adapter contract(s) do not support brokered result collection."
        )
    if remote_collectible_items and "brokered_sync" in set(common_adapter_shipping_modes):
        notes.append("Remote result pickup is bound to `brokered_sync`, so adapters cannot freestyle artifact return paths.")
    if missing_at_dispatch_paths:
        notes.append(
            f"{len(missing_at_dispatch_paths)} declared result item(s) were not present locally at dispatch time and will rely on post-run collection or generation."
        )
    return {
        "items": items,
        "declared_item_count": len(items),
        "required_item_count": len(required_items),
        "remote_collectible_item_count": len(remote_collectible_items),
        "present_at_dispatch_count": len(present_at_dispatch_items),
        "collection_transport_modes": collection_transport_modes,
        "contract_status": contract_status,
        "preflight_ready": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "selected_adapter_contract_ids": selected_adapter_contract_ids,
        "selected_adapter_contract_count": len(selected_adapter_contract_ids),
        "supported_brokered_collection_contract_ids": supported_brokered_collection_contract_ids,
        "unsupported_brokered_collection_contract_ids": unsupported_brokered_collection_contract_ids,
        "selected_adapter_shipping_modes": selected_adapter_shipping_modes,
        "common_adapter_shipping_modes": common_adapter_shipping_modes,
        "brokered_result_collection_supported": not blocking_reasons,
        "missing_at_dispatch_paths": missing_at_dispatch_paths,
        "notes": notes,
    }


def build_remote_transfer_bundle(
    *,
    workspace_path: str | None,
    artifact_contract: dict[str, Any] | None,
    result_contract: dict[str, Any] | None,
    broker_contract: dict[str, Any] | None,
    adapter_contracts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    artifact = dict(artifact_contract or {})
    result = dict(result_contract or {})
    broker = dict(broker_contract or {})
    result_collection_contract = build_remote_result_collection_contract(
        workspace_path=workspace_path,
        artifact_contract=artifact,
        result_contract=result,
        broker_contract=broker,
        adapter_contracts=adapter_contracts,
    )
    local_artifact_paths = _normalized_str_list(artifact.get("local_artifact_paths"))
    remote_artifact_paths = _normalized_str_list(artifact.get("remote_workspace_artifact_paths"))
    selected_adapter_contract_ids = _normalized_str_list(
        [item.get("contract_id") for item in list(adapter_contracts or []) if isinstance(item, dict)]
    )
    staged_outbound_artifacts: list[dict[str, Any]] = []
    staged_outbound_transfer_bytes = 0
    staged_outbound_missing_paths: list[str] = []
    for index, local_path in enumerate(local_artifact_paths):
        remote_path = remote_artifact_paths[index] if index < len(remote_artifact_paths) else None
        size_bytes = _workspace_file_size_bytes(workspace_path, local_path)
        status = "staged" if size_bytes is not None else "missing"
        if size_bytes is None:
            staged_outbound_missing_paths.append(local_path)
        else:
            staged_outbound_transfer_bytes += size_bytes
        staged_outbound_artifacts.append(
            {
                "local_path": local_path,
                "remote_path": remote_path,
                "transfer_direction": "push_to_remote",
                "transfer_transport": "brokered_sync" if remote_path else "local_only",
                "remote_path_strategy": _resolve_remote_path_strategy(remote_path, artifact),
                "path_sandbox_source": (
                    "selected_artifact_root"
                    if _resolve_remote_path_strategy(remote_path, artifact) == "remote_artifact_root"
                    else "remote_workspace_root"
                    if _resolve_remote_path_strategy(remote_path, artifact) == "workspace_relative_sync"
                    else "explicit_remote_path"
                    if remote_path
                    else "workspace_relative"
                ),
                "adapter_contract_ids": list(selected_adapter_contract_ids),
                "bytes": size_bytes,
                "status": status,
            }
        )

    declared_result_collection = [
        dict(item)
        for item in list(result_collection_contract.get("items") or [])
        if isinstance(item, dict)
    ]

    target_file_transfer_quota_mb = _normalized_int(
        broker.get("target_file_transfer_quota_mb"),
        default=None,
        minimum=1,
    )
    target_file_transfer_quota_bytes = (
        int(target_file_transfer_quota_mb) * 1024 * 1024 if target_file_transfer_quota_mb is not None else None
    )
    blocking_reasons: list[str] = []
    if (
        target_file_transfer_quota_bytes is not None
        and staged_outbound_transfer_bytes > target_file_transfer_quota_bytes
    ):
        blocking_reasons.append("remote_staged_outbound_transfer_quota_exceeded")
    blocking_reasons = _dedupe_preserving_order(
        blocking_reasons
        + [
            str(item)
            for item in list(result_collection_contract.get("blocking_reasons") or [])
            if str(item).strip()
        ]
    )
    transfer_quota_status = (
        "blocked"
        if blocking_reasons
        else "not_applicable"
        if target_file_transfer_quota_bytes is None
        else "partial"
        if staged_outbound_missing_paths
        else "ready"
    )
    notes = [
        "Dispatch now persists a transfer bundle with actual staged upload bytes instead of pretending quota planning ends at launch-plan math.",
        f"Staged {len(staged_outbound_artifacts)} outbound artifact path(s) for brokered upload.",
    ]
    if target_file_transfer_quota_bytes is not None:
        notes.append(
            f"Target file-transfer quota allows {target_file_transfer_quota_bytes} byte(s) ({target_file_transfer_quota_mb} MiB) for staged uploads."
        )
    if staged_outbound_missing_paths:
        notes.append(
            f"{len(staged_outbound_missing_paths)} staged outbound artifact path(s) could not be measured at dispatch time."
        )
    if declared_result_collection:
        notes.append(
            f"Declared {len(declared_result_collection)} result collection target(s) for post-run evidence handling."
        )
    notes.extend([str(item) for item in list(result_collection_contract.get("notes") or []) if str(item).strip()])
    return {
        "target_file_transfer_quota_bytes": target_file_transfer_quota_bytes,
        "staged_outbound_artifacts": staged_outbound_artifacts,
        "staged_outbound_transfer_bytes": staged_outbound_transfer_bytes,
        "staged_outbound_transfer_mb": _bytes_to_megabytes(staged_outbound_transfer_bytes),
        "staged_outbound_transfer_path_count": len(staged_outbound_artifacts),
        "staged_outbound_missing_paths": staged_outbound_missing_paths,
        "result_collection_contract": result_collection_contract,
        "result_collection_contract_status": result_collection_contract.get("contract_status"),
        "result_collection_blocking_reasons": list(result_collection_contract.get("blocking_reasons") or []),
        "declared_result_collection": declared_result_collection,
        "declared_result_collection_count": len(declared_result_collection),
        "remote_collectible_result_path_count": result_collection_contract.get("remote_collectible_item_count", 0),
        "selected_adapter_contract_ids": list(result_collection_contract.get("selected_adapter_contract_ids") or []),
        "selected_adapter_contract_count": result_collection_contract.get("selected_adapter_contract_count", 0),
        "selected_adapter_shipping_modes": list(
            result_collection_contract.get("selected_adapter_shipping_modes") or []
        ),
        "common_adapter_shipping_modes": list(result_collection_contract.get("common_adapter_shipping_modes") or []),
        "brokered_result_collection_supported": bool(
            result_collection_contract.get("brokered_result_collection_supported")
        ),
        "transfer_quota_status": transfer_quota_status,
        "preflight_ready": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "notes": notes,
    }


def build_remote_launch_plan(
    *,
    selected_target: dict[str, Any] | None,
    policy_payload: dict[str, Any] | None,
    adapter_command: str | None,
    adapter_args: list[str] | None = None,
    broker_contract: dict[str, Any] | None = None,
    artifact_contract: dict[str, Any] | None = None,
    connector_contract: dict[str, Any] | None = None,
    result_contract: dict[str, Any] | None = None,
    workspace_path: str | None = None,
    allowed_paths: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
    adapter_contracts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    target = dict(selected_target or {})
    policy = normalize_remote_execution_policy(policy_payload)
    broker = dict(
        broker_contract
        or build_remote_broker_contract(
            selected_target=target or None,
            policy_payload=policy,
        )
    )
    artifact = dict(artifact_contract or {})
    connector = dict(connector_contract or {})
    result = dict(result_contract or {})
    if not result:
        session_recording_contract = build_remote_session_recording_contract(
            selected_target=target or None,
            policy_payload=policy,
            artifact_contract=artifact,
            broker_contract=broker,
        )
        result = {
            "session_recording_artifact_paths": list(session_recording_contract.get("artifact_paths") or []),
            "remote_session_recording_artifact_paths": list(session_recording_contract.get("remote_artifact_paths") or []),
            "primary_session_recording_artifact_path": session_recording_contract.get("primary_artifact_path"),
            "primary_remote_session_recording_artifact_path": session_recording_contract.get(
                "primary_remote_artifact_path"
            ),
        }
    result_collection_contract = build_remote_result_collection_contract(
        workspace_path=workspace_path,
        artifact_contract=artifact,
        result_contract=result,
        broker_contract=broker,
        adapter_contracts=adapter_contracts,
    )
    blocking_reasons = _dedupe_preserving_order(
        list(broker.get("blocking_reasons") or [])
        + list(artifact.get("blocking_reasons") or [])
        + list(connector.get("blocking_reasons") or [])
        + list(result.get("blocking_reasons") or [])
        + list(result_collection_contract.get("blocking_reasons") or [])
    )

    if not target:
        blocking_reasons.append("selected_target_missing")
    normalized_command = _normalized_text(adapter_command)
    if normalized_command is None:
        blocking_reasons.append("remote_adapter_command_missing")

    remote_workspace_root = _normalized_text(target.get("workspace_root"))
    target_repo_roots = _normalized_str_list(broker.get("target_repo_roots"))
    target_path_prefixes = _normalized_str_list(broker.get("target_path_prefixes"))
    required_path_prefixes = _normalized_str_list(broker.get("required_path_prefixes"))
    policy_path_prefixes = required_path_prefixes or target_path_prefixes

    rejected_allowed_paths: list[str] = []
    normalized_allowed_paths: list[str] = []
    for raw_path in allowed_paths or []:
        relative = _relative_workspace_path(raw_path, workspace_path)
        if relative is None:
            rejected_allowed_paths.append(str(raw_path))
            continue
        normalized_allowed_paths.append(relative)
    rejected_forbidden_paths: list[str] = []
    normalized_forbidden_paths: list[str] = []
    for raw_path in forbidden_paths or []:
        relative = _relative_workspace_path(raw_path, workspace_path)
        if relative is None:
            rejected_forbidden_paths.append(str(raw_path))
            continue
        normalized_forbidden_paths.append(relative)
    normalized_allowed_paths = _dedupe_preserving_order(normalized_allowed_paths)
    normalized_forbidden_paths = _dedupe_preserving_order(normalized_forbidden_paths)

    if rejected_allowed_paths:
        blocking_reasons.append("task_allowed_path_outside_workspace")
    if rejected_forbidden_paths:
        blocking_reasons.append("task_forbidden_path_outside_workspace")

    effective_allowed_paths = list(normalized_allowed_paths)
    if not effective_allowed_paths:
        effective_allowed_paths = list(policy_path_prefixes)
    if not effective_allowed_paths:
        effective_allowed_paths = ["."]

    if policy_path_prefixes:
        disallowed_paths = [
            path
            for path in normalized_allowed_paths
            if path == "." or not any(_path_matches_prefix(path, prefix) for prefix in policy_path_prefixes)
        ]
        if disallowed_paths:
            blocking_reasons.append("task_allowed_paths_outside_remote_policy")
        if normalized_allowed_paths:
            effective_allowed_paths = [
                path for path in normalized_allowed_paths if any(_path_matches_prefix(path, prefix) for prefix in policy_path_prefixes)
            ]
            if not effective_allowed_paths:
                effective_allowed_paths = list(policy_path_prefixes)

    allowed_remote_paths = [
        remote_workspace_root if path == "." and remote_workspace_root else _join_remote_path(remote_workspace_root, path)
        for path in effective_allowed_paths
    ]
    forbidden_remote_paths = [
        remote_workspace_root if path == "." and remote_workspace_root else _join_remote_path(remote_workspace_root, path)
        for path in normalized_forbidden_paths
    ]
    minimum_command_runtime_seconds = _normalized_int(
        broker.get("minimum_command_runtime_seconds"), default=None, minimum=1
    )
    minimum_file_transfer_quota_mb = _normalized_int(
        broker.get("minimum_file_transfer_quota_mb"), default=None, minimum=1
    )
    target_command_runtime_seconds = _normalized_int(
        broker.get("target_command_runtime_seconds"), default=None, minimum=1
    )
    target_file_transfer_quota_mb = _normalized_int(
        broker.get("target_file_transfer_quota_mb"), default=None, minimum=1
    )
    target_file_transfer_quota_bytes = (
        int(target_file_transfer_quota_mb) * 1024 * 1024 if target_file_transfer_quota_mb is not None else None
    )
    quota_contract = {
        "minimum_command_runtime_seconds": minimum_command_runtime_seconds,
        "minimum_file_transfer_quota_mb": minimum_file_transfer_quota_mb,
        "target_command_runtime_seconds": target_command_runtime_seconds,
        "target_file_transfer_quota_mb": target_file_transfer_quota_mb,
    }
    transfer_estimate = _build_remote_transfer_estimate(
        workspace_path=workspace_path,
        artifact_contract=artifact,
        result_contract=result,
    )
    estimated_outbound_transfer_bytes = int(transfer_estimate.get("estimated_outbound_transfer_bytes") or 0)
    estimated_total_known_transfer_bytes = int(transfer_estimate.get("estimated_total_known_transfer_bytes") or 0)
    estimated_transfer_within_quota = (
        None
        if target_file_transfer_quota_bytes is None
        else estimated_outbound_transfer_bytes <= target_file_transfer_quota_bytes
    )
    if estimated_transfer_within_quota is False:
        blocking_reasons.append("remote_estimated_outbound_transfer_quota_exceeded")

    environment = {
        "MISSION_CONTROL_REMOTE_TARGET_ID": str(target.get("id") or ""),
        "MISSION_CONTROL_REMOTE_TRANSPORT": str(target.get("transport") or ""),
        "MISSION_CONTROL_REMOTE_HOST": str(target.get("host") or ""),
        "MISSION_CONTROL_REMOTE_WORKSPACE_ROOT": remote_workspace_root or "",
        "MISSION_CONTROL_REMOTE_ALLOWED_PATHS_JSON": json.dumps(effective_allowed_paths),
        "MISSION_CONTROL_REMOTE_ALLOWED_REMOTE_PATHS_JSON": json.dumps(allowed_remote_paths),
        "MISSION_CONTROL_REMOTE_FORBIDDEN_PATHS_JSON": json.dumps(normalized_forbidden_paths),
        "MISSION_CONTROL_REMOTE_FORBIDDEN_REMOTE_PATHS_JSON": json.dumps(forbidden_remote_paths),
        "MISSION_CONTROL_REMOTE_ALLOWED_REPO_ROOTS_JSON": json.dumps(target_repo_roots),
        "MISSION_CONTROL_REMOTE_CONNECTOR_FAMILIES_JSON": json.dumps(
            _normalized_str_list(connector.get("available_families"))
        ),
        "MISSION_CONTROL_REMOTE_ARTIFACT_PATHS_JSON": json.dumps(
            _normalized_str_list(artifact.get("remote_workspace_artifact_paths"))
        ),
        "MISSION_CONTROL_REMOTE_COMMAND_FAMILIES_JSON": json.dumps(
            _normalized_str_list(broker.get("target_command_families"))
        ),
        "MISSION_CONTROL_REMOTE_TOOLCHAINS_JSON": json.dumps(_normalized_str_list(broker.get("target_toolchains"))),
        "MISSION_CONTROL_REMOTE_REQUIRED_RESULT_FORMATS_JSON": json.dumps(
            _normalized_str_list(broker.get("required_result_formats"))
        ),
        "MISSION_CONTROL_REMOTE_TARGET_RESULT_FORMATS_JSON": json.dumps(
            _normalized_str_list(broker.get("target_result_formats"))
        ),
        "MISSION_CONTROL_REMOTE_EXPECTED_EVIDENCE_CATEGORIES_JSON": json.dumps(
            _normalized_str_list(result.get("expected_evidence_categories"))
        ),
        "MISSION_CONTROL_REMOTE_ADAPTER_CONTRACT_IDS_JSON": json.dumps(
            _normalized_str_list(result.get("adapter_contract_ids"))
        ),
        "MISSION_CONTROL_REMOTE_ADAPTER_REQUIRED_TOOL_FAMILIES_JSON": json.dumps(
            _normalized_str_list(result.get("adapter_required_tool_families"))
        ),
        "MISSION_CONTROL_REMOTE_ADAPTER_EXPECTED_RESULT_FORMATS_JSON": json.dumps(
            _normalized_str_list(result.get("adapter_expected_result_formats"))
        ),
        "MISSION_CONTROL_REMOTE_RUNNER_COMMAND": normalized_command or "",
        "MISSION_CONTROL_REMOTE_RUNNER_ARGS_JSON": json.dumps(_normalized_str_list(adapter_args)),
        "MISSION_CONTROL_REMOTE_NORMALIZED_SUMMARY_ARTIFACT": str(
            result.get("normalized_summary_artifact") or ""
        ),
        "MISSION_CONTROL_REMOTE_SESSION_RECORDING_REQUIRED": "1" if broker.get("require_session_recording") else "0",
        "MISSION_CONTROL_REMOTE_SESSION_RECORDING_ENABLED": "1" if broker.get("session_recording_enabled") else "0",
        "MISSION_CONTROL_REMOTE_SESSION_RECORDING_ARTIFACT_PATHS_JSON": json.dumps(
            _normalized_str_list(result.get("remote_session_recording_artifact_paths"))
        ),
        "MISSION_CONTROL_REMOTE_SESSION_RECORDING_PRIMARY_ARTIFACT_PATH": str(
            result.get("primary_remote_session_recording_artifact_path") or ""
        ),
        "MISSION_CONTROL_REMOTE_MIN_COMMAND_RUNTIME_SECONDS": (
            str(minimum_command_runtime_seconds) if minimum_command_runtime_seconds is not None else ""
        ),
        "MISSION_CONTROL_REMOTE_MIN_FILE_TRANSFER_QUOTA_MB": (
            str(minimum_file_transfer_quota_mb) if minimum_file_transfer_quota_mb is not None else ""
        ),
        "MISSION_CONTROL_REMOTE_TARGET_COMMAND_RUNTIME_SECONDS": (
            str(target_command_runtime_seconds) if target_command_runtime_seconds is not None else ""
        ),
        "MISSION_CONTROL_REMOTE_TARGET_FILE_TRANSFER_QUOTA_MB": (
            str(target_file_transfer_quota_mb) if target_file_transfer_quota_mb is not None else ""
        ),
        "MISSION_CONTROL_REMOTE_QUOTA_CONTRACT_JSON": json.dumps(quota_contract),
        "MISSION_CONTROL_REMOTE_ESTIMATED_OUTBOUND_TRANSFER_BYTES": str(estimated_outbound_transfer_bytes),
        "MISSION_CONTROL_REMOTE_ESTIMATED_TOTAL_KNOWN_TRANSFER_BYTES": str(estimated_total_known_transfer_bytes),
        "MISSION_CONTROL_REMOTE_TARGET_FILE_TRANSFER_QUOTA_BYTES": (
            str(target_file_transfer_quota_bytes) if target_file_transfer_quota_bytes is not None else ""
        ),
        "MISSION_CONTROL_REMOTE_DECLARED_RESULT_ARTIFACT_PATHS_JSON": json.dumps(
            list(transfer_estimate.get("declared_result_artifact_paths") or [])
        ),
        "MISSION_CONTROL_REMOTE_TRANSFER_ESTIMATE_JSON": json.dumps(transfer_estimate),
        "MISSION_CONTROL_REMOTE_RESULT_COLLECTION_JSON": json.dumps(result_collection_contract),
    }

    exec_args: list[str] = []
    if normalized_command is not None and target:
        exec_args = build_remote_exec_args(
            target,
            command=normalized_command,
            args=_normalized_str_list(adapter_args),
            cwd=remote_workspace_root,
            env=environment,
        )

    notes = [
        "Launch planning now binds remote workspace root, path policy, and broker metadata into the executed runner command instead of leaving them as dashboard fanfiction.",
    ]
    if remote_workspace_root:
        notes.append(f"Remote runner will start inside `{remote_workspace_root}`.")
    else:
        notes.append("Selected target has no remote workspace root, so launch planning can only pass relative policy hints.")
    if policy_path_prefixes:
        notes.append(f"Remote write surface is narrowed to {len(policy_path_prefixes)} broker-declared path prefix(es).")
    if normalized_allowed_paths:
        notes.append(f"Task-level path locks contributed {len(normalized_allowed_paths)} allowed relative path(s).")
    if _normalized_text(result.get("normalized_summary_artifact")):
        notes.append("Normalized result capture is wired into the launch environment for brokered execution audit.")
    if _normalized_str_list(result.get("expected_evidence_categories")):
        notes.append(
            f"Result contract expects {len(_normalized_str_list(result.get('expected_evidence_categories')))} evidence categor(ies)."
        )
    if _normalized_str_list(result.get("adapter_contract_ids")):
        notes.append(
            f"Adapter contract metadata exposes {len(_normalized_str_list(result.get('adapter_contract_ids')))} contract binding(s) to the remote runner environment."
        )
    if int(result_collection_contract.get("remote_collectible_item_count") or 0) > 0:
        notes.append(
            f"Result collection contract exposes {int(result_collection_contract.get('remote_collectible_item_count') or 0)} remote-collectible artifact target(s)."
        )
    if broker.get("require_session_recording"):
        notes.append("Session recording is marked as required for this lane and is exported into the remote launch environment.")
    if any(value is not None for value in quota_contract.values()):
        notes.append("Quota policy is exported into the remote launch environment so adapters can enforce runtime and transfer ceilings instead of just admiring them from a summary.")
    if estimated_outbound_transfer_bytes:
        notes.append(
            f"Known outbound artifact payload is estimated at {estimated_outbound_transfer_bytes} byte(s) before any remote dispatch."
        )
    if target_file_transfer_quota_bytes is not None:
        notes.append(
            f"Target file-transfer quota allows {target_file_transfer_quota_bytes} byte(s) ({target_file_transfer_quota_mb} MiB) for governed transfer planning."
        )
    unknown_outbound_paths = list(transfer_estimate.get("estimated_outbound_unknown_paths") or [])
    if unknown_outbound_paths:
        notes.append(
            f"{len(unknown_outbound_paths)} outbound artifact path(s) could not be sized locally and are tracked as unknown in the transfer estimate."
        )

    return {
        "preflight_ready": not blocking_reasons and bool(exec_args),
        "target_id": str(target.get("id") or "").strip() or None,
        "target_label": str(target.get("label") or target.get("id") or "").strip() or None,
        "selected_target_probe_status": str(target.get("last_probe_status") or "unknown"),
        "required_runner_family": str(policy.get("required_runner_family") or "external_adapter"),
        "transport": str(target.get("transport") or "").strip() or None,
        "host": str(target.get("host") or "").strip() or None,
        "remote_workspace_root": remote_workspace_root,
        "remote_cwd": remote_workspace_root,
        "runner_command": normalized_command,
        "runner_args": _normalized_str_list(adapter_args),
        "adapter_command": normalized_command,
        "adapter_args": _normalized_str_list(adapter_args),
        "allowed_relative_paths": effective_allowed_paths,
        "allowed_remote_paths": allowed_remote_paths,
        "forbidden_relative_paths": normalized_forbidden_paths,
        "forbidden_remote_paths": forbidden_remote_paths,
        "allowed_repo_roots": target_repo_roots,
        "artifact_sync_enabled": bool(artifact.get("sync_enabled")),
        "remote_artifact_paths": _normalized_str_list(artifact.get("remote_workspace_artifact_paths")),
        "connector_families": _normalized_str_list(connector.get("available_families")),
        "required_result_formats": _normalized_str_list(broker.get("required_result_formats")),
        "target_result_formats": _normalized_str_list(broker.get("target_result_formats")),
        "required_command_families": _normalized_str_list(broker.get("required_command_families")),
        "target_command_families": _normalized_str_list(broker.get("target_command_families")),
        "required_toolchains": _normalized_str_list(broker.get("required_toolchains")),
        "target_toolchains": _normalized_str_list(broker.get("target_toolchains")),
        "adapter_contract_ids": _normalized_str_list(result.get("adapter_contract_ids")),
        "adapter_required_command_families": _normalized_str_list(
            result.get("adapter_required_command_families")
        ),
        "adapter_expected_result_formats": _normalized_str_list(
            result.get("adapter_expected_result_formats")
        ),
        "adapter_required_tool_families": _normalized_str_list(
            result.get("adapter_required_tool_families")
        ),
        "minimum_command_runtime_seconds": minimum_command_runtime_seconds,
        "minimum_file_transfer_quota_mb": minimum_file_transfer_quota_mb,
        "target_command_runtime_seconds": target_command_runtime_seconds,
        "target_file_transfer_quota_mb": target_file_transfer_quota_mb,
        "target_file_transfer_quota_bytes": target_file_transfer_quota_bytes,
        "estimated_outbound_transfer_bytes": estimated_outbound_transfer_bytes,
        "estimated_outbound_transfer_mb": transfer_estimate.get("estimated_outbound_transfer_mb"),
        "estimated_outbound_transfer_path_count": transfer_estimate.get("estimated_outbound_transfer_path_count"),
        "estimated_outbound_unknown_paths": list(transfer_estimate.get("estimated_outbound_unknown_paths") or []),
        "declared_result_artifact_paths": list(transfer_estimate.get("declared_result_artifact_paths") or []),
        "declared_result_artifact_count": transfer_estimate.get("declared_result_artifact_count"),
        "result_collection_contract": result_collection_contract,
        "known_result_transfer_bytes": transfer_estimate.get("known_result_transfer_bytes"),
        "known_result_transfer_mb": transfer_estimate.get("known_result_transfer_mb"),
        "estimated_total_known_transfer_bytes": estimated_total_known_transfer_bytes,
        "estimated_total_known_transfer_mb": transfer_estimate.get("estimated_total_known_transfer_mb"),
        "estimated_transfer_within_quota": estimated_transfer_within_quota,
        "expected_evidence_categories": _normalized_str_list(result.get("expected_evidence_categories")),
        "observed_evidence_categories": _normalized_str_list(result.get("observed_evidence_categories")),
        "normalized_summary_artifact": _normalized_text(result.get("normalized_summary_artifact")),
        "session_recording_required": bool(broker.get("require_session_recording")),
        "session_recording_enabled": bool(broker.get("session_recording_enabled")),
        "session_recording_artifact_paths": _normalized_str_list(result.get("session_recording_artifact_paths")),
        "remote_session_recording_artifact_paths": _normalized_str_list(
            result.get("remote_session_recording_artifact_paths")
        ),
        "primary_session_recording_artifact_path": _normalized_text(
            result.get("primary_session_recording_artifact_path")
        ),
        "primary_remote_session_recording_artifact_path": _normalized_text(
            result.get("primary_remote_session_recording_artifact_path")
        ),
        "environment": environment,
        "exec_args": exec_args,
        "command_preview": " ".join(exec_args),
        "blocking_reasons": _dedupe_preserving_order(blocking_reasons),
        "notes": notes,
    }


def _join_remote_path(root: str | None, relative: str) -> str:
    if not root:
        return relative.replace("\\", "/")
    normalized_root = root.rstrip("/\\")
    normalized_relative = relative.replace("\\", "/").lstrip("/")
    return f"{normalized_root}/{normalized_relative}"


def build_remote_exec_args(
    target: dict[str, Any],
    *,
    command: str,
    args: list[str] | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> list[str]:
    normalized_command = _normalized_text(command)
    if normalized_command is None:
        raise ValueError("Remote execution requires a concrete remote command.")
    remote_parts = [normalized_command, *(_normalized_str_list(args) or [])]
    shell_family = _normalized_shell_family(target.get("shell_family"), os_family=_normalized_os_family(target.get("os_family")))
    remote_command = _join_remote_command(
        remote_parts,
        shell_family=shell_family,
        cwd=_normalized_text(cwd),
        env={str(key): str(value) for key, value in dict(env or {}).items() if _normalized_text(key) is not None},
    )
    transport = _normalized_transport(target.get("transport"))
    host = _normalized_text(target.get("host"))
    if host is None:
        raise ValueError("Remote execution target is missing its host.")
    ssh_user = _normalized_text(target.get("ssh_user"))
    destination = f"{ssh_user}@{host}" if ssh_user else host
    if transport == "tailscale_ssh":
        return ["tailscale", "ssh", destination, remote_command]
    exec_args = ["ssh"]
    port = _normalized_int(target.get("ssh_port"), default=22, minimum=1)
    if port and port != 22:
        exec_args.extend(["-p", str(port)])
    exec_args.extend([destination, remote_command])
    return exec_args


def _join_remote_command(
    parts: list[str],
    *,
    shell_family: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    if shell_family == "powershell":
        statements = [f"$env:{key}={_powershell_quote(value)}" for key, value in dict(env or {}).items()]
        if cwd:
            statements.append(f"Set-Location {_powershell_quote(cwd)}")
        statements.append("& " + " ".join(_powershell_quote(part) for part in parts))
        return "; ".join(statements)
    statements = []
    if cwd:
        statements.append(f"cd {shlex.quote(cwd)}")
    if env:
        exports = " ".join(f"{key}={shlex.quote(value)}" for key, value in dict(env or {}).items())
        statements.append(f"export {exports}")
    statements.append(shlex.join(parts))
    return " && ".join(statements)


def _powershell_quote(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"
