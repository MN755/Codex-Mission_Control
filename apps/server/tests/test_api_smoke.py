from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import sample_workspace, wait_for
from main import app


def test_system_status_supports_provider_preview_overrides(client, bridge_headers, monkeypatch) -> None:
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

    status = client.get(
        "/api/system/status",
        params={"provider": "ollama", "provider_endpoint": "http://localhost:11434"},
        headers=bridge_headers,
    ).json()

    assert status["selected_provider"] == "ollama"
    assert status["selected_provider_label"] == "Ollama"
    assert "llama3.2:latest" in status["available_models"]


def test_dry_run_project_flow(client, bridge_headers) -> None:
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

    settings_response = client.get(f"/api/settings?project_id={project_id}")
    assert settings_response.status_code == 200
    assert settings_response.json()["runner_mode"] == "dry_run"

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

    docs_response = client.post(f"/api/projects/{project_id}/docs/generate")
    assert docs_response.status_code == 200
    assert "PROJECT_BRIEF.md" in docs_response.json()["files"]
    assert docs_response.json()["manager_mode_used"] == "deterministic"

    session = client.post(f"/api/projects/{project_id}/interview/start", json={"question_budget": 6}).json()
    while session["status"] != "completed":
        pending_questions = [question for question in session["questions"] if question["status"] == "pending"]
        for question in pending_questions:
            option = question["options"][0]
            session = client.post(
                f"/api/interview/questions/{question['id']}/answer",
                json={
                    "project_id": project_id,
                    "option_id": option["id"],
                    "selected_text": option["label"],
                },
            ).json()
        if session["status"] != "completed" and session["questions_remaining"] > 0:
            session = client.post(f"/api/projects/{project_id}/interview/generate-next").json()

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
        assert raw_client.get(f"/api/projects/{project_id}/swarm/preferences").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/swarm/plan").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/swarm/spawn").status_code == 401
        assert raw_client.get("/api/playbooks").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/playbook/suggest").status_code == 401
        assert raw_client.get("/api/preferences").status_code == 401
        assert raw_client.get("/api/security/policy").status_code == 401
        assert raw_client.get("/api/tools").status_code == 401
        assert raw_client.get("/api/skills").status_code == 401
        assert raw_client.get("/api/handoffs").status_code == 401
        assert raw_client.get("/api/agent-archetypes").status_code == 401
        assert raw_client.get("/api/widgets/catalog").status_code == 401
        assert raw_client.get("/api/widgets/instances", params={"scope": "dashboard"}).status_code == 401
        assert raw_client.get("/api/capabilities/matrix").status_code == 401
        assert raw_client.get("/api/capabilities/benchmarks").status_code == 401
        assert raw_client.get("/api/agents/reputation").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/change-requests", json={"request_text": "Make it better"}).status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/context-packs").status_code == 401
        assert raw_client.get("/api/context-packs/1", params={"project_id": project_id}).status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/risks").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/scope-creep").status_code == 401
        assert raw_client.post("/api/scope-creep/1/resolve", params={"project_id": project_id}, json={"status": "accepted"}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/swarm/simulate-launch").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/swarm/simulations").status_code == 401
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
        assert raw_client.get(f"/api/projects/{project_id}/tasks").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/agents").status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/manager/message", json={"message": "What next?"}).status_code == 401
        assert raw_client.post(f"/api/projects/{project_id}/manager/next-step").status_code == 401
        assert raw_client.post("/api/projects/import-folder", json={"folder_path": sample_workspace("auth-import"), "import_mode": "linked"}).status_code == 401
