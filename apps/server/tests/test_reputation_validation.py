from __future__ import annotations

from conftest import sample_workspace
from db import SessionLocal
from models import Agent, Task


def test_agent_performance_record_route_rejects_nonexistent_or_mismatched_refs(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Reputation Validation",
            "idea": "Validate performance record scoping.",
            "workspace_path": sample_workspace("reputation-validation"),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    foreign = client.post(
        "/api/projects",
        json={
            "name": "Reputation Foreign",
            "idea": "Provide foreign references.",
            "workspace_path": sample_workspace("reputation-foreign"),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()

    db = SessionLocal()
    try:
        agent = Agent(
            project_id=project["id"],
            name="Worker One",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project["workspace_path"],
        )
        task = Task(
            project_id=project["id"],
            title="Scoped task",
            goal="Track a valid performance record.",
            scope="Keep the record scoped.",
            agent_role="Implementation",
            milestone="Validation",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Stay scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        foreign_task = Task(
            project_id=foreign["id"],
            title="Foreign task",
            goal="Act as an invalid reference.",
            scope="Cross-project validation fixture.",
            agent_role="Implementation",
            milestone="Validation",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Stay scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([agent, task, foreign_task])
        db.commit()

        ok = client.post(
            "/api/agents/performance-record",
            json={
                "project_id": project["id"],
                "agent_archetype": "generalist",
                "agent_name": "Worker One",
                "task_category": "validation",
                "task_id": task.id,
                "outcome": "success",
            },
        )
        assert ok.status_code == 200, ok.text

        missing_project = client.post(
            "/api/agents/performance-record",
            json={
                "project_id": 999_999,
                "agent_archetype": "generalist",
                "task_category": "validation",
            },
        )
        assert missing_project.status_code == 404
        assert "Project not found" in missing_project.json()["detail"]

        missing_task = client.post(
            "/api/agents/performance-record",
            json={
                "project_id": project["id"],
                "agent_archetype": "generalist",
                "task_category": "validation",
                "task_id": 999_999,
            },
        )
        assert missing_task.status_code == 404
        assert "Task not found" in missing_task.json()["detail"]

        missing_project_scope = client.post(
            "/api/agents/performance-record",
            json={
                "agent_archetype": "generalist",
                "task_category": "validation",
                "task_id": task.id,
            },
        )
        assert missing_project_scope.status_code == 400
        assert "require a project_id" in missing_project_scope.json()["detail"]

        foreign_task_response = client.post(
            "/api/agents/performance-record",
            json={
                "project_id": project["id"],
                "agent_archetype": "generalist",
                "task_category": "validation",
                "task_id": foreign_task.id,
            },
        )
        assert foreign_task_response.status_code == 404
        assert "Task not found in this project" in foreign_task_response.json()["detail"]
    finally:
        db.close()
