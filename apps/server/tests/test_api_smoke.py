from __future__ import annotations

from pathlib import Path

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

    status = client.get(f"/api/system/status?project_id={project_id}", headers=bridge_headers).json()
    assert "active_runs" in status
    assert status["selected_provider"] == "claude_code"
    assert status["selected_manager_model"] == "gpt-5.5"
    assert status["selected_default_worker_model"] == "gpt-5.4-mini"
    assert "authenticated" in status
    assert "current_auth_job" in status

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
        assert raw_client.post("/api/integrations/import-host-state").status_code == 401
        assert raw_client.get("/api/skills").status_code == 401
        assert raw_client.get("/api/handoffs").status_code == 401
        assert raw_client.get("/api/agent-archetypes").status_code == 401
        assert raw_client.get("/api/widgets/catalog").status_code == 401
        assert raw_client.get("/api/widgets/catalog/project").status_code == 401
        assert raw_client.get("/api/widgets/instances", params={"scope": "dashboard"}).status_code == 401
        assert raw_client.get("/api/widgets/instances").status_code == 401
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
