from __future__ import annotations

from db import SessionLocal
from models import Agent, Project, Task
from conftest import sample_workspace


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


def test_risk_update_rejects_owner_agent_from_another_project(client) -> None:
    project_one = _create_project(client, "Risk Owner Project", "risk-owner-project")
    project_two = _create_project(client, "Foreign Agent Project", "foreign-agent-project")

    db = SessionLocal()
    try:
        foreign_agent = Agent(
            project_id=project_two["id"],
            name="Foreign Worker",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project_two["workspace_path"],
        )
        db.add(foreign_agent)
        db.commit()
        foreign_agent_id = foreign_agent.id
    finally:
        db.close()

    created = client.post(
        f"/api/projects/{project_one['id']}/risks",
        json={
            "title": "Cross-project risk owner",
            "description": "Keep owner validation honest.",
            "severity": "medium",
            "likelihood": "medium",
        },
    )
    assert created.status_code == 200, created.text

    response = client.patch(
        f"/api/risks/{created.json()['id']}",
        json={"project_id": project_one["id"], "owner_agent_id": foreign_agent_id},
    )
    assert response.status_code == 404
    assert "owner agent" in response.json()["detail"].lower()


def test_risk_update_rejects_related_task_from_another_project(client) -> None:
    project_one = _create_project(client, "Risk Task Project", "risk-task-project")
    project_two = _create_project(client, "Foreign Task Project", "foreign-task-project")

    db = SessionLocal()
    try:
        foreign_task = Task(
            project_id=project_two["id"],
            title="Foreign task",
            goal="This task belongs somewhere else.",
            scope="Do not let another project point at it.",
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
        db.add(foreign_task)
        db.commit()
        foreign_task_id = foreign_task.id
    finally:
        db.close()

    created = client.post(
        f"/api/projects/{project_one['id']}/risks",
        json={
            "title": "Cross-project risk task",
            "description": "Keep task validation honest.",
            "severity": "medium",
            "likelihood": "medium",
        },
    )
    assert created.status_code == 200, created.text

    response = client.patch(
        f"/api/risks/{created.json()['id']}",
        json={"project_id": project_one["id"], "related_task_id": foreign_task_id},
    )
    assert response.status_code == 404
    assert "related task" in response.json()["detail"].lower()


def test_risk_update_rejects_nonexistent_related_refs(client) -> None:
    project = _create_project(client, "Missing Refs Project", "missing-refs-project")
    created = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "Missing refs risk",
            "description": "Do not accept fake references.",
            "severity": "medium",
            "likelihood": "medium",
        },
    )
    assert created.status_code == 200, created.text

    owner_response = client.patch(
        f"/api/risks/{created.json()['id']}",
        json={"project_id": project["id"], "owner_agent_id": 999_999},
    )
    assert owner_response.status_code == 404
    assert "owner agent" in owner_response.json()["detail"].lower()

    task_response = client.patch(
        f"/api/risks/{created.json()['id']}",
        json={"project_id": project["id"], "related_task_id": 999_999},
    )
    assert task_response.status_code == 404
    assert "related task" in task_response.json()["detail"].lower()


def test_risk_create_dedupe_updates_mutable_fields(client) -> None:
    project = _create_project(client, "Risk Dedupe Update", "risk-dedupe-update")
    db = SessionLocal()
    try:
        owner = Agent(
            project_id=project["id"],
            name="Risk Owner",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project["workspace_path"],
        )
        task = Task(
            project_id=project["id"],
            title="Risk Task",
            goal="Validate risk dedupe state",
            scope="Keep risk refs scoped.",
            agent_role="Implementation",
            milestone="Validation",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["State stays current"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(owner)
        db.add(task)
        db.commit()
        owner_id = owner.id
        task_id = task.id
    finally:
        db.close()

    created = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "same risk",
            "description": "first",
            "severity": "low",
            "likelihood": "low",
            "mitigation": "m1",
        },
    )
    assert created.status_code == 200, created.text

    updated = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "same risk",
            "description": "second",
            "severity": "high",
            "likelihood": "high",
            "mitigation": "m2",
            "status": "accepted",
            "owner_agent_id": owner_id,
            "related_task_id": task_id,
        },
    )
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["id"] == created.json()["id"]
    assert payload["description"] == "second"
    assert payload["severity"] == "high"
    assert payload["likelihood"] == "high"
    assert payload["mitigation"] == "m2"
    assert payload["status"] == "accepted"
    assert payload["owner_agent_id"] == owner_id
    assert payload["related_task_id"] == task_id
