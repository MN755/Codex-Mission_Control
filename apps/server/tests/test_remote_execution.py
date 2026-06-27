from __future__ import annotations

import asyncio
import pytest

from manager import RunnerRegistry
from project_settings import ResolvedRunSettings
from remote_execution import (
    build_remote_capability_index,
    build_remote_broker_contract,
    build_remote_execution_contract,
    build_remote_exec_args,
    build_remote_launch_plan,
    build_remote_result_contract,
    normalize_remote_execution_policy,
    normalize_remote_execution_registry,
    select_remote_target,
    summarize_remote_execution_registry,
    upsert_remote_target,
)


def test_remote_execution_registry_normalizes_and_summarizes_targets(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry, _target = upsert_remote_target(
        None,
        {
            "label": "Edge Box",
            "transport": "tailscale_ssh",
            "host": "edge-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "tags": ["gpu", "trusted"],
            "capabilities": ["python", "gpu"],
            "runner_families": ["external_adapter"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )

    normalized = normalize_remote_execution_registry(registry)
    summary = summarize_remote_execution_registry(normalized)

    assert normalized["targets"][0]["id"] == "edge-box-edge-box-tailnet-ts-net"
    assert summary["target_count"] == 1
    assert summary["ready_target_count"] == 1
    assert summary["unknown_probe_target_count"] == 0
    assert summary["failed_probe_target_count"] == 0
    assert summary["transport_counts"]["tailscale_ssh"] == 1


def test_remote_capability_index_rolls_up_fleet_capabilities(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "linux-gpu",
                    "label": "Linux GPU",
                    "transport": "tailscale_ssh",
                    "host": "linux-gpu.tailnet.ts.net",
                    "os_family": "linux",
                    "architecture": "x86_64",
                    "gpu": "rtx-4090",
                    "capabilities": ["python", "gpu"],
                    "tags": ["gpu", "trusted"],
                    "adapter_command": "python3",
                    "toolchains": ["python3.11", "cuda12"],
                    "command_families": ["python", "git"],
                    "result_formats": ["json"],
                    "connector_families": ["source_control"],
                    "runner_families": ["external_adapter"],
                    "session_recording_enabled": True,
                    "max_command_runtime_seconds": 1800,
                    "file_transfer_quota_mb": 4096,
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                },
                {
                    "id": "windows-builder",
                    "label": "Windows Builder",
                    "transport": "ssh",
                    "host": "windows-builder.local",
                    "os_family": "windows",
                    "architecture": "x86_64",
                    "toolchains": ["vs2022", "unity6000"],
                    "command_families": ["powershell", "unity_batchmode"],
                    "result_formats": ["json", "junit_xml"],
                    "connector_families": ["source_control", "artifact_store"],
                    "runner_families": ["external_adapter"],
                    "trust_level": "limited",
                    "last_probe_status": "reachable",
                },
            ]
        }
    )

    index = build_remote_capability_index(registry)

    assert index["target_count"] == 2
    assert index["ready_target_count"] == 2
    assert index["toolchain_counts"]["cuda12"] == 1
    assert index["toolchain_counts"]["unity6000"] == 1
    assert index["command_family_counts"]["unity_batchmode"] == 1
    assert index["gpu_counts"]["rtx-4090"] == 1
    assert index["connector_family_counts"]["source_control"] == 2
    linux_gpu = next(item for item in index["targets"] if item["target_id"] == "linux-gpu")
    assert linux_gpu["runner_families"] == ["external_adapter"]
    assert linux_gpu["capabilities"] == ["python", "gpu"]
    assert linux_gpu["tags"] == ["gpu", "trusted"]
    assert linux_gpu["adapter_command"] == "python3"
    assert linux_gpu["session_recording_enabled"] is True
    assert linux_gpu["max_command_runtime_seconds"] == 1800
    assert linux_gpu["file_transfer_quota_mb"] == 4096


