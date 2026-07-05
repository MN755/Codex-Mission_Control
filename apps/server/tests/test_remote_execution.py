from __future__ import annotations

import asyncio
import json
import pytest

from manager import RunnerRegistry
from project_settings import ResolvedRunSettings
from remote_execution import (
    build_remote_capability_index,
    build_remote_broker_contract,
    build_remote_execution_contract,
    build_remote_exec_args,
    build_remote_launch_plan,
    build_remote_result_collection_contract,
    build_remote_result_contract,
    build_remote_transfer_bundle,
    normalize_remote_execution_policy,
    normalize_remote_execution_registry,
    resolve_device_broker_request,
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


def test_remote_execution_registry_accepts_runner_command_alias(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    normalized = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "runner-box",
                    "label": "Runner Box",
                    "transport": "tailscale_ssh",
                    "host": "runner-box.tailnet.ts.net",
                    "os_family": "linux",
                    "runner_command": "python3",
                    "runner_args": ["/opt/mission-control/runner.py"],
                    "runner_families": ["external_adapter"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                }
            ]
        }
    )

    target = normalized["targets"][0]
    assert target["runner_command"] == "python3"
    assert target["runner_args"] == ["/opt/mission-control/runner.py"]
    assert target["adapter_command"] == "python3"
    assert target["adapter_args"] == ["/opt/mission-control/runner.py"]


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
    assert linux_gpu["runner_command"] == "python3"
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


@pytest.mark.parametrize(
    ("intent", "request_payload", "expected_target_id"),
    [
        (
            "run on Windows UE5 host",
            {
                "required_runner_families": ["windows_agent_runner"],
                "required_os_families": ["windows"],
                "required_toolchains": ["ue5", "vs2022"],
                "required_installed_runtimes": ["unreal_engine_5.4"],
                "required_command_families": ["powershell"],
            },
            "windows-ue5",
        ),
        (
            "run on Linux CUDA host",
            {
                "required_runner_families": ["tailscale_ssh_runner"],
                "required_os_families": ["linux"],
                "require_gpu": True,
                "required_toolchains": ["cuda12", "python3.11"],
                "required_installed_runtimes": ["docker", "nvidia_container_toolkit"],
                "required_command_families": ["python"],
            },
            "linux-cuda",
        ),
        (
            "run on macOS Xcode host",
            {
                "required_runner_families": ["macos_agent_runner"],
                "required_os_families": ["macos"],
                "required_toolchains": ["xcode16", "swift5.10"],
                "required_installed_runtimes": ["xcode_16", "ios_simulator"],
                "required_command_families": ["xcodebuild"],
            },
            "macos-xcode",
        ),
    ],
)
def test_device_broker_request_resolves_specialized_hosts(
    monkeypatch,
    intent: str,
    request_payload: dict[str, object],
    expected_target_id: str,
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "linux-cuda",
                    "label": "Linux CUDA",
                    "transport": "tailscale_ssh",
                    "host": "linux-cuda.tailnet.ts.net",
                    "ssh_user": "mike",
                    "os_family": "linux",
                    "architecture": "x86_64",
                    "gpu": "rtx-4090",
                    "toolchains": ["cuda12", "python3.11"],
                    "installed_runtimes": ["docker", "nvidia_container_toolkit"],
                    "command_families": ["python", "bash"],
                    "result_formats": ["json"],
                    "runner_families": ["external_adapter", "tailscale_ssh_runner"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                    "session_recording_enabled": True,
                },
                {
                    "id": "windows-ue5",
                    "label": "Windows UE5",
                    "transport": "ssh",
                    "host": "windows-ue5.local",
                    "ssh_user": "mike",
                    "os_family": "windows",
                    "architecture": "x86_64",
                    "toolchains": ["ue5", "vs2022"],
                    "installed_runtimes": ["unreal_engine_5.4", "dotnet8"],
                    "command_families": ["powershell", "unreal_automation"],
                    "result_formats": ["json", "junit_xml"],
                    "runner_families": ["windows_agent_runner"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                    "session_recording_enabled": True,
                },
                {
                    "id": "macos-xcode",
                    "label": "macOS Xcode",
                    "transport": "ssh",
                    "host": "macos-xcode.local",
                    "ssh_user": "mike",
                    "os_family": "macos",
                    "architecture": "arm64",
                    "toolchains": ["xcode16", "swift5.10"],
                    "installed_runtimes": ["xcode_16", "ios_simulator"],
                    "command_families": ["xcodebuild", "swift"],
                    "result_formats": ["json", "xcresult"],
                    "runner_families": ["macos_agent_runner"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                    "session_recording_enabled": True,
                },
            ]
        }
    )

    resolution = resolve_device_broker_request(
        registry,
        {
            "intent": intent,
            "require_probe_ready": True,
            **request_payload,
        },
    )

    assert resolution["resolution_status"] == "ready"
    assert resolution["selected_target_id"] == expected_target_id
    assert resolution["blocking_reasons"] == []
    assert resolution["ready_candidate_count"] >= 1


