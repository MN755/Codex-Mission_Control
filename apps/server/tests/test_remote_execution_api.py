from __future__ import annotations

import asyncio
import hashlib
import json

def test_remote_execution_registry_and_project_policy_endpoints(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Demo",
            "idea": "Need a remote worker fabric.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "fast-box",
            "label": "Fast Box",
            "transport": "ssh",
            "host": "fast-box.local",
            "ssh_user": "mike",
            "ssh_port": 22,
            "os_family": "linux",
            "shell_family": "posix",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "tags": ["gpu"],
            "capabilities": ["python", "gpu"],
            "runner_families": ["external_adapter"],
            "trust_level": "trusted",
            "enabled": True,
            "allow_write": True,
            "gpu": "rtx-4090",
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json", "junit_xml"],
            "session_recording_enabled": True,
            "max_command_runtime_seconds": 1200,
            "file_transfer_quota_mb": 1024,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["src", "artifacts"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text
    assert upsert.json()["id"] == "fast-box"

    registry = client.get("/api/system/remote-execution")
    assert registry.status_code == 200, registry.text
    assert registry.json()["summary"]["target_count"] == 1

    capability_index = client.get("/api/system/remote-execution/capability-index")
    assert capability_index.status_code == 200, capability_index.text
    capability_payload = capability_index.json()
    assert capability_payload["target_count"] == 1
    assert capability_payload["toolchain_counts"]["cuda12"] == 1
    assert capability_payload["command_family_counts"]["git"] == 1

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "fast-box",
            "required_runner_family": "external_adapter",
            "required_tags": ["gpu"],
            "required_capabilities": ["python"],
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "minimum_command_runtime_seconds": 600,
            "minimum_file_transfer_quota_mb": 512,
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text
    assert policy_update.json()["enabled"] is True

    selection = client.get(f"/api/projects/{project_id}/remote-execution/resolve")
    assert selection.status_code == 200, selection.text
    payload = selection.json()
    assert payload["preflight_ready"] is True, payload
    assert payload["selected_target_id"] == "fast-box"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["ready_candidate_count"] == 1
    assert payload["ready_candidate_ids"] == ["fast-box"]
    assert payload["artifact_contract"]["local_artifact_paths"] == ["artifacts/model.onnx"]
    assert payload["artifact_contract"]["selected_artifact_root"] == "/srv/shadow/artifacts"
    assert payload["connector_contract"]["available_families"] == ["source_control"]
    assert payload["broker_contract"]["target_gpu"] == "rtx-4090"
    assert payload["broker_contract"]["target_toolchains"] == ["python3.11", "cuda12"]
    assert payload["broker_contract"]["preflight_ready"] is True

    launch_plan = client.get(f"/api/projects/{project_id}/remote-execution/launch-plan")
    assert launch_plan.status_code == 200, launch_plan.text
    launch_payload = launch_plan.json()
    expected_artifact_size = (workspace / "artifacts" / "model.onnx").stat().st_size
    assert launch_payload["preflight_ready"] is True, launch_payload
    assert launch_payload["target_id"] == "fast-box"
    assert launch_payload["selected_target_probe_status"] == "ready"
    assert launch_payload["required_runner_family"] == "external_adapter"
    assert launch_payload["remote_workspace_root"] == "/srv/shadow"
    assert launch_payload["artifact_sync_enabled"] is True
    assert launch_payload["remote_artifact_paths"] == ["/srv/shadow/artifacts/model.onnx"]
    assert launch_payload["required_result_formats"] == ["json"]
    assert launch_payload["target_result_formats"] == ["json", "junit_xml"]
    assert launch_payload["minimum_command_runtime_seconds"] == 600
    assert launch_payload["minimum_file_transfer_quota_mb"] == 512
    assert launch_payload["target_command_runtime_seconds"] == 1200
    assert launch_payload["target_file_transfer_quota_mb"] == 1024
    assert launch_payload["estimated_outbound_transfer_bytes"] == expected_artifact_size
    assert launch_payload["estimated_outbound_transfer_path_count"] == 1
    assert launch_payload["estimated_transfer_within_quota"] is True
    assert launch_payload["declared_result_artifact_count"] == 2
    assert launch_payload["session_recording_required"] is True
    assert launch_payload["session_recording_enabled"] is True
    assert launch_payload["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/fast-box.cast"
    ]
    assert launch_payload["remote_session_recording_artifact_paths"] == [
        "/srv/shadow/artifacts/remote-execution-governance/session-recordings/fast-box.cast"
    ]
    assert launch_payload["environment"]["MISSION_CONTROL_REMOTE_TARGET_ID"] == "fast-box"
    assert launch_payload["environment"]["MISSION_CONTROL_REMOTE_REQUIRED_RESULT_FORMATS_JSON"] == json.dumps(["json"])
    assert launch_payload["environment"]["MISSION_CONTROL_REMOTE_MIN_COMMAND_RUNTIME_SECONDS"] == "600"
    assert launch_payload["environment"]["MISSION_CONTROL_REMOTE_MIN_FILE_TRANSFER_QUOTA_MB"] == "512"
    assert launch_payload["environment"]["MISSION_CONTROL_REMOTE_TARGET_COMMAND_RUNTIME_SECONDS"] == "1200"
    assert launch_payload["environment"]["MISSION_CONTROL_REMOTE_TARGET_FILE_TRANSFER_QUOTA_MB"] == "1024"
    assert launch_payload["environment"]["MISSION_CONTROL_REMOTE_ESTIMATED_OUTBOUND_TRANSFER_BYTES"] == str(
        expected_artifact_size
    )
    assert json.loads(launch_payload["environment"]["MISSION_CONTROL_REMOTE_QUOTA_CONTRACT_JSON"]) == {
        "minimum_command_runtime_seconds": 600,
        "minimum_file_transfer_quota_mb": 512,
        "target_command_runtime_seconds": 1200,
        "target_file_transfer_quota_mb": 1024,
    }
    assert json.loads(launch_payload["environment"]["MISSION_CONTROL_REMOTE_TRANSFER_ESTIMATE_JSON"])[
        "estimated_outbound_transfer_bytes"
    ] == expected_artifact_size
    assert (
        launch_payload["environment"]["MISSION_CONTROL_REMOTE_NORMALIZED_SUMMARY_ARTIFACT"]
        == "artifacts/remote-execution-governance/normalized-execution-summary.json"
    )
    assert launch_payload["allowed_relative_paths"] == ["artifacts"]
    assert launch_payload["allowed_remote_paths"] == ["/srv/shadow/artifacts"]

    deleted = client.delete("/api/system/remote-execution/hosts/fast-box")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["ok"] is True


def test_remote_execution_policy_update_allows_clearing_preferred_target(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    workspace = tmp_path / "workspace-clear-policy"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Policy Clear",
            "idea": "Need to clear stale preferred target IDs.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    first_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "fast-box",
            "fallback_to_local": True,
        },
    )
    assert first_update.status_code == 200, first_update.text
    assert first_update.json()["preferred_target_id"] == "fast-box"

    clear_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "preferred_target_id": None,
        },
    )
    assert clear_update.status_code == 200, clear_update.text
    assert clear_update.json()["preferred_target_id"] is None


def test_remote_execution_launch_plan_blocks_missing_result_contract_coverage(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-launch-plan-result-gap"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Launch Result Gap",
            "idea": "Need launch planning to reject targets that cannot satisfy normalized result contracts.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution_launch_plan",
        lambda db, project: {
            "preflight_ready": False,
            "target_id": "text-only-box",
            "target_label": "Text Only Box",
            "selected_target_probe_status": "ready",
            "required_runner_family": "external_adapter",
            "transport": "ssh",
            "host": "text-only-box.local",
            "remote_workspace_root": "/srv/shadow",
            "remote_cwd": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["adapter.py"],
            "allowed_relative_paths": ["src"],
            "allowed_remote_paths": ["/srv/shadow/src"],
            "forbidden_relative_paths": [],
            "forbidden_remote_paths": [],
            "allowed_repo_roots": ["/srv/shadow"],
            "artifact_sync_enabled": False,
            "remote_artifact_paths": [],
            "connector_families": [],
            "required_result_formats": ["json"],
            "target_result_formats": ["text"],
            "required_command_families": ["python"],
            "target_command_families": ["python"],
            "required_toolchains": ["python3.11"],
            "target_toolchains": ["python3.11"],
            "expected_evidence_categories": ["logs", "coverage"],
            "observed_evidence_categories": [],
            "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
            "session_recording_required": False,
            "session_recording_enabled": False,
            "session_recording_artifact_paths": [],
            "remote_session_recording_artifact_paths": [],
            "primary_session_recording_artifact_path": None,
            "primary_remote_session_recording_artifact_path": None,
            "environment": {
                "MISSION_CONTROL_REMOTE_REQUIRED_RESULT_FORMATS_JSON": json.dumps(["json"]),
                "MISSION_CONTROL_REMOTE_NORMALIZED_SUMMARY_ARTIFACT": "artifacts/remote-execution-governance/normalized-execution-summary.json",
            },
            "exec_args": ["ssh", "text-only-box.local", "python3 adapter.py"],
            "command_preview": "ssh text-only-box.local python3 adapter.py",
            "blocking_reasons": ["remote_result_formats_missing"],
            "notes": ["Result contract is missing required json output coverage."],
        },
    )

    launch_plan = client.get(f"/api/projects/{project_id}/remote-execution/launch-plan")
    assert launch_plan.status_code == 200, launch_plan.text
    payload = launch_plan.json()
    assert payload["preflight_ready"] is False
    assert payload["target_id"] == "text-only-box"
    assert payload["required_result_formats"] == ["json"]
    assert payload["target_result_formats"] == ["text"]
    assert "remote_result_formats_missing" in payload["blocking_reasons"]


def test_remote_execution_launch_package_plan_writes_request_command_and_approval_manifests(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.security_service.evaluate_action",
        lambda db, payload, project=None: {
            "policy": {},
            "assessment": {"risk_level": "high"},
            "decision": "pending",
            "reason": "High-risk remote launches require explicit approval.",
        },
    )
    workspace = tmp_path / "workspace-launch-package-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Launch Package Demo",
            "idea": "Need a governed launch package before remote adapter execution.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "max_command_runtime_seconds": 1200,
            "file_transfer_quota_mb": 1024,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["src", "artifacts"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "minimum_command_runtime_seconds": 900,
            "minimum_file_transfer_quota_mb": 512,
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    plan = client.post(
        f"/api/projects/{project_id}/remote-execution/launch-plan",
        json={
            "allowed_paths": ["artifacts/model.onnx"],
            "forbidden_paths": ["secrets"],
            "dry_run": False,
            "write_intent": True,
        },
    )
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] == "partial"
    assert payload["approval_required"] is True
    assert isinstance(payload["approval_id"], int)
    assert payload["approval_status"] == "pending"
    assert payload["dry_run"] is False
    assert payload["write_intent"] is True
    assert payload["target_id"] == "gpu-box"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["availability_diagnostics"]["candidate_count"] == 1
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["required_runner_family"] == "external_adapter"
    assert payload["runner_command"] == "python3"
    assert payload["runner_args"] == ["/opt/mission-control/adapter.py"]
    assert payload["allowed_relative_paths"] == ["artifacts/model.onnx"]
    assert payload["forbidden_relative_paths"] == ["secrets"]
    assert payload["required_result_formats"] == ["json"]
    assert payload["target_result_formats"] == ["json"]
    assert payload["adapter_contract_status"] == "ready"
    assert payload["selected_adapter_contract_ids"] == ["linux_host_runtime"]
    assert payload["required_tool_adapter_families"] == ["desktop_installer", "shell"]
    assert payload["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert payload["minimum_command_runtime_seconds"] == 900
    assert payload["minimum_file_transfer_quota_mb"] == 512
    assert payload["target_command_runtime_seconds"] == 1200
    assert payload["target_file_transfer_quota_mb"] == 1024
    assert payload["estimated_outbound_transfer_bytes"] == (workspace / "artifacts" / "model.onnx").stat().st_size
    assert payload["estimated_transfer_within_quota"] is True
    assert payload["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-box.cast"
    ]
    assert payload["remote_session_recording_artifact_paths"] == [
        "/srv/shadow/artifacts/remote-execution-governance/session-recordings/gpu-box.cast"
    ]
    assert payload["manifest_root"] == "artifacts/remote-execution-launch"
    assert payload["launch_request_path"] == "artifacts/remote-execution-launch/launch-request.json"
    assert payload["launch_command_path"] == "artifacts/remote-execution-launch/launch-command.json"
    assert payload["launch_environment_path"] == "artifacts/remote-execution-launch/launch-environment.json"
    assert payload["approval_checkpoint_path"] == "artifacts/remote-execution-launch/approval-checkpoints.json"

    launch_request = json.loads(
        (workspace / "artifacts" / "remote-execution-launch" / "launch-request.json").read_text(encoding="utf-8")
    )
    assert launch_request["runner_command"] == "python3"
    assert launch_request["runner_args"] == ["/opt/mission-control/adapter.py"]
    assert launch_request["approval_required"] is True
    assert launch_request["approval_id"] == payload["approval_id"]
    assert launch_request["approval_status"] == "pending"
    assert launch_request["allowed_relative_paths"] == ["artifacts/model.onnx"]
    assert launch_request["forbidden_relative_paths"] == ["secrets"]
    assert launch_request["availability_diagnostics"]["candidate_count"] == 1
    assert launch_request["selected_target_requirement_gaps"] == {}
    assert launch_request["minimum_command_runtime_seconds"] == 900
    assert launch_request["minimum_file_transfer_quota_mb"] == 512
    assert launch_request["target_command_runtime_seconds"] == 1200
    assert launch_request["target_file_transfer_quota_mb"] == 1024
    assert launch_request["selected_adapter_contract_ids"] == ["linux_host_runtime"]
    assert launch_request["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert launch_request["estimated_outbound_transfer_bytes"] == (workspace / "artifacts" / "model.onnx").stat().st_size
    assert launch_request["estimated_transfer_within_quota"] is True

    launch_command = json.loads(
        (workspace / "artifacts" / "remote-execution-launch" / "launch-command.json").read_text(encoding="utf-8")
    )
    assert launch_command["required_result_formats"] == ["json"]
    assert launch_command["target_result_formats"] == ["json"]
    assert launch_command["availability_diagnostics"]["candidate_count"] == 1
    assert launch_command["minimum_command_runtime_seconds"] == 900
    assert launch_command["minimum_file_transfer_quota_mb"] == 512
    assert launch_command["target_command_runtime_seconds"] == 1200
    assert launch_command["target_file_transfer_quota_mb"] == 1024
    assert launch_command["required_tool_adapter_families"] == ["desktop_installer", "shell"]
    assert launch_command["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert launch_command["estimated_outbound_transfer_bytes"] == (workspace / "artifacts" / "model.onnx").stat().st_size
    assert launch_command["estimated_transfer_within_quota"] is True
    assert launch_command["normalized_summary_artifact"] == (
        "artifacts/remote-execution-governance/normalized-execution-summary.json"
    )

    launch_environment = json.loads(
        (workspace / "artifacts" / "remote-execution-launch" / "launch-environment.json").read_text(
            encoding="utf-8"
        )
    )
    assert launch_environment["session_recording_required"] is True
    assert launch_environment["minimum_command_runtime_seconds"] == 900
    assert launch_environment["minimum_file_transfer_quota_mb"] == 512
    assert launch_environment["target_command_runtime_seconds"] == 1200
    assert launch_environment["target_file_transfer_quota_mb"] == 1024
    assert launch_environment["estimated_outbound_transfer_bytes"] == (workspace / "artifacts" / "model.onnx").stat().st_size
    assert launch_environment["estimated_transfer_within_quota"] is True
    assert launch_environment["environment"]["MISSION_CONTROL_REMOTE_TARGET_ID"] == "gpu-box"
    assert launch_environment["environment"]["MISSION_CONTROL_REMOTE_MIN_COMMAND_RUNTIME_SECONDS"] == "900"
    assert launch_environment["environment"]["MISSION_CONTROL_REMOTE_MIN_FILE_TRANSFER_QUOTA_MB"] == "512"
    assert launch_environment["environment"]["MISSION_CONTROL_REMOTE_TARGET_COMMAND_RUNTIME_SECONDS"] == "1200"
    assert launch_environment["environment"]["MISSION_CONTROL_REMOTE_TARGET_FILE_TRANSFER_QUOTA_MB"] == "1024"
    assert launch_environment["environment"]["MISSION_CONTROL_REMOTE_EXPECTED_EVIDENCE_CATEGORIES_JSON"] == json.dumps(
        ["logs", "coverage", "screenshots", "crashes", "performance"]
    )

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "remote-execution-launch" / "approval-checkpoints.json").read_text(
            encoding="utf-8"
        )
    )
    checkpoint_statuses = {item["checkpoint_id"]: item["status"] for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_statuses["broker_policy_review"] == "ready"
    assert checkpoint_statuses["path_scope_review"] == "ready"
    assert checkpoint_statuses["adapter_contract_review"] == "ready"
    assert checkpoint_statuses["result_contract_review"] == "ready"
    assert checkpoint_statuses["execution_approval_gate"] == "partial"

    pending_approvals = client.get(f"/api/projects/{project_id}/approvals/pending")
    assert pending_approvals.status_code == 200, pending_approvals.text
    pending_payload = pending_approvals.json()
    matching = [item for item in pending_payload if item["id"] == payload["approval_id"]]
    assert len(matching) == 1
    assert matching[0]["runner_ref"] == f"remote_execution_launch:{project_id}"
    assert matching[0]["request_payload_json"]["launch_request_path"] == (
        "artifacts/remote-execution-launch/launch-request.json"
    )
    assert matching[0]["request_payload_json"]["required_runner_family"] == "external_adapter"
    assert matching[0]["request_payload_json"]["runner_command"] == "python3"
    assert matching[0]["request_payload_json"]["runner_args"] == ["/opt/mission-control/adapter.py"]
    assert matching[0]["request_payload_json"]["minimum_command_runtime_seconds"] == 900
    assert matching[0]["request_payload_json"]["minimum_file_transfer_quota_mb"] == 512
    assert matching[0]["request_payload_json"]["target_command_runtime_seconds"] == 1200
    assert matching[0]["request_payload_json"]["target_file_transfer_quota_mb"] == 1024
    assert matching[0]["request_payload_json"]["estimated_outbound_transfer_bytes"] == (
        workspace / "artifacts" / "model.onnx"
    ).stat().st_size


def test_remote_execution_execution_request_reports_approval_required_until_launch_gate_is_approved(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.security_service.evaluate_action",
        lambda db, payload, project=None: {
            "policy": {},
            "assessment": {"risk_level": "high"},
            "decision": "pending",
            "reason": "High-risk remote launches require explicit approval.",
        },
    )
    workspace = tmp_path / "workspace-execution-request-pending"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Request Pending Demo",
            "idea": "Need execution requests to stay blocked until the launch approval clears.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "max_command_runtime_seconds": 1200,
            "file_transfer_quota_mb": 1024,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["src", "artifacts"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "minimum_command_runtime_seconds": 900,
            "minimum_file_transfer_quota_mb": 512,
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    launch_plan = client.post(
        f"/api/projects/{project_id}/remote-execution/launch-plan",
        json={
            "allowed_paths": ["artifacts/model.onnx"],
            "dry_run": False,
            "write_intent": True,
        },
    )
    assert launch_plan.status_code == 200, launch_plan.text
    launch_payload = launch_plan.json()
    approval_id = launch_payload["approval_id"]
    assert launch_payload["approval_status"] == "pending"

    execution_request = client.post(
        f"/api/projects/{project_id}/remote-execution/execute-request",
        json={"approval_id": approval_id, "expected_target_id": "gpu-box"},
    )
    assert execution_request.status_code == 200, execution_request.text
    payload = execution_request.json()
    assert payload["request_status"] == "approval_required"
    assert payload["approval_required"] is True
    assert payload["approval_id"] == approval_id
    assert payload["approval_status"] == "pending"
    assert payload["target_id"] == "gpu-box"
    assert payload["runner_command"] == "python3"
    assert payload["adapter_contract_status"] == "ready"
    assert payload["selected_adapter_contract_ids"] == ["linux_host_runtime"]
    assert payload["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert payload["minimum_command_runtime_seconds"] == 900
    assert payload["minimum_file_transfer_quota_mb"] == 512
    assert payload["target_command_runtime_seconds"] == 1200
    assert payload["target_file_transfer_quota_mb"] == 1024
    assert payload["staged_outbound_transfer_bytes"] == (workspace / "artifacts" / "model.onnx").stat().st_size
    assert payload["staged_outbound_transfer_path_count"] == 1
    assert payload["transfer_quota_status"] == "ready"
    assert payload["result_collection_contract_status"] == "ready"
    assert payload["remote_collectible_result_path_count"] == 2
    assert payload["transport_mode"] == "remote_artifact_root"
    assert payload["selected_adapter_shipping_modes"] == [
        "workspace_relative_sync",
        "remote_artifact_root",
        "brokered_sync",
    ]
    assert payload["common_adapter_shipping_modes"] == [
        "workspace_relative_sync",
        "remote_artifact_root",
        "brokered_sync",
    ]
    assert payload["transport_mode_adapter_status"] == "ready"
    assert payload["transport_mode_supported_adapter_contract_ids"] == ["linux_host_runtime"]
    assert payload["transport_mode_unsupported_adapter_contract_ids"] == []
    assert payload["transport_mode_undeclared_adapter_contract_ids"] == []
    assert payload["brokered_result_collection_supported"] is True
    assert "launch_package_approval_pending" in payload["blocking_reasons"]
    assert payload["execution_request_path"].startswith("artifacts/remote-execution-requests/")
    assert payload["transfer_bundle_path"].startswith("artifacts/remote-execution-requests/")

    execution_manifest = json.loads((workspace / payload["execution_request_path"]).read_text(encoding="utf-8"))
    assert execution_manifest["request_status"] == "approval_required"
    assert execution_manifest["approval_id"] == approval_id
    assert execution_manifest["runner_command"] == "python3"
    assert execution_manifest["selected_adapter_contract_ids"] == ["linux_host_runtime"]
    assert execution_manifest["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert execution_manifest["minimum_command_runtime_seconds"] == 900
    assert execution_manifest["minimum_file_transfer_quota_mb"] == 512
    assert execution_manifest["target_command_runtime_seconds"] == 1200
    assert execution_manifest["target_file_transfer_quota_mb"] == 1024
    assert execution_manifest["staged_outbound_transfer_bytes"] == (
        workspace / "artifacts" / "model.onnx"
    ).stat().st_size
    assert execution_manifest["transfer_quota_status"] == "ready"

    approval_binding = json.loads((workspace / payload["approval_binding_path"]).read_text(encoding="utf-8"))
    assert approval_binding["approval_status"] == "pending"
    assert approval_binding["resolved_for_execution"] is False
    transfer_bundle = json.loads((workspace / payload["transfer_bundle_path"]).read_text(encoding="utf-8"))
    assert transfer_bundle["request_status"] == "approval_required"
    assert transfer_bundle["staged_outbound_transfer_bytes"] == (
        workspace / "artifacts" / "model.onnx"
    ).stat().st_size
    assert transfer_bundle["transfer_quota_status"] == "ready"
    assert transfer_bundle["result_collection_contract_status"] == "ready"
    assert transfer_bundle["remote_collectible_result_path_count"] == 2
    assert transfer_bundle["declared_result_collection"][0]["collection_transport"] == "brokered_sync"
    assert transfer_bundle["staged_outbound_artifacts"][0]["transfer_direction"] == "push_to_remote"


def test_remote_execution_execution_request_binds_approved_launch_package_and_result_bundle(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.security_service.evaluate_action",
        lambda db, payload, project=None: {
            "policy": {},
            "assessment": {"risk_level": "high"},
            "decision": "pending",
            "reason": "High-risk remote launches require explicit approval.",
        },
    )
    workspace = tmp_path / "workspace-execution-request-ready"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Request Ready Demo",
            "idea": "Need approved launch packages to produce dispatch-ready execution requests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "max_command_runtime_seconds": 1200,
            "file_transfer_quota_mb": 1024,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["src", "artifacts"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "minimum_command_runtime_seconds": 900,
            "minimum_file_transfer_quota_mb": 512,
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    launch_plan = client.post(
        f"/api/projects/{project_id}/remote-execution/launch-plan",
        json={
            "allowed_paths": ["artifacts/model.onnx"],
            "dry_run": False,
            "write_intent": True,
        },
    )
    assert launch_plan.status_code == 200, launch_plan.text
    launch_payload = launch_plan.json()
    approval_id = launch_payload["approval_id"]
    assert launch_payload["approval_status"] == "pending"

    approval = client.post(
        f"/api/projects/{project_id}/approvals/{approval_id}/approve-once",
        json={"project_id": project_id},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["status"] == "approved_once"

    execution_request = client.post(
        f"/api/projects/{project_id}/remote-execution/execute-request",
        json={"approval_id": approval_id, "expected_target_id": "gpu-box"},
    )
    assert execution_request.status_code == 200, execution_request.text
    payload = execution_request.json()
    assert payload["request_status"] == "ready"
    assert payload["approval_required"] is True
    assert payload["approval_id"] == approval_id
    assert payload["approval_status"] == "approved_once"
    assert payload["target_id"] == "gpu-box"
    assert payload["availability_diagnostics"]["candidate_count"] == 1
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["runner_command"] == "python3"
    assert payload["runner_args"] == ["/opt/mission-control/adapter.py"]
    assert payload["adapter_contract_status"] == "ready"
    assert payload["selected_adapter_contract_ids"] == ["linux_host_runtime"]
    assert payload["required_tool_adapter_families"] == ["desktop_installer", "shell"]
    assert payload["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert payload["minimum_command_runtime_seconds"] == 900
    assert payload["minimum_file_transfer_quota_mb"] == 512
    assert payload["target_command_runtime_seconds"] == 1200
    assert payload["target_file_transfer_quota_mb"] == 1024
    assert payload["staged_outbound_transfer_bytes"] == (workspace / "artifacts" / "model.onnx").stat().st_size
    assert payload["staged_outbound_transfer_path_count"] == 1
    assert payload["transfer_quota_status"] == "ready"
    assert payload["result_collection_contract_status"] == "ready"
    assert payload["remote_collectible_result_path_count"] == 2
    assert payload["selected_adapter_shipping_modes"] == [
        "workspace_relative_sync",
        "remote_artifact_root",
        "brokered_sync",
    ]
    assert payload["common_adapter_shipping_modes"] == [
        "workspace_relative_sync",
        "remote_artifact_root",
        "brokered_sync",
    ]
    assert payload["brokered_result_collection_supported"] is True
    assert payload["normalized_summary_artifact"] == (
        "artifacts/remote-execution-governance/normalized-execution-summary.json"
    )
    assert payload["expected_evidence_categories"] == [
        "logs",
        "coverage",
        "screenshots",
        "crashes",
        "performance",
    ]
    assert payload["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-box.cast"
    ]
    assert payload["remote_session_recording_artifact_paths"] == [
        "/srv/shadow/artifacts/remote-execution-governance/session-recordings/gpu-box.cast"
    ]
    assert payload["blocking_reasons"] == []
    assert payload["transfer_bundle_path"].startswith("artifacts/remote-execution-requests/")

    approval_binding = json.loads((workspace / payload["approval_binding_path"]).read_text(encoding="utf-8"))
    assert approval_binding["approval_status"] == "approved_once"
    assert approval_binding["availability_diagnostics"]["candidate_count"] == 1
    assert approval_binding["resolved_for_execution"] is True

    result_bundle = json.loads((workspace / payload["result_bundle_path"]).read_text(encoding="utf-8"))
    assert result_bundle["normalized_summary_artifact"] == (
        "artifacts/remote-execution-governance/normalized-execution-summary.json"
    )
    assert result_bundle["expected_evidence_categories"] == [
        "logs",
        "coverage",
        "screenshots",
        "crashes",
        "performance",
    ]
    assert result_bundle["availability_diagnostics"]["candidate_count"] == 1
    assert result_bundle["adapter_contract_ids"] == ["linux_host_runtime"]
    assert result_bundle["adapter_required_tool_families"] == ["desktop_installer", "shell"]

    execution_manifest = json.loads((workspace / payload["execution_request_path"]).read_text(encoding="utf-8"))
    assert execution_manifest["adapter_contract_status"] == "ready"
    assert execution_manifest["selected_adapter_contract_ids"] == ["linux_host_runtime"]
    assert execution_manifest["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert execution_manifest["availability_diagnostics"]["candidate_count"] == 1
    assert execution_manifest["selected_target_requirement_gaps"] == {}
    assert execution_manifest["minimum_command_runtime_seconds"] == 900
    assert execution_manifest["minimum_file_transfer_quota_mb"] == 512
    assert execution_manifest["target_command_runtime_seconds"] == 1200
    assert execution_manifest["target_file_transfer_quota_mb"] == 1024
    assert execution_manifest["staged_outbound_transfer_bytes"] == (
        workspace / "artifacts" / "model.onnx"
    ).stat().st_size
    assert execution_manifest["transfer_quota_status"] == "ready"
    assert execution_manifest["transport_mode"] == "remote_artifact_root"
    assert execution_manifest["transport_mode_adapter_status"] == "ready"
    transfer_bundle = json.loads((workspace / payload["transfer_bundle_path"]).read_text(encoding="utf-8"))
    assert transfer_bundle["request_status"] == "ready"
    assert transfer_bundle["staged_outbound_transfer_bytes"] == (
        workspace / "artifacts" / "model.onnx"
    ).stat().st_size
    assert transfer_bundle["staged_outbound_transfer_path_count"] == 1
    assert transfer_bundle["transfer_quota_status"] == "ready"
    assert transfer_bundle["result_collection_contract_status"] == "ready"
    assert transfer_bundle["remote_collectible_result_path_count"] == 2
    assert transfer_bundle["transport_mode"] == "remote_artifact_root"
    assert transfer_bundle["transport_mode_adapter_status"] == "ready"
    assert transfer_bundle["declared_result_collection"][0]["collection_transport"] == "brokered_sync"
    assert transfer_bundle["staged_outbound_artifacts"][0]["transfer_direction"] == "push_to_remote"


def test_remote_execution_execution_request_blocks_when_launch_package_preflight_is_blocked(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    workspace = tmp_path / "workspace-execution-request-launch-preflight-blocked"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Launch Preflight Block Demo",
            "idea": "Need execution requests blocked when the persisted launch package was already preflight-blocked.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    launch_plan = client.post(
        f"/api/projects/{project_id}/remote-execution/launch-plan",
        json={
            "allowed_paths": ["artifacts/model.onnx"],
            "dry_run": True,
            "write_intent": False,
        },
    )
    assert launch_plan.status_code == 200, launch_plan.text
    launch_payload = launch_plan.json()
    assert launch_payload["plan_status"] == "ready"

    launch_request_path = workspace / launch_payload["launch_request_path"]
    launch_request = json.loads(launch_request_path.read_text(encoding="utf-8"))
    launch_request["plan_status"] = "blocked"
    launch_request["blocking_reasons"] = ["task_allowed_paths_outside_remote_policy"]
    launch_request_path.write_text(json.dumps(launch_request, indent=2), encoding="utf-8")

    execution_request = client.post(
        f"/api/projects/{project_id}/remote-execution/execute-request",
        json={"expected_target_id": "gpu-box"},
    )
    assert execution_request.status_code == 200, execution_request.text
    payload = execution_request.json()
    assert payload["request_status"] == "blocked"
    assert payload["launch_plan_status"] == "blocked"
    assert payload["launch_preflight_ready"] is False
    assert payload["launch_blocking_reasons"] == ["task_allowed_paths_outside_remote_policy"]
    assert "launch_package_preflight_blocked" in payload["blocking_reasons"]
    assert "task_allowed_paths_outside_remote_policy" in payload["blocking_reasons"]

    execution_manifest = json.loads((workspace / payload["execution_request_path"]).read_text(encoding="utf-8"))
    assert execution_manifest["launch_plan_status"] == "blocked"
    assert execution_manifest["launch_preflight_ready"] is False
    assert execution_manifest["launch_blocking_reasons"] == ["task_allowed_paths_outside_remote_policy"]
    assert "launch_package_preflight_blocked" in execution_manifest["blocking_reasons"]

    approval_binding = json.loads((workspace / payload["approval_binding_path"]).read_text(encoding="utf-8"))
    assert approval_binding["launch_plan_status"] == "blocked"
    assert approval_binding["launch_preflight_ready"] is False
    assert approval_binding["launch_blocking_reasons"] == ["task_allowed_paths_outside_remote_policy"]

    transfer_bundle = json.loads((workspace / payload["transfer_bundle_path"]).read_text(encoding="utf-8"))
    assert transfer_bundle["launch_plan_status"] == "blocked"
    assert transfer_bundle["launch_preflight_ready"] is False
    assert transfer_bundle["launch_blocking_reasons"] == ["task_allowed_paths_outside_remote_policy"]


def test_remote_execution_execution_request_blocks_when_adapter_binding_drifted_since_launch_package(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    workspace = tmp_path / "workspace-execution-request-adapter-drift"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Adapter Drift Demo",
            "idea": "Need execution requests to stop when the adapter contract or route binding drifts after approval planning.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    launch_plan = client.post(
        f"/api/projects/{project_id}/remote-execution/launch-plan",
        json={
            "allowed_paths": ["artifacts/model.onnx"],
            "dry_run": True,
            "write_intent": False,
        },
    )
    assert launch_plan.status_code == 200, launch_plan.text
    payload = launch_plan.json()
    assert payload["plan_status"] == "ready"

    launch_request_path = workspace / payload["launch_request_path"]
    launch_request = json.loads(launch_request_path.read_text(encoding="utf-8"))
    launch_request["selected_adapter_contract_ids"] = ["stale_contract"]
    launch_request["selected_ready_adapter_route_ids"] = ["plain_ssh"]
    launch_request_path.write_text(json.dumps(launch_request, indent=2), encoding="utf-8")

    execution_request = client.post(
        f"/api/projects/{project_id}/remote-execution/execute-request",
        json={"expected_target_id": "gpu-box"},
    )
    assert execution_request.status_code == 200, execution_request.text
    request_payload = execution_request.json()
    assert request_payload["request_status"] == "blocked"
    assert request_payload["adapter_contract_status"] == "ready"
    assert request_payload["selected_adapter_contract_ids"] == ["linux_host_runtime"]
    assert request_payload["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert request_payload["launch_selected_adapter_contract_ids"] == ["stale_contract"]
    assert request_payload["launch_selected_ready_adapter_route_ids"] == ["plain_ssh"]
    assert "selected_adapter_contract_drifted_since_launch_package" in request_payload["blocking_reasons"]
    assert "selected_adapter_route_binding_drifted_since_launch_package" in request_payload["blocking_reasons"]

    execution_manifest = json.loads((workspace / request_payload["execution_request_path"]).read_text(encoding="utf-8"))
    assert execution_manifest["launch_selected_adapter_contract_ids"] == ["stale_contract"]
    assert execution_manifest["launch_selected_ready_adapter_route_ids"] == ["plain_ssh"]
    assert "selected_adapter_contract_drifted_since_launch_package" in execution_manifest["blocking_reasons"]
    assert "selected_adapter_route_binding_drifted_since_launch_package" in execution_manifest["blocking_reasons"]


def test_remote_execution_execution_request_blocks_when_current_adapter_rejects_transport_mode(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    workspace = tmp_path / "workspace-execution-request-transport-mode-blocked"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Transport Mode Block Demo",
            "idea": "Need execution requests blocked when the current adapter contract rejects the resolved transport mode.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    launch_plan = client.post(
        f"/api/projects/{project_id}/remote-execution/launch-plan",
        json={
            "allowed_paths": ["artifacts/model.onnx"],
            "dry_run": True,
            "write_intent": False,
        },
    )
    assert launch_plan.status_code == 200, launch_plan.text
    launch_payload = launch_plan.json()
    assert launch_payload["plan_status"] == "ready"

    original_summary = __import__("manager").service.build_platform_runner_summary

    def _blocked_transport_summary(db, project):
        summary = original_summary(db, project)
        mutated_lanes = []
        for lane in list(summary.get("lanes") or []):
            lane_payload = dict(lane or {})
            if str(lane_payload.get("lane_id") or "") == "linux":
                contract = dict(lane_payload.get("adapter_contract") or {})
                contract["artifact_shipping_modes"] = ["local_only"]
                lane_payload["adapter_contract"] = contract
            mutated_lanes.append(lane_payload)
        summary = dict(summary)
        summary["lanes"] = mutated_lanes
        return summary

    monkeypatch.setattr("manager.service.build_platform_runner_summary", _blocked_transport_summary)

    execution_request = client.post(
        f"/api/projects/{project_id}/remote-execution/execute-request",
        json={"expected_target_id": "gpu-box"},
    )
    assert execution_request.status_code == 200, execution_request.text
    request_payload = execution_request.json()
    assert request_payload["request_status"] == "blocked"
    assert request_payload["transport_mode"] == "remote_artifact_root"
    assert request_payload["transport_mode_adapter_status"] == "blocked"
    assert request_payload["transport_mode_supported_adapter_contract_ids"] == []
    assert request_payload["transport_mode_unsupported_adapter_contract_ids"] == ["linux_host_runtime"]
    assert request_payload["transport_mode_undeclared_adapter_contract_ids"] == []
    assert "selected_adapter_contracts_do_not_support_transport_mode" in request_payload["blocking_reasons"]

    execution_manifest = json.loads((workspace / request_payload["execution_request_path"]).read_text(encoding="utf-8"))
    assert execution_manifest["transport_mode_adapter_status"] == "blocked"
    assert execution_manifest["transport_mode_unsupported_adapter_contract_ids"] == ["linux_host_runtime"]
    assert "selected_adapter_contracts_do_not_support_transport_mode" in execution_manifest["blocking_reasons"]


def test_remote_execution_dispatch_route_launches_remote_task_and_links_run_manifests(
    client, tmp_path, monkeypatch
) -> None:
    from db import SessionLocal
    from models import Agent, Task

    class FakeRunner:
        runner_type = "remote_adapter"

        def __init__(self) -> None:
            self.contexts: list[object] = []

        async def start_task(self, context):
            self.contexts.append(context)
            from codex_runner.base import RunnerHandle

            return RunnerHandle(
                id="remote-dispatch-route-1",
                runner_type="remote_adapter",
                logs_path="C:/logs/remote-dispatch-route-1.log",
                stdout_path="C:/logs/remote-dispatch-route-1.stdout.log",
                stderr_path="C:/logs/remote-dispatch-route-1.stderr.log",
                event_log_path="C:/logs/remote-dispatch-route-1.events.jsonl",
            )

    async def fake_monitor_run(run_id: int) -> None:
        return None

    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    fake_runner = FakeRunner()
    monkeypatch.setattr("manager.service.runners.get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=fake_runner))
    monkeypatch.setattr("manager.service._monitor_run", fake_monitor_run)
    monkeypatch.setattr("manager.context_pack_service.build_context_pack", lambda db, project, agent_id, task_id, **kwargs: {"sections": []})
    monkeypatch.setattr("manager.context_pack_service.render_markdown", lambda payload: "")

    workspace = tmp_path / "workspace-remote-dispatch-route"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Dispatch Route Demo",
            "idea": "Need an explicit brokered dispatch route that returns both request and run metadata.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11"],
            "command_families": ["python"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["python3.11"],
            "required_command_families": ["python"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    launch_plan = client.post(
        f"/api/projects/{project_id}/remote-execution/launch-plan",
        json={
            "allowed_paths": ["artifacts/model.onnx"],
            "dry_run": True,
            "write_intent": False,
        },
    )
    assert launch_plan.status_code == 200, launch_plan.text
    assert launch_plan.json()["plan_status"] == "ready"

    db = SessionLocal()
    try:
        worker = Agent(
            project_id=project_id,
            name="Remote Validation Agent",
            role="Validation",
            kind="worker",
            status="idle",
            workspace_path=workspace.as_posix(),
        )
        task = Task(
            project_id=project_id,
            title="Run governed remote validation",
            goal="Launch through the explicit remote dispatch route.",
            scope="Do not edit code.",
            agent_role="Validation",
            milestone="Milestone 2",
            allowed_paths_json=["artifacts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Run metadata is linked back into the execution request bundle."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.commit()
        task_id = task.id
    finally:
        db.close()

    dispatch = client.post(f"/api/projects/{project_id}/tasks/{task_id}/remote-dispatch")
    assert dispatch.status_code == 200, dispatch.text
    payload = dispatch.json()
    assert payload["ok"] is True
    assert payload["message"] == "Remote execution task dispatched."
    assert payload["runner_type"] == "remote_adapter"
    assert payload["request_status"] == "ready"
    assert payload["target_id"] == "gpu-box"
    assert payload["runner_command"] == "python3"
    assert payload["runner_args"] == ["/opt/mission-control/adapter.py"]
    assert payload["transport_mode"] == "remote_artifact_root"
    assert payload["transport_mode_adapter_status"] == "ready"
    assert payload["selected_adapter_shipping_modes"] == [
        "workspace_relative_sync",
        "remote_artifact_root",
        "brokered_sync",
    ]
    assert payload["common_adapter_shipping_modes"] == [
        "workspace_relative_sync",
        "remote_artifact_root",
        "brokered_sync",
    ]
    assert payload["result_collection_contract_status"] == "ready"
    assert payload["result_collection_blocking_reasons"] == []
    assert payload["brokered_result_collection_supported"] is True
    assert payload["run_id"] is not None
    assert payload["execution_request_path"].startswith("artifacts/remote-execution-requests/")
    assert payload["transfer_bundle_path"].startswith("artifacts/remote-execution-requests/")
    assert payload["staged_outbound_transfer_bytes"] == (workspace / "artifacts" / "model.onnx").stat().st_size
    assert payload["transfer_quota_status"] == "not_applicable"
    assert payload["runtime_manifest_path"] == (
        "artifacts/remote-execution-governance/runtime/remote-dispatch-route-1-launch-manifest.json"
    )
    assert payload["dispatch_status"] == "dispatched"
    assert payload["dispatch_recorded_at"]
    assert payload["availability_diagnostics"]["summary"]
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert fake_runner.contexts
    assert fake_runner.contexts[0].settings.remote_execution["execution_request"]["request_status"] == "ready"

    execution_request_manifest = json.loads((workspace / payload["execution_request_path"]).read_text(encoding="utf-8"))
    assert execution_request_manifest["launched_run_id"] == payload["run_id"]
    assert execution_request_manifest["launched_process_ref"] == "remote-dispatch-route-1"
    assert execution_request_manifest["runtime_manifest_path"] == payload["runtime_manifest_path"]
    assert execution_request_manifest["dispatch_status"] == "dispatched"
    assert execution_request_manifest["dispatch_recorded_at"] == payload["dispatch_recorded_at"]
    assert execution_request_manifest["availability_diagnostics"]["summary"]
    assert execution_request_manifest["selected_target_requirement_gaps"] == {}
    assert execution_request_manifest["selected_target_rejected_reasons"] == []

    result_bundle_manifest = json.loads((workspace / payload["result_bundle_path"]).read_text(encoding="utf-8"))
    assert result_bundle_manifest["launched_run_id"] == payload["run_id"]
    assert result_bundle_manifest["launched_process_ref"] == "remote-dispatch-route-1"
    assert result_bundle_manifest["runtime_manifest_path"] == payload["runtime_manifest_path"]
    assert result_bundle_manifest["dispatch_status"] == "dispatched"
    assert result_bundle_manifest["dispatch_recorded_at"] == payload["dispatch_recorded_at"]
    assert result_bundle_manifest["transport_mode_adapter_status"] == "ready"
    transfer_bundle_manifest = json.loads((workspace / payload["transfer_bundle_path"]).read_text(encoding="utf-8"))
    assert transfer_bundle_manifest["launched_run_id"] == payload["run_id"]
    assert transfer_bundle_manifest["launched_process_ref"] == "remote-dispatch-route-1"
    assert transfer_bundle_manifest["runtime_manifest_path"] == payload["runtime_manifest_path"]
    assert transfer_bundle_manifest["status"] == "dispatched"
    assert transfer_bundle_manifest["dispatch_status"] == "dispatched"
    assert transfer_bundle_manifest["dispatch_recorded_at"] == payload["dispatch_recorded_at"]
    assert transfer_bundle_manifest["result_collection_contract_status"] == "ready"


def test_remote_execution_dispatch_route_reports_blocked_launch_package_preflight(
    client, tmp_path, monkeypatch
) -> None:
    from db import SessionLocal
    from models import Agent, Task

    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)

    workspace = tmp_path / "workspace-remote-dispatch-launch-preflight-blocked"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Dispatch Launch Preflight Block Demo",
            "idea": "Need dispatch to refuse launch packages that were already blocked during planning.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11"],
            "command_families": ["python"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["python3.11"],
            "required_command_families": ["python"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    launch_plan = client.post(
        f"/api/projects/{project_id}/remote-execution/launch-plan",
        json={
            "allowed_paths": ["artifacts/model.onnx"],
            "dry_run": True,
            "write_intent": False,
        },
    )
    assert launch_plan.status_code == 200, launch_plan.text
    launch_payload = launch_plan.json()
    assert launch_payload["plan_status"] == "ready"

    launch_request_path = workspace / launch_payload["launch_request_path"]
    launch_request = json.loads(launch_request_path.read_text(encoding="utf-8"))
    launch_request["plan_status"] = "blocked"
    launch_request["blocking_reasons"] = ["task_allowed_paths_outside_remote_policy"]
    launch_request_path.write_text(json.dumps(launch_request, indent=2), encoding="utf-8")

    db = SessionLocal()
    try:
        worker = Agent(
            project_id=project_id,
            name="Remote Validation Agent",
            role="Validation",
            kind="worker",
            status="idle",
            workspace_path=workspace.as_posix(),
        )
        task = Task(
            project_id=project_id,
            title="Run governed remote validation",
            goal="Dispatch through the explicit remote dispatch route.",
            scope="Do not edit code.",
            agent_role="Validation",
            milestone="Milestone 2",
            allowed_paths_json=["artifacts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Dispatch must stop before a blocked launch package can run."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.commit()
        task_id = task.id
    finally:
        db.close()

    dispatch = client.post(f"/api/projects/{project_id}/tasks/{task_id}/remote-dispatch")
    assert dispatch.status_code == 200, dispatch.text
    payload = dispatch.json()
    assert payload["ok"] is False
    assert payload["message"].startswith("Remote execution dispatch is blocked:")
    assert payload["request_status"] == "blocked"
    assert payload["approval_required"] is False
    assert payload["launch_plan_status"] == "blocked"
    assert payload["launch_preflight_ready"] is False
    assert payload["launch_blocking_reasons"] == ["task_allowed_paths_outside_remote_policy"]
    assert payload["target_id"] == "gpu-box"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["required_runner_family"] == "external_adapter"
    assert payload["transport"] == "tailscale_ssh"
    assert payload["host"] == "gpu-box.tailnet.ts.net"
    assert payload["adapter_contract_status"] == "ready"
    assert payload["selected_adapter_contract_ids"] == ["linux_host_runtime"]
    assert payload["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert payload["execution_request_path"].startswith("artifacts/remote-execution-requests/")
    assert payload["approval_binding_path"].startswith("artifacts/remote-execution-requests/")
    assert payload["result_bundle_path"].startswith("artifacts/remote-execution-requests/")
    assert payload["transfer_bundle_path"].startswith("artifacts/remote-execution-requests/")
    assert "launch_package_preflight_blocked" in payload["blocking_reasons"]
    assert "task_allowed_paths_outside_remote_policy" in payload["blocking_reasons"]
    assert payload["notes"]
    assert "launch_package_preflight_blocked" in payload["message"]
    assert "task_allowed_paths_outside_remote_policy" in payload["message"]


def test_remote_execution_dispatch_route_reports_pending_launch_approval(
    client, tmp_path, monkeypatch
) -> None:
    from db import SessionLocal
    from models import Agent, Task

    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.security_service.evaluate_action",
        lambda db, payload, project=None: {
            "policy": {},
            "assessment": {"risk_level": "high"},
            "decision": "pending",
            "reason": "High-risk remote launches require explicit approval.",
        },
    )

    workspace = tmp_path / "workspace-remote-dispatch-approval-pending"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Dispatch Pending Approval Demo",
            "idea": "Need dispatch to surface approval-required launch state instead of pretending retry logic can read minds.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "adapter_args": ["/opt/mission-control/adapter.py"],
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "max_command_runtime_seconds": 1200,
            "file_transfer_quota_mb": 1024,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "minimum_command_runtime_seconds": 900,
            "minimum_file_transfer_quota_mb": 512,
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    launch_plan = client.post(
        f"/api/projects/{project_id}/remote-execution/launch-plan",
        json={
            "allowed_paths": ["artifacts/model.onnx"],
            "dry_run": False,
            "write_intent": True,
        },
    )
    assert launch_plan.status_code == 200, launch_plan.text
    launch_payload = launch_plan.json()
    assert launch_payload["approval_status"] == "pending"
    approval_id = launch_payload["approval_id"]

    db = SessionLocal()
    try:
        worker = Agent(
            project_id=project_id,
            name="Remote Validation Agent",
            role="Validation",
            kind="worker",
            status="idle",
            workspace_path=workspace.as_posix(),
        )
        task = Task(
            project_id=project_id,
            title="Run governed remote validation",
            goal="Dispatch through the explicit remote dispatch route.",
            scope="Do not edit code.",
            agent_role="Validation",
            milestone="Milestone 2",
            allowed_paths_json=["artifacts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Dispatch must surface approval-required state before any remote run starts."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.commit()
        task_id = task.id
    finally:
        db.close()

    dispatch = client.post(f"/api/projects/{project_id}/tasks/{task_id}/remote-dispatch")
    assert dispatch.status_code == 200, dispatch.text
    payload = dispatch.json()
    assert payload["ok"] is False
    assert payload["message"].startswith("Remote execution dispatch is blocked:")
    assert payload["request_status"] == "approval_required"
    assert payload["approval_required"] is True
    assert payload["approval_id"] == approval_id
    assert payload["approval_status"] == "pending"
    assert payload["launch_plan_status"] == "partial"
    assert payload["launch_preflight_ready"] is True
    assert payload["launch_blocking_reasons"] == []
    assert payload["target_id"] == "gpu-box"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["required_runner_family"] == "external_adapter"
    assert payload["transport"] == "tailscale_ssh"
    assert payload["host"] == "gpu-box.tailnet.ts.net"
    assert payload["adapter_contract_status"] == "ready"
    assert payload["selected_adapter_contract_ids"] == ["linux_host_runtime"]
    assert payload["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert "launch_package_approval_pending" in payload["blocking_reasons"]
    assert payload["execution_request_path"].startswith("artifacts/remote-execution-requests/")
    assert payload["approval_binding_path"].startswith("artifacts/remote-execution-requests/")
    assert payload["result_bundle_path"].startswith("artifacts/remote-execution-requests/")
    assert payload["transfer_bundle_path"].startswith("artifacts/remote-execution-requests/")
    assert payload["notes"]
    assert "launch_package_approval_pending" in payload["message"]


def test_remote_execution_dispatch_route_supports_windows_agent_runner_with_project_adapter_fallback(
    client, tmp_path, monkeypatch
) -> None:
    from db import SessionLocal
    from models import Agent, ProjectSettings, Task

    class FakeRunner:
        runner_type = "remote_adapter"

        def __init__(self) -> None:
            self.contexts: list[object] = []

        async def start_task(self, context):
            self.contexts.append(context)
            from codex_runner.base import RunnerHandle

            return RunnerHandle(
                id="remote-dispatch-win-agent-1",
                runner_type="remote_adapter",
                logs_path="C:/logs/remote-dispatch-win-agent-1.log",
                stdout_path="C:/logs/remote-dispatch-win-agent-1.stdout.log",
                stderr_path="C:/logs/remote-dispatch-win-agent-1.stderr.log",
                event_log_path="C:/logs/remote-dispatch-win-agent-1.events.jsonl",
            )

    async def fake_monitor_run(run_id: int) -> None:
        return None

    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    fake_runner = FakeRunner()
    monkeypatch.setattr("manager.service.runners.get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=fake_runner))
    monkeypatch.setattr("manager.service._monitor_run", fake_monitor_run)
    monkeypatch.setattr("manager.context_pack_service.build_context_pack", lambda db, project, agent_id, task_id, **kwargs: {"sections": []})
    monkeypatch.setattr("manager.context_pack_service.render_markdown", lambda payload: "")

    workspace = tmp_path / "workspace-remote-dispatch-win-agent"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "manifest.json").write_text("{}\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Dispatch Windows Agent Demo",
            "idea": "Need governed dispatch for a Windows agent lane without per-host adapter duplication.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    db = SessionLocal()
    try:
        settings = db.query(ProjectSettings).filter(ProjectSettings.project_id == project_id).one()
        settings.adapter_command = "python"
        settings.adapter_args_json = ["adapter.py"]
        worker = Agent(
            project_id=project_id,
            name="Windows Validation Agent",
            role="Validation",
            kind="worker",
            status="idle",
            workspace_path=workspace.as_posix(),
        )
        task = Task(
            project_id=project_id,
            title="Run governed Windows agent validation",
            goal="Dispatch through the brokered Windows agent lane.",
            scope="Do not edit code.",
            agent_role="Validation",
            milestone="Milestone 2",
            allowed_paths_json=["artifacts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Execution request captures the fallback adapter command."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.commit()
        task_id = task.id
    finally:
        db.close()

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "win-agent",
            "label": "Windows Agent",
            "transport": "tailscale_ssh",
            "host": "win-agent.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "windows",
            "workspace_root": "C:/shadow",
            "runner_families": ["windows_agent_runner"],
            "capabilities": ["unity", "windows_build"],
            "toolchains": ["vs2022", "unity6000"],
            "command_families": ["powershell", "unity_batchmode"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["C:/shadow"],
            "allowed_path_prefixes": ["artifacts"],
            "artifact_roots": ["C:/shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "win-agent",
            "required_runner_family": "windows_agent_runner",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["vs2022"],
            "required_command_families": ["powershell"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["C:/shadow"],
            "required_path_prefixes": ["artifacts"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    launch_plan = client.post(
        f"/api/projects/{project_id}/remote-execution/launch-plan",
        json={
            "allowed_paths": ["artifacts/manifest.json"],
            "dry_run": True,
            "write_intent": False,
        },
    )
    assert launch_plan.status_code == 200, launch_plan.text
    launch_payload = launch_plan.json()
    assert launch_payload["plan_status"] == "ready"
    assert launch_payload["required_runner_family"] == "windows_agent_runner"
    assert launch_payload["runner_command"] == "python"
    assert launch_payload["runner_args"] == ["adapter.py"]
    assert launch_payload["adapter_command"] == "python"

    dispatch = client.post(f"/api/projects/{project_id}/tasks/{task_id}/remote-dispatch")
    assert dispatch.status_code == 200, dispatch.text
    payload = dispatch.json()
    assert payload["ok"] is True
    assert payload["runner_type"] == "remote_adapter"
    assert payload["request_status"] == "ready"
    assert payload["target_id"] == "win-agent"
    assert payload["runner_command"] == "python"
    assert payload["runner_args"] == ["adapter.py"]
    assert payload["dispatch_status"] == "dispatched"
    assert payload["dispatch_recorded_at"]
    assert fake_runner.contexts
    assert fake_runner.contexts[0].settings.remote_execution["execution_request"]["request_status"] == "ready"

    execution_request_manifest = json.loads((workspace / payload["execution_request_path"]).read_text(encoding="utf-8"))
    assert execution_request_manifest["required_runner_family"] == "windows_agent_runner"
    assert execution_request_manifest["runner_command"] == "python"
    assert execution_request_manifest["runner_args"] == ["adapter.py"]
    assert execution_request_manifest["adapter_command"] == "python"
    assert execution_request_manifest["launched_process_ref"] == "remote-dispatch-win-agent-1"


def test_device_broker_summary_route_composes_remote_artifact_and_connector_views(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    workspace = tmp_path / "workspace-device-broker"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Device Broker Demo",
            "idea": "Need a brokered remote execution summary.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "max_command_runtime_seconds": 1200,
            "file_transfer_quota_mb": 1024,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/device-broker/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["project_id"] == project_id
    assert payload["preflight_ready"] is True
    assert payload["selected_target_id"] == "gpu-box"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["ready_candidate_count"] == 1
    assert payload["ready_candidate_ids"] == ["gpu-box"]
    assert payload["ready_target_count"] == 1
    assert payload["recommended_target_ids"] == ["gpu-box"]
    assert payload["availability_diagnostics"]["candidate_count"] == 1
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["capability_index"]["toolchain_counts"]["cuda12"] == 1
    assert payload["artifact_registry"]["artifact_count"] == 1
    assert payload["connector_registry"]["connection_count"] >= 1


def test_device_broker_plan_route_emits_broker_manifests(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    workspace = tmp_path / "workspace-device-broker-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Device Broker Plan Demo",
            "idea": "Need brokered remote execution manifests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-box",
            "label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "max_command_runtime_seconds": 1200,
            "file_transfer_quota_mb": 1024,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "require_target_workspace_root": True,
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    plan = client.post(f"/api/projects/{project_id}/device-broker/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["preflight_ready"] is True
    assert payload["selected_target_id"] == "gpu-box"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["ready_target_count"] == 1
    assert payload["ready_candidate_count"] == 1
    assert payload["availability_diagnostics"]["candidate_count"] == 1
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["required_runner_family"] == "external_adapter"
    assert payload["manifest_root"] == "artifacts/device-broker"
    assert payload["target_index_path"] == "artifacts/device-broker/target-index.json"
    assert payload["broker_selection_path"] == "artifacts/device-broker/broker-selection.json"
    assert payload["policy_contract_path"] == "artifacts/device-broker/policy-contract.json"
    assert payload["artifact_contract_path"] == "artifacts/device-broker/artifact-contract.json"
    assert payload["connector_contract_path"] == "artifacts/device-broker/connector-contract.json"
    assert payload["approval_checkpoint_path"] == "artifacts/device-broker/approval-checkpoints.json"
    assert (workspace / "artifacts" / "device-broker" / "target-index.json").exists()
    assert (workspace / "artifacts" / "device-broker" / "broker-selection.json").exists()
    assert (workspace / "artifacts" / "device-broker" / "policy-contract.json").exists()
    assert (workspace / "artifacts" / "device-broker" / "artifact-contract.json").exists()
    assert (workspace / "artifacts" / "device-broker" / "connector-contract.json").exists()
    assert (workspace / "artifacts" / "device-broker" / "approval-checkpoints.json").exists()

    target_index = json.loads((workspace / "artifacts" / "device-broker" / "target-index.json").read_text(encoding="utf-8"))
    assert target_index["ready_target_ids"] == ["gpu-box"]
    assert target_index["transport_counts"]["tailscale_ssh"] == 1
    assert target_index["os_family_counts"]["linux"] == 1
    assert target_index["targets"][0]["target_id"] == "gpu-box"

    broker_selection = json.loads((workspace / "artifacts" / "device-broker" / "broker-selection.json").read_text(encoding="utf-8"))
    assert broker_selection["selection_requirements"]["approval_required"] is True
    assert broker_selection["selection_requirements"]["session_recording_required"] is True
    assert broker_selection["availability_diagnostics"]["candidate_count"] == 1
    assert broker_selection["selected_target_requirement_gaps"] == {}
    assert broker_selection["selected_target_rejected_reasons"] == []
    assert broker_selection["selected_target"]["transport"] == "tailscale_ssh"

    policy_contract = json.loads((workspace / "artifacts" / "device-broker" / "policy-contract.json").read_text(encoding="utf-8"))
    assert policy_contract["policy_requirements"]["required_toolchains"] == ["cuda12"]
    assert policy_contract["policy_requirements"]["required_path_prefixes"] == ["artifacts"]
    assert policy_contract["security_controls"]["session_recording_required"] is True
    assert policy_contract["security_controls"]["workspace_root_required"] is True

    artifact_contract = json.loads((workspace / "artifacts" / "device-broker" / "artifact-contract.json").read_text(encoding="utf-8"))
    assert artifact_contract["artifact_scope"]["selected_artifact_root"] == "/srv/shadow/artifacts"
    assert artifact_contract["artifact_scope"]["remote_workspace_root"] == "/srv/shadow"
    assert "artifacts/model.onnx" in artifact_contract["artifact_registry"]["artifact_paths"]

    connector_contract = json.loads((workspace / "artifacts" / "device-broker" / "connector-contract.json").read_text(encoding="utf-8"))
    assert connector_contract["required_family_status"]["required_connector_families"] == ["source_control"]
    assert connector_contract["required_family_status"]["missing_required_families"] == []
    assert connector_contract["required_family_status"]["preflight_ready"] is True
    assert "source_control" in connector_contract["required_family_status"]["target_connector_families"]

    approval_checkpoints = json.loads((workspace / "artifacts" / "device-broker" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    checkpoint_ids = [item["checkpoint_id"] for item in approval_checkpoints["checkpoints"]]
    assert "policy_contract_review" in checkpoint_ids
    assert "workspace_root_review" in checkpoint_ids


def test_device_broker_resolve_route_matches_specialized_hosts_and_writes_request_bundle(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    workspace = tmp_path / "workspace-device-broker-resolve"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Device Broker Resolve Demo",
            "idea": "Need brokered host resolution requests for specialized execution lanes.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    for target in [
        {
            "id": "linux-cuda",
            "label": "Linux CUDA",
            "transport": "tailscale_ssh",
            "host": "linux-cuda.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "linux",
            "architecture": "x86_64",
            "workspace_root": "/srv/linux-cuda",
            "runner_families": ["external_adapter", "tailscale_ssh_runner"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["cuda12", "python3.11"],
            "installed_runtimes": ["docker", "nvidia_container_toolkit"],
            "command_families": ["python", "bash"],
            "result_formats": ["json"],
            "trust_level": "trusted",
            "session_recording_enabled": True,
            "last_probe_status": "ready",
        },
        {
            "id": "windows-ue5",
            "label": "Windows UE5",
            "transport": "ssh",
            "host": "windows-ue5.local",
            "ssh_user": "mike",
            "os_family": "windows",
            "architecture": "x86_64",
            "workspace_root": "C:/BuildFarm",
            "runner_families": ["windows_agent_runner"],
            "capabilities": ["powershell", "unreal"],
            "toolchains": ["ue5", "vs2022"],
            "installed_runtimes": ["unreal_engine_5.4", "dotnet8"],
            "command_families": ["powershell", "unreal_automation"],
            "result_formats": ["json", "junit_xml"],
            "trust_level": "trusted",
            "session_recording_enabled": True,
            "last_probe_status": "ready",
        },
        {
            "id": "macos-xcode",
            "label": "macOS Xcode",
            "transport": "ssh",
            "host": "macos-xcode.local",
            "ssh_user": "mike",
            "os_family": "macos",
            "architecture": "arm64",
            "workspace_root": "/Users/build/ios",
            "runner_families": ["macos_agent_runner"],
            "capabilities": ["swift", "ios"],
            "toolchains": ["xcode16", "swift5.10"],
            "installed_runtimes": ["xcode_16", "ios_simulator"],
            "command_families": ["xcodebuild", "swift"],
            "result_formats": ["json", "xcresult"],
            "trust_level": "trusted",
            "session_recording_enabled": True,
            "last_probe_status": "ready",
        },
    ]:
        upsert = client.put("/api/system/remote-execution/hosts", json=target)
        assert upsert.status_code == 200, upsert.text

    resolution = client.post(
        f"/api/projects/{project_id}/device-broker/resolve",
        json={
            "request_id": "linux-cuda-request",
            "intent": "run on Linux CUDA host",
            "required_runner_families": ["tailscale_ssh_runner"],
            "required_os_families": ["linux"],
            "require_gpu": True,
            "required_toolchains": ["cuda12", "python3.11"],
            "required_installed_runtimes": ["docker", "nvidia_container_toolkit"],
            "required_command_families": ["python"],
            "require_probe_ready": True,
        },
    )
    assert resolution.status_code == 200, resolution.text
    payload = resolution.json()
    assert payload["resolution_status"] == "ready"
    assert payload["selected_target_id"] == "linux-cuda"
    assert payload["selected_target_label"] == "Linux CUDA"
    assert payload["ready_candidate_ids"] == ["linux-cuda"]
    assert payload["required_installed_runtimes"] == ["docker", "nvidia_container_toolkit"]
    assert payload["manifest_root"] == "artifacts/device-broker/requests/linux-cuda-request"
    assert payload["availability_diagnostics"]["candidate_count"] == 3
    assert payload["availability_diagnostics"]["eligible_target_count"] == 1
    assert payload["availability_diagnostics"]["ready_candidate_count"] == 1

    request_manifest = json.loads((workspace / payload["request_path"]).read_text(encoding="utf-8"))
    assert request_manifest["request_id"] == "linux-cuda-request"
    assert request_manifest["required_toolchains"] == ["cuda12", "python3.11"]
    assert request_manifest["required_installed_runtimes"] == ["docker", "nvidia_container_toolkit"]

    resolution_manifest = json.loads((workspace / payload["resolution_path"]).read_text(encoding="utf-8"))
    assert resolution_manifest["selected_target_id"] == "linux-cuda"
    assert resolution_manifest["resolution_status"] == "ready"
    assert resolution_manifest["availability_diagnostics"]["candidate_count"] == 3

    candidate_index_manifest = json.loads((workspace / payload["candidate_index_path"]).read_text(encoding="utf-8"))
    assert candidate_index_manifest["capability_index"]["installed_runtime_counts"]["docker"] == 1
    assert candidate_index_manifest["candidates"][0]["target_id"] == "linux-cuda"
    assert candidate_index_manifest["availability_diagnostics"]["candidate_count"] == 3


def test_connector_governance_summary_route_surfaces_authority_and_bounded_discovery(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-connector-governance"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Connector Governance Demo",
            "idea": "Need governed connector discovery instead of connector spaghetti.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    monkeypatch.setattr(
        "manager.service.build_project_integrations",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Three integration families are visible.",
            "family_count": 3,
            "blocking_reasons": ["provider_context_missing"],
            "recommended_fix_values": ["Reconnect design assets through Mission Control auth."],
            "note_values": ["Preview-first actions are available on source control."],
            "families": [
                {
                    "family": "source_control",
                    "name": "Source Control",
                    "category": "developer_workflow",
                    "status": "ready",
                    "connection_status": "connected",
                    "connection_source": "manual",
                    "resolved_provider": "github",
                    "provider_resolution_state": "resolved",
                    "provider_context_status": "verified",
                    "provider_context_verified": True,
                    "host_imported": False,
                    "providers": ["github"],
                    "available_action_count": 3,
                    "blocked_action_count": 0,
                    "available_execution_action_count": 1,
                    "preview_supported_execution_action_count": 1,
                    "safe_command_action_count": 1,
                    "available_non_mutating_action_count": 2,
                    "available_mutating_action_count": 1,
                    "ready_to_execute_action_count": 1,
                    "blockers": [],
                    "recommended_fixes": [],
                    "notes": ["PR preview is available before mutation."],
                },
                {
                    "family": "design_assets",
                    "name": "Design Assets",
                    "category": "design",
                    "status": "partial",
                    "connection_status": "host_detected",
                    "connection_source": "codex_host",
                    "resolved_provider": "figma",
                    "provider_resolution_state": "resolved",
                    "provider_context_status": "missing",
                    "provider_context_verified": False,
                    "host_imported": True,
                    "providers": ["figma"],
                    "available_action_count": 1,
                    "blocked_action_count": 1,
                    "available_execution_action_count": 0,
                    "preview_supported_execution_action_count": 0,
                    "safe_command_action_count": 0,
                    "available_non_mutating_action_count": 1,
                    "available_mutating_action_count": 0,
                    "ready_to_execute_action_count": 0,
                    "blockers": ["provider_context_missing"],
                    "recommended_fixes": ["Reconnect Figma through Mission Control auth."],
                    "notes": ["Host-imported signal is advisory only."],
                },
                {
                    "family": "cloud_storage",
                    "name": "Cloud Storage",
                    "category": "storage",
                    "status": "needs_setup",
                    "connection_status": "disconnected",
                    "connection_source": "mission_control",
                    "resolved_provider": None,
                    "provider_resolution_state": "unresolved",
                    "provider_context_status": "missing",
                    "provider_context_verified": False,
                    "host_imported": False,
                    "providers": [],
                    "available_action_count": 0,
                    "blocked_action_count": 0,
                    "available_execution_action_count": 0,
                    "preview_supported_execution_action_count": 0,
                    "safe_command_action_count": 0,
                    "available_non_mutating_action_count": 0,
                    "available_mutating_action_count": 0,
                    "ready_to_execute_action_count": 0,
                    "blockers": [],
                    "recommended_fixes": ["Connect a storage provider before discovery."],
                    "notes": [],
                },
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.get_connector_registry",
        lambda db: {
            "summary": "Two connector lanes are currently visible.",
            "family_count": 2,
            "connection_count": 2,
            "authoritative_connection_count": 1,
            "host_imported_count": 1,
            "status_counts": {"connected": 1, "host_detected": 1},
            "host_import_roots": {},
            "recent_action_failures": [],
            "ready_family_count": 1,
            "ready_families": ["source_control"],
            "provider_counts": {"github": 1, "figma": 1},
            "provider_count": 2,
            "category_counts": {"developer_workflow": 1, "design": 1},
            "category_count": 2,
            "connection_source_counts": {"manual": 1, "codex_host": 1},
            "connection_source_count": 2,
            "available_action_count": 4,
            "catalog": [],
            "connections": [],
        },
    )

    response = client.get(f"/api/projects/{project_id}/connector-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["governance_status"] == "partial"
    assert payload["recommended_operation_mode"] == "governed_connector_actions"
    assert payload["family_count"] == 3
    assert payload["connected_family_count"] == 2
    assert payload["live_family_count"] == 1
    assert payload["ready_family_count"] == 1
    assert payload["partial_family_count"] == 1
    assert payload["needs_setup_family_count"] == 1
    assert payload["authoritative_family_count"] == 1
    assert payload["host_imported_family_count"] == 1
    assert payload["discovery_ready_family_count"] == 2
    assert payload["execution_ready_family_count"] == 1
    assert payload["previewable_execution_family_count"] == 1
    assert payload["safe_command_family_count"] == 1
    assert payload["provider_context_verified_family_count"] == 1
    assert payload["providers"] == ["github", "figma"]
    assert payload["categories"] == ["developer_workflow", "design", "storage"]
    assert "provider_context_missing" in payload["blocking_reasons"]
    assert payload["live_family_ids"] == ["source_control"]
    assert payload["authoritative_family_ids"] == ["source_control"]
    assert payload["host_imported_family_ids"] == ["design_assets"]
    assert sorted(payload["discovery_ready_family_ids"]) == ["design_assets", "source_control"]
    assert payload["execution_ready_family_ids"] == ["source_control"]
    families = {item["family"]: item for item in payload["families"]}
    assert families["source_control"]["authoritative"] is True
    assert families["source_control"]["execution_ready"] is True
    assert families["design_assets"]["host_imported"] is True
    assert families["design_assets"]["discovery_ready"] is True
    assert "provider_context_missing" in families["design_assets"]["blockers"]
    assert payload["connector_registry"]["authoritative_connection_count"] == 1


def test_artifact_and_connector_governance_plan_routes_emit_project_manifests(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-artifact-connector-plans"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Artifact Connector Governance Plans",
            "idea": "Need manifest-backed artifact and connector planning.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    monkeypatch.setattr(
        "manager.service.build_project_artifact_registry",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "Artifacts are present.",
            "artifact_count": 4,
            "artifact_paths": [
                "artifacts/model.onnx",
                "data/train.parquet",
                "reports/eval.json",
                "configs/model.yaml",
            ],
            "artifact_extensions": [".json", ".onnx", ".parquet", ".yaml"],
            "artifact_extension_count": 4,
            "artifact_kind_summaries": ["dataset:1", "model:1", "report:1", "config:1"],
            "artifact_kind_counts": {"dataset": 1, "model": 1, "report": 1, "config": 1},
            "artifact_kind_count": 4,
            "inspection_command_count": 1,
            "inspection_commands": ["python inspect.py --artifact artifacts/model.onnx"],
            "config_review_path_count": 1,
            "config_review_paths": ["configs/model.yaml"],
            "config_review_command_count": 1,
            "config_review_commands": ["python -c \"print('review config')\""],
            "validation_evidence_target_count": 2,
            "validation_evidence_targets": ["reports/eval.json", "data/train.parquet"],
            "execution_entrypoint_count": 1,
            "execution_entrypoints": ["python eval.py --artifact artifacts/model.onnx"],
            "notebook_path_count": 1,
            "notebook_paths": ["notebooks/error-analysis.ipynb"],
            "recommended_next_steps": ["Review dataset drift before publish."],
            "recommended_next_step_count": 1,
        },
    )
    monkeypatch.setattr(
        "manager.service.build_connector_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Connector governance is partially ready.",
            "governance_status": "partial",
            "recommended_operation_mode": "governed_connector_actions",
            "family_count": 3,
            "connected_family_count": 2,
            "live_family_count": 1,
            "ready_family_count": 1,
            "partial_family_count": 1,
            "needs_setup_family_count": 1,
            "authoritative_family_count": 1,
            "host_imported_family_count": 1,
            "discovery_ready_family_count": 2,
            "execution_ready_family_count": 1,
            "previewable_execution_family_count": 1,
            "safe_command_family_count": 1,
            "mutating_execution_family_count": 1,
            "provider_context_verified_family_count": 1,
            "provider_count": 2,
            "providers": ["github", "figma"],
            "category_count": 3,
            "categories": ["developer_workflow", "design", "storage"],
            "connected_family_ids": ["source_control", "design_assets"],
            "live_family_ids": ["source_control"],
            "authoritative_family_ids": ["source_control"],
            "host_imported_family_ids": ["design_assets"],
            "discovery_ready_family_ids": ["source_control", "design_assets"],
            "execution_ready_family_ids": ["source_control"],
            "blocking_reasons": ["provider_context_missing"],
            "recommended_fixes": ["Reconnect design assets through Mission Control auth."],
            "notes": ["Preview-backed source control lane is ready."],
            "families": [
                {
                    "family": "source_control",
                    "name": "Source Control",
                    "category": "developer_workflow",
                    "status": "ready",
                    "connection_status": "connected",
                    "connection_source": "manual",
                    "authoritative": True,
                    "host_imported": False,
                    "provider_context_verified": True,
                    "available_mutating_action_count": 1,
                    "safe_command_action_count": 1,
                    "discovery_ready": True,
                    "execution_ready": True,
                    "blockers": [],
                },
                {
                    "family": "design_assets",
                    "name": "Design Assets",
                    "category": "design",
                    "status": "partial",
                    "connection_status": "host_detected",
                    "connection_source": "codex_host",
                    "authoritative": False,
                    "host_imported": True,
                    "provider_context_verified": False,
                    "available_mutating_action_count": 0,
                    "safe_command_action_count": 0,
                    "discovery_ready": True,
                    "execution_ready": False,
                    "blockers": ["provider_context_missing"],
                },
                {
                    "family": "cloud_storage",
                    "name": "Cloud Storage",
                    "category": "storage",
                    "status": "needs_setup",
                    "connection_status": "disconnected",
                    "connection_source": "mission_control",
                    "authoritative": False,
                    "host_imported": False,
                    "provider_context_verified": False,
                    "available_mutating_action_count": 0,
                    "safe_command_action_count": 0,
                    "discovery_ready": False,
                    "execution_ready": False,
                    "blockers": [],
                },
            ],
            "connector_registry": {
                "summary": "Two connector lanes are visible.",
                "family_count": 2,
                "connection_count": 2,
                "authoritative_connection_count": 1,
                "host_imported_count": 1,
                "status_counts": {"connected": 1, "host_detected": 1},
                "host_import_roots": {},
                "recent_action_failures": [],
                "ready_family_count": 1,
                "ready_families": ["source_control"],
                "provider_counts": {"github": 1, "figma": 1},
                "provider_count": 2,
                "category_counts": {"developer_workflow": 1, "design": 1},
                "category_count": 2,
                "connection_source_counts": {"manual": 1, "codex_host": 1},
                "connection_source_count": 2,
                "available_action_count": 2,
                "catalog": [],
                "connections": [],
            },
        },
    )

    artifact_plan = client.post(f"/api/projects/{project_id}/artifact-registry/plan")
    assert artifact_plan.status_code == 200, artifact_plan.text
    artifact_payload = artifact_plan.json()
    assert artifact_payload["project_id"] == project_id
    assert artifact_payload["artifact_count"] == 4
    assert artifact_payload["artifact_kind_count"] == 4
    assert artifact_payload["plan_status"] in {"ready", "partial"}
    assert artifact_payload["manifest_root"] == "artifacts/artifact-registry"
    assert artifact_payload["remote_runtime_rollup_path"] == "artifacts/artifact-registry/remote-runtime-rollup.json"
    assert (workspace / "artifacts" / "artifact-registry" / "inventory.json").exists()
    assert (workspace / "artifacts" / "artifact-registry" / "kind-rollup.json").exists()
    assert (workspace / "artifacts" / "artifact-registry" / "inspection-plan.json").exists()
    assert (workspace / "artifacts" / "artifact-registry" / "validation-targets.json").exists()
    assert (workspace / "artifacts" / "artifact-registry" / "execution-surface.json").exists()
    assert (workspace / "artifacts" / "artifact-registry" / "remote-runtime-rollup.json").exists()

    connector_plan = client.post(f"/api/projects/{project_id}/connector-governance/plan")
    assert connector_plan.status_code == 200, connector_plan.text
    connector_payload = connector_plan.json()
    assert connector_payload["project_id"] == project_id
    assert connector_payload["family_count"] == 3
    assert connector_payload["discovery_ready_family_count"] == 2
    assert connector_payload["execution_ready_family_count"] == 1
    assert connector_payload["authoritative_family_count"] == 1
    assert connector_payload["recommended_operation_mode"] == "governed_connector_actions"
    assert connector_payload["plan_status"] in {"ready", "partial"}
    assert connector_payload["manifest_root"] == "artifacts/connector-governance"
    assert (workspace / "artifacts" / "connector-governance" / "family-rollup.json").exists()
    assert (workspace / "artifacts" / "connector-governance" / "discovery-lanes.json").exists()
    assert (workspace / "artifacts" / "connector-governance" / "execution-lanes.json").exists()
    assert (workspace / "artifacts" / "connector-governance" / "provider-context.json").exists()
    assert (workspace / "artifacts" / "connector-governance" / "approval-guardrails.json").exists()
    assert (workspace / "artifacts" / "connector-governance" / "connector-registry.json").exists()

    family_rollup = json.loads((workspace / "artifacts" / "connector-governance" / "family-rollup.json").read_text(encoding="utf-8"))
    assert family_rollup["status_counts"]["ready"] == 1
    assert family_rollup["status_counts"]["partial"] == 1
    assert family_rollup["status_counts"]["needs_setup"] == 1
    assert family_rollup["authoritative_family_ids"] == ["source_control"]
    assert family_rollup["host_imported_family_ids"] == ["design_assets"]

    discovery_lanes = json.loads((workspace / "artifacts" / "connector-governance" / "discovery-lanes.json").read_text(encoding="utf-8"))
    assert discovery_lanes["discovery_requirements"]["authoritative_lane_required_for_publish"] is True
    assert discovery_lanes["discovery_requirements"]["provider_context_review_required"] is True
    discovery_ready_ids = [item["family"] for item in discovery_lanes["discovery_ready_families"]]
    assert discovery_ready_ids == ["source_control", "design_assets"]

    execution_lanes = json.loads((workspace / "artifacts" / "connector-governance" / "execution-lanes.json").read_text(encoding="utf-8"))
    assert execution_lanes["safe_command_family_ids"] == ["source_control"]
    assert execution_lanes["mutation_guard_family_ids"] == ["source_control"]
    assert execution_lanes["execution_requirements"]["mutating_actions_require_guardrails"] is True

    provider_context = json.loads((workspace / "artifacts" / "connector-governance" / "provider-context.json").read_text(encoding="utf-8"))
    assert provider_context["provider_context_missing_family_ids"] == ["cloud_storage", "design_assets"]
    assert provider_context["provider_context_verified_family_ids"] == ["source_control"]
    assert provider_context["provider_resolution_requirements"]["host_import_reauth_required"] is True

    approval_guardrails = json.loads((workspace / "artifacts" / "connector-governance" / "approval-guardrails.json").read_text(encoding="utf-8"))
    assert approval_guardrails["approval_requirements"]["mutating_actions_require_approval_or_preview"] is True
    assert approval_guardrails["provider_context_missing_family_ids"] == ["cloud_storage", "design_assets"]
    checkpoint_ids = [item["checkpoint_id"] for item in approval_guardrails["checkpoints"]]
    assert "authoritative_discovery_lane" in checkpoint_ids
    assert "mutation_guard_review" in checkpoint_ids


def test_external_discovery_governance_summary_route_surfaces_bounded_ingestion_lanes(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-external-discovery"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "External Discovery Demo",
            "idea": "Need governed external discovery across design, storage, and knowledge lanes.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    monkeypatch.setattr(
        "manager.service.build_project_integrations",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "External discovery lanes are visible.",
            "family_count": 3,
            "blocking_reasons": [],
            "recommended_fix_values": [],
            "note_values": ["Preview-backed support search is available."],
            "families": [
                {
                    "family": "google_drive",
                    "name": "Google Drive",
                    "category": "storage",
                    "summary": "Drive indexing lane.",
                    "status": "partial",
                    "connection_status": "connected",
                    "connection_source": "manual",
                    "host_imported": False,
                    "provider_context_verified": True,
                    "providers": ["google_drive"],
                    "available_actions": [
                        {"action_id": "list", "title": "List files", "summary": "List remote files.", "preview_supported": True, "mutates_remote_state": False, "requires_confirmation": False, "safe_command_eligible": True, "ready_to_execute": True, "supports_pagination": True, "supports_streaming_output": True, "supports_file_output": False, "supports_throttle_controls": True},
                        {"action_id": "export", "title": "Export metadata", "summary": "Export file metadata.", "preview_supported": True, "mutates_remote_state": False, "requires_confirmation": False, "safe_command_eligible": False, "ready_to_execute": True, "supports_pagination": False, "supports_streaming_output": False, "supports_file_output": True, "supports_throttle_controls": True},
                    ],
                    "blockers": [],
                    "recommended_fixes": [],
                    "notes": ["Pagination should stay bounded at the connector layer."],
                },
                {
                    "family": "design_assets",
                    "name": "Design Assets",
                    "category": "design",
                    "summary": "Figma asset export lane.",
                    "status": "partial",
                    "connection_status": "host_detected",
                    "connection_source": "codex_host",
                    "host_imported": True,
                    "provider_context_verified": False,
                    "providers": ["figma"],
                    "available_actions": [
                        {"action_id": "export", "title": "Export tokens", "summary": "Export design tokens.", "preview_supported": False, "mutates_remote_state": False, "requires_confirmation": False, "safe_command_eligible": False, "ready_to_execute": False, "supports_pagination": False, "supports_streaming_output": False, "supports_file_output": True, "supports_throttle_controls": True},
                    ],
                    "blockers": ["provider_context_missing"],
                    "recommended_fixes": ["Reconnect Figma through Mission Control auth."],
                    "notes": ["Host-imported lane is advisory."],
                },
                {
                    "family": "support_desk",
                    "name": "Knowledge Base / Support Desk",
                    "category": "support",
                    "summary": "Support search lane.",
                    "status": "ready",
                    "connection_status": "connected",
                    "connection_source": "manual",
                    "host_imported": False,
                    "provider_context_verified": True,
                    "providers": ["zendesk"],
                    "available_actions": [
                        {"action_id": "search", "title": "Search tickets", "summary": "Search support state.", "preview_supported": True, "mutates_remote_state": False, "requires_confirmation": False, "safe_command_eligible": False, "ready_to_execute": True, "supports_pagination": True, "supports_streaming_output": True, "supports_file_output": False, "supports_throttle_controls": True},
                        {"action_id": "create", "title": "Create ticket", "summary": "Create a support artifact.", "preview_supported": True, "mutates_remote_state": True, "requires_confirmation": True, "safe_command_eligible": False, "ready_to_execute": True, "supports_pagination": False, "supports_streaming_output": False, "supports_file_output": False, "supports_throttle_controls": False},
                    ],
                    "blockers": [],
                    "recommended_fixes": [],
                    "notes": ["Search and create stay separate."],
                },
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_connector_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Connector governance is healthy enough.",
            "governance_status": "partial",
            "recommended_operation_mode": "governed_connector_actions",
            "family_count": 3,
            "connected_family_count": 3,
            "ready_family_count": 1,
            "partial_family_count": 2,
            "needs_setup_family_count": 0,
            "authoritative_family_count": 2,
            "host_imported_family_count": 1,
            "discovery_ready_family_count": 3,
            "execution_ready_family_count": 2,
            "previewable_execution_family_count": 2,
            "safe_command_family_count": 1,
            "mutating_execution_family_count": 1,
            "provider_context_verified_family_count": 2,
            "provider_count": 3,
            "providers": ["google_drive", "figma", "zendesk"],
            "category_count": 3,
            "categories": ["storage", "design", "support"],
            "connected_family_ids": ["google_drive", "design_assets", "support_desk"],
            "authoritative_family_ids": ["google_drive", "support_desk"],
            "host_imported_family_ids": ["design_assets"],
            "discovery_ready_family_ids": ["google_drive", "design_assets", "support_desk"],
            "execution_ready_family_ids": ["google_drive", "support_desk"],
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": [],
            "families": [],
            "connector_registry": {
                "summary": "registry",
                "family_count": 3,
                "connection_count": 3,
                "authoritative_connection_count": 2,
                "host_imported_count": 1,
                "status_counts": {"connected": 2, "host_detected": 1},
                "host_import_roots": {},
                "recent_action_failures": [],
                "ready_family_count": 2,
                "ready_families": ["google_drive", "support_desk"],
                "provider_counts": {"google_drive": 1, "figma": 1, "zendesk": 1},
                "provider_count": 3,
                "category_counts": {"storage": 1, "design": 1, "support": 1},
                "category_count": 3,
                "connection_source_counts": {"manual": 2, "codex_host": 1},
                "connection_source_count": 2,
                "available_action_count": 5,
                "catalog": [],
                "connections": [],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_file_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "File governance can back remote storage discovery.",
            "recommended_operation_mode": "hybrid_connector_sync",
            "supports_bulk_planning": True,
            "destructive_actions_require_approval": True,
            "storage_lane_count": 2,
            "connected_storage_lane_count": 1,
            "ready_scanner_lane_count": 1,
            "storage_provider_count": 2,
            "storage_providers": ["local_fs", "google_drive"],
            "ready_scanner_lanes": ["linux"],
            "blocking_reasons": [],
            "notes": ["Scanner lane is available for filesystem verification."],
            "storage_lanes": [],
            "connector_registry": {
                "summary": "registry",
                "family_count": 1,
                "connection_count": 1,
                "authoritative_connection_count": 1,
                "host_imported_count": 0,
                "status_counts": {"connected": 1},
                "host_import_roots": {},
                "recent_action_failures": [],
                "ready_family_count": 1,
                "ready_families": ["google_drive"],
                "provider_counts": {"google_drive": 1},
                "provider_count": 1,
                "category_counts": {"storage": 1},
                "category_count": 1,
                "connection_source_counts": {"manual": 1},
                "connection_source_count": 1,
                "available_action_count": 2,
                "catalog": [],
                "connections": [],
            },
            "platform_runners": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "Linux scanner lane ready.",
                "selected_target_id": None,
                "lane_count": 1,
                "ready_lane_count": 1,
                "partial_lane_count": 0,
                "unavailable_lane_count": 0,
                "ready_lane_ids": ["linux"],
                "partial_lane_ids": [],
                "unavailable_lane_ids": [],
                "lanes": [],
            },
            "artifact_transport": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "Artifact transport ready.",
                "selected_target_id": None,
                "preflight_ready": True,
                "sync_enabled": True,
                "recommended_transport_mode": "connector_only",
                "blocking_reasons": [],
                "ready_platform_lanes": ["linux"],
                "partial_platform_lanes": [],
                "notes": [],
                "artifact_registry": {
                    "project_id": project.id,
                    "project_name": project.name,
                    "workspace_path": project.workspace_path,
                    "available": True,
                    "summary": "artifacts",
                    "artifact_count": 0,
                    "artifact_paths": [],
                    "artifact_extensions": [],
                    "artifact_extension_count": 0,
                    "artifact_kind_summaries": [],
                    "artifact_kind_counts": {},
                    "artifact_kind_count": 0,
                    "inspection_command_count": 0,
                    "inspection_commands": [],
                    "config_review_path_count": 0,
                    "config_review_paths": [],
                    "config_review_command_count": 0,
                    "config_review_commands": [],
                    "validation_evidence_target_count": 0,
                    "validation_evidence_targets": [],
                    "execution_entrypoint_count": 0,
                    "execution_entrypoints": [],
                    "notebook_path_count": 0,
                    "notebook_paths": [],
                    "recommended_next_steps": [],
                    "recommended_next_step_count": 0,
                },
                "connector_registry": {
                    "summary": "registry",
                    "family_count": 1,
                    "connection_count": 1,
                    "authoritative_connection_count": 1,
                    "host_imported_count": 0,
                    "status_counts": {"connected": 1},
                    "host_import_roots": {},
                    "recent_action_failures": [],
                    "ready_family_count": 1,
                    "ready_families": ["google_drive"],
                    "provider_counts": {"google_drive": 1},
                    "provider_count": 1,
                    "category_counts": {"storage": 1},
                    "category_count": 1,
                    "connection_source_counts": {"manual": 1},
                    "connection_source_count": 1,
                    "available_action_count": 2,
                    "catalog": [],
                    "connections": [],
                },
                "artifact_contract": {
                    "sync_enabled": True,
                    "required": False,
                    "local_artifact_paths": [],
                    "local_artifact_path_count": 0,
                    "target_artifact_roots": [],
                    "selected_artifact_root": None,
                    "remote_workspace_root": None,
                    "preflight_ready": True,
                    "blocking_reasons": [],
                },
                "connector_contract": {
                    "required_connector_families": [],
                    "target_connector_families": [],
                    "allow_host_integrated_connectors": True,
                    "require_connector_authority": False,
                    "available_families": ["google_drive"],
                    "available_connector_count": 1,
                    "missing_required_families": [],
                    "preflight_ready": True,
                    "blocking_reasons": [],
                    "notes": [],
                },
            },
        },
    )

    response = client.get(f"/api/projects/{project_id}/external-discovery/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["governance_status"] == "ready"
    assert payload["recommended_operation_mode"] == "bounded_connector_discovery"
    assert payload["bounded_discovery_status"] == "ready"
    assert payload["authoritative_connector_status"] == "ready"
    assert payload["read_only_status"] == "ready"
    assert payload["previewability_status"] == "ready"
    assert payload["mutation_guard_status"] == "ready"
    assert payload["pagination_status"] == "ready"
    assert payload["streaming_status"] == "ready"
    assert payload["file_output_status"] == "ready"
    assert payload["throttle_control_status"] == "ready"
    assert payload["storage_discovery_status"] == "ready"
    assert payload["design_discovery_status"] == "ready"
    assert payload["knowledge_discovery_status"] == "ready"
    assert payload["lane_count"] == 3
    assert payload["authoritative_lane_count"] == 2
    assert payload["live_lane_count"] == 2
    assert payload["host_imported_lane_count"] == 1
    assert payload["discovery_ready_lane_count"] == 3
    assert payload["execution_ready_lane_count"] == 2
    assert payload["previewable_lane_count"] == 2
    assert payload["read_only_lane_count"] == 3
    assert payload["mutating_lane_count"] == 1
    assert payload["confirmation_guarded_lane_count"] == 1
    assert payload["safe_command_lane_count"] == 1
    assert payload["paginated_lane_count"] == 2
    assert payload["streaming_lane_count"] == 2
    assert payload["file_output_lane_count"] == 2
    assert payload["throttled_lane_count"] == 3
    assert payload["storage_lane_count"] == 1
    assert payload["design_lane_count"] == 1
    assert payload["knowledge_lane_count"] == 1
    assert payload["live_lane_ids"] == ["google_drive", "support_desk"]
    lanes = {item["family"]: item for item in payload["lanes"]}
    assert lanes["google_drive"]["supports_listing"] is True
    assert lanes["google_drive"]["supports_export"] is True
    assert lanes["google_drive"]["supports_pagination"] is True
    assert lanes["google_drive"]["supports_streaming_output"] is True
    assert lanes["google_drive"]["supports_file_output"] is True
    assert lanes["google_drive"]["supports_throttle_controls"] is True
    assert lanes["google_drive"]["discovery_ready"] is True
    assert lanes["design_assets"]["authoritative"] is False
    assert lanes["design_assets"]["host_imported"] is True
    assert lanes["design_assets"]["supports_file_output"] is True
    assert lanes["support_desk"]["supports_search"] is True
    assert lanes["support_desk"]["supports_pagination"] is True
    assert lanes["support_desk"]["execution_ready"] is True
    assert payload["file_governance"]["ready_scanner_lanes"] == ["linux"]
    assert payload["connector_governance"]["authoritative_family_ids"] == ["google_drive", "support_desk"]


def test_external_discovery_does_not_promote_unselected_scanner_lane_to_brokered_index(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-external-discovery-unselected-scanner"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "External Discovery Unselected Scanner Demo",
            "idea": "Need external discovery to ignore scanner readiness from the wrong host.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    monkeypatch.setattr(
        "manager.service.build_project_integrations",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "No external discovery lanes are configured yet.",
            "family_count": 0,
            "blocking_reasons": [],
            "recommended_fix_values": [],
            "note_values": [],
            "families": [],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_connector_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Connector governance not configured yet.",
            "governance_status": "blocked",
            "recommended_operation_mode": "artifact_first",
            "family_count": 0,
            "connected_family_count": 0,
            "live_family_count": 0,
            "ready_family_count": 0,
            "partial_family_count": 0,
            "needs_setup_family_count": 0,
            "authoritative_family_count": 0,
            "host_imported_family_count": 0,
            "discovery_ready_family_count": 0,
            "execution_ready_family_count": 0,
            "previewable_execution_family_count": 0,
            "safe_command_family_count": 0,
            "mutating_execution_family_count": 0,
            "provider_context_verified_family_count": 0,
            "provider_count": 0,
            "providers": [],
            "category_count": 0,
            "categories": [],
            "connected_family_ids": [],
            "live_family_ids": [],
            "authoritative_family_ids": [],
            "host_imported_family_ids": [],
            "discovery_ready_family_ids": [],
            "execution_ready_family_ids": [],
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": [],
            "families": [],
            "connector_registry": {"summary": "empty", "family_count": 0, "connection_count": 0},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_file_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Scanner exists, but not on the selected broker target.",
            "recommended_operation_mode": "connector_only",
            "supports_bulk_planning": True,
            "destructive_actions_require_approval": True,
            "storage_lane_count": 1,
            "connected_storage_lane_count": 0,
            "ready_scanner_lane_count": 1,
            "storage_provider_count": 1,
            "storage_providers": ["local_fs"],
            "ready_scanner_lanes": ["linux"],
            "selected_ready_scanner_lanes": [],
            "blocking_reasons": [],
            "notes": [],
            "storage_lanes": [
                {
                    "lane_id": "local_fs",
                    "title": "Local FS",
                    "status": "connected",
                    "summary": "Local filesystem connector exists, but not on the selected broker target.",
                    "providers": ["local_fs"],
                    "provider_count": 1,
                    "host_imported": False,
                    "notes": [],
                }
            ],
            "connector_registry": {"summary": "empty"},
            "platform_runners": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "linux lane belongs to another host",
                "selected_target_id": "unknown-storage",
                "ready_lane_ids": ["linux"],
                "selected_ready_lane_ids": [],
                "target_backed_ready_lane_ids": ["linux"],
                "partial_lane_ids": [],
                "blocking_reasons": ["Selected platform target is not bound to any ready platform lane."],
                "lanes": [],
            },
            "artifact_transport": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "transport blocked on selected target binding",
                "selected_target_id": "unknown-storage",
                "selected_target_probe_status": "ready",
                "preflight_ready": False,
                "sync_enabled": False,
                "recommended_transport_mode": "blocked",
                "blocking_reasons": ["selected_target_not_bound_to_ready_platform_lane_for_transport"],
                "ready_platform_lanes": ["linux"],
                "partial_platform_lanes": [],
                "notes": [],
                "artifact_registry": {
                    "project_id": project.id,
                    "project_name": project.name,
                    "workspace_path": project.workspace_path,
                    "available": False,
                    "summary": "artifacts",
                    "artifact_count": 0,
                    "artifact_paths": [],
                    "artifact_extensions": [],
                    "artifact_extension_count": 0,
                    "artifact_kind_summaries": [],
                    "artifact_kind_counts": {},
                    "artifact_kind_count": 0,
                    "inspection_command_count": 0,
                    "inspection_commands": [],
                    "config_review_path_count": 0,
                    "config_review_paths": [],
                    "config_review_command_count": 0,
                    "config_review_commands": [],
                    "validation_evidence_target_count": 0,
                    "validation_evidence_targets": [],
                    "execution_entrypoint_count": 0,
                    "execution_entrypoints": [],
                    "notebook_path_count": 0,
                    "notebook_paths": [],
                    "recommended_next_steps": [],
                    "recommended_next_step_count": 0,
                },
                "connector_registry": {"summary": "connectors"},
                "artifact_contract": {"sync_enabled": False, "required": False},
                "connector_contract": {"available_families": [], "required_connector_families": []},
            },
        },
    )

    response = client.get(f"/api/projects/{project_id}/external-discovery/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "blocked"
    assert payload["storage_discovery_status"] == "blocked"
    assert payload["recommended_operation_mode"] == "artifact_first"
    assert payload["file_governance"]["ready_scanner_lanes"] == ["linux"]

    plan = client.post(f"/api/projects/{project_id}/external-discovery/plan")
    assert plan.status_code == 200, plan.text
    plan_payload = plan.json()
    assert plan_payload["recommended_operation_mode"] == "artifact_first"

    storage_sync_plan = json.loads(
        (workspace / "artifacts" / "external-discovery-governance" / "storage-sync-plan.json").read_text(encoding="utf-8")
    )
    assert storage_sync_plan["storage_discovery_status"] == "blocked"
    assert storage_sync_plan["ready_scanner_lanes"] == ["linux"]
    assert storage_sync_plan["selected_ready_scanner_lanes"] == []


def test_external_discovery_governance_plan_route_emits_project_manifests(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-external-discovery-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "External Discovery Plan Demo",
            "idea": "Need bounded crawler manifests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    monkeypatch.setattr(
        "manager.service.build_external_discovery_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "External discovery governance is partial.",
            "governance_status": "partial",
            "recommended_operation_mode": "connector_plus_file_graph",
            "bounded_discovery_status": "partial",
            "authoritative_connector_status": "ready",
            "read_only_status": "ready",
            "previewability_status": "ready",
            "mutation_guard_status": "ready",
            "pagination_status": "ready",
            "streaming_status": "ready",
            "file_output_status": "partial",
            "throttle_control_status": "ready",
            "storage_discovery_status": "ready",
            "design_discovery_status": "partial",
            "knowledge_discovery_status": "ready",
            "lane_count": 3,
            "authoritative_lane_count": 2,
            "live_lane_count": 2,
            "host_imported_lane_count": 1,
            "discovery_ready_lane_count": 3,
            "execution_ready_lane_count": 2,
            "previewable_lane_count": 2,
            "read_only_lane_count": 3,
            "mutating_lane_count": 1,
            "confirmation_guarded_lane_count": 1,
            "safe_command_lane_count": 1,
            "paginated_lane_count": 2,
            "streaming_lane_count": 2,
            "file_output_lane_count": 1,
            "throttled_lane_count": 2,
            "storage_lane_count": 1,
            "design_lane_count": 1,
            "knowledge_lane_count": 1,
            "live_lane_ids": ["google_drive", "support_desk"],
            "blocking_reasons": ["provider_context_missing"],
            "recommended_fixes": ["Reconnect design assets through Mission Control auth."],
            "notes": ["Preview-backed support search is available."],
            "lanes": [
                {
                    "family": "google_drive",
                    "name": "Google Drive",
                    "category": "storage",
                    "status": "partial",
                    "connection_status": "connected",
                    "connection_source": "manual",
                    "authoritative": True,
                    "host_imported": False,
                    "provider_context_verified": True,
                    "discovery_action_count": 2,
                    "preview_supported_action_count": 2,
                    "non_mutating_action_count": 2,
                    "mutating_action_count": 0,
                    "confirmation_guarded_action_count": 0,
                    "safe_command_action_count": 1,
                    "ready_to_execute_action_count": 2,
                    "supports_search": False,
                    "supports_listing": True,
                    "supports_export": True,
                    "supports_pagination": True,
                    "supports_streaming_output": True,
                    "supports_file_output": True,
                    "supports_throttle_controls": True,
                    "discovery_ready": True,
                    "execution_ready": True,
                    "blockers": [],
                    "recommended_fixes": [],
                    "notes": [],
                },
                {
                    "family": "design_assets",
                    "name": "Design Assets",
                    "category": "design",
                    "status": "partial",
                    "connection_status": "host_detected",
                    "connection_source": "codex_host",
                    "authoritative": False,
                    "host_imported": True,
                    "provider_context_verified": False,
                    "discovery_action_count": 1,
                    "preview_supported_action_count": 0,
                    "non_mutating_action_count": 1,
                    "mutating_action_count": 0,
                    "confirmation_guarded_action_count": 0,
                    "safe_command_action_count": 0,
                    "ready_to_execute_action_count": 0,
                    "supports_search": False,
                    "supports_listing": False,
                    "supports_export": True,
                    "supports_pagination": False,
                    "supports_streaming_output": False,
                    "supports_file_output": True,
                    "supports_throttle_controls": True,
                    "discovery_ready": True,
                    "execution_ready": False,
                    "blockers": ["provider_context_missing"],
                    "recommended_fixes": ["Reconnect Figma."],
                    "notes": [],
                },
                {
                    "family": "support_desk",
                    "name": "Support Desk",
                    "category": "support",
                    "status": "ready",
                    "connection_status": "connected",
                    "connection_source": "manual",
                    "authoritative": True,
                    "host_imported": False,
                    "provider_context_verified": True,
                    "discovery_action_count": 2,
                    "preview_supported_action_count": 1,
                    "non_mutating_action_count": 1,
                    "mutating_action_count": 1,
                    "confirmation_guarded_action_count": 1,
                    "safe_command_action_count": 0,
                    "ready_to_execute_action_count": 1,
                    "supports_search": True,
                    "supports_listing": True,
                    "supports_export": False,
                    "supports_pagination": True,
                    "supports_streaming_output": True,
                    "supports_file_output": False,
                    "supports_throttle_controls": True,
                    "discovery_ready": True,
                    "execution_ready": True,
                    "blockers": [],
                    "recommended_fixes": [],
                    "notes": [],
                },
            ],
            "connector_governance": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "Connector governance ready enough.",
                "governance_status": "partial",
                "recommended_operation_mode": "governed_connector_actions",
                "family_count": 3,
                "connected_family_count": 3,
                "live_family_count": 2,
                "ready_family_count": 1,
                "partial_family_count": 2,
                "needs_setup_family_count": 0,
                "authoritative_family_count": 2,
                "host_imported_family_count": 1,
                "discovery_ready_family_count": 3,
                "execution_ready_family_count": 2,
                "previewable_execution_family_count": 2,
                "safe_command_family_count": 1,
                "mutating_execution_family_count": 1,
                "provider_context_verified_family_count": 2,
                "provider_count": 3,
                "providers": ["google_drive", "figma", "zendesk"],
                "category_count": 3,
                "categories": ["storage", "design", "support"],
                "connected_family_ids": ["google_drive", "design_assets", "support_desk"],
                "live_family_ids": ["google_drive", "support_desk"],
                "authoritative_family_ids": ["google_drive", "support_desk"],
                "host_imported_family_ids": ["design_assets"],
                "discovery_ready_family_ids": ["google_drive", "design_assets", "support_desk"],
                "execution_ready_family_ids": ["google_drive", "support_desk"],
                "blocking_reasons": ["provider_context_missing"],
                "recommended_fixes": ["Reconnect design assets through Mission Control auth."],
                "notes": [],
                "families": [],
                "connector_registry": {
                    "summary": "Three lanes visible.",
                    "family_count": 3,
                    "connection_count": 3,
                    "authoritative_connection_count": 2,
                    "host_imported_count": 1,
                    "status_counts": {"connected": 2, "host_detected": 1},
                    "host_import_roots": {},
                    "recent_action_failures": [],
                    "ready_family_count": 2,
                    "ready_families": ["google_drive", "support_desk"],
                    "provider_counts": {"google_drive": 1, "figma": 1, "zendesk": 1},
                    "provider_count": 3,
                    "category_counts": {"storage": 1, "design": 1, "support": 1},
                    "category_count": 3,
                    "connection_source_counts": {"manual": 2, "codex_host": 1},
                    "connection_source_count": 2,
                    "available_action_count": 5,
                    "catalog": [],
                    "connections": [],
                },
            },
            "file_governance": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "File governance ready.",
                "recommended_operation_mode": "hybrid_connector_sync",
                "supports_bulk_planning": True,
                "destructive_actions_require_approval": True,
                "storage_lane_count": 1,
                "connected_storage_lane_count": 1,
                "ready_scanner_lane_count": 1,
                "storage_provider_count": 2,
                "storage_providers": ["local_fs", "google_drive"],
                "ready_scanner_lanes": ["linux"],
                "blocking_reasons": [],
                "notes": [],
                "storage_lanes": [{"lane_id": "local_fs", "title": "Local FS", "status": "connected"}],
                "connector_registry": {"summary": "ready", "family_count": 1, "connection_count": 1, "authoritative_connection_count": 1, "host_imported_count": 0, "status_counts": {"connected": 1}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 1, "ready_families": ["storage"], "provider_counts": {"local_fs": 1}, "provider_count": 1, "category_counts": {"storage": 1}, "category_count": 1, "connection_source_counts": {"mission_control": 1}, "connection_source_count": 1, "available_action_count": 1, "catalog": [], "connections": []},
                "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": "linux", "lane_count": 1, "ready_lane_count": 1, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": ["linux"], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
                "artifact_transport": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": "linux", "preflight_ready": True, "sync_enabled": True, "recommended_transport_mode": "brokered_sync", "blocking_reasons": [], "ready_platform_lanes": ["linux"], "partial_platform_lanes": [], "notes": [], "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "stub", "artifact_count": 1, "artifact_paths": ["data/train.parquet"], "artifact_extensions": [".parquet"], "artifact_extension_count": 1, "artifact_kind_summaries": ["dataset:1"], "artifact_kind_counts": {"dataset": 1}, "artifact_kind_count": 1, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 1, "validation_evidence_targets": ["data/train.parquet"], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []}, "connector_registry": {"summary": "ready"}, "artifact_contract": {"sync_enabled": True}, "connector_contract": {"available_families": ["storage"]}},
            },
        },
    )

    plan = client.post(f"/api/projects/{project_id}/external-discovery/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["recommended_operation_mode"] == "connector_plus_file_graph"
    assert payload["lane_count"] == 3
    assert payload["discovery_ready_lane_count"] == 3
    assert payload["authoritative_lane_count"] == 2
    assert payload["manifest_root"] == "artifacts/external-discovery-governance"
    assert payload["lane_inventory_path"] == "artifacts/external-discovery-governance/lane-inventory.json"
    assert payload["bounded_crawl_plan_path"] == "artifacts/external-discovery-governance/bounded-crawl-plan.json"
    assert payload["storage_sync_plan_path"] == "artifacts/external-discovery-governance/storage-sync-plan.json"
    assert payload["connector_contract_path"] == "artifacts/external-discovery-governance/connector-contract.json"
    assert payload["approval_checkpoint_path"] == "artifacts/external-discovery-governance/approval-checkpoints.json"
    assert (workspace / "artifacts" / "external-discovery-governance" / "lane-inventory.json").exists()
    assert (workspace / "artifacts" / "external-discovery-governance" / "bounded-crawl-plan.json").exists()
    assert (workspace / "artifacts" / "external-discovery-governance" / "storage-sync-plan.json").exists()
    assert (workspace / "artifacts" / "external-discovery-governance" / "connector-contract.json").exists()
    assert (workspace / "artifacts" / "external-discovery-governance" / "approval-checkpoints.json").exists()


def test_project_integrations_route_surfaces_storage_and_design_discovery_action_metadata(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-discovery-families"
    workspace.mkdir()
    (workspace / "README.md").write_text(
        "This repo syncs Google Drive exports and Figma design tokens.\n",
        encoding="utf-8",
    )

    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive"],
                "connection_source": "manual",
                "host_imported": False,
                "notes": [],
            },
            "design_assets": {
                "family": "design_assets",
                "status": "host_detected",
                "providers": ["figma"],
                "connection_source": "codex_host",
                "host_imported": True,
                "notes": [],
            },
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "rclone" else None,
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Discovery Families Demo",
            "idea": "Need real storage and design discovery lanes.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    integrations = client.get(f"/api/projects/{project_id}/integrations")
    assert integrations.status_code == 200, integrations.text
    integrations_payload = integrations.json()
    assert integrations_payload["attached_family_count"] == 2
    assert integrations_payload["attached_family_ids"] == ["cloud_storage", "design_assets"]
    assert integrations_payload["authoritative_family_count"] == 1
    assert integrations_payload["authoritative_family_ids"] == ["cloud_storage"]
    assert integrations_payload["status_family_counts"]["ready"] == len(integrations_payload["status_family_ids"]["ready"])
    assert integrations_payload["connection_source_family_counts"]["manual"] == len(
        integrations_payload["connection_source_family_ids"]["manual"]
    )
    assert integrations_payload["action_status_family_counts"]["available"] == len(
        integrations_payload["action_status_family_ids"]["available"]
    )
    for group_key, ids in integrations_payload["available_action_status_family_ids"].items():
        assert integrations_payload["available_action_status_family_counts"][group_key] == len(ids)
    for group_key, ids in integrations_payload["execution_mode_family_ids"].items():
        assert integrations_payload["execution_mode_family_counts"][group_key] == len(ids)
    assert integrations_payload["paginated_action_family_count"] == 4
    assert integrations_payload["paginated_action_family_ids"] == [
        "cloud_storage",
        "design_assets",
        "code_search",
        "support_desk",
    ]
    assert integrations_payload["paginated_action_count"] == 5
    assert integrations_payload["paginated_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "design_assets:list",
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["streaming_action_family_count"] == 4
    assert integrations_payload["streaming_action_family_ids"] == [
        "cloud_storage",
        "design_assets",
        "code_search",
        "support_desk",
    ]
    assert integrations_payload["streaming_action_count"] == 5
    assert integrations_payload["streaming_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "design_assets:list",
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["file_output_action_family_count"] == 2
    assert integrations_payload["file_output_action_family_ids"] == ["cloud_storage", "design_assets"]
    assert integrations_payload["file_output_action_count"] == 2
    assert integrations_payload["file_output_action_refs"] == [
        "cloud_storage:export",
        "design_assets:export",
    ]
    assert integrations_payload["throttle_control_action_family_count"] == 4
    assert integrations_payload["throttle_control_action_family_ids"] == [
        "cloud_storage",
        "design_assets",
        "code_search",
        "support_desk",
    ]
    assert integrations_payload["throttle_control_action_count"] == 7
    assert integrations_payload["throttle_control_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "cloud_storage:export",
        "cloud_storage:archive",
        "design_assets:export",
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["attached_paginated_action_family_count"] == 2
    assert integrations_payload["attached_paginated_action_family_ids"] == ["cloud_storage", "design_assets"]
    assert integrations_payload["attached_paginated_action_count"] == 3
    assert integrations_payload["attached_paginated_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "design_assets:list",
    ]
    assert integrations_payload["attached_streaming_action_family_count"] == 2
    assert integrations_payload["attached_streaming_action_family_ids"] == ["cloud_storage", "design_assets"]
    assert integrations_payload["attached_streaming_action_count"] == 3
    assert integrations_payload["attached_streaming_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "design_assets:list",
    ]
    assert integrations_payload["attached_file_output_action_family_count"] == 2
    assert integrations_payload["attached_file_output_action_family_ids"] == ["cloud_storage", "design_assets"]
    assert integrations_payload["attached_file_output_action_count"] == 2
    assert integrations_payload["attached_file_output_action_refs"] == [
        "cloud_storage:export",
        "design_assets:export",
    ]
    assert integrations_payload["attached_throttle_control_action_family_count"] == 2
    assert integrations_payload["attached_throttle_control_action_family_ids"] == ["cloud_storage", "design_assets"]
    assert integrations_payload["attached_throttle_control_action_count"] == 5
    assert integrations_payload["attached_throttle_control_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "cloud_storage:export",
        "cloud_storage:archive",
        "design_assets:export",
    ]
    assert integrations_payload["connected_paginated_action_family_count"] == 1
    assert integrations_payload["connected_paginated_action_family_ids"] == ["cloud_storage"]
    assert integrations_payload["connected_paginated_action_count"] == 2
    assert integrations_payload["connected_paginated_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
    ]
    assert integrations_payload["connected_streaming_action_family_count"] == 1
    assert integrations_payload["connected_streaming_action_family_ids"] == ["cloud_storage"]
    assert integrations_payload["connected_streaming_action_count"] == 2
    assert integrations_payload["connected_streaming_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
    ]
    assert integrations_payload["connected_file_output_action_family_count"] == 1
    assert integrations_payload["connected_file_output_action_family_ids"] == ["cloud_storage"]
    assert integrations_payload["connected_file_output_action_count"] == 1
    assert integrations_payload["connected_file_output_action_refs"] == [
        "cloud_storage:export",
    ]
    assert integrations_payload["connected_throttle_control_action_family_count"] == 1
    assert integrations_payload["connected_throttle_control_action_family_ids"] == ["cloud_storage"]
    assert integrations_payload["connected_throttle_control_action_count"] == 4
    assert integrations_payload["connected_throttle_control_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "cloud_storage:export",
        "cloud_storage:archive",
    ]
    assert integrations_payload["authoritative_paginated_action_family_count"] == 1
    assert integrations_payload["authoritative_paginated_action_family_ids"] == ["cloud_storage"]
    assert integrations_payload["authoritative_paginated_action_count"] == 2
    assert integrations_payload["authoritative_paginated_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
    ]
    assert integrations_payload["authoritative_streaming_action_family_count"] == 1
    assert integrations_payload["authoritative_streaming_action_family_ids"] == ["cloud_storage"]
    assert integrations_payload["authoritative_streaming_action_count"] == 2
    assert integrations_payload["authoritative_streaming_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
    ]
    assert integrations_payload["authoritative_file_output_action_family_count"] == 1
    assert integrations_payload["authoritative_file_output_action_family_ids"] == ["cloud_storage"]
    assert integrations_payload["authoritative_file_output_action_count"] == 1
    assert integrations_payload["authoritative_file_output_action_refs"] == [
        "cloud_storage:export",
    ]
    assert integrations_payload["authoritative_throttle_control_action_family_count"] == 1
    assert integrations_payload["authoritative_throttle_control_action_family_ids"] == ["cloud_storage"]
    assert integrations_payload["authoritative_throttle_control_action_count"] == 4
    assert integrations_payload["authoritative_throttle_control_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "cloud_storage:export",
        "cloud_storage:archive",
    ]
    families = {item["family"]: item for item in integrations_payload["families"]}
    assert "cloud_storage" in families
    assert "design_assets" in families

    storage_family = client.get(f"/api/projects/{project_id}/integrations/cloud_storage")
    assert storage_family.status_code == 200, storage_family.text
    storage_payload = storage_family.json()
    storage_actions = {item["action_id"]: item for item in storage_payload["available_actions"]}
    assert storage_actions["search"]["supports_pagination"] is True
    assert storage_actions["search"]["supports_streaming_output"] is True
    assert storage_actions["search"]["supports_throttle_controls"] is True
    assert storage_actions["list"]["supports_pagination"] is True
    assert storage_actions["export"]["supports_file_output"] is True

    design_family = client.get(f"/api/projects/{project_id}/integrations/design_assets")
    assert design_family.status_code == 200, design_family.text
    design_payload = design_family.json()
    design_actions = {item["action_id"]: item for item in design_payload["available_actions"]}
    assert design_actions["list"]["supports_pagination"] is True
    assert design_actions["list"]["supports_streaming_output"] is True
    assert design_actions["export"]["supports_file_output"] is True
    assert design_payload["host_imported"] is True

    preview = client.post(
        f"/api/projects/{project_id}/integrations/cloud_storage/actions/search/preview",
        json={"params": {"query": "renders"}},
    )
    assert preview.status_code == 200, preview.text
    preview_payload = preview.json()
    assert preview_payload["supports_pagination"] is True
    assert preview_payload["supports_streaming_output"] is True
    assert preview_payload["supports_throttle_controls"] is True


def test_project_integrations_route_surfaces_code_and_support_search_contract_metadata(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-search-families"
    workspace.mkdir()
    (workspace / "README.md").write_text(
        "This repo uses Sourcegraph search and Zendesk support workflows.\n",
        encoding="utf-8",
    )

    normalized_registry = {
        "connections": {
            "code_search": {
                "family": "code_search",
                "status": "connected",
                "providers": ["sourcegraph"],
                "connection_source": "manual",
                "host_imported": False,
                "notes": [],
            },
            "support_desk": {
                "family": "support_desk",
                "status": "connected",
                "providers": ["zendesk"],
                "connection_source": "manual",
                "host_imported": False,
                "notes": [],
            },
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)

    create = client.post(
        "/api/projects",
        json={
            "name": "Search Families Demo",
            "idea": "Need real search-lane crawler contracts.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    integrations = client.get(f"/api/projects/{project_id}/integrations")
    assert integrations.status_code == 200, integrations.text
    integrations_payload = integrations.json()
    assert integrations_payload["attached_family_count"] == 2
    assert integrations_payload["attached_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["authoritative_family_count"] == 2
    assert integrations_payload["authoritative_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["status_family_counts"]["ready"] == len(integrations_payload["status_family_ids"]["ready"])
    assert integrations_payload["connection_source_family_counts"]["manual"] == len(
        integrations_payload["connection_source_family_ids"]["manual"]
    )
    assert integrations_payload["action_status_family_counts"]["available"] == len(
        integrations_payload["action_status_family_ids"]["available"]
    )
    for group_key, ids in integrations_payload["available_action_status_family_ids"].items():
        assert integrations_payload["available_action_status_family_counts"][group_key] == len(ids)
    for group_key, ids in integrations_payload["execution_mode_family_ids"].items():
        assert integrations_payload["execution_mode_family_counts"][group_key] == len(ids)
    assert integrations_payload["paginated_action_family_count"] == 4
    assert integrations_payload["paginated_action_family_ids"] == [
        "cloud_storage",
        "design_assets",
        "code_search",
        "support_desk",
    ]
    assert integrations_payload["paginated_action_count"] == 5
    assert integrations_payload["paginated_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "design_assets:list",
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["streaming_action_family_count"] == 4
    assert integrations_payload["streaming_action_family_ids"] == [
        "cloud_storage",
        "design_assets",
        "code_search",
        "support_desk",
    ]
    assert integrations_payload["streaming_action_count"] == 5
    assert integrations_payload["streaming_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "design_assets:list",
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["file_output_action_family_count"] == 2
    assert integrations_payload["file_output_action_family_ids"] == ["cloud_storage", "design_assets"]
    assert integrations_payload["file_output_action_count"] == 2
    assert integrations_payload["file_output_action_refs"] == [
        "cloud_storage:export",
        "design_assets:export",
    ]
    assert integrations_payload["throttle_control_action_family_count"] == 4
    assert integrations_payload["throttle_control_action_family_ids"] == [
        "cloud_storage",
        "design_assets",
        "code_search",
        "support_desk",
    ]
    assert integrations_payload["throttle_control_action_count"] == 7
    assert integrations_payload["throttle_control_action_refs"] == [
        "cloud_storage:search",
        "cloud_storage:list",
        "cloud_storage:export",
        "cloud_storage:archive",
        "design_assets:export",
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["attached_paginated_action_family_count"] == 2
    assert integrations_payload["attached_paginated_action_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["attached_paginated_action_count"] == 2
    assert integrations_payload["attached_paginated_action_refs"] == [
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["attached_streaming_action_family_count"] == 2
    assert integrations_payload["attached_streaming_action_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["attached_streaming_action_count"] == 2
    assert integrations_payload["attached_streaming_action_refs"] == [
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["attached_file_output_action_family_count"] == 0
    assert integrations_payload["attached_file_output_action_family_ids"] == []
    assert integrations_payload["attached_file_output_action_count"] == 0
    assert integrations_payload["attached_file_output_action_refs"] == []
    assert integrations_payload["attached_throttle_control_action_family_count"] == 2
    assert integrations_payload["attached_throttle_control_action_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["attached_throttle_control_action_count"] == 2
    assert integrations_payload["attached_throttle_control_action_refs"] == [
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["connected_paginated_action_family_count"] == 2
    assert integrations_payload["connected_paginated_action_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["connected_paginated_action_count"] == 2
    assert integrations_payload["connected_paginated_action_refs"] == [
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["connected_streaming_action_family_count"] == 2
    assert integrations_payload["connected_streaming_action_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["connected_streaming_action_count"] == 2
    assert integrations_payload["connected_streaming_action_refs"] == [
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["connected_file_output_action_family_count"] == 0
    assert integrations_payload["connected_file_output_action_family_ids"] == []
    assert integrations_payload["connected_file_output_action_count"] == 0
    assert integrations_payload["connected_file_output_action_refs"] == []
    assert integrations_payload["connected_throttle_control_action_family_count"] == 2
    assert integrations_payload["connected_throttle_control_action_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["connected_throttle_control_action_count"] == 2
    assert integrations_payload["connected_throttle_control_action_refs"] == [
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["authoritative_paginated_action_family_count"] == 2
    assert integrations_payload["authoritative_paginated_action_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["authoritative_paginated_action_count"] == 2
    assert integrations_payload["authoritative_paginated_action_refs"] == [
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["authoritative_streaming_action_family_count"] == 2
    assert integrations_payload["authoritative_streaming_action_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["authoritative_streaming_action_count"] == 2
    assert integrations_payload["authoritative_streaming_action_refs"] == [
        "code_search:search",
        "support_desk:search",
    ]
    assert integrations_payload["authoritative_file_output_action_family_count"] == 0
    assert integrations_payload["authoritative_file_output_action_family_ids"] == []
    assert integrations_payload["authoritative_file_output_action_count"] == 0
    assert integrations_payload["authoritative_file_output_action_refs"] == []
    assert integrations_payload["authoritative_throttle_control_action_family_count"] == 2
    assert integrations_payload["authoritative_throttle_control_action_family_ids"] == ["code_search", "support_desk"]
    assert integrations_payload["authoritative_throttle_control_action_count"] == 2
    assert integrations_payload["authoritative_throttle_control_action_refs"] == [
        "code_search:search",
        "support_desk:search",
    ]

    code_search_family = client.get(f"/api/projects/{project_id}/integrations/code_search")
    assert code_search_family.status_code == 200, code_search_family.text
    code_payload = code_search_family.json()
    code_actions = {item["action_id"]: item for item in code_payload["available_actions"]}
    assert code_actions["search"]["supports_pagination"] is True
    assert code_actions["search"]["supports_streaming_output"] is True
    assert code_actions["search"]["supports_throttle_controls"] is True

    support_family = client.get(f"/api/projects/{project_id}/integrations/support_desk")
    assert support_family.status_code == 200, support_family.text
    support_payload = support_family.json()
    support_actions = {item["action_id"]: item for item in support_payload["available_actions"]}
    assert support_actions["search"]["supports_pagination"] is True
    assert support_actions["search"]["supports_streaming_output"] is True
    assert support_actions["search"]["supports_throttle_controls"] is True
    assert support_actions["create"]["supports_pagination"] is False

    preview = client.post(
        f"/api/projects/{project_id}/integrations/support_desk/actions/search/preview",
        json={"params": {}},
    )
    assert preview.status_code == 200, preview.text
    preview_payload = preview.json()
    assert preview_payload["supports_pagination"] is True
    assert preview_payload["supports_streaming_output"] is True
    assert preview_payload["supports_throttle_controls"] is True


def test_host_capability_index_summary_route_surfaces_project_matched_and_rejected_targets(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    normalized_registry = {
        "connections": {
            "source_control": {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": [],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-host-capability-index"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Host Capability Index Demo",
            "idea": "Need contract-aware host selection.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    ready_target = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "gpu-linux",
            "label": "GPU Linux",
            "transport": "ssh",
            "host": "gpu-linux.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "tags": ["gpu", "priority"],
            "toolchains": ["cuda12", "python3.11"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "max_command_runtime_seconds": 3600,
            "file_transfer_quota_mb": 4096,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert ready_target.status_code == 200, ready_target.text

    rejected_target = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "limited-macos",
            "label": "Limited macOS",
            "transport": "ssh",
            "host": "limited-macos.local",
            "ssh_user": "mike",
            "os_family": "macos",
            "workspace_root": "/Users/mike/builds",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python"],
            "toolchains": ["python3.11"],
            "command_families": ["python"],
            "result_formats": ["text"],
            "session_recording_enabled": False,
            "allowed_repo_roots": ["/Users/mike/builds"],
            "allowed_path_prefixes": ["tmp"],
            "artifact_roots": ["/Users/mike/builds/out"],
            "connector_families": [],
            "trust_level": "limited",
            "last_probe_status": "ready",
        },
    )
    assert rejected_target.status_code == 200, rejected_target.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "gpu-linux",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "required_connector_families": ["source_control"],
            "require_session_recording": True,
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/host-capability-index/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["project_id"] == project_id
    assert payload["selection_status"] == "ready"
    assert payload["selected_target_id"] == "gpu-linux"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["selected_target_status"] == "ready"
    assert payload["required_runner_family"] == "external_adapter"
    assert payload["target_count"] == 2
    assert payload["ready_target_count"] == 2
    assert payload["eligible_target_count"] == 1
    assert payload["ready_candidate_count"] == 1
    assert payload["ready_candidate_ids"] == ["gpu-linux"]
    assert payload["rejected_target_count"] == 1
    assert payload["recommended_target_ids"] == ["gpu-linux"]
    assert payload["rejected_target_ids"] == ["limited-macos"]
    assert payload["allowed_trust_levels"] == ["trusted"]
    assert payload["required_toolchains"] == ["cuda12"]
    assert payload["required_command_families"] == ["git"]
    assert payload["required_result_formats"] == ["json"]
    assert payload["required_connector_families"] == ["source_control"]
    matches = {item["target_id"]: item for item in payload["matches"]}
    assert matches["gpu-linux"]["status"] == "ready"
    assert matches["gpu-linux"]["selected"] is True
    assert matches["gpu-linux"]["runner_families"] == ["external_adapter"]
    assert matches["gpu-linux"]["capabilities"] == ["python", "gpu"]
    assert matches["gpu-linux"]["tags"] == ["gpu", "priority"]
    assert matches["gpu-linux"]["adapter_command"] == "python3"
    assert matches["gpu-linux"]["session_recording_enabled"] is True
    assert matches["gpu-linux"]["max_command_runtime_seconds"] == 3600
    assert matches["gpu-linux"]["file_transfer_quota_mb"] == 4096
    assert matches["limited-macos"]["status"] == "blocked"
    assert matches["limited-macos"]["selected"] is False
    assert matches["limited-macos"]["rejected_reasons"]
    assert matches["limited-macos"]["requirement_gaps"]["trust_levels"] == ["trusted"]
    assert matches["limited-macos"]["requirement_gaps"]["toolchains"] == ["cuda12"]
    assert matches["limited-macos"]["requirement_gaps"]["command_families"] == ["git"]


def test_remote_broker_and_host_capability_summaries_do_not_recommend_unknown_probe_targets(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    workspace = tmp_path / "workspace-unknown-probe-target"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Unknown Probe Target Demo",
            "idea": "Need broker summaries to avoid recommending unverified targets.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "unknown-box",
            "label": "Unknown Box",
            "transport": "ssh",
            "host": "unknown-box.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python"],
            "toolchains": ["python3.11"],
            "command_families": ["python"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": [],
            "trust_level": "trusted",
            "last_probe_status": "unknown",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "unknown-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    broker_summary = client.get(f"/api/projects/{project_id}/device-broker/summary")
    assert broker_summary.status_code == 200, broker_summary.text
    broker_payload = broker_summary.json()
    assert broker_payload["preflight_ready"] is False
    assert broker_payload["selected_target_id"] == "unknown-box"
    assert broker_payload["selected_target_probe_status"] == "unknown"
    assert broker_payload["ready_candidate_count"] == 0
    assert broker_payload["ready_candidate_ids"] == []
    assert broker_payload["ready_target_count"] == 0
    assert broker_payload["recommended_target_ids"] == []
    assert "selected_target_probe_unverified" in broker_payload["blocking_reasons"]
    assert (
        broker_payload["availability_diagnostics"]["summary"]
        == "A broker target matched `device broker request`, but its transport or probe status is still unverified."
    )
    assert broker_payload["availability_diagnostics"]["notes"] == []

    capability_summary = client.get(f"/api/projects/{project_id}/host-capability-index/summary")
    assert capability_summary.status_code == 200, capability_summary.text
    capability_payload = capability_summary.json()
    assert capability_payload["selection_status"] == "partial"
    assert capability_payload["selected_target_id"] == "unknown-box"
    assert capability_payload["selected_target_probe_status"] == "unknown"
    assert capability_payload["selected_target_status"] == "partial"
    assert capability_payload["ready_target_count"] == 0
    assert capability_payload["eligible_target_count"] == 1
    assert capability_payload["ready_candidate_count"] == 0
    assert capability_payload["ready_candidate_ids"] == []
    assert capability_payload["recommended_target_ids"] == []
    assert "selected_target_probe_unverified" in capability_payload["blocking_reasons"]

    selection = client.get(f"/api/projects/{project_id}/remote-execution/resolve")
    assert selection.status_code == 200, selection.text
    selection_payload = selection.json()
    assert selection_payload["selected_target_id"] == "unknown-box"
    assert selection_payload["selected_target_probe_status"] == "unknown"
    assert selection_payload["eligible_target_count"] == 1
    assert selection_payload["ready_candidate_count"] == 0
    assert selection_payload["ready_candidate_ids"] == []
    assert selection_payload["preflight_ready"] is False
    assert "selected_target_probe_unverified" in selection_payload["blocking_reasons"]


def test_remote_runner_summary_route_surfaces_adapter_family_readiness(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Workspace tooling is available locally.",
            "tools": [],
            "packs": [],
            "artifact_paths": [],
            "artifact_kind_summaries": [],
            "artifact_inspection_commands": [],
            "config_review_paths": [],
            "config_review_commands": [],
            "validation_evidence_targets": [],
            "execution_entrypoints": ["python run_local_checks.py"],
            "notebook_paths": [],
            "recommended_next_steps": [],
            "product_lane_statuses": ["browser:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": [],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
        },
    )
    normalized_registry = {
        "connections": {
            "source_control": {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": [],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-remote-runner-summary"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Runner Summary Demo",
            "idea": "Need a transport-aware runner summary.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    for host_payload in (
        {
            "id": "tailnet-win",
            "label": "Tailnet Windows",
            "transport": "tailscale_ssh",
            "host": "tailnet-win.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "windows",
            "workspace_root": "C:/shadow",
            "adapter_command": "python.exe",
            "runner_families": ["external_adapter"],
            "capabilities": ["unity", "windows_build"],
            "toolchains": ["unity6000", "vs2022"],
            "command_families": ["powershell", "unity_batchmode"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["C:/shadow"],
            "allowed_path_prefixes": ["src", "Assets"],
            "artifact_roots": ["C:/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
        {
            "id": "lan-mac",
            "label": "LAN Mac",
            "transport": "lan_ssh",
            "host": "lan-mac.local",
            "ssh_user": "mike",
            "os_family": "macos",
            "workspace_root": "/Users/mike/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["ios"],
            "toolchains": ["xcode15", "simctl"],
            "command_families": ["xcodebuild", "simctl"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/Users/mike/shadow"],
            "allowed_path_prefixes": ["src", "ios"],
            "artifact_roots": ["/Users/mike/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
        {
            "id": "plain-linux",
            "label": "Plain Linux",
            "transport": "ssh",
            "host": "plain-linux.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python"],
            "toolchains": ["python3.11"],
            "command_families": ["python"],
            "result_formats": ["text"],
            "session_recording_enabled": False,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["tmp"],
            "artifact_roots": ["/srv/shadow/out"],
            "connector_families": [],
            "trust_level": "limited",
            "last_probe_status": "ready",
        },
    ):
        upsert = client.put("/api/system/remote-execution/hosts", json=host_payload)
        assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "tailnet-win",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_command_families": ["unity_batchmode"],
            "required_result_formats": ["json"],
            "required_connector_families": ["source_control"],
            "require_session_recording": True,
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/remote-runners/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["project_id"] == project_id
    assert payload["selected_target_id"] == "tailnet-win"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["ready_candidate_count"] == 1
    assert payload["ready_candidate_ids"] == ["tailnet-win"]
    assert payload["required_runner_family"] == "external_adapter"
    assert payload["route_count"] == 6
    assert payload["ready_route_count"] == 3
    assert payload["remote_ready_route_count"] == 2
    assert payload["remote_contract_ready_route_count"] == 2
    assert payload["selected_ready_route_ids"] == ["tailscale_ssh", "windows_host"]
    assert payload["selected_contract_ready_route_ids"] == ["tailscale_ssh", "windows_host"]
    assert payload["adapter_count"] == 6
    assert "local_workspace" in payload["ready_adapter_ids"]
    assert "tailscale_ssh" in payload["ready_adapter_ids"]
    assert "windows_host" in payload["ready_adapter_ids"]
    assert payload["remote_ready_adapter_count"] == 2
    assert payload["remote_contract_ready_adapter_count"] == 2
    assert payload["remote_ready_adapter_ids"] == ["tailscale_ssh", "windows_host"]
    assert payload["remote_contract_ready_adapter_ids"] == ["tailscale_ssh", "windows_host"]
    assert payload["selected_ready_adapter_ids"] == ["tailscale_ssh", "windows_host"]
    assert payload["selected_contract_ready_adapter_ids"] == ["tailscale_ssh", "windows_host"]
    assert "lan_appliance" in payload["partial_adapter_ids"]
    assert "plain_ssh" in payload["partial_adapter_ids"]
    assert payload["runner_family_count"] >= 3
    assert "external_adapter" in payload["ready_runner_family_ids"]
    assert "tailscale_ssh_runner" in payload["ready_runner_family_ids"]
    assert "windows_agent_runner" in payload["ready_runner_family_ids"]
    assert payload["remote_ready_runner_family_count"] >= 3
    assert "tailscale_ssh_runner" in payload["remote_contract_ready_runner_family_ids"]
    assert "windows_agent_runner" in payload["remote_contract_ready_runner_family_ids"]
    assert "tailscale_ssh_runner" in payload["selected_ready_runner_family_ids"]
    assert "windows_agent_runner" in payload["selected_contract_ready_runner_family_ids"]
    routes = {item["route_id"]: item for item in payload["routes"]}
    assert routes["tailscale_ssh"]["selected_target_ids"] == ["tailnet-win"]
    assert routes["tailscale_ssh"]["status"] == "ready"
    assert "tailscale_ssh_runner" in routes["tailscale_ssh"]["runner_families"]
    assert routes["plain_ssh"]["status"] == "partial"
    adapters = {item["adapter_id"]: item for item in payload["adapters"]}
    assert adapters["tailscale_ssh"]["selected_target_ids"] == ["tailnet-win"]
    assert adapters["tailscale_ssh"]["status"] == "ready"
    assert "tailscale_ssh_runner" in adapters["tailscale_ssh"]["runner_families"]
    assert adapters["tailscale_ssh"]["session_recording_coverage"] == "ready"
    assert adapters["tailscale_ssh"]["selected_session_recording_coverage"] == "ready"
    assert adapters["tailscale_ssh"]["selected_result_format_coverage"] == "ready"
    assert adapters["tailscale_ssh"]["selected_command_family_coverage"] == "ready"
    assert adapters["tailscale_ssh"]["selected_contract_ready"] is True
    assert adapters["plain_ssh"]["status"] == "partial"
    assert adapters["plain_ssh"]["session_recording_coverage"] == "partial"
    assert adapters["plain_ssh"]["result_format_coverage"] == "blocked"
    assert adapters["plain_ssh"]["command_family_coverage"] == "blocked"
    assert adapters["lan_appliance"]["status"] == "partial"
    assert adapters["lan_appliance"]["session_recording_coverage"] == "partial"
    assert adapters["macos_host"]["status"] == "partial"
    assert adapters["macos_host"]["session_recording_coverage"] == "partial"
    runner_families = {item["runner_family_id"]: item for item in payload["runner_families"]}
    assert runner_families["tailscale_ssh_runner"]["selected_target_ids"] == ["tailnet-win"]
    assert runner_families["tailscale_ssh_runner"]["status"] == "ready"
    assert runner_families["windows_agent_runner"]["status"] == "ready"
    assert "tailscale_ssh" in runner_families["tailscale_ssh_runner"]["transports"]
    assert runner_families["plain_ssh_runner"]["status"] == "partial"


def test_remote_runner_plan_route_does_not_treat_local_fallback_as_remote_readiness(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Workspace tooling is available locally.",
            "tools": [],
            "packs": [],
            "artifact_paths": [],
            "artifact_kind_summaries": [],
            "artifact_inspection_commands": [],
            "config_review_paths": [],
            "config_review_commands": [],
            "validation_evidence_targets": [],
            "execution_entrypoints": ["python run_local_checks.py"],
            "notebook_paths": [],
            "recommended_next_steps": [],
            "product_lane_statuses": ["browser:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": [],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
        },
    )
    workspace = tmp_path / "workspace-remote-runner-local-fallback"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Runner Local Fallback Demo",
            "idea": "Need remote runner plans to reject fake readiness from local tooling.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "plain-linux",
            "label": "Plain Linux",
            "transport": "ssh",
            "host": "plain-linux.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python"],
            "toolchains": ["python3.11"],
            "command_families": ["python"],
            "result_formats": ["text"],
            "session_recording_enabled": False,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["src"],
            "artifact_roots": ["/srv/shadow/out"],
            "connector_families": [],
            "trust_level": "trusted",
            "last_probe_status": "unknown",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "plain-linux",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/remote-runners/summary")
    assert summary.status_code == 200, summary.text
    summary_payload = summary.json()
    assert summary_payload["selected_target_id"] == "plain-linux"
    assert summary_payload["selected_target_probe_status"] == "unknown"
    assert "local_workspace" in summary_payload["ready_adapter_ids"]
    assert "Selected target is not bound to a contract-ready remote runner family." in summary_payload["blocking_reasons"]

    plan = client.post(f"/api/projects/{project_id}/remote-runners/plan")
    assert plan.status_code == 200, plan.text
    plan_payload = plan.json()
    assert plan_payload["selected_target_id"] == "plain-linux"
    assert plan_payload["plan_status"] == "partial"
    assert plan_payload["route_count"] == 6
    assert plan_payload["ready_route_count"] == 1
    assert plan_payload["remote_contract_ready_route_count"] == 0
    assert plan_payload["selected_contract_ready_route_count"] == 0
    assert plan_payload["selected_ready_route_ids"] == []
    assert plan_payload["remote_contract_ready_adapter_count"] == 0
    assert plan_payload["selected_contract_ready_adapter_count"] == 0
    assert plan_payload["remote_contract_ready_runner_family_count"] == 0
    assert plan_payload["selected_contract_ready_runner_family_count"] == 0
    assert "no_contract_ready_remote_runner_route" in plan_payload["blocking_reasons"]
    assert "selected_target_not_bound_to_contract_ready_remote_runner_route" in plan_payload["blocking_reasons"]
    assert plan_payload["selected_ready_adapter_ids"] == []
    assert plan_payload["selected_ready_runner_family_ids"] == []
    assert "no_contract_ready_remote_runner_family" in plan_payload["blocking_reasons"]
    assert "selected_target_not_bound_to_contract_ready_remote_runner_family" in plan_payload["blocking_reasons"]
    assert "selected_target_not_bound_to_contract_ready_remote_runner_adapter" in plan_payload["blocking_reasons"]
    assert (workspace / "artifacts" / "remote-runners" / "runner-route-inventory.json").exists()
    assert (workspace / "artifacts" / "remote-runners" / "approval-checkpoints.json").exists()
    assert (workspace / "artifacts" / "remote-runners" / "coverage-report.json").exists()
    assert (workspace / "artifacts" / "remote-runners" / "runner-family-inventory.json").exists()

    coverage_report = json.loads(
        (workspace / "artifacts" / "remote-runners" / "coverage-report.json").read_text(encoding="utf-8")
    )
    assert coverage_report["coverage_summary"]["ready_route_ids"] == ["local_workspace"]
    assert coverage_report["coverage_summary"]["remote_contract_ready_route_ids"] == []
    assert coverage_report["coverage_summary"]["selected_contract_ready_route_ids"] == []
    assert coverage_report["coverage_summary"]["ready_adapter_ids"] == ["local_workspace"]
    assert coverage_report["coverage_summary"]["remote_contract_ready_adapter_ids"] == []
    assert coverage_report["coverage_summary"]["selected_contract_ready_adapter_ids"] == []
    assert coverage_report["coverage_summary"]["remote_contract_ready_runner_family_ids"] == []
    assert coverage_report["coverage_summary"]["selected_contract_ready_runner_family_ids"] == []

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "remote-runners" / "approval-checkpoints.json").read_text(encoding="utf-8")
    )
    checkpoint_statuses = {item["checkpoint_id"]: item["status"] for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_statuses["ready_runner_family_review"] == "blocked"
    assert checkpoint_statuses["ready_adapter_review"] == "blocked"
    assert checkpoint_statuses["selected_target_binding_review"] == "blocked"
    assert checkpoint_statuses["coverage_review"] == "partial"
    assert checkpoint_statuses["result_format_review"] == "partial"


def test_platform_runner_summary_route_maps_remote_and_workspace_lanes(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "summary": "Browser and game-engine tooling are wired locally.",
            "tools": [
                {
                    "id": "playwright",
                    "category": "validation",
                    "installed": True,
                    "configured": True,
                    "status": "ready",
                    "notes": [],
                    "recommended_commands": ["playwright test"],
                },
                {
                    "id": "unity",
                    "category": "validation",
                    "installed": True,
                    "configured": True,
                    "status": "ready",
                    "notes": [],
                    "recommended_commands": ["Unity -batchmode -projectPath . -runTests -testPlatform EditMode -quit"],
                },
                {
                    "id": "unreal",
                    "category": "validation",
                    "installed": True,
                    "configured": True,
                    "status": "ready",
                    "notes": [],
                    "recommended_commands": ['RunUAT BuildCookRun -project="<project>.uproject" -nop4 -build -cook -stage -pak'],
                },
            ],
            "packs": [],
            "recommended_next_steps": [],
            "repo_mode_summaries": [],
            "important_paths": [],
            "execution_entrypoints": [],
            "runtime_blockers": [],
            "validation_evidence_targets": [],
            "product_lane_statuses": ["browser:ready", "unity:ready", "unreal:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": ["playwright test", "Unity -batchmode -runTests", "RunUAT BuildCookRun"],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands": [],
            "installed_tool_ids": ["playwright", "unity", "unreal"],
            "configured_tool_ids": ["playwright", "unity", "unreal"],
        },
    )
    workspace = tmp_path / "workspace-platform-runners"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Platform Runner Demo",
            "idea": "Need governed execution lanes across target families.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    for host_payload in (
        {
            "id": "linux-gpu",
            "label": "Linux GPU",
            "transport": "ssh",
            "host": "linux-gpu.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/linux-shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/linux-shadow"],
            "allowed_path_prefixes": ["src"],
            "artifact_roots": ["/srv/linux-shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
        {
            "id": "win-unity",
            "label": "Windows Unity",
            "transport": "tailscale_ssh",
            "host": "win-unity.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "windows",
            "workspace_root": "C:/shadow",
            "adapter_command": "python.exe",
            "runner_families": ["external_adapter"],
            "capabilities": ["unity", "windows_build"],
            "toolchains": ["vs2022", "unity6000"],
            "command_families": ["powershell", "unity_batchmode"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["C:/shadow"],
            "allowed_path_prefixes": ["src", "Assets"],
            "artifact_roots": ["C:/shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
        {
            "id": "mac-ios",
            "label": "macOS iOS",
            "transport": "ssh",
            "host": "mac-ios.local",
            "ssh_user": "mike",
            "os_family": "macos",
            "workspace_root": "/Users/mike/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["ios", "apple"],
            "toolchains": ["xcode15", "simctl", "ios17"],
            "command_families": ["xcodebuild", "simctl"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/Users/mike/shadow"],
            "allowed_path_prefixes": ["src", "ios"],
            "artifact_roots": ["/Users/mike/shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    ):
        upsert = client.put("/api/system/remote-execution/hosts", json=host_payload)
        assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "win-unity",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["unity6000"],
            "required_command_families": ["unity_batchmode"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/platform-runners/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["project_id"] == project_id
    assert payload["selected_target_id"] == "win-unity"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["ready_candidate_count"] == 1
    assert payload["ready_candidate_ids"] == ["win-unity"]
    assert payload["availability_diagnostics"]["candidate_count"] == 3
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["route_count"] == 4
    assert payload["ready_route_count"] == 4
    assert payload["selected_route_count"] == 2
    assert payload["selected_ready_route_count"] == 2
    assert payload["ready_route_ids"] == ["plain_ssh", "tailscale_ssh", "windows_host", "macos_host"]
    assert payload["selected_route_ids"] == ["tailscale_ssh", "windows_host"]
    assert payload["selected_ready_route_ids"] == ["tailscale_ssh", "windows_host"]
    assert payload["lane_count"] == 8
    assert payload["adapter_contract_count"] == 8
    assert payload["ready_adapter_contract_count"] >= 5
    assert payload["required_tool_family_count"] >= 5
    assert "unity_batchmode" in payload["required_tool_families"]
    assert "linux" in payload["ready_lane_ids"]
    assert "windows" in payload["ready_lane_ids"]
    assert "macos" in payload["ready_lane_ids"]
    assert "unity" in payload["ready_lane_ids"]
    assert "ios" in payload["ready_lane_ids"]
    lanes = {item["lane_id"]: item for item in payload["lanes"]}
    assert lanes["unity"]["selected_target_ids"] == ["win-unity"]
    assert lanes["unity"]["status"] == "ready"
    assert lanes["unity"]["resolution_status"] == "ready"
    assert lanes["unity"]["ready_candidate_ids"] == ["win-unity"]
    assert lanes["unity"]["availability_diagnostics"]["candidate_count"] == 3
    assert lanes["unity"]["selected_target_requirement_gaps"] == {
        "runner_families": [
            "lan_appliance_runner",
            "local_runner",
            "macos_agent_runner",
            "plain_ssh_runner",
            "tailscale_ssh_runner",
            "windows_agent_runner",
        ]
    }
    assert lanes["unity"]["selected_target_rejected_reasons"] == []
    assert lanes["unity"]["runner_families"] == ["external_adapter"]
    assert lanes["unity"]["route_ids"] == ["tailscale_ssh", "windows_host"]
    assert lanes["unity"]["selected_route_ids"] == ["tailscale_ssh", "windows_host"]
    assert lanes["unity"]["selected_ready_route_ids"] == ["tailscale_ssh", "windows_host"]
    assert lanes["unity"]["adapter_contract"]["adapter_family"] == "unity_batchmode"
    assert lanes["unity"]["adapter_contract"]["selected_binding_status"] == "ready"
    assert "logs" in lanes["unity"]["adapter_contract"]["expected_evidence_categories"]
    assert lanes["ios"]["route_ids"] == ["plain_ssh", "macos_host"]
    assert lanes["browser"]["status"] == "partial"
    assert lanes["browser"]["route_ids"] == []
    assert lanes["browser"]["adapter_contract"]["adapter_family"] == "browser_automation"
    assert lanes["browser"]["adapter_contract"]["selected_binding_status"] == "not_applicable"
    assert lanes["unreal"]["status"] == "partial"
    assert "Workspace tooling reports `unreal:ready`." in lanes["unreal"]["notes"]
    assert "playwright test" in lanes["browser"]["recommended_commands"]


def test_platform_runner_summary_route_recognizes_agent_runner_families_via_broker_resolution(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "summary": "No repo-local validation wiring yet.",
            "tools": [],
            "packs": [],
            "recommended_next_steps": [],
            "repo_mode_summaries": [],
            "important_paths": [],
            "execution_entrypoints": [],
            "runtime_blockers": [],
            "validation_evidence_targets": [],
            "product_lane_statuses": [],
            "execution_lane_summaries": [],
            "artifact_kind_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": [],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands": [],
            "installed_tool_ids": [],
            "configured_tool_ids": [],
        },
    )
    workspace = tmp_path / "workspace-platform-runner-agent-families"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Platform Runner Agent Families",
            "idea": "Need platform lanes to respect governed agent runner families.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    for host_payload in (
        {
            "id": "win-agent",
            "label": "Windows Agent",
            "transport": "tailscale_ssh",
            "host": "win-agent.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "windows",
            "workspace_root": "C:/agent-shadow",
            "runner_families": ["windows_agent_runner"],
            "capabilities": ["unity", "windows_build"],
            "toolchains": ["vs2022", "unity6000"],
            "installed_runtimes": ["unity_hub"],
            "command_families": ["powershell", "unity_batchmode"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["C:/agent-shadow"],
            "allowed_path_prefixes": ["src", "Assets"],
            "artifact_roots": ["C:/agent-shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
        {
            "id": "mac-agent",
            "label": "macOS Agent",
            "transport": "ssh",
            "host": "mac-agent.local",
            "ssh_user": "mike",
            "os_family": "macos",
            "workspace_root": "/Users/mike/agent-shadow",
            "runner_families": ["macos_agent_runner"],
            "capabilities": ["ios", "apple"],
            "toolchains": ["xcode15", "simctl", "ios17"],
            "installed_runtimes": ["xcode"],
            "command_families": ["xcodebuild", "simctl"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/Users/mike/agent-shadow"],
            "allowed_path_prefixes": ["src", "ios"],
            "artifact_roots": ["/Users/mike/agent-shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    ):
        upsert = client.put("/api/system/remote-execution/hosts", json=host_payload)
        assert upsert.status_code == 200, upsert.text

    summary = client.get(f"/api/projects/{project_id}/platform-runners/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["selected_target_id"] is None
    assert payload["route_count"] == 4
    assert payload["ready_route_count"] == 4
    assert payload["selected_route_count"] == 0
    assert payload["selected_ready_route_count"] == 0
    assert payload["ready_route_ids"] == ["tailscale_ssh", "windows_host", "plain_ssh", "macos_host"]
    assert "windows" in payload["ready_lane_ids"]
    assert "unity" in payload["ready_lane_ids"]
    assert "macos" in payload["ready_lane_ids"]
    assert "ios" in payload["ready_lane_ids"]
    lanes = {item["lane_id"]: item for item in payload["lanes"]}
    assert lanes["windows"]["target_ids"] == ["win-agent"]
    assert lanes["windows"]["runner_families"] == ["windows_agent_runner"]
    assert lanes["windows"]["ready_candidate_ids"] == ["win-agent"]
    assert lanes["windows"]["route_ids"] == ["tailscale_ssh", "windows_host"]
    assert lanes["unity"]["target_ids"] == ["win-agent"]
    assert lanes["unity"]["installed_runtimes"] == ["unity_hub"]
    assert lanes["unity"]["resolution_status"] == "ready"
    assert lanes["unity"]["route_ids"] == ["tailscale_ssh", "windows_host"]
    assert lanes["ios"]["target_ids"] == ["mac-agent"]
    assert lanes["ios"]["runner_families"] == ["macos_agent_runner"]
    assert lanes["ios"]["ready_candidate_ids"] == ["mac-agent"]
    assert lanes["ios"]["route_ids"] == ["plain_ssh", "macos_host"]


def test_host_and_runner_plan_routes_emit_project_manifests(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "summary": "Browser tooling is wired locally.",
            "tools": [
                {
                    "id": "playwright",
                    "category": "validation",
                    "installed": True,
                    "configured": True,
                    "status": "ready",
                    "notes": [],
                    "recommended_commands": ["playwright test"],
                }
            ],
            "packs": [],
            "recommended_next_steps": [],
            "repo_mode_summaries": [],
            "important_paths": [],
            "execution_entrypoints": [],
            "runtime_blockers": [],
            "validation_evidence_targets": [],
            "product_lane_statuses": ["browser:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": ["playwright test"],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands": [],
        },
    )
    workspace = tmp_path / "workspace-host-runner-plans"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Host Runner Plan Demo",
            "idea": "Need governed host and runner manifests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    for host_payload in (
        {
            "id": "linux-gpu",
            "label": "Linux GPU",
            "transport": "ssh",
            "host": "linux-gpu.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/linux-shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/linux-shadow"],
            "allowed_path_prefixes": ["src"],
            "artifact_roots": ["/srv/linux-shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
        {
            "id": "win-unity",
            "label": "Windows Unity",
            "transport": "tailscale_ssh",
            "host": "win-unity.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "windows",
            "workspace_root": "C:/shadow",
            "adapter_command": "python.exe",
            "runner_families": ["external_adapter"],
            "capabilities": ["unity", "windows_build"],
            "toolchains": ["vs2022", "unity6000"],
            "command_families": ["powershell", "unity_batchmode"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["C:/shadow"],
            "allowed_path_prefixes": ["src", "Assets"],
            "artifact_roots": ["C:/shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
        {
            "id": "mac-ios",
            "label": "macOS iOS",
            "transport": "ssh",
            "host": "mac-ios.local",
            "ssh_user": "mike",
            "os_family": "macos",
            "workspace_root": "/Users/mike/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["ios", "apple"],
            "toolchains": ["xcode15", "simctl", "ios17"],
            "command_families": ["xcodebuild", "simctl"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/Users/mike/shadow"],
            "allowed_path_prefixes": ["src", "ios"],
            "artifact_roots": ["/Users/mike/shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    ):
        upsert = client.put("/api/system/remote-execution/hosts", json=host_payload)
        assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "win-unity",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["unity6000"],
            "required_command_families": ["unity_batchmode"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    host_plan = client.post(f"/api/projects/{project_id}/host-capability-index/plan")
    assert host_plan.status_code == 200, host_plan.text
    host_payload = host_plan.json()
    assert host_payload["selected_target_id"] == "win-unity"
    assert host_payload["manifest_root"] == "artifacts/host-capability-index"
    assert (workspace / "artifacts" / "host-capability-index" / "target-matrix.json").exists()
    assert (workspace / "artifacts" / "host-capability-index" / "eligibility-report.json").exists()
    assert (workspace / "artifacts" / "host-capability-index" / "policy-requirements.json").exists()
    assert (workspace / "artifacts" / "host-capability-index" / "selection-checkpoints.json").exists()

    target_matrix = json.loads((workspace / "artifacts" / "host-capability-index" / "target-matrix.json").read_text(encoding="utf-8"))
    assert target_matrix["selected_target_id"] == "win-unity"
    assert target_matrix["required_runner_family"] == "external_adapter"
    assert target_matrix["status_counts"]["ready"] >= 1
    assert target_matrix["transport_counts"]["tailscale_ssh"] == 1
    assert target_matrix["os_family_counts"]["windows"] == 1
    target_ids = [item["target_id"] for item in target_matrix["matches"]]
    assert "linux-gpu" in target_ids
    assert "mac-ios" in target_ids
    selected_match = next(item for item in target_matrix["matches"] if item["target_id"] == "win-unity")
    assert selected_match["selected"] is True
    assert "unity6000" in selected_match["toolchains"]

    eligibility_report = json.loads((workspace / "artifacts" / "host-capability-index" / "eligibility-report.json").read_text(encoding="utf-8"))
    assert eligibility_report["selection_status"] in {"ready", "partial"}
    assert eligibility_report["selected_target_probe_status"] == "ready"
    assert eligibility_report["recommended_target_ids"] == ["win-unity"]
    assert eligibility_report["selected_match"]["target_id"] == "win-unity"
    assert eligibility_report["blocked_matches"]
    blocked_target_ids = [item["target_id"] for item in eligibility_report["blocked_matches"]]
    assert "linux-gpu" in blocked_target_ids
    assert "mac-ios" in blocked_target_ids
    linux_gpu_blocked = next(item for item in eligibility_report["blocked_matches"] if item["target_id"] == "linux-gpu")
    assert linux_gpu_blocked["requirement_gaps"]["toolchains"] == ["unity6000"]

    policy_requirements = json.loads((workspace / "artifacts" / "host-capability-index" / "policy-requirements.json").read_text(encoding="utf-8"))
    assert policy_requirements["required_toolchains"] == ["unity6000"]
    assert policy_requirements["required_command_families"] == ["unity_batchmode"]
    assert policy_requirements["policy_summary"]["toolchain_constrained"] is True
    assert policy_requirements["policy_summary"]["connector_family_constrained"] is False

    selection_checkpoints = json.loads((workspace / "artifacts" / "host-capability-index" / "selection-checkpoints.json").read_text(encoding="utf-8"))
    checkpoint_ids = [item["checkpoint_id"] for item in selection_checkpoints["checkpoints"]]
    assert "probe_status_review" in checkpoint_ids
    assert "policy_requirement_review" in checkpoint_ids

    remote_plan = client.post(f"/api/projects/{project_id}/remote-runners/plan")
    assert remote_plan.status_code == 200, remote_plan.text
    remote_payload = remote_plan.json()
    assert remote_payload["selected_target_id"] == "win-unity"
    assert remote_payload["route_count"] >= 1
    assert remote_payload["ready_route_count"] >= 1
    assert remote_payload["remote_contract_ready_route_count"] >= 1
    assert remote_payload["selected_contract_ready_route_count"] >= 1
    assert "windows_host" in remote_payload["selected_ready_route_ids"]
    assert "windows_host" in remote_payload["selected_contract_ready_route_ids"]
    assert remote_payload["remote_contract_ready_adapter_count"] >= 1
    assert remote_payload["selected_contract_ready_adapter_count"] >= 1
    assert remote_payload["remote_contract_ready_runner_family_count"] >= 1
    assert remote_payload["selected_contract_ready_runner_family_count"] >= 1
    assert "windows_host" in remote_payload["selected_ready_adapter_ids"]
    assert "windows_host" in remote_payload["selected_contract_ready_adapter_ids"]
    assert "external_adapter" in remote_payload["selected_ready_runner_family_ids"]
    assert "external_adapter" in remote_payload["selected_contract_ready_runner_family_ids"]
    assert remote_payload["manifest_root"] == "artifacts/remote-runners"
    assert remote_payload["route_inventory_path"] == "artifacts/remote-runners/runner-route-inventory.json"
    assert (workspace / "artifacts" / "remote-runners" / "runner-route-inventory.json").exists()
    assert (workspace / "artifacts" / "remote-runners" / "adapter-inventory.json").exists()
    assert (workspace / "artifacts" / "remote-runners" / "runner-family-inventory.json").exists()
    assert (workspace / "artifacts" / "remote-runners" / "coverage-report.json").exists()
    assert (workspace / "artifacts" / "remote-runners" / "target-binding.json").exists()
    assert (workspace / "artifacts" / "remote-runners" / "approval-checkpoints.json").exists()

    route_inventory = json.loads((workspace / "artifacts" / "remote-runners" / "runner-route-inventory.json").read_text(encoding="utf-8"))
    assert route_inventory["selected_target_id"] == "win-unity"
    assert route_inventory["required_runner_family"] == "external_adapter"
    assert route_inventory["status_counts"]["ready"] >= 1
    windows_route = next(item for item in route_inventory["routes"] if item["route_id"] == "windows_host")
    assert windows_route["selected_target_ids"] == ["win-unity"]
    assert windows_route["status"] == "ready"

    adapter_inventory = json.loads((workspace / "artifacts" / "remote-runners" / "adapter-inventory.json").read_text(encoding="utf-8"))
    assert adapter_inventory["selected_target_id"] == "win-unity"
    assert adapter_inventory["required_runner_family"] == "external_adapter"
    assert adapter_inventory["status_counts"]["ready"] >= 1
    assert adapter_inventory["transport_counts"]["tailscale_ssh"] >= 1
    windows_adapter = next(item for item in adapter_inventory["adapters"] if item["adapter_id"] == "windows_host")
    assert windows_adapter["selected_target_ids"] == ["win-unity"]
    assert windows_adapter["status"] == "ready"

    runner_family_inventory = json.loads(
        (workspace / "artifacts" / "remote-runners" / "runner-family-inventory.json").read_text(encoding="utf-8")
    )
    assert runner_family_inventory["selected_target_id"] == "win-unity"
    assert runner_family_inventory["required_runner_family"] == "external_adapter"
    assert "external_adapter" in runner_family_inventory["ready_runner_family_ids"]
    windows_family = next(
        item for item in runner_family_inventory["runner_families"] if item["runner_family_id"] == "external_adapter"
    )
    assert windows_family["selected_target_ids"] == ["win-unity"]
    assert windows_family["status"] == "ready"

    coverage_report = json.loads((workspace / "artifacts" / "remote-runners" / "coverage-report.json").read_text(encoding="utf-8"))
    assert coverage_report["required_runner_family"] == "external_adapter"
    assert "windows_host" in coverage_report["coverage_summary"]["ready_route_ids"]
    assert "windows_host" in coverage_report["coverage_summary"]["ready_adapter_ids"]
    assert "external_adapter" in coverage_report["coverage_summary"]["ready_runner_family_ids"]
    windows_route_coverage = next(item for item in coverage_report["route_coverage"] if item["route_id"] == "windows_host")
    assert windows_route_coverage["result_format_coverage"] == "ready"
    assert windows_route_coverage["command_family_coverage"] == "ready"
    windows_coverage = next(item for item in coverage_report["coverage"] if item["adapter_id"] == "windows_host")
    assert windows_coverage["result_format_coverage"] == "ready"
    assert windows_coverage["command_family_coverage"] == "ready"
    windows_family_coverage = next(
        item for item in coverage_report["runner_family_coverage"] if item["runner_family_id"] == "external_adapter"
    )
    assert windows_family_coverage["result_format_coverage"] == "ready"
    assert windows_family_coverage["command_family_coverage"] == "ready"

    target_binding = json.loads((workspace / "artifacts" / "remote-runners" / "target-binding.json").read_text(encoding="utf-8"))
    assert target_binding["selected_target_id"] == "win-unity"
    assert target_binding["selected_target_probe_status"] == "ready"
    assert "tailscale_ssh" in target_binding["selected_contract_ready_route_ids"]
    assert "windows_host" in target_binding["selected_contract_ready_route_ids"]
    assert "tailscale_ssh" in target_binding["selected_route_ids"]
    assert "windows_host" in target_binding["selected_route_ids"]
    selected_transport_route_binding = next(
        item for item in target_binding["routes_with_selected_targets"] if item["route_id"] == "tailscale_ssh"
    )
    assert selected_transport_route_binding["selected_target_ids"] == ["win-unity"]
    assert selected_transport_route_binding["status"] == "ready"
    selected_route_binding = next(item for item in target_binding["routes_with_selected_targets"] if item["route_id"] == "windows_host")
    assert selected_route_binding["selected_target_ids"] == ["win-unity"]
    assert selected_route_binding["status"] == "ready"
    assert "tailscale_ssh" in target_binding["selected_contract_ready_adapter_ids"]
    assert "windows_host" in target_binding["selected_contract_ready_adapter_ids"]
    assert "tailscale_ssh" in target_binding["selected_adapter_ids"]
    assert "windows_host" in target_binding["selected_adapter_ids"]
    selected_transport_adapter_binding = next(
        item for item in target_binding["adapters_with_selected_targets"] if item["adapter_id"] == "tailscale_ssh"
    )
    assert selected_transport_adapter_binding["selected_target_ids"] == ["win-unity"]
    assert selected_transport_adapter_binding["status"] == "ready"
    selected_binding = next(item for item in target_binding["adapters_with_selected_targets"] if item["adapter_id"] == "windows_host")
    assert selected_binding["selected_target_ids"] == ["win-unity"]
    assert selected_binding["status"] == "ready"
    assert "external_adapter" in target_binding["selected_contract_ready_runner_family_ids"]
    assert "tailscale_ssh_runner" in target_binding["selected_contract_ready_runner_family_ids"]
    assert "windows_agent_runner" in target_binding["selected_contract_ready_runner_family_ids"]
    assert "external_adapter" in target_binding["selected_runner_family_ids"]
    assert "tailscale_ssh_runner" in target_binding["selected_runner_family_ids"]
    assert "windows_agent_runner" in target_binding["selected_runner_family_ids"]
    selected_tailscale_family_binding = next(
        item
        for item in target_binding["runner_families_with_selected_targets"]
        if item["runner_family_id"] == "tailscale_ssh_runner"
    )
    assert selected_tailscale_family_binding["selected_target_ids"] == ["win-unity"]
    assert selected_tailscale_family_binding["status"] == "ready"
    selected_windows_family_binding = next(
        item
        for item in target_binding["runner_families_with_selected_targets"]
        if item["runner_family_id"] == "windows_agent_runner"
    )
    assert selected_windows_family_binding["selected_target_ids"] == ["win-unity"]
    assert selected_windows_family_binding["status"] == "ready"
    selected_family_binding = next(
        item
        for item in target_binding["runner_families_with_selected_targets"]
        if item["runner_family_id"] == "external_adapter"
    )
    assert selected_family_binding["selected_target_ids"] == ["win-unity"]
    assert selected_family_binding["status"] == "ready"

    remote_approval_checkpoints = json.loads((workspace / "artifacts" / "remote-runners" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    remote_checkpoint_ids = [item["checkpoint_id"] for item in remote_approval_checkpoints["checkpoints"]]
    assert "ready_runner_family_review" in remote_checkpoint_ids
    assert "coverage_review" in remote_checkpoint_ids
    assert "result_format_review" in remote_checkpoint_ids

    platform_plan = client.post(f"/api/projects/{project_id}/platform-runners/plan")
    assert platform_plan.status_code == 200, platform_plan.text
    platform_payload = platform_plan.json()
    assert platform_payload["selected_target_id"] == "win-unity"
    assert platform_payload["route_count"] == 4
    assert platform_payload["ready_route_count"] == 4
    assert platform_payload["selected_route_count"] == 2
    assert platform_payload["selected_ready_route_count"] == 2
    assert platform_payload["selected_route_ids"] == ["tailscale_ssh", "windows_host"]
    assert platform_payload["selected_ready_route_ids"] == ["tailscale_ssh", "windows_host"]
    assert platform_payload["selected_ready_lane_count"] >= 1
    assert "windows" in platform_payload["selected_ready_lane_ids"]
    assert "windows" in platform_payload["target_backed_ready_lane_ids"]
    assert platform_payload["adapter_contract_count"] == 8
    assert platform_payload["ready_adapter_contract_count"] >= 5
    assert "unity_batchmode" in platform_payload["ready_adapter_contract_ids"]
    assert "browser_automation" in platform_payload["required_tool_families"]
    assert platform_payload["manifest_root"] == "artifacts/platform-runners"
    assert platform_payload["route_inventory_path"] == "artifacts/platform-runners/route-inventory.json"
    assert (workspace / "artifacts" / "platform-runners" / "route-inventory.json").exists()
    assert (workspace / "artifacts" / "platform-runners" / "lane-inventory.json").exists()
    assert (workspace / "artifacts" / "platform-runners" / "adapter-contracts.json").exists()
    assert (workspace / "artifacts" / "platform-runners" / "native-tooling.json").exists()
    assert (workspace / "artifacts" / "platform-runners" / "execution-matrix.json").exists()
    assert (workspace / "artifacts" / "platform-runners" / "approval-checkpoints.json").exists()

    route_inventory = json.loads((workspace / "artifacts" / "platform-runners" / "route-inventory.json").read_text(encoding="utf-8"))
    assert route_inventory["selected_target_id"] == "win-unity"
    assert route_inventory["ready_route_ids"] == ["plain_ssh", "tailscale_ssh", "windows_host", "macos_host"]
    assert route_inventory["selected_route_ids"] == ["tailscale_ssh", "windows_host"]
    windows_route = next(item for item in route_inventory["routes"] if item["route_id"] == "windows_host")
    assert windows_route["selected_target_ids"] == ["win-unity"]
    assert "windows" in windows_route["ready_lane_ids"]
    assert "unity" in windows_route["ready_lane_ids"]

    lane_inventory = json.loads((workspace / "artifacts" / "platform-runners" / "lane-inventory.json").read_text(encoding="utf-8"))
    assert lane_inventory["selected_target_id"] == "win-unity"
    assert lane_inventory["status_counts"]["ready"] >= 1
    assert "windows" in lane_inventory["ready_lane_ids"]
    assert "unity" in lane_inventory["ready_lane_ids"]
    windows_lane = next(item for item in lane_inventory["lanes"] if item["lane_id"] == "windows")
    assert windows_lane["selected_target_ids"] == ["win-unity"]
    assert "powershell" in windows_lane["command_families"]
    assert windows_lane["selected_ready_route_ids"] == ["tailscale_ssh", "windows_host"]
    assert windows_lane["adapter_contract"]["adapter_family"] == "windows_installer"

    adapter_contracts = json.loads((workspace / "artifacts" / "platform-runners" / "adapter-contracts.json").read_text(encoding="utf-8"))
    assert adapter_contracts["selected_target_id"] == "win-unity"
    assert adapter_contracts["ready_adapter_contract_count"] >= 5
    assert "unity_batchmode" in adapter_contracts["ready_adapter_contract_ids"]
    assert "browser_automation" in adapter_contracts["required_tool_families"]
    unity_contract = next(item for item in adapter_contracts["contracts"] if item["contract_id"] == "unity_batchmode")
    assert unity_contract["selected_binding_status"] == "ready"
    assert "unity_batchmode" in unity_contract["required_tool_families"]


def test_platform_runner_plan_route_requires_selected_target_binding_when_broker_target_exists(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "summary": "Workspace tooling is visible locally.",
            "tools": [],
            "packs": [],
            "recommended_next_steps": [],
            "repo_mode_summaries": [],
            "important_paths": [],
            "execution_entrypoints": [],
            "runtime_blockers": [],
            "validation_evidence_targets": [],
            "product_lane_statuses": [],
            "execution_lane_summaries": [],
            "artifact_kind_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": [],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands": [],
            "installed_tool_ids": [],
            "configured_tool_ids": [],
        },
    )
    workspace = tmp_path / "workspace-platform-runner-selected-binding"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Platform Runner Binding Demo",
            "idea": "Need platform runner plans to respect broker-selected targets.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "linux-unknown",
            "label": "Linux Unknown",
            "transport": "ssh",
            "host": "linux-unknown.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python"],
            "toolchains": ["python3.11"],
            "command_families": ["python"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "unknown",
        },
    )
    assert upsert.status_code == 200, upsert.text

    ready_host = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "win-ready",
            "label": "Windows Ready",
            "transport": "tailscale_ssh",
            "host": "win-ready.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "windows",
            "workspace_root": "C:/shadow",
            "adapter_command": "python.exe",
            "runner_families": ["external_adapter"],
            "capabilities": ["windows_build"],
            "toolchains": ["vs2022"],
            "command_families": ["powershell"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["C:/shadow"],
            "allowed_path_prefixes": ["src"],
            "artifact_roots": ["C:/shadow/artifacts"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert ready_host.status_code == 200, ready_host.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "linux-unknown",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/platform-runners/summary")
    assert summary.status_code == 200, summary.text
    summary_payload = summary.json()
    assert summary_payload["selected_target_id"] == "linux-unknown"
    assert summary_payload["selected_target_probe_status"] == "unknown"
    assert "windows" in summary_payload["ready_lane_ids"]

    plan = client.post(f"/api/projects/{project_id}/platform-runners/plan")
    assert plan.status_code == 200, plan.text
    plan_payload = plan.json()
    assert plan_payload["selected_target_id"] == "linux-unknown"
    assert plan_payload["plan_status"] == "partial"
    assert plan_payload["selected_target_probe_status"] == "unknown"
    assert plan_payload["route_count"] == 3
    assert plan_payload["ready_route_count"] == 2
    assert plan_payload["selected_route_count"] == 1
    assert plan_payload["selected_ready_route_count"] == 0
    assert plan_payload["availability_diagnostics"]["candidate_count"] == 2
    assert plan_payload["selected_target_requirement_gaps"] == {}
    assert plan_payload["selected_target_rejected_reasons"] == []
    assert "selected_target_not_bound_to_ready_platform_runner_lane" in plan_payload["blocking_reasons"]
    assert "selected_target_not_bound_to_ready_platform_runner_route" in plan_payload["blocking_reasons"]

    route_inventory = json.loads(
        (workspace / "artifacts" / "platform-runners" / "route-inventory.json").read_text(encoding="utf-8")
    )
    assert route_inventory["selected_target_id"] == "linux-unknown"
    assert route_inventory["availability_diagnostics"]["candidate_count"] == 2
    assert route_inventory["selected_target_requirement_gaps"] == {}
    assert route_inventory["selected_target_rejected_reasons"] == []
    assert route_inventory["selected_route_ids"] == ["plain_ssh"]
    assert route_inventory["selected_ready_route_ids"] == []
    assert "tailscale_ssh" in route_inventory["ready_route_ids"]
    assert "windows_host" in route_inventory["ready_route_ids"]

    execution_matrix = json.loads(
        (workspace / "artifacts" / "platform-runners" / "execution-matrix.json").read_text(encoding="utf-8")
    )
    assert execution_matrix["selected_target_id"] == "linux-unknown"
    assert execution_matrix["selected_target_probe_status"] == "unknown"
    assert execution_matrix["availability_diagnostics"]["candidate_count"] == 2
    assert execution_matrix["selected_target_requirement_gaps"] == {}
    assert execution_matrix["selected_target_rejected_reasons"] == []
    assert execution_matrix["selected_route_ids"] == ["plain_ssh"]
    assert execution_matrix["selected_ready_route_ids"] == []
    assert execution_matrix["selected_ready_lane_ids"] == []
    assert "windows" in execution_matrix["by_status"]["ready"]
    assert "tailscale_ssh" in execution_matrix["by_route_status"]["ready"]

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "platform-runners" / "approval-checkpoints.json").read_text(encoding="utf-8")
    )
    checkpoint_statuses = {item["checkpoint_id"]: item["status"] for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_statuses["ready_lane_review"] == "ready"
    assert checkpoint_statuses["selected_target_review"] == "blocked"
    assert checkpoint_statuses["selected_binding_review"] == "blocked"
    assert checkpoint_statuses["selected_route_binding_review"] == "blocked"
    assert checkpoint_statuses["engine_native_command_review"] == "ready"


def test_artifact_transport_summary_route_composes_artifacts_connectors_and_lanes(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    normalized_registry = {
        "connections": {
            "source_control": {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["GitHub auth is ready."],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-artifact-transport"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Artifact Transport Demo",
            "idea": "Need a real artifact and connector transport contract.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "linux-sync",
            "label": "Linux Sync",
            "transport": "ssh",
            "host": "linux-sync.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "max_command_runtime_seconds": 1200,
            "file_transfer_quota_mb": 1024,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "linux-sync",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/artifact-transport/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["project_id"] == project_id
    assert payload["selected_target_id"] == "linux-sync"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["ready_candidate_count"] == 1
    assert payload["ready_candidate_ids"] == ["linux-sync"]
    assert payload["availability_diagnostics"]["candidate_count"] == 1
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["preflight_ready"] is True
    assert payload["sync_enabled"] is True
    assert payload["recommended_transport_mode"] == "remote_artifact_root"
    assert payload["adapter_contract_status"] == "ready"
    assert payload["adapter_contract_count"] >= 1
    assert payload["selected_adapter_contract_ids"] == ["linux_host_runtime"]
    assert payload["selected_adapter_shipping_modes"] == [
        "workspace_relative_sync",
        "remote_artifact_root",
        "brokered_sync",
    ]
    assert payload["common_adapter_shipping_modes"] == [
        "workspace_relative_sync",
        "remote_artifact_root",
        "brokered_sync",
    ]
    assert payload["transport_mode_adapter_status"] == "ready"
    assert payload["transport_mode_supported_adapter_contract_ids"] == ["linux_host_runtime"]
    assert payload["transport_mode_unsupported_adapter_contract_ids"] == []
    assert payload["transport_mode_undeclared_adapter_contract_ids"] == []
    assert payload["session_recording_status"] == "planned"
    assert payload["session_recording_required"] is True
    assert payload["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
    ]
    assert payload["produced_session_recording_artifact_paths"] == []
    assert payload["missing_session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
    ]
    assert payload["remote_session_recording_artifact_paths"] == [
        "/srv/shadow/artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
    ]
    assert payload["session_recording_runtime_manifest_count"] == 0
    assert payload["ready_route_count"] == 1
    assert payload["selected_ready_route_count"] == 1
    assert payload["partial_route_count"] == 0
    assert payload["ready_route_ids"] == ["plain_ssh"]
    assert payload["selected_ready_route_ids"] == ["plain_ssh"]
    assert payload["partial_route_ids"] == []
    assert payload["selected_ready_platform_lanes"] == ["linux"]
    assert payload["target_backed_ready_platform_lanes"] == ["linux"]
    assert payload["artifact_contract"]["selected_artifact_root"] == "/srv/shadow/artifacts"
    assert payload["artifact_contract"]["remote_workspace_artifact_paths"] == ["/srv/shadow/artifacts/model.onnx"]
    assert payload["connector_contract"]["available_families"] == ["source_control"]
    assert "linux" in payload["ready_platform_lanes"]


def test_artifact_transport_plan_requires_selected_target_ready_platform_lane(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    normalized_registry = {
        "connections": {
            "source_control": {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["GitHub auth is ready."],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-artifact-transport-selected-lane"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Artifact Transport Binding Demo",
            "idea": "Need artifact transport plans to respect selected target lane bindings.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    selected_target = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "freebsd-storage",
            "label": "Unknown Storage",
            "transport": "ssh",
            "host": "unknown-storage.local",
            "ssh_user": "mike",
            "os_family": "unknown",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "storage"],
            "toolchains": ["python3.11"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert selected_target.status_code == 200, selected_target.text

    unrelated_ready_host = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "win-builder",
            "label": "Windows Builder",
            "transport": "tailscale_ssh",
            "host": "win-builder.tailnet.ts.net",
            "ssh_user": "mike",
            "os_family": "windows",
            "workspace_root": "C:/shadow",
            "adapter_command": "python.exe",
            "runner_families": ["external_adapter"],
            "capabilities": ["windows_build"],
            "toolchains": ["vs2022"],
            "command_families": ["powershell"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["C:/shadow"],
            "allowed_path_prefixes": ["src"],
            "artifact_roots": ["C:/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert unrelated_ready_host.status_code == 200, unrelated_ready_host.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "freebsd-storage",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/artifact-transport/summary")
    assert summary.status_code == 200, summary.text
    summary_payload = summary.json()
    assert summary_payload["selected_target_id"] == "freebsd-storage"
    assert summary_payload["recommended_transport_mode"] == "blocked"
    assert summary_payload["availability_diagnostics"]["candidate_count"] == 2
    assert summary_payload["selected_target_requirement_gaps"] == {}
    assert summary_payload["selected_target_rejected_reasons"] == []
    assert "windows" in summary_payload["ready_platform_lanes"]
    assert "tailscale_ssh" in summary_payload["ready_route_ids"]
    assert "windows_host" in summary_payload["ready_route_ids"]
    assert summary_payload["selected_ready_route_ids"] == []
    assert summary_payload["selected_ready_platform_lanes"] == []
    assert summary_payload["target_backed_ready_platform_lanes"] == ["windows"]
    assert "selected_target_not_bound_to_ready_platform_lane_for_transport" in summary_payload["blocking_reasons"]
    assert "selected_target_not_bound_to_ready_platform_route_for_transport" in summary_payload["blocking_reasons"]

    plan = client.post(f"/api/projects/{project_id}/artifact-transport/plan")
    assert plan.status_code == 200, plan.text
    plan_payload = plan.json()
    assert plan_payload["selected_target_id"] == "freebsd-storage"
    assert plan_payload["plan_status"] == "partial"
    assert plan_payload["selected_target_probe_status"] == "ready"
    assert plan_payload["availability_diagnostics"]["candidate_count"] == 2
    assert plan_payload["selected_target_requirement_gaps"] == {}
    assert plan_payload["selected_target_rejected_reasons"] == []
    assert plan_payload["selected_ready_lane_count"] == 0
    assert plan_payload["ready_route_count"] == 2
    assert plan_payload["selected_ready_route_count"] == 0
    assert "tailscale_ssh" in plan_payload["ready_route_ids"]
    assert "windows_host" in plan_payload["ready_route_ids"]
    assert plan_payload["selected_ready_platform_lanes"] == []
    assert plan_payload["target_backed_ready_platform_lanes"] == ["windows"]
    assert "selected_target_not_bound_to_ready_platform_lane_for_transport" in plan_payload["blocking_reasons"]
    assert "selected_target_not_bound_to_ready_platform_route_for_transport" in plan_payload["blocking_reasons"]

    transport_mode = json.loads((workspace / "artifacts" / "artifact-transport" / "transport-mode.json").read_text(encoding="utf-8"))
    assert transport_mode["recommended_transport_mode"] == "blocked"
    assert transport_mode["availability_diagnostics"]["candidate_count"] == 2
    assert transport_mode["selected_target_requirement_gaps"] == {}
    assert transport_mode["selected_target_rejected_reasons"] == []
    assert transport_mode["selected_ready_route_ids"] == []
    assert "tailscale_ssh" in transport_mode["ready_route_ids"]
    assert transport_mode["selected_ready_platform_lanes"] == []
    assert "windows" in transport_mode["ready_platform_lanes"]

    platform_lane_plan = json.loads((workspace / "artifacts" / "artifact-transport" / "platform-lane-plan.json").read_text(encoding="utf-8"))
    assert platform_lane_plan["selected_target_id"] == "freebsd-storage"
    assert platform_lane_plan["availability_diagnostics"]["candidate_count"] == 2
    assert platform_lane_plan["selected_target_requirement_gaps"] == {}
    assert platform_lane_plan["selected_target_rejected_reasons"] == []
    assert platform_lane_plan["selected_ready_platform_lanes"] == []
    assert platform_lane_plan["selected_ready_lane_count"] == 0
    assert all("route_ids" in item for item in platform_lane_plan["lane_bindings"])

    platform_route_inventory = json.loads(
        (workspace / "artifacts" / "artifact-transport" / "platform-route-inventory.json").read_text(encoding="utf-8")
    )
    assert platform_route_inventory["selected_target_id"] == "freebsd-storage"
    assert platform_route_inventory["availability_diagnostics"]["candidate_count"] == 2
    assert platform_route_inventory["selected_target_requirement_gaps"] == {}
    assert platform_route_inventory["selected_target_rejected_reasons"] == []
    assert platform_route_inventory["selected_ready_route_ids"] == []
    assert "tailscale_ssh" in platform_route_inventory["ready_route_ids"]
    assert "windows_host" in platform_route_inventory["ready_route_ids"]

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "artifact-transport" / "approval-checkpoints.json").read_text(encoding="utf-8")
    )
    checkpoint_statuses = {item["checkpoint_id"]: item["status"] for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_statuses["artifact_contract_review"] == "ready"
    assert checkpoint_statuses["connector_contract_review"] == "ready"
    assert checkpoint_statuses["platform_lane_binding_review"] == "blocked"
    assert checkpoint_statuses["platform_route_binding_review"] == "blocked"
    assert checkpoint_statuses["session_recording_delivery_review"] == "partial"
    assert checkpoint_statuses["publish_gate_review"] == "blocked"


def test_artifact_transport_summary_flags_missing_session_recording_after_runtime_manifest(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    normalized_registry = {
        "connections": {
            "source_control": {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["GitHub auth is ready."],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-artifact-transport-runtime-gap"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")
    runtime_root = workspace / "artifacts" / "remote-execution-governance" / "runtime"
    runtime_root.mkdir(parents=True)
    (
        runtime_root / "linux-sync.json"
    ).write_text(
        json.dumps(
            {
                "run_id": "run-linux-sync",
                "target_id": "linux-sync",
                "transport": "ssh",
                "host": "linux-sync.local",
                "session_recording_required": True,
                "session_recording_enabled": True,
                "session_recording_artifact_paths": [
                    "artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
                ],
                "remote_session_recording_artifact_paths": [
                    "/srv/shadow/artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
                ],
                "remote_artifact_paths": ["/srv/shadow/artifacts/model.onnx"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Artifact Transport Runtime Gap Demo",
            "idea": "Need transport to catch missing session recording evidence after execution.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "linux-sync",
            "label": "Linux Sync",
            "transport": "ssh",
            "host": "linux-sync.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "linux-sync",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/artifact-transport/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["recommended_transport_mode"] == "blocked"
    assert payload["session_recording_status"] == "partial"
    assert payload["session_recording_runtime_manifest_count"] == 1
    assert payload["produced_session_recording_artifact_paths"] == []
    assert payload["missing_session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
    ]
    assert "session_recording_artifact_missing_after_remote_execution" in payload["blocking_reasons"]


def test_artifact_transport_summary_tracks_result_collection_delivery_from_runtime_manifest(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    normalized_registry = {
        "connections": {
            "source_control": {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["GitHub auth is ready."],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-artifact-transport-result-collection"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")
    runtime_root = workspace / "artifacts" / "remote-execution-governance" / "runtime"
    runtime_root.mkdir(parents=True)
    request_root = workspace / "artifacts" / "remote-execution-requests" / "remote-exec-collection"
    request_root.mkdir(parents=True)
    recording_path = workspace / "artifacts" / "remote-execution-governance" / "session-recordings" / "linux-sync.cast"
    recording_path.parent.mkdir(parents=True)
    recording_path.write_text("cast\n", encoding="utf-8")
    summary_path = workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{}", encoding="utf-8")
    (
        request_root / "transfer-bundle.json"
    ).write_text(
        json.dumps(
            {
                "request_id": "remote-exec-collection",
                "declared_result_collection": [
                    {
                        "local_path": "artifacts/screenshots/home.png",
                        "collection_stage": "remote_workspace_artifact",
                    },
                    {
                        "local_path": "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
                        "collection_stage": "remote_session_recording",
                    },
                    {
                        "local_path": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                        "collection_stage": "normalized_summary",
                    },
                ],
                "missing_result_artifact_paths": ["artifacts/screenshots/home.png"],
                "collected_result_artifacts": [
                    {
                        "local_path": "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
                        "collection_stage": "remote_session_recording",
                        "status": "collected",
                    },
                    {
                        "local_path": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                        "collection_stage": "normalized_summary",
                        "status": "collected",
                    },
                    {
                        "local_path": "artifacts/screenshots/home.png",
                        "collection_stage": "remote_workspace_artifact",
                        "status": "missing",
                    },
                ],
                "final_transfer_status": "partial",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (
        runtime_root / "linux-sync.json"
    ).write_text(
        json.dumps(
            {
                "run_id": "run-linux-sync",
                "target_id": "linux-sync",
                "transport": "ssh",
                "host": "linux-sync.local",
                "session_recording_required": True,
                "session_recording_enabled": True,
                "session_recording_artifact_paths": [
                    "artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
                ],
                "remote_session_recording_artifact_paths": [
                    "/srv/shadow/artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
                ],
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "transfer_bundle_path": "artifacts/remote-execution-requests/remote-exec-collection/transfer-bundle.json",
                "remote_artifact_paths": ["/srv/shadow/artifacts/screenshots/home.png"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Artifact Transport Result Collection Demo",
            "idea": "Need transport delivery to understand governed result artifacts after remote execution.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "linux-sync",
            "label": "Linux Sync",
            "transport": "ssh",
            "host": "linux-sync.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "linux-sync",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/artifact-transport/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["recommended_transport_mode"] == "blocked"
    assert payload["result_collection_status"] == "partial"
    assert payload["result_collection_runtime_manifest_count"] == 1
    assert payload["declared_result_collection_count"] == 3
    assert payload["produced_result_artifact_count"] == 2
    assert payload["missing_result_artifact_count"] == 1
    assert payload["produced_result_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
        "artifacts/remote-execution-governance/normalized-execution-summary.json",
    ]
    assert payload["missing_result_artifact_paths"] == ["artifacts/screenshots/home.png"]
    assert payload["result_collection_transfer_statuses"] == {"partial": 1}
    assert "result_artifact_missing_after_remote_execution" in payload["blocking_reasons"]


def test_file_governance_summary_route_surfaces_storage_lanes_and_scanners(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive", "sharepoint"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["Drive and SharePoint lanes are available."],
            },
            "source_control": {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["GitHub auth is ready."],
            },
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-file-governance"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "File Governance Demo",
            "idea": "Need governed large-scale file organization.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "linux-organizer",
            "label": "Linux Organizer",
            "transport": "ssh",
            "host": "linux-organizer.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "file_ops"],
            "toolchains": ["python3.11"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "linux-organizer",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/file-governance/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["project_id"] == project_id
    assert payload["recommended_operation_mode"] == "hybrid_connector_sync"
    assert payload["supports_bulk_planning"] is True
    assert payload["destructive_actions_require_approval"] is True
    assert payload["selected_target_id"] == "linux-organizer"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["availability_diagnostics"]["candidate_count"] == 1
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert "linux" in payload["ready_scanner_lanes"]
    assert "google_drive" in payload["storage_providers"]
    assert "sharepoint" in payload["storage_providers"]
    lanes = {item["lane_id"]: item for item in payload["storage_lanes"]}
    assert lanes["local_fs"]["status"] == "connected"
    assert lanes["cloud_storage"]["providers"] == ["google_drive", "sharepoint"]


def test_file_governance_prefers_connector_only_when_selected_target_has_no_ready_scanner_lane(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["Drive lane is available."],
            },
            "source_control": {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["GitHub auth is ready."],
            },
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-file-governance-selected-scanner"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "File Governance Selected Scanner Demo",
            "idea": "Need file governance to stop borrowing scanner readiness from the wrong host.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    selected_target = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "unknown-storage",
            "label": "Unknown Storage",
            "transport": "ssh",
            "host": "unknown-storage.local",
            "ssh_user": "mike",
            "os_family": "unknown",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "storage"],
            "toolchains": ["python3.11"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert selected_target.status_code == 200, selected_target.text

    unrelated_ready_host = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "linux-scanner",
            "label": "Linux Scanner",
            "transport": "ssh",
            "host": "linux-scanner.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/linux-shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "file_ops"],
            "toolchains": ["python3.11"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/linux-shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/linux-shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert unrelated_ready_host.status_code == 200, unrelated_ready_host.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "unknown-storage",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    summary = client.get(f"/api/projects/{project_id}/file-governance/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["recommended_operation_mode"] == "connector_only"
    assert payload["selected_target_id"] == "unknown-storage"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["availability_diagnostics"]["candidate_count"] == 2
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert "linux" in payload["ready_scanner_lanes"]
    assert payload["ready_scanner_route_ids"] == ["plain_ssh"]
    assert payload["selected_ready_scanner_lanes"] == []
    assert payload["selected_ready_scanner_route_ids"] == []
    assert payload["target_backed_ready_scanner_lanes"] == ["linux"]
    assert payload["virtual_file_graph_status"] == "partial"

    plan = client.post(f"/api/projects/{project_id}/file-governance/plan")
    assert plan.status_code == 200, plan.text
    plan_payload = plan.json()
    assert plan_payload["plan_status"] == "partial"
    assert plan_payload["recommended_operation_mode"] == "connector_only"
    assert plan_payload["selected_target_id"] == "unknown-storage"
    assert plan_payload["selected_target_probe_status"] == "ready"
    assert plan_payload["availability_diagnostics"]["candidate_count"] == 2
    assert plan_payload["selected_target_requirement_gaps"] == {}
    assert plan_payload["selected_target_rejected_reasons"] == []
    assert plan_payload["selected_ready_scanner_lane_count"] == 0
    assert plan_payload["selected_ready_scanner_lanes"] == []
    assert plan_payload["selected_ready_scanner_route_count"] == 0
    assert plan_payload["ready_scanner_route_ids"] == ["plain_ssh"]
    assert plan_payload["target_backed_ready_scanner_lanes"] == ["linux"]
    assert plan_payload["scanner_route_inventory_path"] == "artifacts/file-governance/scanner-route-inventory.json"
    assert plan_payload["virtual_file_graph_path"] == "artifacts/file-governance/virtual-file-graph.json"
    assert plan_payload["file_graph_manifest_root"] == "artifacts/file-graph"

    scanner_lanes = json.loads((workspace / "artifacts" / "file-governance" / "scanner-lanes.json").read_text(encoding="utf-8"))
    assert scanner_lanes["selected_target_id"] == "unknown-storage"
    assert scanner_lanes["selected_target_probe_status"] == "ready"
    assert scanner_lanes["availability_diagnostics"]["candidate_count"] == 2
    assert scanner_lanes["selected_target_requirement_gaps"] == {}
    assert scanner_lanes["selected_target_rejected_reasons"] == []
    assert scanner_lanes["ready_scanner_lanes"] == ["linux"]
    assert scanner_lanes["ready_scanner_route_ids"] == ["plain_ssh"]
    assert scanner_lanes["selected_ready_scanner_lane_count"] == 0
    assert scanner_lanes["selected_ready_scanner_lanes"] == []
    assert scanner_lanes["selected_ready_scanner_route_ids"] == []
    assert scanner_lanes["target_backed_ready_scanner_lanes"] == ["linux"]

    scanner_route_inventory = json.loads(
        (workspace / "artifacts" / "file-governance" / "scanner-route-inventory.json").read_text(encoding="utf-8")
    )
    assert scanner_route_inventory["selected_target_id"] == "unknown-storage"
    assert scanner_route_inventory["selected_target_probe_status"] == "ready"
    assert scanner_route_inventory["availability_diagnostics"]["candidate_count"] == 2
    assert scanner_route_inventory["selected_target_requirement_gaps"] == {}
    assert scanner_route_inventory["selected_target_rejected_reasons"] == []
    assert scanner_route_inventory["ready_scanner_route_ids"] == ["plain_ssh"]
    assert scanner_route_inventory["selected_ready_scanner_route_ids"] == []

    operation_mode = json.loads((workspace / "artifacts" / "file-governance" / "operation-mode.json").read_text(encoding="utf-8"))
    assert operation_mode["recommended_operation_mode"] == "connector_only"
    assert operation_mode["selected_target_id"] == "unknown-storage"
    assert operation_mode["selected_target_probe_status"] == "ready"
    assert operation_mode["availability_diagnostics"]["candidate_count"] == 2
    assert operation_mode["selected_target_requirement_gaps"] == {}
    assert operation_mode["selected_target_rejected_reasons"] == []
    assert operation_mode["virtual_file_graph_status"] == "partial"

    approval_guardrails = json.loads(
        (workspace / "artifacts" / "file-governance" / "approval-guardrails.json").read_text(encoding="utf-8")
    )
    assert approval_guardrails["selected_target_id"] == "unknown-storage"
    assert approval_guardrails["selected_target_probe_status"] == "ready"
    assert approval_guardrails["availability_diagnostics"]["candidate_count"] == 2
    assert approval_guardrails["selected_target_requirement_gaps"] == {}
    assert approval_guardrails["selected_target_rejected_reasons"] == []
    checkpoint_statuses = {item["checkpoint_id"]: item["status"] for item in approval_guardrails["approval_checkpoints"]}
    assert checkpoint_statuses["storage_lane_review"] == "ready"
    assert checkpoint_statuses["scanner_lane_review"] == "partial"
    assert checkpoint_statuses["scanner_route_review"] == "partial"
    assert checkpoint_statuses["mutation_gate_review"] == "ready"

    virtual_file_graph = json.loads(
        (workspace / "artifacts" / "file-governance" / "virtual-file-graph.json").read_text(encoding="utf-8")
    )
    assert virtual_file_graph["selected_target_id"] == "unknown-storage"
    assert virtual_file_graph["selected_target_probe_status"] == "ready"
    assert virtual_file_graph["availability_diagnostics"]["candidate_count"] == 2
    assert virtual_file_graph["selected_target_requirement_gaps"] == {}
    assert virtual_file_graph["selected_target_rejected_reasons"] == []
    assert virtual_file_graph["file_graph_manifest_root"] == "artifacts/file-graph"
    assert virtual_file_graph["dry_run_manifest_path"] == "artifacts/file-graph/bulk-rename-dry-run-plan.json"


def test_artifact_transport_and_file_governance_plan_routes_emit_project_manifests(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive", "sharepoint"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["Drive and SharePoint lanes are available."],
            },
            "source_control": {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["GitHub auth is ready."],
            },
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-transport-governance-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts = workspace / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.onnx").write_text("artifact\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Transport Governance Demo",
            "idea": "Need real artifact transport and file governance manifests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    upsert = client.put(
        "/api/system/remote-execution/hosts",
        json={
            "id": "linux-organizer",
            "label": "Linux Organizer",
            "transport": "ssh",
            "host": "linux-organizer.local",
            "ssh_user": "mike",
            "os_family": "linux",
            "workspace_root": "/srv/shadow",
            "adapter_command": "python3",
            "runner_families": ["external_adapter"],
            "capabilities": ["python", "file_ops", "gpu"],
            "toolchains": ["python3.11", "cuda12"],
            "command_families": ["python", "git"],
            "result_formats": ["json"],
            "session_recording_enabled": True,
            "allowed_repo_roots": ["/srv/shadow"],
            "allowed_path_prefixes": ["artifacts", "src"],
            "artifact_roots": ["/srv/shadow/artifacts"],
            "connector_families": ["source_control"],
            "trust_level": "trusted",
            "last_probe_status": "ready",
        },
    )
    assert upsert.status_code == 200, upsert.text

    policy_update = client.put(
        f"/api/projects/{project_id}/remote-execution/policy",
        json={
            "enabled": True,
            "preferred_target_id": "linux-organizer",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_result_formats": ["json"],
            "require_session_recording": True,
            "artifact_required": True,
            "required_connector_families": ["source_control"],
            "fallback_to_local": False,
        },
    )
    assert policy_update.status_code == 200, policy_update.text

    artifact_transport = client.post(f"/api/projects/{project_id}/artifact-transport/plan")
    assert artifact_transport.status_code == 200, artifact_transport.text
    artifact_transport_payload = artifact_transport.json()
    assert artifact_transport_payload["project_id"] == project_id
    assert artifact_transport_payload["plan_status"] in {"ready", "partial"}
    assert artifact_transport_payload["selected_ready_lane_count"] == 1
    assert artifact_transport_payload["selected_ready_platform_lanes"] == ["linux"]
    assert artifact_transport_payload["target_backed_ready_platform_lanes"] == ["linux"]
    assert artifact_transport_payload["manifest_root"] == "artifacts/artifact-transport"
    assert artifact_transport_payload["transport_mode_path"] == "artifacts/artifact-transport/transport-mode.json"
    assert artifact_transport_payload["artifact_sync_plan_path"] == "artifacts/artifact-transport/artifact-sync-plan.json"
    assert artifact_transport_payload["connector_lane_plan_path"] == "artifacts/artifact-transport/connector-lane-plan.json"
    assert artifact_transport_payload["platform_lane_plan_path"] == "artifacts/artifact-transport/platform-lane-plan.json"
    assert artifact_transport_payload["session_recording_status"] == "planned"
    assert artifact_transport_payload["session_recording_required"] is True
    assert artifact_transport_payload["session_recording_delivery_path"] == "artifacts/artifact-transport/session-recording-delivery.json"
    assert artifact_transport_payload["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/linux-organizer.cast"
    ]
    assert artifact_transport_payload["produced_session_recording_artifact_paths"] == []
    assert artifact_transport_payload["missing_session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/linux-organizer.cast"
    ]
    assert artifact_transport_payload["remote_session_recording_artifact_paths"] == [
        "/srv/shadow/artifacts/remote-execution-governance/session-recordings/linux-organizer.cast"
    ]
    assert artifact_transport_payload["approval_checkpoint_path"] == "artifacts/artifact-transport/approval-checkpoints.json"
    assert (workspace / "artifacts" / "artifact-transport" / "transport-mode.json").exists()
    assert (workspace / "artifacts" / "artifact-transport" / "artifact-sync-plan.json").exists()
    assert (workspace / "artifacts" / "artifact-transport" / "connector-lane-plan.json").exists()
    assert (workspace / "artifacts" / "artifact-transport" / "platform-lane-plan.json").exists()
    assert (workspace / "artifacts" / "artifact-transport" / "session-recording-delivery.json").exists()
    assert (workspace / "artifacts" / "artifact-transport" / "approval-checkpoints.json").exists()

    transport_mode = json.loads((workspace / "artifacts" / "artifact-transport" / "transport-mode.json").read_text(encoding="utf-8"))
    assert transport_mode["recommended_transport_mode"] == "remote_artifact_root"
    assert transport_mode["transport_requirements"]["artifact_sync_required"] is True
    assert transport_mode["ready_platform_lanes"] == ["linux"]

    artifact_sync_plan = json.loads((workspace / "artifacts" / "artifact-transport" / "artifact-sync-plan.json").read_text(encoding="utf-8"))
    assert artifact_sync_plan["selected_artifact_root"] == "/srv/shadow/artifacts"
    assert artifact_sync_plan["remote_workspace_root"] == "/srv/shadow"
    assert artifact_sync_plan["sync_requirements"]["target_root_required"] is True
    assert "artifacts/model.onnx" in artifact_sync_plan["local_artifact_paths"]

    connector_lane_plan = json.loads((workspace / "artifacts" / "artifact-transport" / "connector-lane-plan.json").read_text(encoding="utf-8"))
    assert connector_lane_plan["required_connector_families"] == ["source_control"]
    assert connector_lane_plan["authority_requirements"]["require_connector_authority"] is True
    assert connector_lane_plan["missing_required_families"] == []

    platform_lane_plan = json.loads((workspace / "artifacts" / "artifact-transport" / "platform-lane-plan.json").read_text(encoding="utf-8"))
    assert platform_lane_plan["selected_target_id"] == "linux-organizer"
    assert platform_lane_plan["ready_platform_lanes"] == ["linux"]
    linux_lane_binding = next(item for item in platform_lane_plan["lane_bindings"] if item["lane_id"] == "linux")
    assert linux_lane_binding["status"] == "ready"
    assert linux_lane_binding["selected_target_ids"] == ["linux-organizer"]

    session_recording_delivery = json.loads(
        (workspace / "artifacts" / "artifact-transport" / "session-recording-delivery.json").read_text(encoding="utf-8")
    )
    assert session_recording_delivery["session_recording_status"] == "planned"
    assert session_recording_delivery["session_recording_required"] is True
    assert session_recording_delivery["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/linux-organizer.cast"
    ]
    assert session_recording_delivery["produced_session_recording_artifact_paths"] == []
    assert session_recording_delivery["missing_session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/linux-organizer.cast"
    ]

    artifact_approval_checkpoints = json.loads((workspace / "artifacts" / "artifact-transport" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    artifact_checkpoint_ids = [item["checkpoint_id"] for item in artifact_approval_checkpoints["checkpoints"]]
    assert "platform_lane_binding_review" in artifact_checkpoint_ids
    assert "session_recording_delivery_review" in artifact_checkpoint_ids
    assert "publish_gate_review" in artifact_checkpoint_ids

    file_governance = client.post(f"/api/projects/{project_id}/file-governance/plan")
    assert file_governance.status_code == 200, file_governance.text
    file_governance_payload = file_governance.json()
    assert file_governance_payload["project_id"] == project_id
    assert file_governance_payload["plan_status"] in {"ready", "partial"}
    assert file_governance_payload["selected_target_id"] == "linux-organizer"
    assert file_governance_payload["selected_target_probe_status"] == "ready"
    assert file_governance_payload["availability_diagnostics"]["candidate_count"] == 1
    assert file_governance_payload["selected_target_requirement_gaps"] == {}
    assert file_governance_payload["selected_target_rejected_reasons"] == []
    assert file_governance_payload["selected_ready_scanner_lane_count"] == 1
    assert file_governance_payload["selected_ready_scanner_lanes"] == ["linux"]
    assert file_governance_payload["selected_ready_scanner_route_count"] == 1
    assert file_governance_payload["ready_scanner_route_ids"] == ["plain_ssh"]
    assert file_governance_payload["selected_ready_scanner_route_ids"] == ["plain_ssh"]
    assert file_governance_payload["target_backed_ready_scanner_lanes"] == ["linux"]
    assert file_governance_payload["scanner_route_inventory_path"] == "artifacts/file-governance/scanner-route-inventory.json"
    assert file_governance_payload["manifest_root"] == "artifacts/file-governance"
    assert file_governance_payload["storage_lanes_path"] == "artifacts/file-governance/storage-lanes.json"
    assert file_governance_payload["scanner_lanes_path"] == "artifacts/file-governance/scanner-lanes.json"
    assert file_governance_payload["operation_mode_path"] == "artifacts/file-governance/operation-mode.json"
    assert file_governance_payload["approval_guardrails_path"] == "artifacts/file-governance/approval-guardrails.json"
    assert file_governance_payload["transport_integration_path"] == "artifacts/file-governance/transport-integration.json"
    assert file_governance_payload["virtual_file_graph_path"] == "artifacts/file-governance/virtual-file-graph.json"
    assert file_governance_payload["cloud_storage_traversal_path"] == "artifacts/file-governance/cloud-storage-traversal.json"
    assert file_governance_payload["file_graph_manifest_root"] == "artifacts/file-graph"
    assert file_governance_payload["cloud_provider_count"] == 2
    assert file_governance_payload["cloud_provider_ids"] == ["google_drive", "sharepoint"]
    assert file_governance_payload["cloud_traversal_status"] in {"ready", "partial"}
    assert (workspace / "artifacts" / "file-governance" / "storage-lanes.json").exists()
    assert (workspace / "artifacts" / "file-governance" / "scanner-lanes.json").exists()
    assert (workspace / "artifacts" / "file-governance" / "scanner-route-inventory.json").exists()
    assert (workspace / "artifacts" / "file-governance" / "operation-mode.json").exists()
    assert (workspace / "artifacts" / "file-governance" / "approval-guardrails.json").exists()
    assert (workspace / "artifacts" / "file-governance" / "transport-integration.json").exists()
    assert (workspace / "artifacts" / "file-governance" / "virtual-file-graph.json").exists()
    assert (workspace / "artifacts" / "file-governance" / "cloud-storage-traversal.json").exists()
    assert (workspace / "artifacts" / "file-graph" / "content-hashes.sha256").exists()

    storage_lanes = json.loads((workspace / "artifacts" / "file-governance" / "storage-lanes.json").read_text(encoding="utf-8"))
    assert storage_lanes["selected_target_id"] == "linux-organizer"
    assert storage_lanes["selected_target_probe_status"] == "ready"
    assert storage_lanes["availability_diagnostics"]["candidate_count"] == 1
    assert storage_lanes["selected_target_requirement_gaps"] == {}
    assert storage_lanes["selected_target_rejected_reasons"] == []
    assert storage_lanes["connected_lane_ids"] == ["local_fs", "cloud_storage"]
    assert storage_lanes["transport_dependencies"]["recommended_transport_mode"] == "remote_artifact_root"
    assert storage_lanes["transport_dependencies"]["connector_authority_required"] is True
    assert storage_lanes["governance_requirements"]["reversible_batch_manifest_required"] is True
    storage_binding_ids = [item["lane_id"] for item in storage_lanes["lane_bindings"]]
    assert storage_binding_ids == ["local_fs", "cloud_storage"]

    scanner_lanes = json.loads((workspace / "artifacts" / "file-governance" / "scanner-lanes.json").read_text(encoding="utf-8"))
    assert scanner_lanes["selected_target_id"] == "linux-organizer"
    assert scanner_lanes["selected_target_probe_status"] == "ready"
    assert scanner_lanes["availability_diagnostics"]["candidate_count"] == 1
    assert scanner_lanes["selected_target_requirement_gaps"] == {}
    assert scanner_lanes["selected_target_rejected_reasons"] == []
    assert scanner_lanes["ready_scanner_lanes"] == ["linux"]
    assert scanner_lanes["ready_scanner_route_ids"] == ["plain_ssh"]
    assert scanner_lanes["selected_ready_scanner_lane_count"] == 1
    assert scanner_lanes["selected_ready_scanner_lanes"] == ["linux"]
    assert scanner_lanes["selected_ready_scanner_route_ids"] == ["plain_ssh"]
    assert scanner_lanes["target_backed_ready_scanner_lanes"] == ["linux"]
    assert scanner_lanes["scanner_requirements"]["brokered_execution_only"] is True
    linux_scanner_binding = next(item for item in scanner_lanes["lane_bindings"] if item["lane_id"] == "linux")
    assert linux_scanner_binding["status"] == "ready"
    assert linux_scanner_binding["selected_target_ids"] == ["linux-organizer"]
    assert linux_scanner_binding["selected_ready_route_ids"] == ["plain_ssh"]

    scanner_route_inventory = json.loads(
        (workspace / "artifacts" / "file-governance" / "scanner-route-inventory.json").read_text(encoding="utf-8")
    )
    assert scanner_route_inventory["selected_target_id"] == "linux-organizer"
    assert scanner_route_inventory["selected_target_probe_status"] == "ready"
    assert scanner_route_inventory["availability_diagnostics"]["candidate_count"] == 1
    assert scanner_route_inventory["selected_target_requirement_gaps"] == {}
    assert scanner_route_inventory["selected_target_rejected_reasons"] == []
    assert scanner_route_inventory["ready_scanner_route_ids"] == ["plain_ssh"]
    assert scanner_route_inventory["selected_ready_scanner_route_ids"] == ["plain_ssh"]

    operation_mode = json.loads((workspace / "artifacts" / "file-governance" / "operation-mode.json").read_text(encoding="utf-8"))
    assert operation_mode["recommended_operation_mode"] == "hybrid_connector_sync"
    assert operation_mode["selected_target_id"] == "linux-organizer"
    assert operation_mode["selected_target_probe_status"] == "ready"
    assert operation_mode["availability_diagnostics"]["candidate_count"] == 1
    assert operation_mode["selected_target_requirement_gaps"] == {}
    assert operation_mode["selected_target_rejected_reasons"] == []
    assert operation_mode["recommended_transport_mode"] == "remote_artifact_root"
    assert operation_mode["virtual_file_graph_status"] == "partial"
    assert operation_mode["cloud_traversal_status"] in {"ready", "partial"}
    assert operation_mode["mutation_requirements"]["dry_run_required"] is True
    assert operation_mode["mutation_requirements"]["human_approval_required_for_destructive_mutations"] is True

    approval_guardrails = json.loads((workspace / "artifacts" / "file-governance" / "approval-guardrails.json").read_text(encoding="utf-8"))
    assert approval_guardrails["selected_target_id"] == "linux-organizer"
    assert approval_guardrails["selected_target_probe_status"] == "ready"
    assert approval_guardrails["availability_diagnostics"]["candidate_count"] == 1
    assert approval_guardrails["selected_target_requirement_gaps"] == {}
    assert approval_guardrails["selected_target_rejected_reasons"] == []
    assert approval_guardrails["required_connector_families"] == ["source_control"]
    assert approval_guardrails["dry_run_manifest_required"] is True
    checkpoint_ids = [item["checkpoint_id"] for item in approval_guardrails["approval_checkpoints"]]
    assert "scanner_lane_review" in checkpoint_ids
    assert "scanner_route_review" in checkpoint_ids
    assert "cloud_traversal_review" in checkpoint_ids
    assert "virtual_file_graph_review" in checkpoint_ids
    assert "restore_bundle_review" in checkpoint_ids

    transport_integration = json.loads((workspace / "artifacts" / "file-governance" / "transport-integration.json").read_text(encoding="utf-8"))
    assert transport_integration["selected_target_id"] == "linux-organizer"
    assert transport_integration["selected_target_probe_status"] == "ready"
    assert transport_integration["availability_diagnostics"]["candidate_count"] == 1
    assert transport_integration["selected_target_requirement_gaps"] == {}
    assert transport_integration["selected_target_rejected_reasons"] == []
    assert transport_integration["required_connector_families"] == ["source_control"]
    assert transport_integration["selected_ready_scanner_route_ids"] == ["plain_ssh"]
    assert transport_integration["integration_requirements"]["connector_authority_required"] is True
    linux_transport_binding = next(item for item in transport_integration["lane_bindings"] if item["lane_id"] == "linux")
    assert linux_transport_binding["selected_target_ids"] == ["linux-organizer"]

    virtual_file_graph = json.loads((workspace / "artifacts" / "file-governance" / "virtual-file-graph.json").read_text(encoding="utf-8"))
    assert virtual_file_graph["selected_target_id"] == "linux-organizer"
    assert virtual_file_graph["selected_target_probe_status"] == "ready"
    assert virtual_file_graph["availability_diagnostics"]["candidate_count"] == 1
    assert virtual_file_graph["selected_target_requirement_gaps"] == {}
    assert virtual_file_graph["selected_target_rejected_reasons"] == []
    assert virtual_file_graph["file_graph_manifest_root"] == "artifacts/file-graph"
    assert virtual_file_graph["dry_run_manifest_path"] == "artifacts/file-graph/bulk-rename-dry-run-plan.json"
    assert virtual_file_graph["reversible_batch_manifest_path"] == "artifacts/file-graph/restore-batch-manifest.json"

    cloud_storage_traversal = json.loads(
        (workspace / "artifacts" / "file-governance" / "cloud-storage-traversal.json").read_text(encoding="utf-8")
    )
    assert cloud_storage_traversal["selected_target_id"] == "linux-organizer"
    assert cloud_storage_traversal["selected_target_probe_status"] == "ready"
    assert cloud_storage_traversal["availability_diagnostics"]["candidate_count"] == 1
    assert cloud_storage_traversal["selected_target_requirement_gaps"] == {}
    assert cloud_storage_traversal["selected_target_rejected_reasons"] == []
    assert cloud_storage_traversal["cloud_provider_ids"] == ["google_drive", "sharepoint"]
    assert cloud_storage_traversal["crawl_contract"]["strategy"] == "breadth_first"
    provider_map = {item["provider_id"]: item for item in cloud_storage_traversal["providers"]}
    assert provider_map["google_drive"]["root_selector_types"] == ["drive", "shared_drive", "folder"]
    assert provider_map["sharepoint"]["cursor_model"] == "@odata.nextLink"
    assert provider_map["google_drive"]["dry_run_manifest_path"] == "artifacts/file-graph/bulk-rename-dry-run-plan.json"
    assert provider_map["sharepoint"]["reversible_batch_manifest_path"] == "artifacts/file-graph/restore-batch-manifest.json"


def test_file_governance_cloud_traversal_run_route_emits_governed_jsonl_outputs(client, tmp_path, monkeypatch) -> None:
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive", "sharepoint"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["Drive and SharePoint lanes are available."],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "rclone" else None,
    )

    workspace = tmp_path / "workspace-cloud-traversal-run"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    (workspace / "docs").mkdir()
    (workspace / "docs" / "plan.md").write_text("plan\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Cloud Traversal Run Demo",
            "idea": "Need governed cloud traversal execution artifacts.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    run = client.post(
        f"/api/projects/{project_id}/file-governance/cloud-traversal/run",
        json={
            "provider_ids": ["google_drive", "sharepoint"],
            "max_items_per_provider": 50,
            "concurrency_limit": 2,
            "throttle_window_ms": 200,
            "dry_run": True,
        },
    )
    assert run.status_code == 200, run.text
    payload = run.json()
    assert payload["project_id"] == project_id
    assert payload["run_status"] == "completed"
    assert payload["dry_run"] is True
    assert payload["selected_target_id"] is None
    assert payload["selected_target_probe_status"] == "unknown"
    assert payload["availability_diagnostics"]["candidate_count"] == 0
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["selected_provider_count"] == 2
    assert payload["attempted_provider_count"] == 2
    assert payload["planned_provider_count"] == 2
    assert payload["blocked_provider_count"] == 0
    assert payload["manifest_root"] == "artifacts/file-governance"
    assert payload["traversal_manifest_path"] == "artifacts/file-governance/cloud-storage-traversal.json"
    assert payload["run_manifest_path"] == "artifacts/file-governance/cloud-traversal-run.json"
    assert payload["event_log_path"] == "artifacts/file-governance/cloud-traversal-events.jsonl"
    assert payload["file_graph_manifest_root"] == "artifacts/file-graph"
    assert "artifacts/file-graph/google_drive-crawl.jsonl" in payload["output_paths"]
    assert "artifacts/file-graph/sharepoint-crawl.jsonl" in payload["output_paths"]

    run_manifest = json.loads(
        (workspace / "artifacts" / "file-governance" / "cloud-traversal-run.json").read_text(encoding="utf-8")
    )
    assert run_manifest["run_status"] == "completed"
    assert run_manifest["selected_target_id"] is None
    assert run_manifest["selected_target_probe_status"] == "unknown"
    assert run_manifest["availability_diagnostics"]["candidate_count"] == 0
    assert run_manifest["selected_target_requirement_gaps"] == {}
    assert run_manifest["selected_target_rejected_reasons"] == []
    assert run_manifest["planned_provider_count"] == 2
    assert run_manifest["event_log_path"] == "artifacts/file-governance/cloud-traversal-events.jsonl"

    event_lines = (
        workspace / "artifacts" / "file-governance" / "cloud-traversal-events.jsonl"
    ).read_text(encoding="utf-8").strip().splitlines()
    assert len(event_lines) == 2
    first_event = json.loads(event_lines[0])
    assert first_event["record_type"] == "cloud_traversal_request"
    assert first_event["execution_status"] == "planned"

    provider_map = {item["provider_id"]: item for item in payload["provider_runs"]}
    assert provider_map["google_drive"]["action_id"] == "list"
    assert provider_map["google_drive"]["execution_status"] == "planned"
    assert provider_map["google_drive"]["provider_context_verified"] is True
    assert provider_map["google_drive"]["ready_to_execute"] is True
    assert provider_map["google_drive"]["params"]["provider"] == "google_drive"
    assert provider_map["sharepoint"]["supports_throttle_controls"] is True

    google_output = json.loads(
        (workspace / "artifacts" / "file-graph" / "google_drive-crawl.jsonl").read_text(encoding="utf-8").strip()
    )
    assert google_output["provider_id"] == "google_drive"
    assert google_output["limit"] == 50
    assert google_output["throttle_window_ms"] == 200


def test_file_governance_cloud_traversal_run_route_emits_item_records_for_live_execution(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["Drive lane is available."],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "rclone" else None,
    )

    def _fake_run(args, **kwargs):
        assert args[:2] == ["rclone", "lsjson"]
        assert "google_drive:" in args[2]

        class _Completed:
            returncode = 0
            stdout = json.dumps(
                [
                    {
                        "id": "hero-image",
                        "path": "Designs/hero.png",
                        "size": 128,
                        "sha256": "abc123",
                        "mimeType": "image/png",
                    },
                    {
                        "id": "brief",
                        "path": "Docs/brief.md",
                        "size": 64,
                    },
                ]
            )
            stderr = ""

        return _Completed()

    monkeypatch.setattr("integration_registry.subprocess.run", _fake_run)

    workspace = tmp_path / "workspace-cloud-traversal-live"
    workspace.mkdir()

    create = client.post(
        "/api/projects",
        json={
            "name": "Cloud Traversal Live Demo",
            "idea": "Need real cloud file item evidence.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    run = client.post(
        f"/api/projects/{project_id}/file-governance/cloud-traversal/run",
        json={
            "provider_ids": ["google_drive"],
            "max_items_per_provider": 25,
            "dry_run": False,
            "confirmed": True,
        },
    )
    assert run.status_code == 200, run.text
    payload = run.json()
    assert payload["run_status"] == "completed"
    assert payload["completed_provider_count"] == 1
    assert payload["output_paths"] == ["artifacts/file-graph/google_drive-crawl.jsonl"]
    assert payload["provider_runs"][0]["execution_status"] == "completed"
    assert "Emitted 2 cloud file item record(s)." in payload["provider_runs"][0]["notes"]

    output_lines = (
        workspace / "artifacts" / "file-graph" / "google_drive-crawl.jsonl"
    ).read_text(encoding="utf-8").strip().splitlines()
    assert len(output_lines) == 3
    output_records = [json.loads(line) for line in output_lines]
    assert output_records[0]["record_type"] == "cloud_traversal_request"
    assert output_records[1]["record_type"] == "cloud_file_item"
    assert output_records[1]["remote_path"] == "cloud://google_drive/Designs/hero.png"
    assert output_records[1]["classification"] == "image"
    assert output_records[1]["sha256"] == "abc123"
    assert output_records[2]["record_type"] == "cloud_file_item"
    assert output_records[2]["classification"] == "document"

    event_lines = (
        workspace / "artifacts" / "file-governance" / "cloud-traversal-events.jsonl"
    ).read_text(encoding="utf-8").strip().splitlines()
    assert len(event_lines) == 3
    assert [json.loads(line)["record_type"] for line in event_lines] == [
        "cloud_traversal_request",
        "cloud_file_item",
        "cloud_file_item",
    ]


def test_file_graph_governance_summary_route_surfaces_hash_dedupe_and_reversible_controls(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Large-scale file graph evidence is present.",
            "tools": [],
            "packs": [],
            "artifact_paths": [
                "artifacts/file-graph/content-hashes.sha256",
                "artifacts/file-graph/duplicate-clusters.json",
                "artifacts/file-graph/semantic-classification-taxonomy.json",
                "artifacts/file-graph/bulk-rename-dry-run-plan.json",
                "artifacts/file-graph/restore-batch-manifest.json",
            ],
            "artifact_kind_summaries": ["manifest:5"],
            "artifact_inspection_commands": ["python inspect_file_graph.py"],
            "config_review_paths": ["policies/file-governance-policy.yaml"],
            "config_review_commands": ["python review_file_governance_policy.py"],
            "validation_evidence_targets": ["artifacts/file-graph/bulk-rename-dry-run-plan.json"],
            "execution_entrypoints": [],
            "notebook_paths": [],
            "recommended_next_steps": ["Review the dry-run rename plan before shipping any archive batch."],
            "product_lane_statuses": [],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": ["python inspect_file_graph.py"],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
        },
    )
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive", "sharepoint"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["Drive and SharePoint lanes are available."],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-file-graph-governance"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Governance Demo",
            "idea": "Need governed large-scale file graph automation.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    summary = client.get(f"/api/projects/{project_id}/file-graph-governance/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["project_id"] == project_id
    assert payload["governance_status"] == "ready"
    assert payload["recommended_operation_mode"] == "connector_only"
    assert payload["hashing_readiness_status"] == "ready"
    assert payload["duplicate_clustering_status"] == "ready"
    assert payload["semantic_classification_status"] == "ready"
    assert payload["dry_run_manifest_status"] == "ready"
    assert payload["reversible_batch_status"] == "ready"
    assert payload["destructive_approval_status"] == "ready"
    assert payload["quality_gate_blocker_count"] == 0
    assert payload["pending_question_count"] == 0
    assert payload["hash_manifest_count"] == 1
    assert payload["duplicate_cluster_count"] == 1
    assert payload["classification_manifest_count"] == 1
    assert payload["dry_run_manifest_count"] == 1
    assert payload["reversible_batch_manifest_count"] == 1
    assert "artifacts/file-graph/content-hashes.sha256" in payload["hash_manifest_paths"]
    assert "artifacts/file-graph/duplicate-clusters.json" in payload["duplicate_cluster_paths"]
    assert "artifacts/file-graph/semantic-classification-taxonomy.json" in payload["classification_manifest_paths"]
    assert "artifacts/file-graph/bulk-rename-dry-run-plan.json" in payload["dry_run_manifest_paths"]
    assert "artifacts/file-graph/restore-batch-manifest.json" in payload["reversible_batch_manifest_paths"]
    assert payload["file_governance"]["destructive_actions_require_approval"] is True


def test_file_graph_governance_summary_route_surfaces_quality_gate_and_question_pressure(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 2})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 1})
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Large-scale file graph evidence is present.",
            "tools": [],
            "packs": [],
            "artifact_paths": [
                "artifacts/file-graph/content-hashes.sha256",
                "artifacts/file-graph/duplicate-clusters.json",
                "artifacts/file-graph/semantic-classification-taxonomy.json",
                "artifacts/file-graph/bulk-rename-dry-run-plan.json",
                "artifacts/file-graph/restore-batch-manifest.json",
            ],
            "artifact_kind_summaries": ["manifest:5"],
            "artifact_inspection_commands": ["python inspect_file_graph.py"],
            "config_review_paths": [],
            "config_review_commands": [],
            "validation_evidence_targets": ["artifacts/file-graph/bulk-rename-dry-run-plan.json"],
            "execution_entrypoints": [],
            "notebook_paths": [],
            "recommended_next_steps": [],
            "product_lane_statuses": [],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": [],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
        },
    )
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": [],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-file-graph-pressure"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Pressure Demo",
            "idea": "Need governed large-scale file graph automation.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    summary = client.get(f"/api/projects/{project_id}/file-graph-governance/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["governance_status"] == "blocked"
    assert payload["quality_gate_blocker_count"] == 2
    assert payload["pending_question_count"] == 1
    assert "2 quality gate(s) still block a clean file-graph handoff." in payload["blocking_reasons"]
    assert "Resolve required quality gates before treating this file-graph plan as execution-ready." in payload["recommended_fixes"]
    assert "Resolve pending project questions before approving destructive file-graph execution." in payload["recommended_fixes"]


def test_file_graph_governance_plan_route_generates_reversible_manifests(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})
    workspace = tmp_path / "workspace-file-graph-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    docs = workspace / "docs"
    docs.mkdir()
    dupes = workspace / "dupes"
    dupes.mkdir()
    (docs / "roadmap.txt").write_text("same content\n", encoding="utf-8")
    (dupes / "roadmap-copy.txt").write_text("same content\n", encoding="utf-8")
    (workspace / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Plan Demo",
            "idea": "Need real dry-run file graph manifests, not summary cosplay.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["scanned_file_count"] >= 3
    assert payload["hashed_file_count"] >= 3
    assert payload["cloud_record_count"] == 0
    assert payload["cloud_provider_count"] == 0
    assert payload["graph_node_count"] >= 3
    assert payload["graph_edge_count"] == 0
    assert payload["duplicate_cluster_count"] == 1
    assert payload["classification_bucket_count"] >= 2
    assert payload["action_count"] == 1
    assert payload["action_counts"]["archive_candidate"] == 1
    assert payload["hash_manifest_path"] == "artifacts/file-graph/content-hashes.sha256"
    assert payload["duplicate_cluster_path"] == "artifacts/file-graph/duplicate-clusters.json"
    assert payload["classification_manifest_path"] == "artifacts/file-graph/semantic-classification-taxonomy.json"
    assert payload["virtual_file_graph_path"] == "artifacts/file-graph/virtual-file-graph.json"
    assert payload["dry_run_manifest_path"] == "artifacts/file-graph/bulk-rename-dry-run-plan.json"
    assert payload["reversible_batch_manifest_path"] == "artifacts/file-graph/restore-batch-manifest.json"
    assert payload["selected_target_id"] is None
    assert payload["selected_target_probe_status"] == "unknown"
    assert payload["availability_diagnostics"]["candidate_count"] == 0
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["quality_gate_blocker_count"] == 0
    assert payload["pending_question_count"] == 0
    assert payload["proposed_actions"][0]["action_type"] == "archive_candidate"
    assert payload["restore_actions"][0]["reason"] == "undo_archive_candidate"

    assert (workspace / "artifacts" / "file-graph" / "content-hashes.sha256").exists()
    assert (workspace / "artifacts" / "file-graph" / "duplicate-clusters.json").exists()
    assert (workspace / "artifacts" / "file-graph" / "semantic-classification-taxonomy.json").exists()
    assert (workspace / "artifacts" / "file-graph" / "virtual-file-graph.json").exists()
    assert (workspace / "artifacts" / "file-graph" / "bulk-rename-dry-run-plan.json").exists()
    assert (workspace / "artifacts" / "file-graph" / "restore-batch-manifest.json").exists()

    hash_manifest_lines = (workspace / "artifacts" / "file-graph" / "content-hashes.sha256").read_text(encoding="utf-8").strip().splitlines()
    assert len(hash_manifest_lines) >= 3
    assert any(line.endswith("docs/roadmap.txt") for line in hash_manifest_lines)
    assert any(line.endswith("dupes/roadmap-copy.txt") for line in hash_manifest_lines)

    duplicate_clusters = json.loads((workspace / "artifacts" / "file-graph" / "duplicate-clusters.json").read_text(encoding="utf-8"))
    assert duplicate_clusters[0]["canonical_path"] == "docs/roadmap.txt"
    assert "dupes/roadmap-copy.txt" in duplicate_clusters[0]["paths"]

    classification_manifest = json.loads((workspace / "artifacts" / "file-graph" / "semantic-classification-taxonomy.json").read_text(encoding="utf-8"))
    assert classification_manifest["generated_by"] == "mission-control"
    assert classification_manifest["recommended_operation_mode"] in {"local_only", "workspace_relative_sync", "brokered_sync", "connector_only", "discovery_needed"}
    assert classification_manifest["selected_target_id"] is None
    assert classification_manifest["selected_target_probe_status"] == "unknown"
    assert classification_manifest["availability_diagnostics"]["candidate_count"] == 0
    assert classification_manifest["selected_target_requirement_gaps"] == {}
    assert classification_manifest["selected_target_rejected_reasons"] == []
    assert classification_manifest["bucket_sizes"]["document"] >= 2
    assert classification_manifest["bucket_sizes"]["dataset"] == 1
    assert classification_manifest["bucket_sizes"]["cloud_record"] == 0

    virtual_file_graph = json.loads((workspace / "artifacts" / "file-graph" / "virtual-file-graph.json").read_text(encoding="utf-8"))
    assert virtual_file_graph["selected_target_id"] is None
    assert virtual_file_graph["selected_target_probe_status"] == "unknown"
    assert virtual_file_graph["availability_diagnostics"]["candidate_count"] == 0
    assert virtual_file_graph["selected_target_requirement_gaps"] == {}
    assert virtual_file_graph["selected_target_rejected_reasons"] == []
    assert virtual_file_graph["local_node_count"] >= 3
    assert virtual_file_graph["cloud_node_count"] == 0
    assert virtual_file_graph["cloud_provider_count"] == 0
    assert virtual_file_graph["edge_count"] == 0

    dry_run_manifest = json.loads((workspace / "artifacts" / "file-graph" / "bulk-rename-dry-run-plan.json").read_text(encoding="utf-8"))
    assert dry_run_manifest["mode"] == "dry_run"
    assert dry_run_manifest["requires_human_approval"] is True
    assert dry_run_manifest["selected_target_id"] is None
    assert dry_run_manifest["selected_target_probe_status"] == "unknown"
    assert dry_run_manifest["availability_diagnostics"]["candidate_count"] == 0
    assert dry_run_manifest["selected_target_requirement_gaps"] == {}
    assert dry_run_manifest["selected_target_rejected_reasons"] == []
    assert dry_run_manifest["approval_gate_context"]["apply_runner_ref"] == f"file_graph_apply:{project_id}"
    assert dry_run_manifest["approval_gate_context"]["quality_gate_blocker_count"] == 0
    assert dry_run_manifest["approval_gate_context"]["pending_question_count"] == 0
    assert dry_run_manifest["duplicate_cluster_count"] == 1
    assert dry_run_manifest["cloud_record_count"] == 0
    assert dry_run_manifest["actions"][0]["source_path"] == "dupes/roadmap-copy.txt"

    restore_manifest = json.loads((workspace / "artifacts" / "file-graph" / "restore-batch-manifest.json").read_text(encoding="utf-8"))
    assert restore_manifest["mode"] == "reversible_batch_restore"
    assert restore_manifest["requires_human_approval"] is True
    assert restore_manifest["selected_target_id"] is None
    assert restore_manifest["selected_target_probe_status"] == "unknown"
    assert restore_manifest["availability_diagnostics"]["candidate_count"] == 0
    assert restore_manifest["selected_target_requirement_gaps"] == {}
    assert restore_manifest["selected_target_rejected_reasons"] == []
    assert restore_manifest["approval_gate_context"]["apply_runner_ref"] == f"file_graph_apply:{project_id}"
    assert restore_manifest["approval_gate_context"]["quality_gate_blocker_count"] == 0
    assert restore_manifest["approval_gate_context"]["pending_question_count"] == 0
    assert restore_manifest["restores_action_ids"] == [dry_run_manifest["actions"][0]["action_id"]]
    assert restore_manifest["actions"][0]["restore_destination"] == "dupes/roadmap-copy.txt"

    summary = client.get(f"/api/projects/{project_id}/file-graph-governance/summary")
    assert summary.status_code == 200, summary.text
    summary_payload = summary.json()
    assert "artifacts/file-graph/content-hashes.sha256" in summary_payload["hash_manifest_paths"]
    assert "artifacts/file-graph/duplicate-clusters.json" in summary_payload["duplicate_cluster_paths"]
    assert "artifacts/file-graph/semantic-classification-taxonomy.json" in summary_payload["classification_manifest_paths"]
    assert "artifacts/file-graph/bulk-rename-dry-run-plan.json" in summary_payload["dry_run_manifest_paths"]
    assert "artifacts/file-graph/restore-batch-manifest.json" in summary_payload["reversible_batch_manifest_paths"]


def test_file_graph_governance_plan_ingests_cloud_traversal_outputs_into_virtual_graph(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive", "sharepoint"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": [],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-file-graph-cloud-ingest"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    artifacts_root = workspace / "artifacts" / "file-graph"
    artifacts_root.mkdir(parents=True)
    (artifacts_root / "google_drive-crawl.jsonl").write_text(
        json.dumps(
            {
                "record_type": "cloud_traversal_request",
                "provider_id": "google_drive",
                "action_id": "list",
                "root_selector": "shared_drive",
                "query": "artifacts",
                "output_path": "artifacts/file-graph/google_drive-crawl.jsonl",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (artifacts_root / "sharepoint-crawl.jsonl").write_text(
        json.dumps(
            {
                "record_type": "cloud_traversal_request",
                "provider_id": "sharepoint",
                "action_id": "list",
                "root_selector": "site",
                "query": "*",
                "output_path": "artifacts/file-graph/sharepoint-crawl.jsonl",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Cloud Ingest Demo",
            "idea": "Need cloud traversal evidence folded into the virtual file graph.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["cloud_record_count"] == 2
    assert payload["cloud_provider_count"] == 2
    assert payload["graph_node_count"] >= 3
    assert payload["graph_edge_count"] == 2
    assert payload["virtual_file_graph_path"] == "artifacts/file-graph/virtual-file-graph.json"

    classification_manifest = json.loads((workspace / "artifacts" / "file-graph" / "semantic-classification-taxonomy.json").read_text(encoding="utf-8"))
    assert classification_manifest["bucket_sizes"]["cloud_record"] == 2
    assert "cloud://google_drive/shared_drive?query=artifacts" in classification_manifest["buckets"]["cloud_record"]
    assert "cloud://sharepoint/site" in classification_manifest["buckets"]["cloud_record"]

    virtual_file_graph = json.loads((workspace / "artifacts" / "file-graph" / "virtual-file-graph.json").read_text(encoding="utf-8"))
    assert virtual_file_graph["cloud_node_count"] == 2
    assert virtual_file_graph["cloud_provider_ids"] == ["google_drive", "sharepoint"]
    assert virtual_file_graph["cloud_output_paths"] == [
        "artifacts/file-graph/google_drive-crawl.jsonl",
        "artifacts/file-graph/sharepoint-crawl.jsonl",
    ]
    cloud_nodes = [item for item in virtual_file_graph["nodes"] if item["origin"] == "cloud"]
    assert len(cloud_nodes) == 2
    assert any(node["provider_id"] == "google_drive" for node in cloud_nodes)
    assert any(node["provider_id"] == "sharepoint" for node in cloud_nodes)

    dry_run_manifest = json.loads((workspace / "artifacts" / "file-graph" / "bulk-rename-dry-run-plan.json").read_text(encoding="utf-8"))
    assert dry_run_manifest["cloud_record_count"] == 2
    assert dry_run_manifest["cloud_provider_ids"] == ["google_drive", "sharepoint"]


def test_file_graph_governance_plan_promotes_cloud_file_items_into_duplicate_actions(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": [],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)

    workspace = tmp_path / "workspace-file-graph-cloud-duplicates"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    local_content = "shared duplicate plan\n"
    local_path = workspace / "docs" / "plan.md"
    local_path.write_text(local_content, encoding="utf-8")
    duplicate_sha = hashlib.sha256(local_path.read_bytes()).hexdigest()

    artifacts_root = workspace / "artifacts" / "file-graph"
    artifacts_root.mkdir(parents=True)
    (artifacts_root / "google_drive-crawl.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_type": "cloud_traversal_request",
                        "provider_id": "google_drive",
                        "action_id": "list",
                        "root_selector": "shared_drive",
                        "query": "*",
                        "output_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    }
                ),
                json.dumps(
                    {
                        "record_type": "cloud_file_item",
                        "provider_id": "google_drive",
                        "item_id": "copy-plan",
                        "remote_path": "cloud://google_drive/Shared/plan-copy.md",
                        "relative_path_hint": "Shared/plan-copy.md",
                        "classification": "document",
                        "size_bytes": len(local_content.encode("utf-8")),
                        "sha256": duplicate_sha,
                        "source_artifact_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Cloud Duplicate Demo",
            "idea": "Need remote duplicates surfaced as governed actions.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "ready"
    assert payload["duplicate_cluster_count"] == 1
    assert payload["action_count"] == 1
    assert payload["action_counts"]["remote_archive_candidate"] == 1
    assert payload["hashed_file_count"] == 2

    classification_manifest = json.loads(
        (workspace / "artifacts" / "file-graph" / "semantic-classification-taxonomy.json").read_text(encoding="utf-8")
    )
    assert classification_manifest["bucket_sizes"]["document"] == 2
    assert classification_manifest["bucket_sizes"]["cloud_record"] == 1

    duplicate_clusters = json.loads(
        (workspace / "artifacts" / "file-graph" / "duplicate-clusters.json").read_text(encoding="utf-8")
    )
    assert duplicate_clusters[0]["canonical_path"] == "docs/plan.md"
    assert "cloud://google_drive/Shared/plan-copy.md" in duplicate_clusters[0]["paths"]

    dry_run_manifest = json.loads(
        (workspace / "artifacts" / "file-graph" / "bulk-rename-dry-run-plan.json").read_text(encoding="utf-8")
    )
    assert dry_run_manifest["cloud_record_count"] == 2
    assert dry_run_manifest["cloud_item_count"] == 1
    assert dry_run_manifest["actions"][0]["action_type"] == "remote_archive_candidate"
    assert dry_run_manifest["actions"][0]["provider_id"] == "google_drive"
    assert dry_run_manifest["actions"][0]["requires_connector_approval"] is True

    restore_manifest = json.loads(
        (workspace / "artifacts" / "file-graph" / "restore-batch-manifest.json").read_text(encoding="utf-8")
    )
    assert restore_manifest["actions"][0]["reason"] == "undo_remote_archive_candidate"
    assert restore_manifest["actions"][0]["provider_id"] == "google_drive"

    virtual_file_graph = json.loads(
        (workspace / "artifacts" / "file-graph" / "virtual-file-graph.json").read_text(encoding="utf-8")
    )
    assert virtual_file_graph["cloud_item_node_count"] == 1
    assert virtual_file_graph["cloud_request_node_count"] == 1
    cloud_item_nodes = [
        node for node in virtual_file_graph["nodes"] if node["origin"] == "cloud" and node["record_type"] == "cloud_file_item"
    ]
    assert len(cloud_item_nodes) == 1
    assert cloud_item_nodes[0]["sha256"] == duplicate_sha


def test_file_graph_governance_apply_route_requires_approval_then_moves_local_files(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})
    monkeypatch.setattr(
        "manager.security_service.evaluate_action",
        lambda db, payload, project=None: {
            "policy": {},
            "assessment": {"risk_level": "high"},
            "decision": "pending",
            "reason": "Bulk file mutations require explicit approval.",
        },
    )
    workspace = tmp_path / "workspace-file-graph-apply-local"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    (workspace / "dupes").mkdir()
    (workspace / "docs" / "roadmap.txt").write_text("same content\n", encoding="utf-8")
    (workspace / "dupes" / "roadmap-copy.txt").write_text("same content\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Apply Local Demo",
            "idea": "Need governed local duplicate execution with approvals.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    action_id = plan.json()["proposed_actions"][0]["action_id"]

    pending_apply = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id]},
    )
    assert pending_apply.status_code == 200, pending_apply.text
    pending_payload = pending_apply.json()
    assert pending_payload["run_status"] == "approval_required"
    assert pending_payload["approval_required"] is True
    assert isinstance(pending_payload["approval_id"], int)
    assert pending_payload["selected_target_id"] is None
    assert pending_payload["selected_target_probe_status"] == "unknown"
    assert pending_payload["availability_diagnostics"]["candidate_count"] == 0
    assert pending_payload["selected_target_requirement_gaps"] == {}
    assert pending_payload["selected_target_rejected_reasons"] == []
    assert pending_payload["quality_gate_blocker_count"] == 0
    assert pending_payload["pending_question_count"] == 0
    assert pending_payload["applied_action_count"] == 0
    assert (workspace / "dupes" / "roadmap-copy.txt").exists()

    approval_id = pending_payload["approval_id"]
    approval = client.post(
        f"/api/projects/{project_id}/approvals/{approval_id}/approve-once",
        json={"project_id": project_id},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["status"] == "approved_once"

    apply_run = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id], "approval_id": approval_id},
    )
    assert apply_run.status_code == 200, apply_run.text
    payload = apply_run.json()
    assert payload["run_status"] == "completed"
    assert payload["approval_status"] == "approved_once"
    assert payload["selected_action_count"] == 1
    assert payload["applied_action_count"] == 1
    assert payload["staged_remote_action_count"] == 0
    assert payload["failed_action_count"] == 0
    assert payload["connector_batch_manifest_path"] is None
    assert payload["selected_target_id"] is None
    assert payload["selected_target_probe_status"] == "unknown"
    assert payload["availability_diagnostics"]["candidate_count"] == 0
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["quality_gate_blocker_count"] == 0
    assert payload["pending_question_count"] == 0

    archived_path = workspace / "archive" / "review" / "duplicates" / "dupes__roadmap-copy.txt"
    assert archived_path.exists()
    assert not (workspace / "dupes" / "roadmap-copy.txt").exists()

    run_manifest = json.loads((workspace / payload["run_manifest_path"]).read_text(encoding="utf-8"))
    assert run_manifest["run_status"] == "completed"
    assert run_manifest["selected_target_id"] is None
    assert run_manifest["selected_target_probe_status"] == "unknown"
    assert run_manifest["availability_diagnostics"]["candidate_count"] == 0
    assert run_manifest["selected_target_requirement_gaps"] == {}
    assert run_manifest["selected_target_rejected_reasons"] == []
    assert run_manifest["quality_gate_blocker_count"] == 0
    assert run_manifest["pending_question_count"] == 0
    assert run_manifest["applied_action_count"] == 1
    assert run_manifest["action_results"][0]["execution_status"] == "applied"


def test_file_graph_governance_restore_route_requires_approval_then_restores_local_files(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})
    monkeypatch.setattr(
        "manager.security_service.evaluate_action",
        lambda db, payload, project=None: {
            "policy": {},
            "assessment": {"risk_level": "high"},
            "decision": "pending",
            "reason": "Bulk file mutations require explicit approval.",
        },
    )
    workspace = tmp_path / "workspace-file-graph-restore-local"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    (workspace / "dupes").mkdir()
    (workspace / "docs" / "roadmap.txt").write_text("same content\n", encoding="utf-8")
    (workspace / "dupes" / "roadmap-copy.txt").write_text("same content\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Restore Local Demo",
            "idea": "Need governed local duplicate restore execution with approvals.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    action_id = plan.json()["proposed_actions"][0]["action_id"]

    pending_apply = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id]},
    )
    assert pending_apply.status_code == 200, pending_apply.text
    apply_approval_id = pending_apply.json()["approval_id"]
    apply_approval = client.post(
        f"/api/projects/{project_id}/approvals/{apply_approval_id}/approve-once",
        json={"project_id": project_id},
    )
    assert apply_approval.status_code == 200, apply_approval.text
    apply_run = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id], "approval_id": apply_approval_id},
    )
    assert apply_run.status_code == 200, apply_run.text

    archived_path = workspace / "archive" / "review" / "duplicates" / "dupes__roadmap-copy.txt"
    assert archived_path.exists()
    assert not (workspace / "dupes" / "roadmap-copy.txt").exists()

    pending_restore = client.post(
        f"/api/projects/{project_id}/file-graph-governance/restore",
        json={"action_ids": [action_id]},
    )
    assert pending_restore.status_code == 200, pending_restore.text
    pending_payload = pending_restore.json()
    assert pending_payload["run_status"] == "approval_required"
    assert pending_payload["approval_required"] is True
    assert isinstance(pending_payload["approval_id"], int)
    assert pending_payload["selected_target_id"] is None
    assert pending_payload["selected_target_probe_status"] == "unknown"
    assert pending_payload["availability_diagnostics"]["candidate_count"] == 0
    assert pending_payload["selected_target_requirement_gaps"] == {}
    assert pending_payload["selected_target_rejected_reasons"] == []
    assert pending_payload["quality_gate_blocker_count"] == 0
    assert pending_payload["pending_question_count"] == 0
    assert pending_payload["restored_action_count"] == 0

    restore_approval_id = pending_payload["approval_id"]
    restore_approval = client.post(
        f"/api/projects/{project_id}/approvals/{restore_approval_id}/approve-once",
        json={"project_id": project_id},
    )
    assert restore_approval.status_code == 200, restore_approval.text
    assert restore_approval.json()["status"] == "approved_once"

    restore_run = client.post(
        f"/api/projects/{project_id}/file-graph-governance/restore",
        json={"action_ids": [action_id], "approval_id": restore_approval_id},
    )
    assert restore_run.status_code == 200, restore_run.text
    payload = restore_run.json()
    assert payload["run_status"] == "completed"
    assert payload["approval_status"] == "approved_once"
    assert payload["selected_action_count"] == 1
    assert payload["restored_action_count"] == 1
    assert payload["staged_remote_action_count"] == 0
    assert payload["failed_action_count"] == 0
    assert payload["connector_batch_manifest_path"] is None
    assert payload["selected_target_id"] is None
    assert payload["selected_target_probe_status"] == "unknown"
    assert payload["availability_diagnostics"]["candidate_count"] == 0
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["quality_gate_blocker_count"] == 0
    assert payload["pending_question_count"] == 0

    assert not archived_path.exists()
    assert (workspace / "dupes" / "roadmap-copy.txt").exists()

    run_manifest = json.loads((workspace / payload["run_manifest_path"]).read_text(encoding="utf-8"))
    assert run_manifest["run_status"] == "completed"
    assert run_manifest["selected_target_id"] is None
    assert run_manifest["selected_target_probe_status"] == "unknown"
    assert run_manifest["availability_diagnostics"]["candidate_count"] == 0
    assert run_manifest["selected_target_requirement_gaps"] == {}
    assert run_manifest["selected_target_rejected_reasons"] == []
    assert run_manifest["quality_gate_blocker_count"] == 0
    assert run_manifest["pending_question_count"] == 0
    assert run_manifest["restored_action_count"] == 1
    assert run_manifest["action_results"][0]["execution_status"] == "restored"


def test_file_graph_governance_apply_route_stages_remote_connector_batch_after_approval(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})
    monkeypatch.setattr(
        "manager.security_service.evaluate_action",
        lambda db, payload, project=None: {
            "policy": {},
            "assessment": {"risk_level": "high"},
            "decision": "pending",
            "reason": "Remote archive staging requires explicit approval.",
        },
    )
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": [],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)

    workspace = tmp_path / "workspace-file-graph-apply-remote"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    local_content = "shared duplicate plan\n"
    local_path = workspace / "docs" / "plan.md"
    local_path.write_text(local_content, encoding="utf-8")
    duplicate_sha = hashlib.sha256(local_path.read_bytes()).hexdigest()
    artifacts_root = workspace / "artifacts" / "file-graph"
    artifacts_root.mkdir(parents=True)
    (artifacts_root / "google_drive-crawl.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_type": "cloud_traversal_request",
                        "provider_id": "google_drive",
                        "action_id": "list",
                        "root_selector": "shared_drive",
                        "query": "*",
                        "output_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    }
                ),
                json.dumps(
                    {
                        "record_type": "cloud_file_item",
                        "provider_id": "google_drive",
                        "item_id": "copy-plan",
                        "remote_path": "cloud://google_drive/Shared/plan-copy.md",
                        "relative_path_hint": "Shared/plan-copy.md",
                        "classification": "document",
                        "size_bytes": len(local_content.encode("utf-8")),
                        "sha256": duplicate_sha,
                        "source_artifact_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Apply Remote Demo",
            "idea": "Need governed remote duplicate staging.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    remote_action = next(
        item for item in plan.json()["proposed_actions"] if item["action_type"] == "remote_archive_candidate"
    )
    action_id = remote_action["action_id"]

    pending_apply = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id]},
    )
    assert pending_apply.status_code == 200, pending_apply.text
    pending_payload = pending_apply.json()
    assert pending_payload["run_status"] == "approval_required"
    assert pending_payload["selected_target_id"] is None
    assert pending_payload["selected_target_probe_status"] == "unknown"
    assert pending_payload["availability_diagnostics"]["candidate_count"] == 0
    assert pending_payload["selected_target_requirement_gaps"] == {}
    assert pending_payload["selected_target_rejected_reasons"] == []
    assert pending_payload["quality_gate_blocker_count"] == 0
    assert pending_payload["pending_question_count"] == 0
    approval_id = pending_payload["approval_id"]

    approval = client.post(
        f"/api/projects/{project_id}/approvals/{approval_id}/approve-once",
        json={"project_id": project_id},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["status"] == "approved_once"

    apply_run = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id], "approval_id": approval_id},
    )
    assert apply_run.status_code == 200, apply_run.text
    payload = apply_run.json()
    assert payload["run_status"] == "partial"
    assert payload["applied_action_count"] == 0
    assert payload["staged_remote_action_count"] == 1
    assert payload["failed_action_count"] == 0
    assert payload["connector_batch_manifest_path"] is not None
    assert payload["action_results"][0]["execution_status"] == "staged"
    assert payload["selected_target_id"] is None
    assert payload["selected_target_probe_status"] == "unknown"
    assert payload["availability_diagnostics"]["candidate_count"] == 0
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["quality_gate_blocker_count"] == 0
    assert payload["pending_question_count"] == 0

    connector_batch = json.loads((workspace / payload["connector_batch_manifest_path"]).read_text(encoding="utf-8"))
    assert connector_batch["status"] == "staged"
    assert connector_batch["selected_target_id"] is None
    assert connector_batch["selected_target_probe_status"] == "unknown"
    assert connector_batch["availability_diagnostics"]["candidate_count"] == 0
    assert connector_batch["selected_target_requirement_gaps"] == {}
    assert connector_batch["selected_target_rejected_reasons"] == []
    assert connector_batch["quality_gate_blocker_count"] == 0
    assert connector_batch["pending_question_count"] == 0
    assert connector_batch["action_count"] == 1
    assert connector_batch["actions"][0]["provider_id"] == "google_drive"
    assert connector_batch["actions"][0]["operation"] == "archive"


def test_file_graph_connector_batch_execute_route_runs_staged_remote_actions(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})
    monkeypatch.setattr(
        "manager.security_service.evaluate_action",
        lambda db, payload, project=None: {
            "policy": {},
            "assessment": {"risk_level": "high"},
            "decision": "pending",
            "reason": "Remote archive staging requires explicit approval.",
        },
    )
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": [],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)

    workspace = tmp_path / "workspace-file-graph-connector-execute"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    local_content = "shared duplicate plan\n"
    local_path = workspace / "docs" / "plan.md"
    local_path.write_text(local_content, encoding="utf-8")
    duplicate_sha = hashlib.sha256(local_path.read_bytes()).hexdigest()
    artifacts_root = workspace / "artifacts" / "file-graph"
    artifacts_root.mkdir(parents=True)
    (artifacts_root / "google_drive-crawl.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_type": "cloud_traversal_request",
                        "provider_id": "google_drive",
                        "action_id": "list",
                        "root_selector": "shared_drive",
                        "query": "*",
                        "output_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    }
                ),
                json.dumps(
                    {
                        "record_type": "cloud_file_item",
                        "provider_id": "google_drive",
                        "item_id": "copy-plan",
                        "remote_path": "cloud://google_drive/Shared/plan-copy.md",
                        "relative_path_hint": "Shared/plan-copy.md",
                        "classification": "document",
                        "size_bytes": len(local_content.encode("utf-8")),
                        "sha256": duplicate_sha,
                        "source_artifact_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Connector Execute Demo",
            "idea": "Need staged remote duplicate batches to execute through Mission Control.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    remote_action = next(
        item for item in plan.json()["proposed_actions"] if item["action_type"] == "remote_archive_candidate"
    )
    action_id = remote_action["action_id"]

    pending_apply = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id]},
    )
    assert pending_apply.status_code == 200, pending_apply.text
    approval_id = pending_apply.json()["approval_id"]

    approval = client.post(
        f"/api/projects/{project_id}/approvals/{approval_id}/approve-once",
        json={"project_id": project_id},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["status"] == "approved_once"

    apply_run = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id], "approval_id": approval_id},
    )
    assert apply_run.status_code == 200, apply_run.text
    connector_batch_manifest_path = apply_run.json()["connector_batch_manifest_path"]

    def _preview_cloud_archive(db, project, *, family, action_id, params):
        assert family == "cloud_storage"
        assert action_id == "archive"
        assert params["provider"] == "google_drive"
        return {
            "family": family,
            "action_id": action_id,
            "title": "Archive file",
            "summary": "Preview archive for google_drive.",
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "command": None,
            "risk_level": "high",
            "permission_policy": "ask_every_time",
            "preview_supported": True,
            "mutates_remote_state": True,
            "requires_confirmation": True,
            "required_params": ["source_path", "destination_path"],
            "missing_params": [],
            "params_complete": True,
            "supports_pagination": False,
            "supports_streaming_output": False,
            "supports_file_output": False,
            "supports_throttle_controls": True,
            "provider": "google_drive",
            "provider_candidates": ["google_drive"],
            "provider_signal_breakdown": {"google_drive": {"connection_status": "connected"}},
            "resolved_provider_evidence": {"connection_status": "connected"},
            "cli_only_candidates_suppressed": [],
            "provider_resolution_state": "resolved",
            "provider_support_mode": "provider_specific",
            "supported_providers": ["google_drive"],
            "supported_provider_count": 1,
            "provider_lane_resolved": True,
            "provider_context_verified": True,
            "provider_context_source": "connection",
            "provider_context_status": "verified",
            "provider_verification_required": False,
            "provider_verification_reason": None,
            "verification_scope": None,
            "executable_name": None,
            "defaulted_params": {},
            "command_ready": False,
            "execution_mode": "guided_remote",
            "execution_block_reason": None,
            "blocking_reasons": [],
            "blocking_reason_count": 0,
            "preflight_ready": True,
            "confirmation_eligible": True,
            "ready_to_execute": False,
            "safe_command_eligible": False,
            "safe_command_reason": "non_local_execution",
            "context_required": False,
            "context_requirement_reason": None,
            "context_available": True,
            "suppressed_command_reason": None,
            "provider_guidance": None,
            "notes": ["Provider lane is verified for guided remote archive execution."],
        }

    def _execute_cloud_archive(db, project, *, family, action_id, params, confirmed):
        assert confirmed is True
        assert family == "cloud_storage"
        assert action_id == "archive"
        assert params["provider"] == "google_drive"
        return {
            "family": family,
            "action_id": action_id,
            "status": "completed",
            "summary": "Archived remote duplicate.",
            "stdout": "archived remote duplicate",
            "stderr": "",
            "returncode": 0,
            "risk_level": "high",
            "notes": ["Executed through governed provider adapter."],
        }

    monkeypatch.setattr("manager.service.preview_project_integration_action", _preview_cloud_archive)
    monkeypatch.setattr("manager.service.execute_project_integration_action", _execute_cloud_archive)

    execute = client.post(
        f"/api/projects/{project_id}/file-graph-governance/connector-batch/execute",
        json={"batch_manifest_path": connector_batch_manifest_path, "approval_id": approval_id},
    )
    assert execute.status_code == 200, execute.text
    payload = execute.json()
    assert payload["run_status"] == "completed"
    assert payload["approval_status"] == "approved_once"
    assert payload["batch_manifest_path"] == connector_batch_manifest_path
    assert payload["selected_target_id"] is None
    assert payload["selected_target_probe_status"] == "unknown"
    assert payload["availability_diagnostics"]["candidate_count"] == 0
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["quality_gate_blocker_count"] == 0
    assert payload["pending_question_count"] == 0
    assert payload["selected_action_count"] == 1
    assert payload["executed_action_count"] == 1
    assert payload["failed_action_count"] == 0
    assert payload["blocked_action_count"] == 0
    assert payload["action_results"][0]["execution_status"] == "executed"

    connector_batch = json.loads((workspace / connector_batch_manifest_path).read_text(encoding="utf-8"))
    assert connector_batch["status"] == "completed"
    assert connector_batch["selected_target_id"] is None
    assert connector_batch["selected_target_probe_status"] == "unknown"
    assert connector_batch["availability_diagnostics"]["candidate_count"] == 0
    assert connector_batch["selected_target_requirement_gaps"] == {}
    assert connector_batch["selected_target_rejected_reasons"] == []
    assert connector_batch["quality_gate_blocker_count"] == 0
    assert connector_batch["pending_question_count"] == 0
    assert connector_batch["executed_action_count"] == 1
    assert connector_batch["action_results"][0]["execution_status"] == "executed"

    run_manifest = json.loads((workspace / payload["run_manifest_path"]).read_text(encoding="utf-8"))
    assert run_manifest["run_status"] == "completed"
    assert run_manifest["selected_target_id"] is None
    assert run_manifest["selected_target_probe_status"] == "unknown"
    assert run_manifest["availability_diagnostics"]["candidate_count"] == 0
    assert run_manifest["selected_target_requirement_gaps"] == {}
    assert run_manifest["selected_target_rejected_reasons"] == []
    assert run_manifest["quality_gate_blocker_count"] == 0
    assert run_manifest["pending_question_count"] == 0
    assert run_manifest["executed_action_count"] == 1


def test_file_graph_connector_batch_execute_route_runs_real_cloud_archive_provider_command(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})
    monkeypatch.setattr(
        "manager.security_service.evaluate_action",
        lambda db, payload, project=None: {
            "policy": {},
            "assessment": {"risk_level": "high"},
            "decision": "pending",
            "reason": "Remote archive staging requires explicit approval.",
        },
    )
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": [],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "rclone" else None,
    )
    invoked: dict[str, object] = {}

    def _fake_run(args, **kwargs):
        invoked["args"] = args
        invoked["kwargs"] = kwargs

        class _Completed:
            returncode = 0
            stdout = "remote archive complete"
            stderr = ""

        return _Completed()

    monkeypatch.setattr("integration_registry.subprocess.run", _fake_run)

    workspace = tmp_path / "workspace-file-graph-connector-execute-real"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    local_content = "shared duplicate plan\n"
    local_path = workspace / "docs" / "plan.md"
    local_path.write_text(local_content, encoding="utf-8")
    duplicate_sha = hashlib.sha256(local_path.read_bytes()).hexdigest()
    artifacts_root = workspace / "artifacts" / "file-graph"
    artifacts_root.mkdir(parents=True)
    (artifacts_root / "google_drive-crawl.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_type": "cloud_traversal_request",
                        "provider_id": "google_drive",
                        "action_id": "list",
                        "root_selector": "shared_drive",
                        "query": "*",
                        "output_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    }
                ),
                json.dumps(
                    {
                        "record_type": "cloud_file_item",
                        "provider_id": "google_drive",
                        "item_id": "copy-plan",
                        "remote_path": "cloud://google_drive/Shared/plan-copy.md",
                        "relative_path_hint": "Shared/plan-copy.md",
                        "classification": "document",
                        "size_bytes": len(local_content.encode("utf-8")),
                        "sha256": duplicate_sha,
                        "source_artifact_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Connector Execute Real Demo",
            "idea": "Need staged remote duplicate batches to execute through Mission Control.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    remote_action = next(
        item for item in plan.json()["proposed_actions"] if item["action_type"] == "remote_archive_candidate"
    )
    action_id = remote_action["action_id"]

    pending_apply = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id]},
    )
    assert pending_apply.status_code == 200, pending_apply.text
    approval_id = pending_apply.json()["approval_id"]

    approval = client.post(
        f"/api/projects/{project_id}/approvals/{approval_id}/approve-once",
        json={"project_id": project_id},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["status"] == "approved_once"

    apply_run = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id], "approval_id": approval_id},
    )
    assert apply_run.status_code == 200, apply_run.text
    connector_batch_manifest_path = apply_run.json()["connector_batch_manifest_path"]

    execute = client.post(
        f"/api/projects/{project_id}/file-graph-governance/connector-batch/execute",
        json={"batch_manifest_path": connector_batch_manifest_path, "approval_id": approval_id},
    )
    assert execute.status_code == 200, execute.text
    payload = execute.json()
    assert payload["run_status"] == "completed"
    assert payload["executed_action_count"] == 1
    assert payload["failed_action_count"] == 0
    assert payload["blocked_action_count"] == 0
    assert payload["action_results"][0]["execution_status"] == "executed"
    assert invoked["args"] == [
        "rclone",
        "moveto",
        "google_drive:Shared/plan-copy.md",
        "google_drive:archive/review/duplicates/google_drive/Shared__plan-copy.md",
    ]

    connector_batch = json.loads((workspace / connector_batch_manifest_path).read_text(encoding="utf-8"))
    assert connector_batch["status"] == "completed"
    assert connector_batch["executed_action_count"] == 1
    assert connector_batch["action_results"][0]["execution_status"] == "executed"


def test_file_graph_connector_batch_execute_route_runs_real_cloud_restore_provider_command(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})
    monkeypatch.setattr(
        "manager.security_service.evaluate_action",
        lambda db, payload, project=None: {
            "policy": {},
            "assessment": {"risk_level": "high"},
            "decision": "pending",
            "reason": "Remote restore staging requires explicit approval.",
        },
    )
    normalized_registry = {
        "connections": {
            "cloud_storage": {
                "family": "cloud_storage",
                "status": "connected",
                "providers": ["google_drive"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": [],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "rclone" else None,
    )
    invoked: dict[str, object] = {}

    def _fake_run(args, **kwargs):
        invoked["args"] = args
        invoked["kwargs"] = kwargs

        class _Completed:
            returncode = 0
            stdout = "remote restore complete"
            stderr = ""

        return _Completed()

    monkeypatch.setattr("integration_registry.subprocess.run", _fake_run)

    workspace = tmp_path / "workspace-file-graph-connector-restore-real"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    local_content = "shared duplicate plan\n"
    local_path = workspace / "docs" / "plan.md"
    local_path.write_text(local_content, encoding="utf-8")
    duplicate_sha = hashlib.sha256(local_path.read_bytes()).hexdigest()
    artifacts_root = workspace / "artifacts" / "file-graph"
    artifacts_root.mkdir(parents=True)
    (artifacts_root / "google_drive-crawl.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_type": "cloud_traversal_request",
                        "provider_id": "google_drive",
                        "action_id": "list",
                        "root_selector": "shared_drive",
                        "query": "*",
                        "output_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    }
                ),
                json.dumps(
                    {
                        "record_type": "cloud_file_item",
                        "provider_id": "google_drive",
                        "item_id": "copy-plan",
                        "remote_path": "cloud://google_drive/Shared/plan-copy.md",
                        "relative_path_hint": "Shared/plan-copy.md",
                        "classification": "document",
                        "size_bytes": len(local_content.encode("utf-8")),
                        "sha256": duplicate_sha,
                        "source_artifact_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Connector Restore Real Demo",
            "idea": "Need staged remote duplicate restores to execute through Mission Control.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    remote_action = next(
        item for item in plan.json()["proposed_actions"] if item["action_type"] == "remote_archive_candidate"
    )
    action_id = remote_action["action_id"]

    pending_restore = client.post(
        f"/api/projects/{project_id}/file-graph-governance/restore",
        json={"action_ids": [action_id]},
    )
    assert pending_restore.status_code == 200, pending_restore.text
    restore_approval_id = pending_restore.json()["approval_id"]

    restore_approval = client.post(
        f"/api/projects/{project_id}/approvals/{restore_approval_id}/approve-once",
        json={"project_id": project_id},
    )
    assert restore_approval.status_code == 200, restore_approval.text
    assert restore_approval.json()["status"] == "approved_once"

    restore_run = client.post(
        f"/api/projects/{project_id}/file-graph-governance/restore",
        json={"action_ids": [action_id], "approval_id": restore_approval_id},
    )
    assert restore_run.status_code == 200, restore_run.text
    restore_payload = restore_run.json()
    assert restore_payload["run_status"] == "partial"
    assert restore_payload["staged_remote_action_count"] == 1
    connector_batch_manifest_path = restore_payload["connector_batch_manifest_path"]

    execute = client.post(
        f"/api/projects/{project_id}/file-graph-governance/connector-batch/execute",
        json={"batch_manifest_path": connector_batch_manifest_path, "approval_id": restore_approval_id},
    )
    assert execute.status_code == 200, execute.text
    payload = execute.json()
    assert payload["run_status"] == "completed"
    assert payload["executed_action_count"] == 1
    assert payload["failed_action_count"] == 0
    assert payload["blocked_action_count"] == 0
    assert payload["action_results"][0]["execution_status"] == "executed"
    assert invoked["args"] == [
        "rclone",
        "moveto",
        "google_drive:archive/review/duplicates/google_drive/Shared__plan-copy.md",
        "google_drive:Shared/plan-copy.md",
    ]

    connector_batch = json.loads((workspace / connector_batch_manifest_path).read_text(encoding="utf-8"))
    assert connector_batch["status"] == "completed"
    assert connector_batch["executed_action_count"] == 1
    assert connector_batch["action_results"][0]["execution_status"] == "executed"


def test_file_graph_connector_batch_execute_route_blocks_when_batch_is_not_execution_ready(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    preview_called = {"value": False}
    execute_called = {"value": False}

    def _preview(*args, **kwargs):
        preview_called["value"] = True
        return {}

    def _execute(*args, **kwargs):
        execute_called["value"] = True
        return {}

    monkeypatch.setattr("manager.service.preview_project_integration_action", _preview)
    monkeypatch.setattr("manager.service.execute_project_integration_action", _execute)

    workspace = tmp_path / "workspace-file-graph-connector-execute-blocked"
    workspace.mkdir()
    artifacts_root = workspace / "artifacts" / "file-graph" / "apply-runs" / "manual-batch"
    artifacts_root.mkdir(parents=True)

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Connector Execute Blocked Demo",
            "idea": "Unsafe staged connector mutations should stop before provider execution.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    batch_manifest_path = artifacts_root / "connector-mutation-batch.json"
    batch_manifest_path.write_text(
        json.dumps(
            {
                "generated_by": "mission-control",
                "project_id": project_id,
                "project_name": "File Graph Connector Execute Blocked Demo",
                "status": "staged",
                "supports_bulk_planning": True,
                "approval_required": False,
                "approval_id": None,
                "approval_status": None,
                "selected_target_id": None,
                "selected_target_probe_status": "unknown",
                "availability_diagnostics": {"candidate_count": 0},
                "selected_target_requirement_gaps": {},
                "selected_target_rejected_reasons": [],
                "quality_gate_blocker_count": 2,
                "pending_question_count": 1,
                "blocking_reasons": ["destructive_bulk_actions_are_not_approval_gated"],
                "action_count": 1,
                "actions": [
                    {
                        "action_id": "remote-restore-1",
                        "provider_id": "google_drive",
                        "operation": "restore",
                        "source_path": "cloud://google_drive/archive/review/duplicates/google_drive/Shared__plan-copy.md",
                        "destination_path": "cloud://google_drive/Shared/plan-copy.md",
                        "requires_connector_approval": True,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    execute = client.post(
        f"/api/projects/{project_id}/file-graph-governance/connector-batch/execute",
        json={"batch_manifest_path": batch_manifest_path.relative_to(workspace).as_posix()},
    )
    assert execute.status_code == 200, execute.text
    payload = execute.json()
    assert payload["run_status"] == "blocked"
    assert payload["approval_id"] is None
    assert payload["quality_gate_blocker_count"] == 2
    assert payload["pending_question_count"] == 1
    assert "destructive_bulk_actions_are_not_approval_gated" in payload["blocking_reasons"]
    assert "2 quality gate(s) still block a clean file-graph handoff." in payload["blocking_reasons"]
    assert "1 pending decision question(s) still block destructive file-graph execution." in payload["blocking_reasons"]
    assert payload["executed_action_count"] == 0
    assert payload["blocked_action_count"] == 1
    assert preview_called["value"] is False
    assert execute_called["value"] is False


def test_file_graph_governance_plan_route_respects_quality_and_approval_blockers(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.service.build_file_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Bulk planning exists, but destructive policy and gates are still busted.",
            "recommended_operation_mode": "local_only",
            "supports_bulk_planning": True,
            "destructive_actions_require_approval": False,
            "notes": ["Approval gating is disabled for destructive file mutations."],
        },
    )
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 2})
    workspace = tmp_path / "workspace-file-graph-plan-blocked"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    (workspace / "notes.txt").write_text("same content\n", encoding="utf-8")
    dupes = workspace / "dupes"
    dupes.mkdir()
    (dupes / "notes-copy.txt").write_text("same content\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Plan Blocker Demo",
            "idea": "Need file-graph planning to stop pretending unsafe execution is ready.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "partial"
    assert payload["destructive_actions_require_approval"] is False
    assert "destructive_bulk_actions_are_not_approval_gated" in payload["blocking_reasons"]
    assert "2 quality gate(s) still block a clean file-graph handoff." in payload["blocking_reasons"]
    assert any("execution-ready" in note for note in payload["notes"])

    dry_run_manifest = json.loads((workspace / "artifacts" / "file-graph" / "bulk-rename-dry-run-plan.json").read_text(encoding="utf-8"))
    assert "destructive_bulk_actions_are_not_approval_gated" in dry_run_manifest["blocking_reasons"]
    assert "2 quality gate(s) still block a clean file-graph handoff." in dry_run_manifest["blocking_reasons"]


def test_file_graph_governance_apply_and_restore_block_when_plan_is_not_execution_ready(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.service.build_file_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Bulk planning exists, but destructive policy and gates are still busted.",
            "recommended_operation_mode": "local_only",
            "supports_bulk_planning": True,
            "destructive_actions_require_approval": False,
            "notes": ["Approval gating is disabled for destructive file mutations."],
        },
    )
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 2})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 1})
    workspace = tmp_path / "workspace-file-graph-apply-restore-blocked"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    (workspace / "dupes").mkdir()
    (workspace / "docs" / "roadmap.txt").write_text("same content\n", encoding="utf-8")
    (workspace / "dupes" / "roadmap-copy.txt").write_text("same content\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "File Graph Execution Blocker Demo",
            "idea": "Unsafe file-graph execution should stop before mutation, not after regret.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/file-graph-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    action_id = payload["proposed_actions"][0]["action_id"]

    apply_run = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": [action_id]},
    )
    assert apply_run.status_code == 200, apply_run.text
    apply_payload = apply_run.json()
    assert apply_payload["run_status"] == "blocked"
    assert apply_payload["approval_id"] is None
    assert apply_payload["quality_gate_blocker_count"] == 2
    assert apply_payload["pending_question_count"] == 1
    assert "destructive_bulk_actions_are_not_approval_gated" in apply_payload["blocking_reasons"]
    assert "2 quality gate(s) still block a clean file-graph handoff." in apply_payload["blocking_reasons"]
    assert "1 pending decision question(s) still block destructive file-graph execution." in apply_payload["blocking_reasons"]
    assert apply_payload["applied_action_count"] == 0
    assert apply_payload["staged_remote_action_count"] == 0

    restore_run = client.post(
        f"/api/projects/{project_id}/file-graph-governance/restore",
        json={"action_ids": [action_id]},
    )
    assert restore_run.status_code == 200, restore_run.text
    restore_payload = restore_run.json()
    assert restore_payload["run_status"] == "blocked"
    assert restore_payload["approval_id"] is None
    assert restore_payload["quality_gate_blocker_count"] == 2
    assert restore_payload["pending_question_count"] == 1
    assert "destructive_bulk_actions_are_not_approval_gated" in restore_payload["blocking_reasons"]
    assert "2 quality gate(s) still block a clean file-graph handoff." in restore_payload["blocking_reasons"]
    assert "1 pending decision question(s) still block destructive file-graph execution." in restore_payload["blocking_reasons"]
    assert restore_payload["restored_action_count"] == 0
    assert restore_payload["staged_remote_action_count"] == 0


def test_native_app_validation_governance_summary_prefers_transport_recording_delivery_signal(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-native-app-transport-recording-gap"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_project_artifact_registry",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "artifacts",
            "artifact_count": 3,
            "artifact_paths": [
                "builds/android/app-release.apk",
                "artifacts/logs/device.log",
                "artifacts/screenshots/home.png",
            ],
            "validation_evidence_target_count": 1,
            "validation_evidence_targets": ["artifacts/logs/device.log"],
            "execution_entrypoint_count": 1,
            "execution_entrypoints": ["./gradlew connectedCheck"],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Android lane is ready.",
            "selected_target_id": "android-lab",
            "lane_count": 1,
            "ready_lane_count": 1,
            "partial_lane_count": 0,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["android"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": [],
            "selected_ready_lane_ids": ["android"],
            "lanes": [
                {
                    "lane_id": "android",
                    "title": "Android Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["android-lab"],
                    "target_count": 1,
                    "selected_target_ids": ["android-lab"],
                    "os_families": ["linux"],
                    "toolchains": ["adb", "gradle"],
                    "command_families": ["adb", "gradle"],
                    "recommended_commands": ["./gradlew connectedCheck"],
                    "notes": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Artifact transport is partial because recording delivery is missing.",
            "selected_target_id": "android-lab",
            "preflight_ready": False,
            "sync_enabled": True,
            "recommended_transport_mode": "blocked",
            "blocking_reasons": ["session_recording_artifact_missing_after_remote_execution"],
            "session_recording_status": "partial",
            "session_recording_required": True,
            "session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/android-lab.cast"
            ],
            "produced_session_recording_artifact_paths": [],
            "missing_session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/android-lab.cast"
            ],
            "remote_session_recording_artifact_paths": [
                "/srv/android/artifacts/remote-execution-governance/session-recordings/android-lab.cast"
            ],
            "ready_platform_lanes": ["android"],
            "selected_ready_platform_lanes": ["android"],
            "target_backed_ready_platform_lanes": ["android"],
            "partial_platform_lanes": [],
            "notes": ["Session recording was declared but not produced."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
            "artifact_contract": {"sync_enabled": True, "required": True, "preflight_ready": True},
            "connector_contract": {"available_families": ["source_control"], "preflight_ready": True},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_game_engine_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "No engine surfaces detected.",
            "governance_status": "not_applicable",
            "detected_engines": [],
            "scene_or_map_count": 0,
            "scene_or_map_paths": [],
            "automation_signal_count": 0,
            "automation_signal_paths": [],
            "screenshot_artifact_count": 0,
            "screenshot_artifact_paths": [],
            "playable_contract_status": "not_applicable",
            "normalized_results_summary_path": None,
            "normalized_summary_count": 0,
            "normalized_passed_count": 0,
            "normalized_failed_count": 0,
            "normalized_missing_count": 0,
            "normalized_publish_ready": False,
            "normalized_results_status": "not_applicable",
            "publish_gate_status": "not_applicable",
            "publish_blockers": [],
            "recommended_fixes": [],
            "notes": [],
        },
    )
    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution",
        lambda db, project: {
            "selected_target_id": "android-lab",
            "selected_target": {
                "id": "android-lab",
                "label": "Android Lab",
                "transport": "ssh",
                "host": "android-lab.local",
                "workspace_root": "/srv/android/work",
            },
            "policy": {"enabled": True, "require_session_recording": True},
            "artifact_contract": {
                "selected_artifact_root": "/srv/android/artifacts",
                "remote_workspace_root": "/srv/android/work",
            },
            "broker_contract": {"require_session_recording": True, "session_recording_enabled": True},
            "result_contract": {
                "session_recording_artifact_paths": [
                    "artifacts/remote-execution-governance/session-recordings/android-lab.cast"
                ],
                "remote_session_recording_artifact_paths": [
                    "/srv/android/artifacts/remote-execution-governance/session-recordings/android-lab.cast"
                ],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native App Transport Recording Gap Demo",
            "idea": "Transport delivery should gate native validation evidence.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/native-app-validation-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["session_recording_status"] == "partial"
    assert payload["session_recording_required"] is True
    assert payload["produced_session_recording_artifact_count"] == 0
    assert payload["produced_session_recording_artifact_paths"] == []
    assert payload["missing_session_recording_artifact_count"] == 1
    assert payload["missing_session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/android-lab.cast"
    ]
    assert payload["evidence_pipeline_status"] == "partial"
    assert payload["governance_status"] == "partial"
    assert "Artifact transport is blocked, so even valid app artifacts cannot be moved to the right platform lane safely." in payload["blocking_reasons"]
    assert "Session recording is required for the selected brokered validation lane, but the workspace is still missing the produced recording artifact." in payload["blocking_reasons"]
    assert "Produce the missing session recording artifact paths inside the workspace before treating the validation bundle as publishable." in payload["recommended_fixes"]


def test_design_transfer_summary_route_surfaces_figma_artifacts_and_browser_lane(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Design exports and browser tooling are present.",
            "tools": [
                {
                    "id": "playwright",
                    "category": "validation",
                    "installed": True,
                    "configured": True,
                    "status": "ready",
                    "notes": [],
                    "recommended_commands": ["playwright test"],
                }
            ],
            "packs": [],
            "artifact_paths": [
                "artifacts/design/mock-home.png",
                "artifacts/design/design-tokens.json",
            ],
            "artifact_kind_summaries": ["image:1", "design_tokens:1"],
            "artifact_inspection_commands": ["python inspect_design_assets.py"],
            "config_review_paths": [],
            "config_review_commands": [],
            "validation_evidence_targets": ["artifacts/design/mock-home.png"],
            "execution_entrypoints": [],
            "notebook_paths": [],
            "recommended_next_steps": ["Sync the design tokens into the web app."],
            "product_lane_statuses": ["browser:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": ["playwright test"],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
        },
    )
    normalized_registry = {
        "connections": {
            "figma": {
                "family": "figma",
                "status": "connected",
                "providers": ["figma"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["Design API access is wired."],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-design-transfer"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Design Transfer Demo",
            "idea": "Need a proper design-to-code bridge.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    summary = client.get(f"/api/projects/{project_id}/design-transfer/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["project_id"] == project_id
    assert payload["recommended_ingestion_mode"] == "figma_plus_artifacts"
    assert payload["figma_connected"] is True
    assert payload["design_artifact_count"] == 2
    assert payload["browser_lane_status"] == "partial"
    assert payload["supports_visual_regression"] is True
    assert payload["code_conformance_ready"] is False
    assert "artifacts/design/mock-home.png" in payload["design_artifact_paths"]
    assert ".png" in payload["design_artifact_formats"]
    assert ".json" in payload["design_artifact_formats"]


def test_design_transfer_plan_route_generates_intent_and_conformance_manifests(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Design exports and browser tooling are present.",
            "tools": [
                {
                    "id": "playwright",
                    "category": "validation",
                    "installed": True,
                    "configured": True,
                    "status": "ready",
                    "notes": [],
                    "recommended_commands": ["playwright test"],
                }
            ],
            "packs": [],
            "artifact_paths": [
                "artifacts/design/mock-home.png",
                "artifacts/design/design-tokens.json",
            ],
            "artifact_kind_summaries": ["image:1", "design_tokens:1"],
            "artifact_inspection_commands": ["python inspect_design_assets.py"],
            "config_review_paths": [],
            "config_review_commands": [],
            "validation_evidence_targets": ["artifacts/design/mock-home.png"],
            "execution_entrypoints": [],
            "notebook_paths": [],
            "recommended_next_steps": ["Sync the design tokens into the web app."],
            "product_lane_statuses": ["browser:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": ["playwright test"],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
        },
    )
    normalized_registry = {
        "connections": {
            "figma": {
                "family": "figma",
                "status": "connected",
                "providers": ["figma"],
                "connection_source": "mission_control",
                "host_imported": False,
                "notes": ["Design API access is wired."],
            }
        }
    }
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    monkeypatch.setattr("remote_execution.normalize_integration_registry", lambda registry, accounts=None: normalized_registry)
    workspace = tmp_path / "workspace-design-transfer-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")
    src = workspace / "src"
    src.mkdir()
    (src / "Home.tsx").write_text("export function Home() { return <main>Home</main>; }\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Design Transfer Plan Demo",
            "idea": "Need governed design-to-code manifests, not screenshot telepathy.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/design-transfer/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["recommended_ingestion_mode"] == "figma_plus_artifacts"
    assert payload["figma_connected"] is True
    assert payload["browser_lane_status"] == "partial"
    assert payload["browser_lane_target_ids"] == []
    assert payload["design_artifact_count"] == 2
    assert payload["supports_visual_regression"] is True
    assert payload["code_conformance_ready"] is False
    assert payload["component_mapping_count"] == 2
    assert payload["conformance_check_count"] == 3
    assert payload["manifest_root"] == "artifacts/design-transfer"
    assert payload["design_intent_manifest_path"] == "artifacts/design-transfer/design-intent-transfer.json"
    assert payload["component_map_manifest_path"] == "artifacts/design-transfer/component-map.json"
    assert payload["screenshot_diff_plan_path"] == "artifacts/design-transfer/screenshot-diff-plan.json"
    assert payload["token_usage_plan_path"] == "artifacts/design-transfer/design-token-usage-plan.json"
    assert payload["aria_check_plan_path"] == "artifacts/design-transfer/dom-aria-check-plan.json"
    assert len(payload["component_mappings"]) == 2
    assert len(payload["conformance_checks"]) == 3

    assert (workspace / "artifacts" / "design-transfer" / "design-intent-transfer.json").exists()
    assert (workspace / "artifacts" / "design-transfer" / "component-map.json").exists()
    assert (workspace / "artifacts" / "design-transfer" / "screenshot-diff-plan.json").exists()
    assert (workspace / "artifacts" / "design-transfer" / "design-token-usage-plan.json").exists()
    assert (workspace / "artifacts" / "design-transfer" / "dom-aria-check-plan.json").exists()


def test_spatial_asset_governance_summary_route_surfaces_workflows_and_runner_state(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr(
        "manager.service.build_decision_audit_summary",
        lambda db, project: {"pending_approval_count": 0, "pending_question_count": 0},
    )
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Spatial validation signals are present.",
            "tools": [
                {
                    "id": "playwright",
                    "category": "validation",
                    "installed": True,
                    "configured": True,
                    "status": "ready",
                    "notes": [],
                    "recommended_commands": ["playwright test"],
                }
            ],
            "packs": [],
            "artifact_paths": ["artifacts/renders/frame_0001.png"],
            "artifact_kind_summaries": ["image:1"],
            "artifact_inspection_commands": ["python inspect_render.py"],
            "config_review_paths": ["configs/streaming.yaml"],
            "config_review_commands": ["python review_config.py"],
            "validation_evidence_targets": ["artifacts/renders/frame_0001.png"],
            "execution_entrypoints": [],
            "notebook_paths": [],
            "recommended_next_steps": ["Run the browser render probe against the latest scene export."],
            "product_lane_statuses": ["browser:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": ["playwright test"],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
            "spatial3d_repo": {
                "enabled": True,
                "mode": "spatial3d_geospatial",
                "frameworks": ["OpenUSD", "3D Gaussian Splatting"],
                "build_commands": ["python -m pip install -e ."],
                "render_commands": [],
                "conversion_commands": ["python scripts/convert_splats.py"],
                "capture_commands": ["python pipeline/capture.py"],
                "benchmark_commands": ["python benchmarks/render_benchmark.py"],
                "product_workflows": ["browser_renderer", "visual_regression", "cloud_reconstruction", "dataset_quality"],
                "validation_notes": ["Fail fast on weak capture coverage before expensive reconstruction starts."],
                "asset_paths": ["assets/city.splat", "assets/city.usda"],
                "scene_paths": ["assets/city.usda"],
                "config_paths": ["configs/streaming.yaml"],
            },
            "spatial3d_validation_plan": {
                "available": True,
                "status": "ready",
                "summary": "Spatial validation is ready.",
                "repo_mode_enabled": True,
                "repo_mode": "spatial3d_geospatial",
                "steps": [
                    {"title": "Run browser probe", "command": "playwright test", "type": "inspect", "status": "pending"},
                    {"title": "Run benchmark", "command": "python benchmarks/render_benchmark.py", "type": "benchmark", "status": "pending"},
                ],
                "blockers": [],
                "recommended_fixes": [],
                "evidence_targets": ["render diff summary", "streaming benchmark output"],
                "product_workflows": ["browser_renderer", "visual_regression", "cloud_reconstruction", "dataset_quality"],
            },
        },
    )
    workspace = tmp_path / "workspace-spatial-governance"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Spatial Governance Demo",
            "idea": "Need a governed spatial lane.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    summary = client.get(f"/api/projects/{project_id}/spatial-asset-governance/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["project_id"] == project_id
    assert payload["repo_mode_enabled"] is True
    assert payload["governance_status"] == "partial"
    assert payload["repo_mode"] == "spatial3d_geospatial"
    assert payload["validation_status"] == "ready"
    assert payload["browser_lane_status"] == "partial"
    assert payload["headless_runner_status"] == "unavailable"
    assert payload["recommended_transport_mode"] == "blocked"
    assert payload["supports_visual_regression"] is True
    assert payload["primary_scene_path"] == "assets/city.usda"
    assert payload["asset_count"] == 2
    assert "browser_renderer" in payload["product_workflows"]
    assert "browser_renderer" in payload["recommended_feature_ids"]
    assert "visual_regression_3d" in payload["recommended_feature_ids"]
    assert ".splat" in payload["asset_extensions"]
    assert ".usda" in payload["asset_extensions"]
    assert "streaming benchmark output" in payload["validation_evidence_targets"]


def test_spatial_asset_governance_requires_selected_target_bound_headless_lane(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr(
        "manager.service.build_decision_audit_summary",
        lambda db, project: {"pending_approval_count": 0, "pending_question_count": 0},
    )
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Spatial validation signals are present.",
            "tools": [],
            "packs": [],
            "artifact_paths": ["artifacts/renders/frame_0001.png"],
            "artifact_kind_summaries": ["image:1"],
            "artifact_inspection_commands": ["python inspect_render.py"],
            "config_review_paths": ["configs/scene.yaml"],
            "config_review_commands": ["python review_config.py"],
            "validation_evidence_targets": ["artifacts/renders/frame_0001.png"],
            "execution_entrypoints": [],
            "notebook_paths": [],
            "recommended_next_steps": [],
            "product_lane_statuses": ["linux:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": ["python validate_scene.py"],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
            "spatial3d_repo": {
                "enabled": True,
                "mode": "spatial3d_scene_authoring",
                "frameworks": ["Blender", "OpenUSD"],
                "build_commands": ["python -m pip install -e ."],
                "render_commands": ["python render_scene.py"],
                "conversion_commands": [],
                "capture_commands": [],
                "benchmark_commands": ["python benchmarks/render_benchmark.py"],
                "product_workflows": ["scene_authoring"],
                "validation_notes": ["Scene validation is technically runnable."],
                "asset_paths": ["assets/set.blend", "assets/set.usda"],
                "scene_paths": ["assets/set.usda"],
                "config_paths": ["configs/scene.yaml"],
            },
            "spatial3d_validation_plan": {
                "available": True,
                "status": "ready",
                "summary": "Spatial validation is ready.",
                "repo_mode_enabled": True,
                "repo_mode": "spatial3d_scene_authoring",
                "steps": [
                    {"title": "Validate scene", "command": "python validate_scene.py", "type": "validate", "status": "pending"},
                ],
                "blockers": [],
                "recommended_fixes": [],
                "evidence_targets": ["render diff summary"],
                "product_workflows": ["scene_authoring"],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "A Linux lane exists, but only on another host while the selected target is browser-only.",
            "selected_target_id": "browser-dcc",
            "selected_ready_lane_ids": ["browser"],
            "lane_count": 3,
            "ready_lane_count": 2,
            "partial_lane_count": 0,
            "unavailable_lane_count": 1,
            "ready_lane_ids": ["browser", "linux"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": ["windows"],
            "lanes": [
                {
                    "lane_id": "browser",
                    "title": "Browser Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["browser-dcc"],
                    "target_count": 1,
                    "selected_target_ids": ["browser-dcc"],
                    "os_families": ["linux"],
                    "toolchains": ["playwright"],
                    "command_families": ["browser"],
                    "recommended_commands": ["playwright test"],
                    "notes": [],
                },
                {
                    "lane_id": "linux",
                    "title": "Linux Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["linux-render"],
                    "target_count": 1,
                    "selected_target_ids": [],
                    "os_families": ["linux"],
                    "toolchains": ["blender"],
                    "command_families": ["headless"],
                    "recommended_commands": ["python validate_scene.py"],
                    "notes": [],
                },
                {
                    "lane_id": "windows",
                    "title": "Windows Runner",
                    "status": "unavailable",
                    "summary": "unavailable",
                    "target_ids": [],
                    "target_count": 0,
                    "selected_target_ids": [],
                    "os_families": [],
                    "toolchains": [],
                    "command_families": [],
                    "recommended_commands": ["powershell -File .\\scripts\\validate.ps1"],
                    "notes": [],
                },
            ],
        },
    )

    workspace = tmp_path / "workspace-spatial-selected-target"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Spatial Selected Target Demo",
            "idea": "Need spatial governance to reject headless lanes on the wrong host.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    summary = client.get(f"/api/projects/{project_id}/spatial-asset-governance/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["governance_status"] == "blocked"
    assert payload["selected_target_id"] == "browser-dcc"
    assert payload["headless_runner_status"] == "unavailable"
    assert payload["browser_lane_status"] == "ready"
    assert payload["blocking_reasons"] == [
        "Headless scene validation is required here, but no Linux, Windows, or macOS runner lane is bound to the selected broker target."
    ]
    assert "Bind the selected broker target to a ready Linux, Windows, or macOS runner lane before pretending Blender or USD work is governed." in payload["recommended_fixes"]
    assert "Selected broker target is `browser-dcc` for spatial execution." in payload["notes"]

    plan = client.post(f"/api/projects/{project_id}/spatial-asset-governance/plan")
    assert plan.status_code == 200, plan.text
    plan_payload = plan.json()
    assert plan_payload["selected_target_id"] == "browser-dcc"


def test_spatial_asset_governance_plan_route_generates_scene_and_validation_manifests(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr(
        "manager.service.build_decision_audit_summary",
        lambda db, project: {"pending_approval_count": 0, "pending_question_count": 0},
    )
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Spatial validation signals are present.",
            "tools": [
                {
                    "id": "playwright",
                    "category": "validation",
                    "installed": True,
                    "configured": True,
                    "status": "ready",
                    "notes": [],
                    "recommended_commands": ["playwright test"],
                }
            ],
            "packs": [],
            "artifact_paths": ["artifacts/renders/frame_0001.png"],
            "artifact_kind_summaries": ["image:1"],
            "artifact_inspection_commands": ["python inspect_render.py"],
            "config_review_paths": ["configs/streaming.yaml"],
            "config_review_commands": ["python review_config.py"],
            "validation_evidence_targets": ["artifacts/renders/frame_0001.png"],
            "execution_entrypoints": [],
            "notebook_paths": [],
            "recommended_next_steps": ["Run the browser render probe against the latest scene export."],
            "product_lane_statuses": ["browser:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": ["playwright test"],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
            "spatial3d_repo": {
                "enabled": True,
                "mode": "spatial3d_geospatial",
                "frameworks": ["OpenUSD", "3D Gaussian Splatting"],
                "build_commands": ["python -m pip install -e ."],
                "render_commands": [],
                "conversion_commands": ["python scripts/convert_splats.py"],
                "capture_commands": ["python pipeline/capture.py"],
                "benchmark_commands": ["python benchmarks/render_benchmark.py"],
                "product_workflows": ["browser_renderer", "visual_regression", "cloud_reconstruction", "dataset_quality"],
                "validation_notes": ["Fail fast on weak capture coverage before expensive reconstruction starts."],
                "asset_paths": ["assets/city.splat", "assets/city.usda"],
                "scene_paths": ["assets/city.usda"],
                "config_paths": ["configs/streaming.yaml"],
            },
            "spatial3d_validation_plan": {
                "available": True,
                "status": "ready",
                "summary": "Spatial validation is ready.",
                "repo_mode_enabled": True,
                "repo_mode": "spatial3d_geospatial",
                "steps": [
                    {"title": "Run browser probe", "command": "playwright test", "type": "inspect", "status": "pending"},
                    {"title": "Run benchmark", "command": "python benchmarks/render_benchmark.py", "type": "benchmark", "status": "pending"},
                ],
                "blockers": [],
                "recommended_fixes": [],
                "evidence_targets": ["render diff summary", "streaming benchmark output"],
                "product_workflows": ["browser_renderer", "visual_regression", "cloud_reconstruction", "dataset_quality"],
            },
        },
    )
    workspace = tmp_path / "workspace-spatial-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Spatial Plan Demo",
            "idea": "Need governed spatial manifests, not post-hoc chaos.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/spatial-asset-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["repo_mode"] == "spatial3d_geospatial"
    assert payload["asset_count"] == 2
    assert payload["workflow_count"] == 4
    assert payload["validation_step_count"] == 2
    assert payload["manifest_root"] == "artifacts/spatial-governance"
    assert payload["scene_contract_path"] == "artifacts/spatial-governance/scene-contract.json"
    assert payload["asset_provenance_path"] == "artifacts/spatial-governance/asset-provenance.json"
    assert payload["visual_regression_plan_path"] == "artifacts/spatial-governance/visual-regression-plan.json"
    assert payload["export_validation_plan_path"] == "artifacts/spatial-governance/export-validation-plan.json"
    assert payload["approval_checkpoint_path"] == "artifacts/spatial-governance/approval-checkpoints.json"

    assert (workspace / "artifacts" / "spatial-governance" / "scene-contract.json").exists()
    assert (workspace / "artifacts" / "spatial-governance" / "asset-provenance.json").exists()
    assert (workspace / "artifacts" / "spatial-governance" / "visual-regression-plan.json").exists()
    assert (workspace / "artifacts" / "spatial-governance" / "export-validation-plan.json").exists()
    assert (workspace / "artifacts" / "spatial-governance" / "approval-checkpoints.json").exists()

    scene_contract = json.loads((workspace / "artifacts" / "spatial-governance" / "scene-contract.json").read_text(encoding="utf-8"))
    assert scene_contract["unit_system"] == "meters"
    assert scene_contract["transport_mode"] == "blocked"
    assert "usd" in scene_contract["export_targets"]
    assert "glb" in scene_contract["export_targets"]
    assert scene_contract["materials"]["completeness_required"] is True
    assert scene_contract["rigging"]["review_required"] is True
    assert "triangle_budget" in scene_contract["quality_gate_expectations"]
    assert scene_contract["approval_requirements"]["pre_export_required"] is True
    assert len(scene_contract["objects"]) == 2
    assert len(scene_contract["collections"]) == 2

    asset_provenance = json.loads((workspace / "artifacts" / "spatial-governance" / "asset-provenance.json").read_text(encoding="utf-8"))
    assert asset_provenance[0]["approval_required_before_publish"] is True
    assert "generation_method" in asset_provenance[0]
    assert "export_targets" in asset_provenance[0]

    visual_regression_plan = json.loads((workspace / "artifacts" / "spatial-governance" / "visual-regression-plan.json").read_text(encoding="utf-8"))
    assert visual_regression_plan["checks"]["black_frame_check"] is True
    assert visual_regression_plan["checks"]["overlay_artifact_check"] is True
    assert visual_regression_plan["diff_thresholds"]["max_pixel_ratio_delta"] == 0.02
    assert len(visual_regression_plan["fixed_camera_views"]) == 3

    export_validation_plan = json.loads((workspace / "artifacts" / "spatial-governance" / "export-validation-plan.json").read_text(encoding="utf-8"))
    assert "usd" in export_validation_plan["export_targets"]
    assert any(item["check_id"] == "manifold_geometry" for item in export_validation_plan["quality_checks"])
    assert export_validation_plan["budget_controls"]["triangle_budget_required"] is True

    approval_checkpoints = json.loads((workspace / "artifacts" / "spatial-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    checkpoint_ids = [item["checkpoint_id"] for item in approval_checkpoints["checkpoints"]]
    assert "provenance_review" in checkpoint_ids
    assert "export_validation_review" in checkpoint_ids


def test_spatial_asset_governance_summary_route_blocks_on_quality_gates_and_pending_approval(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Spatial validation signals are present.",
            "tools": [],
            "packs": [],
            "artifact_paths": ["artifacts/renders/frame_0001.png"],
            "artifact_kind_summaries": ["image:1"],
            "artifact_inspection_commands": ["python inspect_render.py"],
            "config_review_paths": ["configs/streaming.yaml"],
            "config_review_commands": ["python review_config.py"],
            "validation_evidence_targets": ["artifacts/renders/frame_0001.png"],
            "execution_entrypoints": [],
            "notebook_paths": [],
            "recommended_next_steps": [],
            "product_lane_statuses": ["browser:ready", "linux:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": ["playwright test", "python validate_scene.py"],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
            "spatial3d_repo": {
                "enabled": True,
                "mode": "spatial3d_scene_authoring",
                "frameworks": ["Blender", "OpenUSD"],
                "build_commands": ["python -m pip install -e ."],
                "render_commands": ["python render_scene.py"],
                "conversion_commands": [],
                "capture_commands": [],
                "benchmark_commands": ["python benchmarks/render_benchmark.py"],
                "product_workflows": ["browser_renderer", "visual_regression", "scene_authoring"],
                "validation_notes": ["Scene validation is technically runnable."],
                "asset_paths": ["assets/set.blend", "assets/set.usda"],
                "scene_paths": ["assets/set.usda"],
                "config_paths": ["configs/streaming.yaml"],
            },
            "spatial3d_validation_plan": {
                "available": True,
                "status": "ready",
                "summary": "Spatial validation is ready.",
                "repo_mode_enabled": True,
                "repo_mode": "spatial3d_scene_authoring",
                "steps": [
                    {"title": "Run browser probe", "command": "playwright test", "type": "inspect", "status": "pending"},
                    {"title": "Validate scene", "command": "python validate_scene.py", "type": "validate", "status": "pending"},
                ],
                "blockers": [],
                "recommended_fixes": [],
                "evidence_targets": ["render diff summary"],
                "product_workflows": ["browser_renderer", "visual_regression", "scene_authoring"],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Browser and Linux lanes are ready.",
            "selected_target_id": "linux-dcc",
            "lane_count": 2,
            "ready_lane_count": 2,
            "partial_lane_count": 0,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["browser", "linux"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": [],
            "lanes": [
                {"lane_id": "browser", "title": "Browser Runner", "status": "ready", "summary": "ready", "target_ids": ["browser-1"], "target_count": 1, "selected_target_ids": ["browser-1"], "os_families": ["linux"], "toolchains": ["playwright"], "command_families": ["browser"], "recommended_commands": ["playwright test"], "notes": []},
                {"lane_id": "linux", "title": "Linux Runner", "status": "ready", "summary": "ready", "target_ids": ["linux-dcc"], "target_count": 1, "selected_target_ids": ["linux-dcc"], "os_families": ["linux"], "toolchains": ["blender"], "command_families": ["headless"], "recommended_commands": ["python validate_scene.py"], "notes": []},
            ],
        },
    )
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 1})
    monkeypatch.setattr(
        "manager.service.build_decision_audit_summary",
        lambda db, project: {"pending_approval_count": 1, "pending_question_count": 1},
    )

    workspace = tmp_path / "workspace-spatial-governance-blocked"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Spatial Governance Blocker Demo",
            "idea": "Need spatial governance to stop pretending blocked publish lanes are ready.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    summary = client.get(f"/api/projects/{project_id}/spatial-asset-governance/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["governance_status"] == "blocked"
    assert payload["quality_gate_blocker_count"] == 1
    assert payload["pending_approval_count"] == 1
    assert payload["pending_question_count"] == 1
    assert "1 quality gate blocker(s) still prevent spatial publish review." in payload["blocking_reasons"]
    assert "Clear pending spatial approval checkpoints before publishing or exporting generated assets." in payload["recommended_fixes"]
    assert "Resolve pending spatial governance questions before approving export or publish." in payload["recommended_fixes"]


def test_spatial_asset_governance_plan_route_keeps_publish_gate_blocked_for_quality_and_approval_pressure(
    client, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace_path, project_name=None: {
            "workspace_path": str(_workspace_path),
            "available": True,
            "summary": "Spatial validation signals are present.",
            "tools": [],
            "packs": [],
            "artifact_paths": ["artifacts/renders/frame_0001.png"],
            "artifact_kind_summaries": ["image:1"],
            "artifact_inspection_commands": ["python inspect_render.py"],
            "config_review_paths": ["configs/streaming.yaml"],
            "config_review_commands": ["python review_config.py"],
            "validation_evidence_targets": ["artifacts/renders/frame_0001.png"],
            "execution_entrypoints": [],
            "notebook_paths": [],
            "recommended_next_steps": [],
            "product_lane_statuses": ["browser:ready", "linux:ready"],
            "execution_lane_summaries": [],
            "artifact_kind_summaries_extra": [],
            "important_paths": [],
            "runtime_blockers": [],
            "repo_mode_summaries": [],
            "intake_commands": [],
            "notebook_commands": [],
            "validation_commands": ["playwright test", "python validate_scene.py"],
            "observability_commands": [],
            "security_commands": [],
            "deployment_commands": [],
            "artifact_inspection_commands_extra": [],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_commands_extra": [],
            "spatial3d_repo": {
                "enabled": True,
                "mode": "spatial3d_scene_authoring",
                "frameworks": ["Blender", "OpenUSD"],
                "build_commands": ["python -m pip install -e ."],
                "render_commands": ["python render_scene.py"],
                "conversion_commands": [],
                "capture_commands": [],
                "benchmark_commands": ["python benchmarks/render_benchmark.py"],
                "product_workflows": ["browser_renderer", "visual_regression", "scene_authoring"],
                "validation_notes": ["Scene validation is technically runnable."],
                "asset_paths": ["assets/set.blend", "assets/set.usda"],
                "scene_paths": ["assets/set.usda"],
                "config_paths": ["configs/streaming.yaml"],
            },
            "spatial3d_validation_plan": {
                "available": True,
                "status": "ready",
                "summary": "Spatial validation is ready.",
                "repo_mode_enabled": True,
                "repo_mode": "spatial3d_scene_authoring",
                "steps": [
                    {"title": "Run browser probe", "command": "playwright test", "type": "inspect", "status": "pending"},
                    {"title": "Validate scene", "command": "python validate_scene.py", "type": "validate", "status": "pending"},
                ],
                "blockers": [],
                "recommended_fixes": [],
                "evidence_targets": ["render diff summary"],
                "product_workflows": ["browser_renderer", "visual_regression", "scene_authoring"],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Browser and Linux lanes are ready.",
            "selected_target_id": "linux-dcc",
            "lane_count": 2,
            "ready_lane_count": 2,
            "partial_lane_count": 0,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["browser", "linux"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": [],
            "lanes": [
                {"lane_id": "browser", "title": "Browser Runner", "status": "ready", "summary": "ready", "target_ids": ["browser-1"], "target_count": 1, "selected_target_ids": ["browser-1"], "os_families": ["linux"], "toolchains": ["playwright"], "command_families": ["browser"], "recommended_commands": ["playwright test"], "notes": []},
                {"lane_id": "linux", "title": "Linux Runner", "status": "ready", "summary": "ready", "target_ids": ["linux-dcc"], "target_count": 1, "selected_target_ids": ["linux-dcc"], "os_families": ["linux"], "toolchains": ["blender"], "command_families": ["headless"], "recommended_commands": ["python validate_scene.py"], "notes": []},
            ],
        },
    )
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 1})
    monkeypatch.setattr(
        "manager.service.build_decision_audit_summary",
        lambda db, project: {"pending_approval_count": 1, "pending_question_count": 1},
    )

    workspace = tmp_path / "workspace-spatial-plan-blocked"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    create = client.post(
        "/api/projects",
        json={
            "name": "Spatial Plan Blocker Demo",
            "idea": "Need blocked spatial publish gates reflected in the generated plan.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/spatial-asset-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "partial"
    assert "1 quality gate blocker(s) still prevent spatial publish review." in payload["blocking_reasons"]
    assert any("publish review staged" in note for note in payload["notes"])

    approval_checkpoints = json.loads((workspace / "artifacts" / "spatial-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    publish_gate = next(item for item in approval_checkpoints["checkpoints"] if item["checkpoint_id"] == "publish_gate")
    assert publish_gate["status"] == "blocked"


def test_nvidia_execution_governance_summary_route_surfaces_provider_runtime_and_gpu_lanes(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-nvidia-governance"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_nvidia_dynamo_status",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "provider": "nvidia_dynamo",
            "label": "NVIDIA Dynamo",
            "available": True,
            "reachable": True,
            "endpoint": "http://dynamo.local:8000",
            "endpoint_configured": True,
            "api_key_configured": True,
            "auth_required": True,
            "authenticated": True,
            "available_models": ["gpt-cuda"],
            "runtime_ready": True,
            "runtime_status": "ready",
            "runtime_summary": "Dynamo runtime is healthy.",
            "runtime_blockers": [],
            "adapter_command_configured": True,
            "adapter_command_detected": True,
            "adapter_command_path": "python",
            "adapter_args": ["adapter.py"],
            "adapter_recipe_source": "project_settings",
            "summary": "Dynamo is ready.",
            "notes": ["Use this lane for governed GPU-backed execution."],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_nim_status",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "provider": "nvidia_nim",
            "label": "NVIDIA NIM",
            "available": False,
            "reachable": True,
            "endpoint": "https://integrate.api.nvidia.com",
            "endpoint_configured": True,
            "api_key_configured": False,
            "auth_required": True,
            "authenticated": False,
            "available_models": [],
            "runtime_ready": False,
            "runtime_status": "blocked",
            "runtime_summary": "NIM auth is missing.",
            "runtime_blockers": ["NIM API key is missing."],
            "adapter_command_configured": False,
            "adapter_command_detected": False,
            "adapter_command_path": None,
            "adapter_args": [],
            "adapter_recipe_source": None,
            "summary": "NIM is not ready.",
            "notes": ["Configure auth before using NIM."],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_aiq_status",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "available": True,
            "install_status": "ready",
            "summary": "AI-Q is reachable.",
            "endpoint": "http://aiq.local:8000",
            "endpoint_configured": True,
            "api_key_configured": True,
            "auth_required": False,
            "dask_available": True,
            "agent_types": ["deep_researcher"],
            "data_sources": ["docs"],
            "recommended_fix": None,
            "notes": ["Use AI-Q for deep CUDA research when needed."],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_gpu_diagnostics",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "available": True,
            "status": "ready",
            "summary": "Cluster telemetry is healthy.",
            "prometheus_url": "http://prom.local:9090",
            "workspace_relevant": True,
            "telemetry_status": "ready",
            "workspace_summary_status": "ready",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_python",
            "cluster_usable": True,
            "pending_pod_count": 0,
            "gpu_memory_saturation_pct": 42.0,
            "gpu_memory_saturated": False,
            "likely_failure_source": "repo",
            "blocking_reasons": [],
            "detected_signals": ["prometheus"],
            "observability_sources": ["dcgm"],
            "summary_files": [],
            "safe_commands": ["curl http://prom.local:9090/-/healthy"],
            "metrics": {"gpu_util": 0.5},
            "alerts": [],
            "recommended_fixes": [],
            "queries": {"gpu_util": "avg(dcgm_gpu_utilization)"},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_local_runtime_status",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "available": True,
            "status": "ready",
            "summary": "Local CUDA runtime is ready.",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_python",
            "detected_tools": ["nvidia_smi", "nvcc", "compute_sanitizer"],
            "missing_required_tools": [],
            "missing_optional_tools": [],
            "tool_paths": {"nvidia_smi": "C:/Windows/System32/nvidia-smi.exe", "nvcc": "C:/CUDA/bin/nvcc.exe"},
            "gpu_names": ["RTX 4090"],
            "driver_version": "555.10",
            "nvcc_version": "Cuda compilation tools, release 12.4",
            "cuda_release": "12.4",
            "cuda_home": "C:/CUDA",
            "compute_sanitizer_available": True,
            "nsight_systems_available": True,
            "nsight_compute_available": True,
            "cuda_gdb_available": False,
            "container_toolkit_available": True,
            "ngc_cli_available": False,
            "container_runtime_ready": True,
            "docker_available": True,
            "recommended_fixes": [],
            "validation_hints": ["python -m pytest tests/gpu -q"],
            "notes": ["Local runtime is usable."],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_validation_plan",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "available": True,
            "status": "ready",
            "summary": "NVIDIA validation is credible.",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_python",
            "local_runtime_status": "ready",
            "gpu_diagnostics_status": "ready",
            "sanitizer_ready": True,
            "profiler_ready": True,
            "container_smoke_ready": True,
            "ngc_smoke_image": "nvcr.io/test/smoke:latest",
            "steps": [{"title": "Run GPU tests", "command": "python -m pytest tests/gpu -q", "type": "test", "source": "repo_mode", "status": "pending"}],
            "blockers": [],
            "recommended_fixes": [],
            "evidence_targets": ["benchmark delta", "sanitizer output"],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "GPU runner lanes are ready.",
            "selected_target_id": "gpu-linux",
            "lane_count": 2,
            "ready_lane_count": 2,
            "partial_lane_count": 0,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["linux", "unity"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": [],
            "lanes": [
                {"lane_id": "linux", "title": "Linux Runner", "status": "ready", "summary": "ready", "target_ids": ["gpu-linux"], "target_count": 1, "selected_target_ids": ["gpu-linux"], "os_families": ["linux"], "toolchains": ["cuda12"], "command_families": ["python"], "recommended_commands": ["python -m pytest"], "notes": []},
                {"lane_id": "unity", "title": "Unity Runner", "status": "ready", "summary": "ready", "target_ids": ["gpu-linux"], "target_count": 1, "selected_target_ids": ["gpu-linux"], "os_families": ["linux"], "toolchains": ["unity6000"], "command_families": ["unity_batchmode"], "recommended_commands": ["Unity -batchmode -runTests"], "notes": []},
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_device_broker_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Broker sees one GPU host.",
            "preflight_ready": True,
            "selected_target_id": "gpu-linux",
            "recommended_target_ids": ["gpu-linux"],
            "blocking_reasons": [],
            "ready_target_count": 1,
                "capability_index": {
                    "target_count": 1,
                    "ready_target_count": 1,
                    "targets": [
                        {
                            "target_id": "gpu-linux",
                            "label": "GPU Linux",
                            "transport": "ssh",
                            "host": "gpu-linux.tailnet.ts.net",
                            "os_family": "linux",
                            "architecture": "x86_64",
                            "ready": True,
                            "gpu": "RTX 4090",
                            "toolchains": ["python3.11", "cuda12"],
                            "command_families": ["python", "git"],
                            "result_formats": ["json"],
                            "connector_families": [],
                            "artifact_roots": ["/srv/work/artifacts"],
                            "allowed_repo_roots": ["/srv/work"],
                            "allowed_path_prefixes": ["src", "artifacts"],
                            "session_recording_enabled": True,
                            "probe_status": "ready",
                        }
                    ],
                },
                "remote_execution": {
                    "policy": {"enabled": True},
                    "registry_summary": {},
                    "required_runner_family": "external_adapter",
                    "require_write_access": True,
                    "eligible_target_count": 1,
                    "selected_target_id": "gpu-linux",
                    "preflight_ready": True,
                    "blocking_reasons": [],
                    "candidates": [],
                    "artifact_contract": {"sync_enabled": True},
                    "connector_contract": {},
                    "broker_contract": {},
                },
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "artifact_count": 0, "artifact_paths": [], "artifact_kind_summaries": [], "artifact_inspection_commands": [], "summary": "none"},
            "connector_registry": {"summary": "none", "connection_count": 0, "connections": [], "ready_families": [], "ready_family_count": 0, "provider_counts": {}, "provider_count": 0, "category_counts": {}, "category_count": 0, "connection_source_counts": {}, "connection_source_count": 0, "available_action_count": 0, "catalog": []},
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "NVIDIA Governance Demo",
            "idea": "Need governed CUDA execution.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/nvidia/governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["governance_status"] == "ready"
    assert payload["recommended_execution_lane"] == "nvidia_dynamo"
    assert payload["cuda_repo_enabled"] is True
    assert payload["validation_status"] == "ready"
    assert payload["local_runtime_status"] == "ready"
    assert payload["gpu_diagnostics_status"] == "ready"
    assert payload["aiq_status"] == "ready"
    assert payload["remote_gpu_target_count"] == 1
    assert payload["ready_remote_gpu_target_count"] == 1
    assert payload["selected_remote_target_id"] == "gpu-linux"
    assert payload["selected_remote_target_gpu"] == "RTX 4090"
    assert payload["provider_ready_ids"] == ["nvidia_dynamo"]
    assert payload["provider_partial_ids"] == ["nvidia_nim"]
    assert payload["available_provider_count"] == 1
    assert payload["sanitizer_ready"] is True
    assert payload["profiler_ready"] is True
    assert payload["container_smoke_ready"] is True
    assert payload["blocking_reasons"] == []
    assert payload["dynamo_status"]["runtime_ready"] is True
    assert payload["nim_status"]["runtime_status"] == "blocked"
    assert payload["validation_plan"]["status"] == "ready"


def test_nvidia_execution_governance_plan_route_emits_manifest_cluster(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-nvidia-governance-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_nvidia_execution_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "NVIDIA governance summary stub.",
            "governance_status": "ready",
            "recommended_execution_lane": "nvidia_dynamo",
            "cuda_repo_enabled": True,
            "validation_status": "ready",
            "local_runtime_status": "ready",
            "gpu_diagnostics_status": "ready",
            "aiq_status": "ready",
            "remote_gpu_target_count": 1,
            "ready_remote_gpu_target_count": 1,
            "selected_remote_target_id": "gpu-linux",
            "selected_remote_target_gpu": "RTX 4090",
            "provider_ready_ids": ["nvidia_dynamo"],
            "provider_partial_ids": ["nvidia_nim"],
            "available_provider_count": 1,
            "sanitizer_ready": True,
            "profiler_ready": True,
            "container_smoke_ready": True,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["GPU lane ready."],
            "dynamo_status": {"runtime_ready": True, "runtime_status": "ready", "endpoint": "http://dynamo.local:8000"},
            "nim_status": {"runtime_ready": False, "runtime_status": "blocked", "endpoint": "https://integrate.api.nvidia.com"},
            "aiq": {"available": True, "install_status": "ready", "endpoint": "http://aiq.local:8000"},
            "gpu_diagnostics": {"status": "ready", "repo_mode_enabled": True, "recommended_fixes": [], "blocking_reasons": []},
            "local_runtime": {"status": "ready", "repo_mode_enabled": True},
            "validation_plan": {"status": "ready", "steps": [{"title": "Run GPU tests", "type": "test", "source": "repo_mode", "status": "pending"}]},
            "platform_runners": {"summary": "GPU lanes ready.", "selected_target_id": "gpu-linux", "ready_lane_ids": ["linux"]},
            "device_broker": {"summary": "Broker sees one GPU host.", "selected_target_id": "gpu-linux"},
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "NVIDIA Governance Plan Demo",
            "idea": "Need concrete CUDA governance manifests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.post(f"/api/projects/{project_id}/nvidia/governance/plan")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["manifest_root"] == "artifacts/nvidia-governance"
    assert payload["execution_lane_path"] == "artifacts/nvidia-governance/execution-lane-selection.json"
    assert payload["provider_runtime_path"] == "artifacts/nvidia-governance/provider-runtime-matrix.json"
    assert payload["gpu_target_inventory_path"] == "artifacts/nvidia-governance/gpu-target-inventory.json"
    assert payload["validation_evidence_path"] == "artifacts/nvidia-governance/validation-evidence-plan.json"
    assert payload["telemetry_gate_path"] == "artifacts/nvidia-governance/telemetry-and-safety-gates.json"
    assert payload["approval_checkpoint_path"] == "artifacts/nvidia-governance/approval-checkpoints.json"
    assert (workspace / "artifacts" / "nvidia-governance" / "execution-lane-selection.json").exists()
    assert (workspace / "artifacts" / "nvidia-governance" / "provider-runtime-matrix.json").exists()
    assert (workspace / "artifacts" / "nvidia-governance" / "gpu-target-inventory.json").exists()
    assert (workspace / "artifacts" / "nvidia-governance" / "validation-evidence-plan.json").exists()
    assert (workspace / "artifacts" / "nvidia-governance" / "telemetry-and-safety-gates.json").exists()
    assert (workspace / "artifacts" / "nvidia-governance" / "approval-checkpoints.json").exists()


def test_nvidia_governance_requires_selected_ready_remote_gpu_target(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-nvidia-selected-target"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_nvidia_dynamo_status",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
                "endpoint": "",
            "summary": "Dynamo is not configured.",
            "available": False,
            "reachable": False,
            "endpoint_configured": False,
            "api_key_configured": False,
            "auth_required": True,
            "authenticated": False,
            "runtime_ready": False,
            "runtime_status": "blocked",
            "runtime_summary": "blocked",
            "runtime_blockers": [],
            "notes": [],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_nim_status",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
                "endpoint": "",
            "summary": "NIM is not configured.",
            "available": False,
            "reachable": False,
            "endpoint_configured": False,
            "api_key_configured": False,
            "auth_required": True,
            "authenticated": False,
            "runtime_ready": False,
            "runtime_status": "blocked",
            "runtime_summary": "blocked",
            "runtime_blockers": [],
            "notes": [],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_aiq_status",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "install_status": "missing",
            "summary": "AIQ is missing.",
                "endpoint": "",
            "available": False,
            "notes": [],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_gpu_diagnostics",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "available": True,
            "status": "ready",
            "summary": "GPU diagnostics look fine.",
            "prometheus_url": None,
            "workspace_relevant": True,
            "telemetry_status": "ready",
            "workspace_summary_status": "ready",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_python",
            "cluster_usable": True,
            "pending_pod_count": 0,
            "gpu_memory_saturation_pct": None,
            "gpu_memory_saturated": False,
            "likely_failure_source": "selection",
            "blocking_reasons": [],
            "detected_signals": [],
            "observability_sources": [],
            "summary_files": [],
            "safe_commands": [],
            "metrics": {},
            "alerts": [],
            "recommended_fixes": [],
            "queries": {},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_local_runtime_status",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "available": False,
            "status": "missing",
            "summary": "Local CUDA runtime is unavailable.",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_python",
            "detected_tools": [],
            "missing_required_tools": ["nvidia_smi", "nvcc"],
            "missing_optional_tools": ["compute_sanitizer"],
            "tool_paths": {},
            "gpu_names": [],
            "driver_version": None,
            "nvcc_version": None,
            "cuda_release": None,
            "cuda_home": None,
            "compute_sanitizer_available": False,
            "nsight_systems_available": False,
            "nsight_compute_available": False,
            "cuda_gdb_available": False,
            "container_toolkit_available": False,
            "ngc_cli_available": False,
            "container_runtime_ready": False,
            "docker_available": False,
            "recommended_fixes": [],
            "validation_hints": [],
            "notes": [],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_validation_plan",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "available": True,
            "status": "ready",
            "summary": "Validation exists, but execution lane selection is wrong.",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_python",
            "local_runtime_status": "missing",
            "gpu_diagnostics_status": "ready",
            "sanitizer_ready": False,
            "profiler_ready": False,
            "container_smoke_ready": False,
            "ngc_smoke_image": None,
            "steps": [{"title": "Run GPU tests", "command": "python -m pytest tests/gpu -q", "type": "test", "source": "repo_mode", "status": "pending"}],
            "blockers": [],
            "recommended_fixes": [],
            "evidence_targets": ["benchmark delta"],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "A Linux GPU lane exists, but not for the selected target.",
            "selected_target_id": "gpu-offline",
            "selected_target_probe_status": "offline",
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-right"],
            "lane_count": 1,
            "ready_lane_count": 1,
            "partial_lane_count": 0,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["linux"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": [],
            "lanes": [
                {
                    "lane_id": "linux",
                    "title": "Linux Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["gpu-right"],
                    "target_count": 1,
                    "selected_target_ids": [],
                    "os_families": ["linux"],
                    "toolchains": ["cuda12"],
                    "command_families": ["python"],
                    "recommended_commands": ["python -m pytest"],
                    "notes": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_device_broker_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Broker selected the wrong GPU host.",
            "preflight_ready": False,
            "selected_target_id": "gpu-offline",
            "selected_target_probe_status": "offline",
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-right"],
            "recommended_target_ids": ["gpu-right"],
            "blocking_reasons": ["selected_target_not_ready"],
            "ready_target_count": 1,
            "capability_index": {
                "target_count": 2,
                "ready_target_count": 1,
                "targets": [
                    {
                        "target_id": "gpu-offline",
                        "label": "Offline GPU Host",
                        "transport": "ssh",
                        "host": "gpu-offline.tailnet.ts.net",
                        "os_family": "linux",
                        "architecture": "x86_64",
                        "ready": False,
                        "gpu": "RTX 4090",
                        "toolchains": ["python3.11", "cuda12"],
                        "command_families": ["python", "git"],
                        "result_formats": ["json"],
                        "connector_families": [],
                        "artifact_roots": ["/srv/work/artifacts"],
                        "allowed_repo_roots": ["/srv/work"],
                        "allowed_path_prefixes": ["src", "artifacts"],
                        "session_recording_enabled": True,
                        "probe_status": "offline",
                    },
                    {
                        "target_id": "gpu-right",
                        "label": "Ready GPU Host",
                        "transport": "ssh",
                        "host": "gpu-right.tailnet.ts.net",
                        "os_family": "linux",
                        "architecture": "x86_64",
                        "ready": True,
                        "gpu": "RTX 4090",
                        "toolchains": ["python3.11", "cuda12"],
                        "command_families": ["python", "git"],
                        "result_formats": ["json"],
                        "connector_families": [],
                        "artifact_roots": ["/srv/work/artifacts"],
                        "allowed_repo_roots": ["/srv/work"],
                        "allowed_path_prefixes": ["src", "artifacts"],
                        "session_recording_enabled": True,
                        "probe_status": "ready",
                    },
                ],
            },
            "remote_execution": {
                "policy": {"enabled": True},
                "registry_summary": {},
                "required_runner_family": "external_adapter",
                "require_write_access": True,
                "eligible_target_count": 1,
                "selected_target_id": "gpu-offline",
                "preflight_ready": False,
                "blocking_reasons": ["selected_target_not_ready"],
                "candidates": [],
                "artifact_contract": {"sync_enabled": True},
                "connector_contract": {},
                "broker_contract": {},
            },
            "artifact_registry": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "available": False,
                "summary": "none",
                "artifact_count": 0,
                "artifact_paths": [],
                "artifact_extensions": [],
                "artifact_extension_count": 0,
                "artifact_kind_summaries": [],
                "artifact_kind_counts": {},
                "artifact_kind_count": 0,
                "inspection_command_count": 0,
                "inspection_commands": [],
                "config_review_path_count": 0,
                "config_review_paths": [],
                "config_review_command_count": 0,
                "config_review_commands": [],
                "validation_evidence_target_count": 0,
                "validation_evidence_targets": [],
                "execution_entrypoint_count": 0,
                "execution_entrypoints": [],
                "notebook_path_count": 0,
                "notebook_paths": [],
                "recommended_next_steps": [],
                "recommended_next_step_count": 0,
            },
            "connector_registry": {
                "summary": "none",
                "connection_count": 0,
                "connections": [],
                "ready_families": [],
                "ready_family_count": 0,
                "provider_counts": {},
                "provider_count": 0,
                "category_counts": {},
                "category_count": 0,
                "connection_source_counts": {},
                "connection_source_count": 0,
                "available_action_count": 0,
                "catalog": [],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "NVIDIA Selected Target Demo",
            "idea": "Need governance to reject the wrong selected GPU host.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/nvidia/governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "blocked"
    assert payload["recommended_execution_lane"] == "discovery_needed"
    assert payload["remote_gpu_target_count"] == 2
    assert payload["ready_remote_gpu_target_count"] == 1
    assert payload["selected_ready_remote_gpu_target_count"] == 0
    assert payload["selected_remote_target_id"] == "gpu-offline"
    assert payload["selected_remote_target_ready"] is False
    assert payload["selected_remote_target_gpu"] == "RTX 4090"
    assert "Rebind the selected broker target to a ready GPU host before treating remote CUDA execution as governed." in payload["recommended_fixes"]

    plan = client.post(f"/api/projects/{project_id}/nvidia/governance/plan")
    assert plan.status_code == 200, plan.text
    plan_payload = plan.json()
    assert plan_payload["recommended_execution_lane"] == "discovery_needed"
    assert plan_payload["selected_ready_remote_gpu_target_count"] == 0

    execution_lane = json.loads(
        (workspace / "artifacts" / "nvidia-governance" / "execution-lane-selection.json").read_text(encoding="utf-8")
    )
    assert execution_lane["selected_remote_target_id"] == "gpu-offline"
    assert execution_lane["selected_remote_target_ready"] is False
    assert execution_lane["selected_ready_remote_gpu_target_count"] == 0

    gpu_inventory = json.loads(
        (workspace / "artifacts" / "nvidia-governance" / "gpu-target-inventory.json").read_text(encoding="utf-8")
    )
    assert gpu_inventory["ready_remote_gpu_target_count"] == 1
    assert gpu_inventory["selected_ready_remote_gpu_target_count"] == 0

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "nvidia-governance" / "approval-checkpoints.json").read_text(encoding="utf-8")
    )
    checkpoints = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoints["gpu_lane_review"]["status"] == "blocked"


def test_game_engine_governance_summary_route_surfaces_unity_runner_and_playable_signals(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-game-engine-governance"
    (workspace / "Assets" / "Scenes").mkdir(parents=True, exist_ok=True)
    (workspace / "ProjectSettings").mkdir(parents=True, exist_ok=True)
    (workspace / "Packages").mkdir(parents=True, exist_ok=True)
    (workspace / "Assets" / "Tests").mkdir(parents=True, exist_ok=True)
    (workspace / "Artifacts" / "Screenshots").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "game-engine-governance").mkdir(parents=True, exist_ok=True)
    (workspace / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.0f1\n", encoding="utf-8")
    (workspace / "Packages" / "manifest.json").write_text("{}\n", encoding="utf-8")
    (workspace / "Assets" / "Scenes" / "MainMenu.unity").write_text("scene\n", encoding="utf-8")
    (workspace / "Assets" / "Tests" / "SmokeTest.cs").write_text("// test\n", encoding="utf-8")
    (workspace / "Artifacts" / "Screenshots" / "frame_0001.png").write_text("png\n", encoding="utf-8")
    (workspace / "artifacts" / "game-engine-governance" / "normalized-results-summary.json").write_text(
        json.dumps(
            {
                "summary_count": 3,
                "passed_count": 2,
                "failed_count": 0,
                "missing_count": 1,
                "publish_ready": False,
                "summaries": [],
            }
        ),
        encoding="utf-8",
    )
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Unity lane is ready.",
            "selected_target_id": "win-unity",
            "lane_count": 3,
            "ready_lane_count": 2,
            "partial_lane_count": 1,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["unity", "windows"],
            "partial_lane_ids": ["browser"],
            "unavailable_lane_ids": [],
            "lanes": [
                {"lane_id": "unity", "title": "Unity Runner", "status": "ready", "summary": "ready", "target_ids": ["win-unity"], "target_count": 1, "selected_target_ids": ["win-unity"], "os_families": ["windows"], "toolchains": ["unity6000"], "command_families": ["unity_batchmode"], "recommended_commands": ["Unity -batchmode -runTests"], "notes": []},
                {"lane_id": "unreal", "title": "Unreal Runner", "status": "unavailable", "summary": "unavailable", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": [], "command_families": [], "recommended_commands": ["RunUAT BuildCookRun"], "notes": []},
                {"lane_id": "browser", "title": "Browser Runner", "status": "partial", "summary": "partial", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": ["playwright"], "command_families": ["browser"], "recommended_commands": ["playwright test"], "notes": []},
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_design_transfer_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Design transfer is artifact-only.",
            "recommended_ingestion_mode": "artifact_only",
            "figma_connected": False,
            "design_artifact_count": 1,
            "design_artifact_paths": ["Artifacts/Screenshots/frame_0001.png"],
            "design_artifact_formats": [".png"],
            "browser_lane_status": "partial",
            "browser_lane_target_ids": [],
            "supports_visual_regression": True,
            "code_conformance_ready": False,
            "blocking_reasons": [],
            "notes": ["Artifacts can drive screenshot-based conformance."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts", "artifact_count": 1, "artifact_paths": ["Artifacts/Screenshots/frame_0001.png"], "artifact_extensions": [".png"], "artifact_extension_count": 1, "artifact_kind_summaries": ["image:1"], "artifact_kind_counts": {"image": 1}, "artifact_kind_count": 1, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 1, "validation_evidence_targets": ["Artifacts/Screenshots/frame_0001.png"], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []},
            "connector_registry": {"summary": "none", "connection_count": 0, "status_counts": {}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 0, "ready_families": [], "provider_counts": {}, "provider_count": 0, "category_counts": {}, "category_count": 0, "connection_source_counts": {}, "connection_source_count": 0, "available_action_count": 0, "catalog": [], "connections": []},
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": "win-unity", "lane_count": 0, "ready_lane_count": 0, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": [], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_spatial_asset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Spatial not applicable.",
            "governance_status": "not_applicable",
            "repo_mode_enabled": False,
            "repo_mode": None,
            "frameworks": [],
            "product_workflows": [],
            "recommended_feature_ids": [],
            "asset_count": 0,
            "asset_paths": [],
            "asset_extensions": [],
            "config_paths": [],
            "primary_scene_path": None,
            "headless_runner_status": "unavailable",
            "browser_lane_status": "partial",
            "recommended_transport_mode": "discovery_needed",
            "build_commands": [],
            "render_commands": [],
            "conversion_commands": [],
            "capture_commands": [],
            "benchmark_commands": [],
            "validation_status": "not_applicable",
            "validation_available": False,
            "validation_step_count": 0,
            "validation_evidence_targets": [],
            "supports_visual_regression": False,
            "quality_gate_blocker_count": 0,
            "quality_gate_missing_evidence_count": 0,
            "pending_approval_count": 0,
            "pending_question_count": 0,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": [],
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": None, "lane_count": 0, "ready_lane_count": 0, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": [], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
            "artifact_transport": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": None, "preflight_ready": False, "sync_enabled": False, "recommended_transport_mode": "discovery_needed", "blocking_reasons": [], "ready_platform_lanes": [], "partial_platform_lanes": [], "notes": [], "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": False, "summary": "stub", "artifact_count": 0, "artifact_paths": [], "artifact_extensions": [], "artifact_extension_count": 0, "artifact_kind_summaries": [], "artifact_kind_counts": {}, "artifact_kind_count": 0, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 0, "validation_evidence_targets": [], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []}, "connector_registry": {"summary": "none", "connection_count": 0, "status_counts": {}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 0, "ready_families": [], "provider_counts": {}, "provider_count": 0, "category_counts": {}, "category_count": 0, "connection_source_counts": {}, "connection_source_count": 0, "available_action_count": 0, "catalog": [], "connections": []}, "artifact_contract": {"sync_enabled": False}, "connector_contract": {}},
        },
    )
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})

    create = client.post(
        "/api/projects",
        json={
            "name": "Game Engine Governance Demo",
            "idea": "Need governed Unity execution.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/game-engine-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["selected_target_id"] == "win-unity"
    assert payload["governance_status"] == "partial"
    assert payload["detected_engines"] == ["unity"]
    assert payload["unity_detected"] is True
    assert payload["unreal_detected"] is False
    assert payload["scene_or_map_count"] == 1
    assert payload["automation_signal_count"] >= 1
    assert payload["screenshot_artifact_count"] == 1
    assert payload["playable_contract_status"] == "ready"
    assert payload["asset_lock_status"] == "ready"
    assert payload["task_routing_status"] == "ready"
    assert payload["engine_test_matrix_status"] == "partial"
    assert payload["publish_gate_status"] == "blocked"
    assert payload["normalized_results_status"] == "partial"
    assert payload["publish_blocker_count"] == 1
    assert payload["publish_blockers"] == [
        "Normalized Unity/Unreal result rollups still contain missing, failed, or parse-error evidence."
    ]
    assert payload["repo_owned_tests_required"] is True
    assert payload["content_task_asset_lock_required"] is True
    assert payload["mixed_task_publish_review_required"] is True
    assert payload["visual_regression_ready"] is True
    assert payload["normalized_results_summary_path"] == "artifacts/game-engine-governance/normalized-results-summary.json"
    assert payload["normalized_summary_count"] == 3
    assert payload["normalized_passed_count"] == 2
    assert payload["normalized_failed_count"] == 0
    assert payload["normalized_missing_count"] == 1
    assert payload["normalized_publish_ready"] is False
    assert payload["unity_lane_status"] == "ready"
    assert payload["unreal_lane_status"] == "unavailable"
    assert payload["browser_lane_status"] == "partial"
    assert payload["recommended_runner_lane"] == "unity"
    assert payload["blocking_reasons"] == []
    assert "Refresh or repair normalized Unity/Unreal evidence artifacts before treating the game pipeline as publish-ready." in payload["recommended_fixes"]
    assert "Normalized engine evidence exists but is not publish-ready yet." in payload["notes"]
    assert "Asset-lock status is `ready`, task routing is `ready`, and publish gate is `blocked`." in payload["notes"]
    assert "Normalized result status is `partial` with 1 publish blocker(s)." in payload["notes"]
    assert "Assets/Scenes/MainMenu.unity" in payload["scene_or_map_paths"]


def test_game_engine_governance_requires_selected_target_bound_engine_lane(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-game-engine-selected-target"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service._build_game_engine_workspace_profile",
        lambda project: {
            "unity_detected": True,
            "unreal_detected": False,
            "detected_engines": ["unity"],
            "detected_project_paths": ["ProjectSettings/ProjectVersion.txt"],
            "scene_or_map_paths": ["Assets/Scenes/MainMenu.unity"],
            "automation_signal_paths": [],
            "screenshot_artifact_paths": ["Artifacts/Screenshots/frame_0001.png"],
        },
    )
    monkeypatch.setattr(
        "manager.service._load_game_engine_normalized_results_summary",
        lambda workspace_root: {
            "normalized_results_summary_path": "artifacts/game-engine-governance/normalized-results-summary.json",
            "normalized_summary_count": 2,
            "normalized_passed_count": 2,
            "normalized_failed_count": 0,
            "normalized_missing_count": 0,
            "normalized_publish_ready": True,
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Unity exists, but only on another Windows host.",
            "selected_target_id": "win-selected",
            "selected_ready_lane_ids": [],
            "lane_count": 3,
            "ready_lane_count": 2,
            "partial_lane_count": 0,
            "unavailable_lane_count": 1,
            "ready_lane_ids": ["unity", "windows"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": ["browser"],
            "lanes": [
                {
                    "lane_id": "unity",
                    "title": "Unity Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["win-other"],
                    "target_count": 1,
                    "selected_target_ids": [],
                    "os_families": ["windows"],
                    "toolchains": ["unity6000"],
                    "command_families": ["unity_batchmode"],
                    "recommended_commands": ["Unity -batchmode -runTests"],
                    "notes": [],
                },
                {
                    "lane_id": "unreal",
                    "title": "Unreal Runner",
                    "status": "unavailable",
                    "summary": "unavailable",
                    "target_ids": [],
                    "target_count": 0,
                    "selected_target_ids": [],
                    "os_families": [],
                    "toolchains": [],
                    "command_families": [],
                    "recommended_commands": ["RunUAT BuildCookRun"],
                    "notes": [],
                },
                {
                    "lane_id": "browser",
                    "title": "Browser Runner",
                    "status": "unavailable",
                    "summary": "unavailable",
                    "target_ids": [],
                    "target_count": 0,
                    "selected_target_ids": [],
                    "os_families": [],
                    "toolchains": [],
                    "command_families": [],
                    "recommended_commands": ["playwright test"],
                    "notes": [],
                },
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_design_transfer_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Artifacts provide visual regression input.",
            "recommended_ingestion_mode": "artifact_only",
            "figma_connected": False,
            "design_artifact_count": 1,
            "design_artifact_paths": ["Artifacts/Screenshots/frame_0001.png"],
            "design_artifact_formats": [".png"],
            "browser_lane_status": "unavailable",
            "browser_lane_target_ids": [],
            "supports_visual_regression": True,
            "code_conformance_ready": False,
            "blocking_reasons": [],
            "notes": ["Artifacts can drive screenshot-based conformance."],
            "artifact_registry": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "available": True,
                "summary": "artifacts",
                "artifact_count": 1,
                "artifact_paths": ["Artifacts/Screenshots/frame_0001.png"],
                "artifact_extensions": [".png"],
                "artifact_extension_count": 1,
                "artifact_kind_summaries": ["image:1"],
                "artifact_kind_counts": {"image": 1},
                "artifact_kind_count": 1,
                "inspection_command_count": 0,
                "inspection_commands": [],
                "config_review_path_count": 0,
                "config_review_paths": [],
                "config_review_command_count": 0,
                "config_review_commands": [],
                "validation_evidence_target_count": 1,
                "validation_evidence_targets": ["Artifacts/Screenshots/frame_0001.png"],
                "execution_entrypoint_count": 0,
                "execution_entrypoints": [],
                "notebook_path_count": 0,
                "notebook_paths": [],
            },
            "connector_registry": {"summary": "none", "connection_count": 0, "status_counts": {}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 0, "ready_families": [], "provider_counts": {}, "provider_count": 0, "category_counts": {}, "category_count": 0, "connection_source_counts": {}, "connection_source_count": 0, "available_action_count": 0, "catalog": [], "connections": []},
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": "win-selected", "lane_count": 0, "ready_lane_count": 0, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": [], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_spatial_asset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Spatial not applicable.",
            "governance_status": "not_applicable",
            "repo_mode_enabled": False,
            "repo_mode": None,
            "frameworks": [],
            "product_workflows": [],
            "recommended_feature_ids": [],
            "asset_count": 0,
            "asset_paths": [],
            "asset_extensions": [],
            "config_paths": [],
            "primary_scene_path": None,
            "headless_runner_status": "unavailable",
            "browser_lane_status": "unavailable",
            "recommended_transport_mode": "discovery_needed",
            "build_commands": [],
            "render_commands": [],
            "conversion_commands": [],
            "capture_commands": [],
            "benchmark_commands": [],
            "validation_status": "not_applicable",
            "validation_available": False,
            "validation_step_count": 0,
            "validation_evidence_targets": [],
            "supports_visual_regression": False,
            "quality_gate_blocker_count": 0,
            "quality_gate_missing_evidence_count": 0,
            "pending_approval_count": 0,
            "pending_question_count": 0,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": [],
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": None, "lane_count": 0, "ready_lane_count": 0, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": [], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
            "artifact_transport": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": None, "preflight_ready": False, "sync_enabled": False, "recommended_transport_mode": "discovery_needed", "blocking_reasons": [], "ready_platform_lanes": [], "partial_platform_lanes": [], "notes": [], "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": False, "summary": "stub", "artifact_count": 0, "artifact_paths": [], "artifact_extensions": [], "artifact_extension_count": 0, "artifact_kind_summaries": [], "artifact_kind_counts": {}, "artifact_kind_count": 0, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 0, "validation_evidence_targets": [], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []}, "connector_registry": {"summary": "none", "connection_count": 0, "status_counts": {}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 0, "ready_families": [], "provider_counts": {}, "provider_count": 0, "category_counts": {}, "category_count": 0, "connection_source_counts": {}, "connection_source_count": 0, "available_action_count": 0, "catalog": [], "connections": []}, "artifact_contract": {"sync_enabled": False}, "connector_contract": {}},
        },
    )
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})

    create = client.post(
        "/api/projects",
        json={
            "name": "Game Engine Selected Target Demo",
            "idea": "Need governance to reject engine lanes on the wrong selected host.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/game-engine-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["selected_target_id"] == "win-selected"
    assert payload["governance_status"] == "blocked"
    assert payload["playable_contract_status"] == "partial"
    assert payload["task_routing_status"] == "blocked"
    assert payload["engine_test_matrix_status"] == "blocked"
    assert payload["publish_gate_status"] == "blocked"
    assert payload["unity_lane_status"] == "unavailable"
    assert payload["recommended_runner_lane"] == "discovery_needed"
    assert payload["blocking_reasons"] == [
        "Unity project signals are present, but no Unity runner lane is bound to the selected broker target."
    ]
    assert "Bind the selected broker target to a Unity-capable runner lane so EditMode or PlayMode tests can run through Mission Control." in payload["recommended_fixes"]
    assert "Selected broker target is `win-selected`." in payload["notes"]


def test_game_engine_governance_summary_route_calls_out_missing_normalized_rollups(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-game-engine-governance-missing-rollup"
    (workspace / "Assets" / "Scenes").mkdir(parents=True, exist_ok=True)
    (workspace / "ProjectSettings").mkdir(parents=True, exist_ok=True)
    (workspace / "Assets" / "Tests").mkdir(parents=True, exist_ok=True)
    (workspace / "Artifacts" / "Screenshots").mkdir(parents=True, exist_ok=True)
    (workspace / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.0f1\n", encoding="utf-8")
    (workspace / "Assets" / "Scenes" / "MainMenu.unity").write_text("scene\n", encoding="utf-8")
    (workspace / "Assets" / "Tests" / "SmokeTest.cs").write_text("// test\n", encoding="utf-8")
    (workspace / "Artifacts" / "Screenshots" / "frame_0001.png").write_text("png\n", encoding="utf-8")
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Unity lane is ready.",
            "selected_target_id": "win-unity",
            "lane_count": 3,
            "ready_lane_count": 2,
            "partial_lane_count": 1,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["unity", "windows"],
            "partial_lane_ids": ["browser"],
            "unavailable_lane_ids": [],
            "lanes": [
                {"lane_id": "unity", "title": "Unity Runner", "status": "ready", "summary": "ready", "target_ids": ["win-unity"], "target_count": 1, "selected_target_ids": ["win-unity"], "os_families": ["windows"], "toolchains": ["unity6000"], "command_families": ["unity_batchmode"], "recommended_commands": ["Unity -batchmode -runTests"], "notes": []},
                {"lane_id": "unreal", "title": "Unreal Runner", "status": "unavailable", "summary": "unavailable", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": [], "command_families": [], "recommended_commands": ["RunUAT BuildCookRun"], "notes": []},
                {"lane_id": "browser", "title": "Browser Runner", "status": "partial", "summary": "partial", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": ["playwright"], "command_families": ["browser"], "recommended_commands": ["playwright test"], "notes": []},
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_design_transfer_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Design transfer is artifact-only.",
            "recommended_ingestion_mode": "artifact_only",
            "figma_connected": False,
            "design_artifact_count": 1,
            "design_artifact_paths": ["Artifacts/Screenshots/frame_0001.png"],
            "design_artifact_formats": [".png"],
            "browser_lane_status": "partial",
            "browser_lane_target_ids": [],
            "supports_visual_regression": True,
            "code_conformance_ready": False,
            "blocking_reasons": [],
            "notes": ["Artifacts can drive screenshot-based conformance."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts", "artifact_count": 1, "artifact_paths": ["Artifacts/Screenshots/frame_0001.png"], "artifact_extensions": [".png"], "artifact_extension_count": 1, "artifact_kind_summaries": ["image:1"], "artifact_kind_counts": {"image": 1}, "artifact_kind_count": 1, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 1, "validation_evidence_targets": ["Artifacts/Screenshots/frame_0001.png"], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []},
            "connector_registry": {"summary": "none", "connection_count": 0, "status_counts": {}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 0, "ready_families": [], "provider_counts": {}, "provider_count": 0, "category_counts": {}, "category_count": 0, "connection_source_counts": {}, "connection_source_count": 0, "available_action_count": 0, "catalog": [], "connections": []},
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": "win-unity", "lane_count": 0, "ready_lane_count": 0, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": [], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_spatial_asset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Spatial not applicable.",
            "governance_status": "not_applicable",
            "repo_mode_enabled": False,
            "repo_mode": None,
            "frameworks": [],
            "product_workflows": [],
            "recommended_feature_ids": [],
            "asset_count": 0,
            "asset_paths": [],
            "asset_extensions": [],
            "config_paths": [],
            "primary_scene_path": None,
            "headless_runner_status": "unavailable",
            "browser_lane_status": "partial",
            "recommended_transport_mode": "discovery_needed",
            "build_commands": [],
            "render_commands": [],
            "conversion_commands": [],
            "capture_commands": [],
            "benchmark_commands": [],
            "validation_status": "not_applicable",
            "validation_available": False,
            "validation_step_count": 0,
            "validation_evidence_targets": [],
            "supports_visual_regression": False,
            "quality_gate_blocker_count": 0,
            "quality_gate_missing_evidence_count": 0,
            "pending_approval_count": 0,
            "pending_question_count": 0,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": [],
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": None, "lane_count": 0, "ready_lane_count": 0, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": [], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
            "artifact_transport": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": None, "preflight_ready": False, "sync_enabled": False, "recommended_transport_mode": "discovery_needed", "blocking_reasons": [], "ready_platform_lanes": [], "partial_platform_lanes": [], "notes": [], "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": False, "summary": "stub", "artifact_count": 0, "artifact_paths": [], "artifact_extensions": [], "artifact_extension_count": 0, "artifact_kind_summaries": [], "artifact_kind_counts": {}, "artifact_kind_count": 0, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 0, "validation_evidence_targets": [], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []}, "connector_registry": {"summary": "none", "connection_count": 0, "status_counts": {}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 0, "ready_families": [], "provider_counts": {}, "provider_count": 0, "category_counts": {}, "category_count": 0, "connection_source_counts": {}, "connection_source_count": 0, "available_action_count": 0, "catalog": [], "connections": []}, "artifact_contract": {"sync_enabled": False}, "connector_contract": {}},
        },
    )
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})

    create = client.post(
        "/api/projects",
        json={
            "name": "Game Engine Governance Missing Rollup Demo",
            "idea": "Need missing rollup blockers surfaced explicitly.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/game-engine-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "partial"
    assert payload["normalized_results_summary_path"] is None
    assert payload["normalized_results_status"] == "missing"
    assert payload["publish_gate_status"] == "blocked"
    assert payload["publish_blocker_count"] == 1
    assert payload["publish_blockers"] == [
        "No normalized Unity/Unreal result rollup exists yet, so publish evidence is still missing."
    ]
    assert "Generate normalized Unity/Unreal result rollups before publish so the engine lane has a governed pass/fail artifact instead of raw logs and vibes." in payload["recommended_fixes"]
    assert "Normalized engine evidence is missing, so publish review has no rollup to trust yet." in payload["notes"]

    plan = client.post(f"/api/projects/{project_id}/game-engine-governance/plan")
    assert plan.status_code == 200, plan.text
    plan_payload = plan.json()
    assert plan_payload["plan_status"] == "partial"
    assert plan_payload["normalized_publish_ready"] is False
    validation_lane_plan = json.loads((workspace / "artifacts" / "game-engine-governance" / "validation-lane-plan.json").read_text(encoding="utf-8"))
    assert validation_lane_plan["publish_blockers"] == [
        "Normalized Unity/Unreal result rollups still contain missing, failed, or parse-error evidence."
    ]


def test_game_engine_governance_summary_route_keeps_publish_gate_blocked_when_quality_gates_fail(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-game-engine-governance-quality-gates"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service._build_game_engine_workspace_profile",
        lambda project: {
            "unity_detected": True,
            "unreal_detected": False,
            "detected_engines": ["unity"],
            "detected_project_paths": ["ProjectSettings/ProjectVersion.txt"],
            "scene_or_map_paths": ["Assets/Scenes/MainMenu.unity"],
            "automation_signal_paths": ["Assets/Tests/SmokeTest.cs"],
            "screenshot_artifact_paths": ["Artifacts/Screenshots/frame_0001.png"],
        },
    )
    monkeypatch.setattr(
        "manager.service._load_game_engine_normalized_results_summary",
        lambda workspace_root: {
            "normalized_results_summary_path": "artifacts/game-engine-governance/normalized-results-summary.json",
            "normalized_summary_count": 3,
            "normalized_passed_count": 3,
            "normalized_failed_count": 0,
            "normalized_missing_count": 0,
            "normalized_publish_ready": True,
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Unity lane is ready.",
            "selected_target_id": "win-unity",
            "lane_count": 3,
            "ready_lane_count": 2,
            "partial_lane_count": 1,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["unity", "windows"],
            "partial_lane_ids": ["browser"],
            "unavailable_lane_ids": [],
            "lanes": [
                {"lane_id": "unity", "title": "Unity Runner", "status": "ready", "summary": "ready", "target_ids": ["win-unity"], "target_count": 1, "selected_target_ids": ["win-unity"], "os_families": ["windows"], "toolchains": ["unity6000"], "command_families": ["unity_batchmode"], "recommended_commands": ["Unity -batchmode -runTests"], "notes": []},
                {"lane_id": "unreal", "title": "Unreal Runner", "status": "unavailable", "summary": "unavailable", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": [], "command_families": [], "recommended_commands": ["RunUAT BuildCookRun"], "notes": []},
                {"lane_id": "browser", "title": "Browser Runner", "status": "partial", "summary": "partial", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": ["playwright"], "command_families": ["browser"], "recommended_commands": ["playwright test"], "notes": []},
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_design_transfer_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Design transfer is artifact-only.",
            "recommended_ingestion_mode": "artifact_only",
            "figma_connected": False,
            "design_artifact_count": 1,
            "design_artifact_paths": ["Artifacts/Screenshots/frame_0001.png"],
            "design_artifact_formats": [".png"],
            "browser_lane_status": "partial",
            "browser_lane_target_ids": [],
            "supports_visual_regression": True,
            "code_conformance_ready": False,
            "blocking_reasons": [],
            "notes": ["Artifacts can drive screenshot-based conformance."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts", "artifact_count": 1, "artifact_paths": ["Artifacts/Screenshots/frame_0001.png"], "artifact_extensions": [".png"], "artifact_extension_count": 1, "artifact_kind_summaries": ["image:1"], "artifact_kind_counts": {"image": 1}, "artifact_kind_count": 1, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 1, "validation_evidence_targets": ["Artifacts/Screenshots/frame_0001.png"], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []},
            "connector_registry": {"summary": "none", "connection_count": 0, "status_counts": {}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 0, "ready_families": [], "provider_counts": {}, "provider_count": 0, "category_counts": {}, "category_count": 0, "connection_source_counts": {}, "connection_source_count": 0, "available_action_count": 0, "catalog": [], "connections": []},
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": "win-unity", "lane_count": 0, "ready_lane_count": 0, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": [], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_spatial_asset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Spatial not applicable.",
            "governance_status": "not_applicable",
            "repo_mode_enabled": False,
            "repo_mode": None,
            "frameworks": [],
            "product_workflows": [],
            "recommended_feature_ids": [],
            "asset_count": 0,
            "asset_paths": [],
            "asset_extensions": [],
            "config_paths": [],
            "primary_scene_path": None,
            "headless_runner_status": "unavailable",
            "browser_lane_status": "partial",
            "recommended_transport_mode": "discovery_needed",
            "build_commands": [],
            "render_commands": [],
            "conversion_commands": [],
            "capture_commands": [],
            "benchmark_commands": [],
            "validation_status": "not_applicable",
            "validation_available": False,
            "validation_step_count": 0,
            "validation_evidence_targets": [],
            "supports_visual_regression": False,
            "quality_gate_blocker_count": 0,
            "quality_gate_missing_evidence_count": 0,
            "pending_approval_count": 0,
            "pending_question_count": 0,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": [],
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": None, "lane_count": 0, "ready_lane_count": 0, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": [], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
            "artifact_transport": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": None, "preflight_ready": False, "sync_enabled": False, "recommended_transport_mode": "discovery_needed", "blocking_reasons": [], "ready_platform_lanes": [], "partial_platform_lanes": [], "notes": [], "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": False, "summary": "stub", "artifact_count": 0, "artifact_paths": [], "artifact_extensions": [], "artifact_extension_count": 0, "artifact_kind_summaries": [], "artifact_kind_counts": {}, "artifact_kind_count": 0, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 0, "validation_evidence_targets": [], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []}, "connector_registry": {"summary": "none", "connection_count": 0, "status_counts": {}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 0, "ready_families": [], "provider_counts": {}, "provider_count": 0, "category_counts": {}, "category_count": 0, "connection_source_counts": {}, "connection_source_count": 0, "available_action_count": 0, "catalog": [], "connections": []}, "artifact_contract": {"sync_enabled": False}, "connector_contract": {}},
        },
    )
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 1})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})

    create = client.post(
        "/api/projects",
        json={
            "name": "Game Engine Governance Quality Gate Demo",
            "idea": "Need publish gate to stay blocked when project quality gates fail.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/game-engine-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "partial"
    assert payload["playable_contract_status"] == "ready"
    assert payload["normalized_publish_ready"] is True
    assert payload["quality_gate_blocker_count"] == 1
    assert payload["publish_gate_status"] == "blocked"
    assert payload["publish_blocker_count"] == 1
    assert payload["publish_blockers"] == ["1 quality gate blocker(s) still prevent publish review."]
    assert any("publish gate is `blocked`" in note for note in payload["notes"])
    assert "Resolve required project quality gates before treating the game pipeline as publish-ready." in payload["recommended_fixes"]


def test_game_engine_governance_plan_route_generates_playable_and_publish_manifests(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-game-engine-plan"
    (workspace / "Assets" / "Scenes").mkdir(parents=True)
    (workspace / "ProjectSettings").mkdir(parents=True)
    (workspace / "Tests").mkdir(parents=True)
    (workspace / "artifacts" / "game-engine-governance").mkdir(parents=True)
    (workspace / "artifacts" / "renders").mkdir(parents=True)
    (workspace / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.0f1\n", encoding="utf-8")
    (workspace / "Assets" / "Scenes" / "MainMenu.unity").write_text("%YAML 1.1\n", encoding="utf-8")
    (workspace / "Tests" / "SmokeTests.cs").write_text("// smoke\n", encoding="utf-8")
    (workspace / "artifacts" / "game-engine-governance" / "unity-editmode-results.xml").write_text(
        '<testsuite tests="2" failures="0" errors="0" skipped="0" time="1.25"></testsuite>\n',
        encoding="utf-8",
    )
    (workspace / "artifacts" / "game-engine-governance" / "unity-playmode-results.xml").write_text(
        '<testsuite tests="3" failures="0" errors="0" skipped="1" time="2.50"></testsuite>\n',
        encoding="utf-8",
    )
    (workspace / "artifacts" / "renders" / "frame_0001.png").write_bytes(b"png")

    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Unity lane is available and browser lane is partial.",
            "selected_target_id": None,
            "lane_count": 3,
            "ready_lane_count": 1,
            "partial_lane_count": 1,
            "unavailable_lane_count": 1,
            "ready_lane_ids": ["unity"],
            "partial_lane_ids": ["browser"],
            "unavailable_lane_ids": ["unreal"],
            "lanes": [
                {"lane_id": "unity", "label": "Unity", "status": "ready", "ready": True, "reason": "Unity CLI available."},
                {"lane_id": "browser", "label": "Browser", "status": "partial", "ready": False, "reason": "Browser capture partial."},
                {"lane_id": "unreal", "label": "Unreal", "status": "unavailable", "ready": False, "reason": "No Unreal runner."},
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_design_transfer_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Design transfer summary stub.",
            "governance_status": "partial",
            "design_intent_status": "partial",
            "code_conformance_status": "partial",
            "supports_visual_regression": True,
            "artifact_count": 0,
            "artifact_paths": [],
            "artifact_extensions": [],
            "token_count": 0,
            "token_paths": [],
            "component_map_count": 0,
            "component_map_paths": [],
            "flow_count": 0,
            "flow_paths": [],
            "code_conformance_signal_count": 0,
            "screenshot_diff_signal_count": 0,
            "dom_aria_signal_count": 0,
            "state_coverage_signal_count": 0,
            "recommended_feature_ids": [],
            "pending_question_count": 0,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Design transfer can already supply screenshot diff evidence."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": False, "summary": "stub", "artifact_count": 0, "artifact_paths": [], "artifact_extensions": [], "artifact_extension_count": 0, "artifact_kind_summaries": [], "artifact_kind_counts": {}, "artifact_kind_count": 0, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 0, "validation_evidence_targets": [], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []},
            "connector_governance": {"summary": "stub", "connection_count": 0, "status_counts": {}, "ready_family_count": 0, "ready_families": [], "provider_counts": {}, "provider_count": 0, "category_counts": {}, "category_count": 0, "connection_source_counts": {}, "connection_source_count": 0, "available_action_count": 0, "catalog": [], "connections": []},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_spatial_asset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "stub",
            "governance_status": "partial",
            "repo_mode_enabled": False,
            "repo_mode": None,
            "frameworks": [],
            "product_workflows": [],
            "recommended_feature_ids": [],
            "asset_count": 0,
            "asset_paths": [],
            "asset_extensions": [],
            "config_paths": [],
            "primary_scene_path": None,
            "headless_runner_status": "unavailable",
            "browser_lane_status": "partial",
            "recommended_transport_mode": "discovery_needed",
            "build_commands": [],
            "render_commands": [],
            "conversion_commands": [],
            "capture_commands": [],
            "benchmark_commands": [],
            "validation_status": "not_applicable",
            "validation_available": False,
            "validation_step_count": 0,
            "validation_evidence_targets": [],
            "supports_visual_regression": True,
            "quality_gate_blocker_count": 0,
            "quality_gate_missing_evidence_count": 0,
            "pending_approval_count": 0,
            "pending_question_count": 0,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Spatial governance already exposes render evidence."],
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": None, "lane_count": 0, "ready_lane_count": 0, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": [], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
            "artifact_transport": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": None, "preflight_ready": False, "sync_enabled": False, "recommended_transport_mode": "discovery_needed", "blocking_reasons": [], "ready_platform_lanes": [], "partial_platform_lanes": [], "notes": [], "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": False, "summary": "stub", "artifact_count": 0, "artifact_paths": [], "artifact_extensions": [], "artifact_extension_count": 0, "artifact_kind_summaries": [], "artifact_kind_counts": {}, "artifact_kind_count": 0, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 0, "validation_evidence_targets": [], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []}},
        },
    )
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})

    create = client.post(
        "/api/projects",
        json={
            "name": "Game Engine Plan Demo",
            "idea": "Need governed playable manifests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/game-engine-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["detected_engines"] == ["unity"]
    assert payload["engine_count"] == 1
    assert payload["playable_contract_status"] == "ready"
    assert payload["selected_target_id"] is None
    assert payload["ready_execution_lane_count"] == 1
    assert payload["command_bundle_count"] == 6
    assert payload["manifest_root"] == "artifacts/game-engine-governance"
    assert payload["playable_definition_path"] == "artifacts/game-engine-governance/playable-definition.json"
    assert payload["scene_governance_path"] == "artifacts/game-engine-governance/scene-governance.json"
    assert payload["asset_lock_plan_path"] == "artifacts/game-engine-governance/asset-lock-plan.json"
    assert payload["task_routing_plan_path"] == "artifacts/game-engine-governance/task-routing-plan.json"
    assert payload["content_budget_plan_path"] == "artifacts/game-engine-governance/content-budget-plan.json"
    assert payload["automation_pack_path"] == "artifacts/game-engine-governance/automation-pack.json"
    assert payload["engine_test_matrix_path"] == "artifacts/game-engine-governance/engine-test-matrix.json"
    assert payload["validation_lane_plan_path"] == "artifacts/game-engine-governance/validation-lane-plan.json"
    assert payload["evidence_contract_path"] == "artifacts/game-engine-governance/evidence-contract.json"
    assert payload["result_normalization_plan_path"] == "artifacts/game-engine-governance/result-normalization-plan.json"
    assert payload["normalized_results_summary_path"] == "artifacts/game-engine-governance/normalized-results-summary.json"
    assert payload["normalized_summary_count"] >= 3
    assert payload["normalized_passed_count"] >= 2
    assert payload["normalized_failed_count"] == 0
    assert payload["normalized_missing_count"] == 0
    assert payload["normalized_publish_ready"] is True
    assert payload["publish_gate_status"] == "ready"
    assert payload["publish_blocker_count"] == 0
    assert payload["publish_blockers"] == []
    assert payload["screenshot_regression_plan_path"] == "artifacts/game-engine-governance/screenshot-regression-plan.json"
    assert payload["publish_gate_path"] == "artifacts/game-engine-governance/publish-gates.json"
    assert payload["approval_checkpoint_path"] == "artifacts/game-engine-governance/approval-checkpoints.json"

    assert (workspace / "artifacts" / "game-engine-governance" / "playable-definition.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "scene-governance.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "asset-lock-plan.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "task-routing-plan.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "content-budget-plan.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "automation-pack.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "engine-test-matrix.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "validation-lane-plan.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "evidence-contract.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "result-normalization-plan.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "normalized-results-summary.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "screenshot-regression-plan.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "publish-gates.json").exists()
    assert (workspace / "artifacts" / "game-engine-governance" / "approval-checkpoints.json").exists()

    playable_definition = json.loads((workspace / "artifacts" / "game-engine-governance" / "playable-definition.json").read_text(encoding="utf-8"))
    assert playable_definition["recommended_runner_lane"] == "unity"
    assert "golden_path_map" in playable_definition["required_checks"]
    assert playable_definition["playable_targets"][0]["path"] == "Assets/Scenes/MainMenu.unity"
    lane_matrix = {item["engine"]: item for item in playable_definition["engine_lane_matrix"]}
    assert lane_matrix["unity"]["lane_status"] == "ready"
    assert lane_matrix["browser"]["selected_for_validation"] is False

    scene_governance = json.loads((workspace / "artifacts" / "game-engine-governance" / "scene-governance.json").read_text(encoding="utf-8"))
    assert scene_governance["ownership_rules"]["content_task_requires_asset_lock_review"] is True
    assert ".unity" in scene_governance["ownership_rules"]["lock_required_asset_suffixes"]
    assert scene_governance["scene_targets"][0]["golden_path_candidate"] is True

    asset_lock_plan = json.loads((workspace / "artifacts" / "game-engine-governance" / "asset-lock-plan.json").read_text(encoding="utf-8"))
    assert asset_lock_plan["lock_rules"]["content_task_requires_asset_lock_review"] is True
    assert ".unity" in asset_lock_plan["lock_rules"]["lock_required_asset_suffixes"]
    assert "Assets/**/*.unity" in asset_lock_plan["ownership_zones"]["content_owned_path_globs"]

    task_routing_plan = json.loads((workspace / "artifacts" / "game-engine-governance" / "task-routing-plan.json").read_text(encoding="utf-8"))
    routing_profiles = {item["task_type"]: item for item in task_routing_plan["routing_profiles"]}
    assert routing_profiles["code"]["content_lock_required"] is False
    assert routing_profiles["content"]["content_lock_required"] is True
    assert "publish_gate" in routing_profiles["mixed"]["required_gates"]
    assert task_routing_plan["handoff_rules"]["mixed_tasks_require_explicit_publish_gate"] is True

    content_budget_plan = json.loads((workspace / "artifacts" / "game-engine-governance" / "content-budget-plan.json").read_text(encoding="utf-8"))
    assert content_budget_plan["budget_requirements"]["performance_budget_required"] is True
    assert "draw_calls" in content_budget_plan["budget_categories"]
    assert "Assets" in content_budget_plan["detected_project_paths"]
    assert content_budget_plan["engine_targets"] == ["unity"]

    automation_pack = json.loads((workspace / "artifacts" / "game-engine-governance" / "automation-pack.json").read_text(encoding="utf-8"))
    unity_lane = next(item for item in automation_pack["engine_native_lanes"] if item["engine"] == "unity")
    assert unity_lane["lane_status"] == "ready"
    assert "PlayMode" in unity_lane["required_test_modes"]
    assert automation_pack["publish_requirements"]["repo_owned_tests_required"] is True

    engine_test_matrix = json.loads((workspace / "artifacts" / "game-engine-governance" / "engine-test-matrix.json").read_text(encoding="utf-8"))
    unity_test_matrix = next(item for item in engine_test_matrix["engines"] if item["engine"] == "unity")
    assert unity_test_matrix["plugin_pack_required"] is False
    assert "EditMode" in unity_test_matrix["required_test_modes"]
    assert engine_test_matrix["task_boundaries"]["mixed_code_and_content_publish_requires_extra_review"] is True

    validation_lane_plan = json.loads((workspace / "artifacts" / "game-engine-governance" / "validation-lane-plan.json").read_text(encoding="utf-8"))
    assert validation_lane_plan["selected_target_id"] is None
    assert validation_lane_plan["ready_execution_lane_ids"] == ["unity"]
    unity_validation_lane = next(item for item in validation_lane_plan["execution_lanes"] if item["engine"] == "unity")
    assert unity_validation_lane["project_file_path"] == "ProjectSettings/ProjectVersion.txt"
    assert unity_validation_lane["golden_path_target"] == "Assets/Scenes/MainMenu.unity"
    assert unity_validation_lane["command_bundles"][0]["bundle_id"] == "unity_editmode_tests"
    assert "unity-editmode-results.xml" in unity_validation_lane["command_bundles"][0]["expected_outputs"][0]

    evidence_contract = json.loads((workspace / "artifacts" / "game-engine-governance" / "evidence-contract.json").read_text(encoding="utf-8"))
    assert evidence_contract["required_evidence"][0]["evidence_id"] == "engine_native_test_results"
    assert evidence_contract["engine_expectations"]["unity"]["project_file_path"] == "ProjectSettings/ProjectVersion.txt"
    assert evidence_contract["engine_expectations"]["unreal"]["plugin_pack_required"] is True

    result_normalization_plan = json.loads((workspace / "artifacts" / "game-engine-governance" / "result-normalization-plan.json").read_text(encoding="utf-8"))
    unity_normalizer = next(item for item in result_normalization_plan["normalizers"] if item["normalizer_id"] == "unity_editmode_results")
    assert unity_normalizer["result_format"] == "junit_xml"
    assert "tests" in unity_normalizer["extract_fields"]
    unreal_normalizer = next(item for item in result_normalization_plan["normalizers"] if item["normalizer_id"] == "unreal_automation_log")
    assert unreal_normalizer["parser_strategy"] == "keyword_and_phase_scan"
    assert "Fatal error:" in unreal_normalizer["failure_markers"]
    assert result_normalization_plan["normalized_output_contract"]["rollup_artifact"] == "artifacts/game-engine-governance/normalized-results-summary.json"

    normalized_results_summary = json.loads((workspace / "artifacts" / "game-engine-governance" / "normalized-results-summary.json").read_text(encoding="utf-8"))
    assert normalized_results_summary["passed_count"] >= 2
    assert normalized_results_summary["publish_ready"] is True
    normalized_by_artifact = {item["output_artifact"]: item for item in normalized_results_summary["summaries"]}
    assert normalized_by_artifact["artifacts/game-engine-governance/unity-editmode-summary.json"]["status"] == "passed"
    assert normalized_by_artifact["artifacts/game-engine-governance/unity-playmode-summary.json"]["tests"] == 3
    assert normalized_by_artifact["artifacts/game-engine-governance/golden-path-capture-summary.json"]["frame_count"] == 1

    screenshot_regression_plan = json.loads((workspace / "artifacts" / "game-engine-governance" / "screenshot-regression-plan.json").read_text(encoding="utf-8"))
    assert screenshot_regression_plan["visual_regression_ready"] is True
    assert screenshot_regression_plan["evidence_requirements"]["fixed_camera_required"] is True
    assert screenshot_regression_plan["evidence_requirements"]["replay_capture_review_required"] is True
    assert "artifacts/renders/frame_0001.png" in screenshot_regression_plan["screenshot_artifact_paths"]

    publish_gates = json.loads((workspace / "artifacts" / "game-engine-governance" / "publish-gates.json").read_text(encoding="utf-8"))
    gate_ids = [item["gate_id"] for item in publish_gates["gates"]]
    assert "scene_governance_review" in gate_ids
    assert "engine_test_matrix_review" in gate_ids
    assert "result_normalization_review" in gate_ids
    assert "screenshot_regression_review" in gate_ids
    assert "publish_gate" in gate_ids
    publish_gate_by_id = {item["gate_id"]: item for item in publish_gates["gates"]}
    assert publish_gate_by_id["result_normalization_review"]["status"] == "ready"
    assert publish_gate_by_id["publish_gate"]["status"] == "ready"

    approval_checkpoints = json.loads((workspace / "artifacts" / "game-engine-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    checkpoint_ids = [item["checkpoint_id"] for item in approval_checkpoints["checkpoints"]]
    assert "engine_lane_ready_review" in checkpoint_ids
    assert "evidence_contract_review" in checkpoint_ids
    assert "normalized_results_review" in checkpoint_ids
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_by_id["normalized_results_review"]["status"] == "ready"


def test_game_engine_governance_plan_route_keeps_publish_manifests_blocked_when_quality_gates_fail(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-game-engine-plan-quality-gates"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_game_engine_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Game-engine governance is partial because project quality gates still block publish.",
            "governance_status": "partial",
            "detected_engines": ["unity"],
            "unity_detected": True,
            "unreal_detected": False,
            "detected_project_paths": ["ProjectSettings/ProjectVersion.txt"],
            "scene_or_map_count": 1,
            "scene_or_map_paths": ["Assets/Scenes/MainMenu.unity"],
            "automation_signal_count": 1,
            "automation_signal_paths": ["Assets/Tests/SmokeTest.cs"],
            "screenshot_artifact_count": 1,
            "screenshot_artifact_paths": ["artifacts/renders/frame_0001.png"],
            "playable_contract_status": "ready",
            "asset_lock_status": "ready",
            "task_routing_status": "ready",
            "engine_test_matrix_status": "ready",
            "publish_gate_status": "blocked",
            "normalized_results_status": "ready",
            "publish_blocker_count": 1,
            "publish_blockers": ["1 quality gate blocker(s) still prevent publish review."],
            "repo_owned_tests_required": True,
            "content_task_asset_lock_required": True,
            "mixed_task_publish_review_required": True,
            "visual_regression_ready": True,
            "normalized_results_summary_path": "artifacts/game-engine-governance/normalized-results-summary.json",
            "normalized_summary_count": 3,
            "normalized_passed_count": 3,
            "normalized_failed_count": 0,
            "normalized_missing_count": 0,
            "normalized_publish_ready": True,
            "unity_lane_status": "ready",
            "unreal_lane_status": "unavailable",
            "browser_lane_status": "partial",
            "recommended_runner_lane": "unity",
            "quality_gate_blocker_count": 1,
            "pending_question_count": 0,
            "blocking_reasons": [],
            "recommended_fixes": ["Resolve required project quality gates before publish."],
            "notes": ["Quality gates still block publish despite clean normalized engine evidence."],
            "platform_runners": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "Unity lane is ready.",
                "selected_target_id": None,
                "lane_count": 3,
                "ready_lane_count": 2,
                "partial_lane_count": 1,
                "unavailable_lane_count": 0,
                "ready_lane_ids": ["unity", "windows"],
                "partial_lane_ids": ["browser"],
                "unavailable_lane_ids": [],
                "lanes": [
                    {"lane_id": "unity", "title": "Unity Runner", "status": "ready", "summary": "ready", "target_ids": ["win-unity"], "target_count": 1, "selected_target_ids": ["win-unity"], "os_families": ["windows"], "toolchains": ["unity6000"], "command_families": ["unity_batchmode"], "recommended_commands": ["Unity -batchmode -runTests"], "notes": []},
                    {"lane_id": "unreal", "title": "Unreal Runner", "status": "unavailable", "summary": "unavailable", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": [], "command_families": [], "recommended_commands": ["RunUAT BuildCookRun"], "notes": []},
                    {"lane_id": "browser", "title": "Browser Runner", "status": "partial", "summary": "partial", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": ["playwright"], "command_families": ["browser"], "recommended_commands": ["playwright test"], "notes": []},
                ],
            },
            "design_transfer": {"summary": "stub"},
            "spatial_governance": {"summary": "stub"},
        },
    )
    monkeypatch.setattr(
        "manager.service._materialize_game_engine_normalized_results",
        lambda workspace_root, *, result_normalization_plan: {
            "summary_count": 3,
            "passed_count": 3,
            "failed_count": 0,
            "missing_count": 0,
            "publish_ready": True,
            "blocking_summary_ids": [],
            "summaries": [
                {
                    "status": "passed",
                    "engine": "unity",
                    "evidence_kind": "junit_xml",
                    "source_path": "artifacts/game-engine-governance/unity-editmode-results.xml",
                    "pass_signal": True,
                    "failure_count": 0,
                    "warning_count": 0,
                    "output_artifact": "artifacts/game-engine-governance/unity-editmode-summary.json",
                }
            ],
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Game Engine Plan Quality Gate Demo",
            "idea": "Need publish manifests to stay blocked when project quality gates fail.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/game-engine-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "partial"
    assert payload["normalized_publish_ready"] is True
    assert payload["publish_gate_status"] == "blocked"
    assert payload["publish_blocker_count"] == 1
    assert payload["publish_blockers"] == ["1 quality gate blocker(s) still prevent publish review."]

    publish_gates = json.loads((workspace / "artifacts" / "game-engine-governance" / "publish-gates.json").read_text(encoding="utf-8"))
    publish_gate_by_id = {item["gate_id"]: item for item in publish_gates["gates"]}
    assert publish_gate_by_id["result_normalization_review"]["status"] == "ready"
    assert publish_gate_by_id["publish_gate"]["status"] == "blocked"
    assert "project quality-gate blockers" in publish_gate_by_id["publish_gate"]["reason"]

    approval_checkpoints = json.loads((workspace / "artifacts" / "game-engine-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_by_id["normalized_results_review"]["status"] == "ready"
    assert checkpoint_by_id["publish_readiness_review"]["status"] == "blocked"
    assert "project quality gates" in checkpoint_by_id["publish_readiness_review"]["reason"]


def test_dataset_governance_summary_route_surfaces_ml_artifacts_validation_and_execution_lane(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-dataset-governance"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_workspace_tooling_status",
        lambda project: {
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "TensorFlow and PyTorch lanes detected.",
            "validation_evidence_targets": ["Capture validation metrics and exported artifact paths."],
            "tensorflow_repo": {
                "enabled": True,
                "frameworks": ["Keras"],
                "product_workflows": ["training_pipeline"],
                "config_paths": ["configs/schema.pbtxt"],
                "important_paths": ["configs/schema.pbtxt"],
                "existing_savedmodel_artifacts": ["exports/saved_model/saved_model.pb"],
                "existing_tflite_artifacts": [],
            },
            "tensorflow_validation_plan": {
                "available": True,
                "status": "ready",
                "repo_mode_enabled": True,
                "repo_mode": "keras_training",
                "steps": [
                    {"title": "Run Keras smoke train", "command": "python train.py --epochs 1", "type": "train", "status": "pending"},
                ],
                "blockers": [],
                "recommended_fixes": [],
                "evidence_targets": ["training metrics", "saved model export"],
                "product_workflows": ["training_pipeline"],
            },
            "pytorch_repo": {
                "enabled": True,
                "frameworks": ["TorchScript"],
                "product_workflows": ["evaluation_pipeline"],
                "config_paths": ["configs/dataset.yaml"],
                "important_paths": ["configs/dataset.yaml"],
                "checkpoint_paths": ["checkpoints/model.ckpt"],
                "existing_onnx_artifacts": ["artifacts/model.onnx"],
                "existing_torchscript_artifacts": ["artifacts/model.pt"],
            },
            "pytorch_runtime_status": {
                "available": True,
                "status": "ready",
                "blockers": [],
                "recommended_fixes": [],
            },
            "pytorch_validation_plan": {
                "available": True,
                "status": "ready",
                "repo_mode_enabled": True,
                "repo_mode": "pytorch_training",
                "runtime_status": "ready",
                "steps": [
                    {"title": "Run eval smoke", "command": "python eval.py --limit 8", "type": "eval", "status": "pending"},
                ],
                "blockers": [],
                "recommended_fixes": [],
                "evidence_targets": ["eval metrics", "checkpoint load"],
                "product_workflows": ["evaluation_pipeline"],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_project_artifact_registry",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "Dataset and model artifacts are present.",
            "artifact_count": 9,
            "artifact_paths": [
                "data/train.parquet",
                "artifacts/model.onnx",
                "checkpoints/model.ckpt",
                "exports/saved_model/saved_model.pb",
                "metadata/dataset_manifest.json",
                "metadata/pii_policy.json",
                "reports/dedupe_report.json",
                "reports/corruption_scan.json",
                "metadata/label_map.json",
            ],
            "artifact_extensions": [".parquet", ".onnx", ".ckpt", ".pb", ".json"],
            "artifact_extension_count": 5,
            "artifact_kind_summaries": ["dataset:6", "model:3"],
            "artifact_kind_counts": {"dataset": 6, "model": 3},
            "artifact_kind_count": 2,
            "inspection_command_count": 0,
            "inspection_commands": [],
            "config_review_path_count": 2,
            "config_review_paths": ["configs/dataset.yaml", "configs/schema.pbtxt"],
            "config_review_command_count": 0,
            "config_review_commands": [],
            "validation_evidence_target_count": 2,
            "validation_evidence_targets": ["data/train.parquet", "artifacts/model.onnx"],
            "execution_entrypoint_count": 2,
            "execution_entrypoints": ["python train.py --epochs 1", "python eval.py --limit 8"],
            "notebook_path_count": 0,
            "notebook_paths": [],
            "recommended_next_steps": [],
            "recommended_next_step_count": 0,
        },
    )
    monkeypatch.setattr(
        "manager.service.build_file_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "File governance is ready for dataset ingress.",
            "recommended_operation_mode": "hybrid_connector_sync",
            "supports_bulk_planning": True,
            "destructive_actions_require_approval": True,
            "storage_lane_count": 1,
            "connected_storage_lane_count": 1,
            "ready_scanner_lane_count": 1,
            "storage_provider_count": 2,
            "storage_providers": ["local_fs", "google_drive"],
            "ready_scanner_lanes": ["linux"],
            "blocking_reasons": [],
            "notes": ["Use dry-run manifests for bulk moves."],
            "storage_lanes": [
                {
                    "lane_id": "local_fs",
                    "title": "Local Filesystem",
                    "status": "connected",
                    "summary": "Local repo lane is ready.",
                    "providers": ["local_fs"],
                    "provider_count": 1,
                    "connection_source": "mission_control",
                    "host_imported": False,
                    "notes": [],
                }
            ],
            "connector_registry": {
                "summary": "Storage connector is ready.",
                "family_count": 1,
                "connection_count": 1,
                "ready_family_count": 1,
                "ready_families": ["storage"],
                "provider_counts": {"google_drive": 1},
                "provider_count": 1,
                "category_counts": {"storage": 1},
                "category_count": 1,
                "connection_source_counts": {"mission_control": 1},
                "connection_source_count": 1,
                "available_action_count": 1,
            },
            "platform_runners": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "Linux lane is ready.",
                "selected_target_id": "gpu-linux",
                "lane_count": 1,
                "ready_lane_count": 1,
                "partial_lane_count": 0,
                "unavailable_lane_count": 0,
                "ready_lane_ids": ["linux"],
                "partial_lane_ids": [],
                "unavailable_lane_ids": [],
                "lanes": [
                    {
                        "lane_id": "linux",
                        "title": "Linux Runner",
                        "status": "ready",
                        "summary": "ready",
                        "target_ids": ["gpu-linux"],
                        "target_count": 1,
                        "selected_target_ids": ["gpu-linux"],
                        "os_families": ["linux"],
                        "toolchains": ["python3.11", "cuda12"],
                        "command_families": ["python"],
                        "recommended_commands": ["python -m pytest"],
                        "notes": [],
                    }
                ],
            },
            "artifact_transport": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "Artifact sync is ready.",
                "selected_target_id": "gpu-linux",
                "preflight_ready": True,
                "sync_enabled": True,
                "recommended_transport_mode": "brokered_sync",
                "blocking_reasons": [],
                "ready_platform_lanes": ["linux"],
                "partial_platform_lanes": [],
                "notes": [],
                "artifact_registry": {
                    "project_id": project.id,
                    "project_name": project.name,
                    "workspace_path": project.workspace_path,
                    "available": True,
                    "summary": "artifacts",
                    "artifact_count": 1,
                    "artifact_paths": ["data/train.parquet"],
                },
                "connector_registry": {"summary": "Storage connector is ready."},
                "artifact_contract": {
                    "sync_enabled": True,
                    "required": True,
                    "local_artifact_paths": ["data/train.parquet"],
                    "local_artifact_path_count": 1,
                    "target_artifact_roots": ["/srv/work/artifacts"],
                    "selected_artifact_root": "/srv/work/artifacts",
                    "preflight_ready": True,
                },
                "connector_contract": {
                    "required_connector_families": ["storage"],
                    "target_connector_families": ["storage"],
                    "available_families": ["storage"],
                    "available_connector_count": 1,
                    "missing_required_families": [],
                    "preflight_ready": True,
                },
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_execution_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "NVIDIA governance is ready.",
            "governance_status": "ready",
            "recommended_execution_lane": "nvidia_dynamo",
            "cuda_repo_enabled": True,
            "validation_status": "ready",
            "local_runtime_status": "ready",
            "gpu_diagnostics_status": "ready",
            "aiq_status": "ready",
            "remote_gpu_target_count": 1,
            "ready_remote_gpu_target_count": 1,
            "selected_remote_target_id": "gpu-linux",
            "selected_remote_target_gpu": "RTX 4090",
            "provider_ready_ids": ["nvidia_dynamo"],
            "provider_partial_ids": [],
            "available_provider_count": 1,
            "sanitizer_ready": True,
            "profiler_ready": True,
            "container_smoke_ready": True,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["GPU execution is governed."],
            "dynamo_status": {
                "project_id": project.id,
                "project_name": project.name,
                "endpoint": "http://dynamo.local:8000",
                "summary": "Dynamo is ready.",
                "available": True,
                "reachable": True,
                "endpoint_configured": True,
                "api_key_configured": True,
                "auth_required": True,
                "authenticated": True,
                "runtime_ready": True,
                "runtime_status": "ready",
                "runtime_summary": "ready",
            },
            "nim_status": {
                "project_id": project.id,
                "project_name": project.name,
                "endpoint": "https://integrate.api.nvidia.com",
                "summary": "NIM is optional here.",
                "available": False,
                "reachable": False,
            },
            "aiq": {
                "project_id": project.id,
                "project_name": project.name,
                "install_status": "ready",
                "summary": "AI-Q ready.",
                "endpoint": "http://aiq.local:8000",
                "available": True,
            },
            "gpu_diagnostics": {
                "project_id": project.id,
                "project_name": project.name,
                "available": True,
                "status": "ready",
                "summary": "Telemetry healthy.",
            },
            "local_runtime": {
                "project_id": project.id,
                "project_name": project.name,
                "available": True,
                "status": "ready",
                "summary": "Local CUDA ready.",
            },
            "validation_plan": {
                "project_id": project.id,
                "project_name": project.name,
                "available": True,
                "status": "ready",
                "summary": "Validation lane ready.",
                "repo_mode_enabled": True,
                "steps": [
                    {
                        "title": "Run GPU eval",
                        "command": "python eval.py --limit 8",
                        "type": "eval",
                        "source": "repo_mode",
                        "status": "pending",
                    }
                ],
            },
            "platform_runners": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "Linux lane ready.",
            },
            "device_broker": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "Broker sees one ready GPU target.",
                "preflight_ready": True,
                "selected_target_id": "gpu-linux",
                "recommended_target_ids": ["gpu-linux"],
                "blocking_reasons": [],
                "ready_target_count": 1,
                "artifact_registry": {
                    "project_id": project.id,
                    "project_name": project.name,
                    "workspace_path": project.workspace_path,
                    "available": True,
                    "summary": "artifacts",
                },
                "connector_registry": {"summary": "storage"},
                "remote_execution": {
                    "policy": {"enabled": True},
                    "required_runner_family": "external_adapter",
                },
            },
        },
    )
    monkeypatch.setattr("manager.service.build_quality_gate_summary", lambda db, project: {"blocking_gate_count": 0})
    monkeypatch.setattr("manager.service.build_decision_audit_summary", lambda db, project: {"pending_question_count": 0})

    create = client.post(
        "/api/projects",
        json={
            "name": "Dataset Governance Demo",
            "idea": "Need governed dataset and model validation.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/dataset-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["governance_status"] == "ready"
    assert payload["dataset_contract_status"] == "ready"
    assert payload["data_hygiene_status"] == "ready"
    assert payload["repo_mode_enabled"] is True
    assert payload["tensorflow_enabled"] is True
    assert payload["pytorch_enabled"] is True
    assert payload["validation_status"] == "ready"
    assert payload["runtime_status"] == "ready"
    assert payload["recommended_execution_lane"] == "nvidia_dynamo"
    assert payload["supports_gpu_execution"] is True
    assert payload["supports_bulk_file_governance"] is True
    assert payload["dataset_artifact_count"] >= 4
    assert ".parquet" in payload["dataset_artifact_extensions"]
    assert ".onnx" in payload["dataset_artifact_extensions"]
    assert payload["schema_or_config_count"] == 2
    assert payload["checkpoint_artifact_count"] >= 1
    assert payload["provenance_signal_count"] >= 1
    assert payload["split_signal_count"] >= 1
    assert payload["evaluation_signal_count"] >= 1
    assert payload["pii_signal_count"] >= 1
    assert payload["duplication_signal_count"] >= 1
    assert payload["corruption_signal_count"] >= 1
    assert payload["label_coverage_signal_count"] >= 1
    assert payload["validation_step_count"] == 2
    assert "TensorFlow" in payload["detected_frameworks"]
    assert "PyTorch" in payload["detected_frameworks"]
    assert payload["blocking_reasons"] == []
    assert payload["file_governance"]["recommended_operation_mode"] == "hybrid_connector_sync"
    assert payload["nvidia_governance"]["recommended_execution_lane"] == "nvidia_dynamo"


def test_dataset_governance_plan_route_generates_contract_hygiene_and_evaluation_manifests(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-dataset-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_dataset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Dataset governance is ready.",
            "governance_status": "ready",
            "dataset_contract_status": "ready",
            "data_hygiene_status": "ready",
            "repo_mode_enabled": True,
            "tensorflow_enabled": True,
            "pytorch_enabled": True,
            "detected_frameworks": ["TensorFlow", "PyTorch"],
            "detected_product_workflows": ["training_pipeline", "evaluation_pipeline"],
            "dataset_artifact_count": 4,
            "dataset_artifact_paths": ["data/train.parquet", "artifacts/model.onnx", "checkpoints/model.ckpt", "metadata/dataset_manifest.json"],
            "dataset_artifact_extensions": [".parquet", ".onnx", ".ckpt", ".json"],
            "schema_or_config_count": 2,
            "schema_or_config_paths": ["configs/dataset.yaml", "configs/schema.pbtxt"],
            "checkpoint_artifact_count": 1,
            "checkpoint_artifact_paths": ["checkpoints/model.ckpt"],
            "provenance_signal_count": 1,
            "provenance_signals": ["metadata/dataset_manifest.json"],
            "split_signal_count": 1,
            "split_signals": ["data/train.parquet"],
            "evaluation_signal_count": 1,
            "evaluation_signals": ["reports/eval_metrics.json"],
            "pii_signal_count": 1,
            "pii_signals": ["metadata/pii_policy.json"],
            "duplication_signal_count": 1,
            "duplication_signals": ["reports/dedupe_report.json"],
            "corruption_signal_count": 1,
            "corruption_signals": ["reports/corruption_scan.json"],
            "label_coverage_signal_count": 1,
            "label_coverage_signals": ["metadata/label_map.json"],
            "validation_status": "ready",
            "runtime_status": "ready",
            "validation_step_count": 2,
            "validation_evidence_targets": ["reports/eval_metrics.json", "artifacts/model.onnx"],
            "recommended_execution_lane": "nvidia_dynamo",
            "supports_gpu_execution": True,
            "supports_bulk_file_governance": True,
            "quality_gate_blocker_count": 0,
            "pending_question_count": 0,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Dataset contract and hygiene are ready."],
            "file_governance": {
                "recommended_operation_mode": "hybrid_connector_sync",
                "supports_bulk_planning": True,
            },
            "nvidia_governance": {
                "governance_status": "ready",
                "recommended_execution_lane": "nvidia_dynamo",
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Dataset Plan Demo",
            "idea": "Need governed dataset manifests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/dataset-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["detected_frameworks"] == ["TensorFlow", "PyTorch"]
    assert payload["validation_step_count"] == 2
    assert payload["manifest_root"] == "artifacts/dataset-governance"
    assert payload["dataset_contract_path"] == "artifacts/dataset-governance/dataset-contract.json"
    assert payload["data_profile_path"] == "artifacts/dataset-governance/data-profile.json"
    assert payload["pii_review_path"] == "artifacts/dataset-governance/pii-review.json"
    assert payload["split_plan_path"] == "artifacts/dataset-governance/split-plan.json"
    assert payload["duplication_audit_path"] == "artifacts/dataset-governance/duplication-audit.json"
    assert payload["corruption_audit_path"] == "artifacts/dataset-governance/corruption-audit.json"
    assert payload["evaluation_plan_path"] == "artifacts/dataset-governance/evaluation-plan.json"
    assert payload["approval_checkpoint_path"] == "artifacts/dataset-governance/approval-checkpoints.json"

    assert (workspace / "artifacts" / "dataset-governance" / "dataset-contract.json").exists()
    assert (workspace / "artifacts" / "dataset-governance" / "data-profile.json").exists()
    assert (workspace / "artifacts" / "dataset-governance" / "pii-review.json").exists()
    assert (workspace / "artifacts" / "dataset-governance" / "split-plan.json").exists()
    assert (workspace / "artifacts" / "dataset-governance" / "duplication-audit.json").exists()
    assert (workspace / "artifacts" / "dataset-governance" / "corruption-audit.json").exists()
    assert (workspace / "artifacts" / "dataset-governance" / "evaluation-plan.json").exists()
    assert (workspace / "artifacts" / "dataset-governance" / "approval-checkpoints.json").exists()

    dataset_contract = json.loads((workspace / "artifacts" / "dataset-governance" / "dataset-contract.json").read_text(encoding="utf-8"))
    assert dataset_contract["contract_requirements"]["schema_required"] is True
    assert dataset_contract["contract_requirements"]["provenance_required"] is True
    assert dataset_contract["schema_expectations"]["pii_review_required"] is True
    assert ".onnx" in dataset_contract["dataset_artifact_extensions"]
    assert ".parquet" in dataset_contract["dataset_artifact_extensions"]
    assert "metadata/dataset_manifest.json" in dataset_contract["provenance_signals"]

    data_profile = json.loads((workspace / "artifacts" / "dataset-governance" / "data-profile.json").read_text(encoding="utf-8"))
    assert data_profile["storage_lane_support"]["supports_bulk_planning"] is True
    assert data_profile["storage_lane_support"]["destructive_actions_require_approval"] is True
    assert data_profile["profile_expectations"]["row_count_required"] is True

    pii_review = json.loads((workspace / "artifacts" / "dataset-governance" / "pii-review.json").read_text(encoding="utf-8"))
    assert pii_review["approval_required_for_bulk_mutation"] is True
    assert pii_review["screening_scope"]["dataset_artifact_count"] == 4

    split_plan = json.loads((workspace / "artifacts" / "dataset-governance" / "split-plan.json").read_text(encoding="utf-8"))
    assert split_plan["required_splits"] == ["train", "validation", "test"]
    assert "overlap_detection" in split_plan["split_integrity_checks"]

    duplication_audit = json.loads((workspace / "artifacts" / "dataset-governance" / "duplication-audit.json").read_text(encoding="utf-8"))
    assert duplication_audit["dry_run_required_before_mutation"] is True
    assert duplication_audit["cluster_review_required"] is True

    corruption_audit = json.loads((workspace / "artifacts" / "dataset-governance" / "corruption-audit.json").read_text(encoding="utf-8"))
    assert "checksum_or_decode_review" in corruption_audit["integrity_checks"]

    evaluation_plan = json.loads((workspace / "artifacts" / "dataset-governance" / "evaluation-plan.json").read_text(encoding="utf-8"))
    assert evaluation_plan["baseline_compare_required"] is True
    assert evaluation_plan["rollback_ready"] is True
    assert evaluation_plan["quality_thresholds"]["metric_delta_review_required"] is True
    assert "reports/eval_metrics.json" in evaluation_plan["evaluation_signals"]

    approval_checkpoints = json.loads((workspace / "artifacts" / "dataset-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    checkpoint_ids = [item["checkpoint_id"] for item in approval_checkpoints["checkpoints"]]
    assert "provenance_review" in checkpoint_ids
    assert "evaluation_gate_review" in checkpoint_ids


def test_dataset_governance_plan_route_keeps_publish_gate_blocked_when_quality_or_questions_remain(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-dataset-plan-blocked"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_dataset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Dataset governance looks runnable, but publish review is still blocked upstream.",
            "governance_status": "partial",
            "dataset_contract_status": "ready",
            "data_hygiene_status": "ready",
            "repo_mode_enabled": True,
            "tensorflow_enabled": True,
            "pytorch_enabled": False,
            "detected_frameworks": ["TensorFlow"],
            "detected_product_workflows": ["training_pipeline"],
            "dataset_artifact_count": 2,
            "dataset_artifact_paths": ["data/train.parquet", "metadata/dataset_manifest.json"],
            "dataset_artifact_extensions": [".parquet", ".json"],
            "schema_or_config_count": 1,
            "schema_or_config_paths": ["configs/dataset.yaml"],
            "checkpoint_artifact_count": 1,
            "checkpoint_artifact_paths": ["checkpoints/model.ckpt"],
            "provenance_signal_count": 1,
            "provenance_signals": ["metadata/dataset_manifest.json"],
            "split_signal_count": 1,
            "split_signals": ["data/train.parquet"],
            "evaluation_signal_count": 1,
            "evaluation_signals": ["reports/eval_metrics.json"],
            "pii_signal_count": 1,
            "pii_signals": ["metadata/pii_policy.json"],
            "duplication_signal_count": 1,
            "duplication_signals": ["reports/dedupe_report.json"],
            "corruption_signal_count": 1,
            "corruption_signals": ["reports/corruption_scan.json"],
            "label_coverage_signal_count": 1,
            "label_coverage_signals": ["metadata/label_map.json"],
            "validation_status": "ready",
            "runtime_status": "ready",
            "validation_step_count": 1,
            "validation_evidence_targets": ["reports/eval_metrics.json"],
            "recommended_execution_lane": "nvidia_dynamo",
            "supports_gpu_execution": True,
            "supports_bulk_file_governance": True,
            "quality_gate_blocker_count": 1,
            "pending_question_count": 1,
            "blocking_reasons": [],
            "recommended_fixes": [
                "Resolve required quality gates before treating the dataset lane as publish-ready.",
                "Resolve pending project questions before approving dataset publish.",
            ],
            "notes": ["Dataset contract and hygiene are ready, but publish review is still staged."],
            "file_governance": {
                "recommended_operation_mode": "hybrid_connector_sync",
                "supports_bulk_planning": True,
                "destructive_actions_require_approval": True,
            },
            "nvidia_governance": {
                "governance_status": "ready",
                "recommended_execution_lane": "nvidia_dynamo",
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Dataset Plan Blocker Demo",
            "idea": "Need blocked dataset publish gates reflected in the generated plan.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/dataset-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "partial"
    assert any("publish review staged" in note for note in payload["notes"])

    approval_checkpoints = json.loads((workspace / "artifacts" / "dataset-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    publish_gate = next(item for item in approval_checkpoints["checkpoints"] if item["checkpoint_id"] == "publish_gate")
    assert publish_gate["status"] == "blocked"


def test_model_refactor_governance_summary_route_surfaces_compatibility_benchmarks_and_rollback(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-model-refactor-governance"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_workspace_tooling_status",
        lambda project: {
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "PyTorch and TensorFlow model lanes detected.",
            "validation_commands": ["python -m pytest tests/api_contracts -q", "python eval.py --baseline metrics/baseline.json"],
            "observability_commands": ["python benchmarks/compare.py --baseline metrics/baseline.json"],
            "checkpoint_commands": ["python resume.py --checkpoint checkpoints/model.ckpt"],
            "execution_entrypoints": ["python serve.py", "python train.py --epochs 1"],
            "tensorflow_repo": {
                "enabled": True,
                "frameworks": ["SavedModel / Serving"],
                "important_paths": ["serving/api_contract.yaml", "metrics/baseline.json"],
                "existing_savedmodel_artifacts": ["exports/saved_model/saved_model.pb"],
                "existing_tflite_artifacts": [],
            },
            "tensorflow_validation_plan": {
                "available": True,
                "status": "ready",
                "repo_mode_enabled": True,
                "evidence_targets": ["serving compatibility report", "benchmark delta"],
            },
            "pytorch_repo": {
                "enabled": True,
                "frameworks": ["TorchScript"],
                "important_paths": ["schemas/model_signature.json", "benchmarks/refactor_metrics.json"],
                "existing_onnx_artifacts": ["artifacts/model.onnx"],
                "existing_torchscript_artifacts": ["artifacts/model.pt"],
                "checkpoint_paths": ["checkpoints/model.ckpt"],
            },
            "pytorch_runtime_status": {"available": True, "status": "ready"},
            "pytorch_validation_plan": {
                "available": True,
                "status": "ready",
                "repo_mode_enabled": True,
                "evidence_targets": ["accuracy scorecard", "rollback checkpoint audit"],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_project_artifact_registry",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "Model artifacts and contracts are present.",
            "artifact_count": 5,
            "artifact_paths": [
                "artifacts/model.onnx",
                "artifacts/model.pt",
                "checkpoints/model.ckpt",
                "exports/saved_model/saved_model.pb",
                "benchmarks/refactor_metrics.json",
            ],
            "artifact_extensions": [".onnx", ".pt", ".ckpt", ".pb", ".json"],
            "artifact_extension_count": 5,
            "artifact_kind_summaries": ["model:4", "benchmark:1"],
            "artifact_kind_counts": {"model": 4, "benchmark": 1},
            "artifact_kind_count": 2,
            "inspection_command_count": 0,
            "inspection_commands": [],
            "config_review_path_count": 2,
            "config_review_paths": ["serving/api_contract.yaml", "schemas/model_signature.json"],
            "config_review_command_count": 0,
            "config_review_commands": [],
            "validation_evidence_target_count": 3,
            "validation_evidence_targets": ["benchmark delta", "serving compatibility report", "accuracy scorecard"],
            "execution_entrypoint_count": 2,
            "execution_entrypoints": ["python serve.py", "python train.py --epochs 1"],
            "notebook_path_count": 0,
            "notebook_paths": [],
            "recommended_next_steps": [],
            "recommended_next_step_count": 0,
        },
    )
    monkeypatch.setattr(
        "manager.service.build_dataset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Dataset governance is ready.",
            "governance_status": "ready",
            "dataset_contract_status": "ready",
            "data_hygiene_status": "ready",
            "repo_mode_enabled": True,
            "tensorflow_enabled": True,
            "pytorch_enabled": True,
            "detected_frameworks": ["TensorFlow", "PyTorch"],
            "detected_product_workflows": ["training_pipeline", "evaluation_pipeline"],
            "dataset_artifact_count": 4,
            "dataset_artifact_paths": ["data/train.parquet"],
            "dataset_artifact_extensions": [".parquet"],
            "schema_or_config_count": 2,
            "schema_or_config_paths": ["serving/api_contract.yaml", "schemas/model_signature.json"],
            "checkpoint_artifact_count": 1,
            "checkpoint_artifact_paths": ["checkpoints/model.ckpt"],
            "provenance_signal_count": 1,
            "provenance_signals": ["metadata/dataset_manifest.json"],
            "split_signal_count": 1,
            "split_signals": ["data/train.parquet"],
            "evaluation_signal_count": 1,
            "evaluation_signals": ["accuracy scorecard"],
            "pii_signal_count": 1,
            "pii_signals": ["metadata/pii_policy.json"],
            "duplication_signal_count": 1,
            "duplication_signals": ["reports/dedupe_report.json"],
            "corruption_signal_count": 1,
            "corruption_signals": ["reports/corruption_scan.json"],
            "label_coverage_signal_count": 1,
            "label_coverage_signals": ["metadata/label_map.json"],
            "validation_status": "ready",
            "runtime_status": "ready",
            "validation_step_count": 2,
            "validation_evidence_targets": ["accuracy scorecard", "benchmark delta"],
            "recommended_execution_lane": "nvidia_dynamo",
            "supports_gpu_execution": True,
            "supports_bulk_file_governance": True,
            "quality_gate_blocker_count": 0,
            "pending_question_count": 0,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Dataset contract and hygiene are ready."],
            "file_governance": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "File governance ready.",
                "recommended_operation_mode": "hybrid_connector_sync",
                "supports_bulk_planning": True,
                "destructive_actions_require_approval": True,
                "storage_lane_count": 1,
                "connected_storage_lane_count": 1,
                "ready_scanner_lane_count": 1,
                "storage_provider_count": 1,
                "storage_providers": ["local_fs"],
                "ready_scanner_lanes": ["linux"],
                "blocking_reasons": [],
                "notes": [],
                "storage_lanes": [],
                "connector_registry": {"summary": "ready", "family_count": 1, "connection_count": 1, "ready_family_count": 1, "ready_families": ["storage"], "provider_counts": {"local_fs": 1}, "provider_count": 1, "category_counts": {"storage": 1}, "category_count": 1, "connection_source_counts": {"mission_control": 1}, "connection_source_count": 1, "available_action_count": 1},
                "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": "gpu-linux", "lane_count": 1, "ready_lane_count": 1, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": ["linux"], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
                "artifact_transport": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": "gpu-linux", "preflight_ready": True, "sync_enabled": True, "recommended_transport_mode": "brokered_sync", "blocking_reasons": [], "ready_platform_lanes": ["linux"], "partial_platform_lanes": [], "notes": [], "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "stub", "artifact_count": 1, "artifact_paths": ["data/train.parquet"]}, "connector_registry": {"summary": "ready"}, "artifact_contract": {"sync_enabled": True}, "connector_contract": {"available_families": ["storage"]}},
            },
            "nvidia_governance": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "ready", "governance_status": "ready", "recommended_execution_lane": "nvidia_dynamo", "cuda_repo_enabled": True, "validation_status": "ready", "local_runtime_status": "ready", "gpu_diagnostics_status": "ready", "aiq_status": "ready", "remote_gpu_target_count": 1, "ready_remote_gpu_target_count": 1, "selected_remote_target_id": "gpu-linux", "selected_remote_target_gpu": "RTX 4090", "provider_ready_ids": ["nvidia_dynamo"], "provider_partial_ids": [], "available_provider_count": 1, "sanitizer_ready": True, "profiler_ready": True, "container_smoke_ready": True, "blocking_reasons": [], "recommended_fixes": [], "notes": ["GPU lane ready."], "dynamo_status": {"project_id": project.id, "project_name": project.name, "endpoint": "http://dynamo.local:8000", "summary": "ready", "available": True, "reachable": True, "endpoint_configured": True, "api_key_configured": True, "auth_required": True, "authenticated": True, "runtime_ready": True, "runtime_status": "ready", "runtime_summary": "ready"}, "nim_status": {"project_id": project.id, "project_name": project.name, "endpoint": "https://integrate.api.nvidia.com", "summary": "optional", "available": False, "reachable": False}, "aiq": {"project_id": project.id, "project_name": project.name, "install_status": "ready", "summary": "ready", "endpoint": "http://aiq.local:8000", "available": True}, "gpu_diagnostics": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready"}, "local_runtime": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready"}, "validation_plan": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready", "repo_mode_enabled": True, "steps": [{"title": "Run GPU eval", "command": "python eval.py --baseline metrics/baseline.json", "type": "eval", "source": "repo_mode", "status": "pending"}]}, "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub"}, "device_broker": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "preflight_ready": True, "selected_target_id": "gpu-linux", "recommended_target_ids": ["gpu-linux"], "blocking_reasons": [], "ready_target_count": 1, "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "stub"}, "connector_registry": {"summary": "ready"}, "remote_execution": {"policy": {"enabled": True}, "required_runner_family": "external_adapter"}}},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_execution_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "NVIDIA governance is ready.",
            "governance_status": "ready",
            "recommended_execution_lane": "nvidia_dynamo",
            "cuda_repo_enabled": True,
            "validation_status": "ready",
            "local_runtime_status": "ready",
            "gpu_diagnostics_status": "ready",
            "aiq_status": "ready",
            "remote_gpu_target_count": 1,
            "ready_remote_gpu_target_count": 1,
            "selected_remote_target_id": "gpu-linux",
            "selected_remote_target_gpu": "RTX 4090",
            "provider_ready_ids": ["nvidia_dynamo"],
            "provider_partial_ids": [],
            "available_provider_count": 1,
            "sanitizer_ready": True,
            "profiler_ready": True,
            "container_smoke_ready": True,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["GPU execution is governed."],
            "dynamo_status": {"project_id": project.id, "project_name": project.name, "endpoint": "http://dynamo.local:8000", "summary": "ready", "available": True, "reachable": True, "endpoint_configured": True, "api_key_configured": True, "auth_required": True, "authenticated": True, "runtime_ready": True, "runtime_status": "ready", "runtime_summary": "ready"},
            "nim_status": {"project_id": project.id, "project_name": project.name, "endpoint": "https://integrate.api.nvidia.com", "summary": "optional", "available": False, "reachable": False},
            "aiq": {"project_id": project.id, "project_name": project.name, "install_status": "ready", "summary": "ready", "endpoint": "http://aiq.local:8000", "available": True},
            "gpu_diagnostics": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready"},
            "local_runtime": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready"},
            "validation_plan": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready", "repo_mode_enabled": True, "steps": [{"title": "Run GPU eval", "command": "python eval.py --baseline metrics/baseline.json", "type": "eval", "source": "repo_mode", "status": "pending"}]},
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub"},
            "device_broker": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "preflight_ready": True, "selected_target_id": "gpu-linux", "recommended_target_ids": ["gpu-linux"], "blocking_reasons": [], "ready_target_count": 1, "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "stub"}, "connector_registry": {"summary": "ready"}, "remote_execution": {"policy": {"enabled": True}, "required_runner_family": "external_adapter"}},
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Model Refactor Governance Demo",
            "idea": "Need governed model refactors.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/model-refactor-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["governance_status"] == "ready"
    assert payload["repo_mode_enabled"] is True
    assert payload["compatibility_contract_status"] == "ready"
    assert payload["benchmark_readiness_status"] == "ready"
    assert payload["rollback_readiness_status"] == "ready"
    assert payload["evaluation_first_ready"] is True
    assert payload["recommended_execution_lane"] == "nvidia_dynamo"
    assert payload["model_artifact_count"] >= 4
    assert ".onnx" in payload["model_artifact_extensions"]
    assert payload["compatibility_signal_count"] >= 1
    assert payload["benchmark_signal_count"] >= 1
    assert payload["rollback_signal_count"] >= 1
    assert payload["validation_signal_count"] >= 1
    assert "TensorFlow" in payload["detected_frameworks"]
    assert "PyTorch" in payload["detected_frameworks"]
    assert payload["blocking_reasons"] == []
    assert payload["dataset_governance"]["governance_status"] == "ready"
    assert payload["nvidia_governance"]["recommended_execution_lane"] == "nvidia_dynamo"


def test_model_refactor_governance_plan_route_generates_compatibility_benchmark_and_rollback_manifests(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-model-refactor-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_model_refactor_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Model refactor governance is ready.",
            "governance_status": "ready",
            "repo_mode_enabled": True,
            "detected_frameworks": ["TensorFlow", "PyTorch"],
            "compatibility_contract_status": "ready",
            "benchmark_readiness_status": "ready",
            "rollback_readiness_status": "ready",
            "evaluation_first_ready": True,
            "recommended_execution_lane": "nvidia_dynamo",
            "model_artifact_count": 4,
            "model_artifact_paths": [
                "artifacts/model.onnx",
                "artifacts/model.pt",
                "checkpoints/model.ckpt",
                "exports/saved_model/saved_model.pb",
            ],
            "model_artifact_extensions": [".onnx", ".pt", ".ckpt", ".pb"],
            "compatibility_signal_count": 2,
            "compatibility_signals": ["serving/api_contract.yaml", "schemas/model_signature.json"],
            "benchmark_signal_count": 2,
            "benchmark_signals": ["benchmarks/refactor_metrics.json", "benchmark delta"],
            "rollback_signal_count": 2,
            "rollback_signals": ["checkpoints/model.ckpt", "rollback checkpoint audit"],
            "validation_signal_count": 2,
            "validation_signals": ["python -m pytest tests/api_contracts -q", "accuracy scorecard"],
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Compatibility, benchmarks, and rollback are all ready."],
            "dataset_governance": {
                "governance_status": "ready",
                "validation_status": "ready",
                "checkpoint_artifact_paths": ["checkpoints/model.ckpt"],
            },
            "nvidia_governance": {
                "governance_status": "ready",
                "recommended_execution_lane": "nvidia_dynamo",
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Model Refactor Plan Demo",
            "idea": "Need governed model refactor manifests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/model-refactor-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["detected_frameworks"] == ["TensorFlow", "PyTorch"]
    assert payload["manifest_root"] == "artifacts/model-refactor-governance"
    assert payload["compatibility_contract_path"] == "artifacts/model-refactor-governance/compatibility-contract.json"
    assert payload["benchmark_comparison_path"] == "artifacts/model-refactor-governance/benchmark-comparison.json"
    assert payload["rollback_bundle_path"] == "artifacts/model-refactor-governance/rollback-bundle.json"
    assert payload["validation_plan_path"] == "artifacts/model-refactor-governance/validation-plan.json"
    assert payload["evaluation_gate_path"] == "artifacts/model-refactor-governance/evaluation-gates.json"
    assert payload["approval_checkpoint_path"] == "artifacts/model-refactor-governance/approval-checkpoints.json"

    assert (workspace / "artifacts" / "model-refactor-governance" / "compatibility-contract.json").exists()
    assert (workspace / "artifacts" / "model-refactor-governance" / "benchmark-comparison.json").exists()
    assert (workspace / "artifacts" / "model-refactor-governance" / "rollback-bundle.json").exists()
    assert (workspace / "artifacts" / "model-refactor-governance" / "validation-plan.json").exists()
    assert (workspace / "artifacts" / "model-refactor-governance" / "evaluation-gates.json").exists()
    assert (workspace / "artifacts" / "model-refactor-governance" / "approval-checkpoints.json").exists()

    compatibility_contract = json.loads((workspace / "artifacts" / "model-refactor-governance" / "compatibility-contract.json").read_text(encoding="utf-8"))
    assert compatibility_contract["contract_requirements"]["api_signature_required"] is True
    assert compatibility_contract["contract_requirements"]["serving_interface_required"] is True
    assert "schemas/model_signature.json" in compatibility_contract["compatibility_signals"]

    benchmark_comparison = json.loads((workspace / "artifacts" / "model-refactor-governance" / "benchmark-comparison.json").read_text(encoding="utf-8"))
    assert benchmark_comparison["baseline_compare_required"] is True
    assert benchmark_comparison["quality_thresholds"]["latency_regression_review_required"] is True
    assert "benchmarks/refactor_metrics.json" in benchmark_comparison["benchmark_signals"]

    rollback_bundle = json.loads((workspace / "artifacts" / "model-refactor-governance" / "rollback-bundle.json").read_text(encoding="utf-8"))
    assert rollback_bundle["rollback_requirements"]["checkpoint_required"] is True
    assert rollback_bundle["rollback_requirements"]["restore_drill_required"] is True
    assert "checkpoints/model.ckpt" in rollback_bundle["checkpoint_artifact_paths"]

    validation_plan = json.loads((workspace / "artifacts" / "model-refactor-governance" / "validation-plan.json").read_text(encoding="utf-8"))
    assert validation_plan["gpu_lane_required"] is True
    assert "accuracy scorecard" in validation_plan["validation_signals"]

    evaluation_gates = json.loads((workspace / "artifacts" / "model-refactor-governance" / "evaluation-gates.json").read_text(encoding="utf-8"))
    gate_ids = [item["gate_id"] for item in evaluation_gates["gates"]]
    assert "dataset_validation_alignment" in gate_ids

    approval_checkpoints = json.loads((workspace / "artifacts" / "model-refactor-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    checkpoint_ids = [item["checkpoint_id"] for item in approval_checkpoints["checkpoints"]]
    assert "rollback_rehearsal_gate" in checkpoint_ids


def test_model_refactor_governance_summary_route_blocks_when_dataset_governance_is_still_partial(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-model-refactor-governance-blocked"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_workspace_tooling_status",
        lambda project: {
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "Model lanes detected.",
            "validation_commands": ["python -m pytest tests/api_contracts -q", "python eval.py --baseline metrics/baseline.json"],
            "observability_commands": ["python benchmarks/compare.py --baseline metrics/baseline.json"],
            "checkpoint_commands": ["python resume.py --checkpoint checkpoints/model.ckpt"],
            "execution_entrypoints": ["python serve.py"],
            "tensorflow_repo": {
                "enabled": True,
                "frameworks": ["SavedModel / Serving"],
                "important_paths": ["serving/api_contract.yaml", "metrics/baseline.json"],
                "existing_savedmodel_artifacts": ["exports/saved_model/saved_model.pb"],
                "existing_tflite_artifacts": [],
            },
            "tensorflow_validation_plan": {
                "available": True,
                "status": "ready",
                "repo_mode_enabled": True,
                "evidence_targets": ["serving compatibility report", "benchmark delta"],
            },
            "pytorch_repo": {
                "enabled": False,
                "frameworks": [],
                "important_paths": ["schemas/model_signature.json", "benchmarks/refactor_metrics.json"],
                "existing_onnx_artifacts": ["artifacts/model.onnx"],
                "existing_torchscript_artifacts": [],
                "checkpoint_paths": ["checkpoints/model.ckpt"],
            },
            "pytorch_runtime_status": {"available": True, "status": "ready"},
            "pytorch_validation_plan": {
                "available": False,
                "status": "not_applicable",
                "repo_mode_enabled": False,
                "evidence_targets": [],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_project_artifact_registry",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "Model artifacts and contracts are present.",
            "artifact_count": 4,
            "artifact_paths": [
                "artifacts/model.onnx",
                "checkpoints/model.ckpt",
                "exports/saved_model/saved_model.pb",
                "benchmarks/refactor_metrics.json",
            ],
            "artifact_extensions": [".onnx", ".ckpt", ".pb", ".json"],
            "artifact_extension_count": 4,
            "artifact_kind_summaries": ["model:3", "benchmark:1"],
            "artifact_kind_counts": {"model": 3, "benchmark": 1},
            "artifact_kind_count": 2,
            "inspection_command_count": 0,
            "inspection_commands": [],
            "config_review_path_count": 2,
            "config_review_paths": ["serving/api_contract.yaml", "schemas/model_signature.json"],
            "config_review_command_count": 0,
            "config_review_commands": [],
            "validation_evidence_target_count": 2,
            "validation_evidence_targets": ["benchmark delta", "serving compatibility report"],
            "execution_entrypoint_count": 1,
            "execution_entrypoints": ["python serve.py"],
            "notebook_path_count": 0,
            "notebook_paths": [],
            "recommended_next_steps": [],
            "recommended_next_step_count": 0,
        },
    )
    monkeypatch.setattr(
        "manager.service.build_dataset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Dataset validation is green, but governance is still staged.",
            "governance_status": "partial",
            "dataset_contract_status": "ready",
            "data_hygiene_status": "ready",
            "repo_mode_enabled": True,
            "tensorflow_enabled": True,
            "pytorch_enabled": False,
            "detected_frameworks": ["TensorFlow"],
            "detected_product_workflows": ["training_pipeline"],
            "dataset_artifact_count": 2,
            "dataset_artifact_paths": ["data/train.parquet"],
            "dataset_artifact_extensions": [".parquet"],
            "schema_or_config_count": 1,
            "schema_or_config_paths": ["configs/dataset.yaml"],
            "checkpoint_artifact_count": 1,
            "checkpoint_artifact_paths": ["checkpoints/model.ckpt"],
            "provenance_signal_count": 1,
            "provenance_signals": ["metadata/dataset_manifest.json"],
            "split_signal_count": 1,
            "split_signals": ["data/train.parquet"],
            "evaluation_signal_count": 1,
            "evaluation_signals": ["accuracy scorecard"],
            "pii_signal_count": 1,
            "pii_signals": ["metadata/pii_policy.json"],
            "duplication_signal_count": 1,
            "duplication_signals": ["reports/dedupe_report.json"],
            "corruption_signal_count": 1,
            "corruption_signals": ["reports/corruption_scan.json"],
            "label_coverage_signal_count": 1,
            "label_coverage_signals": ["metadata/label_map.json"],
            "validation_status": "ready",
            "runtime_status": "ready",
            "validation_step_count": 1,
            "validation_evidence_targets": ["accuracy scorecard"],
            "recommended_execution_lane": "nvidia_dynamo",
            "supports_gpu_execution": True,
            "supports_bulk_file_governance": True,
            "quality_gate_blocker_count": 1,
            "pending_question_count": 1,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Dataset validation is green, but publish review is still staged."],
            "file_governance": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "File governance ready.",
                "recommended_operation_mode": "hybrid_connector_sync",
                "supports_bulk_planning": True,
                "destructive_actions_require_approval": True,
                "storage_lane_count": 1,
                "connected_storage_lane_count": 1,
                "ready_scanner_lane_count": 1,
                "storage_provider_count": 1,
                "storage_providers": ["local_fs"],
                "ready_scanner_lanes": ["linux"],
                "blocking_reasons": [],
                "notes": [],
                "storage_lanes": [],
                "connector_registry": {
                    "summary": "ready",
                    "family_count": 1,
                    "connection_count": 1,
                    "ready_family_count": 1,
                    "ready_families": ["storage"],
                    "provider_counts": {"local_fs": 1},
                    "provider_count": 1,
                    "category_counts": {"storage": 1},
                    "category_count": 1,
                    "connection_source_counts": {"mission_control": 1},
                    "connection_source_count": 1,
                    "available_action_count": 1,
                    "catalog": [],
                    "connections": [],
                    "status_counts": {},
                    "host_import_roots": {},
                    "recent_action_failures": [],
                },
                "platform_runners": {
                    "project_id": project.id,
                    "project_name": project.name,
                    "workspace_path": project.workspace_path,
                    "summary": "stub",
                    "selected_target_id": "gpu-linux",
                    "lane_count": 1,
                    "ready_lane_count": 1,
                    "partial_lane_count": 0,
                    "unavailable_lane_count": 0,
                    "ready_lane_ids": ["linux"],
                    "partial_lane_ids": [],
                    "unavailable_lane_ids": [],
                    "lanes": [],
                },
                "artifact_transport": {
                    "project_id": project.id,
                    "project_name": project.name,
                    "workspace_path": project.workspace_path,
                    "summary": "stub",
                    "selected_target_id": "gpu-linux",
                    "selected_target_probe_status": "ready",
                    "ready_candidate_count": 1,
                    "ready_candidate_ids": ["gpu-linux"],
                    "preflight_ready": True,
                    "sync_enabled": True,
                    "recommended_transport_mode": "brokered_sync",
                    "blocking_reasons": [],
                    "ready_platform_lanes": ["linux"],
                    "partial_platform_lanes": [],
                    "notes": [],
                    "artifact_registry": {
                        "project_id": project.id,
                        "project_name": project.name,
                        "workspace_path": project.workspace_path,
                        "available": True,
                        "summary": "stub",
                        "artifact_count": 1,
                        "artifact_paths": ["data/train.parquet"],
                        "artifact_extensions": [".parquet"],
                        "artifact_extension_count": 1,
                        "artifact_kind_summaries": ["dataset:1"],
                        "artifact_kind_counts": {"dataset": 1},
                        "artifact_kind_count": 1,
                        "inspection_command_count": 0,
                        "inspection_commands": [],
                        "config_review_path_count": 0,
                        "config_review_paths": [],
                        "config_review_command_count": 0,
                        "config_review_commands": [],
                        "validation_evidence_target_count": 0,
                        "validation_evidence_targets": [],
                        "execution_entrypoint_count": 0,
                        "execution_entrypoints": [],
                        "notebook_path_count": 0,
                        "notebook_paths": [],
                    },
                    "connector_registry": {
                        "summary": "ready",
                        "family_count": 1,
                        "connection_count": 1,
                        "ready_family_count": 1,
                        "ready_families": ["storage"],
                        "provider_counts": {"local_fs": 1},
                        "provider_count": 1,
                        "category_counts": {"storage": 1},
                        "category_count": 1,
                        "connection_source_counts": {"mission_control": 1},
                        "connection_source_count": 1,
                        "available_action_count": 1,
                        "catalog": [],
                        "connections": [],
                        "status_counts": {},
                        "host_import_roots": {},
                        "recent_action_failures": [],
                    },
                    "artifact_contract": {"sync_enabled": True},
                    "connector_contract": {"available_families": ["storage"]},
                },
            },
            "nvidia_governance": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "ready",
                "governance_status": "ready",
                "recommended_execution_lane": "nvidia_dynamo",
                "cuda_repo_enabled": True,
                "validation_status": "ready",
                "local_runtime_status": "ready",
                "gpu_diagnostics_status": "ready",
                "aiq_status": "ready",
                "remote_gpu_target_count": 1,
                "ready_remote_gpu_target_count": 1,
                "selected_remote_target_id": "gpu-linux",
                "selected_remote_target_gpu": "RTX 4090",
                "provider_ready_ids": ["nvidia_dynamo"],
                "provider_partial_ids": [],
                "available_provider_count": 1,
                "sanitizer_ready": True,
                "profiler_ready": True,
                "container_smoke_ready": True,
                "blocking_reasons": [],
                "recommended_fixes": [],
                "notes": ["GPU lane ready."],
                "dynamo_status": {"project_id": project.id, "project_name": project.name, "endpoint": "http://dynamo.local:8000", "summary": "ready", "available": True, "reachable": True, "endpoint_configured": True, "api_key_configured": True, "auth_required": True, "authenticated": True, "runtime_ready": True, "runtime_status": "ready", "runtime_summary": "ready"},
                "nim_status": {"project_id": project.id, "project_name": project.name, "endpoint": "https://integrate.api.nvidia.com", "summary": "optional", "available": False, "reachable": False},
                "aiq": {"project_id": project.id, "project_name": project.name, "install_status": "ready", "summary": "ready", "endpoint": "http://aiq.local:8000", "available": True},
                "gpu_diagnostics": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready"},
                "local_runtime": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready"},
                "validation_plan": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready", "repo_mode_enabled": True, "steps": [{"title": "Run GPU eval", "command": "python eval.py --baseline metrics/baseline.json", "type": "eval", "source": "repo_mode", "status": "pending"}]},
                "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub"},
                "device_broker": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "preflight_ready": True, "selected_target_id": "gpu-linux", "recommended_target_ids": ["gpu-linux"], "blocking_reasons": [], "ready_target_count": 1, "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "stub"}, "connector_registry": {"summary": "ready"}, "remote_execution": {"policy": {"enabled": True}, "required_runner_family": "external_adapter"}},
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_nvidia_execution_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "NVIDIA governance is ready.",
            "governance_status": "ready",
            "recommended_execution_lane": "nvidia_dynamo",
            "cuda_repo_enabled": True,
            "validation_status": "ready",
            "local_runtime_status": "ready",
            "gpu_diagnostics_status": "ready",
            "aiq_status": "ready",
            "remote_gpu_target_count": 1,
            "ready_remote_gpu_target_count": 1,
            "selected_remote_target_id": "gpu-linux",
            "selected_remote_target_gpu": "RTX 4090",
            "provider_ready_ids": ["nvidia_dynamo"],
            "provider_partial_ids": [],
            "available_provider_count": 1,
            "sanitizer_ready": True,
            "profiler_ready": True,
            "container_smoke_ready": True,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["GPU lane ready."],
            "dynamo_status": {"project_id": project.id, "project_name": project.name, "endpoint": "http://dynamo.local:8000", "summary": "ready", "available": True, "reachable": True, "endpoint_configured": True, "api_key_configured": True, "auth_required": True, "authenticated": True, "runtime_ready": True, "runtime_status": "ready", "runtime_summary": "ready"},
            "nim_status": {"project_id": project.id, "project_name": project.name, "endpoint": "https://integrate.api.nvidia.com", "summary": "optional", "available": False, "reachable": False},
            "aiq": {"project_id": project.id, "project_name": project.name, "install_status": "ready", "summary": "ready", "endpoint": "http://aiq.local:8000", "available": True},
            "gpu_diagnostics": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready"},
            "local_runtime": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready"},
            "validation_plan": {"project_id": project.id, "project_name": project.name, "available": True, "status": "ready", "summary": "ready", "repo_mode_enabled": True, "steps": [{"title": "Run GPU eval", "command": "python eval.py --baseline metrics/baseline.json", "type": "eval", "source": "repo_mode", "status": "pending"}]},
            "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub"},
            "device_broker": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "preflight_ready": True, "selected_target_id": "gpu-linux", "recommended_target_ids": ["gpu-linux"], "blocking_reasons": [], "ready_target_count": 1, "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "stub"}, "connector_registry": {"summary": "ready"}, "remote_execution": {"policy": {"enabled": True}, "required_runner_family": "external_adapter"}},
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Model Refactor Governance Blocker Demo",
            "idea": "Need model refactor readiness to respect upstream dataset governance blockers.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/model-refactor-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "partial"
    assert payload["evaluation_first_ready"] is False
    assert "1 dataset quality gate blocker(s) still prevent evaluation-first refactor review." in payload["blocking_reasons"]
    assert "1 pending dataset governance question(s) still keep refactor publish review staged." in payload["blocking_reasons"]
    assert "Resolve required dataset quality gates before treating model refactors as evaluation-first ready." in payload["recommended_fixes"]
    assert "Resolve pending dataset-governance questions before approving model refactor publish review." in payload["recommended_fixes"]


def test_model_refactor_governance_plan_route_keeps_publish_gate_blocked_when_dataset_governance_is_partial(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-model-refactor-plan-blocked"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_model_refactor_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Model refactor governance is staged behind dataset blockers.",
            "governance_status": "partial",
            "repo_mode_enabled": True,
            "detected_frameworks": ["TensorFlow"],
            "compatibility_contract_status": "ready",
            "benchmark_readiness_status": "ready",
            "rollback_readiness_status": "ready",
            "evaluation_first_ready": False,
            "recommended_execution_lane": "nvidia_dynamo",
            "model_artifact_count": 3,
            "model_artifact_paths": [
                "artifacts/model.onnx",
                "checkpoints/model.ckpt",
                "exports/saved_model/saved_model.pb",
            ],
            "model_artifact_extensions": [".onnx", ".ckpt", ".pb"],
            "compatibility_signal_count": 2,
            "compatibility_signals": ["serving/api_contract.yaml", "schemas/model_signature.json"],
            "benchmark_signal_count": 1,
            "benchmark_signals": ["benchmarks/refactor_metrics.json"],
            "rollback_signal_count": 1,
            "rollback_signals": ["checkpoints/model.ckpt"],
            "validation_signal_count": 1,
            "validation_signals": ["accuracy scorecard"],
            "blocking_reasons": [
                "1 dataset quality gate blocker(s) still prevent evaluation-first refactor review.",
                "1 pending dataset governance question(s) still keep refactor publish review staged.",
            ],
            "recommended_fixes": [],
            "notes": ["Refactor readiness is staged behind upstream dataset governance."],
            "dataset_governance": {
                "governance_status": "partial",
                "validation_status": "ready",
                "quality_gate_blocker_count": 1,
                "pending_question_count": 1,
                "checkpoint_artifact_paths": ["checkpoints/model.ckpt"],
            },
            "nvidia_governance": {
                "governance_status": "ready",
                "recommended_execution_lane": "nvidia_dynamo",
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Model Refactor Plan Blocker Demo",
            "idea": "Need blocked model-refactor publish gates reflected in the generated plan.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/model-refactor-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "partial"

    approval_checkpoints = json.loads((workspace / "artifacts" / "model-refactor-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    publish_gate = next(item for item in approval_checkpoints["checkpoints"] if item["checkpoint_id"] == "publish_gate")
    assert publish_gate["status"] == "blocked"


def test_native_app_validation_governance_summary_route_surfaces_platform_lanes_artifacts_and_evidence(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-native-app-governance"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_project_artifact_registry",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "Native app artifacts and evidence are present.",
            "artifact_count": 8,
            "artifact_paths": [
                "builds/android/app-release.apk",
                "builds/ios/TestFlight.ipa",
                "builds/web/index.html",
                "artifacts/logs/device.log",
                "artifacts/screenshots/home.png",
                "artifacts/traces/playwright-trace.zip",
                "artifacts/crash/app.crash",
                "artifacts/coverage/lcov.info",
            ],
            "artifact_extensions": [".apk", ".ipa", ".html", ".log", ".png", ".zip", ".crash", ".info"],
            "artifact_extension_count": 8,
            "artifact_kind_summaries": ["installable:3", "evidence:5"],
            "artifact_kind_counts": {"installable": 3, "evidence": 5},
            "artifact_kind_count": 2,
            "inspection_command_count": 0,
            "inspection_commands": [],
            "config_review_path_count": 0,
            "config_review_paths": [],
            "config_review_command_count": 0,
            "config_review_commands": [],
            "validation_evidence_target_count": 5,
            "validation_evidence_targets": [
                "artifacts/logs/device.log",
                "artifacts/screenshots/home.png",
                "artifacts/traces/playwright-trace.zip",
                "artifacts/crash/app.crash",
                "artifacts/coverage/lcov.info",
            ],
            "execution_entrypoint_count": 2,
            "execution_entrypoints": ["./gradlew connectedCheck", "xcodebuild test"],
            "notebook_path_count": 0,
            "notebook_paths": [],
            "recommended_next_steps": [],
            "recommended_next_step_count": 0,
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Mobile and browser lanes are mostly ready.",
            "selected_target_id": None,
            "selected_target_probe_status": "unknown",
            "availability_diagnostics": {"candidate_count": 0, "ready_candidate_count": 0},
            "selected_target_requirement_gaps": {},
            "selected_target_rejected_reasons": [],
            "lane_count": 6,
            "ready_lane_count": 3,
            "partial_lane_count": 2,
            "unavailable_lane_count": 1,
            "ready_lane_ids": ["android", "ios", "browser"],
            "partial_lane_ids": ["macos", "windows"],
            "unavailable_lane_ids": ["linux"],
            "lanes": [
                {"lane_id": "android", "title": "Android Runner", "status": "ready", "summary": "ready", "target_ids": ["android-lab"], "target_count": 1, "selected_target_ids": ["android-lab"], "os_families": ["linux"], "toolchains": ["adb", "gradle", "emulator"], "command_families": ["adb", "gradle"], "recommended_commands": ["./gradlew connectedCheck"], "adapter_contract": {"contract_id": "android_adb_contract", "adapter_family": "android_adb", "status": "ready", "selected_binding_status": "ready", "required_tool_families": ["adb", "gradle", "emulator"], "expected_evidence_categories": ["logs", "screenshots", "traces", "crashes", "coverage", "performance"]}, "notes": []},
                {"lane_id": "ios", "title": "iOS Runner", "status": "ready", "summary": "ready", "target_ids": ["mac-ios"], "target_count": 1, "selected_target_ids": ["mac-ios"], "os_families": ["macos"], "toolchains": ["xcode15", "simctl"], "command_families": ["xcodebuild", "simctl"], "recommended_commands": ["xcodebuild test"], "adapter_contract": {"contract_id": "ios_xcodebuild_contract", "adapter_family": "ios_xcodebuild", "status": "ready", "selected_binding_status": "ready", "required_tool_families": ["xcodebuild", "simctl"], "expected_evidence_categories": ["logs", "screenshots", "traces", "crashes", "coverage", "performance"]}, "notes": []},
                {"lane_id": "browser", "title": "Browser Runner", "status": "ready", "summary": "ready", "target_ids": ["browser-lab"], "target_count": 1, "selected_target_ids": ["browser-lab"], "os_families": ["linux"], "toolchains": ["playwright"], "command_families": ["browser"], "recommended_commands": ["playwright test"], "adapter_contract": {"contract_id": "browser_automation_contract", "adapter_family": "browser_automation", "status": "ready", "selected_binding_status": "not_required", "required_tool_families": ["browser_automation", "playwright"], "expected_evidence_categories": ["logs", "screenshots", "traces", "coverage", "performance"]}, "notes": []},
                {"lane_id": "macos", "title": "macOS Runner", "status": "partial", "summary": "partial", "target_ids": ["mac-ios"], "target_count": 1, "selected_target_ids": [], "os_families": ["macos"], "toolchains": ["xcode15"], "command_families": ["xcodebuild"], "recommended_commands": ["xcodebuild test"], "adapter_contract": {"contract_id": "macos_xcode_installer_contract", "adapter_family": "macos_xcode_installer", "status": "partial", "selected_binding_status": "visible_but_not_ready", "required_tool_families": ["xcodebuild", "desktop_installer"], "expected_evidence_categories": ["logs", "screenshots", "traces", "crashes", "coverage", "performance"]}, "notes": []},
                {"lane_id": "windows", "title": "Windows Runner", "status": "partial", "summary": "partial", "target_ids": ["win-lab"], "target_count": 1, "selected_target_ids": [], "os_families": ["windows"], "toolchains": ["powershell"], "command_families": ["powershell"], "recommended_commands": ["powershell -File .\\scripts\\validate.ps1"], "adapter_contract": {"contract_id": "windows_installer_contract", "adapter_family": "windows_installer", "status": "partial", "selected_binding_status": "visible_but_not_ready", "required_tool_families": ["desktop_installer", "powershell"], "expected_evidence_categories": ["logs", "screenshots", "traces", "crashes", "coverage", "performance"]}, "notes": []},
                {"lane_id": "linux", "title": "Linux Runner", "status": "unavailable", "summary": "unavailable", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": [], "command_families": [], "recommended_commands": ["python -m pytest"], "adapter_contract": {"contract_id": "linux_host_runtime_contract", "adapter_family": "linux_host_runtime", "status": "unavailable", "selected_binding_status": "missing", "required_tool_families": ["desktop_installer", "shell"], "expected_evidence_categories": ["logs", "screenshots", "traces", "crashes", "coverage", "performance"]}, "notes": []},
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Artifact transport is ready.",
            "selected_target_id": None,
            "preflight_ready": True,
            "sync_enabled": True,
            "recommended_transport_mode": "remote_artifact_root",
            "blocking_reasons": [],
            "ready_platform_lanes": ["android", "ios", "browser"],
            "partial_platform_lanes": ["macos", "windows"],
            "notes": ["Artifacts can be shipped to the selected target roots."],
            "artifact_registry": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "available": True,
                "summary": "artifacts",
                "artifact_count": 3,
                "artifact_paths": ["builds/android/app-release.apk", "builds/ios/TestFlight.ipa", "builds/web/index.html"],
            },
            "connector_registry": {"summary": "ready"},
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "local_artifact_paths": ["builds/android/app-release.apk", "builds/ios/TestFlight.ipa", "builds/web/index.html"],
                "local_artifact_path_count": 3,
                "target_artifact_roots": ["/srv/artifacts", "/Users/runner/artifacts"],
                "selected_artifact_root": "/Users/runner/artifacts",
                "preflight_ready": True,
            },
            "connector_contract": {
                "available_families": ["source_control"],
                "available_connector_count": 1,
                "preflight_ready": True,
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution",
        lambda db, project: {
            "selected_target_id": None,
            "selected_target": {
                "id": "mac-lab",
                "label": "Mac Lab",
                "transport": "ssh",
                "host": "mac-lab.local",
                "workspace_root": "/Users/runner/work",
            },
            "policy": {"enabled": True, "require_session_recording": True},
            "artifact_contract": {
                "selected_artifact_root": "/Users/runner/artifacts",
                "remote_workspace_root": "/Users/runner/work",
            },
            "broker_contract": {"require_session_recording": True, "session_recording_enabled": True},
            "result_contract": {
                "session_recording_artifact_paths": [
                    "artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
                ],
                "remote_session_recording_artifact_paths": [
                    "/Users/runner/artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
                ],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native App Governance Demo",
            "idea": "Need governed multi-platform app validation.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/native-app-validation-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["governance_status"] == "ready"
    assert payload["selected_target_id"] is None
    assert payload["selected_target_probe_status"] == "unknown"
    assert payload["availability_diagnostics"]["candidate_count"] == 0
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["evidence_pipeline_status"] == "ready"
    assert payload["recommended_transport_mode"] == "remote_artifact_root"
    assert payload["installable_artifact_count"] == 3
    assert ".apk" in payload["installable_artifact_extensions"]
    assert ".ipa" in payload["installable_artifact_extensions"]
    assert "android" in payload["detected_platforms"]
    assert "ios" in payload["detected_platforms"]
    assert "browser" in payload["detected_platforms"]
    assert payload["log_artifact_count"] >= 1
    assert payload["screenshot_artifact_count"] >= 1
    assert payload["trace_artifact_count"] >= 1
    assert payload["crash_artifact_count"] >= 1
    assert payload["coverage_artifact_count"] >= 1
    assert payload["session_recording_status"] == "ready"
    assert payload["session_recording_required"] is True
    assert payload["adapter_contract_status"] == "ready"
    assert payload["adapter_contract_count"] == 5
    assert payload["ready_adapter_contract_ids"] == [
        "android_adb_contract",
        "ios_xcodebuild_contract",
        "browser_automation_contract",
    ]
    assert payload["required_tool_adapter_family_count"] >= 4
    assert "playwright" in payload["required_tool_adapter_families"]
    assert "traces" in payload["required_adapter_evidence_categories"]
    assert payload["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
    ]
    assert payload["produced_session_recording_artifact_count"] == 0
    assert payload["produced_session_recording_artifact_paths"] == []
    assert payload["missing_session_recording_artifact_count"] == 0
    assert payload["missing_session_recording_artifact_paths"] == []
    assert payload["remote_session_recording_artifact_paths"] == [
        "/Users/runner/artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
    ]
    assert "android" in payload["recommended_runner_lanes"]
    assert "ios" in payload["recommended_runner_lanes"]
    assert "browser" in payload["recommended_runner_lanes"]
    assert payload["blocking_reasons"] == []
    assert payload["game_engine_normalized_results_summary_path"] is None
    assert payload["game_engine_normalized_summary_count"] == 0
    assert payload["game_engine_normalized_publish_ready"] is False
    assert payload["game_engine_scene_or_map_count"] == 0
    assert payload["game_engine_scene_or_map_paths"] == []
    assert payload["game_engine_automation_signal_count"] == 0
    assert payload["game_engine_automation_signal_paths"] == []
    assert payload["game_engine_screenshot_artifact_count"] == 0
    assert payload["game_engine_screenshot_artifact_paths"] == []
    assert payload["game_engine_normalized_results_status"] == "not_applicable"
    assert payload["game_engine_publish_gate_status"] == "not_applicable"
    assert payload["game_engine_publish_blocker_count"] == 0
    assert payload["game_engine_publish_blockers"] == []
    assert payload["platform_runners"]["ready_lane_ids"] == ["android", "ios", "browser"]
    assert payload["adapter_contracts"][0]["contract_id"] == "android_adb_contract"


def test_native_app_validation_governance_summary_route_includes_game_engine_surfaces_without_installables(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-native-engine-governance"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_project_artifact_registry",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "Engine evidence is present.",
            "artifact_count": 5,
            "artifact_paths": [
                "artifacts/logs/unity.log",
                "artifacts/screenshots/frame_0001.png",
                "artifacts/traces/unity-trace.zip",
                "artifacts/coverage/editmode-results.xml",
                "artifacts/perf/fps-benchmark.json",
            ],
            "artifact_extensions": [".log", ".png", ".zip", ".xml", ".json"],
            "artifact_extension_count": 5,
            "artifact_kind_summaries": ["evidence:5"],
            "artifact_kind_counts": {"evidence": 5},
            "artifact_kind_count": 1,
            "inspection_command_count": 0,
            "inspection_commands": [],
            "config_review_path_count": 0,
            "config_review_paths": [],
            "config_review_command_count": 0,
            "config_review_commands": [],
            "validation_evidence_target_count": 5,
            "validation_evidence_targets": [
                "artifacts/logs/unity.log",
                "artifacts/screenshots/frame_0001.png",
                "artifacts/traces/unity-trace.zip",
                "artifacts/coverage/editmode-results.xml",
                "artifacts/perf/fps-benchmark.json",
            ],
            "execution_entrypoint_count": 1,
            "execution_entrypoints": ["Unity -batchmode -runTests"],
            "notebook_path_count": 0,
            "notebook_paths": [],
            "recommended_next_steps": [],
            "recommended_next_step_count": 0,
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Unity lane is ready.",
            "selected_target_id": "win-unity",
            "lane_count": 1,
            "ready_lane_count": 1,
            "partial_lane_count": 0,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["unity"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": [],
            "lanes": [
                {"lane_id": "unity", "title": "Unity Runner", "status": "ready", "summary": "ready", "target_ids": ["win-unity"], "target_count": 1, "selected_target_ids": ["win-unity"], "os_families": ["windows"], "toolchains": ["unity6000"], "command_families": ["unity_batchmode"], "recommended_commands": ["Unity -batchmode -runTests"], "notes": []},
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Engine artifact transport is ready.",
            "selected_target_id": "win-unity",
            "preflight_ready": True,
            "sync_enabled": True,
            "recommended_transport_mode": "remote_artifact_root",
            "blocking_reasons": [],
            "ready_platform_lanes": ["unity"],
            "partial_platform_lanes": [],
            "notes": ["Engine evidence can be shipped to the selected target."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "evidence"},
            "connector_registry": {"summary": "ready"},
            "artifact_contract": {"sync_enabled": True, "required": True, "preflight_ready": True},
            "connector_contract": {"available_families": ["source_control"], "preflight_ready": True},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_game_engine_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Unity governance is ready.",
            "governance_status": "ready",
            "detected_engines": ["unity"],
            "unity_detected": True,
            "unreal_detected": False,
            "detected_project_paths": ["ProjectSettings/ProjectVersion.txt"],
            "scene_or_map_count": 1,
            "scene_or_map_paths": ["Assets/Scenes/MainMenu.unity"],
            "automation_signal_count": 1,
            "automation_signal_paths": ["Tests/SmokeTests.cs"],
            "screenshot_artifact_count": 1,
            "screenshot_artifact_paths": ["artifacts/screenshots/frame_0001.png"],
            "playable_contract_status": "ready",
            "visual_regression_ready": True,
            "unity_lane_status": "ready",
            "unreal_lane_status": "unavailable",
            "browser_lane_status": "partial",
            "recommended_runner_lane": "unity",
            "quality_gate_blocker_count": 0,
            "pending_question_count": 0,
            "normalized_results_summary_path": "artifacts/game-engine-governance/normalized-results-summary.json",
            "normalized_summary_count": 1,
            "normalized_passed_count": 0,
            "normalized_failed_count": 0,
            "normalized_missing_count": 1,
            "normalized_publish_ready": False,
            "normalized_results_status": "partial",
            "publish_gate_status": "blocked",
            "publish_blocker_count": 1,
            "publish_blockers": [
                "Normalized Unity/Unreal result rollups still contain missing, failed, or parse-error evidence."
            ],
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Unity pipeline already exposes golden-path evidence."],
            "platform_runners": {"summary": "Unity lane ready."},
            "design_transfer": {"summary": "stub"},
            "spatial_governance": {"summary": "stub"},
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native Engine Governance Demo",
            "idea": "Need native validation to understand Unity surfaces.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/native-app-validation-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "partial"
    assert payload["detected_platforms"] == []
    assert payload["governed_surface_count"] == 1
    assert payload["game_engine_surface_count"] == 1
    assert payload["game_engine_surface_ids"] == ["unity"]
    assert payload["game_engine_governance_status"] == "ready"
    assert payload["game_engine_playable_contract_status"] == "ready"
    assert payload["game_engine_scene_or_map_count"] == 1
    assert payload["game_engine_scene_or_map_paths"] == ["Assets/Scenes/MainMenu.unity"]
    assert payload["game_engine_automation_signal_count"] == 1
    assert payload["game_engine_automation_signal_paths"] == ["Tests/SmokeTests.cs"]
    assert payload["game_engine_screenshot_artifact_count"] == 1
    assert payload["game_engine_screenshot_artifact_paths"] == ["artifacts/screenshots/frame_0001.png"]
    assert payload["game_engine_normalized_results_summary_path"] == "artifacts/game-engine-governance/normalized-results-summary.json"
    assert payload["game_engine_normalized_summary_count"] == 1
    assert payload["game_engine_normalized_missing_count"] == 1
    assert payload["game_engine_normalized_publish_ready"] is False
    assert payload["game_engine_normalized_results_status"] == "partial"
    assert payload["game_engine_publish_gate_status"] == "blocked"
    assert payload["game_engine_publish_blocker_count"] == 1
    assert payload["game_engine_publish_blockers"] == [
        "Normalized Unity/Unreal result rollups still contain missing, failed, or parse-error evidence."
    ]
    assert payload["evidence_pipeline_status"] == "partial"
    assert payload["recommended_runner_lanes"] == ["unity"]
    assert "unity" in payload["ready_runner_lanes"]
    assert any("Game-engine evidence is not normalized" in reason for reason in payload["blocking_reasons"])
    assert any("Game-engine publish blockers still exist:" in reason for reason in payload["blocking_reasons"])


def test_native_app_validation_governance_requires_selected_target_bound_runner_lanes(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-native-app-selected-target"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_project_artifact_registry",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "Android and browser installables plus evidence are present.",
            "artifact_count": 5,
            "artifact_paths": [
                "builds/android/app-release.apk",
                "builds/web/index.html",
                "artifacts/logs/device.log",
                "artifacts/screenshots/home.png",
                "artifacts/traces/playwright-trace.zip",
            ],
            "artifact_extensions": [".apk", ".html", ".log", ".png", ".zip"],
            "artifact_extension_count": 5,
            "artifact_kind_summaries": ["installable:2", "evidence:3"],
            "artifact_kind_counts": {"installable": 2, "evidence": 3},
            "artifact_kind_count": 2,
            "inspection_command_count": 0,
            "inspection_commands": [],
            "config_review_path_count": 0,
            "config_review_paths": [],
            "config_review_command_count": 0,
            "config_review_commands": [],
            "validation_evidence_target_count": 3,
            "validation_evidence_targets": [
                "artifacts/logs/device.log",
                "artifacts/screenshots/home.png",
                "artifacts/traces/playwright-trace.zip",
            ],
            "execution_entrypoint_count": 2,
            "execution_entrypoints": ["./gradlew connectedCheck", "playwright test"],
            "notebook_path_count": 0,
            "notebook_paths": [],
            "recommended_next_steps": [],
            "recommended_next_step_count": 0,
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Selected target is iOS, while Android and browser runners exist elsewhere.",
            "selected_target_id": "mac-ios",
            "lane_count": 3,
            "ready_lane_count": 2,
            "partial_lane_count": 0,
            "unavailable_lane_count": 1,
            "ready_lane_ids": ["android", "browser"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": ["ios"],
            "selected_ready_lane_ids": [],
            "lanes": [
                {
                    "lane_id": "android",
                    "title": "Android Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["android-lab"],
                    "target_count": 1,
                    "selected_target_ids": [],
                    "os_families": ["linux"],
                    "toolchains": ["adb", "gradle"],
                    "command_families": ["adb", "gradle"],
                    "recommended_commands": ["./gradlew connectedCheck"],
                    "notes": [],
                },
                {
                    "lane_id": "browser",
                    "title": "Browser Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["browser-lab"],
                    "target_count": 1,
                    "selected_target_ids": [],
                    "os_families": ["linux"],
                    "toolchains": ["playwright"],
                    "command_families": ["browser"],
                    "recommended_commands": ["playwright test"],
                    "notes": [],
                },
                {
                    "lane_id": "ios",
                    "title": "iOS Runner",
                    "status": "unavailable",
                    "summary": "unavailable",
                    "target_ids": ["mac-ios"],
                    "target_count": 1,
                    "selected_target_ids": ["mac-ios"],
                    "os_families": ["macos"],
                    "toolchains": ["xcode15"],
                    "command_families": ["xcodebuild"],
                    "recommended_commands": ["xcodebuild test"],
                    "notes": [],
                },
            ],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Artifact transport is ready for the selected target.",
            "selected_target_id": "mac-ios",
            "preflight_ready": True,
            "sync_enabled": True,
            "recommended_transport_mode": "remote_artifact_root",
            "blocking_reasons": [],
            "ready_platform_lanes": ["android", "browser"],
            "partial_platform_lanes": [],
            "notes": ["Artifacts can move, but selected-target lane binding still matters."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
            "artifact_contract": {"sync_enabled": True, "required": True, "preflight_ready": True},
            "connector_contract": {"available_families": ["source_control"], "preflight_ready": True},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_game_engine_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "No engine surfaces detected.",
            "governance_status": "not_applicable",
            "detected_engines": [],
            "scene_or_map_count": 0,
            "scene_or_map_paths": [],
            "automation_signal_count": 0,
            "automation_signal_paths": [],
            "screenshot_artifact_count": 0,
            "screenshot_artifact_paths": [],
            "playable_contract_status": "not_applicable",
            "normalized_results_summary_path": None,
            "normalized_summary_count": 0,
            "normalized_passed_count": 0,
            "normalized_failed_count": 0,
            "normalized_missing_count": 0,
            "normalized_publish_ready": False,
            "normalized_results_status": "not_applicable",
            "publish_gate_status": "not_applicable",
            "publish_blockers": [],
            "recommended_fixes": [],
            "notes": [],
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native App Selected Target Demo",
            "idea": "Selected target should gate native app runner readiness.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/native-app-validation-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["selected_target_id"] == "mac-ios"
    assert payload["selected_target_probe_status"] == "unknown"
    assert payload["availability_diagnostics"]["candidate_count"] == 0
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["governance_status"] == "partial"
    assert payload["detected_platforms"] == ["android", "browser"]
    assert payload["ready_runner_lanes"] == []
    assert payload["recommended_runner_lanes"] == []
    assert payload["evidence_pipeline_status"] == "ready"
    assert any(
        "Selected broker target `mac-ios` is not bound to runner lanes for detected app surfaces: android, browser."
        == reason
        for reason in payload["blocking_reasons"]
    )
    assert any(
        "Bind the selected broker target to runner lanes for: android, browser." == fix
        for fix in payload["recommended_fixes"]
    )
    assert any("Selected broker target is `mac-ios`." == note for note in payload["notes"])


def test_native_app_validation_governance_plan_route_generates_install_flow_runner_lane_and_evidence_manifests(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-native-app-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_native_app_validation_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Native app validation governance is ready.",
            "governance_status": "ready",
            "selected_target_id": "mac-lab",
            "selected_target_probe_status": "ready",
            "availability_diagnostics": {"candidate_count": 1, "ready_candidate_count": 1},
            "selected_target_requirement_gaps": {},
            "selected_target_rejected_reasons": [],
            "detected_platforms": ["android", "ios", "browser"],
            "governed_surface_count": 4,
            "game_engine_surface_count": 1,
            "game_engine_surface_ids": ["unity"],
            "game_engine_governance_status": "ready",
            "game_engine_playable_contract_status": "ready",
            "game_engine_scene_or_map_count": 1,
            "game_engine_scene_or_map_paths": ["Assets/Scenes/MainMenu.unity"],
            "game_engine_automation_signal_count": 1,
            "game_engine_automation_signal_paths": ["Tests/SmokeTests.cs"],
            "game_engine_screenshot_artifact_count": 1,
            "game_engine_screenshot_artifact_paths": ["artifacts/screenshots/frame_0001.png"],
            "game_engine_normalized_results_summary_path": "artifacts/game-engine-governance/normalized-results-summary.json",
            "game_engine_normalized_summary_count": 2,
            "game_engine_normalized_passed_count": 2,
            "game_engine_normalized_failed_count": 0,
            "game_engine_normalized_missing_count": 0,
            "game_engine_normalized_publish_ready": True,
            "game_engine_normalized_results_status": "ready",
            "game_engine_publish_gate_status": "ready",
            "game_engine_publish_blocker_count": 0,
            "game_engine_publish_blockers": [],
            "ready_runner_lanes": ["android", "browser"],
            "partial_runner_lanes": ["ios", "unity"],
            "unavailable_runner_lanes": ["linux", "macos", "windows"],
            "installable_artifact_count": 3,
            "installable_artifact_paths": [
                "builds/android/app-release.apk",
                "builds/ios/TestFlight.ipa",
                "builds/web/index.html",
            ],
            "installable_artifact_extensions": [".apk", ".ipa", ".html"],
            "log_artifact_count": 1,
            "log_artifact_paths": ["artifacts/logs/device.log"],
            "screenshot_artifact_count": 1,
            "screenshot_artifact_paths": ["artifacts/screenshots/home.png"],
            "trace_artifact_count": 1,
            "trace_artifact_paths": ["artifacts/traces/playwright-trace.zip"],
            "crash_artifact_count": 1,
            "crash_artifact_paths": ["artifacts/crash/app.crash"],
            "coverage_artifact_count": 1,
            "coverage_artifact_paths": ["artifacts/coverage/lcov.info"],
            "performance_artifact_count": 1,
            "performance_artifact_paths": ["artifacts/perf/fps-benchmark.json"],
            "session_recording_status": "ready",
            "session_recording_required": True,
            "session_recording_artifact_count": 1,
            "session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
            ],
            "produced_session_recording_artifact_count": 1,
            "produced_session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
            ],
            "missing_session_recording_artifact_count": 0,
            "missing_session_recording_artifact_paths": [],
            "remote_session_recording_artifact_paths": [
                "/Users/runner/artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
            ],
            "result_bundle_status": "ready",
            "result_collection_status": "ready",
            "declared_result_collection_count": 3,
            "declared_result_artifact_paths": [
                "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "artifacts/remote-execution-governance/session-recordings/mac-lab.cast",
                "artifacts/screenshots/home.png",
            ],
            "produced_result_artifact_count": 3,
            "produced_result_artifact_paths": [
                "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "artifacts/remote-execution-governance/session-recordings/mac-lab.cast",
                "artifacts/screenshots/home.png",
            ],
            "missing_result_artifact_count": 0,
            "missing_result_artifact_paths": [],
            "result_collection_transfer_statuses": {"completed": 1},
            "evidence_pipeline_status": "ready",
            "adapter_contract_status": "partial",
            "adapter_contract_count": 4,
            "adapter_contract_surface_ids": ["android", "browser", "ios", "unity"],
            "missing_adapter_contract_surfaces": [],
            "ready_adapter_contract_ids": ["android_adb_contract", "browser_automation_contract"],
            "partial_adapter_contract_ids": ["ios_xcodebuild_contract", "unity_batchmode_contract"],
            "unavailable_adapter_contract_ids": [],
            "required_tool_adapter_family_count": 6,
            "required_tool_adapter_families": ["adb", "gradle", "browser_automation", "playwright", "xcodebuild", "unity_batchmode"],
            "required_adapter_evidence_categories": ["logs", "screenshots", "traces", "crashes", "coverage", "performance"],
            "optional_adapter_evidence_categories": ["session_recordings"],
            "adapter_contracts": [
                {"contract_id": "android_adb_contract", "adapter_family": "android_adb", "status": "ready", "selected_binding_status": "ready", "required_tool_families": ["adb", "gradle"], "expected_evidence_categories": ["logs", "screenshots", "traces", "crashes", "coverage", "performance"], "artifact_shipping_modes": ["brokered_sync", "workspace_relative_sync"]},
                {"contract_id": "browser_automation_contract", "adapter_family": "browser_automation", "status": "ready", "selected_binding_status": "not_required", "required_tool_families": ["browser_automation", "playwright"], "expected_evidence_categories": ["logs", "screenshots", "traces", "coverage", "performance"], "artifact_shipping_modes": ["brokered_sync", "local_only", "connector_only"]},
                {"contract_id": "ios_xcodebuild_contract", "adapter_family": "ios_xcodebuild", "status": "partial", "selected_binding_status": "visible_but_not_ready", "required_tool_families": ["xcodebuild"], "expected_evidence_categories": ["logs", "screenshots", "traces", "crashes", "coverage", "performance"], "artifact_shipping_modes": ["brokered_sync", "workspace_relative_sync"]},
                {"contract_id": "unity_batchmode_contract", "adapter_family": "unity_batchmode", "status": "partial", "selected_binding_status": "visible_but_not_ready", "required_tool_families": ["unity_batchmode"], "expected_evidence_categories": ["logs", "screenshots", "traces", "coverage", "performance"], "artifact_shipping_modes": ["brokered_sync", "workspace_relative_sync"]},
            ],
            "recommended_runner_lanes": ["android", "browser", "ios", "unity"],
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Platform evidence is already wired."],
            "platform_runners": {
                "summary": "Android and browser lanes are ready.",
                "ready_route_ids": ["tailscale_ssh"],
                "selected_route_ids": [],
                "selected_ready_route_ids": [],
                "partial_route_ids": ["plain_ssh", "macos_host"],
                "unavailable_route_ids": [],
                "ready_lane_ids": ["android", "browser"],
                "partial_lane_ids": ["ios", "unity"],
                "unavailable_lane_ids": ["linux", "macos", "windows"],
                "lanes": [
                    {"lane_id": "android", "route_ids": ["tailscale_ssh"], "selected_route_ids": [], "selected_ready_route_ids": [], "adapter_contract": {"contract_id": "android_adb_contract", "adapter_family": "android_adb", "status": "ready", "selected_binding_status": "ready", "required_tool_families": ["adb", "gradle"], "expected_evidence_categories": ["logs", "screenshots", "traces", "crashes", "coverage", "performance"], "artifact_shipping_modes": ["brokered_sync", "workspace_relative_sync"]}},
                    {"lane_id": "browser", "route_ids": [], "selected_route_ids": [], "selected_ready_route_ids": [], "adapter_contract": {"contract_id": "browser_automation_contract", "adapter_family": "browser_automation", "status": "ready", "selected_binding_status": "not_required", "required_tool_families": ["browser_automation", "playwright"], "expected_evidence_categories": ["logs", "screenshots", "traces", "coverage", "performance"], "artifact_shipping_modes": ["brokered_sync", "local_only", "connector_only"]}},
                    {"lane_id": "ios", "route_ids": ["plain_ssh", "macos_host"], "selected_route_ids": [], "selected_ready_route_ids": [], "adapter_contract": {"contract_id": "ios_xcodebuild_contract", "adapter_family": "ios_xcodebuild", "status": "partial", "selected_binding_status": "visible_but_not_ready", "required_tool_families": ["xcodebuild"], "expected_evidence_categories": ["logs", "screenshots", "traces", "crashes", "coverage", "performance"], "artifact_shipping_modes": ["brokered_sync", "workspace_relative_sync"]}},
                    {"lane_id": "unity", "route_ids": ["plain_ssh"], "selected_route_ids": [], "selected_ready_route_ids": [], "adapter_contract": {"contract_id": "unity_batchmode_contract", "adapter_family": "unity_batchmode", "status": "partial", "selected_binding_status": "visible_but_not_ready", "required_tool_families": ["unity_batchmode"], "expected_evidence_categories": ["logs", "screenshots", "traces", "coverage", "performance"], "artifact_shipping_modes": ["brokered_sync", "workspace_relative_sync"]}},
                ],
            },
            "artifact_transport": {
                "summary": "Artifact sync is ready.",
                "recommended_transport_mode": "brokered_sync",
                "ready_platform_lanes": ["android", "browser"],
                "partial_platform_lanes": ["ios"],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native App Plan Demo",
            "idea": "Need governed platform validation manifests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/native-app-validation-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["selected_target_id"] == "mac-lab"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["availability_diagnostics"]["candidate_count"] == 1
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["detected_platforms"] == ["android", "ios", "browser"]
    assert payload["governed_surface_count"] == 4
    assert payload["game_engine_surface_count"] == 1
    assert payload["game_engine_surface_ids"] == ["unity"]
    assert payload["game_engine_scene_or_map_count"] == 1
    assert payload["game_engine_scene_or_map_paths"] == ["Assets/Scenes/MainMenu.unity"]
    assert payload["game_engine_automation_signal_count"] == 1
    assert payload["game_engine_automation_signal_paths"] == ["Tests/SmokeTests.cs"]
    assert payload["game_engine_screenshot_artifact_count"] == 1
    assert payload["game_engine_screenshot_artifact_paths"] == ["artifacts/screenshots/frame_0001.png"]
    assert payload["evidence_pipeline_status"] == "ready"
    assert payload["ready_runner_lanes"] == ["android", "browser"]
    assert payload["partial_runner_lanes"] == ["ios", "unity"]
    assert payload["unavailable_runner_lanes"] == ["linux", "macos", "windows"]
    assert payload["adapter_contract_status"] == "partial"
    assert payload["adapter_contract_count"] == 4
    assert payload["ready_adapter_contract_ids"] == ["android_adb_contract", "browser_automation_contract"]
    assert payload["partial_adapter_contract_ids"] == ["ios_xcodebuild_contract", "unity_batchmode_contract"]
    assert "playwright" in payload["required_tool_adapter_families"]
    assert payload["recommended_runner_lanes"] == ["android", "browser", "ios", "unity"]
    assert payload["recommended_transport_mode"] == "brokered_sync"
    assert payload["selected_adapter_contract_ids"] == [
        "android_adb_contract",
        "browser_automation_contract",
        "ios_xcodebuild_contract",
        "unity_batchmode_contract",
    ]
    assert payload["selected_adapter_shipping_modes"] == [
        "brokered_sync",
        "workspace_relative_sync",
        "local_only",
        "connector_only",
    ]
    assert payload["common_adapter_shipping_modes"] == ["brokered_sync"]
    assert payload["transport_mode_adapter_status"] == "ready"
    assert payload["transport_mode_supported_adapter_contract_ids"] == [
        "android_adb_contract",
        "browser_automation_contract",
        "ios_xcodebuild_contract",
        "unity_batchmode_contract",
    ]
    assert payload["transport_mode_unsupported_adapter_contract_ids"] == []
    assert payload["transport_mode_undeclared_adapter_contract_ids"] == []
    assert payload["installable_artifact_count"] == 3
    assert payload["installable_artifact_paths"] == [
        "builds/android/app-release.apk",
        "builds/ios/TestFlight.ipa",
        "builds/web/index.html",
    ]
    assert payload["installable_artifact_extensions"] == [".apk", ".ipa", ".html"]
    assert payload["game_engine_normalized_results_summary_path"] == "artifacts/game-engine-governance/normalized-results-summary.json"
    assert payload["game_engine_normalized_summary_count"] == 2
    assert payload["game_engine_normalized_publish_ready"] is True
    assert payload["game_engine_normalized_results_status"] == "ready"
    assert payload["game_engine_publish_gate_status"] == "ready"
    assert payload["game_engine_publish_blocker_count"] == 0
    assert payload["game_engine_publish_blockers"] == []
    assert payload["session_recording_status"] == "ready"
    assert payload["session_recording_required"] is True
    assert payload["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
    ]
    assert payload["produced_session_recording_artifact_count"] == 1
    assert payload["produced_session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
    ]
    assert payload["missing_session_recording_artifact_count"] == 0
    assert payload["missing_session_recording_artifact_paths"] == []
    assert payload["remote_session_recording_artifact_paths"] == [
        "/Users/runner/artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
    ]
    assert payload["result_bundle_status"] == "ready"
    assert payload["result_collection_status"] == "ready"
    assert payload["declared_result_collection_count"] == 3
    assert payload["produced_result_artifact_count"] == 3
    assert payload["missing_result_artifact_count"] == 0
    assert payload["produced_result_artifact_paths"] == [
        "artifacts/remote-execution-governance/normalized-execution-summary.json",
        "artifacts/remote-execution-governance/session-recordings/mac-lab.cast",
        "artifacts/screenshots/home.png",
    ]
    assert payload["result_collection_transfer_statuses"] == {"completed": 1}
    assert payload["manifest_root"] == "artifacts/native-app-validation-governance"
    assert payload["platform_matrix_path"] == "artifacts/native-app-validation-governance/platform-matrix.json"
    assert payload["artifact_shipping_plan_path"] == "artifacts/native-app-validation-governance/artifact-shipping-plan.json"
    assert payload["install_flow_plan_path"] == "artifacts/native-app-validation-governance/install-flow-plan.json"
    assert payload["runner_lane_plan_path"] == "artifacts/native-app-validation-governance/runner-lane-plan.json"
    assert payload["adapter_evidence_contract_path"] == "artifacts/native-app-validation-governance/adapter-evidence-contracts.json"
    assert payload["evidence_bundle_plan_path"] == "artifacts/native-app-validation-governance/evidence-bundle-plan.json"
    assert payload["approval_checkpoint_path"] == "artifacts/native-app-validation-governance/approval-checkpoints.json"
    evidence_bundle = json.loads((workspace / "artifacts" / "native-app-validation-governance" / "evidence-bundle-plan.json").read_text(encoding="utf-8"))
    assert evidence_bundle["game_engine_scene_or_map_count"] == 1
    assert evidence_bundle["game_engine_scene_or_map_paths"] == ["Assets/Scenes/MainMenu.unity"]
    assert evidence_bundle["game_engine_automation_signal_count"] == 1
    assert evidence_bundle["game_engine_automation_signal_paths"] == ["Tests/SmokeTests.cs"]
    assert evidence_bundle["game_engine_screenshot_artifact_count"] == 1
    assert evidence_bundle["game_engine_screenshot_artifact_paths"] == ["artifacts/screenshots/frame_0001.png"]
    assert evidence_bundle["game_engine_normalized_results_summary_path"] == "artifacts/game-engine-governance/normalized-results-summary.json"
    assert evidence_bundle["game_engine_normalized_summary_count"] == 2
    assert evidence_bundle["game_engine_normalized_publish_ready"] is True
    assert evidence_bundle["game_engine_normalized_results_status"] == "ready"
    assert evidence_bundle["game_engine_publish_gate_status"] == "ready"
    assert evidence_bundle["game_engine_publish_blocker_count"] == 0
    assert evidence_bundle["game_engine_publish_blockers"] == []
    assert evidence_bundle["session_recording_status"] == "ready"
    assert evidence_bundle["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
    ]
    assert evidence_bundle["produced_session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
    ]
    assert evidence_bundle["missing_session_recording_artifact_paths"] == []
    assert evidence_bundle["result_bundle_status"] == "ready"
    assert evidence_bundle["result_collection_status"] == "ready"
    assert evidence_bundle["declared_result_collection_count"] == 3
    assert evidence_bundle["produced_result_artifact_count"] == 3
    assert evidence_bundle["missing_result_artifact_count"] == 0
    assert evidence_bundle["produced_result_artifact_paths"] == [
        "artifacts/remote-execution-governance/normalized-execution-summary.json",
        "artifacts/remote-execution-governance/session-recordings/mac-lab.cast",
        "artifacts/screenshots/home.png",
    ]
    assert "session_recordings" in evidence_bundle["required_categories"]
    assert evidence_bundle["publish_ready"] is True
    approval_checkpoints = json.loads((workspace / "artifacts" / "native-app-validation-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    assert any(
        checkpoint["checkpoint_id"] == "game_engine_normalization_review" and checkpoint["status"] == "ready"
        for checkpoint in approval_checkpoints["checkpoints"]
    )

    assert (workspace / "artifacts" / "native-app-validation-governance" / "platform-matrix.json").exists()
    assert (workspace / "artifacts" / "native-app-validation-governance" / "artifact-shipping-plan.json").exists()
    assert (workspace / "artifacts" / "native-app-validation-governance" / "install-flow-plan.json").exists()
    assert (workspace / "artifacts" / "native-app-validation-governance" / "runner-lane-plan.json").exists()
    assert (workspace / "artifacts" / "native-app-validation-governance" / "adapter-evidence-contracts.json").exists()
    assert (workspace / "artifacts" / "native-app-validation-governance" / "evidence-bundle-plan.json").exists()
    assert (workspace / "artifacts" / "native-app-validation-governance" / "approval-checkpoints.json").exists()

    platform_matrix = json.loads((workspace / "artifacts" / "native-app-validation-governance" / "platform-matrix.json").read_text(encoding="utf-8"))
    assert platform_matrix["selected_target_id"] == "mac-lab"
    assert platform_matrix["selected_target_probe_status"] == "ready"
    assert platform_matrix["availability_diagnostics"]["candidate_count"] == 1
    assert platform_matrix["selected_target_requirement_gaps"] == {}
    assert platform_matrix["selected_target_rejected_reasons"] == []
    assert platform_matrix["recommended_transport_mode"] == "brokered_sync"
    assert platform_matrix["game_engine_surface_ids"] == ["unity"]
    assert platform_matrix["game_engine_scene_or_map_count"] == 1
    assert platform_matrix["game_engine_scene_or_map_paths"] == ["Assets/Scenes/MainMenu.unity"]
    assert platform_matrix["game_engine_automation_signal_count"] == 1
    assert platform_matrix["game_engine_automation_signal_paths"] == ["Tests/SmokeTests.cs"]
    assert platform_matrix["game_engine_screenshot_artifact_count"] == 1
    assert platform_matrix["game_engine_screenshot_artifact_paths"] == ["artifacts/screenshots/frame_0001.png"]
    assert platform_matrix["governed_surface_count"] == 4
    assert platform_matrix["ready_runner_route_ids"] == ["tailscale_ssh"]
    assert platform_matrix["partial_runner_route_ids"] == ["plain_ssh", "macos_host"]
    platform_records = {item["platform"]: item for item in platform_matrix["platforms"]}
    assert platform_records["android"]["runner_lane_status"] == "ready"
    assert platform_records["android"]["route_ids"] == ["tailscale_ssh"]
    assert "builds/android/app-release.apk" in platform_records["android"]["installable_artifacts"]
    assert platform_records["ios"]["runner_lane_status"] == "partial"
    assert platform_records["ios"]["route_ids"] == ["plain_ssh", "macos_host"]
    assert platform_records["browser"]["recommended_for_validation"] is True
    assert platform_records["unity"]["surface_type"] == "engine"
    assert platform_records["unity"]["runner_lane_status"] == "partial"
    assert platform_records["unity"]["engine_validation_input_count"] == 3
    assert "Assets/Scenes/MainMenu.unity" in platform_records["unity"]["engine_validation_inputs"]

    artifact_shipping_plan = json.loads((workspace / "artifacts" / "native-app-validation-governance" / "artifact-shipping-plan.json").read_text(encoding="utf-8"))
    assert artifact_shipping_plan["selected_target_id"] == "mac-lab"
    assert artifact_shipping_plan["selected_target_probe_status"] == "ready"
    assert artifact_shipping_plan["availability_diagnostics"]["candidate_count"] == 1
    assert artifact_shipping_plan["selected_target_requirement_gaps"] == {}
    assert artifact_shipping_plan["selected_target_rejected_reasons"] == []
    assert artifact_shipping_plan["shipping_requirements"]["approval_required_before_dispatch"] is True
    assert artifact_shipping_plan["shipping_requirements"]["installable_artifact_required"] is True
    assert artifact_shipping_plan["shipping_requirements"]["engine_validation_input_required"] is True
    assert artifact_shipping_plan["shipping_requirements"]["result_bundle_status"] == "ready"
    assert artifact_shipping_plan["shipping_requirements"]["result_collection_status"] == "ready"
    assert artifact_shipping_plan["shipping_requirements"]["transport_mode_adapter_status"] == "ready"
    assert artifact_shipping_plan["shipping_requirements"]["adapter_transport_mode_review_required"] is False
    assert "artifacts/traces/playwright-trace.zip" in artifact_shipping_plan["evidence_artifact_paths"]
    assert artifact_shipping_plan["selected_adapter_contract_ids"] == [
        "android_adb_contract",
        "browser_automation_contract",
        "ios_xcodebuild_contract",
        "unity_batchmode_contract",
    ]
    assert artifact_shipping_plan["result_collection_contract"]["declared_result_collection_count"] == 3
    assert artifact_shipping_plan["result_collection_contract"]["produced_result_artifact_count"] == 3
    assert artifact_shipping_plan["result_collection_contract"]["missing_result_artifact_count"] == 0
    shipping_targets = {item["platform"]: item for item in artifact_shipping_plan["target_lane_matrix"]}
    assert shipping_targets["android"]["ready_for_dispatch"] is True
    assert shipping_targets["android"]["transport_mode_adapter_status"] == "ready"
    assert shipping_targets["ios"]["runner_lane_status"] == "partial"
    assert shipping_targets["unity"]["ready_for_dispatch"] is True
    assert "Tests/SmokeTests.cs" in shipping_targets["unity"]["engine_validation_inputs"]

    install_flow_plan = json.loads((workspace / "artifacts" / "native-app-validation-governance" / "install-flow-plan.json").read_text(encoding="utf-8"))
    install_flows = {item["platform"]: item for item in install_flow_plan["platform_install_flows"]}
    assert install_flows["android"]["install_surface"] == "adb_install"
    assert "capture_evidence" in install_flows["android"]["required_steps"]
    assert install_flows["android"]["adapter_contract"]["contract_id"] == "android_adb_contract"
    assert install_flows["browser"]["install_surface"] == "browser_navigation"
    assert install_flows["unity"]["install_surface"] == "engine_batchmode"
    assert "engine_native_tests" in install_flows["unity"]["required_steps"]
    assert "unity_batchmode" in install_flows["unity"]["required_tool_families"]
    assert "Assets/Scenes/MainMenu.unity" in install_flows["unity"]["engine_validation_inputs"]

    runner_lane_plan = json.loads((workspace / "artifacts" / "native-app-validation-governance" / "runner-lane-plan.json").read_text(encoding="utf-8"))
    assert runner_lane_plan["selected_target_id"] == "mac-lab"
    assert runner_lane_plan["selected_target_probe_status"] == "ready"
    assert runner_lane_plan["availability_diagnostics"]["candidate_count"] == 1
    assert runner_lane_plan["selected_target_requirement_gaps"] == {}
    assert runner_lane_plan["selected_target_rejected_reasons"] == []
    assert runner_lane_plan["ready_route_ids"] == ["tailscale_ssh"]
    assert runner_lane_plan["partial_route_ids"] == ["plain_ssh", "macos_host"]
    assert runner_lane_plan["adapter_contract_status"] == "partial"
    assert runner_lane_plan["transport_mode_adapter_status"] == "ready"
    assert runner_lane_plan["required_tool_adapter_families"] == ["adb", "gradle", "browser_automation", "playwright", "xcodebuild", "unity_batchmode"]
    lane_dispatch = {item["lane_id"]: item for item in runner_lane_plan["lane_dispatch"]}
    assert lane_dispatch["browser"]["selected_for_validation"] is True
    assert lane_dispatch["browser"]["transport_mode_adapter_status"] == "ready"
    assert lane_dispatch["android"]["route_ids"] == ["tailscale_ssh"]
    assert lane_dispatch["android"]["adapter_contract"]["contract_id"] == "android_adb_contract"
    assert lane_dispatch["ios"]["status"] == "partial"
    assert lane_dispatch["ios"]["route_ids"] == ["plain_ssh", "macos_host"]
    assert lane_dispatch["unity"]["selected_for_validation"] is True
    assert lane_dispatch["unity"]["engine_validation_input_count"] == 3
    assert runner_lane_plan["dispatch_requirements"]["broker_route_review_required"] is True
    assert runner_lane_plan["dispatch_requirements"]["transport_review_required"] is True
    assert runner_lane_plan["dispatch_requirements"]["installable_artifact_required"] is True
    assert runner_lane_plan["dispatch_requirements"]["engine_validation_input_required"] is True

    evidence_bundle_plan = json.loads((workspace / "artifacts" / "native-app-validation-governance" / "evidence-bundle-plan.json").read_text(encoding="utf-8"))
    assert evidence_bundle_plan["publish_ready"] is True
    assert "performance" in evidence_bundle_plan["categories_present"]
    assert "session_recordings" in evidence_bundle_plan["categories_present"]
    evidence_categories = {item["category"]: item for item in evidence_bundle_plan["evidence_categories"]}
    assert evidence_categories["logs"]["path_count"] == 1
    assert "artifacts/coverage/lcov.info" in evidence_categories["coverage"]["paths"]
    assert evidence_categories["session_recordings"]["paths"] == [
        "artifacts/remote-execution-governance/session-recordings/mac-lab.cast"
    ]

    adapter_evidence_contracts = json.loads((workspace / "artifacts" / "native-app-validation-governance" / "adapter-evidence-contracts.json").read_text(encoding="utf-8"))
    assert adapter_evidence_contracts["adapter_contract_status"] == "partial"
    assert adapter_evidence_contracts["ready_adapter_contract_ids"] == ["android_adb_contract", "browser_automation_contract"]
    assert "playwright" in adapter_evidence_contracts["required_tool_adapter_families"]
    assert "screenshots" in adapter_evidence_contracts["required_adapter_evidence_categories"]

    approval_checkpoints = json.loads((workspace / "artifacts" / "native-app-validation-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    checkpoint_ids = [item["checkpoint_id"] for item in approval_checkpoints["checkpoints"]]
    assert "adapter_contract_review" in checkpoint_ids
    assert "adapter_transport_mode_review" in checkpoint_ids
    assert "result_collection_review" in checkpoint_ids
    assert "session_recording_review" in checkpoint_ids
    assert "transport_review" in checkpoint_ids
    assert "runner_route_review" in checkpoint_ids
    assert "publish_gate" in checkpoint_ids
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_by_id["installable_artifact_review"]["status"] == "ready"
    assert checkpoint_by_id["adapter_contract_review"]["status"] == "partial"
    assert checkpoint_by_id["adapter_transport_mode_review"]["status"] == "ready"
    assert checkpoint_by_id["runner_route_review"]["status"] == "blocked"
    assert checkpoint_by_id["result_collection_review"]["status"] == "ready"
    assert checkpoint_by_id["session_recording_review"]["status"] == "ready"
    assert checkpoint_by_id["publish_gate"]["status"] == "ready"


def test_native_app_validation_governance_plan_route_keeps_publish_ready_false_when_game_engine_gate_is_blocked(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-native-app-plan-blocked-engine-gate"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_native_app_validation_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Native app validation governance is partial because the engine publish gate is blocked.",
            "governance_status": "partial",
            "detected_platforms": ["browser"],
            "governed_surface_count": 2,
            "game_engine_surface_count": 1,
            "game_engine_surface_ids": ["unity"],
            "game_engine_governance_status": "partial",
            "game_engine_playable_contract_status": "ready",
            "game_engine_normalized_results_summary_path": "artifacts/game-engine-governance/normalized-results-summary.json",
            "game_engine_normalized_summary_count": 2,
            "game_engine_normalized_passed_count": 2,
            "game_engine_normalized_failed_count": 0,
            "game_engine_normalized_missing_count": 0,
            "game_engine_normalized_publish_ready": True,
            "game_engine_normalized_results_status": "ready",
            "game_engine_publish_gate_status": "blocked",
            "game_engine_publish_blocker_count": 1,
            "game_engine_publish_blockers": ["Playable contract coverage is still missing one required golden-path checkpoint."],
            "ready_runner_lanes": ["browser"],
            "partial_runner_lanes": ["unity"],
            "unavailable_runner_lanes": ["android", "ios", "linux", "macos", "windows", "unreal"],
            "installable_artifact_count": 1,
            "installable_artifact_paths": ["builds/web/index.html"],
            "installable_artifact_extensions": [".html"],
            "log_artifact_count": 1,
            "log_artifact_paths": ["artifacts/logs/device.log"],
            "screenshot_artifact_count": 1,
            "screenshot_artifact_paths": ["artifacts/screenshots/home.png"],
            "trace_artifact_count": 1,
            "trace_artifact_paths": ["artifacts/traces/playwright-trace.zip"],
            "crash_artifact_count": 1,
            "crash_artifact_paths": ["artifacts/crash/app.crash"],
            "coverage_artifact_count": 1,
            "coverage_artifact_paths": ["artifacts/coverage/lcov.info"],
            "performance_artifact_count": 1,
            "performance_artifact_paths": ["artifacts/perf/fps-benchmark.json"],
            "evidence_pipeline_status": "ready",
            "recommended_runner_lanes": ["browser", "unity"],
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": [
                "Game-engine publish blockers still exist: Playable contract coverage is still missing one required golden-path checkpoint.."
            ],
            "recommended_fixes": [],
            "notes": ["Engine evidence exists, but publish is still blocked upstream."],
            "platform_runners": {
                "summary": "Browser lane is ready and Unity lane is partial.",
                "ready_lane_ids": ["browser"],
                "partial_lane_ids": ["unity"],
                "unavailable_lane_ids": ["android", "ios", "linux", "macos", "windows", "unreal"],
            },
            "artifact_transport": {
                "summary": "Artifact sync is ready.",
                "recommended_transport_mode": "brokered_sync",
                "ready_platform_lanes": ["browser"],
                "partial_platform_lanes": ["unity"],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native App Plan Blocked Engine Gate Demo",
            "idea": "Need publish readiness to stay blocked when the game-engine gate is blocked.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/native-app-validation-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["game_engine_publish_gate_status"] == "blocked"
    assert payload["game_engine_publish_blocker_count"] == 1
    evidence_bundle = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "evidence-bundle-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence_bundle["game_engine_normalized_publish_ready"] is True
    assert evidence_bundle["game_engine_publish_gate_status"] == "blocked"
    assert evidence_bundle["game_engine_publish_blocker_count"] == 1
    assert evidence_bundle["publish_ready"] is False
    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "approval-checkpoints.json").read_text(
            encoding="utf-8"
        )
    )
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_by_id["publish_gate"]["status"] == "blocked"


def test_native_app_validation_governance_plan_route_accepts_engine_inputs_without_installables(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-native-app-plan-engine-only"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_native_app_validation_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Native app validation governance is ready for an engine-only Unity surface.",
            "governance_status": "ready",
            "detected_platforms": [],
            "governed_surface_count": 1,
            "game_engine_surface_count": 1,
            "game_engine_surface_ids": ["unity"],
            "game_engine_governance_status": "ready",
            "game_engine_playable_contract_status": "ready",
            "game_engine_scene_or_map_count": 1,
            "game_engine_scene_or_map_paths": ["Assets/Scenes/MainMenu.unity"],
            "game_engine_automation_signal_count": 1,
            "game_engine_automation_signal_paths": ["Tests/SmokeTests.cs"],
            "game_engine_screenshot_artifact_count": 1,
            "game_engine_screenshot_artifact_paths": ["artifacts/screenshots/frame_0001.png"],
            "game_engine_normalized_results_summary_path": "artifacts/game-engine-governance/normalized-results-summary.json",
            "game_engine_normalized_summary_count": 1,
            "game_engine_normalized_passed_count": 1,
            "game_engine_normalized_failed_count": 0,
            "game_engine_normalized_missing_count": 0,
            "game_engine_normalized_publish_ready": True,
            "game_engine_normalized_results_status": "ready",
            "game_engine_publish_gate_status": "ready",
            "game_engine_publish_blocker_count": 0,
            "game_engine_publish_blockers": [],
            "ready_runner_lanes": ["unity"],
            "partial_runner_lanes": [],
            "unavailable_runner_lanes": ["android", "ios", "linux", "macos", "windows", "browser", "unreal"],
            "installable_artifact_count": 0,
            "installable_artifact_paths": [],
            "installable_artifact_extensions": [],
            "log_artifact_count": 1,
            "log_artifact_paths": ["artifacts/logs/unity.log"],
            "screenshot_artifact_count": 1,
            "screenshot_artifact_paths": ["artifacts/screenshots/frame_0001.png"],
            "trace_artifact_count": 1,
            "trace_artifact_paths": ["artifacts/traces/unity-trace.zip"],
            "crash_artifact_count": 0,
            "crash_artifact_paths": [],
            "coverage_artifact_count": 1,
            "coverage_artifact_paths": ["artifacts/coverage/editmode-results.xml"],
            "performance_artifact_count": 1,
            "performance_artifact_paths": ["artifacts/perf/fps-benchmark.json"],
            "evidence_pipeline_status": "ready",
            "recommended_runner_lanes": ["unity"],
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Unity lane should dispatch off engine-native inputs."],
            "platform_runners": {
                "summary": "Unity lane is ready.",
                "ready_lane_ids": ["unity"],
                "partial_lane_ids": [],
                "unavailable_lane_ids": ["android", "ios", "linux", "macos", "windows", "browser", "unreal"],
            },
            "artifact_transport": {
                "summary": "Artifact sync is ready.",
                "recommended_transport_mode": "brokered_sync",
                "ready_platform_lanes": ["unity"],
                "partial_platform_lanes": [],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native App Plan Engine Only Demo",
            "idea": "Need Unity surfaces to dispatch from engine-native inputs without fake installables.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/native-app-validation-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "ready"
    assert payload["detected_platforms"] == []
    assert payload["game_engine_surface_count"] == 1
    assert payload["game_engine_scene_or_map_count"] == 1
    assert payload["game_engine_automation_signal_count"] == 1
    assert payload["game_engine_screenshot_artifact_count"] == 1

    artifact_shipping_plan = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "artifact-shipping-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact_shipping_plan["shipping_requirements"]["installable_artifact_required"] is False
    assert artifact_shipping_plan["shipping_requirements"]["engine_validation_input_required"] is True
    shipping_targets = {item["platform"]: item for item in artifact_shipping_plan["target_lane_matrix"]}
    assert shipping_targets["unity"]["ready_for_dispatch"] is True
    assert "Assets/Scenes/MainMenu.unity" in shipping_targets["unity"]["engine_validation_inputs"]

    install_flow_plan = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "install-flow-plan.json").read_text(
            encoding="utf-8"
        )
    )
    install_flows = {item["platform"]: item for item in install_flow_plan["platform_install_flows"]}
    assert install_flows["unity"]["installable_artifacts"] == []
    assert "Tests/SmokeTests.cs" in install_flows["unity"]["engine_validation_inputs"]

    runner_lane_plan = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "runner-lane-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert runner_lane_plan["dispatch_requirements"]["installable_artifact_required"] is False
    assert runner_lane_plan["dispatch_requirements"]["engine_validation_input_required"] is True
    lane_dispatch = {item["lane_id"]: item for item in runner_lane_plan["lane_dispatch"]}
    assert lane_dispatch["unity"]["engine_validation_input_count"] == 3

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "approval-checkpoints.json").read_text(
            encoding="utf-8"
        )
    )
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_by_id["installable_artifact_review"]["status"] == "ready"
    assert checkpoint_by_id["publish_gate"]["status"] == "ready"


def test_native_app_validation_governance_plan_route_keeps_publish_gate_partial_when_evidence_is_incomplete(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-native-app-plan-partial-evidence"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_native_app_validation_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Native app validation governance is partial because evidence coverage is incomplete.",
            "governance_status": "partial",
            "detected_platforms": ["android"],
            "governed_surface_count": 1,
            "game_engine_surface_count": 0,
            "game_engine_surface_ids": [],
            "game_engine_governance_status": "not_applicable",
            "game_engine_playable_contract_status": "not_applicable",
            "game_engine_scene_or_map_count": 0,
            "game_engine_scene_or_map_paths": [],
            "game_engine_automation_signal_count": 0,
            "game_engine_automation_signal_paths": [],
            "game_engine_screenshot_artifact_count": 0,
            "game_engine_screenshot_artifact_paths": [],
            "game_engine_normalized_results_summary_path": None,
            "game_engine_normalized_summary_count": 0,
            "game_engine_normalized_passed_count": 0,
            "game_engine_normalized_failed_count": 0,
            "game_engine_normalized_missing_count": 0,
            "game_engine_normalized_publish_ready": False,
            "game_engine_normalized_results_status": "not_applicable",
            "game_engine_publish_gate_status": "not_applicable",
            "game_engine_publish_blocker_count": 0,
            "game_engine_publish_blockers": [],
            "ready_runner_lanes": ["android"],
            "partial_runner_lanes": [],
            "unavailable_runner_lanes": ["ios", "linux", "macos", "windows", "browser", "unity", "unreal"],
            "installable_artifact_count": 1,
            "installable_artifact_paths": ["builds/android/app-release.apk"],
            "installable_artifact_extensions": [".apk"],
            "log_artifact_count": 1,
            "log_artifact_paths": ["artifacts/logs/device.log"],
            "screenshot_artifact_count": 0,
            "screenshot_artifact_paths": [],
            "trace_artifact_count": 0,
            "trace_artifact_paths": [],
            "crash_artifact_count": 0,
            "crash_artifact_paths": [],
            "coverage_artifact_count": 0,
            "coverage_artifact_paths": [],
            "performance_artifact_count": 0,
            "performance_artifact_paths": [],
            "evidence_pipeline_status": "partial",
            "recommended_runner_lanes": ["android"],
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": [],
            "recommended_fixes": ["Capture screenshots, traces, crashes, coverage, and perf before publish."],
            "notes": ["Evidence is real but incomplete."],
            "platform_runners": {
                "summary": "Android lane is ready.",
                "ready_lane_ids": ["android"],
                "partial_lane_ids": [],
                "unavailable_lane_ids": ["ios", "linux", "macos", "windows", "browser", "unity", "unreal"],
            },
            "artifact_transport": {
                "summary": "Artifact sync is ready.",
                "recommended_transport_mode": "brokered_sync",
                "ready_platform_lanes": ["android"],
                "partial_platform_lanes": [],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native App Plan Partial Evidence Demo",
            "idea": "Need the publish checkpoint to stay partial when evidence coverage is incomplete.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/native-app-validation-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "partial"

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "approval-checkpoints.json").read_text(
            encoding="utf-8"
        )
    )
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_by_id["evidence_bundle_review"]["status"] == "partial"
    assert checkpoint_by_id["publish_gate"]["status"] == "partial"


def test_native_app_validation_governance_plan_route_blocks_dispatch_when_adapter_rejects_transport_mode(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-native-app-plan-blocked-transport-mode"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_native_app_validation_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Native app validation is blocked because the selected adapter contract rejects brokered sync.",
            "governance_status": "partial",
            "detected_platforms": ["browser"],
            "governed_surface_count": 1,
            "game_engine_surface_count": 0,
            "game_engine_surface_ids": [],
            "game_engine_governance_status": "not_applicable",
            "game_engine_playable_contract_status": "not_applicable",
            "game_engine_scene_or_map_count": 0,
            "game_engine_scene_or_map_paths": [],
            "game_engine_automation_signal_count": 0,
            "game_engine_automation_signal_paths": [],
            "game_engine_screenshot_artifact_count": 0,
            "game_engine_screenshot_artifact_paths": [],
            "game_engine_normalized_results_summary_path": None,
            "game_engine_normalized_summary_count": 0,
            "game_engine_normalized_passed_count": 0,
            "game_engine_normalized_failed_count": 0,
            "game_engine_normalized_missing_count": 0,
            "game_engine_normalized_publish_ready": False,
            "game_engine_normalized_results_status": "not_applicable",
            "game_engine_publish_gate_status": "not_applicable",
            "game_engine_publish_blocker_count": 0,
            "game_engine_publish_blockers": [],
            "ready_runner_lanes": ["browser"],
            "partial_runner_lanes": [],
            "unavailable_runner_lanes": ["android", "ios", "linux", "macos", "windows", "unity", "unreal"],
            "installable_artifact_count": 1,
            "installable_artifact_paths": ["builds/web/index.html"],
            "installable_artifact_extensions": [".html"],
            "log_artifact_count": 1,
            "log_artifact_paths": ["artifacts/logs/browser.log"],
            "screenshot_artifact_count": 1,
            "screenshot_artifact_paths": ["artifacts/screenshots/home.png"],
            "trace_artifact_count": 1,
            "trace_artifact_paths": ["artifacts/traces/playwright-trace.zip"],
            "crash_artifact_count": 0,
            "crash_artifact_paths": [],
            "coverage_artifact_count": 1,
            "coverage_artifact_paths": ["artifacts/coverage/lcov.info"],
            "performance_artifact_count": 1,
            "performance_artifact_paths": ["artifacts/perf/fps-benchmark.json"],
            "evidence_pipeline_status": "ready",
            "adapter_contract_status": "ready",
            "adapter_contract_count": 1,
            "adapter_contract_surface_ids": ["browser"],
            "missing_adapter_contract_surfaces": [],
            "ready_adapter_contract_ids": ["browser_automation_contract"],
            "partial_adapter_contract_ids": [],
            "unavailable_adapter_contract_ids": [],
            "required_tool_adapter_family_count": 2,
            "required_tool_adapter_families": ["browser_automation", "playwright"],
            "required_adapter_evidence_categories": ["logs", "screenshots", "traces", "coverage", "performance"],
            "optional_adapter_evidence_categories": [],
            "adapter_contracts": [
                {
                    "contract_id": "browser_automation_contract",
                    "adapter_family": "browser_automation",
                    "status": "ready",
                    "selected_binding_status": "ready",
                    "required_tool_families": ["browser_automation", "playwright"],
                    "expected_evidence_categories": ["logs", "screenshots", "traces", "coverage", "performance"],
                    "artifact_shipping_modes": ["local_only", "connector_only"],
                }
            ],
            "recommended_runner_lanes": ["browser"],
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": [],
            "recommended_fixes": ["Declare brokered sync on the browser automation contract before dispatch."],
            "notes": ["Browser lane is real, but its shipping modes reject brokered sync."],
            "platform_runners": {
                "summary": "Browser lane is ready.",
                "ready_lane_ids": ["browser"],
                "partial_lane_ids": [],
                "unavailable_lane_ids": ["android", "ios", "linux", "macos", "windows", "unity", "unreal"],
                "ready_route_ids": [],
                "selected_route_ids": [],
                "selected_ready_route_ids": [],
                "partial_route_ids": [],
                "unavailable_route_ids": [],
                "lanes": [
                    {
                        "lane_id": "browser",
                        "route_ids": [],
                        "selected_route_ids": [],
                        "selected_ready_route_ids": [],
                        "adapter_contract": {
                            "contract_id": "browser_automation_contract",
                            "adapter_family": "browser_automation",
                            "status": "ready",
                            "selected_binding_status": "ready",
                            "required_tool_families": ["browser_automation", "playwright"],
                            "expected_evidence_categories": ["logs", "screenshots", "traces", "coverage", "performance"],
                            "artifact_shipping_modes": ["local_only", "connector_only"],
                        },
                    }
                ],
            },
            "artifact_transport": {
                "summary": "Artifact sync resolves to brokered sync.",
                "recommended_transport_mode": "brokered_sync",
                "ready_platform_lanes": ["browser"],
                "partial_platform_lanes": [],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native App Plan Blocked Transport Mode Demo",
            "idea": "Need dispatch blocked when the adapter contract rejects the transport mode.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/native-app-validation-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "partial"
    assert payload["transport_mode_adapter_status"] == "blocked"
    assert payload["transport_mode_supported_adapter_contract_ids"] == []
    assert payload["transport_mode_unsupported_adapter_contract_ids"] == ["browser_automation_contract"]

    artifact_shipping_plan = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "artifact-shipping-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact_shipping_plan["shipping_requirements"]["transport_mode_adapter_status"] == "blocked"
    assert artifact_shipping_plan["shipping_requirements"]["adapter_transport_mode_review_required"] is True
    shipping_targets = {item["platform"]: item for item in artifact_shipping_plan["target_lane_matrix"]}
    assert shipping_targets["browser"]["transport_mode_adapter_status"] == "blocked"
    assert shipping_targets["browser"]["ready_for_dispatch"] is False

    runner_lane_plan = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "runner-lane-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert runner_lane_plan["transport_mode_adapter_status"] == "blocked"
    assert runner_lane_plan["dispatch_requirements"]["adapter_transport_mode_review_required"] is True

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "approval-checkpoints.json").read_text(
            encoding="utf-8"
        )
    )
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_by_id["adapter_transport_mode_review"]["status"] == "blocked"
    assert checkpoint_by_id["publish_gate"]["status"] == "blocked"


def test_native_app_validation_governance_plan_route_keeps_evidence_bundle_publish_ready_false_when_runner_lanes_are_missing(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-native-app-plan-missing-runner-lane"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_native_app_validation_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Native app validation governance is blocked because no runner lane matches the detected surface.",
            "governance_status": "partial",
            "detected_platforms": ["android"],
            "governed_surface_count": 1,
            "game_engine_surface_count": 0,
            "game_engine_surface_ids": [],
            "game_engine_governance_status": "not_applicable",
            "game_engine_playable_contract_status": "not_applicable",
            "game_engine_scene_or_map_count": 0,
            "game_engine_scene_or_map_paths": [],
            "game_engine_automation_signal_count": 0,
            "game_engine_automation_signal_paths": [],
            "game_engine_screenshot_artifact_count": 0,
            "game_engine_screenshot_artifact_paths": [],
            "game_engine_normalized_results_summary_path": None,
            "game_engine_normalized_summary_count": 0,
            "game_engine_normalized_passed_count": 0,
            "game_engine_normalized_failed_count": 0,
            "game_engine_normalized_missing_count": 0,
            "game_engine_normalized_publish_ready": False,
            "game_engine_normalized_results_status": "not_applicable",
            "game_engine_publish_gate_status": "not_applicable",
            "game_engine_publish_blocker_count": 0,
            "game_engine_publish_blockers": [],
            "ready_runner_lanes": [],
            "partial_runner_lanes": [],
            "unavailable_runner_lanes": ["android", "ios", "linux", "macos", "windows", "browser", "unity", "unreal"],
            "installable_artifact_count": 1,
            "installable_artifact_paths": ["builds/android/app-release.apk"],
            "installable_artifact_extensions": [".apk"],
            "log_artifact_count": 1,
            "log_artifact_paths": ["artifacts/logs/device.log"],
            "screenshot_artifact_count": 1,
            "screenshot_artifact_paths": ["artifacts/screenshots/home.png"],
            "trace_artifact_count": 1,
            "trace_artifact_paths": ["artifacts/traces/device-trace.zip"],
            "crash_artifact_count": 1,
            "crash_artifact_paths": ["artifacts/crash/app.crash"],
            "coverage_artifact_count": 1,
            "coverage_artifact_paths": ["artifacts/coverage/lcov.info"],
            "performance_artifact_count": 1,
            "performance_artifact_paths": ["artifacts/perf/fps-benchmark.json"],
            "evidence_pipeline_status": "ready",
            "recommended_runner_lanes": [],
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": ["No ready or partial platform runner lane matches the detected app surfaces yet."],
            "recommended_fixes": ["Wire the matching Android lane before publish."],
            "notes": ["Evidence exists, but it has nowhere governed to run."],
            "platform_runners": {
                "summary": "No Android lane is ready.",
                "ready_lane_ids": [],
                "partial_lane_ids": [],
                "unavailable_lane_ids": ["android", "ios", "linux", "macos", "windows", "browser", "unity", "unreal"],
            },
            "artifact_transport": {
                "summary": "Artifact sync is ready.",
                "recommended_transport_mode": "brokered_sync",
                "ready_platform_lanes": [],
                "partial_platform_lanes": [],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native App Plan Missing Runner Demo",
            "idea": "Need evidence bundles to stay not-ready when the platform lane is missing.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/native-app-validation-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "partial"

    evidence_bundle = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "evidence-bundle-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence_bundle["publish_ready"] is False

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "approval-checkpoints.json").read_text(
            encoding="utf-8"
        )
    )
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_by_id["runner_lane_review"]["status"] == "blocked"
    assert checkpoint_by_id["publish_gate"]["status"] == "blocked"


def test_native_app_validation_governance_plan_route_stays_partial_when_only_partial_runner_lanes_exist(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-native-app-plan-partial-runner"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_native_app_validation_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Native app validation governance is partial because only a partial Android lane is available.",
            "governance_status": "partial",
            "detected_platforms": ["android"],
            "governed_surface_count": 1,
            "game_engine_surface_count": 0,
            "game_engine_surface_ids": [],
            "game_engine_governance_status": "not_applicable",
            "game_engine_playable_contract_status": "not_applicable",
            "game_engine_scene_or_map_count": 0,
            "game_engine_scene_or_map_paths": [],
            "game_engine_automation_signal_count": 0,
            "game_engine_automation_signal_paths": [],
            "game_engine_screenshot_artifact_count": 0,
            "game_engine_screenshot_artifact_paths": [],
            "game_engine_normalized_results_summary_path": None,
            "game_engine_normalized_summary_count": 0,
            "game_engine_normalized_passed_count": 0,
            "game_engine_normalized_failed_count": 0,
            "game_engine_normalized_missing_count": 0,
            "game_engine_normalized_publish_ready": False,
            "game_engine_normalized_results_status": "not_applicable",
            "game_engine_publish_gate_status": "not_applicable",
            "game_engine_publish_blocker_count": 0,
            "game_engine_publish_blockers": [],
            "ready_runner_lanes": [],
            "partial_runner_lanes": ["android"],
            "unavailable_runner_lanes": ["ios", "linux", "macos", "windows", "browser", "unity", "unreal"],
            "installable_artifact_count": 1,
            "installable_artifact_paths": ["builds/android/app-release.apk"],
            "installable_artifact_extensions": [".apk"],
            "log_artifact_count": 1,
            "log_artifact_paths": ["artifacts/logs/device.log"],
            "screenshot_artifact_count": 1,
            "screenshot_artifact_paths": ["artifacts/screenshots/home.png"],
            "trace_artifact_count": 1,
            "trace_artifact_paths": ["artifacts/traces/device-trace.zip"],
            "crash_artifact_count": 1,
            "crash_artifact_paths": ["artifacts/crash/app.crash"],
            "coverage_artifact_count": 1,
            "coverage_artifact_paths": ["artifacts/coverage/lcov.info"],
            "performance_artifact_count": 1,
            "performance_artifact_paths": ["artifacts/perf/fps-benchmark.json"],
            "evidence_pipeline_status": "ready",
            "recommended_runner_lanes": ["android"],
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": [],
            "recommended_fixes": ["Upgrade the Android lane from partial to ready before publish."],
            "notes": ["A partial runner lane should not count as publish-ready."],
            "platform_runners": {
                "summary": "Android lane is partial.",
                "ready_lane_ids": [],
                "partial_lane_ids": ["android"],
                "unavailable_lane_ids": ["ios", "linux", "macos", "windows", "browser", "unity", "unreal"],
            },
            "artifact_transport": {
                "summary": "Artifact sync is ready.",
                "recommended_transport_mode": "brokered_sync",
                "ready_platform_lanes": [],
                "partial_platform_lanes": ["android"],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Native App Plan Partial Runner Demo",
            "idea": "Partial lanes should keep native app publish readiness degraded.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/native-app-validation-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["plan_status"] == "partial"

    evidence_bundle = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "evidence-bundle-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence_bundle["publish_ready"] is False

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "native-app-validation-governance" / "approval-checkpoints.json").read_text(
            encoding="utf-8"
        )
    )
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_by_id["runner_lane_review"]["status"] == "partial"
    assert checkpoint_by_id["publish_gate"]["status"] == "partial"


def test_remote_execution_governance_summary_route_surfaces_policy_contracts_and_transport(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-remote-execution-governance"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution",
        lambda db, project: {
            "policy": {
                "enabled": True,
                "preferred_target_id": "gpu-linux",
                "required_runner_family": "external_adapter",
                "allowed_trust_levels": ["trusted"],
                "required_toolchains": ["cuda12"],
                "required_command_families": ["python", "git"],
                "required_result_formats": ["json"],
                "require_target_workspace_root": True,
                "artifact_sync_enabled": True,
                "artifact_required": True,
                "required_connector_families": ["source_control"],
                "require_session_recording": True,
                "required_repo_roots": ["/srv/work"],
                "required_path_prefixes": ["src", "artifacts"],
                "minimum_command_runtime_seconds": 900,
                "minimum_file_transfer_quota_mb": 512,
            },
                "required_runner_family": "external_adapter",
                "eligible_target_count": 1,
                "availability_diagnostics": {
                    "summary": "1 governed target is ready for brokered execution.",
                    "has_blockers": False,
                },
                "selected_target_id": "gpu-linux",
                "selected_target": {
                "id": "gpu-linux",
                "label": "GPU Linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "os_family": "linux",
            },
            "preflight_ready": True,
            "blocking_reasons": [],
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "selected_artifact_root": "/srv/work/artifacts",
                "remote_workspace_root": "/srv/work",
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "connector_contract": {
                "required_connector_families": ["source_control"],
                "available_families": ["source_control"],
                "missing_required_families": [],
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "broker_contract": {
                "allowed_trust_levels": ["trusted"],
                "required_toolchains": ["cuda12"],
                "required_command_families": ["python", "git"],
                "required_result_formats": ["json"],
                "require_session_recording": True,
                "require_target_workspace_root": True,
                "required_repo_roots": ["/srv/work"],
                "required_path_prefixes": ["src", "artifacts"],
                "minimum_command_runtime_seconds": 900,
                "minimum_file_transfer_quota_mb": 512,
                "target_gpu": "RTX 4090",
                "target_toolchains": ["python3.11", "cuda12"],
                "target_command_families": ["python", "git"],
                "target_result_formats": ["json"],
                "session_recording_enabled": True,
                "target_command_runtime_seconds": 1200,
                "target_file_transfer_quota_mb": 1024,
                "target_repo_roots": ["/srv/work"],
                "target_path_prefixes": ["src", "artifacts"],
                "preflight_ready": True,
                "blocking_reasons": [],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_device_broker_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Broker sees one ready target.",
            "preflight_ready": True,
            "selected_target_id": "gpu-linux",
            "recommended_target_ids": ["gpu-linux"],
            "blocking_reasons": [],
            "ready_target_count": 1,
            "capability_index": {
                "target_count": 1,
                "ready_target_count": 1,
                "toolchain_counts": {"cuda12": 1},
                "command_family_counts": {"python": 1, "git": 1},
                "result_format_counts": {"json": 1},
                "gpu_counts": {"RTX 4090": 1},
                "trust_level_counts": {"trusted": 1},
                "connector_family_counts": {"source_control": 1},
                "targets": [
                    {
                        "target_id": "gpu-linux",
                        "label": "GPU Linux",
                        "transport": "tailscale_ssh",
                        "host": "gpu-linux.tailnet.ts.net",
                        "os_family": "linux",
                        "architecture": "x86_64",
                        "gpu": "RTX 4090",
                        "trust_level": "trusted",
                        "workspace_root": "/srv/work",
                        "toolchains": ["python3.11", "cuda12"],
                        "command_families": ["python", "git"],
                        "result_formats": ["json"],
                        "connector_families": ["source_control"],
                        "artifact_roots": ["/srv/work/artifacts"],
                        "allowed_repo_roots": ["/srv/work"],
                        "allowed_path_prefixes": ["src", "artifacts"],
                        "session_recording_enabled": True,
                        "probe_status": "ready",
                        "ready": True,
                    }
                ],
            },
            "remote_execution": {"policy": {"enabled": True}, "required_runner_family": "external_adapter"},
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Artifact transport is ready.",
            "selected_target_id": "gpu-linux",
            "preflight_ready": True,
            "sync_enabled": True,
            "recommended_transport_mode": "remote_artifact_root",
            "blocking_reasons": [],
            "ready_route_count": 1,
            "selected_ready_route_count": 1,
            "partial_route_count": 1,
            "ready_route_ids": ["tailscale_ssh"],
            "selected_ready_route_ids": ["tailscale_ssh"],
            "partial_route_ids": ["plain_ssh"],
            "ready_platform_lanes": ["linux"],
            "partial_platform_lanes": [],
            "selected_adapter_shipping_modes": [
                "workspace_relative_sync",
                "remote_artifact_root",
                "brokered_sync",
            ],
            "common_adapter_shipping_modes": [
                "workspace_relative_sync",
                "remote_artifact_root",
                "brokered_sync",
            ],
            "transport_mode_adapter_status": "ready",
            "transport_mode_supported_adapter_contract_ids": ["linux_cuda_contract"],
            "transport_mode_unsupported_adapter_contract_ids": [],
            "transport_mode_undeclared_adapter_contract_ids": [],
            "notes": ["Remote artifact root is selected."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
            "artifact_contract": {"sync_enabled": True, "required": True, "selected_artifact_root": "/srv/work/artifacts", "remote_workspace_root": "/srv/work", "preflight_ready": True, "blocking_reasons": []},
            "connector_contract": {"available_families": ["source_control"], "available_connector_count": 1, "preflight_ready": True, "blocking_reasons": []},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Linux lane is ready.",
            "selected_target_id": "gpu-linux",
            "lane_count": 3,
            "ready_lane_count": 1,
            "partial_lane_count": 1,
            "unavailable_lane_count": 1,
            "ready_route_count": 1,
            "selected_ready_route_count": 1,
            "partial_route_count": 1,
            "ready_lane_ids": ["linux"],
            "ready_route_ids": ["tailscale_ssh"],
            "partial_lane_ids": ["browser"],
            "partial_route_ids": ["plain_ssh"],
            "unavailable_lane_ids": ["windows"],
            "selected_ready_route_ids": ["tailscale_ssh"],
            "lanes": [
                {"lane_id": "linux", "title": "Linux Runner", "status": "ready", "summary": "ready", "target_ids": ["gpu-linux"], "target_count": 1, "selected_target_ids": ["gpu-linux"], "os_families": ["linux"], "toolchains": ["cuda12"], "command_families": ["python", "git"], "route_ids": ["tailscale_ssh"], "ready_route_ids": ["tailscale_ssh"], "selected_route_ids": ["tailscale_ssh"], "selected_ready_route_ids": ["tailscale_ssh"], "recommended_commands": ["python -m pytest"], "adapter_contract": {"contract_id": "linux_cuda_contract", "adapter_family": "linux_cuda", "status": "ready", "selected_binding_status": "ready", "required_tool_families": ["python", "cuda"], "required_command_families": ["python", "git"], "expected_result_formats": ["json"], "expected_evidence_categories": ["logs", "coverage"]}, "notes": []},
                {"lane_id": "browser", "title": "Browser Runner", "status": "partial", "summary": "partial", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": ["playwright"], "command_families": ["browser"], "route_ids": ["plain_ssh"], "ready_route_ids": [], "selected_route_ids": [], "selected_ready_route_ids": [], "recommended_commands": ["playwright test"], "notes": []},
                {"lane_id": "windows", "title": "Windows Runner", "status": "unavailable", "summary": "unavailable", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": [], "command_families": [], "route_ids": [], "ready_route_ids": [], "selected_route_ids": [], "selected_ready_route_ids": [], "recommended_commands": ["powershell -File .\\scripts\\validate.ps1"], "notes": []},
            ],
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Governance Demo",
            "idea": "Need a governed remote execution lane.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/remote-execution-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["governance_status"] == "ready"
    assert payload["policy_enabled"] is True
    assert payload["selected_target_id"] == "gpu-linux"
    assert payload["selected_target_probe_status"] == "unknown"
    assert payload["availability_diagnostics"]["summary"]
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["selected_transport"] == "tailscale_ssh"
    assert payload["selected_os_family"] == "linux"
    assert payload["required_runner_family"] == "external_adapter"
    assert payload["transport_status"] == "ready"
    assert payload["broker_contract_status"] == "ready"
    assert payload["artifact_contract_status"] == "ready"
    assert payload["connector_contract_status"] == "ready"
    assert payload["session_recording_status"] == "ready"
    assert payload["path_sandbox_status"] == "ready"
    assert payload["result_contract_status"] == "ready"
    assert payload["quota_status"] == "ready"
    assert payload["ready_candidate_count"] == 0
    assert payload["ready_candidate_ids"] == []
    assert payload["ready_target_count"] == 1
    assert payload["ready_lane_ids"] == ["linux"]
    assert payload["ready_route_count"] == 1
    assert payload["ready_route_ids"] == ["tailscale_ssh"]
    assert payload["selected_ready_lane_count"] == 1
    assert payload["selected_ready_lane_ids"] == ["linux"]
    assert payload["selected_ready_route_count"] == 1
    assert payload["selected_ready_route_ids"] == ["tailscale_ssh"]
    assert payload["partial_route_count"] == 1
    assert payload["partial_route_ids"] == ["plain_ssh"]
    assert payload["allowed_trust_levels"] == ["trusted"]
    assert payload["required_repo_roots"] == ["/srv/work"]
    assert payload["required_path_prefixes"] == ["src", "artifacts"]
    assert payload["required_result_formats"] == ["json"]
    assert payload["required_command_families"] == ["python", "git"]
    assert payload["required_toolchains"] == ["cuda12"]
    assert payload["adapter_contract_status"] == "ready"
    assert payload["adapter_contract_count"] == 1
    assert payload["selected_adapter_contract_count"] == 1
    assert payload["selected_adapter_contract_ids"] == ["linux_cuda_contract"]
    assert payload["selected_adapter_shipping_modes"] == [
        "workspace_relative_sync",
        "remote_artifact_root",
        "brokered_sync",
    ]
    assert payload["common_adapter_shipping_modes"] == [
        "workspace_relative_sync",
        "remote_artifact_root",
        "brokered_sync",
    ]
    assert payload["transport_mode_adapter_status"] == "ready"
    assert payload["transport_mode_supported_adapter_contract_ids"] == ["linux_cuda_contract"]
    assert payload["transport_mode_unsupported_adapter_contract_ids"] == []
    assert payload["transport_mode_undeclared_adapter_contract_ids"] == []
    assert payload["required_tool_adapter_families"] == ["python", "cuda"]
    assert payload["adapter_expected_result_formats"] == ["json"]
    assert payload["adapter_required_command_families"] == ["python", "git"]
    assert payload["expected_evidence_categories"] == ["logs", "coverage"]
    assert payload["observed_evidence_categories"] == []
    assert payload["normalized_summary_artifact"] == "artifacts/remote-execution-governance/normalized-execution-summary.json"
    assert payload["session_recording_runtime_manifest_count"] == 0
    assert payload["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]
    assert payload["produced_session_recording_artifact_paths"] == []
    assert payload["missing_session_recording_artifact_paths"] == []
    assert payload["remote_session_recording_artifact_paths"] == [
        "/srv/work/artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]
    assert payload["minimum_command_runtime_seconds"] == 900
    assert payload["minimum_file_transfer_quota_mb"] == 512
    assert payload["blocking_reasons"] == []


def test_remote_execution_governance_summary_prefers_runtime_recording_delivery_signal(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-remote-execution-governance-runtime-gap"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution",
        lambda db, project: {
            "policy": {
                "enabled": True,
                "preferred_target_id": "gpu-linux",
                "required_runner_family": "external_adapter",
                "allowed_trust_levels": ["trusted"],
                "required_toolchains": ["cuda12"],
                "required_command_families": ["python", "git"],
                "required_result_formats": ["json"],
                "require_target_workspace_root": True,
                "artifact_sync_enabled": True,
                "artifact_required": True,
                "required_connector_families": ["source_control"],
                "require_session_recording": True,
                "required_repo_roots": ["/srv/work"],
                "required_path_prefixes": ["src", "artifacts"],
            },
            "required_runner_family": "external_adapter",
            "eligible_target_count": 1,
            "selected_target_id": "gpu-linux",
            "selected_target": {
                "id": "gpu-linux",
                "label": "GPU Linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "os_family": "linux",
            },
            "preflight_ready": True,
            "blocking_reasons": [],
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "selected_artifact_root": "/srv/work/artifacts",
                "remote_workspace_root": "/srv/work",
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "connector_contract": {
                "required_connector_families": ["source_control"],
                "available_families": ["source_control"],
                "missing_required_families": [],
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "broker_contract": {
                "allowed_trust_levels": ["trusted"],
                "required_toolchains": ["cuda12"],
                "required_command_families": ["python", "git"],
                "required_result_formats": ["json"],
                "require_session_recording": True,
                "require_target_workspace_root": True,
                "required_repo_roots": ["/srv/work"],
                "required_path_prefixes": ["src", "artifacts"],
                "target_gpu": "RTX 4090",
                "target_toolchains": ["python3.11", "cuda12"],
                "target_command_families": ["python", "git"],
                "target_result_formats": ["json"],
                "session_recording_enabled": True,
                "target_command_runtime_seconds": 1200,
                "target_file_transfer_quota_mb": 1024,
                "target_repo_roots": ["/srv/work"],
                "target_path_prefixes": ["src", "artifacts"],
                "preflight_ready": True,
                "blocking_reasons": [],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_device_broker_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Broker sees one ready target.",
            "preflight_ready": True,
            "selected_target_id": "gpu-linux",
            "recommended_target_ids": ["gpu-linux"],
            "blocking_reasons": [],
            "ready_target_count": 1,
            "capability_index": {
                "target_count": 1,
                "ready_target_count": 1,
                "toolchain_counts": {"cuda12": 1},
                "command_family_counts": {"python": 1, "git": 1},
                "result_format_counts": {"json": 1},
                "gpu_counts": {"RTX 4090": 1},
                "trust_level_counts": {"trusted": 1},
                "connector_family_counts": {"source_control": 1},
                "targets": [
                    {
                        "target_id": "gpu-linux",
                        "label": "GPU Linux",
                        "transport": "tailscale_ssh",
                        "host": "gpu-linux.tailnet.ts.net",
                        "os_family": "linux",
                        "architecture": "x86_64",
                        "gpu": "RTX 4090",
                        "trust_level": "trusted",
                        "workspace_root": "/srv/work",
                        "toolchains": ["python3.11", "cuda12"],
                        "command_families": ["python", "git"],
                        "result_formats": ["json"],
                        "connector_families": ["source_control"],
                        "artifact_roots": ["/srv/work/artifacts"],
                        "allowed_repo_roots": ["/srv/work"],
                        "allowed_path_prefixes": ["src", "artifacts"],
                        "session_recording_enabled": True,
                        "probe_status": "ready",
                        "ready": True,
                    }
                ],
            },
            "remote_execution": {"policy": {"enabled": True}, "required_runner_family": "external_adapter"},
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Artifact transport found a recording gap after execution.",
            "selected_target_id": "gpu-linux",
            "preflight_ready": True,
            "sync_enabled": True,
            "recommended_transport_mode": "blocked",
            "session_recording_status": "partial",
            "session_recording_runtime_manifest_count": 1,
            "session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
            ],
            "produced_session_recording_artifact_paths": [],
            "missing_session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
            ],
            "remote_session_recording_artifact_paths": [
                "/srv/work/artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
            ],
            "blocking_reasons": ["session_recording_artifact_missing_after_remote_execution"],
            "ready_platform_lanes": ["linux"],
            "partial_platform_lanes": [],
            "notes": ["Runtime manifest says the cast file never made it home."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
            "artifact_contract": {"sync_enabled": True, "required": True, "selected_artifact_root": "/srv/work/artifacts", "remote_workspace_root": "/srv/work", "preflight_ready": True, "blocking_reasons": []},
            "connector_contract": {"available_families": ["source_control"], "available_connector_count": 1, "preflight_ready": True, "blocking_reasons": []},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Linux lane is ready.",
            "selected_target_id": "gpu-linux",
            "lane_count": 1,
            "ready_lane_count": 1,
            "partial_lane_count": 0,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["linux"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": [],
            "lanes": [
                {"lane_id": "linux", "title": "Linux Runner", "status": "ready", "summary": "ready", "target_ids": ["gpu-linux"], "target_count": 1, "selected_target_ids": ["gpu-linux"], "os_families": ["linux"], "toolchains": ["cuda12"], "command_families": ["python", "git"], "recommended_commands": ["python -m pytest"], "notes": []},
            ],
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Governance Runtime Gap Demo",
            "idea": "Need post-run recording truth to override preflight optimism.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/remote-execution-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "partial"
    assert payload["session_recording_status"] == "partial"
    assert payload["session_recording_runtime_manifest_count"] == 1
    assert payload["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]
    assert payload["produced_session_recording_artifact_paths"] == []
    assert payload["missing_session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]
    assert (
        "Remote execution recorded a brokered run, but the session-recording artifact is still missing from the workspace."
        in payload["blocking_reasons"]
    )
    assert (
        "Materialize the missing session-recording artifact inside the workspace before treating the brokered run as fully auditable."
        in payload["recommended_fixes"]
    )


def test_remote_execution_governance_summary_becomes_partial_when_adapter_transport_mode_is_blocked(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-remote-execution-transport-mode-blocked"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution",
        lambda db, project: {
            "policy": {
                "enabled": True,
                "preferred_target_id": "gpu-linux",
                "required_runner_family": "external_adapter",
                "allowed_trust_levels": ["trusted"],
                "required_toolchains": ["cuda12"],
                "required_command_families": ["python", "git"],
                "required_result_formats": ["json"],
                "require_target_workspace_root": True,
                "artifact_sync_enabled": True,
                "artifact_required": True,
                "required_connector_families": ["source_control"],
                "require_session_recording": True,
                "required_repo_roots": ["/srv/work"],
                "required_path_prefixes": ["src", "artifacts"],
            },
            "required_runner_family": "external_adapter",
            "eligible_target_count": 1,
            "selected_target_id": "gpu-linux",
            "selected_target": {
                "id": "gpu-linux",
                "label": "GPU Linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "os_family": "linux",
            },
            "preflight_ready": True,
            "blocking_reasons": [],
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "selected_artifact_root": "/srv/work/artifacts",
                "remote_workspace_root": "/srv/work",
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "connector_contract": {
                "required_connector_families": ["source_control"],
                "available_families": ["source_control"],
                "missing_required_families": [],
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "broker_contract": {
                "allowed_trust_levels": ["trusted"],
                "required_toolchains": ["cuda12"],
                "required_command_families": ["python", "git"],
                "required_result_formats": ["json"],
                "require_session_recording": True,
                "require_target_workspace_root": True,
                "required_repo_roots": ["/srv/work"],
                "required_path_prefixes": ["src", "artifacts"],
                "target_gpu": "RTX 4090",
                "target_toolchains": ["python3.11", "cuda12"],
                "target_command_families": ["python", "git"],
                "target_result_formats": ["json"],
                "session_recording_enabled": True,
                "target_command_runtime_seconds": 1200,
                "target_file_transfer_quota_mb": 1024,
                "target_repo_roots": ["/srv/work"],
                "target_path_prefixes": ["src", "artifacts"],
                "preflight_ready": True,
                "blocking_reasons": [],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_device_broker_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Broker sees one ready target.",
            "preflight_ready": True,
            "selected_target_id": "gpu-linux",
            "recommended_target_ids": ["gpu-linux"],
            "blocking_reasons": [],
            "ready_target_count": 1,
            "capability_index": {
                "target_count": 1,
                "ready_target_count": 1,
                "toolchain_counts": {"cuda12": 1},
                "command_family_counts": {"python": 1, "git": 1},
                "result_format_counts": {"json": 1},
                "gpu_counts": {"RTX 4090": 1},
                "trust_level_counts": {"trusted": 1},
                "connector_family_counts": {"source_control": 1},
                "targets": [
                    {
                        "target_id": "gpu-linux",
                        "label": "GPU Linux",
                        "transport": "tailscale_ssh",
                        "host": "gpu-linux.tailnet.ts.net",
                        "os_family": "linux",
                        "architecture": "x86_64",
                        "gpu": "RTX 4090",
                        "trust_level": "trusted",
                        "workspace_root": "/srv/work",
                        "toolchains": ["python3.11", "cuda12"],
                        "command_families": ["python", "git"],
                        "result_formats": ["json"],
                        "connector_families": ["source_control"],
                        "artifact_roots": ["/srv/work/artifacts"],
                        "allowed_repo_roots": ["/srv/work"],
                        "allowed_path_prefixes": ["src", "artifacts"],
                        "session_recording_enabled": True,
                        "probe_status": "ready",
                        "ready": True,
                    }
                ],
            },
            "remote_execution": {"policy": {"enabled": True}, "required_runner_family": "external_adapter"},
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Artifact transport is ready, but the selected adapter refuses that shipping mode.",
            "selected_target_id": "gpu-linux",
            "preflight_ready": True,
            "sync_enabled": True,
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": [],
            "ready_route_count": 1,
            "selected_ready_route_count": 1,
            "partial_route_count": 0,
            "ready_route_ids": ["tailscale_ssh"],
            "selected_ready_route_ids": ["tailscale_ssh"],
            "partial_route_ids": [],
            "ready_platform_lanes": ["linux"],
            "partial_platform_lanes": [],
            "selected_adapter_shipping_modes": ["local_only"],
            "common_adapter_shipping_modes": ["local_only"],
            "transport_mode_adapter_status": "blocked",
            "transport_mode_supported_adapter_contract_ids": [],
            "transport_mode_unsupported_adapter_contract_ids": ["linux_host_runtime"],
            "transport_mode_undeclared_adapter_contract_ids": [],
            "notes": ["The selected adapter only permits local-only artifact delivery."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "selected_artifact_root": "/srv/work/artifacts",
                "remote_workspace_root": "/srv/work",
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "connector_contract": {
                "available_families": ["source_control"],
                "available_connector_count": 1,
                "preflight_ready": True,
                "blocking_reasons": [],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Linux lane is ready.",
            "selected_target_id": "gpu-linux",
            "lane_count": 1,
            "ready_lane_count": 1,
            "partial_lane_count": 0,
            "unavailable_lane_count": 0,
            "ready_route_count": 1,
            "selected_ready_route_count": 1,
            "partial_route_count": 0,
            "ready_lane_ids": ["linux"],
            "ready_route_ids": ["tailscale_ssh"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": [],
            "selected_ready_lane_ids": ["linux"],
            "selected_ready_route_ids": ["tailscale_ssh"],
            "lanes": [
                {
                    "lane_id": "linux",
                    "title": "Linux Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["gpu-linux"],
                    "target_count": 1,
                    "selected_target_ids": ["gpu-linux"],
                    "os_families": ["linux"],
                    "toolchains": ["cuda12"],
                    "command_families": ["python", "git"],
                    "route_ids": ["tailscale_ssh"],
                    "ready_route_ids": ["tailscale_ssh"],
                    "selected_route_ids": ["tailscale_ssh"],
                    "selected_ready_route_ids": ["tailscale_ssh"],
                    "recommended_commands": ["python -m pytest"],
                    "adapter_contract": {
                        "contract_id": "linux_host_runtime",
                        "adapter_family": "linux_host",
                        "status": "ready",
                        "selected_binding_status": "ready",
                        "required_tool_families": ["python", "shell"],
                        "required_command_families": ["python", "git"],
                        "expected_result_formats": ["json"],
                        "expected_evidence_categories": ["logs", "coverage"],
                        "artifact_shipping_modes": ["local_only"],
                    },
                    "notes": [],
                }
            ],
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Transport Mode Governance Demo",
            "idea": "Need summary governance to degrade when adapter shipping modes reject the resolved transport.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/remote-execution-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "partial"
    assert payload["transport_status"] == "ready"
    assert payload["transport_mode_adapter_status"] == "blocked"
    assert payload["selected_adapter_shipping_modes"] == ["local_only"]
    assert payload["common_adapter_shipping_modes"] == ["local_only"]
    assert payload["transport_mode_supported_adapter_contract_ids"] == []
    assert payload["transport_mode_unsupported_adapter_contract_ids"] == ["linux_host_runtime"]
    assert payload["transport_mode_undeclared_adapter_contract_ids"] == []
    assert (
        "Remote execution transport mode is not supported by the selected adapter contracts."
        in payload["blocking_reasons"]
    )
    assert (
        "Declare explicit artifact shipping modes on the selected adapter contracts so the broker can prove the current transport path is actually allowed."
        in payload["recommended_fixes"]
    )


def test_remote_execution_governance_plan_route_generates_policy_contract_and_quota_manifests(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-remote-execution-plan"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_remote_execution_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Remote execution governance is ready.",
            "governance_status": "ready",
            "policy_enabled": True,
            "selected_target_id": "gpu-linux",
            "selected_target_probe_status": "ready",
            "availability_diagnostics": {
                "candidate_count": 1,
                "eligible_target_count": 1,
                "ready_candidate_count": 1,
                "summary": "1 ready candidate remains after policy filtering.",
            },
            "selected_target_requirement_gaps": {},
            "selected_target_rejected_reasons": [],
            "selected_transport": "tailscale_ssh",
            "selected_os_family": "linux",
            "required_runner_family": "external_adapter",
            "transport_status": "ready",
            "broker_contract_status": "ready",
            "artifact_contract_status": "ready",
            "connector_contract_status": "ready",
            "session_recording_status": "ready",
            "path_sandbox_status": "ready",
            "result_contract_status": "ready",
            "quota_status": "ready",
            "eligible_target_count": 1,
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-linux"],
            "ready_target_count": 1,
            "ready_lane_count": 1,
            "ready_lane_ids": ["linux"],
            "allowed_trust_levels": ["trusted"],
            "required_repo_roots": ["/srv/work"],
            "required_path_prefixes": ["src", "artifacts"],
            "required_result_formats": ["json"],
            "effective_required_result_formats": ["json"],
            "required_command_families": ["python", "git"],
            "effective_required_command_families": ["python", "git"],
            "required_toolchains": ["cuda12"],
            "adapter_contract_status": "ready",
            "adapter_contract_count": 1,
            "selected_adapter_contract_count": 1,
            "selected_adapter_contract_ids": ["linux_cuda_contract"],
            "selected_adapter_shipping_modes": ["brokered_sync", "remote_artifact_root"],
            "common_adapter_shipping_modes": ["brokered_sync", "remote_artifact_root"],
            "transport_mode_adapter_status": "ready",
            "transport_mode_supported_adapter_contract_ids": ["linux_cuda_contract"],
            "transport_mode_unsupported_adapter_contract_ids": [],
            "transport_mode_undeclared_adapter_contract_ids": [],
            "ready_adapter_contract_ids": ["linux_cuda_contract"],
            "partial_adapter_contract_ids": [],
            "unavailable_adapter_contract_ids": [],
            "required_tool_adapter_family_count": 2,
            "required_tool_adapter_families": ["python", "cuda"],
            "required_adapter_evidence_categories": ["logs", "coverage"],
            "optional_adapter_evidence_categories": [],
            "adapter_expected_result_formats": ["json"],
            "adapter_required_command_families": ["python", "git"],
            "adapter_contracts": [
                {
                    "contract_id": "linux_cuda_contract",
                    "adapter_family": "linux_cuda",
                    "status": "ready",
                    "selected_binding_status": "ready",
                    "required_tool_families": ["python", "cuda"],
                    "required_command_families": ["python", "git"],
                    "expected_result_formats": ["json"],
                    "expected_evidence_categories": ["logs", "coverage"],
                }
            ],
            "expected_evidence_categories": ["logs", "coverage"],
            "observed_evidence_categories": ["coverage"],
            "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
            "session_recording_runtime_manifest_count": 0,
            "produced_session_recording_artifact_paths": [],
            "missing_session_recording_artifact_paths": [],
            "minimum_command_runtime_seconds": 900,
            "minimum_file_transfer_quota_mb": 512,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Remote execution policy is fully satisfied."],
            "device_broker": {"summary": "ready"},
            "artifact_transport": {"summary": "ready"},
            "platform_runners": {"summary": "ready"},
        },
    )
    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution",
        lambda db, project: {
            "policy": {
                "enabled": True,
                "preferred_target_id": "gpu-linux",
                "required_tags": ["gpu"],
                "required_capabilities": ["python", "cuda"],
                "allowed_trust_levels": ["trusted"],
                "allowed_transports": ["tailscale_ssh"],
                "allowed_os_families": ["linux"],
                "require_write_access": True,
                "fallback_to_local": False,
                "require_target_workspace_root": True,
                "artifact_sync_enabled": True,
                "artifact_required": True,
                "artifact_path_allowlist": ["artifacts/model.onnx"],
                "required_connector_families": ["source_control"],
                "allow_host_integrated_connectors": True,
                "require_connector_authority": True,
                "require_probe_ready": True,
                "require_session_recording": True,
                "required_repo_roots": ["/srv/work"],
                "required_path_prefixes": ["src", "artifacts"],
                "required_result_formats": ["json"],
                "required_command_families": ["python", "git"],
                "required_toolchains": ["cuda12"],
                "minimum_command_runtime_seconds": 900,
                "minimum_file_transfer_quota_mb": 512,
            },
            "selected_target": {
                "id": "gpu-linux",
                "label": "GPU Linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "os_family": "linux",
            },
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "selected_artifact_root": "/srv/work/artifacts",
                "remote_workspace_root": "/srv/work",
                "preflight_ready": True,
            },
            "connector_contract": {
                "required_connector_families": ["source_control"],
                "available_families": ["source_control"],
                "missing_required_families": [],
                "preflight_ready": True,
            },
            "broker_contract": {
                "require_session_recording": True,
                "target_gpu": "RTX 4090",
                "target_toolchains": ["python3.11", "cuda12"],
                "target_command_families": ["python", "git"],
                "target_result_formats": ["json"],
                "session_recording_enabled": True,
                "target_command_runtime_seconds": 1200,
                "target_file_transfer_quota_mb": 1024,
                "target_repo_roots": ["/srv/work"],
                "target_path_prefixes": ["src", "artifacts"],
                "preflight_ready": True,
            },
            "result_contract": {
                "adapter_contract_ids": ["linux_cuda_contract"],
                "adapter_required_command_families": ["python", "git"],
                "adapter_expected_result_formats": ["json"],
                "adapter_required_tool_families": ["python", "cuda"],
                "missing_required_result_formats": [],
                "missing_required_command_families": [],
                "missing_required_toolchains": [],
                "expected_evidence_categories": ["logs", "coverage"],
                "observed_evidence_categories": ["coverage"],
                "evidence_category_paths": {"coverage": ["artifacts/coverage/run.json"]},
                "validation_evidence_targets": ["artifacts/coverage/run.json"],
                "artifact_paths": ["artifacts/model.onnx"],
                "execution_entrypoints": ["python -m pytest"],
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "preflight_ready": True,
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Plan Demo",
            "idea": "Need governed remote execution manifests.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    plan = client.post(f"/api/projects/{project_id}/remote-execution-governance/plan")
    assert plan.status_code == 200, plan.text
    payload = plan.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["selected_target_id"] == "gpu-linux"
    assert payload["selected_target_probe_status"] == "ready"
    assert payload["availability_diagnostics"]["candidate_count"] == 1
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["selected_transport"] == "tailscale_ssh"
    assert payload["required_runner_family"] == "external_adapter"
    assert payload["manifest_root"] == "artifacts/remote-execution-governance"
    assert payload["execution_policy_path"] == "artifacts/remote-execution-governance/execution-policy.json"
    assert payload["broker_contract_path"] == "artifacts/remote-execution-governance/broker-contract.json"
    assert payload["artifact_contract_path"] == "artifacts/remote-execution-governance/artifact-contract.json"
    assert payload["connector_contract_path"] == "artifacts/remote-execution-governance/connector-contract.json"
    assert payload["adapter_contract_path"] == "artifacts/remote-execution-governance/adapter-contracts.json"
    assert payload["path_sandbox_plan_path"] == "artifacts/remote-execution-governance/path-sandbox-plan.json"
    assert payload["result_contract_path"] == "artifacts/remote-execution-governance/result-contract.json"
    assert payload["session_recording_plan_path"] == "artifacts/remote-execution-governance/session-recording-plan.json"
    assert payload["quota_plan_path"] == "artifacts/remote-execution-governance/quota-plan.json"
    assert payload["approval_checkpoint_path"] == "artifacts/remote-execution-governance/approval-checkpoints.json"
    assert payload["adapter_contract_status"] == "ready"
    assert payload["adapter_contract_count"] == 1
    assert payload["selected_adapter_contract_ids"] == ["linux_cuda_contract"]
    assert payload["selected_adapter_shipping_modes"] == ["brokered_sync", "remote_artifact_root"]
    assert payload["common_adapter_shipping_modes"] == ["brokered_sync", "remote_artifact_root"]
    assert payload["transport_mode_adapter_status"] == "ready"
    assert payload["transport_mode_supported_adapter_contract_ids"] == ["linux_cuda_contract"]
    assert payload["transport_mode_unsupported_adapter_contract_ids"] == []
    assert payload["transport_mode_undeclared_adapter_contract_ids"] == []
    assert payload["session_recording_runtime_manifest_count"] == 0
    assert payload["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]
    assert payload["produced_session_recording_artifact_paths"] == []
    assert payload["missing_session_recording_artifact_paths"] == []
    assert payload["remote_session_recording_artifact_paths"] == [
        "/srv/work/artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]

    assert (workspace / "artifacts" / "remote-execution-governance" / "execution-policy.json").exists()
    assert (workspace / "artifacts" / "remote-execution-governance" / "broker-contract.json").exists()
    assert (workspace / "artifacts" / "remote-execution-governance" / "artifact-contract.json").exists()
    assert (workspace / "artifacts" / "remote-execution-governance" / "connector-contract.json").exists()
    assert (workspace / "artifacts" / "remote-execution-governance" / "adapter-contracts.json").exists()
    assert (workspace / "artifacts" / "remote-execution-governance" / "path-sandbox-plan.json").exists()
    assert (workspace / "artifacts" / "remote-execution-governance" / "result-contract.json").exists()
    assert (workspace / "artifacts" / "remote-execution-governance" / "session-recording-plan.json").exists()
    assert (workspace / "artifacts" / "remote-execution-governance" / "quota-plan.json").exists()
    assert (workspace / "artifacts" / "remote-execution-governance" / "approval-checkpoints.json").exists()

    execution_policy = json.loads((workspace / "artifacts" / "remote-execution-governance" / "execution-policy.json").read_text(encoding="utf-8"))
    assert execution_policy["preferred_target_id"] == "gpu-linux"
    assert execution_policy["availability_diagnostics"]["candidate_count"] == 1
    assert execution_policy["selected_target_requirement_gaps"] == {}
    assert execution_policy["selected_target_rejected_reasons"] == []
    assert execution_policy["required_tags"] == ["gpu"]
    assert execution_policy["required_capabilities"] == ["python", "cuda"]
    assert execution_policy["allowed_transports"] == ["tailscale_ssh"]
    assert execution_policy["allowed_os_families"] == ["linux"]
    assert execution_policy["artifact_path_allowlist"] == ["artifacts/model.onnx"]
    assert execution_policy["required_connector_families"] == ["source_control"]
    assert execution_policy["require_connector_authority"] is True
    assert execution_policy["require_probe_ready"] is True
    assert execution_policy["minimum_command_runtime_seconds"] == 900
    assert execution_policy["minimum_file_transfer_quota_mb"] == 512

    broker_contract = json.loads((workspace / "artifacts" / "remote-execution-governance" / "broker-contract.json").read_text(encoding="utf-8"))
    assert broker_contract["selected_target_probe_status"] == "ready"
    assert broker_contract["availability_diagnostics"]["candidate_count"] == 1
    assert broker_contract["selected_target_requirement_gaps"] == {}
    assert broker_contract["selected_target_rejected_reasons"] == []
    assert broker_contract["target_repo_roots"] == ["/srv/work"]
    assert broker_contract["target_path_prefixes"] == ["src", "artifacts"]
    assert broker_contract["target_command_runtime_seconds"] == 1200
    assert broker_contract["target_file_transfer_quota_mb"] == 1024
    assert broker_contract["session_recording_enabled"] is True

    adapter_contracts = json.loads((workspace / "artifacts" / "remote-execution-governance" / "adapter-contracts.json").read_text(encoding="utf-8"))
    assert adapter_contracts["adapter_contract_status"] == "ready"
    assert adapter_contracts["selected_adapter_contract_ids"] == ["linux_cuda_contract"]
    assert adapter_contracts["selected_adapter_shipping_modes"] == ["brokered_sync", "remote_artifact_root"]
    assert adapter_contracts["transport_mode_adapter_status"] == "ready"
    assert adapter_contracts["required_tool_adapter_families"] == ["python", "cuda"]

    result_contract = json.loads((workspace / "artifacts" / "remote-execution-governance" / "result-contract.json").read_text(encoding="utf-8"))
    assert result_contract["availability_diagnostics"]["candidate_count"] == 1
    assert result_contract["selected_target_requirement_gaps"] == {}
    assert result_contract["selected_target_rejected_reasons"] == []
    assert result_contract["expected_evidence_categories"] == ["logs", "coverage"]
    assert result_contract["adapter_contract_ids"] == ["linux_cuda_contract"]
    assert result_contract["adapter_required_tool_families"] == ["python", "cuda"]
    assert result_contract["observed_evidence_categories"] == ["coverage"]
    assert result_contract["normalized_summary_artifact"] == "artifacts/remote-execution-governance/normalized-execution-summary.json"
    assert result_contract["validation_evidence_targets"] == ["artifacts/coverage/run.json"]
    assert result_contract["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]
    assert result_contract["produced_session_recording_artifact_paths"] == []
    assert result_contract["missing_session_recording_artifact_paths"] == []
    assert result_contract["remote_session_recording_artifact_paths"] == [
        "/srv/work/artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]

    session_recording_plan = json.loads(
        (workspace / "artifacts" / "remote-execution-governance" / "session-recording-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert session_recording_plan["availability_diagnostics"]["candidate_count"] == 1
    assert session_recording_plan["selected_target_requirement_gaps"] == {}
    assert session_recording_plan["selected_target_rejected_reasons"] == []
    assert session_recording_plan["artifact_format"] == "asciinema_cast"
    assert session_recording_plan["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]
    assert session_recording_plan["produced_session_recording_artifact_paths"] == []
    assert session_recording_plan["missing_session_recording_artifact_paths"] == []
    assert session_recording_plan["remote_session_recording_artifact_paths"] == [
        "/srv/work/artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]

    quota_plan = json.loads((workspace / "artifacts" / "remote-execution-governance" / "quota-plan.json").read_text(encoding="utf-8"))
    assert quota_plan["availability_diagnostics"]["candidate_count"] == 1
    assert quota_plan["selected_target_requirement_gaps"] == {}
    assert quota_plan["selected_target_rejected_reasons"] == []
    assert quota_plan["minimum_command_runtime_seconds"] == 900
    assert quota_plan["minimum_file_transfer_quota_mb"] == 512
    assert quota_plan["target_command_runtime_seconds"] == 1200
    assert quota_plan["target_file_transfer_quota_mb"] == 1024

    approval_checkpoints = json.loads((workspace / "artifacts" / "remote-execution-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    checkpoint_ids = [item["checkpoint_id"] for item in approval_checkpoints["checkpoints"]]
    assert "adapter_contract_review" in checkpoint_ids
    assert "adapter_transport_mode_review" in checkpoint_ids
    assert "result_contract_review" in checkpoint_ids


def test_remote_execution_governance_plan_route_does_not_report_ready_when_transport_or_contract_statuses_are_blocked(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-remote-execution-plan-status-guard"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.build_remote_execution_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Remote execution governance is partial for the selected target.",
            "governance_status": "partial",
            "policy_enabled": True,
            "selected_target_id": "gpu-linux",
            "selected_target_probe_status": "ready",
            "selected_transport": "tailscale_ssh",
            "selected_os_family": "linux",
            "required_runner_family": "external_adapter",
            "transport_status": "blocked",
            "broker_contract_status": "ready",
            "artifact_contract_status": "blocked",
            "connector_contract_status": "blocked",
            "session_recording_status": "ready",
            "path_sandbox_status": "ready",
            "result_contract_status": "ready",
            "quota_status": "ready",
            "eligible_target_count": 1,
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-linux"],
            "ready_target_count": 1,
            "ready_lane_count": 1,
            "ready_lane_ids": ["linux"],
            "allowed_trust_levels": ["trusted"],
            "required_repo_roots": ["/srv/work"],
            "required_path_prefixes": ["src"],
            "required_result_formats": ["json"],
            "required_command_families": ["python"],
            "required_toolchains": ["python3.11"],
            "minimum_command_runtime_seconds": None,
            "minimum_file_transfer_quota_mb": None,
            "blocking_reasons": [],
            "recommended_fixes": ["Unblock artifact or connector contracts so brokered execution can move code and evidence safely."],
            "notes": ["Transport and contract status are intentionally degraded for this test."],
            "device_broker": {"summary": "broker ready"},
            "artifact_transport": {"summary": "artifact transport blocked"},
            "platform_runners": {"summary": "linux lane ready"},
        },
    )
    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution",
        lambda db, project: {
            "policy": {
                "enabled": True,
                "preferred_target_id": "gpu-linux",
                "required_runner_family": "external_adapter",
                "allowed_trust_levels": ["trusted"],
                "required_repo_roots": ["/srv/work"],
                "required_path_prefixes": ["src"],
                "required_result_formats": ["json"],
                "required_command_families": ["python"],
                "required_toolchains": ["python3.11"],
                "artifact_sync_enabled": True,
                "artifact_required": True,
                "required_connector_families": ["source_control"],
                "require_session_recording": True,
            },
            "selected_target": {
                "id": "gpu-linux",
                "label": "GPU Linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "os_family": "linux",
            },
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "selected_artifact_root": "/srv/work/artifacts",
                "remote_workspace_root": "/srv/work",
                "preflight_ready": False,
                "blocking_reasons": [],
            },
            "connector_contract": {
                "required_connector_families": ["source_control"],
                "available_families": [],
                "missing_required_families": ["source_control"],
                "preflight_ready": False,
                "blocking_reasons": [],
            },
            "broker_contract": {
                "require_session_recording": True,
                "session_recording_enabled": True,
                "target_toolchains": ["python3.11"],
                "target_command_families": ["python"],
                "target_result_formats": ["json"],
                "target_repo_roots": ["/srv/work"],
                "target_path_prefixes": ["src"],
                "preflight_ready": True,
                "blocking_reasons": [],
            },
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Plan Status Guard",
            "idea": "Ensure blocked transport or contract statuses degrade plan readiness.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.post(f"/api/projects/{project_id}/remote-execution-governance/plan")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["plan_status"] == "partial"

    approval_checkpoints = json.loads(
        (workspace / "artifacts" / "remote-execution-governance" / "approval-checkpoints.json").read_text(encoding="utf-8")
    )
    checkpoints = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoints["artifact_and_connector_review"]["status"] == "partial"
    assert checkpoints["publish_gate"]["status"] == "blocked"


def test_remote_execution_governance_summary_treats_brokered_sync_transport_as_ready(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-remote-execution-brokered-sync"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution",
        lambda db, project: {
            "policy": {
                "enabled": True,
                "preferred_target_id": "gpu-linux",
                "required_runner_family": "external_adapter",
                "artifact_sync_enabled": True,
                "artifact_required": True,
            },
            "required_runner_family": "external_adapter",
            "eligible_target_count": 1,
            "selected_target_id": "gpu-linux",
            "selected_target": {
                "id": "gpu-linux",
                "label": "GPU Linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "os_family": "linux",
            },
            "preflight_ready": True,
            "blocking_reasons": [],
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "remote_workspace_root": "/srv/work",
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "connector_contract": {
                "required_connector_families": [],
                "available_families": [],
                "missing_required_families": [],
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "broker_contract": {
                "preflight_ready": True,
                "blocking_reasons": [],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_device_broker_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Broker sees one ready target.",
            "preflight_ready": True,
            "selected_target_id": "gpu-linux",
            "recommended_target_ids": ["gpu-linux"],
            "blocking_reasons": [],
            "ready_target_count": 1,
            "capability_index": {
                "target_count": 1,
                "ready_target_count": 1,
                "toolchain_counts": {},
                "command_family_counts": {},
                "result_format_counts": {},
                "gpu_counts": {},
                "trust_level_counts": {},
                "connector_family_counts": {},
                "targets": [],
            },
            "remote_execution": {"policy": {"enabled": True}, "required_runner_family": "external_adapter"},
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Artifact transport is ready via brokered sync.",
            "selected_target_id": "gpu-linux",
            "preflight_ready": True,
            "sync_enabled": True,
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": [],
            "ready_route_count": 1,
            "selected_ready_route_count": 1,
            "partial_route_count": 0,
            "ready_route_ids": ["tailscale_ssh"],
            "selected_ready_route_ids": ["tailscale_ssh"],
            "partial_route_ids": [],
            "ready_platform_lanes": ["linux"],
            "partial_platform_lanes": [],
            "notes": ["Broker-managed sync is available."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
            "artifact_contract": {"sync_enabled": True, "required": True, "remote_workspace_root": "/srv/work", "preflight_ready": True, "blocking_reasons": []},
            "connector_contract": {"available_families": [], "available_connector_count": 0, "preflight_ready": True, "blocking_reasons": []},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Linux lane is ready.",
            "selected_target_id": "gpu-linux",
            "lane_count": 1,
            "ready_lane_count": 1,
            "partial_lane_count": 0,
            "unavailable_lane_count": 0,
            "ready_route_count": 1,
            "selected_ready_route_count": 1,
            "partial_route_count": 0,
            "ready_lane_ids": ["linux"],
            "ready_route_ids": ["tailscale_ssh"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": [],
            "selected_ready_lane_ids": ["linux"],
            "selected_ready_route_ids": ["tailscale_ssh"],
            "lanes": [
                {
                    "lane_id": "linux",
                    "title": "Linux Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["gpu-linux"],
                    "target_count": 1,
                    "selected_target_ids": ["gpu-linux"],
                    "os_families": ["linux"],
                    "toolchains": ["python3.11"],
                    "command_families": ["python"],
                    "route_ids": ["tailscale_ssh"],
                    "ready_route_ids": ["tailscale_ssh"],
                    "selected_route_ids": ["tailscale_ssh"],
                    "selected_ready_route_ids": ["tailscale_ssh"],
                    "recommended_commands": ["python -m pytest"],
                    "notes": [],
                }
            ],
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Brokered Sync Demo",
            "idea": "Need brokered artifact sync to count as a ready transport lane.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/remote-execution-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "ready"
    assert payload["transport_status"] == "ready"
    assert payload["artifact_contract_status"] == "ready"
    assert payload["selected_target_probe_status"] == "unknown"
    assert payload["ready_candidate_count"] == 0
    assert payload["ready_candidate_ids"] == []
    assert payload["ready_lane_ids"] == ["linux"]
    assert payload["selected_ready_lane_count"] == 1
    assert payload["selected_ready_lane_ids"] == ["linux"]


def test_remote_execution_governance_summary_separates_selected_target_ready_lanes_from_fleet_ready_lanes(
    client, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace-remote-execution-selected-lanes"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution",
        lambda db, project: {
            "policy": {
                "enabled": True,
                "preferred_target_id": "browser-box",
                "required_runner_family": "external_adapter",
                "artifact_sync_enabled": True,
                "artifact_required": True,
            },
            "required_runner_family": "external_adapter",
            "eligible_target_count": 1,
            "selected_target_id": "browser-box",
            "selected_target": {
                "id": "browser-box",
                "label": "Browser Box",
                "transport": "tailscale_ssh",
                "host": "browser-box.tailnet.ts.net",
                "os_family": "linux",
            },
            "preflight_ready": False,
            "blocking_reasons": ["selected target is not bound to the required execution lane"],
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "connector_contract": {
                "required_connector_families": [],
                "available_families": [],
                "missing_required_families": [],
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "broker_contract": {
                "preflight_ready": False,
                "blocking_reasons": ["selected target is not bound to the required execution lane"],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_device_broker_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Broker sees one selected target and one unrelated ready lane host.",
            "preflight_ready": False,
            "selected_target_id": "browser-box",
            "selected_target_probe_status": "ready",
            "recommended_target_ids": ["browser-box"],
            "blocking_reasons": ["selected target is not bound to the required execution lane"],
            "ready_target_count": 1,
            "capability_index": {
                "target_count": 2,
                "ready_target_count": 1,
                "toolchain_counts": {},
                "command_family_counts": {},
                "result_format_counts": {},
                "gpu_counts": {},
                "trust_level_counts": {},
                "connector_family_counts": {},
                "targets": [],
            },
            "remote_execution": {"policy": {"enabled": True}, "required_runner_family": "external_adapter"},
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Artifact transport is only partially aligned.",
            "selected_target_id": "browser-box",
            "selected_target_probe_status": "ready",
            "preflight_ready": False,
            "sync_enabled": True,
            "recommended_transport_mode": "partial_sync",
            "blocking_reasons": ["selected target is not bound to the required execution lane"],
            "ready_route_count": 1,
            "selected_ready_route_count": 0,
            "partial_route_count": 0,
            "ready_route_ids": ["plain_ssh"],
            "selected_ready_route_ids": [],
            "partial_route_ids": [],
            "ready_platform_lanes": ["linux"],
            "selected_ready_platform_lanes": [],
            "partial_platform_lanes": ["browser"],
            "notes": ["A fleet-ready Linux lane exists, but not on the selected target."],
            "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "artifacts"},
            "connector_registry": {"summary": "ready"},
            "artifact_contract": {"sync_enabled": True, "required": True, "preflight_ready": True, "blocking_reasons": []},
            "connector_contract": {"available_families": [], "available_connector_count": 0, "preflight_ready": True, "blocking_reasons": []},
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Linux lane is ready elsewhere, browser lane is only partial on the selected target.",
            "selected_target_id": "browser-box",
            "selected_target_probe_status": "ready",
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["browser-box"],
            "lane_count": 2,
            "ready_lane_count": 1,
            "partial_lane_count": 1,
            "unavailable_lane_count": 0,
            "ready_route_count": 1,
            "selected_ready_route_count": 0,
            "partial_route_count": 0,
            "ready_lane_ids": ["linux"],
            "ready_route_ids": ["plain_ssh"],
            "partial_lane_ids": ["browser"],
            "unavailable_lane_ids": [],
            "selected_ready_lane_ids": [],
            "selected_ready_route_ids": [],
            "partial_route_ids": [],
            "lanes": [
                {
                    "lane_id": "linux",
                    "title": "Linux Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["gpu-linux"],
                    "target_count": 1,
                    "selected_target_ids": [],
                    "os_families": ["linux"],
                    "toolchains": ["python3.11"],
                    "command_families": ["python"],
                    "route_ids": ["plain_ssh"],
                    "ready_route_ids": ["plain_ssh"],
                    "selected_route_ids": [],
                    "selected_ready_route_ids": [],
                    "recommended_commands": ["python -m pytest"],
                    "notes": [],
                },
                {
                    "lane_id": "browser",
                    "title": "Browser Runner",
                    "status": "partial",
                    "summary": "partial",
                    "target_ids": ["browser-box"],
                    "target_count": 1,
                    "selected_target_ids": ["browser-box"],
                    "os_families": ["linux"],
                    "toolchains": ["playwright"],
                    "command_families": ["browser"],
                    "route_ids": [],
                    "ready_route_ids": [],
                    "selected_route_ids": [],
                    "selected_ready_route_ids": [],
                    "recommended_commands": ["playwright test"],
                    "notes": [],
                },
            ],
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Selected Lane Separation Demo",
            "idea": "Need remote execution governance to separate selected-target lane readiness from fleet inventory.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/remote-execution-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "partial"
    assert payload["selected_target_id"] == "browser-box"
    assert payload["ready_lane_ids"] == ["linux"]
    assert payload["selected_ready_lane_count"] == 0
    assert payload["selected_ready_lane_ids"] == []
    assert payload["ready_route_ids"] == ["plain_ssh"]
    assert payload["selected_ready_route_ids"] == []
    assert any(
        "Required runner family is `external_adapter` with 0 selected-target-ready platform lane(s) and 1 fleet-ready lane(s)."
        == note
        for note in payload["notes"]
    )
    assert any(
        "Route coverage shows 0 selected-target-ready route(s), 1 fleet-ready route(s), and 0 partial route(s)."
        == note
        for note in payload["notes"]
    )


def test_remote_execution_governance_summary_blocks_mismatched_path_result_and_quota_contracts(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace-remote-execution-governance-mismatch"
    workspace.mkdir()
    (workspace / "README.md").write_text("demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "manager.service.preview_project_remote_execution",
        lambda db, project: {
            "policy": {
                "enabled": True,
                "preferred_target_id": "gpu-linux",
                "required_runner_family": "external_adapter",
                "required_repo_roots": ["/srv/work/src"],
                "required_path_prefixes": ["src/runtime"],
                "required_result_formats": ["json", "junit_xml"],
                "required_command_families": ["python", "git"],
                "required_toolchains": ["python3.11", "cuda12"],
                "minimum_command_runtime_seconds": 900,
                "minimum_file_transfer_quota_mb": 512,
            },
            "required_runner_family": "external_adapter",
            "selected_target_id": "gpu-linux",
            "selected_target_probe_status": "ready",
            "selected_target": {
                "id": "gpu-linux",
                "label": "GPU Linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "os_family": "linux",
            },
            "eligible_target_count": 1,
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-linux"],
            "preflight_ready": True,
            "blocking_reasons": [],
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "connector_contract": {
                "required_connector_families": [],
                "available_families": [],
                "missing_required_families": [],
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "broker_contract": {
                "preflight_ready": True,
                "blocking_reasons": [],
                "require_session_recording": False,
                "session_recording_enabled": True,
                "target_repo_roots": ["/srv/work/tmp"],
                "target_path_prefixes": ["tmp"],
                "target_result_formats": ["json"],
                "target_command_families": ["python"],
                "target_toolchains": ["python3.11"],
                "target_command_runtime_seconds": 600,
                "target_file_transfer_quota_mb": 256,
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_device_broker_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "device broker partial",
            "preflight_ready": True,
            "selected_target_id": "gpu-linux",
            "selected_target_probe_status": "ready",
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-linux"],
            "recommended_target_ids": ["gpu-linux"],
            "ready_target_count": 1,
            "capability_index": {
                "target_count": 1,
                "ready_target_count": 1,
                "toolchain_counts": {"python3.11": 1},
                "command_family_counts": {"python": 1},
                "result_format_counts": {"json": 1},
                "gpu_counts": {"RTX 4090": 1},
                "trust_level_counts": {"trusted": 1},
                "connector_family_counts": {},
                "targets": [
                    {
                        "target_id": "gpu-linux",
                        "label": "GPU Linux",
                        "transport": "tailscale_ssh",
                        "host": "gpu-linux.tailnet.ts.net",
                        "os_family": "linux",
                        "architecture": "x86_64",
                        "gpu": "RTX 4090",
                        "trust_level": "trusted",
                        "workspace_root": "/srv/work",
                        "capabilities": ["python"],
                        "tags": ["gpu"],
                        "runner_families": ["external_adapter"],
                        "adapter_command": "python3",
                        "toolchains": ["python3.11"],
                        "command_families": ["python"],
                        "result_formats": ["json"],
                        "connector_families": [],
                        "artifact_roots": ["/srv/work/artifacts"],
                        "allowed_repo_roots": ["/srv/work/tmp"],
                        "allowed_path_prefixes": ["tmp"],
                        "session_recording_enabled": True,
                        "max_command_runtime_seconds": 600,
                        "file_transfer_quota_mb": 256,
                        "probe_status": "ready",
                        "ready": True,
                    }
                ],
            },
            "remote_execution": {
                "policy": {
                    "enabled": True,
                    "required_repo_roots": ["/srv/work/src"],
                    "required_path_prefixes": ["src/runtime"],
                    "required_result_formats": ["json", "junit_xml"],
                    "required_command_families": ["python", "git"],
                    "required_toolchains": ["python3.11", "cuda12"],
                    "minimum_command_runtime_seconds": 900,
                    "minimum_file_transfer_quota_mb": 512,
                },
                "required_runner_family": "external_adapter",
            },
            "artifact_registry": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "available": True,
                "summary": "artifacts",
            },
            "connector_registry": {
                "summary": "connectors",
            },
            "blocking_reasons": [],
        },
    )
    monkeypatch.setattr(
        "manager.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "artifact transport ready",
            "selected_target_id": "gpu-linux",
            "selected_target_probe_status": "ready",
            "preflight_ready": True,
            "sync_enabled": True,
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": [],
            "ready_platform_lanes": ["linux"],
            "partial_platform_lanes": [],
            "notes": [],
            "artifact_registry": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "available": True,
                "summary": "artifacts",
            },
            "connector_registry": {
                "summary": "connectors",
            },
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "selected_artifact_root": "/srv/work/artifacts",
                "remote_workspace_root": "/srv/work",
                "preflight_ready": True,
                "blocking_reasons": [],
            },
            "connector_contract": {
                "available_families": [],
                "available_connector_count": 0,
                "preflight_ready": True,
                "blocking_reasons": [],
            },
        },
    )
    monkeypatch.setattr(
        "manager.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "platform runners partial",
            "selected_target_id": "gpu-linux",
            "selected_target_probe_status": "ready",
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-linux"],
            "lane_count": 1,
            "ready_lane_count": 1,
            "partial_lane_count": 0,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["linux"],
            "partial_lane_ids": [],
            "unavailable_lane_ids": [],
            "lanes": [
                {
                    "lane_id": "linux",
                    "title": "Linux Runner",
                    "status": "ready",
                    "summary": "ready",
                    "target_ids": ["gpu-linux"],
                    "target_count": 1,
                    "selected_target_ids": ["gpu-linux"],
                    "os_families": ["linux"],
                    "toolchains": ["python3.11"],
                    "command_families": ["python"],
                    "recommended_commands": ["python -m pytest"],
                    "notes": [],
                }
            ],
        },
    )

    create = client.post(
        "/api/projects",
        json={
            "name": "Remote Execution Governance Mismatch Demo",
            "idea": "Need governance to reject targets that miss exact broker policy requirements.",
            "workspace_path": workspace.as_posix(),
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    response = client.get(f"/api/projects/{project_id}/remote-execution-governance/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["governance_status"] == "partial"
    assert payload["transport_status"] == "ready"
    assert payload["broker_contract_status"] == "ready"
    assert payload["path_sandbox_status"] == "blocked"
    assert payload["result_contract_status"] == "blocked"
    assert payload["quota_status"] == "blocked"
    assert "Remote execution path sandbox requirements are not fully satisfied by the selected target." in payload["blocking_reasons"]
    assert "Remote execution result contracts are not fully satisfied by the selected target." in payload["blocking_reasons"]
    assert "Remote execution quota requirements are not satisfied by the selected target." in payload["blocking_reasons"]
    assert "Tighten or satisfy required repo roots and path prefixes so workers cannot freestyle outside the intended sandbox." in payload["recommended_fixes"]
    assert "Expose the required toolchains, command families, and result formats on the selected target before using it for governed runs." in payload["recommended_fixes"]
    assert "Increase target runtime or file-transfer quotas, or lower the policy floor to something the lane can honestly satisfy." in payload["recommended_fixes"]