def test_remote_execution_selection_prefers_matching_preferred_target(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "slow-box",
                    "label": "Slow Box",
                    "transport": "ssh",
                    "host": "slow-box.local",
                    "os_family": "linux",
                    "adapter_command": "python3",
                    "runner_families": ["external_adapter"],
                    "capabilities": ["python"],
                    "tags": ["cpu"],
                    "trust_level": "limited",
                    "last_probe_status": "ready",
                },
                {
                    "id": "fast-box",
                    "label": "Fast Box",
                    "transport": "tailscale_ssh",
                    "host": "fast-box.tailnet.ts.net",
                    "ssh_user": "mike",
                    "os_family": "linux",
                    "adapter_command": "python3",
                    "runner_families": ["external_adapter"],
                    "capabilities": ["python", "gpu"],
                    "tags": ["gpu"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                },
            ]
        }
    )
    policy = normalize_remote_execution_policy(
        {
            "enabled": True,
            "preferred_target_id": "fast-box",
            "required_runner_family": "external_adapter",
            "required_tags": ["gpu"],
            "required_capabilities": ["python"],
            "fallback_to_local": False,
        }
    )

    selection = select_remote_target(registry, policy)

    assert selection["preflight_ready"] is True
    assert selection["selected_target_id"] == "fast-box"
    assert selection["eligible_target_count"] == 1
    assert selection["ready_candidate_count"] == 1
    assert selection["ready_candidate_ids"] == ["fast-box"]
    assert selection["selected_target_probe_status"] == "ready"


def test_build_remote_exec_args_supports_ssh_and_powershell() -> None:
    args = build_remote_exec_args(
        {
            "transport": "ssh",
            "host": "windows-builder.local",
            "ssh_user": "mike",
            "ssh_port": 2222,
            "os_family": "windows",
            "shell_family": "powershell",
        },
        command="python",
        args=["C:\\mission-control\\adapter.py", "--project", "demo app"],
    )

    assert args[:4] == ["ssh", "-p", "2222", "mike@windows-builder.local"]
    assert "'demo app'" in args[-1]


def test_build_remote_exec_args_includes_remote_cwd_and_env_for_posix() -> None:
    args = build_remote_exec_args(
        {
            "transport": "ssh",
            "host": "linux-builder.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "shell_family": "posix",
        },
        command="python3",
        args=["/opt/mission-control/adapter.py"],
        cwd="/srv/shadow",
        env={"MISSION_CONTROL_REMOTE_TARGET_ID": "gpu-box"},
    )

    assert args[:2] == ["ssh", "mike@linux-builder.local"]
    assert "cd /srv/shadow" in args[-1]
    assert "export MISSION_CONTROL_REMOTE_TARGET_ID=gpu-box" in args[-1]


def test_build_remote_launch_plan_maps_workspace_and_policy_to_remote_execution() -> None:
    plan = build_remote_launch_plan(
        selected_target={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "shell_family": "posix",
            "workspace_root": "/srv/shadow",
        },
        policy_payload={"enabled": True, "required_runner_family": "external_adapter"},
        adapter_command="python3",
        adapter_args=["/opt/mission-control/adapter.py"],
        broker_contract={
            "preflight_ready": True,
            "blocking_reasons": [],
            "target_repo_roots": ["/srv/shadow"],
            "target_path_prefixes": ["src", "artifacts"],
            "target_command_families": ["python", "git"],
            "target_toolchains": ["python3.11", "cuda12"],
            "require_session_recording": True,
            "session_recording_enabled": True,
        },
        artifact_contract={
            "sync_enabled": True,
            "blocking_reasons": [],
            "remote_workspace_artifact_paths": ["/srv/shadow/artifacts/model.onnx"],
        },
        connector_contract={
            "blocking_reasons": [],
            "available_families": ["source_control"],
        },
        workspace_path="/workspace/demo",
        allowed_paths=["src", "/workspace/demo/artifacts/model.onnx"],
        forbidden_paths=["secrets"],
    )

    assert plan["preflight_ready"] is True, plan
    assert plan["selected_target_probe_status"] == "unknown"
    assert plan["required_runner_family"] == "external_adapter"
    assert plan["remote_workspace_root"] == "/srv/shadow"
    assert plan["allowed_relative_paths"] == ["src", "artifacts/model.onnx"]
    assert plan["allowed_remote_paths"] == ["/srv/shadow/src", "/srv/shadow/artifacts/model.onnx"]
    assert plan["forbidden_relative_paths"] == ["secrets"]
    assert plan["connector_families"] == ["source_control"]
    assert plan["required_result_formats"] == []
    assert plan["target_result_formats"] == []
    assert plan["expected_evidence_categories"] == []
    assert plan["session_recording_required"] is True
    assert plan["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-box.cast"
    ]
    assert plan["remote_session_recording_artifact_paths"] == [
        "/srv/shadow/artifacts/remote-execution-governance/session-recordings/gpu-box.cast"
    ]
    assert plan["environment"]["MISSION_CONTROL_REMOTE_SESSION_RECORDING_PRIMARY_ARTIFACT_PATH"] == (
        "/srv/shadow/artifacts/remote-execution-governance/session-recordings/gpu-box.cast"
    )
    assert plan["environment"]["MISSION_CONTROL_REMOTE_TARGET_ID"] == "gpu-box"
    assert "cd /srv/shadow" in plan["command_preview"]