def test_device_broker_request_reports_blocked_when_required_runtime_is_missing(monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "macos-xcode",
                    "label": "macOS Xcode",
                    "transport": "ssh",
                    "host": "macos-xcode.local",
                    "ssh_user": "mike",
                    "os_family": "macos",
                    "architecture": "arm64",
                    "toolchains": ["xcode16", "swift5.10"],
                    "installed_runtimes": ["xcode_16", "ios_simulator"],
                    "command_families": ["xcodebuild", "swift"],
                    "result_formats": ["json", "xcresult"],
                    "runner_families": ["macos_agent_runner"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                }
            ]
        }
    )

    resolution = resolve_device_broker_request(
        registry,
        {
            "intent": "run on macOS Xcode 17 host",
            "required_runner_families": ["macos_agent_runner"],
            "required_os_families": ["macos"],
            "required_toolchains": ["xcode17"],
            "required_installed_runtimes": ["xcode_17"],
            "require_probe_ready": True,
        },
    )

    assert resolution["resolution_status"] == "blocked"
    assert resolution["selected_target_id"] is None
    assert "no_eligible_device_broker_targets" in resolution["blocking_reasons"]
    assert resolution["candidates"][0]["rejected_reasons"] == [
        "missing_required_toolchains",
        "missing_required_installed_runtimes",
    ]
    assert resolution["candidates"][0]["requirement_gaps"] == {
        "toolchains": ["xcode17"],
        "installed_runtimes": ["xcode_17"],
    }
    assert (
        resolution["availability_diagnostics"]["summary"]
        == "No eligible device broker targets matched `run on macOS Xcode 17 host`. Top blockers: missing_required_installed_runtimes (1), missing_required_toolchains (1)."
    )
    assert resolution["availability_diagnostics"]["rejection_reason_counts"] == {
        "missing_required_toolchains": 1,
        "missing_required_installed_runtimes": 1,
    }
    assert resolution["availability_diagnostics"]["requirement_gap_counts"]["toolchains"] == {"xcode17": 1}
    assert resolution["availability_diagnostics"]["requirement_gap_counts"]["installed_runtimes"] == {
        "xcode_17": 1
    }
    assert resolution["availability_diagnostics"]["notes"] == [
        "Required toolchains are missing on the indexed fleet; add them to a host or relax the request.",
        "Installed runtime requirements are stricter than what the indexed hosts advertise.",
    ]


def test_device_broker_request_reports_probe_and_transport_unavailability(monkeypatch) -> None:
    monkeypatch.setattr(
        "remote_execution.remote_transport_client_available",
        lambda transport: transport != "tailscale_ssh",
    )
    registry = normalize_remote_execution_registry(
        {
            "targets": [
                {
                    "id": "linux-cuda",
                    "label": "Linux CUDA",
                    "transport": "tailscale_ssh",
                    "host": "linux-cuda.tailnet.ts.net",
                    "ssh_user": "mike",
                    "os_family": "linux",
                    "toolchains": ["cuda12", "python3.11"],
                    "installed_runtimes": ["docker"],
                    "command_families": ["python"],
                    "runner_families": ["external_adapter", "tailscale_ssh_runner"],
                    "trust_level": "trusted",
                    "last_probe_status": "ready",
                    "session_recording_enabled": True,
                }
            ]
        }
    )

    resolution = resolve_device_broker_request(
        registry,
        {
            "intent": "run on Linux CUDA host",
            "required_runner_families": ["tailscale_ssh_runner"],
            "required_os_families": ["linux"],
            "required_toolchains": ["cuda12"],
            "required_installed_runtimes": ["docker"],
            "required_command_families": ["python"],
            "require_probe_ready": True,
        },
    )

    assert resolution["resolution_status"] == "blocked"
    assert resolution["selected_target_id"] is None
    assert resolution["blocking_reasons"] == ["no_eligible_device_broker_targets"]
    assert resolution["candidates"][0]["rejected_reasons"] == [
        "local_transport_client_missing",
        "target_probe_not_ready",
    ]
    assert resolution["candidates"][0]["requirement_gaps"] == {
        "transport_client": ["tailscale_ssh"],
        "probe_status": ["ready"],
    }
    assert (
        resolution["availability_diagnostics"]["summary"]
        == "No eligible device broker targets matched `run on Linux CUDA host`. Top blockers: local_transport_client_missing (1), target_probe_not_ready (1)."
    )
    assert resolution["availability_diagnostics"]["notes"] == [
        "Mission Control lacks a local transport client for at least one candidate transport.",
        "At least one candidate host exists but is not probe-ready yet, so broker execution stays governed instead of YOLO-routing.",
    ]


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


