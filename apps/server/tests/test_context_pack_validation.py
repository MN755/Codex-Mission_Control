from __future__ import annotations

from sqlalchemy import func, select

from conftest import sample_workspace
from db import SessionLocal
from models import ContextPack


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


def test_context_pack_build_rejects_nonexistent_agent_id(client) -> None:
    project = _create_project(client, "Context Pack Agent Validation", "context-pack-agent-validation")

    response = client.post(
        f"/api/projects/{project['id']}/context-packs/build",
        json={"agent_id": 999999},
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Agent not found"

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ContextPack.id)).where(ContextPack.project_id == project["id"])) == 0
    finally:
        db.close()


def test_context_pack_build_rejects_nonexistent_task_id(client) -> None:
    project = _create_project(client, "Context Pack Task Validation", "context-pack-task-validation")

    response = client.post(
        f"/api/projects/{project['id']}/context-packs/build",
        json={"task_id": 999999},
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Task not found"

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ContextPack.id)).where(ContextPack.project_id == project["id"])) == 0
    finally:
        db.close()
