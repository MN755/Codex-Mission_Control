from __future__ import annotations

import json

from pathlib import Path

from bridge_messages import bridge_runtime_service
from models import utc_now
from fastapi.testclient import TestClient

from conftest import sample_workspace, wait_for
from main import app


def test_system_status_supports_provider_preview_overrides(client, bridge_headers, monkeypatch) -> None:
    monkeypatch.setattr("system_status.detect_codex_status", lambda: {
        "provider": "codex",
        "label": "Codex",
        "cli_detected": True,
        "cli_path": "codex",
        "cli_path_exists": True,
        "cli_execution_available": True,
        "cli_version": "codex 1.0.0",
        "login_status": "Logged in using ChatGPT",
        "auth_mode": "chatgpt",
        "authenticated": True,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": True,
        "supports_app_server": True,
        "supports_builtin_auth": True,
        "available_models": [],
        "configured_plugins": [],
        "configured_mcp_servers": [],
        "local_skills": [],
        "mcp_servers": [],
        "mcp_state": {},
        "notes": [],
    })
    monkeypatch.setattr("system_status.detect_claude_code_status", lambda: {
        "provider": "claude_code",
        "label": "Claude Code",
        "cli_detected": False,
        "cli_path": None,
        "cli_path_exists": False,
        "cli_execution_available": False,
        "cli_version": None,
        "login_status": "Claude CLI was not detected.",
        "auth_mode": None,
        "authenticated": False,
        "auth_status_detectable": False,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": [],
    })
    def fake_detect_ollama_status(endpoint: str | None = None) -> dict:
        return {
            "provider": "ollama",
            "label": "Ollama",
            "cli_detected": True,
            "cli_version": endpoint or "http://localhost:11434",
            "login_status": f"Ollama endpoint reachable at {endpoint or 'http://localhost:11434'}.",
            "auth_mode": "local",
            "authenticated": True,
            "auth_status_detectable": True,
            "supports_model_override": True,
            "supports_reasoning_effort": True,
            "supports_app_server": False,
            "supports_builtin_auth": False,
            "available_models": ["llama3.2:latest", "qwen2.5-coder:7b"],
            "notes": [],
            "reachable": True,
            "summary": "Reachable",
        }

    monkeypatch.setattr("system_status.detect_ollama_status", fake_detect_ollama_status)
    monkeypatch.setattr("system_status.detect_nvidia_dynamo_status", lambda endpoint=None: {
        "provider": "nvidia_dynamo",
        "label": "NVIDIA Dynamo",
        "cli_detected": False,
        "cli_path": endpoint or "http://dynamo.local:8000",
        "cli_path_exists": False,
        "cli_execution_available": False,
        "cli_version": None,
        "login_status": "NVIDIA Dynamo endpoint is not reachable.",
        "auth_mode": None,
        "authenticated": False,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": [],
        "reachable": False,
        "summary": "offline",
        "endpoint": endpoint or "http://dynamo.local:8000",
        "endpoint_configured": False,
        "api_key_configured": False,
        "auth_required": False,
    })
    monkeypatch.setattr("system_status.detect_nvidia_nim_status", lambda endpoint=None: {
        "provider": "nvidia_nim",
        "label": "NVIDIA NIM",
        "cli_detected": False,
        "cli_path": endpoint or "https://integrate.api.nvidia.com",
        "cli_path_exists": False,
        "cli_execution_available": False,
        "cli_version": None,
        "login_status": "NVIDIA NIM endpoint is not reachable.",
        "auth_mode": None,
        "authenticated": False,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": [],
        "reachable": False,
        "summary": "offline",
        "endpoint": endpoint or "https://integrate.api.nvidia.com",
        "endpoint_configured": False,
        "api_key_configured": False,
        "auth_required": True,
    })
    monkeypatch.setattr("system_status.detect_webwright_status", lambda: {"summary": "not installed"})

    status = client.get(
        "/api/system/status",
        params={"provider": "ollama", "provider_endpoint": "http://localhost:11434"},
        headers=bridge_headers,
    ).json()

    assert status["selected_provider"] == "ollama"
    assert status["selected_provider_label"] == "Ollama"
    assert "llama3.2:latest" in status["available_models"]


def test_dry_run_project_flow(client, bridge_headers, monkeypatch) -> None:
    async def fake_get_system_status(
        db,
        project,
        provider_override=None,
        provider_endpoint_override=None,
        adapter_command_override=None,
        adapter_args_override=None,
    ):
        return {
            "selected_provider": "claude_code",
            "selected_provider_label": "Claude Code",
            "cli_detected": True,
            "cli_path": "claude",
            "cli_path_exists": True,
            "cli_execution_available": True,
            "cli_version": "claude 1.0.0",
            "login_status": "Claude CLI is executable.",
            "auth_mode": None,
            "authenticated": False,
            "runtime_ready": True,
            "runtime_status": "ready",
            "runtime_summary": "Claude preview status is available.",
            "runtime_blockers": [],
            "app_server_supported": False,
            "app_server_handshake_status": "unsupported",
            "app_server_transport": "unsupported",
            "effective_runner_mode": "auto",
            "dry_run_available": True,
            "runtime_directory": "runtime",
            "diagnostics_directory": None,
            "repo_root": "repo",
            "launcher_root": "launcher",
            "plugin_source_root": "plugins/mission-control",
            "backend_host": "127.0.0.1",
            "backend_port": 8010,
            "backend_base_url": "http://127.0.0.1:8010",
            "configured_backend_port": 8010,
            "backend_binding_source": "test",
            "frontend_port": 5173,
            "active_runs": [],
            "current_settings_summary": None,
            "selected_manager_model": "gpt-5.5",
            "selected_default_worker_model": "gpt-5.4-mini",
            "available_models": ["sonnet"],
            "model_advisories": [],
            "provider_statuses": [],
            "mcp_servers": [],
            "configured_mcp_servers": [],
            "mcp_state": {},
            "configured_plugins": [],
            "local_skills": [],
            "current_auth_job": None,
            "notes": [],
            "startup_summary": None,
            "app_state_summary": None,
        }

    def fake_auth_state():
        return {
            "authenticated": False,
            "auth_mode": None,
            "login_status": "Claude CLI is executable.",
            "cli_detected": True,
            "provider": "claude_code",
            "current_job": None,
            "chatgpt_supported": True,
            "device_auth_supported": True,
            "api_key_supported": True,
            "provider_statuses": [],
            "notes": [],
        }

    async def fake_start_idle_agents(db, project):
        from main import service as app_service

        app_service.events.publish(
            db,
            project.id,
            "agent.started",
            {
                "project_id": project.id,
                "effective_settings": {"model": "gpt-5.5-mini"},
            },
        )
        return 1

    async def fake_approve_plan(db, project, action, note):
        from main import service as app_service

        latest_plan = app_service._latest_plan(db, project.id)
        latest_plan.status = "approved"
        project.status = "building"
        app_service.events.publish(db, project.id, "plan.approved", {"plan_id": latest_plan.id, "action": action})
        app_service.events.publish(
            db,
            project.id,
            "agent.started",
            {
                "project_id": project.id,
                "effective_settings": {"model": "gpt-5.5-mini"},
            },
        )
        db.flush()
        return latest_plan

    monkeypatch.setattr("main.service.get_system_status", fake_get_system_status)
    monkeypatch.setattr("main.service.auth_state", fake_auth_state)
    monkeypatch.setattr("main.service.start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr("main.service.approve_plan", fake_approve_plan)
    monkeypatch.setattr(
        "main.service.preview_operational_instincts",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "instinct_count": 2,
            "instincts": [
                {
                    "key": "ship-with-evidence",
                    "title": "Ship with evidence",
                    "trigger": "Validation evidence is still missing.",
                    "rule": "Do not hand off without named validation evidence.",
                    "rationale": "The manager needs explicit proof before claiming readiness.",
                    "summary": "Validation evidence is required before handoff.",
                    "confidence": "high",
                    "tags": ["validation", "handoff"],
                    "evidence": ["Named pytest slice exists."],
                },
                {
                    "key": "turn-gaps-into-checks",
                    "title": "Turn gaps into checks",
                    "trigger": "A validation gap is recorded.",
                    "rule": "Convert each validation gap into an explicit follow-up check.",
                    "rationale": "Named checks are easier to track than vague concerns.",
                    "summary": "Convert open gaps into explicit validation steps.",
                    "confidence": "medium",
                    "tags": ["validation"],
                    "evidence": [],
                },
            ],
            "confidence_levels": ["high", "medium"],
            "confidence_counts": {"high": 1, "medium": 1},
            "confidence_group_count": 2,
            "tags": ["handoff", "validation"],
            "tag_counts": {"handoff": 1, "validation": 2},
            "tag_group_count": 2,
            "evidence_item_count": 1,
            "evidenceful_instinct_count": 1,
            "generated_at": utc_now(),
        },
    )

    profile_response = client.get("/api/profile", headers=bridge_headers)
    assert profile_response.status_code == 200
    assert profile_response.json()["onboarding_completed"] is False

    saved_profile = client.put(
        "/api/profile",
        json={
            "display_name": "Morgan",
            "preferred_provider_choice": "codex",
            "preferred_start_mode": "guided_walkthrough",
            "onboarding_completed": True,
        },
        headers=bridge_headers,
    )
    assert saved_profile.status_code == 200
    assert saved_profile.json()["display_name"] == "Morgan"

    create_response = client.post(
        "/api/projects",
        json={
            "name": "Mission Control Demo",
            "idea": "Build a local orchestration dashboard",
            "workspace_path": sample_workspace("demo-project"),
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    project = create_response.json()
    project_id = project["id"]
    assert project["created_by"] == "Morgan"

    details_response = client.get(f"/api/projects/{project_id}/details")
    assert details_response.status_code == 200
    assert details_response.json()["id"] == project_id

    widget_catalog_response = client.get("/api/widgets/catalog")
    assert widget_catalog_response.status_code == 200

    project_widget_catalog_response = client.get("/api/widgets/catalog/project")
    assert project_widget_catalog_response.status_code == 200

    widget_instances_response = client.get("/api/widgets/instances")
    assert widget_instances_response.status_code == 200

    active_orchestration = client.get(f"/api/projects/{project_id}/orchestrations/active")
    assert active_orchestration.status_code == 200

    settings_response = client.get(f"/api/settings?project_id={project_id}")
    assert settings_response.status_code == 200
    assert settings_response.json()["runner_mode"] == "dry_run"

    project_settings_response = client.get(f"/api/projects/{project_id}/settings")
    assert project_settings_response.status_code == 200
    assert project_settings_response.json()["runner_mode"] == "dry_run"

    updated_settings = client.put(
        f"/api/settings?project_id={project_id}",
        json={
            "provider": "claude_code",
            "manager_model": "gpt-5.5",
            "default_worker_model": "gpt-5.4-mini",
            "manager_reasoning_effort": "high",
            "default_worker_reasoning_effort": "low",
            "per_role_model_overrides_json": {"Primary implementation": "gpt-5.5-mini"},
            "per_role_reasoning_overrides_json": {"Primary implementation": "minimal"},
            "adapter_command": None,
            "adapter_args_json": [],
            "runner_mode": "dry_run",
            "sandbox_mode": "workspace-write",
            "approval_policy": "on-request",
        },
    )
    assert updated_settings.status_code == 200
    assert updated_settings.json()["manager_model"] == "gpt-5.5"
    assert updated_settings.json()["provider"] == "claude_code"

    updated_project_settings = client.put(
        f"/api/projects/{project_id}/settings",
        json={
            "provider": "claude_code",
            "manager_model": "gpt-5.5",
            "default_worker_model": "gpt-5.4-mini",
            "manager_reasoning_effort": "high",
            "default_worker_reasoning_effort": "low",
            "per_role_model_overrides_json": {"Primary implementation": "gpt-5.5-mini"},
            "per_role_reasoning_overrides_json": {"Primary implementation": "minimal"},
            "adapter_command": None,
            "adapter_args_json": [],
            "runner_mode": "dry_run",
            "sandbox_mode": "workspace-write",
            "approval_policy": "on-request",
        },
    )
    assert updated_project_settings.status_code == 200
    assert updated_project_settings.json()["manager_model"] == "gpt-5.5"

    status = client.get(f"/api/projects/{project_id}/system/status", headers=bridge_headers).json()
    assert "active_runs" in status
    assert status["selected_provider"] == "claude_code"
    assert status["selected_manager_model"] == "gpt-5.5"
    assert status["selected_default_worker_model"] == "gpt-5.4-mini"
    assert "authenticated" in status
    assert "current_auth_job" in status

    codex_status = client.get(f"/api/projects/{project_id}/system/codex-status", headers=bridge_headers).json()
    assert codex_status["runtime_ready"] is True
    assert codex_status["selected_provider"] == "claude_code"
    assert codex_status["selected_manager_model"] == "gpt-5.5"

    auth_state = client.get("/api/system/auth-state").json()
    assert "authenticated" in auth_state
    assert "cli_detected" in auth_state
    assert "notes" in auth_state

    swarm_plan_alias = client.get(f"/api/projects/{project_id}/swarm-plan")
    swarm_plan_canonical = client.get(f"/api/projects/{project_id}/swarm/plan")
    assert swarm_plan_alias.status_code == 200
    assert swarm_plan_alias.json() == swarm_plan_canonical.json()

    risk_register = client.get(f"/api/projects/{project_id}/risk-register")
    risks = client.get(f"/api/projects/{project_id}/risks")
    assert risk_register.status_code == 200
    assert risk_register.json() == risks.json()

    validation_summary = client.get(f"/api/projects/{project_id}/validation-summary")
    validation_coverage_summary = client.get(f"/api/projects/{project_id}/validation-coverage/summary")
    assert validation_summary.status_code == 200
    assert validation_summary.json() == validation_coverage_summary.json()

    instincts = client.get(f"/api/projects/{project_id}/instincts")
    instincts_preview = client.get(f"/api/projects/{project_id}/instincts/preview")
    assert instincts.status_code == 200
    instincts_payload = instincts.json()
    instincts_preview_payload = instincts_preview.json()
    assert instincts_payload["generated_at"] != ""
    assert instincts_preview_payload["generated_at"] != ""
    assert {k: v for k, v in instincts_payload.items() if k != "generated_at"} == {
        k: v for k, v in instincts_preview_payload.items() if k != "generated_at"
    }

    orchestration = active_orchestration.json()
    if orchestration is not None:
        orchestration_id = orchestration["id"]
        orchestration_detail = client.get(f"/api/projects/{project_id}/orchestrations/{orchestration_id}")
        orchestration_status = client.get(f"/api/projects/{project_id}/orchestrations/{orchestration_id}/status")
        orchestration_events = client.get(f"/api/projects/{project_id}/orchestrations/{orchestration_id}/events")
        orchestration_handoff = client.get(f"/api/projects/{project_id}/orchestrations/{orchestration_id}/handoff")
        orchestration_pending_decisions = client.get(
            f"/api/projects/{project_id}/orchestrations/{orchestration_id}/pending-decisions"
        )
        assert orchestration_detail.status_code == 200
        assert orchestration_status.status_code == 200
        assert orchestration_events.status_code == 200
        assert orchestration_handoff.status_code == 200
        assert orchestration_pending_decisions.status_code == 200

    docs_response = client.post(f"/api/projects/{project_id}/docs/generate")
    assert docs_response.status_code == 200
    assert "PROJECT_BRIEF.md" in docs_response.json()["files"]
    assert docs_response.json()["manager_mode_used"] == "deterministic"

    session = client.post(f"/api/projects/{project_id}/interview/start", json={"question_budget": 0}).json()
    assert session["status"] == "completed"
    assert session["question_budget"] == 0
    assert session["questions"] == []

    plan_response = client.post(f"/api/projects/{project_id}/plan/generate", json={"force_rebuild": True})
    assert plan_response.status_code == 200
    approve_response = client.post(f"/api/projects/{project_id}/plan/approve", json={"action": "approve_build"})
    assert approve_response.status_code == 200
    task_generation = client.post(f"/api/projects/{project_id}/tasks/generate")
    assert task_generation.status_code == 200

    def project_is_active() -> bool:
        current = client.get(f"/api/projects/{project_id}").json()
        return current["status"] in {"building", "handoff_ready"}

    wait_for(project_is_active, timeout=12.0)

    events = client.get(f"/api/projects/{project_id}/events").json()
    assert any(event["event_type"] == "agent.started" for event in events)
    started_events = [event for event in events if event["event_type"] == "agent.started"]
    assert any(event["payload_json"]["effective_settings"]["model"] in {"gpt-5.5-mini", "gpt-5.4-mini"} for event in started_events)
    reservations = client.get(f"/api/projects/{project_id}/reservations").json()
    assert isinstance(reservations, list)


def test_privileged_headless_and_status_routes_require_token() -> None:
    with TestClient(app) as raw_client:
        assert raw_client.get("/api/system/status").status_code == 401
        assert raw_client.get("/api/profile").status_code == 401
        assert raw_client.get("/api/profile/summary").status_code == 401
        assert raw_client.get("/api/diagnostics/identity").status_code == 401
        assert raw_client.get("/api/headless/config").status_code == 401
        assert raw_client.get("/api/runners/status").status_code == 401
        assert raw_client.get("/api/system/auth-state").status_code == 401
        assert raw_client.post("/api/system/auth/login/chatgpt", json={"device_auth": True}).status_code == 401
        assert raw_client.post("/api/system/auth/login/device").status_code == 401
        assert raw_client.post("/api/system/auth/login/api-key", json={"api_key": "test-key"}).status_code == 401
        assert raw_client.post("/api/system/auth/logout").status_code == 401
        assert raw_client.get("/api/system/auth-jobs/example").status_code == 401
        assert raw_client.get("/api/plugin/health").status_code == 401
        assert raw_client.post("/api/plugin/health/check").status_code == 401
        assert raw_client.get("/api/headless/health").status_code == 401
        assert raw_client.post("/api/headless/autowire", json={}).status_code == 401
        assert raw_client.post("/api/headless/repair", json={}).status_code == 401
        assert raw_client.post("/api/startup/check", json={"attempt_number": 1, "include_optional_checks": True}).status_code == 401
        assert raw_client.post("/api/startup/retry", json={"attempt_number": 1, "failed_check": "runtime_paths", "retry_mode": "full"}).status_code == 401
        assert raw_client.get("/api/startup/status").status_code == 401
        assert raw_client.post("/api/startup/complete-first-run").status_code == 401
        assert raw_client.post("/api/startup/diagnostics", json={"include_support_bundle": True}).status_code == 401
        assert raw_client.post("/api/startup/open-diagnostics-folder").status_code == 401
        assert raw_client.get("/api/diagnostics/reports").status_code == 401
        assert raw_client.get("/api/projects/1/diagnostics/reports").status_code == 401


def test_runtime_and_project_control_routes_require_token(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Auth Surface",
            "idea": "Lock down route access",
            "workspace_path": sample_workspace("auth-surface"),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    with TestClient(app) as raw_client:
        assert raw_client.post(
            "/api/projects",
            json={
                "name": "Unauthenticated Create",
                "idea": "Should fail",
                "workspace_path": sample_workspace("unauth-create"),
                "provider": "codex",
                "runner_mode": "dry_run",
                "manager_mode": "auto",
            },
        ).status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}").status_code == 401
        assert raw_client.patch(f"/api/projects/{project_id}", json={"name": "Nope"}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/open").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/pause").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/resume").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/archive").status_code == 401
        assert raw_client.get("/api/dashboard/summary").status_code == 401
        assert raw_client.get("/api/dashboard/stream").status_code == 401
        assert raw_client.get("/api/settings", params={"project_id": project_id}).status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/settings").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/details").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/swarm-plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/risk-register").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/validation-summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/instincts").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/orchestrations/1").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/orchestrations/1/status").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/orchestrations/1/pause").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/orchestrations/1/resume").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/orchestrations/1/events").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/orchestrations/1/handoff").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/orchestrations/1/pending-decisions").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/orchestrations/1/status-summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/orchestrations/1/event-digest").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/orchestrations/1/handoff-summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/swarm/preferences").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/swarm/plan").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/swarm/spawn").status_code == 401
        assert raw_client.get("/api/playbooks").status_code == 401
        assert raw_client.get("/api/profile/summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/playbook").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/playbook/recommendations").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/playbook/suggest").status_code == 401
        assert raw_client.get("/api/preferences").status_code == 401
        assert raw_client.get("/api/preferences/summary").status_code == 401
        assert raw_client.delete("/api/preferences/example").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/preferences/summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/preferences/effective").status_code == 401
        assert raw_client.delete(f"/api/projects/{project_id}/preferences/example").status_code == 401
        assert raw_client.get("/api/security/policy").status_code == 401
        assert raw_client.get("/api/tools").status_code == 401
        assert raw_client.get("/api/integrations/catalog").status_code == 401
        assert raw_client.get("/api/integrations/connections").status_code == 401
        assert raw_client.get("/api/integrations/health").status_code == 401
        assert raw_client.get("/api/integrations/registry").status_code == 401
        assert raw_client.post("/api/integrations/import-host-state").status_code == 401
        assert raw_client.get("/api/skills").status_code == 401
        assert raw_client.get("/api/handoffs").status_code == 401
        assert raw_client.get("/api/agent-archetypes").status_code == 401
        assert raw_client.get("/api/widgets/catalog").status_code == 401
        assert raw_client.get("/api/widgets/catalog/project").status_code == 401
        assert raw_client.get("/api/widgets/instances", params={"scope": "dashboard"}).status_code == 401
        assert raw_client.get("/api/widgets/instances").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/system/status").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/system/codex-status").status_code == 401
        assert raw_client.patch(f"/api/projects/{project_id}/widgets/instances/1", json={"collapsed": True}).status_code == 401
        assert raw_client.delete(f"/api/projects/{project_id}/widgets/instances/1").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/widgets/instances/1/data").status_code == 401
        assert raw_client.get("/api/capabilities/matrix").status_code == 401
        assert raw_client.get("/api/capabilities/benchmarks").status_code == 401
        assert raw_client.get("/api/agents/reputation").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/agents/1/start").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/agents/1/stop").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/agents/1/pause").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/tasks/1/start").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/tasks/1/complete").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/subagent-batches/1/results", json={"results": []}).status_code == 401
        assert raw_client.post(
            f"/api/projects/{project_id}/runs/1/report",
            json={"agent": "x", "task_id": "1", "status": "done", "summary": "x", "files_changed": [], "tests_run": [], "blockers": [], "risks": [], "recommended_next_task": "none"},
        ).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/change-requests", json={"request_text": "Make it better"}).status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/context-packs").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/workspace-tooling").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/artifact-registry").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/artifact-registry/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/connector-governance/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/connector-governance/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/external-discovery/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/external-discovery/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/artifact-transport/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/artifact-transport/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/file-governance/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/file-governance/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/file-graph-governance/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/file-graph-governance/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/design-transfer/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/design-transfer/plan").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/spatial-asset-governance/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/spatial-asset-governance/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/game-engine-governance/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/game-engine-governance/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/dataset-governance/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/dataset-governance/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/model-refactor-governance/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/model-refactor-governance/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/native-app-validation-governance/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/native-app-validation-governance/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/remote-execution-governance/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/remote-execution-governance/summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/device-broker/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/device-broker/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/host-capability-index/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/host-capability-index/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/remote-runners/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/remote-runners/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/platform-runners/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/platform-runners/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/integrations").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/integrations/source_control").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/integrations/source_control/actions").status_code == 401
        assert raw_client.post(
            f"/api/projects/{project_id}/integrations/source_control/actions/create/preview",
            json={"params": {"title": "x", "body": "y"}},
        ).status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/context-packs/1").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia-dynamo").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia-nim").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia-aiq").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia-gpu-diagnostics").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia-local-runtime").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia-validation-plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/tensorflow/features").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/pytorch/features").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/codebase/search", json={"pattern": "TODO"}).status_code == 401
        assert raw_client.get("/api/context-packs/1", params={"project_id": project_id}).status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/risks").status_code == 401
        assert raw_client.get("/api/risks/common").status_code == 401
        assert raw_client.get("/api/risks/summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/risks/summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/scope-creep").status_code == 401
        assert raw_client.post("/api/scope-creep/1/resolve", params={"project_id": project_id}, json={"status": "accepted"}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/scope-creep/1/resolve", json={"status": "accepted"}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/questions/1/answer", json={"option_id": "x", "selected_text": "x"}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/questions/1/auto-decide").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/decisions/1/answer", json={"option_id": "x", "selected_text": "x"}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/recovery-plans/1/select", json={"action": "ask_user"}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/approvals/1/approve-once", json={"project_id": project_id}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/approvals/1/deny", json={"project_id": project_id}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/approvals/1/allow-for-project", json={"project_id": project_id}).status_code == 401
        assert raw_client.patch(f"/api/projects/{project_id}/risks/1", json={"status": "accepted"}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/swarm/simulate-launch").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/swarm/simulations").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/swarm/simulations/latest").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/validation-coverage/summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/execution-policy/summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/coordination/summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/quality-gates/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/quality-gates/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/decision-audit/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/decision-audit/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/runbook").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/runbook/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/runbook/generate").status_code == 401
        assert raw_client.put(f"/api/projects/{project_id}/runbook", json={"content_markdown": "# hi"}).status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/workspace").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/actions").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/widgets", json={"widgets": ["Repo Intelligence"]}).status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/events").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/stream").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/reservations").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/swarm/events").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/questions/pending").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/approvals/pending").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/manager/messages").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/manager/queue").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/docs/generate").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/interview/start", json={"question_budget": 4}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/plan/generate", json={"force_rebuild": True}).status_code == 401
        assert raw_client.get("/api/subagent-policy/summary").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/tasks").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/agents").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/manager/message", json={"message": "What next?"}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/manager/next-step").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia/dynamo").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia/nim").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia/aiq").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/nvidia/aiq/research", json={"query": "test"}).status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia/gpu-diagnostics").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia/local-runtime").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia/validation-plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/nvidia/governance/summary").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/nvidia/governance/plan").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/capability-report").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/capability-report/semantic_code_impact_mapping").status_code == 401
        assert raw_client.post("/api/projects/import-folder", json={"folder_path": sample_workspace("auth-import"), "import_mode": "linked"}).status_code == 401


