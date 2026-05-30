from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from conftest import sample_workspace
from db import SessionLocal, init_db
from models import Agent, AgentArchetype, AgentRun, ImportedCodebaseSafety, Project, SecurityPolicy, SwarmPreferences, Task, ValidationCoverageArea
from schemas import RunReportRequest


def _create_project(client, name: str, workspace_name: str) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"{name} idea",
            "workspace_path": sample_workspace(workspace_name),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_legacy_project(name: str, workspace_name: str) -> int:
    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name=name,
            idea=f"{name} idea",
            workspace_path=sample_workspace(workspace_name),
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
        return project.id
    finally:
        db.close()


def test_agent_archetypes_get_does_not_seed_rows(client) -> None:
    init_db()
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AgentArchetype.id))) == 0
    finally:
        db.close()

    response = client.get("/api/agent-archetypes")
    assert response.status_code == 200, response.text
    assert response.json()

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AgentArchetype.id))) == 0
    finally:
        db.close()


def test_swarm_preferences_get_returns_defaults_without_persisting_row(client) -> None:
    project_id = _create_legacy_project("Swarm Read Safety", "swarm-read-safety")

    response = client.get(f"/api/projects/{project_id}/swarm/preferences")
    assert response.status_code == 200, response.text
    assert response.json()["optimization_mode"] == "balanced"

    db = SessionLocal()
    try:
        row_count = db.scalar(select(func.count(SwarmPreferences.project_id)).where(SwarmPreferences.project_id == project_id))
        assert row_count == 0
    finally:
        db.close()


def test_validation_coverage_get_returns_preview_without_persisting_rows(client) -> None:
    project_id = _create_legacy_project("Coverage Preview", "coverage-preview")

    response = client.get(f"/api/projects/{project_id}/validation-coverage")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    assert all(item["project_id"] == project_id for item in payload)

    db = SessionLocal()
    try:
        row_count = db.scalar(select(func.count(ValidationCoverageArea.id)).where(ValidationCoverageArea.project_id == project_id))
        assert row_count == 0
    finally:
        db.close()


def test_safe_mode_get_and_import_safety_do_not_mutate_non_imported_project(client, bridge_headers) -> None:
    project_id = _create_legacy_project("Safe Mode Read", "safe-mode-read")

    response = client.get(f"/api/projects/{project_id}/safe-mode", headers=bridge_headers)
    assert response.status_code == 200, response.text
    assert response.json()["project_id"] == project_id

    import_safety = client.get(f"/api/projects/{project_id}/import-safety")
    assert import_safety.status_code == 400

    db = SessionLocal()
    try:
        project_policy_count = db.scalar(select(func.count(SecurityPolicy.id)).where(SecurityPolicy.project_id == project_id))
        swarm_pref_count = db.scalar(select(func.count(SwarmPreferences.project_id)).where(SwarmPreferences.project_id == project_id))
        import_safety_count = db.scalar(select(func.count(ImportedCodebaseSafety.project_id)).where(ImportedCodebaseSafety.project_id == project_id))
        assert project_policy_count == 0
        assert swarm_pref_count == 0
        assert import_safety_count == 0
    finally:
        db.close()


def test_global_id_routes_require_matching_project_scope(client, bridge_headers) -> None:
    project_one = _create_project(client, "Scope One", "scope-one-read")
    project_two = _create_project(client, "Scope Two", "scope-two-read")

    workspace = Path(project_one["workspace_path"])
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# Existing codebase\n", encoding="utf-8")

    pack = client.post(
        f"/api/projects/{project_one['id']}/context-packs/build",
        json={"title": "Scoped Pack", "goal": "Summarize the repo for workers."},
    )
    assert pack.status_code == 200, pack.text
    pack_id = pack.json()["id"]

    wrong_pack = client.get(f"/api/context-packs/{pack_id}", params={"project_id": project_two["id"]})
    assert wrong_pack.status_code == 404

    orchestration = client.post(
        "/api/orchestrations",
        headers=bridge_headers,
        json={"project_id": project_one["id"], "user_request": "Run Mission Control here.", "source": "test"},
    )
    assert orchestration.status_code == 200, orchestration.text
    orchestration_id = orchestration.json()["id"]

    wrong_status = client.get(
        f"/api/orchestrations/{orchestration_id}/status",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_status.status_code == 404

    opened = client.post(f"/api/projects/{project_one['id']}/open")
    assert opened.status_code == 200, opened.text
    question = client.get(f"/api/projects/{project_one['id']}/questions/pending").json()[0]
    wrong_auto_decide = client.post(
        f"/api/questions/{question['id']}/auto-decide",
        params={"project_id": project_two["id"]},
    )
    assert wrong_auto_decide.status_code == 404

    db = SessionLocal()
    try:
        stored = db.get(Project, project_one["id"])
        assert stored is not None
    finally:
        db.close()


def test_agent_task_and_run_routes_require_matching_project_scope(client) -> None:
    project_one = _create_project(client, "Runtime Scope One", "runtime-scope-one")
    project_two = _create_project(client, "Runtime Scope Two", "runtime-scope-two")

    db = SessionLocal()
    try:
        worker = Agent(
            project_id=project_one["id"],
            name="Scoped Worker",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project_one["workspace_path"],
        )
        task = Task(
            project_id=project_one["id"],
            title="Scoped task",
            goal="Keep task actions isolated.",
            scope="Limit task actions to the owning project.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest"],
            success_criteria_json=["Task stays scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="scope-test", status="working")
        db.add(run)
        db.commit()
        db.refresh(worker)
        db.refresh(task)
        db.refresh(run)
        worker_id = worker.id
        task_id = task.id
        run_id = run.id
    finally:
        db.close()

    assert client.post(f"/api/agents/{worker_id}/start", params={"project_id": project_two["id"]}).status_code == 404
    assert client.post(f"/api/agents/{worker_id}/pause", params={"project_id": project_two["id"]}).status_code == 404
    assert client.post(f"/api/agents/{worker_id}/stop", params={"project_id": project_two["id"]}).status_code == 404
    assert client.get(f"/api/agents/{worker_id}/logs", params={"project_id": project_two["id"]}).status_code == 404
    assert client.post(f"/api/tasks/{task_id}/start", params={"project_id": project_two["id"]}).status_code == 404
    assert client.post(f"/api/tasks/{task_id}/complete", params={"project_id": project_two["id"]}).status_code == 404

    wrong_report = client.post(
        f"/api/runs/{run_id}/report",
        params={"project_id": project_two["id"]},
        json=RunReportRequest(
            agent="Scoped Worker",
            task_id=str(task_id),
            status="done",
            summary="Completed",
            files_changed=["src/app.py"],
            tests_run=["pytest"],
            blockers=[],
            risks=[],
            recommended_next_task="",
        ).model_dump(),
    )
    assert wrong_report.status_code == 404

    correct_logs = client.get(f"/api/agents/{worker_id}/logs", params={"project_id": project_one["id"]})
    assert correct_logs.status_code == 200, correct_logs.text

    correct_complete = client.post(f"/api/tasks/{task_id}/complete", params={"project_id": project_one["id"]})
    assert correct_complete.status_code == 200, correct_complete.text
