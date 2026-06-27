from __future__ import annotations

import json
import shlex
import shutil
from collections.abc import Iterable
from typing import Any

from integration_registry import AUTHORITATIVE_CONNECTION_SOURCES, list_connections, normalize_integration_registry
from result_normalization import classify_evidence_artifacts


REMOTE_EXECUTION_REGISTRY_VERSION = 1
SUPPORTED_TRANSPORTS = {"ssh", "lan_ssh", "tailscale_ssh"}
SUPPORTED_SHELL_FAMILIES = {"posix", "powershell"}
SUPPORTED_OS_FAMILIES = {"windows", "linux", "macos", "unknown"}
SUPPORTED_RUNNER_FAMILIES = {"external_adapter", "codex_cli", "claude_code_cli"}
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


def _normalize_remote_target(payload: dict[str, Any]) -> dict[str, Any]:
    os_family = _normalized_os_family(payload.get("os_family"))
    label = _normalized_text(payload.get("label")) or "Remote Target"
    host = _normalized_text(payload.get("host")) or "unknown-host"
    transport = _normalized_transport(payload.get("transport"))
    target_id = _normalized_text(payload.get("id")) or _slugify_remote_target_id(label=label, host=host)
    ssh_user = _normalized_text(payload.get("ssh_user"))
    ssh_port = _normalized_int(payload.get("ssh_port"), default=22, minimum=1)
    workspace_root = _normalized_text(payload.get("workspace_root"))
    adapter_command = _normalized_text(payload.get("adapter_command"))
    adapter_args = _normalized_str_list(payload.get("adapter_args"))
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
                "adapter_command": _normalized_text(target.get("adapter_command")),
                "toolchains": _normalized_str_list(target.get("toolchains")),
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
    eligible: list[dict[str, Any]] = []
    ready_candidates: list[dict[str, Any]] = []
    scored: list[tuple[int, dict[str, Any], list[str]]] = []
    required_tags = set(policy["required_tags"])
    required_capabilities = set(policy["required_capabilities"])
    allowed_trust_levels = set(policy["allowed_trust_levels"])
    required_toolchains = set(policy["required_toolchains"])
    required_command_families = set(policy["required_command_families"])
    required_result_formats = set(policy["required_result_formats"])
    allowed_transports = set(policy["allowed_transports"])
    allowed_os_families = set(policy["allowed_os_families"])
    require_probe_ready = bool(policy.get("require_probe_ready"))
    for target in registry["targets"]:
        reasons: list[str] = []
        if not target.get("enabled"):
            reasons.append("target_disabled")
        if runner_family not in set(target.get("runner_families") or []):
            reasons.append("runner_family_not_supported")
        if runner_family == "external_adapter" and not _normalized_text(target.get("adapter_command")):
            reasons.append("remote_adapter_command_missing")
        if require_write and not target.get("allow_write"):
            reasons.append("write_not_allowed")
        if allowed_trust_levels and str(target.get("trust_level")) not in allowed_trust_levels:
            reasons.append("trust_level_not_allowed")
        if allowed_transports and str(target.get("transport")) not in allowed_transports:
            reasons.append("transport_not_allowed")
        if allowed_os_families and str(target.get("os_family")) not in allowed_os_families:
            reasons.append("os_family_not_allowed")
        if required_tags and not required_tags.issubset(set(target.get("tags") or [])):
            reasons.append("missing_required_tags")
        if required_capabilities and not required_capabilities.issubset(set(target.get("capabilities") or [])):
            reasons.append("missing_required_capabilities")
        if required_toolchains and not required_toolchains.issubset(set(target.get("toolchains") or [])):
            reasons.append("missing_required_toolchains")
        if required_command_families and not required_command_families.issubset(set(target.get("command_families") or [])):
            reasons.append("missing_required_command_families")
        if required_result_formats and not required_result_formats.issubset(set(target.get("result_formats") or [])):
            reasons.append("missing_required_result_formats")
        if policy.get("require_target_workspace_root") and not _normalized_text(target.get("workspace_root")):
            reasons.append("target_workspace_root_missing")
        if not remote_transport_client_available(str(target.get("transport") or "ssh")):
            reasons.append("local_transport_client_missing")
        if target.get("last_probe_status") == "failed":
            reasons.append("target_probe_failed")
        if require_probe_ready and target.get("last_probe_status") not in {"ready", "reachable"}:
            reasons.append("target_probe_not_ready")
        if reasons:
            scored.append((-1000, target, reasons))
            continue
        score = 0
        if target.get("id") == policy.get("preferred_target_id"):
            score += 100
        score += 20 if target.get("trust_level") == "trusted" else 0
        score += 8 if target.get("transport") == "tailscale_ssh" else 0
        score += 5 if target.get("last_probe_status") == "ready" else 0
        score += len(required_tags.intersection(set(target.get("tags") or []))) * 3
        score += len(required_capabilities.intersection(set(target.get("capabilities") or []))) * 3
        eligible.append(target)
        if target.get("last_probe_status") in {"ready", "reachable"}:
            ready_candidates.append(target)
        scored.append((score, target, []))
    scored.sort(key=lambda item: (item[0], str(item[1].get("label") or "").lower(), str(item[1].get("id") or "").lower()), reverse=True)
    selected = next((target for score, target, reasons in scored if score >= 0 and not reasons), None)
    if selected is not None and str(selected.get("last_probe_status") or "unknown") not in {"ready", "reachable"}:
        blocking_reasons.append("selected_target_probe_unverified")
    if selected is None and policy["enabled"] and not blocking_reasons:
        blocking_reasons.append("no_eligible_remote_targets")
    return {
        "policy": policy,
        "registry_summary": summarize_remote_execution_registry(registry),
        "required_runner_family": runner_family,
        "require_write_access": require_write,
        "eligible_target_count": len(eligible),
        "ready_candidate_count": len(ready_candidates),
        "ready_candidate_ids": [str(target.get("id") or "") for target in ready_candidates if str(target.get("id") or "").strip()],
        "selected_target": selected,
        "selected_target_id": selected.get("id") if selected else None,
        "selected_target_probe_status": str(selected.get("last_probe_status") or "unknown") if selected else "unknown",
        "preflight_ready": selected is not None and not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "candidates": [
            {
                "target_id": str(target.get("id")),
                "label": str(target.get("label")),
                "score": score,
                "rejected_reasons": reasons,
                "transport": target.get("transport"),
                "os_family": target.get("os_family"),
                "trust_level": target.get("trust_level"),
                "toolchains": list(target.get("toolchains") or []),
                "command_families": list(target.get("command_families") or []),
            }
            for score, target, reasons in scored
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


def build_remote_result_contract(
    *,
    selected_target: dict[str, Any] | None,
    policy_payload: dict[str, Any] | None,
    workspace_tooling_payload: dict[str, Any] | None,
    artifact_contract: dict[str, Any] | None = None,
    broker_contract: dict[str, Any] | None = None,
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

    expected_evidence_categories = ["logs"]
    if any(fmt in {"junit_xml", "xcresult", "json"} for fmt in required_result_formats + target_result_formats):
        expected_evidence_categories.append("coverage")
    if any(family in {"browser", "playwright"} for family in required_command_families + target_command_families):
        expected_evidence_categories.extend(["screenshots", "traces"])
    if any(family in {"unity_batchmode", "unreal_commandlet"} for family in required_command_families + target_command_families):
        expected_evidence_categories.extend(["screenshots"])
    if any(token in family for family in required_command_families + target_command_families for token in ("benchmark", "perf", "profile")):
        expected_evidence_categories.append("performance")
    expected_evidence_categories = _dedupe_preserving_order(expected_evidence_categories)

    missing_required_result_formats = [
        fmt for fmt in required_result_formats if fmt not in set(target_result_formats)
    ]
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
        "required_command_families": required_command_families,
        "required_toolchains": required_toolchains,
        "target_result_formats": target_result_formats,
        "target_command_families": target_command_families,
        "target_toolchains": target_toolchains,
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
    blocking_reasons = _dedupe_preserving_order(
        list(broker.get("blocking_reasons") or [])
        + list(artifact.get("blocking_reasons") or [])
        + list(connector.get("blocking_reasons") or [])
        + list(result.get("blocking_reasons") or [])
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
        "Launch planning now binds remote workspace root, path policy, and broker metadata into the executed command instead of leaving them as dashboard fanfiction.",
    ]
    if remote_workspace_root:
        notes.append(f"Remote adapter will start inside `{remote_workspace_root}`.")
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
    if broker.get("require_session_recording"):
        notes.append("Session recording is marked as required for this lane and is exported into the remote launch environment.")

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