def test_workspace_tooling_and_codebase_search_routes_return_project_scoped_payloads(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("tooling-search")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    Path(workspace, "app.py").write_text("print('hi')\n# TODO hook quality gate\n", encoding="utf-8")
    project = client.post(
        "/api/projects",
        json={
            "name": "Tooling Search Demo",
            "idea": "Check workspace tooling and repo search",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace, project_name=None: {
            "workspace_path": workspace,
            "available": True,
            "summary": "Repo-native tooling is detectable.",
            "repo_profile": {"python_repo": True, "node_repo": True},
            "tools": [
                {
                    "id": "ruff",
                    "label": "Ruff",
                    "category": "validation",
                    "installed": True,
                    "binary_path": "C:/tools/ruff.exe",
                    "configured": True,
                    "config_files": ["pyproject.toml"],
                    "config_sections": ["[tool.ruff]"],
                    "status": "ready",
                    "recommended_commands": ["ruff check ."],
                    "notes": [],
                },
                {
                    "id": "playwright",
                    "label": "Playwright",
                    "category": "validation",
                    "installed": False,
                    "binary_path": None,
                    "configured": True,
                    "config_files": ["playwright.config.ts"],
                    "config_sections": [],
                    "status": "needs_setup",
                    "recommended_commands": ["playwright test"],
                    "notes": [],
                },
                {
                    "id": "gitleaks",
                    "label": "Gitleaks",
                    "category": "security",
                    "installed": True,
                    "binary_path": "C:/tools/gitleaks.exe",
                    "configured": False,
                    "config_files": [],
                    "config_sections": [],
                    "status": "available",
                    "recommended_commands": ["gitleaks dir . --redact"],
                    "notes": [],
                },
            ],
            "packs": [
                {
                    "id": "validation_evidence_pack",
                    "title": "Validation evidence pack",
                    "status": "needs_setup",
                    "summary": "Validation helpers still need setup.",
                    "tool_ids": ["ruff", "playwright"],
                    "installed_tool_ids": ["ruff"],
                    "missing_tool_ids": ["playwright"],
                },
                {
                    "id": "security_pack",
                    "title": "Security pack",
                    "status": "ready",
                    "summary": "Security lane is available.",
                    "tool_ids": ["gitleaks"],
                    "installed_tool_ids": ["gitleaks"],
                    "missing_tool_ids": [],
                },
            ],
            "recommended_next_steps": ["Install Playwright."],
            "repo_mode_summaries": ["Node and Python lanes detected."],
            "important_paths": ["app.py"],
            "execution_entrypoints": ["python app.py"],
            "runtime_blockers": ["Playwright browser binaries are missing."],
            "validation_evidence_targets": ["Capture a named validation run."],
            "product_lane_statuses": ["python:ready", "browser:needs_setup"],
            "execution_lane_summaries": ["Validation lane exists."],
            "artifact_kind_summaries": ["log:1"],
            "intake_commands": ["rg --files"],
            "notebook_paths": [],
            "notebook_commands": [],
            "validation_commands": ["ruff check .", "playwright test"],
            "observability_commands": [],
            "security_commands": ["gitleaks dir . --redact"],
            "deployment_commands": ["python app.py"],
            "artifact_paths": ["artifacts/build.log"],
            "artifact_inspection_commands": ["type artifacts/build.log"],
            "checkpoint_commands": [],
            "distributed_launcher_commands": [],
            "config_review_paths": [],
            "config_review_commands": [],
            "tensorflow_repo": {"enabled": False},
            "tensorflow_validation_plan": {"status": "not_applicable"},
            "pytorch_repo": {"enabled": False},
            "pytorch_runtime_status": {"status": "not_applicable"},
            "pytorch_validation_plan": {"status": "not_applicable"},
            "spatial3d_repo": {"enabled": False},
            "spatial3d_validation_plan": {"status": "not_applicable"},
        },
    )
    monkeypatch.setattr("manager.shutil.which", lambda command: "C:/tools/rg.exe" if command == "rg" else None)

    class Result:
        returncode = 0
        stdout = "app.py:2:# TODO hook quality gate\n"

    monkeypatch.setattr("manager.subprocess.run", lambda *args, **kwargs: Result())

    tooling = client.get(f"/api/projects/{project_id}/workspace-tooling", headers=bridge_headers)
    assert tooling.status_code == 200
    tooling_payload = tooling.json()
    assert tooling_payload["project_id"] == project_id
    assert tooling_payload["project_name"] == "Tooling Search Demo"
    assert tooling_payload["tool_count"] == len(tooling_payload["tools"]) == 3
    assert tooling_payload["tool_ids"] == ["ruff", "playwright", "gitleaks"]
    assert tooling_payload["installed_tool_count"] == 2
    assert tooling_payload["installed_tool_ids"] == ["ruff", "gitleaks"]
    assert tooling_payload["configured_tool_count"] == 2
    assert tooling_payload["configured_tool_ids"] == ["ruff", "playwright"]
    assert tooling_payload["missing_tool_count"] == 1
    assert tooling_payload["missing_tool_ids"] == ["playwright"]
    assert tooling_payload["tool_statuses"] == ["available", "needs_setup", "ready"]
    assert tooling_payload["tool_status_counts"] == {"available": 1, "needs_setup": 1, "ready": 1}
    assert tooling_payload["tool_status_group_count"] == 3
    assert tooling_payload["tool_categories"] == ["security", "validation"]
    assert tooling_payload["tool_category_counts"] == {"security": 1, "validation": 2}
    assert tooling_payload["tool_category_group_count"] == 2
    assert tooling_payload["pack_count"] == len(tooling_payload["packs"]) == 2
    assert tooling_payload["pack_ids"] == ["validation_evidence_pack", "security_pack"]
    assert tooling_payload["pack_statuses"] == ["needs_setup", "ready"]
    assert tooling_payload["pack_status_counts"] == {"needs_setup": 1, "ready": 1}
    assert tooling_payload["pack_status_group_count"] == 2
    assert tooling_payload["recommended_next_step_count"] == len(tooling_payload["recommended_next_steps"]) == 1
    assert tooling_payload["repo_mode_summary_count"] == len(tooling_payload["repo_mode_summaries"]) == 1
    assert tooling_payload["important_path_count"] == len(tooling_payload["important_paths"]) == 1
    assert tooling_payload["execution_entrypoint_count"] == len(tooling_payload["execution_entrypoints"]) == 1
    assert tooling_payload["runtime_blocker_count"] == len(tooling_payload["runtime_blockers"]) == 1
    assert tooling_payload["validation_evidence_target_count"] == len(tooling_payload["validation_evidence_targets"]) == 1
    assert tooling_payload["product_lane_status_count"] == len(tooling_payload["product_lane_statuses"]) == 2
    assert tooling_payload["execution_lane_summary_count"] == len(tooling_payload["execution_lane_summaries"]) == 1
    assert tooling_payload["artifact_kind_summary_count"] == len(tooling_payload["artifact_kind_summaries"]) == 1
    assert tooling_payload["command_count"] == len(tooling_payload["commands"]) == 6
    assert tooling_payload["commands"] == [
        "rg --files",
        "ruff check .",
        "playwright test",
        "gitleaks dir . --redact",
        "python app.py",
        "type artifacts/build.log",
    ]
    assert "repo_profile" in tooling_payload

    search = client.post(
        f"/api/projects/{project_id}/codebase/search",
        json={"pattern": "TODO", "max_matches": 5},
        headers=bridge_headers,
    )
    assert search.status_code == 200
    payload = search.json()
    assert payload["project_id"] == project_id
    assert payload["search_backend"] == "ripgrep"
    assert payload["matches"][0]["path"] == "app.py"


def test_artifact_and_connector_registry_routes_return_normalized_payloads(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("artifact-connector-registry")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Artifact Connector Demo",
            "idea": "Exercise registry-grade artifact and connector summaries",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda _workspace, project_name=None: {
            "workspace_path": workspace,
            "available": True,
            "summary": "Workspace exposes artifact and inspection lanes.",
            "artifact_paths": ["artifacts/model.onnx", "checkpoints/weights.ckpt"],
            "artifact_kind_summaries": ["onnx:1", "checkpoint:1"],
            "artifact_inspection_commands": ["python inspect_artifacts.py"],
            "config_review_paths": ["configs/train.yaml"],
            "config_review_commands": ["python review_config.py"],
            "validation_evidence_targets": ["artifacts/model.onnx"],
            "execution_entrypoints": ["python train.py"],
            "notebook_paths": ["notebooks/analysis.ipynb"],
            "recommended_next_steps": ["Install artifact validators."],
        },
    )
    monkeypatch.setattr("manager.normalize_integration_registry", lambda registry, accounts=None: registry or {})
    monkeypatch.setattr(
        "manager.build_integration_health",
        lambda registry: {
            "version": 1,
            "family_count": 2,
            "connection_count": 2,
            "authoritative_connection_count": 1,
            "host_imported_count": 1,
            "status_counts": {"connected": 1, "host_detected": 1},
            "recent_action_failures": [],
            "host_import_roots": {"github": ["C:/Users/mike"]},
        },
    )
    monkeypatch.setattr(
        "manager.build_integration_catalog_with_connections",
        lambda registry: [
            {
                "family": "source_control",
                "name": "Source Control",
                "summary": "Repo host is wired.",
                "category": "developer_workflow",
                "providers": ["github"],
                "host_support": ["windows"],
                "available_action_ids": ["create_branch", "open_pr"],
                "status": "connected",
                "connection_source": "manual",
                "host_imported": False,
                "notes": [],
            },
            {
                "family": "design_assets",
                "name": "Design Assets",
                "summary": "Design export lane is visible from host state.",
                "category": "design",
                "providers": ["figma"],
                "host_support": ["windows"],
                "available_action_ids": ["export_tokens"],
                "status": "host_detected",
                "connection_source": "codex_host",
                "host_imported": True,
                "notes": [],
            },
        ],
    )
    monkeypatch.setattr(
        "manager.list_connections",
        lambda registry: [
            {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "manual",
                "host_imported": False,
                "approval_policy": "ask_every_time",
                "notes": [],
            },
            {
                "family": "design_assets",
                "status": "host_detected",
                "providers": ["figma"],
                "connection_source": "codex_host",
                "host_imported": True,
                "approval_policy": "ask_every_time",
                "notes": [],
            },
        ],
    )

    artifact_registry = client.get(f"/api/projects/{project_id}/artifact-registry", headers=bridge_headers)
    assert artifact_registry.status_code == 200, artifact_registry.text
    artifact_payload = artifact_registry.json()
    assert artifact_payload["artifact_count"] == 2
    assert artifact_payload["artifact_kind_counts"] == {"onnx": 1, "checkpoint": 1}
    assert artifact_payload["artifact_extension_count"] == 2
    assert artifact_payload["inspection_command_count"] == 1
    assert artifact_payload["execution_entrypoint_count"] == 1

    connector_registry = client.get("/api/integrations/registry", headers=bridge_headers)
    assert connector_registry.status_code == 200, connector_registry.text
    connector_payload = connector_registry.json()
    assert connector_payload["family_count"] == 2
    assert connector_payload["connection_count"] == 2
    assert connector_payload["ready_family_count"] == 1
    assert connector_payload["provider_counts"] == {"github": 1, "figma": 1}
    assert connector_payload["category_counts"] == {"developer_workflow": 1, "design": 1}
    assert connector_payload["available_action_count"] == 3


def test_artifact_registry_route_promotes_remote_runtime_manifest_signals(client, bridge_headers) -> None:
    workspace = Path(sample_workspace("artifact-registry-remote-runtime-route"))
    runtime_root = workspace / "artifacts" / "remote-execution-governance" / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# remote runtime route\n", encoding="utf-8")
    (workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json").write_text(
        json.dumps({"run_count": 1}, indent=2),
        encoding="utf-8",
    )
    (runtime_root / "remote-adapter-xyz-launch-manifest.json").write_text(
        json.dumps(
            {
                "run_id": "remote-adapter-xyz",
                "target_id": "gpu-linux",
                "transport": "tailscale_ssh",
                "remote_artifact_paths": ["/srv/gpu-work/artifacts/screenshots/boot.png"],
                "session_recording_required": True,
                "session_recording_enabled": True,
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "command_preview": "tailscale ssh gpu-linux.tailnet.ts.net python -m pytest",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    project = client.post(
        "/api/projects",
        json={
            "name": "Artifact Registry Remote Runtime Route",
            "idea": "Surface runtime manifests through the artifact registry route.",
            "workspace_path": workspace.as_posix(),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    artifact_registry = client.get(f"/api/projects/{project_id}/artifact-registry", headers=bridge_headers)
    assert artifact_registry.status_code == 200, artifact_registry.text
    artifact_payload = artifact_registry.json()
    assert "artifacts/remote-execution-governance/runtime/remote-adapter-xyz-launch-manifest.json" in artifact_payload["config_review_paths"]
    assert artifact_payload["artifact_kind_counts"]["remote_execution_runtime_manifest"] == 1
    assert "artifacts/remote-execution-governance/normalized-execution-summary.json" in artifact_payload["validation_evidence_targets"]
    assert "/srv/gpu-work/artifacts/screenshots/boot.png" in artifact_payload["validation_evidence_targets"]
    assert "tailscale ssh gpu-linux.tailnet.ts.net python -m pytest" in artifact_payload["execution_entrypoints"]
    assert any("session-recording artifact" in step for step in artifact_payload["recommended_next_steps"])


def test_artifact_registry_plan_route_writes_remote_runtime_rollup_and_flags_recording_gaps(client, bridge_headers) -> None:
    workspace = Path(sample_workspace("artifact-registry-remote-runtime-plan-route"))
    runtime_root = workspace / "artifacts" / "remote-execution-governance" / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# remote runtime plan route\n", encoding="utf-8")
    (workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json").write_text(
        json.dumps({"run_count": 1}, indent=2),
        encoding="utf-8",
    )
    (runtime_root / "remote-adapter-route-launch-manifest.json").write_text(
        json.dumps(
            {
                "run_id": "remote-adapter-route",
                "target_id": "mac-xcode",
                "transport": "ssh",
                "host": "mac-builder.local",
                "remote_artifact_paths": ["/srv/mac-work/artifacts/screenshots/boot.png"],
                "session_recording_required": True,
                "session_recording_enabled": True,
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "command_preview": "ssh mac-builder.local xcodebuild test",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    project = client.post(
        "/api/projects",
        json={
            "name": "Artifact Registry Remote Runtime Plan Route",
            "idea": "Emit a remote runtime rollup for artifact planning.",
            "workspace_path": workspace.as_posix(),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    artifact_plan = client.post(f"/api/projects/{project_id}/artifact-registry/plan", headers=bridge_headers)
    assert artifact_plan.status_code == 200, artifact_plan.text
    payload = artifact_plan.json()
    assert payload["remote_runtime_rollup_path"] == "artifacts/artifact-registry/remote-runtime-rollup.json"
    assert payload["plan_status"] == "partial"
    assert "remote_session_recording_artifact_gap" in payload["blocking_reasons"]
    rollup = json.loads((workspace / "artifacts" / "artifact-registry" / "remote-runtime-rollup.json").read_text(encoding="utf-8"))
    assert rollup["runtime_manifest_count"] == 1
    assert rollup["target_ids"] == ["mac-xcode"]
    assert rollup["session_recording_artifact_gap_count"] == 1
    assert rollup["execution_entrypoints"] == ["ssh mac-builder.local xcodebuild test"]


def test_quality_gate_and_decision_audit_summary_routes_return_project_governance_payloads(client, bridge_headers) -> None:
    workspace = sample_workspace("governance-summaries")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    Path(workspace, "app.py").write_text("print('hi')\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Governance Summaries Demo",
            "idea": "Exercise quality gate and decision audit summaries",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    quality = client.get(f"/api/projects/{project_id}/quality-gates/summary", headers=bridge_headers)
    assert quality.status_code == 200, quality.text
    quality_payload = quality.json()
    assert quality_payload["project_id"] == project_id
    assert isinstance(quality_payload["summary"], str) and quality_payload["summary"]
    assert quality_payload["gate_count"] >= 0
    assert quality_payload["required_gate_count"] >= 0
    assert isinstance(quality_payload["gate_status_counts"], dict)
    assert isinstance(quality_payload["missing_evidence"], list)

    decision_audit = client.get(f"/api/projects/{project_id}/decision-audit/summary", headers=bridge_headers)
    assert decision_audit.status_code == 200, decision_audit.text
    decision_payload = decision_audit.json()
    assert decision_payload["project_id"] == project_id
    assert isinstance(decision_payload["summary"], str) and decision_payload["summary"]
    assert decision_payload["decision_count"] >= 0
    assert decision_payload["approval_audit_count"] >= 0
    assert isinstance(decision_payload["decision_type_counts"], dict)
    assert isinstance(decision_payload["approval_decision_counts"], dict)


def test_quality_gate_and_decision_audit_plan_routes_generate_governance_manifests(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("governance-plans")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    Path(workspace, "app.py").write_text("print('hi')\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Governance Plans Demo",
            "idea": "Exercise quality gate and decision audit planners",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "main.service.build_quality_gate_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "summary": "Quality gate summary stub.",
            "gate_count": 4,
            "required_gate_count": 3,
            "passed_gate_count": 2,
            "failed_gate_count": 0,
            "pending_gate_count": 1,
            "review_gate_count": 4,
            "gate_status_counts": {"passed": 2, "pending": 1, "review": 1},
            "gate_type_counts": {"tests": 2, "evidence": 2},
            "blocking_gate_titles": ["Collect release evidence"],
            "blocking_gate_count": 1,
            "evidence_item_count": 3,
            "evidence_type_counts": {"log": 1, "screenshot": 1, "trace": 1},
            "missing_evidence": ["coverage report"],
            "missing_evidence_count": 1,
        },
    )
    monkeypatch.setattr(
        "main.service.build_decision_audit_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "summary": "Decision audit summary stub.",
            "decision_count": 5,
            "decision_type_counts": {"approval": 2, "routing": 3},
            "approval_audit_count": 4,
            "approval_decision_counts": {"approved": 3, "denied": 1},
            "approval_actor_counts": {"user": 2, "manager": 2},
            "pending_approval_count": 1,
            "pending_question_count": 1,
            "reversible_decision_count": 3,
            "superseded_decision_count": 1,
            "recent_decision_titles": ["Approve remote lane", "Request more evidence"],
            "recent_audit_actions": ["approve_once", "deny"],
        },
    )

    quality = client.post(f"/api/projects/{project_id}/quality-gates/plan", headers=bridge_headers)
    assert quality.status_code == 200, quality.text
    quality_payload = quality.json()
    assert quality_payload["project_id"] == project_id
    assert quality_payload["plan_status"] in {"ready", "partial"}
    assert quality_payload["manifest_root"] == "artifacts/quality-gates"
    assert quality_payload["gate_rollup_path"] == "artifacts/quality-gates/gate-rollup.json"
    assert quality_payload["evidence_requirements_path"] == "artifacts/quality-gates/evidence-requirements.json"
    assert quality_payload["handoff_checkpoint_path"] == "artifacts/quality-gates/handoff-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "quality-gates" / "gate-rollup.json").exists()
    assert (Path(workspace) / "artifacts" / "quality-gates" / "evidence-requirements.json").exists()
    assert (Path(workspace) / "artifacts" / "quality-gates" / "handoff-checkpoints.json").exists()

    decision = client.post(f"/api/projects/{project_id}/decision-audit/plan", headers=bridge_headers)
    assert decision.status_code == 200, decision.text
    decision_payload = decision.json()
    assert decision_payload["project_id"] == project_id
    assert decision_payload["plan_status"] in {"ready", "partial"}
    assert decision_payload["manifest_root"] == "artifacts/decision-audit"
    assert decision_payload["decision_ledger_path"] == "artifacts/decision-audit/decision-ledger.json"
    assert decision_payload["approval_audit_path"] == "artifacts/decision-audit/approval-audit.json"
    assert decision_payload["pending_actions_path"] == "artifacts/decision-audit/pending-actions.json"
    assert decision_payload["reversibility_review_path"] == "artifacts/decision-audit/reversibility-review.json"
    assert decision_payload["approval_checkpoint_path"] == "artifacts/decision-audit/approval-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "decision-audit" / "decision-ledger.json").exists()
    assert (Path(workspace) / "artifacts" / "decision-audit" / "approval-audit.json").exists()
    assert (Path(workspace) / "artifacts" / "decision-audit" / "pending-actions.json").exists()
    assert (Path(workspace) / "artifacts" / "decision-audit" / "reversibility-review.json").exists()
    assert (Path(workspace) / "artifacts" / "decision-audit" / "approval-checkpoints.json").exists()


def test_artifact_and_connector_governance_plan_routes_generate_governance_manifests(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("artifact-connector-plans")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# demo\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Artifact Connector Plans",
            "idea": "Exercise artifact and connector governance planners",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "main.service.build_project_artifact_registry",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "summary": "Artifacts are present.",
            "artifact_count": 3,
            "artifact_paths": ["artifacts/model.onnx", "data/train.parquet", "reports/eval.json"],
            "artifact_extensions": [".json", ".onnx", ".parquet"],
            "artifact_extension_count": 3,
            "artifact_kind_summaries": ["dataset:1", "model:1", "report:1"],
            "artifact_kind_counts": {"dataset": 1, "model": 1, "report": 1},
            "artifact_kind_count": 3,
            "inspection_command_count": 1,
            "inspection_commands": ["python inspect.py --artifact artifacts/model.onnx"],
            "config_review_path_count": 1,
            "config_review_paths": ["configs/model.yaml"],
            "config_review_command_count": 0,
            "config_review_commands": [],
            "validation_evidence_target_count": 2,
            "validation_evidence_targets": ["reports/eval.json", "data/train.parquet"],
            "execution_entrypoint_count": 1,
            "execution_entrypoints": ["python eval.py --artifact artifacts/model.onnx"],
            "notebook_path_count": 0,
            "notebook_paths": [],
            "recommended_next_steps": ["Review eval drift before publish."],
            "recommended_next_step_count": 1,
        },
    )
    monkeypatch.setattr(
        "main.service.build_connector_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Connector lanes are partially governed.",
            "governance_status": "partial",
            "recommended_operation_mode": "governed_connector_actions",
            "family_count": 2,
            "connected_family_count": 2,
            "live_family_count": 1,
            "ready_family_count": 1,
            "partial_family_count": 1,
            "needs_setup_family_count": 0,
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
            "category_count": 2,
            "categories": ["developer_workflow", "design"],
            "connected_family_ids": ["source_control", "design_assets"],
            "live_family_ids": ["source_control"],
            "authoritative_family_ids": ["source_control"],
            "host_imported_family_ids": ["design_assets"],
            "discovery_ready_family_ids": ["source_control", "design_assets"],
            "execution_ready_family_ids": ["source_control"],
            "blocking_reasons": ["provider_context_missing"],
            "recommended_fixes": ["Reconnect Figma through Mission Control auth."],
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
            ],
            "connector_registry": {
                "summary": "Two connector lanes visible.",
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

    artifact = client.post(f"/api/projects/{project_id}/artifact-registry/plan", headers=bridge_headers)
    assert artifact.status_code == 200, artifact.text
    artifact_payload = artifact.json()
    assert artifact_payload["project_id"] == project_id
    assert artifact_payload["plan_status"] in {"ready", "partial"}
    assert artifact_payload["manifest_root"] == "artifacts/artifact-registry"
    assert artifact_payload["inventory_path"] == "artifacts/artifact-registry/inventory.json"
    assert artifact_payload["kind_rollup_path"] == "artifacts/artifact-registry/kind-rollup.json"
    assert artifact_payload["inspection_plan_path"] == "artifacts/artifact-registry/inspection-plan.json"
    assert artifact_payload["validation_targets_path"] == "artifacts/artifact-registry/validation-targets.json"
    assert artifact_payload["execution_surface_path"] == "artifacts/artifact-registry/execution-surface.json"
    assert artifact_payload["remote_runtime_rollup_path"] == "artifacts/artifact-registry/remote-runtime-rollup.json"
    assert (Path(workspace) / "artifacts" / "artifact-registry" / "inventory.json").exists()
    assert (Path(workspace) / "artifacts" / "artifact-registry" / "kind-rollup.json").exists()
    assert (Path(workspace) / "artifacts" / "artifact-registry" / "inspection-plan.json").exists()
    assert (Path(workspace) / "artifacts" / "artifact-registry" / "validation-targets.json").exists()
    assert (Path(workspace) / "artifacts" / "artifact-registry" / "execution-surface.json").exists()
    assert (Path(workspace) / "artifacts" / "artifact-registry" / "remote-runtime-rollup.json").exists()

    connector = client.post(f"/api/projects/{project_id}/connector-governance/plan", headers=bridge_headers)
    assert connector.status_code == 200, connector.text
    connector_payload = connector.json()
    assert connector_payload["project_id"] == project_id
    assert connector_payload["plan_status"] in {"ready", "partial"}
    assert connector_payload["recommended_operation_mode"] == "governed_connector_actions"
    assert connector_payload["manifest_root"] == "artifacts/connector-governance"
    assert connector_payload["family_rollup_path"] == "artifacts/connector-governance/family-rollup.json"
    assert connector_payload["discovery_lanes_path"] == "artifacts/connector-governance/discovery-lanes.json"
    assert connector_payload["execution_lanes_path"] == "artifacts/connector-governance/execution-lanes.json"
    assert connector_payload["provider_context_path"] == "artifacts/connector-governance/provider-context.json"
    assert connector_payload["approval_guardrails_path"] == "artifacts/connector-governance/approval-guardrails.json"
    assert connector_payload["connector_registry_path"] == "artifacts/connector-governance/connector-registry.json"
    assert (Path(workspace) / "artifacts" / "connector-governance" / "family-rollup.json").exists()
    assert (Path(workspace) / "artifacts" / "connector-governance" / "discovery-lanes.json").exists()
    assert (Path(workspace) / "artifacts" / "connector-governance" / "execution-lanes.json").exists()
    assert (Path(workspace) / "artifacts" / "connector-governance" / "provider-context.json").exists()
    assert (Path(workspace) / "artifacts" / "connector-governance" / "approval-guardrails.json").exists()
    assert (Path(workspace) / "artifacts" / "connector-governance" / "connector-registry.json").exists()

    family_rollup = json.loads((Path(workspace) / "artifacts" / "connector-governance" / "family-rollup.json").read_text(encoding="utf-8"))
    assert family_rollup["connected_family_ids"] == ["source_control", "design_assets"]
    assert family_rollup["host_imported_family_ids"] == ["design_assets"]

    discovery_lanes = json.loads((Path(workspace) / "artifacts" / "connector-governance" / "discovery-lanes.json").read_text(encoding="utf-8"))
    assert discovery_lanes["discovery_requirements"]["host_import_review_required"] is True
    assert [item["family"] for item in discovery_lanes["discovery_ready_families"]] == ["source_control", "design_assets"]

    execution_lanes = json.loads((Path(workspace) / "artifacts" / "connector-governance" / "execution-lanes.json").read_text(encoding="utf-8"))
    assert execution_lanes["safe_command_family_ids"] == ["source_control"]
    assert execution_lanes["execution_requirements"]["preview_or_safe_command_required"] is True

    provider_context = json.loads((Path(workspace) / "artifacts" / "connector-governance" / "provider-context.json").read_text(encoding="utf-8"))
    assert provider_context["provider_context_missing_family_ids"] == ["design_assets"]
    assert provider_context["provider_context_verified_family_ids"] == ["source_control"]

    approval_guardrails = json.loads((Path(workspace) / "artifacts" / "connector-governance" / "approval-guardrails.json").read_text(encoding="utf-8"))
    assert approval_guardrails["approval_requirements"]["authoritative_lane_required_for_publish"] is True
    assert approval_guardrails["mutation_guard_family_ids"] == ["source_control"]


def test_external_discovery_governance_plan_route_generates_governance_manifests(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("external-discovery-plan")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# demo\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "External Discovery Plan",
            "idea": "Exercise external discovery planning",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "main.service.build_external_discovery_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "External discovery is partially governed.",
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
            "authoritative_lane_count": 1,
            "live_lane_count": 2,
            "host_imported_lane_count": 1,
            "discovery_ready_lane_count": 3,
            "execution_ready_lane_count": 1,
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
                "summary": "Connector governance summary stub.",
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
                "connector_registry": {"summary": "ready", "family_count": 3, "connection_count": 3, "authoritative_connection_count": 2, "host_imported_count": 1, "status_counts": {"connected": 2, "host_detected": 1}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 2, "ready_families": ["google_drive", "support_desk"], "provider_counts": {"google_drive": 1, "figma": 1, "zendesk": 1}, "provider_count": 3, "category_counts": {"storage": 1, "design": 1, "support": 1}, "category_count": 3, "connection_source_counts": {"manual": 2, "codex_host": 1}, "connection_source_count": 2, "available_action_count": 5, "catalog": [], "connections": []},
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
                "storage_lanes": [{"lane_id": "local_fs", "title": "Local Filesystem", "status": "connected"}],
                "connector_registry": {"summary": "ready", "family_count": 1, "connection_count": 1, "authoritative_connection_count": 1, "host_imported_count": 0, "status_counts": {"connected": 1}, "host_import_roots": {}, "recent_action_failures": [], "ready_family_count": 1, "ready_families": ["storage"], "provider_counts": {"local_fs": 1}, "provider_count": 1, "category_counts": {"storage": 1}, "category_count": 1, "connection_source_counts": {"mission_control": 1}, "connection_source_count": 1, "available_action_count": 1, "catalog": [], "connections": []},
                "platform_runners": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": "linux", "lane_count": 1, "ready_lane_count": 1, "partial_lane_count": 0, "unavailable_lane_count": 0, "ready_lane_ids": ["linux"], "partial_lane_ids": [], "unavailable_lane_ids": [], "lanes": []},
                "artifact_transport": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "summary": "stub", "selected_target_id": "linux", "preflight_ready": True, "sync_enabled": True, "recommended_transport_mode": "brokered_sync", "blocking_reasons": [], "ready_platform_lanes": ["linux"], "partial_platform_lanes": [], "notes": [], "artifact_registry": {"project_id": project.id, "project_name": project.name, "workspace_path": project.workspace_path, "available": True, "summary": "stub", "artifact_count": 1, "artifact_paths": ["data/train.parquet"], "artifact_extensions": [".parquet"], "artifact_extension_count": 1, "artifact_kind_summaries": ["dataset:1"], "artifact_kind_counts": {"dataset": 1}, "artifact_kind_count": 1, "inspection_command_count": 0, "inspection_commands": [], "config_review_path_count": 0, "config_review_paths": [], "config_review_command_count": 0, "config_review_commands": [], "validation_evidence_target_count": 1, "validation_evidence_targets": ["data/train.parquet"], "execution_entrypoint_count": 0, "execution_entrypoints": [], "notebook_path_count": 0, "notebook_paths": []}, "connector_registry": {"summary": "ready"}, "artifact_contract": {"sync_enabled": True}, "connector_contract": {"available_families": ["storage"]}},
            },
        },
    )

    response = client.post(f"/api/projects/{project_id}/external-discovery/plan", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["recommended_operation_mode"] == "connector_plus_file_graph"
    assert payload["manifest_root"] == "artifacts/external-discovery-governance"
    assert payload["lane_inventory_path"] == "artifacts/external-discovery-governance/lane-inventory.json"
    assert payload["bounded_crawl_plan_path"] == "artifacts/external-discovery-governance/bounded-crawl-plan.json"
    assert payload["storage_sync_plan_path"] == "artifacts/external-discovery-governance/storage-sync-plan.json"
    assert payload["connector_contract_path"] == "artifacts/external-discovery-governance/connector-contract.json"
    assert payload["approval_checkpoint_path"] == "artifacts/external-discovery-governance/approval-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "external-discovery-governance" / "lane-inventory.json").exists()
    assert (Path(workspace) / "artifacts" / "external-discovery-governance" / "bounded-crawl-plan.json").exists()
    assert (Path(workspace) / "artifacts" / "external-discovery-governance" / "storage-sync-plan.json").exists()
    assert (Path(workspace) / "artifacts" / "external-discovery-governance" / "connector-contract.json").exists()
    assert (Path(workspace) / "artifacts" / "external-discovery-governance" / "approval-checkpoints.json").exists()


def test_device_broker_plan_route_generates_governance_manifests(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("device-broker-plan")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# demo\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Device Broker Plan",
            "idea": "Exercise device broker planning",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "main.service.build_device_broker_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Broker summary stub.",
            "preflight_ready": True,
            "selected_target_id": "gpu-box",
            "selected_target_probe_status": "ready",
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-box"],
            "recommended_target_ids": ["gpu-box"],
            "blocking_reasons": [],
            "ready_target_count": 1,
            "capability_index": {
                "target_count": 1,
                "ready_target_count": 1,
                "toolchain_counts": {"cuda12": 1},
                "command_family_counts": {"git": 1},
                "result_format_counts": {"json": 1},
                "gpu_counts": {"RTX 4090": 1},
                "trust_level_counts": {"trusted": 1},
                "connector_family_counts": {"source_control": 1},
                "targets": [{"target_id": "gpu-box", "label": "GPU Box", "transport": "tailscale_ssh", "host": "gpu-box.tailnet.ts.net", "ready": True}],
            },
            "remote_execution": {
                "policy": {"enabled": True, "preferred_target_id": "gpu-box"},
                "registry_summary": {"target_count": 1},
                "required_runner_family": "external_adapter",
                "require_write_access": True,
                "eligible_target_count": 1,
                "ready_candidate_count": 1,
                "ready_candidate_ids": ["gpu-box"],
                "selected_target": {"id": "gpu-box", "label": "GPU Box"},
                "selected_target_id": "gpu-box",
                "selected_target_probe_status": "ready",
                "preflight_ready": True,
                "blocking_reasons": [],
                "candidates": [{"target_id": "gpu-box", "ready": True}],
                "artifact_contract": {
                    "sync_enabled": True,
                    "required": True,
                    "artifact_path_allowlist": ["artifacts/model.onnx"],
                    "artifact_kind_summaries": ["model:1"],
                    "local_artifact_paths": ["artifacts/model.onnx"],
                    "local_artifact_path_count": 1,
                    "artifact_inspection_commands": ["python inspect.py"],
                    "target_artifact_roots": ["/srv/shadow/artifacts"],
                    "selected_artifact_root": "/srv/shadow/artifacts",
                    "remote_workspace_root": "/srv/shadow",
                    "remote_workspace_artifact_paths": ["/srv/shadow/artifacts/model.onnx"],
                    "preflight_ready": True,
                    "blocking_reasons": [],
                    "notes": [],
                },
                "connector_contract": {
                    "required_connector_families": ["source_control"],
                    "target_connector_families": ["source_control"],
                    "allow_host_integrated_connectors": False,
                    "require_connector_authority": True,
                    "available_families": ["source_control"],
                    "available_connector_count": 1,
                    "missing_required_families": [],
                    "connections": [],
                    "preflight_ready": True,
                    "blocking_reasons": [],
                    "notes": [],
                },
                "broker_contract": {
                    "allowed_trust_levels": ["trusted"],
                    "required_toolchains": ["cuda12"],
                    "required_command_families": ["git"],
                    "required_result_formats": ["json"],
                    "require_session_recording": True,
                    "require_target_workspace_root": True,
                    "required_repo_roots": ["/srv/shadow"],
                    "required_path_prefixes": ["artifacts"],
                    "target_gpu": "RTX 4090",
                    "target_toolchains": ["cuda12"],
                    "target_command_families": ["git"],
                    "target_result_formats": ["json"],
                    "session_recording_enabled": True,
                    "target_repo_roots": ["/srv/shadow"],
                    "target_path_prefixes": ["artifacts"],
                    "preflight_ready": True,
                    "blocking_reasons": [],
                    "notes": [],
                },
            },
            "artifact_registry": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "available": True,
                "summary": "Artifacts are present.",
                "artifact_count": 1,
                "artifact_paths": ["artifacts/model.onnx"],
                "artifact_extensions": [".onnx"],
                "artifact_extension_count": 1,
                "artifact_kind_summaries": ["model:1"],
                "artifact_kind_counts": {"model": 1},
                "artifact_kind_count": 1,
                "inspection_command_count": 1,
                "inspection_commands": ["python inspect.py"],
                "config_review_path_count": 0,
                "config_review_paths": [],
                "config_review_command_count": 0,
                "config_review_commands": [],
                "validation_evidence_target_count": 1,
                "validation_evidence_targets": ["artifacts/model.onnx"],
                "execution_entrypoint_count": 1,
                "execution_entrypoints": ["python eval.py"],
                "notebook_path_count": 0,
                "notebook_paths": [],
                "recommended_next_steps": [],
                "recommended_next_step_count": 0,
            },
            "connector_registry": {
                "summary": "Connector registry ready.",
                "family_count": 1,
                "connection_count": 1,
                "authoritative_connection_count": 1,
                "host_imported_count": 0,
                "status_counts": {"connected": 1},
                "host_import_roots": {},
                "recent_action_failures": [],
                "ready_family_count": 1,
                "ready_families": ["source_control"],
                "provider_counts": {"github": 1},
                "provider_count": 1,
                "category_counts": {"developer_workflow": 1},
                "category_count": 1,
                "connection_source_counts": {"mission_control": 1},
                "connection_source_count": 1,
                "available_action_count": 1,
                "catalog": [],
                "connections": [],
            },
        },
    )

    response = client.post(f"/api/projects/{project_id}/device-broker/plan", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["plan_status"] in {"ready", "partial"}
    assert payload["preflight_ready"] is True
    assert payload["selected_target_id"] == "gpu-box"
    assert payload["manifest_root"] == "artifacts/device-broker"
    assert payload["target_index_path"] == "artifacts/device-broker/target-index.json"
    assert payload["broker_selection_path"] == "artifacts/device-broker/broker-selection.json"
    assert payload["policy_contract_path"] == "artifacts/device-broker/policy-contract.json"
    assert payload["artifact_contract_path"] == "artifacts/device-broker/artifact-contract.json"
    assert payload["connector_contract_path"] == "artifacts/device-broker/connector-contract.json"
    assert payload["approval_checkpoint_path"] == "artifacts/device-broker/approval-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "device-broker" / "target-index.json").exists()
    assert (Path(workspace) / "artifacts" / "device-broker" / "broker-selection.json").exists()
    assert (Path(workspace) / "artifacts" / "device-broker" / "policy-contract.json").exists()
    assert (Path(workspace) / "artifacts" / "device-broker" / "artifact-contract.json").exists()
    assert (Path(workspace) / "artifacts" / "device-broker" / "connector-contract.json").exists()
    assert (Path(workspace) / "artifacts" / "device-broker" / "approval-checkpoints.json").exists()


def test_host_and_runner_plan_routes_generate_governance_manifests(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("host-runner-plans")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# demo\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Host Runner Plans",
            "idea": "Exercise host and runner planners",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "main.service.build_host_capability_index_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Host capability summary stub.",
            "selection_status": "ready",
            "selected_target_id": "gpu-box",
            "selected_target_probe_status": "ready",
            "selected_target_status": "ready",
            "required_runner_family": "external_adapter",
            "target_count": 2,
            "ready_target_count": 1,
            "eligible_target_count": 1,
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-box"],
            "rejected_target_count": 1,
            "recommended_target_ids": ["gpu-box"],
            "rejected_target_ids": ["limited-macos"],
            "allowed_trust_levels": ["trusted"],
            "required_toolchains": ["cuda12"],
            "required_command_families": ["git"],
            "required_result_formats": ["json"],
            "required_connector_families": ["source_control"],
            "blocking_reasons": [],
            "notes": ["Policy requirements are explicit."],
            "matches": [
                {"target_id": "gpu-box", "label": "GPU Box", "transport": "tailscale_ssh", "host": "gpu-box.tailnet.ts.net", "os_family": "linux", "architecture": "x86_64", "gpu": "RTX 4090", "trust_level": "trusted", "ready": True, "selected": True, "status": "ready", "runner_families": ["external_adapter"], "toolchains": ["cuda12"], "command_families": ["git"], "result_formats": ["json"], "connector_families": ["source_control"], "rejected_reasons": [], "notes": ["Selected broker target for the current project policy."]},
                {"target_id": "limited-macos", "label": "Limited Mac", "transport": "ssh", "host": "limited-macos.local", "os_family": "macos", "architecture": "arm64", "gpu": None, "trust_level": "limited", "ready": True, "selected": False, "status": "blocked", "runner_families": ["external_adapter"], "toolchains": ["python3.11"], "command_families": ["python"], "result_formats": ["text"], "connector_families": [], "rejected_reasons": ["trust level mismatch"], "notes": []},
            ],
        },
    )
    monkeypatch.setattr(
        "main.service.build_remote_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Remote runner summary stub.",
            "selected_target_id": "gpu-box",
            "selected_target_probe_status": "ready",
            "required_runner_family": "external_adapter",
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-box"],
            "route_count": 3,
            "ready_route_count": 1,
            "partial_route_count": 1,
            "unavailable_route_count": 1,
            "ready_route_ids": ["tailscale_ssh"],
            "partial_route_ids": ["windows_host"],
            "unavailable_route_ids": ["plain_ssh"],
            "adapter_count": 3,
            "ready_adapter_count": 1,
            "partial_adapter_count": 1,
            "unavailable_adapter_count": 1,
            "ready_adapter_ids": ["tailscale_ssh"],
            "partial_adapter_ids": ["windows_host"],
            "unavailable_adapter_ids": ["plain_ssh"],
            "blocking_reasons": [],
            "notes": ["Remote fabric is mostly sane."],
            "routes": [
                {"route_id": "tailscale_ssh", "title": "Tailscale SSH Adapter", "status": "ready", "summary": "ready", "transport": "tailscale_ssh", "target_ids": ["gpu-box"], "selected_target_ids": ["gpu-box"], "os_families": ["linux"], "ready_target_count": 1, "selected_ready": True, "session_recording_coverage": "ready", "result_format_coverage": "ready", "command_family_coverage": "ready", "notes": []},
                {"route_id": "windows_host", "title": "Windows Host Adapter", "status": "partial", "summary": "partial", "transport": "host_family", "target_ids": ["win-box"], "selected_target_ids": [], "os_families": ["windows"], "ready_target_count": 0, "selected_ready": False, "session_recording_coverage": "partial", "result_format_coverage": "blocked", "command_family_coverage": "blocked", "notes": []},
                {"route_id": "plain_ssh", "title": "Plain SSH Adapter", "status": "unavailable", "summary": "unavailable", "transport": "ssh", "target_ids": [], "selected_target_ids": [], "os_families": [], "ready_target_count": 0, "selected_ready": False, "session_recording_coverage": "not_applicable", "result_format_coverage": "not_applicable", "command_family_coverage": "not_applicable", "notes": []},
            ],
            "adapters": [
                {"adapter_id": "tailscale_ssh", "title": "Tailscale SSH Adapter", "status": "ready", "summary": "ready", "transport": "tailscale_ssh", "target_ids": ["gpu-box"], "selected_target_ids": ["gpu-box"], "os_families": ["linux"], "ready_target_count": 1, "selected_ready": True, "session_recording_coverage": "ready", "result_format_coverage": "ready", "command_family_coverage": "ready", "notes": []},
                {"adapter_id": "windows_host", "title": "Windows Host Adapter", "status": "partial", "summary": "partial", "transport": "host_family", "target_ids": ["win-box"], "selected_target_ids": [], "os_families": ["windows"], "ready_target_count": 0, "selected_ready": False, "session_recording_coverage": "partial", "result_format_coverage": "blocked", "command_family_coverage": "blocked", "notes": []},
                {"adapter_id": "plain_ssh", "title": "Plain SSH Adapter", "status": "unavailable", "summary": "unavailable", "transport": "ssh", "target_ids": [], "selected_target_ids": [], "os_families": [], "ready_target_count": 0, "selected_ready": False, "session_recording_coverage": "not_applicable", "result_format_coverage": "not_applicable", "command_family_coverage": "not_applicable", "notes": []},
            ],
        },
    )
    monkeypatch.setattr(
        "main.service.build_platform_runner_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Platform runner summary stub.",
            "selected_target_id": "gpu-box",
            "selected_target_probe_status": "ready",
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-box"],
            "route_count": 1,
            "ready_route_count": 1,
            "selected_route_count": 1,
            "selected_ready_route_count": 1,
            "partial_route_count": 0,
            "unavailable_route_count": 0,
            "ready_route_ids": ["plain_ssh"],
            "selected_route_ids": ["plain_ssh"],
            "selected_ready_route_ids": ["plain_ssh"],
            "partial_route_ids": [],
            "unavailable_route_ids": [],
            "lane_count": 3,
            "ready_lane_count": 2,
            "partial_lane_count": 1,
            "unavailable_lane_count": 0,
            "ready_lane_ids": ["linux", "unity"],
            "partial_lane_ids": ["browser"],
            "unavailable_lane_ids": [],
            "lanes": [
                {"lane_id": "linux", "title": "Linux Runner", "status": "ready", "summary": "ready", "target_ids": ["gpu-box"], "target_count": 1, "selected_target_ids": ["gpu-box"], "os_families": ["linux"], "toolchains": ["cuda12"], "command_families": ["git"], "route_ids": ["plain_ssh"], "ready_route_ids": ["plain_ssh"], "selected_route_ids": ["plain_ssh"], "selected_ready_route_ids": ["plain_ssh"], "recommended_commands": ["python -m pytest"], "notes": []},
                {"lane_id": "unity", "title": "Unity Runner", "status": "ready", "summary": "ready", "target_ids": ["gpu-box"], "target_count": 1, "selected_target_ids": [], "os_families": ["linux"], "toolchains": ["unity6000"], "command_families": ["unity_batchmode"], "route_ids": ["plain_ssh"], "ready_route_ids": ["plain_ssh"], "selected_route_ids": [], "selected_ready_route_ids": [], "recommended_commands": ["Unity -batchmode -runTests"], "notes": []},
                {"lane_id": "browser", "title": "Browser Runner", "status": "partial", "summary": "partial", "target_ids": [], "target_count": 0, "selected_target_ids": [], "os_families": [], "toolchains": ["playwright"], "command_families": ["playwright"], "route_ids": [], "ready_route_ids": [], "selected_route_ids": [], "selected_ready_route_ids": [], "recommended_commands": ["playwright test"], "notes": []},
            ],
        },
    )

    host = client.post(f"/api/projects/{project_id}/host-capability-index/plan", headers=bridge_headers)
    assert host.status_code == 200, host.text
    host_payload = host.json()
    assert host_payload["manifest_root"] == "artifacts/host-capability-index"
    assert host_payload["target_matrix_path"] == "artifacts/host-capability-index/target-matrix.json"
    assert host_payload["eligibility_report_path"] == "artifacts/host-capability-index/eligibility-report.json"
    assert host_payload["policy_requirements_path"] == "artifacts/host-capability-index/policy-requirements.json"
    assert host_payload["selection_checkpoint_path"] == "artifacts/host-capability-index/selection-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "host-capability-index" / "target-matrix.json").exists()

    remote = client.post(f"/api/projects/{project_id}/remote-runners/plan", headers=bridge_headers)
    assert remote.status_code == 200, remote.text
    remote_payload = remote.json()
    assert remote_payload["manifest_root"] == "artifacts/remote-runners"
    assert remote_payload["route_inventory_path"] == "artifacts/remote-runners/runner-route-inventory.json"
    assert remote_payload["adapter_inventory_path"] == "artifacts/remote-runners/adapter-inventory.json"
    assert remote_payload["runner_family_inventory_path"] == "artifacts/remote-runners/runner-family-inventory.json"
    assert remote_payload["coverage_report_path"] == "artifacts/remote-runners/coverage-report.json"
    assert remote_payload["target_binding_path"] == "artifacts/remote-runners/target-binding.json"
    assert remote_payload["approval_checkpoint_path"] == "artifacts/remote-runners/approval-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "remote-runners" / "runner-route-inventory.json").exists()
    assert (Path(workspace) / "artifacts" / "remote-runners" / "adapter-inventory.json").exists()
    assert (Path(workspace) / "artifacts" / "remote-runners" / "runner-family-inventory.json").exists()

    platform = client.post(f"/api/projects/{project_id}/platform-runners/plan", headers=bridge_headers)
    assert platform.status_code == 200, platform.text
    platform_payload = platform.json()
    assert platform_payload["manifest_root"] == "artifacts/platform-runners"
    assert platform_payload["route_inventory_path"] == "artifacts/platform-runners/route-inventory.json"
    assert platform_payload["lane_inventory_path"] == "artifacts/platform-runners/lane-inventory.json"
    assert platform_payload["native_tooling_path"] == "artifacts/platform-runners/native-tooling.json"
    assert platform_payload["execution_matrix_path"] == "artifacts/platform-runners/execution-matrix.json"
    assert platform_payload["approval_checkpoint_path"] == "artifacts/platform-runners/approval-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "platform-runners" / "route-inventory.json").exists()
    assert (Path(workspace) / "artifacts" / "platform-runners" / "lane-inventory.json").exists()


def test_advanced_governance_plan_routes_generate_manifest_clusters(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("advanced-governance-plans")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# demo\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Advanced Governance Plans",
            "idea": "Exercise advanced governance planners",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "main.service.build_dataset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Dataset governance summary stub.",
            "governance_status": "ready",
            "dataset_contract_status": "ready",
            "data_hygiene_status": "ready",
            "repo_mode_enabled": True,
            "tensorflow_enabled": True,
            "pytorch_enabled": True,
            "detected_frameworks": ["TensorFlow", "PyTorch"],
            "detected_product_workflows": ["training_pipeline", "evaluation_pipeline"],
            "dataset_artifact_count": 3,
            "dataset_artifact_paths": ["data/train.parquet", "data/valid.parquet", "artifacts/model.onnx"],
            "dataset_artifact_extensions": [".parquet", ".onnx"],
            "schema_or_config_count": 2,
            "schema_or_config_paths": ["configs/schema.pbtxt", "configs/dataset.yaml"],
            "checkpoint_artifact_count": 1,
            "checkpoint_artifact_paths": ["checkpoints/model.ckpt"],
            "provenance_signal_count": 1,
            "provenance_signals": ["metadata/dataset_manifest.json"],
            "split_signal_count": 1,
            "split_signals": ["configs/dataset.yaml"],
            "evaluation_signal_count": 2,
            "evaluation_signals": ["python eval.py --limit 8", "reports/eval_metrics.json"],
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
            "notes": ["Dataset lane is ready for governed evaluation."],
            "file_governance": {"recommended_operation_mode": "hybrid_connector_sync"},
            "nvidia_governance": {"recommended_execution_lane": "nvidia_dynamo", "governance_status": "ready"},
        },
    )
    monkeypatch.setattr(
        "main.service.build_model_refactor_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Model refactor summary stub.",
            "governance_status": "ready",
            "repo_mode_enabled": True,
            "detected_frameworks": ["TensorFlow", "PyTorch"],
            "compatibility_contract_status": "ready",
            "benchmark_readiness_status": "ready",
            "rollback_readiness_status": "ready",
            "evaluation_first_ready": True,
            "recommended_execution_lane": "nvidia_dynamo",
            "model_artifact_count": 3,
            "model_artifact_paths": ["artifacts/model.onnx", "exports/saved_model/saved_model.pb", "checkpoints/model.ckpt"],
            "model_artifact_extensions": [".onnx", ".pb", ".ckpt"],
            "compatibility_signal_count": 1,
            "compatibility_signals": ["configs/serving_contract.yaml"],
            "benchmark_signal_count": 1,
            "benchmark_signals": ["reports/benchmark.json"],
            "rollback_signal_count": 1,
            "rollback_signals": ["checkpoints/model.ckpt"],
            "validation_signal_count": 2,
            "validation_signals": ["python eval.py --limit 8", "reports/eval_metrics.json"],
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Refactor lane has contract and rollback coverage."],
            "dataset_governance": {
                "governance_status": "ready",
                "validation_status": "ready",
                "checkpoint_artifact_paths": ["checkpoints/model.ckpt"],
            },
            "nvidia_governance": {"recommended_execution_lane": "nvidia_dynamo", "governance_status": "ready"},
        },
    )
    monkeypatch.setattr(
        "main.service.build_native_app_validation_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Native app validation summary stub.",
            "governance_status": "ready",
            "detected_platforms": ["windows", "ios", "browser"],
            "governed_surface_count": 4,
            "game_engine_surface_count": 1,
            "game_engine_surface_ids": ["unity"],
            "game_engine_governance_status": "ready",
            "game_engine_playable_contract_status": "ready",
            "game_engine_normalized_results_summary_path": "artifacts/game-engine-governance/normalized-results-summary.json",
            "game_engine_normalized_summary_count": 1,
            "game_engine_normalized_passed_count": 0,
            "game_engine_normalized_failed_count": 0,
            "game_engine_normalized_missing_count": 1,
            "game_engine_normalized_publish_ready": False,
            "game_engine_normalized_results_status": "partial",
            "game_engine_publish_gate_status": "blocked",
            "game_engine_publish_blocker_count": 1,
            "game_engine_publish_blockers": [
                "Normalized Unity/Unreal result rollups still contain missing, failed, or parse-error evidence."
            ],
            "ready_runner_lanes": ["windows", "ios"],
            "partial_runner_lanes": ["browser"],
            "unavailable_runner_lanes": [],
            "installable_artifact_count": 2,
            "installable_artifact_paths": ["dist/app-installer.exe", "dist/app.ipa"],
            "installable_artifact_extensions": [".exe", ".ipa"],
            "log_artifact_count": 1,
            "log_artifact_paths": ["artifacts/logs/run.log"],
            "screenshot_artifact_count": 1,
            "screenshot_artifact_paths": ["artifacts/screenshots/boot.png"],
            "trace_artifact_count": 1,
            "trace_artifact_paths": ["artifacts/traces/trace.json"],
            "crash_artifact_count": 1,
            "crash_artifact_paths": ["artifacts/crash/crash.dmp"],
            "coverage_artifact_count": 1,
            "coverage_artifact_paths": ["artifacts/coverage/coverage.xml"],
            "performance_artifact_count": 1,
            "performance_artifact_paths": ["artifacts/perf/profile.json"],
            "evidence_pipeline_status": "ready",
            "recommended_runner_lanes": ["windows", "ios", "browser"],
            "recommended_transport_mode": "brokered_sync",
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Evidence bundle contract is ready."],
            "platform_runners": {
                "summary": "Platform lanes ready.",
                "ready_lane_ids": ["windows", "ios"],
                "partial_lane_ids": ["browser"],
                "unavailable_lane_ids": [],
            },
            "artifact_transport": {
                "summary": "Artifact transport ready.",
                "ready_platform_lanes": ["windows", "ios"],
                "partial_platform_lanes": ["browser"],
            },
        },
    )
    monkeypatch.setattr(
        "main.service.build_remote_execution_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Remote execution governance summary stub.",
            "governance_status": "ready",
            "policy_enabled": True,
            "selected_target_id": "gpu-box",
            "selected_target_probe_status": "ready",
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
            "ready_candidate_ids": ["gpu-box"],
            "ready_target_count": 1,
            "ready_lane_count": 2,
            "ready_lane_ids": ["linux", "unity"],
            "ready_route_count": 1,
            "ready_route_ids": ["plain_ssh"],
            "selected_ready_lane_count": 1,
            "selected_ready_lane_ids": ["linux"],
            "selected_ready_route_count": 1,
            "selected_ready_route_ids": ["plain_ssh"],
            "partial_route_count": 1,
            "partial_route_ids": ["browser_socket"],
            "allowed_trust_levels": ["trusted"],
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts", "src"],
            "required_result_formats": ["json"],
            "required_command_families": ["git", "python"],
            "required_toolchains": ["cuda12"],
            "minimum_command_runtime_seconds": 900,
            "minimum_file_transfer_quota_mb": 512,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Broker contract is fully satisfied."],
        },
    )
    monkeypatch.setattr(
        "main.service.preview_project_remote_execution",
        lambda db, project: {
            "policy": {
                "enabled": True,
                "require_session_recording": True,
            },
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "selected_artifact_root": "/srv/shadow/artifacts",
                "remote_workspace_root": "/srv/shadow",
                "preflight_ready": True,
            },
            "connector_contract": {
                "required_connector_families": ["source_control"],
                "available_families": ["source_control"],
                "missing_required_families": [],
                "preflight_ready": True,
            },
            "broker_contract": {
                "target_gpu": "RTX 4090",
                "target_toolchains": ["cuda12"],
                "target_command_families": ["git", "python"],
                "target_result_formats": ["json"],
                "target_repo_roots": ["/srv/shadow"],
                "target_path_prefixes": ["artifacts", "src"],
                "target_command_runtime_seconds": 1800,
                "target_file_transfer_quota_mb": 2048,
                "session_recording_enabled": True,
                "preflight_ready": True,
            },
            "selected_target": {
                "id": "gpu-box",
                "label": "GPU Box",
                "transport": "tailscale_ssh",
                "os_family": "linux",
            },
        },
    )
    monkeypatch.setattr(
        "main.service.build_nvidia_execution_governance_summary",
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
            "selected_remote_target_id": "gpu-box",
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
            "platform_runners": {"summary": "GPU lanes ready.", "selected_target_id": "gpu-box", "ready_lane_ids": ["linux"]},
            "device_broker": {"summary": "Broker sees one GPU host.", "selected_target_id": "gpu-box"},
        },
    )

    dataset = client.post(f"/api/projects/{project_id}/dataset-governance/plan", headers=bridge_headers)
    assert dataset.status_code == 200, dataset.text
    dataset_payload = dataset.json()
    assert dataset_payload["manifest_root"] == "artifacts/dataset-governance"
    assert dataset_payload["dataset_contract_path"] == "artifacts/dataset-governance/dataset-contract.json"
    assert dataset_payload["data_profile_path"] == "artifacts/dataset-governance/data-profile.json"
    assert dataset_payload["pii_review_path"] == "artifacts/dataset-governance/pii-review.json"
    assert dataset_payload["split_plan_path"] == "artifacts/dataset-governance/split-plan.json"
    assert dataset_payload["duplication_audit_path"] == "artifacts/dataset-governance/duplication-audit.json"
    assert dataset_payload["corruption_audit_path"] == "artifacts/dataset-governance/corruption-audit.json"
    assert dataset_payload["evaluation_plan_path"] == "artifacts/dataset-governance/evaluation-plan.json"
    assert dataset_payload["approval_checkpoint_path"] == "artifacts/dataset-governance/approval-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "dataset-governance" / "dataset-contract.json").exists()

    model = client.post(f"/api/projects/{project_id}/model-refactor-governance/plan", headers=bridge_headers)
    assert model.status_code == 200, model.text
    model_payload = model.json()
    assert model_payload["manifest_root"] == "artifacts/model-refactor-governance"
    assert model_payload["compatibility_contract_path"] == "artifacts/model-refactor-governance/compatibility-contract.json"
    assert model_payload["benchmark_comparison_path"] == "artifacts/model-refactor-governance/benchmark-comparison.json"
    assert model_payload["rollback_bundle_path"] == "artifacts/model-refactor-governance/rollback-bundle.json"
    assert model_payload["validation_plan_path"] == "artifacts/model-refactor-governance/validation-plan.json"
    assert model_payload["evaluation_gate_path"] == "artifacts/model-refactor-governance/evaluation-gates.json"
    assert model_payload["approval_checkpoint_path"] == "artifacts/model-refactor-governance/approval-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "model-refactor-governance" / "compatibility-contract.json").exists()

    native = client.post(f"/api/projects/{project_id}/native-app-validation-governance/plan", headers=bridge_headers)
    assert native.status_code == 200, native.text
    native_payload = native.json()
    assert native_payload["manifest_root"] == "artifacts/native-app-validation-governance"
    assert native_payload["platform_matrix_path"] == "artifacts/native-app-validation-governance/platform-matrix.json"
    assert native_payload["artifact_shipping_plan_path"] == "artifacts/native-app-validation-governance/artifact-shipping-plan.json"
    assert native_payload["install_flow_plan_path"] == "artifacts/native-app-validation-governance/install-flow-plan.json"
    assert native_payload["runner_lane_plan_path"] == "artifacts/native-app-validation-governance/runner-lane-plan.json"
    assert native_payload["evidence_bundle_plan_path"] == "artifacts/native-app-validation-governance/evidence-bundle-plan.json"
    assert native_payload["approval_checkpoint_path"] == "artifacts/native-app-validation-governance/approval-checkpoints.json"
    assert native_payload["game_engine_normalized_results_summary_path"] == "artifacts/game-engine-governance/normalized-results-summary.json"
    assert native_payload["game_engine_normalized_summary_count"] == 1
    assert native_payload["game_engine_normalized_publish_ready"] is False
    assert native_payload["game_engine_normalized_results_status"] == "partial"
    assert native_payload["game_engine_publish_gate_status"] == "blocked"
    assert native_payload["game_engine_publish_blocker_count"] == 1
    assert native_payload["game_engine_publish_blockers"] == [
        "Normalized Unity/Unreal result rollups still contain missing, failed, or parse-error evidence."
    ]
    assert (Path(workspace) / "artifacts" / "native-app-validation-governance" / "platform-matrix.json").exists()

    remote = client.post(f"/api/projects/{project_id}/remote-execution-governance/plan", headers=bridge_headers)
    assert remote.status_code == 200, remote.text
    remote_payload = remote.json()
    assert remote_payload["manifest_root"] == "artifacts/remote-execution-governance"
    assert remote_payload["execution_policy_path"] == "artifacts/remote-execution-governance/execution-policy.json"
    assert remote_payload["broker_contract_path"] == "artifacts/remote-execution-governance/broker-contract.json"
    assert remote_payload["artifact_contract_path"] == "artifacts/remote-execution-governance/artifact-contract.json"
    assert remote_payload["connector_contract_path"] == "artifacts/remote-execution-governance/connector-contract.json"
    assert remote_payload["path_sandbox_plan_path"] == "artifacts/remote-execution-governance/path-sandbox-plan.json"
    assert remote_payload["result_contract_path"] == "artifacts/remote-execution-governance/result-contract.json"
    assert remote_payload["session_recording_plan_path"] == "artifacts/remote-execution-governance/session-recording-plan.json"
    assert remote_payload["quota_plan_path"] == "artifacts/remote-execution-governance/quota-plan.json"
    assert remote_payload["approval_checkpoint_path"] == "artifacts/remote-execution-governance/approval-checkpoints.json"
    assert remote_payload["ready_route_count"] == 1
    assert remote_payload["selected_ready_route_count"] == 1
    assert remote_payload["ready_route_ids"] == ["plain_ssh"]
    assert remote_payload["selected_ready_route_ids"] == ["plain_ssh"]
    assert (Path(workspace) / "artifacts" / "remote-execution-governance" / "execution-policy.json").exists()

    nvidia = client.post(f"/api/projects/{project_id}/nvidia/governance/plan", headers=bridge_headers)
    assert nvidia.status_code == 200, nvidia.text
    nvidia_payload = nvidia.json()
    assert nvidia_payload["manifest_root"] == "artifacts/nvidia-governance"
    assert nvidia_payload["execution_lane_path"] == "artifacts/nvidia-governance/execution-lane-selection.json"
    assert nvidia_payload["provider_runtime_path"] == "artifacts/nvidia-governance/provider-runtime-matrix.json"
    assert nvidia_payload["gpu_target_inventory_path"] == "artifacts/nvidia-governance/gpu-target-inventory.json"
    assert nvidia_payload["validation_evidence_path"] == "artifacts/nvidia-governance/validation-evidence-plan.json"
    assert nvidia_payload["telemetry_gate_path"] == "artifacts/nvidia-governance/telemetry-and-safety-gates.json"
    assert nvidia_payload["approval_checkpoint_path"] == "artifacts/nvidia-governance/approval-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "nvidia-governance" / "execution-lane-selection.json").exists()