def test_build_remote_launch_plan_blocks_task_paths_outside_remote_policy() -> None:
    plan = build_remote_launch_plan(
        selected_target={
            "id": "gpu-box",
            "transport": "ssh",
            "host": "gpu-box.local",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
        },
        policy_payload={"enabled": True, "required_runner_family": "external_adapter"},
        adapter_command="python3",
        adapter_args=["adapter.py"],
        broker_contract={
            "preflight_ready": True,
            "blocking_reasons": [],
            "target_repo_roots": ["/srv/shadow"],
            "target_path_prefixes": ["src"],
            "target_command_families": ["python"],
            "target_toolchains": ["python3.11"],
            "require_session_recording": False,
            "session_recording_enabled": False,
        },
        workspace_path="/workspace/demo",
        allowed_paths=["docs"],
    )

    assert plan["preflight_ready"] is False
    assert "task_allowed_paths_outside_remote_policy" in plan["blocking_reasons"]


def test_build_remote_launch_plan_respects_result_contract_blockers() -> None:
    plan = build_remote_launch_plan(
        selected_target={
            "id": "gpu-box",
            "transport": "ssh",
            "host": "gpu-box.local",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "last_probe_status": "ready",
        },
        policy_payload={"enabled": True, "required_runner_family": "external_adapter"},
        adapter_command="python3",
        adapter_args=["adapter.py"],
        broker_contract={
            "preflight_ready": True,
            "blocking_reasons": [],
            "target_repo_roots": ["/srv/shadow"],
            "target_path_prefixes": ["src"],
            "required_result_formats": ["json"],
            "target_result_formats": ["text"],
            "target_command_families": ["python"],
            "target_toolchains": ["python3.11"],
            "require_session_recording": False,
            "session_recording_enabled": False,
        },
        result_contract={
            "blocking_reasons": ["remote_result_formats_missing"],
            "required_result_formats": ["json"],
            "target_result_formats": ["text"],
            "expected_evidence_categories": ["logs", "coverage"],
            "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
        },
        workspace_path="/workspace/demo",
    )

    assert plan["preflight_ready"] is False
    assert plan["selected_target_probe_status"] == "ready"
    assert plan["required_result_formats"] == ["json"]
    assert plan["target_result_formats"] == ["text"]
    assert plan["expected_evidence_categories"] == ["logs", "coverage"]
    assert (
        plan["environment"]["MISSION_CONTROL_REMOTE_NORMALIZED_SUMMARY_ARTIFACT"]
        == "artifacts/remote-execution-governance/normalized-execution-summary.json"
    )
    assert "remote_result_formats_missing" in plan["blocking_reasons"]