def test_build_remote_launch_plan_estimates_outbound_transfer_and_exports_it(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact_path = workspace / "artifacts" / "model.onnx"
    artifact_path.parent.mkdir(parents=True)
    artifact_bytes = b"artifact-payload"
    artifact_path.write_bytes(artifact_bytes)

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
            "target_path_prefixes": ["artifacts"],
            "target_command_families": ["python"],
            "target_toolchains": ["python3.11"],
            "target_file_transfer_quota_mb": 2,
            "require_session_recording": False,
            "session_recording_enabled": False,
        },
        artifact_contract={
            "sync_enabled": True,
            "blocking_reasons": [],
            "local_artifact_paths": ["artifacts/model.onnx"],
            "remote_workspace_artifact_paths": ["/srv/shadow/artifacts/model.onnx"],
        },
        result_contract={
            "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
            "session_recording_artifact_paths": ["artifacts/remote-execution-governance/session-recordings/gpu-box.cast"],
        },
        workspace_path=workspace.as_posix(),
        allowed_paths=["artifacts/model.onnx"],
    )

    assert plan["preflight_ready"] is True, plan
    assert plan["estimated_outbound_transfer_bytes"] == len(artifact_bytes)
    assert plan["estimated_outbound_transfer_path_count"] == 1
    assert plan["estimated_outbound_unknown_paths"] == []
    assert plan["declared_result_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-box.cast",
        "artifacts/remote-execution-governance/normalized-execution-summary.json",
    ]
    assert plan["known_result_transfer_bytes"] == 0
    assert plan["estimated_total_known_transfer_bytes"] == len(artifact_bytes)
    assert plan["estimated_transfer_within_quota"] is True
    assert plan["result_collection_contract"]["declared_item_count"] == 3
    assert plan["result_collection_contract"]["remote_collectible_item_count"] == 1
    assert [item["collection_stage"] for item in plan["result_collection_contract"]["items"]] == [
        "remote_workspace_artifact",
        "remote_session_recording",
        "normalized_summary",
    ]
    assert plan["environment"]["MISSION_CONTROL_REMOTE_ESTIMATED_OUTBOUND_TRANSFER_BYTES"] == str(len(artifact_bytes))
    assert json.loads(plan["environment"]["MISSION_CONTROL_REMOTE_TRANSFER_ESTIMATE_JSON"])[
        "estimated_outbound_transfer_bytes"
    ] == len(artifact_bytes)
    assert json.loads(plan["environment"]["MISSION_CONTROL_REMOTE_RESULT_COLLECTION_JSON"])[
        "declared_item_count"
    ] == 3


