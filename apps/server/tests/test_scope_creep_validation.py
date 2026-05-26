from __future__ import annotations

from sqlalchemy import func, select

from conftest import sample_workspace
from db import SessionLocal
from models import ScopeChangeSignal


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


def test_scope_creep_analyze_rejects_nonexistent_related_task_id(client) -> None:
    project = _create_project(client, "Scope Creep Task Validation", "scope-creep-task-validation")

    response = client.post(
        f"/api/projects/{project['id']}/scope-creep/analyze",
        json={
            "summary": "Need a surprise rewrite.",
            "related_task_id": 999999,
        },
    )

    assert response.status_code == 404, response.text
    assert "not found" in response.json()["detail"].lower()

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ScopeChangeSignal.id)).where(ScopeChangeSignal.project_id == project["id"])) == 0
    finally:
        db.close()


def test_scope_creep_analyze_rejects_nonexistent_related_message_id(client) -> None:
    project = _create_project(client, "Scope Creep Message Validation", "scope-creep-message-validation")

    response = client.post(
        f"/api/projects/{project['id']}/scope-creep/analyze",
        json={
            "summary": "Need a surprise rewrite.",
            "related_message_id": 999999,
        },
    )

    assert response.status_code == 404, response.text
    assert "not found" in response.json()["detail"].lower()

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ScopeChangeSignal.id)).where(ScopeChangeSignal.project_id == project["id"])) == 0
    finally:
        db.close()