def test_runner_registry_selects_remote_adapter_when_remote_target_is_ready(monkeypatch) -> None:
    registry = RunnerRegistry()

    async def fake_handshake(settings=None) -> bool:
        remote_execution = dict(getattr(settings, "remote_execution", None) or {})
        return bool(remote_execution.get("selected_target", {}).get("id") == "fast-box")

    monkeypatch.setattr(registry.runners["remote_adapter"], "handshake", fake_handshake)
    resolved = ResolvedRunSettings(
        provider="openai_api",
        provider_label="OpenAI API",
        provider_endpoint=None,
        runner_mode="auto",
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        model="gpt-4.1-mini",
        reasoning_effort="medium",
        adapter_command="python",
        adapter_args=["adapter.py"],
        effective_model_label="gpt-4.1-mini",
        effective_reasoning_label="medium",
        remote_execution={
            "policy": {
                "enabled": True,
                "required_runner_family": "external_adapter",
                "fallback_to_local": False,
            },
            "selection": {
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "selected_target": {
                "id": "fast-box",
                "transport": "tailscale_ssh",
                "host": "fast-box.tailnet.ts.net",
                "adapter_command": "python3",
            },
        },
    )

    runner = asyncio.run(registry.get_runner_for_settings(resolved))
    assert runner.runner_type == "remote_adapter"


def test_runner_registry_rejects_remote_adapter_when_contract_is_not_ready(monkeypatch) -> None:
    registry = RunnerRegistry()

    async def fake_handshake(settings=None) -> bool:
        return True

    monkeypatch.setattr(registry.runners["remote_adapter"], "handshake", fake_handshake)
    resolved = ResolvedRunSettings(
        provider="openai_api",
        provider_label="OpenAI API",
        provider_endpoint=None,
        runner_mode="auto",
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        model="gpt-4.1-mini",
        reasoning_effort="medium",
        adapter_command="python",
        adapter_args=["adapter.py"],
        effective_model_label="gpt-4.1-mini",
        effective_reasoning_label="medium",
        remote_execution={
            "policy": {
                "enabled": True,
                "required_runner_family": "external_adapter",
                "fallback_to_local": False,
            },
            "selection": {
                "preflight_ready": False,
                "blocking_reasons": ["required_remote_connectors_missing"],
            },
            "selected_target": {
                "id": "fast-box",
                "transport": "tailscale_ssh",
                "host": "fast-box.tailnet.ts.net",
                "adapter_command": "python3",
            },
        },
    )

    with pytest.raises(RuntimeError, match="No available runner"):
        asyncio.run(registry.get_runner_for_settings(resolved))


def test_remote_execution_contract_includes_artifact_and_connector_layers(monkeypatch) -> None:
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "edge-box",
                    "label": "Edge Box",
                    "transport": "tailscale_ssh",
                    "host": "edge-box.tailnet.ts.net",
                    "ssh_user": "mike",
                    "os_family": "linux",
                    "workspace_root": "/srv/shadow-repo",
                    "artifact_roots": ["/srv/shadow-repo/artifacts"],
                    "connector_families": ["source_control"],
                    "adapter_command": "python3",
                    "runner_families": ["external_adapter"],
                    "capabilities": ["python", "gpu"],
                    "tags": ["gpu"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                }
            ]
        }
    )
    policy = normalize_remote_execution_policy(
        {
            "enabled": True,
            "preferred_target_id": "edge-box",
            "required_runner_family": "external_adapter",
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        }
    )
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    contract = build_remote_execution_contract(
        registry,
        policy,
        integration_registry_payload={
            "connections": {
                "source_control": {
                    "family": "source_control",
                    "status": "connected",
                    "providers": ["github"],
                    "connection_source": "manual",
                    "host_imported": False,
                    "notes": [],
                }
            }
        },
        workspace_tooling_payload={
            "artifact_paths": ["artifacts/model.onnx"],
            "artifact_kind_summaries": ["onnx:1"],
            "artifact_inspection_commands": ["python inspect_artifacts.py"],
        },
    )

    assert contract["preflight_ready"] is True, contract
    assert contract["artifact_contract"]["local_artifact_path_count"] == 1
    assert contract["artifact_contract"]["selected_artifact_root"] == "/srv/shadow-repo/artifacts"
    assert contract["artifact_contract"]["remote_workspace_artifact_paths"] == ["/srv/shadow-repo/artifacts/model.onnx"]
    assert contract["connector_contract"]["available_families"] == ["source_control"]
    assert contract["result_contract"]["required_result_formats"] == []
    assert contract["result_contract"]["expected_evidence_categories"] == ["logs"]


def test_remote_execution_selection_blocks_external_adapter_target_without_remote_command(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "broken-box",
                    "label": "Broken Box",
                    "transport": "ssh",
                    "host": "broken-box.local",
                    "os_family": "linux",
                    "runner_families": ["external_adapter"],
                    "capabilities": ["python"],
                    "tags": ["cpu"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                }
            ]
        }
    )
    policy = normalize_remote_execution_policy(
        {
            "enabled": True,
            "required_runner_family": "external_adapter",
            "fallback_to_local": False,
        }
    )

    selection = select_remote_target(registry, policy)

    assert selection["preflight_ready"] is False
    assert selection["selected_target_id"] is None
    assert "no_eligible_remote_targets" in selection["blocking_reasons"]
    assert selection["candidates"][0]["rejected_reasons"] == ["remote_adapter_command_missing"]