def test_remote_result_collection_contract_tracks_remote_workspace_artifacts_and_required_items(tmp_path) -> None:
    workspace = tmp_path / "workspace-result-collection"
    workspace.mkdir()
    (workspace / "artifacts" / "screenshots").mkdir(parents=True)
    (workspace / "artifacts" / "screenshots" / "boot.png").write_bytes(b"png")

    contract = build_remote_result_collection_contract(
        workspace_path=workspace.as_posix(),
        artifact_contract={
            "required": False,
            "local_artifact_paths": ["artifacts/screenshots/boot.png"],
            "remote_workspace_root": "/srv/browser-work",
            "remote_workspace_artifact_paths": ["/srv/browser-work/artifacts/screenshots/boot.png"],
        },
        result_contract={
            "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
            "session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
            ],
            "remote_session_recording_artifact_paths": [
                "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
            ],
        },
        broker_contract={"require_session_recording": True},
        adapter_contracts=[
            {
                "contract_id": "browser_automation",
                "supports_brokered_result_collection": True,
                "artifact_shipping_modes": [
                    "workspace_relative_sync",
                    "brokered_sync",
                ],
            }
        ],
    )

    assert contract["declared_item_count"] == 3
    assert contract["required_item_count"] == 2
    assert contract["remote_collectible_item_count"] == 2
    assert contract["present_at_dispatch_count"] == 1
    assert contract["missing_at_dispatch_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/browser-box.cast",
        "artifacts/remote-execution-governance/normalized-execution-summary.json",
    ]
    assert contract["items"][0]["collection_stage"] == "remote_workspace_artifact"
    assert contract["items"][0]["source_kind"] == "workspace_artifact"
    assert contract["items"][0]["collection_transport"] == "brokered_sync"
    assert contract["items"][0]["remote_path_strategy"] == "workspace_relative_sync"
    assert contract["items"][0]["path_sandbox_source"] == "remote_workspace_root"
    assert contract["items"][0]["present_at_dispatch"] is True
    assert contract["items"][1]["required"] is True
    assert contract["items"][2]["collection_mode"] == "local_generated_artifact"
    assert contract["contract_status"] == "ready"
    assert contract["selected_adapter_contract_ids"] == ["browser_automation"]
    assert contract["common_adapter_shipping_modes"] == ["workspace_relative_sync", "brokered_sync"]
    assert contract["brokered_result_collection_supported"] is True


def test_remote_transfer_bundle_declares_remote_workspace_artifacts_for_post_run_collection(tmp_path) -> None:
    workspace = tmp_path / "workspace-transfer-bundle"
    workspace.mkdir()
    (workspace / "artifacts" / "screenshots").mkdir(parents=True)
    (workspace / "artifacts" / "screenshots" / "boot.png").write_bytes(b"png")

    bundle = build_remote_transfer_bundle(
        workspace_path=workspace.as_posix(),
        artifact_contract={
            "local_artifact_paths": ["artifacts/screenshots/boot.png"],
            "remote_workspace_root": "/srv/browser-work",
            "remote_workspace_artifact_paths": ["/srv/browser-work/artifacts/screenshots/boot.png"],
        },
        result_contract={
            "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
            "session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
            ],
            "remote_session_recording_artifact_paths": [
                "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
            ],
        },
        broker_contract={"require_session_recording": True},
        adapter_contracts=[
            {
                "contract_id": "browser_automation",
                "supports_brokered_result_collection": True,
                "artifact_shipping_modes": [
                    "workspace_relative_sync",
                    "brokered_sync",
                ],
            }
        ],
    )

    assert bundle["declared_result_collection_count"] == 3
    assert bundle["result_collection_contract"]["remote_collectible_item_count"] == 2
    assert bundle["result_collection_contract_status"] == "ready"
    assert bundle["selected_adapter_shipping_modes"] == ["workspace_relative_sync", "brokered_sync"]
    assert bundle["brokered_result_collection_supported"] is True
    assert bundle["declared_result_collection"][0]["collection_stage"] == "remote_workspace_artifact"
    assert bundle["declared_result_collection"][0]["collection_transport"] == "brokered_sync"
    assert bundle["declared_result_collection"][0]["remote_path"] == "/srv/browser-work/artifacts/screenshots/boot.png"
    assert bundle["declared_result_collection"][1]["collection_stage"] == "remote_session_recording"
    assert bundle["declared_result_collection"][2]["collection_stage"] == "normalized_summary"
    assert bundle["staged_outbound_artifacts"][0]["transfer_direction"] == "push_to_remote"
    assert bundle["staged_outbound_artifacts"][0]["remote_path_strategy"] == "workspace_relative_sync"


