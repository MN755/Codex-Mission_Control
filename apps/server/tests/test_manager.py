from __future__ import annotations

import asyncio

from manager import MissionControlService
from models import Agent, AgentRun, Project, Task
from project_settings import get_or_create_project_settings, resolve_manager_settings, resolve_worker_settings
from schemas import WorkerReport


def test_manager_doc_generation_uses_deterministic_for_dry_run(client) -> None:
    response = client.post(
        "/api/projects",
        json={
            "name": "Docs Demo",
            "idea": "Build a local project manager",
            "workspace_path": "C:/Users/mike/OneDrive/Desktop/Codex Mission Control/apps/server/.runtime/docs-demo",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    project_id = response.json()["id"]
    docs = client.post(f"/api/projects/{project_id}/docs/generate").json()
    assert docs["manager_mode_used"] == "deterministic"


def test_path_reservations_acquire_and_release() -> None:
    service = MissionControlService()

    class DummyDb:
        pass

    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Demo", idea="Idea", workspace_path="C:/demo", status="building", runner_mode="dry_run", manager_mode="auto")
        db.add(project)
        db.flush()
        agent = Agent(project_id=project.id, name="Worker", role="Primary implementation", kind="worker", status="idle", workspace_path="C:/demo")
        task = Task(
            project_id=project.id,
            title="Task",
            goal="Goal",
            scope="Scope",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["check"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([agent, task])
        db.flush()
        service._reserve_task_paths(db, project, agent, task)
        assert len(service.list_reservations(db, project.id)) == 1
        service._release_reservations(db, project.id, task_id=task.id, agent_id=agent.id)
        assert len(service.list_reservations(db, project.id)) == 0
    finally:
        db.close()


def test_worker_report_ingestion_routes_next_task() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Demo",
            idea="Idea",
            workspace_path="C:/Users/mike/OneDrive/Desktop/Codex Mission Control/apps/server/.runtime/unit-demo",
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="working", workspace_path=project.workspace_path, current_task_id=1, locked_paths_json=["src"])
        task_one = Task(
            id=1,
            project_id=project.id,
            assigned_agent_id=None,
            title="Vertical slice",
            goal="Build",
            scope="Scope",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["run"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        task_two = Task(
            project_id=project.id,
            title="Validation",
            goal="Validate",
            scope="Scope",
            agent_role="Primary implementation",
            milestone="Milestone 2",
            allowed_paths_json=["tests"],
            forbidden_paths_json=[],
            validation_steps_json=["test"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([manager_agent, worker, task_one, task_two])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task_one.id, runner_type="dry_run", process_ref="dry-test", status="working")
        db.add(run)
        db.flush()
        report = WorkerReport(
            agent=worker.name,
            task_id=str(task_one.id),
            status="done",
            summary="Completed",
            files_changed=["src/app.ts"],
            tests_run=["npm run build"],
            blockers=[],
            risks=[],
            recommended_next_task="Validation",
        )
        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        assert task_one.status == "done"
        assert decision.decision_type in {"assign_next_task", "wait"}
    finally:
        db.close()


def test_project_settings_resolution_prefers_role_overrides() -> None:
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Settings Demo", idea="Idea", workspace_path="C:/demo", status="draft", runner_mode="auto", manager_mode="auto")
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.manager_model = "gpt-5.5"
        settings.manager_reasoning_effort = "high"
        settings.default_worker_model = "gpt-5.4"
        settings.default_worker_reasoning_effort = "low"
        settings.per_role_model_overrides_json = {"Primary implementation": "gpt-5.5-mini"}
        settings.per_role_reasoning_overrides_json = {"Primary implementation": "minimal"}

        manager_settings = resolve_manager_settings(project, settings)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="idle", workspace_path="C:/demo")
        worker_settings = resolve_worker_settings(project, settings, worker)

        assert manager_settings.model == "gpt-5.5"
        assert manager_settings.reasoning_effort == "high"
        assert worker_settings.model == "gpt-5.5-mini"
        assert worker_settings.reasoning_effort == "minimal"
    finally:
        db.close()