def test_transport_and_file_governance_plan_routes_generate_manifest_clusters(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("transport-file-governance-plans")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# demo\n", encoding="utf-8")
    Path(workspace, "artifacts").mkdir(parents=True, exist_ok=True)
    Path(workspace, "artifacts", "model.onnx").write_text("artifact\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Transport And File Governance Plans",
            "idea": "Exercise artifact transport and file governance planners",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "main.service.build_artifact_transport_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Artifact transport summary stub.",
            "selected_target_id": "gpu-box",
            "selected_target_probe_status": "ready",
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["gpu-box"],
            "preflight_ready": True,
            "sync_enabled": True,
            "recommended_transport_mode": "remote_artifact_root",
            "blocking_reasons": [],
            "ready_route_count": 1,
            "selected_ready_route_count": 1,
            "partial_route_count": 1,
            "ready_route_ids": ["plain_ssh"],
            "selected_ready_route_ids": ["plain_ssh"],
            "partial_route_ids": ["browser_socket"],
            "ready_platform_lanes": ["linux"],
            "partial_platform_lanes": ["browser"],
            "notes": ["Transport lane is ready."],
            "artifact_registry": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "available": True,
                "summary": "Artifacts are present.",
                "artifact_count": 2,
                "artifact_paths": ["artifacts/model.onnx", "artifacts/report.json"],
                "artifact_extensions": [".onnx", ".json"],
                "artifact_extension_count": 2,
                "artifact_kind_summaries": ["model:1", "report:1"],
                "artifact_kind_counts": {"model": 1, "report": 1},
                "artifact_kind_count": 2,
                "inspection_command_count": 1,
                "inspection_commands": ["python inspect.py"],
                "config_review_path_count": 0,
                "config_review_paths": [],
                "config_review_command_count": 0,
                "config_review_commands": [],
                "validation_evidence_target_count": 1,
                "validation_evidence_targets": ["artifacts/report.json"],
                "execution_entrypoint_count": 1,
                "execution_entrypoints": ["python eval.py"],
                "notebook_path_count": 0,
                "notebook_paths": [],
                "recommended_next_steps": [],
                "recommended_next_step_count": 0,
            },
            "connector_registry": {
                "summary": "Connector registry ready.",
                "family_count": 1,
                "connection_count": 1,
                "authoritative_connection_count": 1,
                "host_imported_count": 0,
                "status_counts": {"connected": 1},
                "host_import_roots": {},
                "recent_action_failures": [],
                "ready_family_count": 1,
                "ready_families": ["source_control"],
                "provider_counts": {"github": 1},
                "provider_count": 1,
                "category_counts": {"developer_workflow": 1},
                "category_count": 1,
                "connection_source_counts": {"mission_control": 1},
                "connection_source_count": 1,
                "available_action_count": 1,
                "catalog": [],
                "connections": [],
            },
            "artifact_contract": {
                "sync_enabled": True,
                "required": True,
                "artifact_path_allowlist": ["artifacts/model.onnx", "artifacts/report.json"],
                "artifact_kind_summaries": ["model:1", "report:1"],
                "local_artifact_paths": ["artifacts/model.onnx", "artifacts/report.json"],
                "local_artifact_path_count": 2,
                "artifact_inspection_commands": ["python inspect.py"],
                "target_artifact_roots": ["/srv/shadow/artifacts"],
                "selected_artifact_root": "/srv/shadow/artifacts",
                "remote_workspace_root": "/srv/shadow",
                "remote_workspace_artifact_paths": ["/srv/shadow/artifacts/model.onnx", "/srv/shadow/artifacts/report.json"],
                "preflight_ready": True,
                "blocking_reasons": [],
                "notes": [],
            },
            "connector_contract": {
                "required_connector_families": ["source_control"],
                "target_connector_families": ["source_control"],
                "allow_host_integrated_connectors": False,
                "require_connector_authority": True,
                "available_families": ["source_control"],
                "available_connector_count": 1,
                "missing_required_families": [],
                "connections": [],
                "preflight_ready": True,
                "blocking_reasons": [],
                "notes": [],
            },
        },
    )
    monkeypatch.setattr(
        "main.service.build_file_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "File governance summary stub.",
            "recommended_operation_mode": "hybrid_connector_sync",
            "supports_bulk_planning": True,
            "destructive_actions_require_approval": True,
            "storage_lane_count": 2,
            "connected_storage_lane_count": 2,
            "ready_scanner_lane_count": 1,
            "ready_scanner_route_count": 1,
            "selected_ready_scanner_route_count": 1,
            "partial_scanner_route_count": 0,
            "storage_provider_count": 3,
            "storage_providers": ["local_fs", "google_drive", "sharepoint"],
            "ready_scanner_lanes": ["linux"],
            "ready_scanner_route_ids": ["plain_ssh"],
            "selected_target_id": "gpu-box",
            "selected_ready_scanner_lanes": ["linux"],
            "selected_ready_scanner_route_ids": ["plain_ssh"],
            "target_backed_ready_scanner_lanes": ["linux"],
            "partial_scanner_route_ids": [],
            "virtual_file_graph_status": "partial",
            "hash_manifest_count": 0,
            "duplicate_cluster_count": 0,
            "classification_manifest_count": 0,
            "dry_run_manifest_count": 0,
            "reversible_batch_manifest_count": 0,
            "blocking_reasons": [],
            "notes": ["Bulk actions remain approval-gated."],
            "storage_lanes": [
                {
                    "lane_id": "local_fs",
                    "title": "Local Filesystem",
                    "status": "connected",
                    "summary": "Local lane ready.",
                    "providers": ["local_fs"],
                    "provider_count": 1,
                    "connection_source": "mission_control",
                    "host_imported": False,
                    "notes": [],
                },
                {
                    "lane_id": "cloud_storage",
                    "title": "Cloud Storage",
                    "status": "connected",
                    "summary": "Cloud storage lane ready.",
                    "providers": ["google_drive", "sharepoint"],
                    "provider_count": 2,
                    "connection_source": "mission_control",
                    "host_imported": False,
                    "notes": [],
                },
            ],
            "connector_registry": {
                "summary": "Connector registry ready.",
                "family_count": 2,
                "connection_count": 2,
                "authoritative_connection_count": 2,
                "host_imported_count": 0,
                "status_counts": {"connected": 2},
                "host_import_roots": {},
                "recent_action_failures": [],
                "ready_family_count": 2,
                "ready_families": ["cloud_storage", "source_control"],
                "provider_counts": {"google_drive": 1, "sharepoint": 1, "github": 1},
                "provider_count": 3,
                "category_counts": {"storage": 1, "developer_workflow": 1},
                "category_count": 2,
                "connection_source_counts": {"mission_control": 2},
                "connection_source_count": 1,
                "available_action_count": 3,
                "catalog": [],
                "connections": [],
            },
            "platform_runners": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "Linux runner ready.",
                "selected_target_id": "gpu-box",
                "selected_target_probe_status": "ready",
                "ready_candidate_count": 1,
                "ready_candidate_ids": ["gpu-box"],
                "ready_route_count": 1,
                "selected_ready_route_count": 1,
                "partial_route_count": 0,
                "lane_count": 1,
                "ready_lane_count": 1,
                "partial_lane_count": 0,
                "unavailable_lane_count": 0,
                "ready_lane_ids": ["linux"],
                "ready_route_ids": ["plain_ssh"],
                "partial_lane_ids": [],
                "unavailable_lane_ids": [],
                "selected_ready_lane_ids": ["linux"],
                "selected_ready_route_ids": ["plain_ssh"],
                "lanes": [
                    {
                        "lane_id": "linux",
                        "title": "Linux Runner",
                        "status": "ready",
                        "summary": "ready",
                        "selected_target_ids": ["gpu-box"],
                        "recommended_commands": ["python -m pytest"],
                        "toolchains": ["cuda12"],
                        "route_ids": ["plain_ssh"],
                        "ready_route_ids": ["plain_ssh"],
                        "selected_route_ids": ["plain_ssh"],
                        "selected_ready_route_ids": ["plain_ssh"],
                    }
                ],
            },
            "artifact_transport": {
                "project_id": project.id,
                "project_name": project.name,
                "workspace_path": project.workspace_path,
                "summary": "Artifact transport summary stub.",
                "selected_target_id": "gpu-box",
                "selected_target_probe_status": "ready",
                "ready_candidate_count": 1,
                "ready_candidate_ids": ["gpu-box"],
                "preflight_ready": True,
                "sync_enabled": True,
                "recommended_transport_mode": "remote_artifact_root",
                "blocking_reasons": [],
                "ready_platform_lanes": ["linux"],
                "partial_platform_lanes": [],
                "notes": ["Transport lane is ready."],
                "artifact_registry": {
                    "project_id": project.id,
                    "project_name": project.name,
                    "workspace_path": project.workspace_path,
                    "available": True,
                    "summary": "Artifacts are present.",
                    "artifact_count": 1,
                    "artifact_paths": ["artifacts/model.onnx"],
                    "artifact_extensions": [".onnx"],
                    "artifact_extension_count": 1,
                    "artifact_kind_summaries": ["model:1"],
                    "artifact_kind_counts": {"model": 1},
                    "artifact_kind_count": 1,
                    "inspection_command_count": 1,
                    "inspection_commands": ["python inspect.py"],
                    "config_review_path_count": 0,
                    "config_review_paths": [],
                    "config_review_command_count": 0,
                    "config_review_commands": [],
                    "validation_evidence_target_count": 1,
                    "validation_evidence_targets": ["artifacts/model.onnx"],
                    "execution_entrypoint_count": 1,
                    "execution_entrypoints": ["python eval.py"],
                    "notebook_path_count": 0,
                    "notebook_paths": [],
                    "recommended_next_steps": [],
                    "recommended_next_step_count": 0,
                },
                "connector_registry": {
                    "summary": "Connector registry ready.",
                    "family_count": 1,
                    "connection_count": 1,
                    "authoritative_connection_count": 1,
                    "host_imported_count": 0,
                    "status_counts": {"connected": 1},
                    "host_import_roots": {},
                    "recent_action_failures": [],
                    "ready_family_count": 1,
                    "ready_families": ["source_control"],
                    "provider_counts": {"github": 1},
                    "provider_count": 1,
                    "category_counts": {"developer_workflow": 1},
                    "category_count": 1,
                    "connection_source_counts": {"mission_control": 1},
                    "connection_source_count": 1,
                    "available_action_count": 1,
                    "catalog": [],
                    "connections": [],
                },
                "artifact_contract": {
                    "sync_enabled": True,
                    "required": True,
                    "artifact_path_allowlist": ["artifacts/model.onnx"],
                    "artifact_kind_summaries": ["model:1"],
                    "local_artifact_paths": ["artifacts/model.onnx"],
                    "local_artifact_path_count": 1,
                    "artifact_inspection_commands": ["python inspect.py"],
                    "target_artifact_roots": ["/srv/shadow/artifacts"],
                    "selected_artifact_root": "/srv/shadow/artifacts",
                    "remote_workspace_root": "/srv/shadow",
                    "remote_workspace_artifact_paths": ["/srv/shadow/artifacts/model.onnx"],
                    "preflight_ready": True,
                    "blocking_reasons": [],
                    "notes": [],
                },
                "connector_contract": {
                    "required_connector_families": ["source_control"],
                    "target_connector_families": ["source_control"],
                    "allow_host_integrated_connectors": False,
                    "require_connector_authority": True,
                    "available_families": ["source_control"],
                    "available_connector_count": 1,
                    "missing_required_families": [],
                    "connections": [],
                    "preflight_ready": True,
                    "blocking_reasons": [],
                    "notes": [],
                },
            },
        },
    )
    monkeypatch.setattr(
        "main.service.build_external_discovery_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "External discovery traversal is ready.",
            "governance_status": "ready",
            "recommended_operation_mode": "connector_plus_file_graph",
            "bounded_discovery_status": "ready",
            "pagination_status": "ready",
            "streaming_status": "ready",
            "file_output_status": "ready",
            "throttle_control_status": "ready",
            "storage_discovery_status": "ready",
            "lanes": [
                {
                    "family": "cloud_storage",
                    "connection_status": "connected",
                    "connection_source": "mission_control",
                    "supports_listing": True,
                    "supports_pagination": True,
                    "supports_streaming_output": True,
                    "supports_file_output": True,
                    "supports_throttle_controls": True,
                    "discovery_ready": True,
                    "notes": [],
                }
            ],
            "notes": ["Connector traversal can stream results to file."],
        },
    )

    artifact_transport = client.post(f"/api/projects/{project_id}/artifact-transport/plan", headers=bridge_headers)
    assert artifact_transport.status_code == 200, artifact_transport.text
    artifact_transport_payload = artifact_transport.json()
    assert artifact_transport_payload["manifest_root"] == "artifacts/artifact-transport"
    assert artifact_transport_payload["transport_mode_path"] == "artifacts/artifact-transport/transport-mode.json"
    assert artifact_transport_payload["artifact_sync_plan_path"] == "artifacts/artifact-transport/artifact-sync-plan.json"
    assert artifact_transport_payload["connector_lane_plan_path"] == "artifacts/artifact-transport/connector-lane-plan.json"
    assert artifact_transport_payload["platform_lane_plan_path"] == "artifacts/artifact-transport/platform-lane-plan.json"
    assert artifact_transport_payload["platform_route_inventory_path"] == "artifacts/artifact-transport/platform-route-inventory.json"
    assert artifact_transport_payload["approval_checkpoint_path"] == "artifacts/artifact-transport/approval-checkpoints.json"
    assert artifact_transport_payload["ready_route_count"] == 1
    assert artifact_transport_payload["selected_ready_route_count"] == 1
    assert (Path(workspace) / "artifacts" / "artifact-transport" / "transport-mode.json").exists()
    assert (Path(workspace) / "artifacts" / "artifact-transport" / "platform-route-inventory.json").exists()

    file_governance = client.post(f"/api/projects/{project_id}/file-governance/plan", headers=bridge_headers)
    assert file_governance.status_code == 200, file_governance.text
    file_governance_payload = file_governance.json()
    assert file_governance_payload["manifest_root"] == "artifacts/file-governance"
    assert file_governance_payload["storage_lanes_path"] == "artifacts/file-governance/storage-lanes.json"
    assert file_governance_payload["scanner_lanes_path"] == "artifacts/file-governance/scanner-lanes.json"
    assert file_governance_payload["scanner_route_inventory_path"] == "artifacts/file-governance/scanner-route-inventory.json"
    assert file_governance_payload["operation_mode_path"] == "artifacts/file-governance/operation-mode.json"
    assert file_governance_payload["approval_guardrails_path"] == "artifacts/file-governance/approval-guardrails.json"
    assert file_governance_payload["transport_integration_path"] == "artifacts/file-governance/transport-integration.json"
    assert file_governance_payload["virtual_file_graph_path"] == "artifacts/file-governance/virtual-file-graph.json"
    assert file_governance_payload["cloud_storage_traversal_path"] == "artifacts/file-governance/cloud-storage-traversal.json"
    assert file_governance_payload["cloud_provider_count"] == 2
    assert file_governance_payload["cloud_provider_ids"] == ["google_drive", "sharepoint"]
    assert file_governance_payload["cloud_traversal_status"] == "ready"
    assert (Path(workspace) / "artifacts" / "file-governance" / "storage-lanes.json").exists()
    assert (Path(workspace) / "artifacts" / "file-governance" / "scanner-route-inventory.json").exists()
    assert (Path(workspace) / "artifacts" / "file-governance" / "virtual-file-graph.json").exists()
    assert (Path(workspace) / "artifacts" / "file-governance" / "cloud-storage-traversal.json").exists()

    storage_lanes = json.loads((Path(workspace) / "artifacts" / "file-governance" / "storage-lanes.json").read_text(encoding="utf-8"))
    assert storage_lanes["connected_lane_ids"] == ["local_fs", "cloud_storage"]
    assert storage_lanes["transport_dependencies"]["recommended_transport_mode"] == "remote_artifact_root"
    assert storage_lanes["governance_requirements"]["dry_run_manifest_required"] is True

    scanner_lanes = json.loads((Path(workspace) / "artifacts" / "file-governance" / "scanner-lanes.json").read_text(encoding="utf-8"))
    assert scanner_lanes["selected_target_id"] == "gpu-box"
    assert scanner_lanes["ready_platform_lanes"] == ["linux"]
    assert scanner_lanes["ready_scanner_route_ids"] == ["plain_ssh"]
    assert scanner_lanes["scanner_requirements"]["transport_preflight_required"] is True

    scanner_route_inventory = json.loads((Path(workspace) / "artifacts" / "file-governance" / "scanner-route-inventory.json").read_text(encoding="utf-8"))
    assert scanner_route_inventory["selected_target_id"] == "gpu-box"
    assert scanner_route_inventory["selected_ready_scanner_route_ids"] == ["plain_ssh"]

    operation_mode = json.loads((Path(workspace) / "artifacts" / "file-governance" / "operation-mode.json").read_text(encoding="utf-8"))
    assert operation_mode["recommended_transport_mode"] == "remote_artifact_root"
    assert operation_mode["virtual_file_graph_status"] == "partial"
    assert operation_mode["cloud_traversal_status"] == "ready"
    assert operation_mode["mutation_requirements"]["semantic_classification_required"] is True

    approval_guardrails = json.loads((Path(workspace) / "artifacts" / "file-governance" / "approval-guardrails.json").read_text(encoding="utf-8"))
    assert approval_guardrails["required_connector_families"] == ["source_control"]
    assert approval_guardrails["reversible_batch_manifest_required"] is True
    approval_checkpoint_ids = [item["checkpoint_id"] for item in approval_guardrails["approval_checkpoints"]]
    assert "mutation_gate_review" in approval_checkpoint_ids
    assert "scanner_route_review" in approval_checkpoint_ids
    assert "cloud_traversal_review" in approval_checkpoint_ids
    assert "virtual_file_graph_review" in approval_checkpoint_ids

    transport_integration = json.loads((Path(workspace) / "artifacts" / "file-governance" / "transport-integration.json").read_text(encoding="utf-8"))
    assert transport_integration["selected_target_id"] == "gpu-box"
    assert transport_integration["selected_ready_scanner_route_ids"] == ["plain_ssh"]
    assert transport_integration["integration_requirements"]["connector_authority_required"] is True

    virtual_file_graph = json.loads((Path(workspace) / "artifacts" / "file-governance" / "virtual-file-graph.json").read_text(encoding="utf-8"))
    assert virtual_file_graph["file_graph_manifest_root"] == "artifacts/file-graph"

    cloud_storage_traversal = json.loads(
        (Path(workspace) / "artifacts" / "file-governance" / "cloud-storage-traversal.json").read_text(encoding="utf-8")
    )
    assert cloud_storage_traversal["cloud_provider_ids"] == ["google_drive", "sharepoint"]
    assert cloud_storage_traversal["crawl_contract"]["strategy"] == "breadth_first"
    assert cloud_storage_traversal["ready_cloud_provider_ids"] == ["google_drive", "sharepoint"]


