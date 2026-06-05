from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from db import SessionLocal, init_db
from manager import service
from models import Agent, ChangeRequest, ManagerMessage, Project, ProjectSettings
from conftest import sample_workspace, seed_imported_codebase_records


@pytest.fixture(autouse=True)
def _fast_workspace_dependencies(monkeypatch) -> None:
    def fake_initial_scan(db, project, *, depth: str | None = None):
        return seed_imported_codebase_records(db, project, scan_depth=depth or "standard")

    async def fake_system_status(db, project=None, **kwargs):
        return {
            "selected_provider": "codex",
            "selected_provider_label": "Codex",
            "cli_detected": True,
            "cli_path": "codex",
            "cli_path_exists": True,
            "cli_execution_available": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Logged in using ChatGPT",
            "auth_mode": "chatgpt",
            "authenticated": True,
            "runtime_ready": True,
            "runtime_summary": "Codex preview status is available.",
            "app_server_supported": False,
            "app_server_handshake_status": "unsupported",
            "app_server_transport": "unsupported",
            "effective_runner_mode": "dry_run",
            "dry_run_available": True,
            "runtime_directory": "runtime",
            "repo_root": "repo",
            "launcher_root": "launcher",
            "plugin_source_root": "plugins/mission-control",
            "backend_host": "127.0.0.1",
            "backend_port": 8010,
            "backend_base_url": "http://127.0.0.1:8010",
            "configured_backend_port": 8010,
            "backend_binding_source": "test",
            "frontend_port": 5173,
            "provider_statuses": [],
            "available_models": [],
            "active_runs": [],
            "mcp_servers": [],
            "configured_mcp_servers": [],
            "mcp_state": {},
            "configured_plugins": [],
            "local_skills": [],
            "current_auth_job": None,
            "startup_summary": None,
            "diagnostics_directory": None,
            "current_settings_summary": None,
            "selected_manager_model": None,
            "selected_default_worker_model": None,
            "model_advisories": [],
            "app_state_summary": None,
            "notes": [],
        }

    async def empty_items(db, projects=None):
        return []

    async def fake_widget_summary(db):
        return {"instances": [], "catalog": [], "data": []}

    monkeypatch.setattr("imported_codebase.import_service.initial_scan", fake_initial_scan)
    monkeypatch.setattr("manager.service.get_system_status", fake_system_status)
    monkeypatch.setattr("manager.service._dashboard_active_builds", empty_items)
    monkeypatch.setattr("manager.service._dashboard_attention_items", empty_items)
    monkeypatch.setattr("manager.service.get_dashboard_widget_summary", fake_widget_summary)