def test_remote_execution_selection_can_require_probe_ready(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "unknown-box",
                    "label": "Unknown Box",
                    "transport": "ssh",
                    "host": "unknown-box.local",
                    "os_family": "linux",
                    "adapter_command": "python3",
                    "runner_families": ["external_adapter"],
                    "capabilities": ["python"],
                    "tags": ["cpu"],
                    "trust_level": "trusted",
                    "last_probe_status": "unknown",
                }
            ]
        }
    )
    policy = normalize_remote_execution_policy(
        {
            "enabled": True,
            "required_runner_family": "external_adapter",
            "fallback_to_local": False,
            "require_probe_ready": True,
        }
    )

    selection = select_remote_target(registry, policy)

    assert selection["preflight_ready"] is False
    assert selection["selected_target_id"] is None
    assert "no_eligible_remote_targets" in selection["blocking_reasons"]
    assert selection["candidates"][0]["rejected_reasons"] == ["target_probe_not_ready"]


def test_remote_execution_selection_marks_unknown_probe_target_not_preflight_ready(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "unknown-box",
                    "label": "Unknown Box",
                    "transport": "ssh",
                    "host": "unknown-box.local",
                    "os_family": "linux",
                    "adapter_command": "python3",
                    "runner_families": ["external_adapter"],
                    "capabilities": ["python"],
                    "tags": ["cpu"],
                    "trust_level": "trusted",
                    "last_probe_status": "unknown",
                }
            ]
        }
    )
    policy = normalize_remote_execution_policy(
        {
            "enabled": True,
            "required_runner_family": "external_adapter",
            "fallback_to_local": False,
        }
    )

    selection = select_remote_target(registry, policy)

    assert selection["selected_target_id"] == "unknown-box"
    assert selection["eligible_target_count"] == 1
    assert selection["ready_candidate_count"] == 0
    assert selection["ready_candidate_ids"] == []
    assert selection["selected_target_probe_status"] == "unknown"
    assert selection["preflight_ready"] is False
    assert selection["blocking_reasons"] == ["selected_target_probe_unverified"]
    assert selection["candidates"][0]["rejected_reasons"] == []


def test_remote_execution_registry_summary_does_not_count_unknown_probe_targets_as_ready(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "unknown-box",
                    "label": "Unknown Box",
                    "transport": "ssh",
                    "host": "unknown-box.local",
                    "os_family": "linux",
                    "adapter_command": "python3",
                    "runner_families": ["external_adapter"],
                    "trust_level": "trusted",
                    "last_probe_status": "unknown",
                }
            ]
        }
    )

    summary = summarize_remote_execution_registry(registry)

    assert summary["target_count"] == 1
    assert summary["ready_target_count"] == 0
    assert summary["ready_target_ids"] == []
    assert summary["unknown_probe_target_count"] == 1


def test_remote_execution_selection_requires_toolchains_and_command_families(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "gpu-builder",
                    "label": "GPU Builder",
                    "transport": "tailscale_ssh",
                    "host": "gpu-builder.tailnet.ts.net",
                    "os_family": "linux",
                    "workspace_root": "/srv/shadow-repo",
                    "adapter_command": "python3",
                    "runner_families": ["external_adapter"],
                    "capabilities": ["python", "gpu"],
                    "toolchains": ["python3.11", "cuda12", "unity6000"],
                    "command_families": ["python", "git", "unity_batchmode"],
                    "result_formats": ["json", "junit_xml"],
                    "tags": ["gpu"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                }
            ]
        }
    )
    policy = normalize_remote_execution_policy(
        {
            "enabled": True,
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["unity_batchmode"],
            "required_result_formats": ["json"],
            "require_target_workspace_root": True,
            "fallback_to_local": False,
        }
    )

    selection = select_remote_target(registry, policy)

    assert selection["preflight_ready"] is True, selection
    assert selection["selected_target_id"] == "gpu-builder"
    assert selection["candidates"][0]["toolchains"] == ["python3.11", "cuda12", "unity6000"]
    assert selection["candidates"][0]["command_families"] == ["python", "git", "unity_batchmode"]