def test_file_governance_cloud_traversal_run_route_generates_governed_dry_run_outputs(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("cloud-traversal-run")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "main.service.run_file_governance_cloud_traversal",
        lambda db, project, payload: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Generated a governed cloud traversal run.",
            "run_status": "completed",
            "dry_run": True,
            "recommended_operation_mode": "connector_plus_file_graph",
            "cloud_traversal_status": "ready",
            "selected_provider_count": 2,
            "attempted_provider_count": 2,
            "planned_provider_count": 2,
            "completed_provider_count": 0,
            "blocked_provider_count": 0,
            "approval_required_provider_count": 0,
            "output_file_count": 2,
            "manifest_root": "artifacts/file-governance",
            "traversal_manifest_path": "artifacts/file-governance/cloud-storage-traversal.json",
            "run_manifest_path": "artifacts/file-governance/cloud-traversal-run.json",
            "event_log_path": "artifacts/file-governance/cloud-traversal-events.jsonl",
            "file_graph_manifest_root": "artifacts/file-graph",
            "output_paths": [
                "artifacts/file-graph/google_drive-crawl.jsonl",
                "artifacts/file-graph/sharepoint-crawl.jsonl",
            ],
            "provider_runs": [
                {
                    "provider_id": "google_drive",
                    "action_id": "list",
                    "execution_status": "planned",
                    "dry_run": True,
                    "output_path": "artifacts/file-graph/google_drive-crawl.jsonl",
                    "preflight_ready": True,
                    "ready_to_execute": False,
                    "provider_lane_resolved": True,
                    "provider_context_verified": True,
                    "supports_pagination": True,
                    "supports_streaming_output": True,
                    "supports_file_output": True,
                    "supports_throttle_controls": True,
                    "params": {"provider": "google_drive", "limit": 100},
                    "blocking_reasons": [],
                    "notes": [],
                },
                {
                    "provider_id": "sharepoint",
                    "action_id": "list",
                    "execution_status": "planned",
                    "dry_run": True,
                    "output_path": "artifacts/file-graph/sharepoint-crawl.jsonl",
                    "preflight_ready": True,
                    "ready_to_execute": False,
                    "provider_lane_resolved": True,
                    "provider_context_verified": True,
                    "supports_pagination": True,
                    "supports_streaming_output": True,
                    "supports_file_output": True,
                    "supports_throttle_controls": True,
                    "params": {"provider": "sharepoint", "limit": 100},
                    "blocking_reasons": [],
                    "notes": [],
                },
            ],
            "blocking_reasons": [],
            "notes": ["Dry-run connector traversal is ready."],
        },
    )

    create = client.post(
        "/api/projects",
        headers=bridge_headers,
        json={
            "name": "Cloud Traversal Smoke",
            "idea": "Exercise cloud traversal run route.",
            "workspace_path": workspace,
            "provider": "openai_api",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert create.status_code == 200, create.text
    project_id = create.json()["id"]

    run = client.post(
        f"/api/projects/{project_id}/file-governance/cloud-traversal/run",
        headers=bridge_headers,
        json={"provider_ids": ["google_drive", "sharepoint"], "dry_run": True},
    )
    assert run.status_code == 200, run.text
    payload = run.json()
    assert payload["run_status"] == "completed"
    assert payload["cloud_traversal_status"] == "ready"
    assert payload["selected_provider_count"] == 2
    assert payload["output_file_count"] == 2
    assert payload["output_paths"] == [
        "artifacts/file-graph/google_drive-crawl.jsonl",
        "artifacts/file-graph/sharepoint-crawl.jsonl",
    ]


def test_creative_governance_plan_routes_generate_manifest_clusters(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("creative-governance-plans")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# demo\n", encoding="utf-8")
    Path(workspace, "src").mkdir(parents=True, exist_ok=True)
    Path(workspace, "src", "Home.tsx").write_text("export function Home() { return <main>Home</main>; }\n", encoding="utf-8")
    Path(workspace, "docs").mkdir(parents=True, exist_ok=True)
    Path(workspace, "dupes").mkdir(parents=True, exist_ok=True)
    Path(workspace, "docs", "roadmap.txt").write_text("same content\n", encoding="utf-8")
    Path(workspace, "dupes", "roadmap-copy.txt").write_text("same content\n", encoding="utf-8")
    Path(workspace, "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Creative Governance Plans",
            "idea": "Exercise creative governance planners",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "main.service.build_design_transfer_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Design transfer summary stub.",
            "recommended_ingestion_mode": "figma_plus_artifacts",
            "figma_connected": True,
            "design_artifact_count": 2,
            "design_artifact_paths": ["artifacts/design/mock-home.png", "artifacts/design/design-tokens.json"],
            "design_artifact_formats": [".png", ".json"],
            "browser_lane_status": "partial",
            "browser_lane_target_ids": [],
            "supports_visual_regression": True,
            "code_conformance_ready": False,
            "blocking_reasons": [],
            "notes": ["Design inputs are ready for governed mapping."],
        },
    )
    monkeypatch.setattr(
        "main.service.build_spatial_asset_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Spatial governance summary stub.",
            "governance_status": "partial",
            "repo_mode_enabled": True,
            "repo_mode": "spatial3d_geospatial",
            "frameworks": ["OpenUSD", "3D Gaussian Splatting"],
            "product_workflows": ["browser_renderer", "visual_regression", "cloud_reconstruction", "dataset_quality"],
            "recommended_feature_ids": ["browser_renderer", "visual_regression_3d"],
            "asset_count": 2,
            "asset_paths": ["assets/city.splat", "assets/city.usda"],
            "asset_extensions": [".splat", ".usda"],
            "config_paths": ["configs/streaming.yaml"],
            "primary_scene_path": "assets/city.usda",
            "headless_runner_status": "unavailable",
            "browser_lane_status": "partial",
            "recommended_transport_mode": "blocked",
            "build_commands": ["python -m pip install -e ."],
            "render_commands": [],
            "conversion_commands": ["python scripts/convert_splats.py"],
            "capture_commands": ["python pipeline/capture.py"],
            "benchmark_commands": ["python benchmarks/render_benchmark.py"],
            "validation_status": "ready",
            "validation_available": True,
            "validation_step_count": 2,
            "validation_evidence_targets": ["render diff summary", "streaming benchmark output"],
            "supports_visual_regression": True,
            "quality_gate_blocker_count": 0,
            "quality_gate_missing_evidence_count": 0,
            "pending_approval_count": 0,
            "pending_question_count": 0,
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Spatial lane exposes validation evidence."],
        },
    )
    monkeypatch.setattr(
        "main.service.build_workspace_tooling_status",
        lambda project: {
            "spatial3d_validation_plan": {
                "steps": [
                    {"title": "Run browser probe", "command": "playwright test", "type": "inspect", "status": "pending"},
                    {"title": "Run benchmark", "command": "python benchmarks/render_benchmark.py", "type": "benchmark", "status": "pending"},
                ]
            }
        },
    )
    monkeypatch.setattr(
        "main.service.build_game_engine_governance_summary",
        lambda db, project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Game engine governance summary stub.",
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
            "screenshot_artifact_paths": ["artifacts/renders/frame_0001.png"],
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
            "blocking_reasons": [],
            "recommended_fixes": [],
            "notes": ["Playable contract is grounded in repo-owned assets."],
        },
    )
    monkeypatch.setattr(
        "main.service.build_file_governance_summary",
        lambda db, project: {
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
            "notes": ["Dry-run only, approval stays explicit."],
        },
    )

    design = client.post(f"/api/projects/{project_id}/design-transfer/plan", headers=bridge_headers)
    assert design.status_code == 200, design.text
    design_payload = design.json()
    assert design_payload["manifest_root"] == "artifacts/design-transfer"
    assert design_payload["design_intent_manifest_path"] == "artifacts/design-transfer/design-intent-transfer.json"
    assert design_payload["component_map_manifest_path"] == "artifacts/design-transfer/component-map.json"
    assert design_payload["screenshot_diff_plan_path"] == "artifacts/design-transfer/screenshot-diff-plan.json"
    assert design_payload["token_usage_plan_path"] == "artifacts/design-transfer/design-token-usage-plan.json"
    assert design_payload["aria_check_plan_path"] == "artifacts/design-transfer/dom-aria-check-plan.json"
    assert (Path(workspace) / "artifacts" / "design-transfer" / "design-intent-transfer.json").exists()

    spatial = client.post(f"/api/projects/{project_id}/spatial-asset-governance/plan", headers=bridge_headers)
    assert spatial.status_code == 200, spatial.text
    spatial_payload = spatial.json()
    assert spatial_payload["manifest_root"] == "artifacts/spatial-governance"
    assert spatial_payload["scene_contract_path"] == "artifacts/spatial-governance/scene-contract.json"
    assert spatial_payload["asset_provenance_path"] == "artifacts/spatial-governance/asset-provenance.json"
    assert spatial_payload["visual_regression_plan_path"] == "artifacts/spatial-governance/visual-regression-plan.json"
    assert spatial_payload["export_validation_plan_path"] == "artifacts/spatial-governance/export-validation-plan.json"
    assert spatial_payload["approval_checkpoint_path"] == "artifacts/spatial-governance/approval-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "spatial-governance" / "scene-contract.json").exists()

    game = client.post(f"/api/projects/{project_id}/game-engine-governance/plan", headers=bridge_headers)
    assert game.status_code == 200, game.text
    game_payload = game.json()
    assert game_payload["manifest_root"] == "artifacts/game-engine-governance"
    assert game_payload["playable_definition_path"] == "artifacts/game-engine-governance/playable-definition.json"
    assert game_payload["scene_governance_path"] == "artifacts/game-engine-governance/scene-governance.json"
    assert game_payload["asset_lock_plan_path"] == "artifacts/game-engine-governance/asset-lock-plan.json"
    assert game_payload["task_routing_plan_path"] == "artifacts/game-engine-governance/task-routing-plan.json"
    assert game_payload["content_budget_plan_path"] == "artifacts/game-engine-governance/content-budget-plan.json"
    assert game_payload["automation_pack_path"] == "artifacts/game-engine-governance/automation-pack.json"
    assert game_payload["engine_test_matrix_path"] == "artifacts/game-engine-governance/engine-test-matrix.json"
    assert game_payload["validation_lane_plan_path"] == "artifacts/game-engine-governance/validation-lane-plan.json"
    assert game_payload["evidence_contract_path"] == "artifacts/game-engine-governance/evidence-contract.json"
    assert game_payload["result_normalization_plan_path"] == "artifacts/game-engine-governance/result-normalization-plan.json"
    assert game_payload["normalized_results_summary_path"] == "artifacts/game-engine-governance/normalized-results-summary.json"
    assert game_payload["normalized_summary_count"] >= 1
    assert game_payload["normalized_publish_ready"] is False
    assert game_payload["publish_gate_status"] == "blocked"
    assert game_payload["publish_blocker_count"] == 1
    assert game_payload["publish_blockers"] == [
        "Normalized Unity/Unreal result rollups still contain missing, failed, or parse-error evidence."
    ]
    assert game_payload["screenshot_regression_plan_path"] == "artifacts/game-engine-governance/screenshot-regression-plan.json"
    assert game_payload["publish_gate_path"] == "artifacts/game-engine-governance/publish-gates.json"
    assert game_payload["approval_checkpoint_path"] == "artifacts/game-engine-governance/approval-checkpoints.json"
    assert (Path(workspace) / "artifacts" / "game-engine-governance" / "playable-definition.json").exists()
    assert (Path(workspace) / "artifacts" / "game-engine-governance" / "asset-lock-plan.json").exists()
    assert (Path(workspace) / "artifacts" / "game-engine-governance" / "task-routing-plan.json").exists()
    assert (Path(workspace) / "artifacts" / "game-engine-governance" / "result-normalization-plan.json").exists()
    assert (Path(workspace) / "artifacts" / "game-engine-governance" / "normalized-results-summary.json").exists()

    scene_governance = json.loads((Path(workspace) / "artifacts" / "game-engine-governance" / "scene-governance.json").read_text(encoding="utf-8"))
    assert scene_governance["play_level_governance"]["golden_path_scene_required"] is True
    assert scene_governance["ownership_rules"]["code_task_requires_engine_native_validation"] is True

    asset_lock_plan = json.loads((Path(workspace) / "artifacts" / "game-engine-governance" / "asset-lock-plan.json").read_text(encoding="utf-8"))
    assert asset_lock_plan["lock_rules"]["mixed_code_content_changes_require_publish_review"] is True

    task_routing_plan = json.loads((Path(workspace) / "artifacts" / "game-engine-governance" / "task-routing-plan.json").read_text(encoding="utf-8"))
    assert task_routing_plan["handoff_rules"]["content_tasks_cannot_close_without_asset_lock_review"] is True

    engine_test_matrix = json.loads((Path(workspace) / "artifacts" / "game-engine-governance" / "engine-test-matrix.json").read_text(encoding="utf-8"))
    assert engine_test_matrix["regression_requirements"]["engine_native_test_evidence_required"] is True
    assert engine_test_matrix["task_boundaries"]["content_tasks_must_not_skip_asset_lock_review"] is True

    validation_lane_plan = json.loads((Path(workspace) / "artifacts" / "game-engine-governance" / "validation-lane-plan.json").read_text(encoding="utf-8"))
    assert validation_lane_plan["ready_execution_lane_ids"] == ["unity"]
    assert validation_lane_plan["execution_lanes"][0]["command_bundles"][0]["bundle_id"] == "unity_editmode_tests"

    evidence_contract = json.loads((Path(workspace) / "artifacts" / "game-engine-governance" / "evidence-contract.json").read_text(encoding="utf-8"))
    assert evidence_contract["engine_expectations"]["unity"]["required_test_modes"] == ["EditMode", "PlayMode"]

    result_normalization_plan = json.loads((Path(workspace) / "artifacts" / "game-engine-governance" / "result-normalization-plan.json").read_text(encoding="utf-8"))
    assert result_normalization_plan["normalizers"][0]["result_format"] == "junit_xml"
    assert result_normalization_plan["normalized_output_contract"]["publish_blocking_statuses"] == ["failed", "missing", "parse_error"]

    normalized_results_summary = json.loads((Path(workspace) / "artifacts" / "game-engine-governance" / "normalized-results-summary.json").read_text(encoding="utf-8"))
    assert normalized_results_summary["summary_count"] >= 1
    assert normalized_results_summary["publish_ready"] is False

    approval_checkpoints = json.loads((Path(workspace) / "artifacts" / "game-engine-governance" / "approval-checkpoints.json").read_text(encoding="utf-8"))
    assert approval_checkpoints["checkpoints"][0]["checkpoint_id"] == "engine_lane_ready_review"
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_checkpoints["checkpoints"]}
    assert checkpoint_by_id["normalized_results_review"]["status"] == "blocked"

    publish_gates = json.loads((Path(workspace) / "artifacts" / "game-engine-governance" / "publish-gates.json").read_text(encoding="utf-8"))
    gate_by_id = {item["gate_id"]: item for item in publish_gates["gates"]}
    assert gate_by_id["result_normalization_review"]["status"] == "blocked"

    file_graph = client.post(f"/api/projects/{project_id}/file-graph-governance/plan", headers=bridge_headers)
    assert file_graph.status_code == 200, file_graph.text
    file_graph_payload = file_graph.json()
    assert file_graph_payload["manifest_root"] == "artifacts/file-graph"
    assert file_graph_payload["hash_manifest_path"] == "artifacts/file-graph/content-hashes.sha256"
    assert file_graph_payload["duplicate_cluster_path"] == "artifacts/file-graph/duplicate-clusters.json"
    assert file_graph_payload["classification_manifest_path"] == "artifacts/file-graph/semantic-classification-taxonomy.json"
    assert file_graph_payload["dry_run_manifest_path"] == "artifacts/file-graph/bulk-rename-dry-run-plan.json"
    assert file_graph_payload["reversible_batch_manifest_path"] == "artifacts/file-graph/restore-batch-manifest.json"
    assert (Path(workspace) / "artifacts" / "file-graph" / "content-hashes.sha256").exists()