def test_remote_transfer_bundle_blocks_when_selected_adapter_cannot_broker_result_collection(tmp_path) -> None:
    workspace = tmp_path / "workspace-transfer-bundle-blocked"
    workspace.mkdir()
    (workspace / "artifacts" / "screenshots").mkdir(parents=True)
    (workspace / "artifacts" / "screenshots" / "boot.png").write_bytes(b"png")

    bundle = build_remote_transfer_bundle(
        workspace_path=workspace.as_posix(),
        artifact_contract={
            "local_artifact_paths": ["artifacts/screenshots/boot.png"],
            "remote_workspace_root": "/srv/browser-work",
            "remote_workspace_artifact_paths": ["/srv/browser-work/artifacts/screenshots/boot.png"],
        },
        result_contract={
            "session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
            ],
            "remote_session_recording_artifact_paths": [
                "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
            ],
        },
        broker_contract={"require_session_recording": True},
        adapter_contracts=[
            {
                "contract_id": "local_only_browser",
                "supports_brokered_result_collection": False,
                "artifact_shipping_modes": ["local_only"],
            }
        ],
    )

    assert bundle["preflight_ready"] is False
    assert bundle["result_collection_contract_status"] == "blocked"
    assert bundle["brokered_result_collection_supported"] is False
    assert "selected_adapter_contract_missing_brokered_result_collection_support" in bundle["blocking_reasons"]
    assert "selected_adapter_contract_missing_brokered_sync_mode" in bundle["blocking_reasons"]


def test_build_remote_launch_plan_blocks_when_known_outbound_transfer_exceeds_target_quota(tmp_path) -> None:
    workspace = tmp_path / "workspace-over-quota"
    workspace.mkdir()
    artifact_path = workspace / "artifacts" / "huge.bin"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"x" * ((1024 * 1024) + 16))

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
            "target_path_prefixes": ["artifacts"],
            "target_command_families": ["python"],
            "target_toolchains": ["python3.11"],
            "target_file_transfer_quota_mb": 1,
            "require_session_recording": False,
            "session_recording_enabled": False,
        },
        artifact_contract={
            "sync_enabled": True,
            "blocking_reasons": [],
            "local_artifact_paths": ["artifacts/huge.bin"],
            "remote_workspace_artifact_paths": ["/srv/shadow/artifacts/huge.bin"],
        },
        workspace_path=workspace.as_posix(),
        allowed_paths=["artifacts/huge.bin"],
    )

    assert plan["preflight_ready"] is False
    assert plan["estimated_outbound_transfer_bytes"] > 1024 * 1024
    assert plan["estimated_transfer_within_quota"] is False
    assert "remote_estimated_outbound_transfer_quota_exceeded" in plan["blocking_reasons"]


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