def test_remote_broker_contract_blocks_missing_governance_fields() -> None:
    contract = build_remote_broker_contract(
        selected_target={
            "id": "weak-box",
            "workspace_root": None,
            "toolchains": ["python3.11"],
            "command_families": ["python"],
            "result_formats": ["json"],
            "session_recording_enabled": False,
            "max_command_runtime_seconds": 300,
            "file_transfer_quota_mb": 128,
            "allowed_repo_roots": ["/srv/other-repo"],
            "allowed_path_prefixes": ["src"],
        },
        policy_payload={
            "enabled": True,
            "require_target_workspace_root": True,
            "require_session_recording": True,
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["junit_xml"],
            "required_repo_roots": ["/srv/shadow-repo"],
            "required_path_prefixes": ["artifacts"],
            "minimum_command_runtime_seconds": 600,
            "minimum_file_transfer_quota_mb": 256,
        },
    )

    assert contract["preflight_ready"] is False
    assert contract["blocking_reasons"] == [
        "broker_toolchains_missing",
        "broker_command_families_missing",
        "broker_result_formats_missing",
        "broker_session_recording_required",
        "broker_workspace_root_required",
        "broker_repo_roots_missing",
        "broker_path_prefixes_missing",
        "broker_command_runtime_too_small",
        "broker_file_transfer_quota_too_small",
    ]


def test_remote_execution_contract_includes_broker_layer(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "governed-box",
                    "label": "Governed Box",
                    "transport": "tailscale_ssh",
                    "host": "governed-box.tailnet.ts.net",
                    "os_family": "linux",
                    "workspace_root": "/srv/shadow-repo",
                    "adapter_command": "python3",
                    "runner_families": ["external_adapter"],
                    "capabilities": ["python", "gpu"],
                    "toolchains": ["python3.11", "cuda12"],
                    "command_families": ["python", "git"],
                    "result_formats": ["json", "junit_xml"],
                    "session_recording_enabled": True,
                    "max_command_runtime_seconds": 1200,
                    "file_transfer_quota_mb": 2048,
                    "allowed_repo_roots": ["/srv/shadow-repo"],
                    "allowed_path_prefixes": ["src", "artifacts"],
                    "artifact_roots": ["/srv/shadow-repo/artifacts"],
                    "connector_families": ["source_control"],
                    "tags": ["gpu"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                }
            ]
        }
    )
    policy = normalize_remote_execution_policy(
        {
            "enabled": True,
            "preferred_target_id": "governed-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow-repo"],
            "required_path_prefixes": ["artifacts"],
            "minimum_command_runtime_seconds": 600,
            "minimum_file_transfer_quota_mb": 512,
            "required_connector_families": ["source_control"],
            "artifact_required": False,
            "fallback_to_local": False,
        }
    )

    contract = build_remote_execution_contract(
        registry,
        policy,
        integration_registry_payload={
            "connections": {
                "source_control": {
                    "family": "source_control",
                    "status": "connected",
                    "providers": ["github"],
                    "connection_source": "manual",
                    "host_imported": False,
                    "notes": [],
                }
            }
        },
        workspace_tooling_payload={"artifact_paths": ["artifacts/model.onnx"]},
    )

    assert contract["preflight_ready"] is True, contract
    assert contract["broker_contract"]["preflight_ready"] is True
    assert contract["broker_contract"]["target_toolchains"] == ["python3.11", "cuda12"]
    assert contract["broker_contract"]["target_command_families"] == ["python", "git"]


def test_remote_result_contract_describes_expected_and_observed_evidence_categories() -> None:
    contract = build_remote_result_contract(
        selected_target={
            "id": "browser-box",
            "result_formats": ["json", "junit_xml"],
            "command_families": ["browser", "python"],
            "toolchains": ["python3.11"],
            "workspace_root": "/srv/browser-work",
        },
        policy_payload={
            "enabled": True,
            "required_result_formats": ["json"],
            "required_command_families": ["browser"],
            "required_toolchains": ["python3.11"],
            "require_session_recording": True,
        },
        workspace_tooling_payload={
            "validation_evidence_targets": ["artifacts/screenshots/home.png", "artifacts/coverage/lcov.info"],
            "artifact_paths": ["artifacts/traces/playwright-trace.zip"],
            "execution_entrypoints": ["playwright test"],
        },
        artifact_contract={
            "selected_artifact_root": "/srv/browser-work/artifacts",
            "remote_workspace_root": "/srv/browser-work",
        },
        broker_contract={"require_session_recording": True, "session_recording_enabled": True},
    )

    assert contract["preflight_ready"] is True
    assert contract["expected_evidence_categories"] == ["logs", "coverage", "screenshots", "traces"]
    assert contract["observed_evidence_categories"] == ["screenshots", "traces", "coverage"]
    assert contract["normalized_summary_artifact"] == "artifacts/remote-execution-governance/normalized-execution-summary.json"
    assert contract["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
    ]
    assert contract["remote_session_recording_artifact_paths"] == [
        "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
    ]