def test_file_graph_apply_route_surfaces_governed_execution_contract(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("file-graph-apply-route")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# demo\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "File Graph Apply Route",
            "idea": "Expose the file graph apply API properly",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
        headers=bridge_headers,
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "main.service.apply_file_graph_governance_plan",
        lambda db, project, payload: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Applied governed file-graph actions.",
            "run_status": "partial",
            "approval_required": True,
            "approval_id": 91,
            "approval_status": "approved_once",
            "selected_action_count": 2,
            "applied_action_count": 1,
            "staged_remote_action_count": 1,
            "failed_action_count": 0,
            "skipped_action_count": 0,
            "manifest_root": "artifacts/file-graph/apply-runs/file-graph-apply-123",
            "dry_run_manifest_path": "artifacts/file-graph/bulk-rename-dry-run-plan.json",
            "reversible_batch_manifest_path": "artifacts/file-graph/restore-batch-manifest.json",
            "run_manifest_path": "artifacts/file-graph/apply-runs/file-graph-apply-123/apply-run.json",
            "connector_batch_manifest_path": "artifacts/file-graph/apply-runs/file-graph-apply-123/connector-mutation-batch.json",
            "blocking_reasons": [],
            "notes": ["Remote connector work is staged."],
            "action_results": [
                {
                    "action_id": "duplicate-review-1",
                    "action_type": "archive_candidate",
                    "execution_status": "applied",
                    "source_path": "dupes/roadmap-copy.txt",
                    "destination_path": "archive/review/duplicates/dupes__roadmap-copy.txt",
                    "source_origin": "local",
                    "execution_surface": "local",
                    "provider_id": None,
                    "notes": [],
                    "error": None,
                }
            ],
        },
    )

    response = client.post(
        f"/api/projects/{project_id}/file-graph-governance/apply",
        json={"action_ids": ["duplicate-review-1"], "approval_id": 91},
        headers=bridge_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_status"] == "partial"
    assert payload["approval_id"] == 91
    assert payload["applied_action_count"] == 1
    assert payload["staged_remote_action_count"] == 1
    assert payload["run_manifest_path"].endswith("/apply-run.json")
    assert payload["connector_batch_manifest_path"].endswith("/connector-mutation-batch.json")
    assert payload["action_results"][0]["execution_status"] == "applied"


def test_file_graph_connector_batch_execute_route_surfaces_governed_execution_contract(client, bridge_headers, monkeypatch) -> None:
    workspace = sample_workspace("file-graph-connector-batch-route")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# demo\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "File Graph Connector Batch Route",
            "idea": "Expose the connector batch execution API properly",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
        headers=bridge_headers,
    ).json()
    project_id = project["id"]

    monkeypatch.setattr(
        "main.service.execute_file_graph_connector_batch",
        lambda db, project, payload: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "summary": "Executed governed connector batch actions.",
            "run_status": "completed",
            "approval_required": True,
            "approval_id": 91,
            "approval_status": "approved_once",
            "batch_manifest_path": "artifacts/file-graph/apply-runs/file-graph-apply-123/connector-mutation-batch.json",
            "run_manifest_path": "artifacts/file-graph/apply-runs/file-graph-apply-123/connector-execution-run.json",
            "selected_action_count": 1,
            "executed_action_count": 1,
            "failed_action_count": 0,
            "blocked_action_count": 0,
            "blocking_reasons": [],
            "notes": ["Executed through the governed cloud storage lane."],
            "action_results": [
                {
                    "action_id": "duplicate-review-1",
                    "provider_id": "google_drive",
                    "operation": "archive",
                    "execution_status": "executed",
                    "source_path": "cloud://google_drive/Shared/plan-copy.md",
                    "destination_path": "archive/review/duplicates/google_drive/Shared__plan-copy.md",
                    "notes": [],
                    "error": None,
                }
            ],
        },
    )

    response = client.post(
        f"/api/projects/{project_id}/file-graph-governance/connector-batch/execute",
        json={
            "batch_manifest_path": "artifacts/file-graph/apply-runs/file-graph-apply-123/connector-mutation-batch.json",
            "approval_id": 91,
        },
        headers=bridge_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_status"] == "completed"
    assert payload["approval_id"] == 91
    assert payload["executed_action_count"] == 1
    assert payload["run_manifest_path"].endswith("/connector-execution-run.json")
    assert payload["action_results"][0]["execution_status"] == "executed"


def test_runbook_routes_generate_update_and_summarize(client, bridge_headers) -> None:
    workspace = sample_workspace("runbook-routes")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    Path(workspace, "app.py").write_text("print('hi')\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Runbook Routes",
            "idea": "Expose the runbook API properly",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    initial = client.get(f"/api/projects/{project_id}/runbook", headers=bridge_headers)
    assert initial.status_code == 200, initial.text
    assert initial.json() is None

    generated = client.post(f"/api/projects/{project_id}/runbook/generate", headers=bridge_headers)
    assert generated.status_code == 200, generated.text
    generated_payload = generated.json()
    assert generated_payload["project_id"] == project_id
    assert "# Runbook" in generated_payload["content_markdown"]

    summary = client.get(f"/api/projects/{project_id}/runbook/summary", headers=bridge_headers)
    assert summary.status_code == 200, summary.text
    summary_payload = summary.json()
    assert summary_payload["exists"] is True
    assert summary_payload["section_count"] >= 1

    updated = client.put(
        f"/api/projects/{project_id}/runbook",
        headers=bridge_headers,
        json={"content_markdown": "# Custom Runbook\n\n## Start\n- python -m pytest"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["content_markdown"].startswith("# Custom Runbook")


def test_context_pack_routes_return_summary_rollups(client) -> None:
    workspace = sample_workspace("context-pack-rollups")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# Existing codebase\n", encoding="utf-8")

    project = client.post(
        "/api/projects",
        json={
            "name": "Context Pack Rollup Demo",
            "idea": "Check context pack summary rollups",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    pack_response = client.post(
        f"/api/projects/{project_id}/context-packs/build",
        json={"title": "Scoped Pack", "goal": "Summarize the repo for workers."},
    )
    assert pack_response.status_code == 200, pack_response.text
    payload = pack_response.json()

    assert payload["project_id"] == project_id
    assert payload["included_doc_count"] == len(payload["included_docs_json"])
    assert payload["included_file_count"] == len(payload["included_files_json"])
    assert payload["excluded_file_count"] == len(payload["excluded_files_json"])
    assert payload["known_decision_count"] == len(payload["known_decisions_json"])
    assert payload["relevant_assumption_count"] == len(payload["relevant_assumptions_json"])
    assert payload["validation_step_count"] == len(payload["validation_steps_json"])
    assert payload["warning_count"] == len(payload["warnings_json"])
    assert payload["section_count"] == len(payload["sections"]) == 6
    expected_section_type_counts = {}
    expected_source_refs = []
    seen_source_refs = set()
    for section in payload["sections"]:
        expected_section_type_counts[section["section_type"]] = expected_section_type_counts.get(section["section_type"], 0) + 1
        assert section["source_ref_count"] == len(section["source_refs_json"])
        for ref in section["source_refs_json"]:
            if ref in seen_source_refs:
                continue
            seen_source_refs.add(ref)
            expected_source_refs.append(ref)
    assert payload["section_types"] == sorted(expected_section_type_counts)
    assert payload["section_type_counts"] == expected_section_type_counts
    assert payload["section_type_group_count"] == len(expected_section_type_counts)
    assert payload["section_titles"] == [section["title"] for section in payload["sections"]]
    assert payload["source_refs"] == expected_source_refs
    assert payload["source_ref_count"] == len(expected_source_refs)

    listed = client.get(f"/api/projects/{project_id}/context-packs")
    assert listed.status_code == 200, listed.text
    listed_payload = listed.json()
    assert len(listed_payload) == 1
    assert listed_payload[0]["id"] == payload["id"]
    assert listed_payload[0]["section_type_counts"] == payload["section_type_counts"]

    fetched = client.get(f"/api/projects/{project_id}/context-packs/{payload['id']}")
    assert fetched.status_code == 200, fetched.text
    fetched_payload = fetched.json()
    assert fetched_payload["id"] == payload["id"]
    assert fetched_payload["source_refs"] == payload["source_refs"]

    fetched_without_scope = client.get(f"/api/context-packs/{payload['id']}")
    assert fetched_without_scope.status_code == 200, fetched_without_scope.text
    assert fetched_without_scope.json()["id"] == payload["id"]


def test_project_ascii_monitor_returns_live_ascii_frame(client, bridge_headers, monkeypatch) -> None:
    response = client.post(
        "/api/projects",
        json={
            "name": "ASCII Browser Monitor",
            "idea": "Keep a browser copy of the live ASCII viewer.",
            "workspace_path": sample_workspace("ascii-browser-monitor"),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
        headers=bridge_headers,
    )
    assert response.status_code == 200
    project = response.json()
    created_at = utc_now()

    monkeypatch.setattr(
        bridge_runtime_service,
        "get_status_summary_preview",
        lambda db, project, orchestration=None: {
            "id": f"status-{project.id}",
            "project_id": project.id,
            "orchestration_id": None,
            "source_type": "manager",
            "message_type": "status_update",
            "title": "Mission Control status",
            "summary": "Idle project preview",
            "user_action_required": False,
            "risk_level": None,
            "options_json": None,
            "machine_payload_json": {
                "manager_status": "No active orchestration session yet.",
                "current_work": ["Waiting for fresh work."],
                "next_expected_step": "Start or resume an orchestration.",
                "current_blockers": [],
                "handoff_readiness": "not_ready",
                "active_agent_count": 0,
                "model_advisories": [],
                "orchestration_status": "planning",
            },
            "fallback_markdown": "status",
            "redaction_status": "clean",
            "created_at": created_at,
            "expires_at": None,
            "resolved_at": None,
        },
    )
    monkeypatch.setattr(
        bridge_runtime_service,
        "get_handoff_summary",
        lambda db, project, orchestration=None: {
            "id": f"handoff-{project.id}",
            "project_id": project.id,
            "orchestration_id": None,
            "source_type": "handoff",
            "message_type": "status_update",
            "title": "Handoff status",
            "summary": "No handoff yet.",
            "user_action_required": False,
            "risk_level": None,
            "options_json": None,
            "machine_payload_json": {"status": "not_ready"},
            "fallback_markdown": "handoff",
            "redaction_status": "clean",
            "created_at": created_at,
            "expires_at": None,
            "resolved_at": None,
        },
    )
    monkeypatch.setattr(bridge_runtime_service, "get_pending_decisions", lambda db, project, orchestration=None: [])

    monitor = client.get(f"/api/projects/{project['id']}/ascii-monitor", headers=bridge_headers)
    assert monitor.status_code == 200
    payload = monitor.json()

    assert payload["project_id"] == project["id"]
    assert payload["orchestration_id"] is None
    assert payload["refresh_seconds"] == 1.0
    assert "MISSION CONTROL LIVE" in payload["frame"]
    assert "ASCII Browser Monitor" in payload["frame"]
    assert "No active orchestration session yet." in payload["frame"]
    assert "orchestration-display --project-id" in payload["viewer_command"]