def test_workspace_dry_run_loop_and_action_flow(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Workspace Loop Demo",
            "idea": "Exercise the workspace loop",
            "workspace_path": sample_workspace("workspace-loop"),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()

    opened = client.post(f"/api/projects/{project['id']}/open")
    assert opened.status_code == 200
    assert opened.json()["slug"] == "workspace-loop-demo"
    assert opened.json()["last_opened_at"] is not None

    workspace = client.get(f"/api/projects/{project['id']}/workspace").json()
    assert workspace["project"]["id"] == project["id"]
    assert workspace["current_action"]["type"] == "manager_question"
    assert workspace["pending_question"]["status"] == "pending"
    assert workspace["manager_queue"]["waiting_on_user"]
    assert workspace["agents"]
    assert workspace["workflow"]["current_phase"] == "build"
    assert workspace["overview"]["checklist"]
    assert workspace["tasks"]
    assert workspace["activity_log"]

    question = workspace["pending_question"]
    answer = client.post(
        f"/api/projects/{project['id']}/questions/{question['id']}/answer",
        json={"option_id": "workflow", "selected_text": "Workflow loop"},
    )
    assert answer.status_code == 200
    assert answer.json()["status"] == "answered"

    approvals = client.get(f"/api/projects/{project['id']}/approvals/pending").json()
    assert len(approvals) == 1
    assert approvals[0]["request_type"] == "command"

    action = client.get(f"/api/projects/{project['id']}/action").json()
    assert action["type"] == "command_approval"

    approval = client.post(f"/api/projects/{project['id']}/approvals/{approvals[0]['id']}/approve-once", json={"project_id": project["id"]})
    assert approval.status_code == 200
    assert approval.json()["status"] == "approved_once"

    workspace_after = client.get(f"/api/projects/{project['id']}/workspace").json()
    assert any(message["message_type"] == "milestone_report" for message in workspace_after["manager_messages"])
    assert workspace_after["agents"][0]["display_status"] in {"running", "coding", "active"}


def test_high_impact_question_cannot_auto_decide(client) -> None:
    init_db()
    db = SessionLocal()
    try:
        project = Project(name="High Impact", idea="Idea", workspace_path=sample_workspace("high-impact"), runner_mode="dry_run", manager_mode="auto")
        db.add(project)
        db.flush()
        db.add(
            Agent(
                project_id=project.id,
                name="Manager AI",
                role="Project orchestration",
                kind="manager",
                status="idle",
                workspace_path=project.workspace_path,
            )
        )
        db.flush()
        question = service._create_question(
            db,
            project,
            question="Should the manager rewrite the app architecture?",
            options_json=[{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
            impact="high",
            manager_recommendation="No",
        )
        db.commit()
        response = client.post(f"/api/projects/{project.id}/questions/{question.id}/auto-decide")
        assert response.status_code == 400
    finally:
        db.close()


def test_project_pause_and_resume_flow(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Pause Resume Demo",
            "idea": "Pause and resume the project workspace",
            "workspace_path": sample_workspace("pause-resume-demo"),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()

    paused = client.post(f"/api/projects/{project['id']}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    workspace_paused = client.get(f"/api/projects/{project['id']}/workspace").json()
    assert workspace_paused["project"]["status"] == "paused"
    assert any(message["message_type"] == "system_notice" for message in workspace_paused["manager_messages"])

    resumed = client.post(f"/api/projects/{project['id']}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] in {"building", "draft"}


def test_project_metadata_update_refreshes_slug(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Metadata Demo",
            "idea": "Original project brief",
            "workspace_path": sample_workspace("metadata-demo"),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()

    response = client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "Renamed Workspace", "idea": "Sharper manager-led workspace copy"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Renamed Workspace"
    assert payload["slug"] == "renamed-workspace"
    assert payload["idea"] == "Sharper manager-led workspace copy"


def test_approval_resolution_is_project_scoped(client) -> None:
    init_db()
    db = SessionLocal()
    try:
        project_one = Project(name="Project One", idea="Idea", workspace_path=sample_workspace("scope-one"), runner_mode="dry_run", manager_mode="auto")
        project_two = Project(name="Project Two", idea="Idea", workspace_path=sample_workspace("scope-two"), runner_mode="dry_run", manager_mode="auto")
        db.add_all([project_one, project_two])
        db.flush()
        approval = service._create_approval(
            db,
            project_one,
            request_type="command",
            title="Simulated command",
            reason_short="Simulated approval for scope safety.",
            risk_level="medium",
            cwd=project_one.workspace_path,
            request_payload_json={"command": "echo test"},
        )
        db.commit()

        response = client.post(f"/api/projects/{project_two.id}/approvals/{approval.id}/approve-once", json={"project_id": project_two.id})
        assert response.status_code == 404

        db.refresh(approval)
        assert approval.status == "pending"
    finally:
        db.close()


def test_legacy_project_without_settings_reads_defaults_without_persisting_row(client, bridge_headers) -> None:
    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Legacy Workspace",
            idea="This project predates project settings.",
            workspace_path=sample_workspace("legacy-workspace"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        project.last_opened_at = project.created_at
        db.add(
            Agent(
                project_id=project.id,
                name="Manager AI",
                role="Project orchestration",
                kind="manager",
                status="idle",
                workspace_path=project.workspace_path,
            )
        )
        db.commit()
        project_id = project.id
    finally:
        db.close()

    settings_response = client.get(f"/api/settings?project_id={project_id}")
    assert settings_response.status_code == 200
    assert settings_response.json()["runner_mode"] == "dry_run"

    dashboard_response = client.get("/api/dashboard/summary")
    assert dashboard_response.status_code == 200

    system_status_response = client.get(f"/api/projects/{project_id}/system/status", headers=bridge_headers)
    assert system_status_response.status_code == 200

    db = SessionLocal()
    try:
        stored = db.get(Project, project_id)
        assert stored is not None
        row_count = db.scalar(select(func.count(ProjectSettings.id)).where(ProjectSettings.project_id == project_id))
        assert row_count == 0
        original_last_opened_at = stored.last_opened_at
    finally:
        db.close()

    workspace_response = client.get(f"/api/projects/{project_id}/workspace")
    assert workspace_response.status_code == 200
    assert workspace_response.json()["project"]["id"] == project_id

    db = SessionLocal()
    try:
        stored = db.get(Project, project_id)
        assert stored is not None
        row_count = db.scalar(select(func.count(ProjectSettings.id)).where(ProjectSettings.project_id == project_id))
        assert row_count == 0
        assert stored.last_opened_at == original_last_opened_at
    finally:
        db.close()


def test_updating_legacy_project_settings_creates_the_row(client) -> None:
    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Legacy Settings Write",
            idea="This project should persist settings when explicitly updated.",
            workspace_path=sample_workspace("legacy-settings-write"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        db.add(
            Agent(
                project_id=project.id,
                name="Manager AI",
                role="Project orchestration",
                kind="manager",
                status="idle",
                workspace_path=project.workspace_path,
            )
        )
        db.commit()
        project_id = project.id
    finally:
        db.close()

    response = client.put(
        f"/api/settings?project_id={project_id}",
        json={
            "provider": "ollama",
            "manager_model": "qwen2.5:7b",
            "default_worker_model": "llama3:latest",
            "manager_reasoning_effort": "medium",
            "default_worker_reasoning_effort": "low",
            "per_role_model_overrides_json": {},
            "per_role_reasoning_overrides_json": {},
            "adapter_command": None,
            "adapter_args_json": [],
            "runner_mode": "dry_run",
            "sandbox_mode": "workspace-write",
            "approval_policy": "on-request",
            "workspace_widgets_json": [],
            "approval_overrides_json": {},
        },
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "ollama"

    db = SessionLocal()
    try:
        settings = db.scalar(select(ProjectSettings).where(ProjectSettings.project_id == project_id))
        assert settings is not None
        assert settings.provider == "ollama"
    finally:
        db.close()


def test_change_request_route_creates_record_and_manager_notice(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Change Request Demo",
            "idea": "Track scoped follow-up work",
            "workspace_path": sample_workspace("change-request-demo"),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()

    created = client.post(
        f"/api/projects/{project['id']}/change-requests",
        json={"request_text": "Add an explicit change-request intake flow"},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["project_id"] == project["id"]
    assert payload["classification"] == "needs_triage"
    assert payload["status"] == "new"

    duplicate = client.post(
        f"/api/projects/{project['id']}/change-requests",
        json={"request_text": "  Add   an explicit  change-request intake flow  "},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == payload["id"]

    db = SessionLocal()
    try:
        stored_requests = list(
            db.scalars(select(ChangeRequest).where(ChangeRequest.project_id == project["id"]).order_by(ChangeRequest.id.asc()))
        )
        assert len(stored_requests) == 1
        assert stored_requests[0].request_text == "Add an explicit change-request intake flow"

        manager_notice = db.scalar(
            select(ManagerMessage)
            .where(ManagerMessage.project_id == project["id"], ManagerMessage.message_type == "system_notice")
            .order_by(ManagerMessage.id.desc())
        )
        assert manager_notice is not None
        assert "Change request logged" in manager_notice.content_markdown
        assert manager_notice.metadata_json is not None
        assert manager_notice.metadata_json["change_request_id"] == payload["id"]
    finally:
        db.close()


def test_import_existing_folder_reuses_existing_workspace_project(client) -> None:
    workspace = Path(sample_workspace("import-folder-reuse"))
    workspace.mkdir(parents=True, exist_ok=True)
    created = client.post(
        "/api/projects",
        json={
            "name": "Import Folder Reuse",
            "idea": "Existing workspace project",
            "workspace_path": workspace.as_posix(),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    )
    assert created.status_code == 200, created.text
    project_id = created.json()["id"]

    imported = client.post(
        "/api/projects/import-folder",
        json={"folder_path": workspace.as_posix(), "import_mode": "linked", "start_read_only_scan": False},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["project"]["id"] == project_id