def test_runner_registry_selects_remote_adapter_for_windows_agent_family(monkeypatch) -> None:
    registry = RunnerRegistry()

    async def fake_handshake(settings=None) -> bool:
        remote_execution = dict(getattr(settings, "remote_execution", None) or {})
        target = dict(remote_execution.get("selected_target") or {})
        policy = dict(remote_execution.get("policy") or {})
        return (
            bool(target.get("id") == "win-agent")
            and str(policy.get("required_runner_family") or "") == "windows_agent_runner"
        )

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
                "required_runner_family": "windows_agent_runner",
                "fallback_to_local": False,
            },
            "selection": {
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "selected_target": {
                "id": "win-agent",
                "transport": "tailscale_ssh",
                "host": "win-agent.tailnet.ts.net",
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


def test_remote_launch_plan_exports_quota_contract_into_environment() -> None:
    launch_plan = build_remote_launch_plan(
        selected_target={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "command_families": ["python", "git"],
            "toolchains": ["python3.11", "cuda12"],
            "result_formats": ["json"],
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts"],
            "max_command_runtime_seconds": 1200,
            "file_transfer_quota_mb": 1024,
            "last_probe_status": "ready",
        },
        policy_payload={
            "enabled": True,
            "required_runner_family": "external_adapter",
            "required_result_formats": ["json"],
            "required_command_families": ["git"],
            "required_toolchains": ["cuda12"],
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "minimum_command_runtime_seconds": 900,
            "minimum_file_transfer_quota_mb": 512,
        },
        adapter_command="python3",
        adapter_args=["/opt/mission-control/adapter.py"],
        workspace_path="C:/workspace",
        allowed_paths=["artifacts/model.onnx"],
    )

    assert launch_plan["minimum_command_runtime_seconds"] == 900
    assert launch_plan["minimum_file_transfer_quota_mb"] == 512
    assert launch_plan["target_command_runtime_seconds"] == 1200
    assert launch_plan["target_file_transfer_quota_mb"] == 1024
    assert launch_plan["environment"]["MISSION_CONTROL_REMOTE_MIN_COMMAND_RUNTIME_SECONDS"] == "900"
    assert launch_plan["environment"]["MISSION_CONTROL_REMOTE_MIN_FILE_TRANSFER_QUOTA_MB"] == "512"
    assert launch_plan["environment"]["MISSION_CONTROL_REMOTE_TARGET_COMMAND_RUNTIME_SECONDS"] == "1200"
    assert launch_plan["environment"]["MISSION_CONTROL_REMOTE_TARGET_FILE_TRANSFER_QUOTA_MB"] == "1024"
    assert json.loads(launch_plan["environment"]["MISSION_CONTROL_REMOTE_QUOTA_CONTRACT_JSON"]) == {
        "minimum_command_runtime_seconds": 900,
        "minimum_file_transfer_quota_mb": 512,
        "target_command_runtime_seconds": 1200,
        "target_file_transfer_quota_mb": 1024,
    }
    assert any("Quota policy is exported into the remote launch environment" in note for note in launch_plan["notes"])


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


def test_remote_result_contract_merges_selected_adapter_contract_expectations() -> None:
    contract = build_remote_result_contract(
        selected_target={
            "id": "android-lab",
            "result_formats": ["json", "junit_xml"],
            "command_families": ["adb", "gradle", "browser"],
            "toolchains": ["python3.11"],
            "workspace_root": "/srv/android-work",
        },
        policy_payload={
            "enabled": True,
            "required_result_formats": ["json"],
            "required_command_families": ["adb"],
            "required_toolchains": ["python3.11"],
        },
        workspace_tooling_payload={
            "validation_evidence_targets": ["artifacts/logs/run.log"],
            "artifact_paths": ["artifacts/traces/app.trace.zip"],
            "execution_entrypoints": ["./gradlew connectedCheck"],
        },
        adapter_contracts=[
            {
                "contract_id": "android_adb_contract",
                "required_command_families": ["adb", "browser"],
                "required_tool_families": ["adb", "gradle", "emulator"],
                "expected_result_formats": ["junit_xml"],
                "expected_evidence_categories": ["logs", "screenshots", "traces", "coverage", "performance"],
            }
        ],
    )

    assert contract["adapter_contract_ids"] == ["android_adb_contract"]
    assert contract["effective_required_result_formats"] == ["json", "junit_xml"]
    assert contract["effective_required_command_families"] == ["adb", "browser"]
    assert contract["adapter_required_tool_families"] == ["adb", "gradle", "emulator"]
    assert contract["expected_evidence_categories"] == [
        "logs",
        "coverage",
        "screenshots",
        "traces",
        "performance",
    ]


def test_remote_launch_plan_exports_adapter_contract_metadata_to_environment() -> None:
    launch_plan = build_remote_launch_plan(
        selected_target={
            "id": "android-lab",
            "label": "Android Lab",
            "transport": "tailscale_ssh",
            "host": "android-lab.tailnet.ts.net",
            "os_family": "linux",
            "shell_family": "posix",
            "workspace_root": "/srv/android-work",
            "ssh_user": "runner",
        },
        policy_payload={"enabled": True, "required_runner_family": "external_adapter"},
        adapter_command="python3",
        adapter_args=["/opt/mission-control/adapter.py"],
        broker_contract={
            "preflight_ready": True,
            "target_repo_roots": ["/srv/android-work"],
            "target_path_prefixes": ["artifacts"],
            "target_command_families": ["adb", "browser"],
            "target_result_formats": ["json", "junit_xml"],
            "target_toolchains": ["python3.11"],
        },
        result_contract={
            "preflight_ready": True,
            "expected_evidence_categories": ["logs", "screenshots", "traces"],
            "adapter_contract_ids": ["android_adb_contract"],
            "adapter_required_tool_families": ["adb", "gradle", "emulator"],
            "adapter_expected_result_formats": ["junit_xml"],
        },
        workspace_path="C:/workspace",
        allowed_paths=["artifacts"],
    )

    assert json.loads(launch_plan["environment"]["MISSION_CONTROL_REMOTE_ADAPTER_CONTRACT_IDS_JSON"]) == [
        "android_adb_contract"
    ]
    assert json.loads(
        launch_plan["environment"]["MISSION_CONTROL_REMOTE_ADAPTER_REQUIRED_TOOL_FAMILIES_JSON"]
    ) == ["adb", "gradle", "emulator"]
    assert json.loads(
        launch_plan["environment"]["MISSION_CONTROL_REMOTE_ADAPTER_EXPECTED_RESULT_FORMATS_JSON"]
    ) == ["junit_xml"]
    assert any("Adapter contract metadata exposes 1 contract binding" in note for note in launch_plan["notes"])
