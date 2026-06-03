from __future__ import annotations

from sqlalchemy import select

from conftest import sample_workspace
from db import SessionLocal
from models import DecisionRecord, ProjectPlaybookSelection, ValidationRecipe


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


def test_reapplying_same_playbook_does_not_duplicate_decisions(client) -> None:
    project = _create_project(client, "Playbook Idempotence", "playbook-idempotence")

    first = client.post(
        f"/api/projects/{project['id']}/playbook/apply",
        json={"playbook_key": "fastapi_react_web_app"},
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"/api/projects/{project['id']}/playbook/apply",
        json={"playbook_key": "fastapi_react_web_app"},
    )
    assert second.status_code == 200, second.text

    db = SessionLocal()
    try:
        decisions = list(
            db.scalars(
                select(DecisionRecord)
                .where(DecisionRecord.project_id == project["id"], DecisionRecord.decision_type == "playbook")
                .order_by(DecisionRecord.id.asc())
            )
        )
        recipes = list(
            db.scalars(select(ValidationRecipe).where(ValidationRecipe.project_id == project["id"]).order_by(ValidationRecipe.id.asc()))
        )
        assert len(decisions) == 1
        assert len(recipes) == 1
        assert recipes[0].name == "FastAPI + React Web App validation recipe"
        assert recipes[0].status == "draft"
    finally:
        db.close()


def test_switching_playbooks_supersedes_prior_playbook_recipe(client) -> None:
    project = _create_project(client, "Playbook Switching", "playbook-switching")

    first = client.post(
        f"/api/projects/{project['id']}/playbook/apply",
        json={"playbook_key": "fastapi_react_web_app"},
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"/api/projects/{project['id']}/playbook/apply",
        json={"playbook_key": "static_docs_site"},
    )
    assert second.status_code == 200, second.text

    db = SessionLocal()
    try:
        recipes = {
            recipe.name: recipe
            for recipe in db.scalars(select(ValidationRecipe).where(ValidationRecipe.project_id == project["id"]))
        }
        assert recipes["FastAPI + React Web App validation recipe"].status == "superseded"
        assert recipes["Static Docs Site validation recipe"].status == "draft"
    finally:
        db.close()


def test_project_playbook_state_route_returns_applied_selection(client) -> None:
    project = _create_project(client, "Playbook State", "playbook-state")

    applied = client.post(
        f"/api/projects/{project['id']}/playbook/apply",
        json={"playbook_key": "fastapi_react_web_app"},
    )
    assert applied.status_code == 200, applied.text

    response = client.get(f"/api/projects/{project['id']}/playbook")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "applied"
    assert payload["playbook_key"] == "fastapi_react_web_app"
    assert payload["playbook"]["name"] == "FastAPI + React Web App"


def test_playbook_recommendations_rank_project_matches(client) -> None:
    project = _create_project(client, "Headless MCP Daemon Plugin", "playbook-recommendations")

    response = client.get(f"/api/projects/{project['id']}/playbook/recommendations", params={"limit": 4})
    assert response.status_code == 200, response.text
    payload = response.json()

    assert len(payload) == 4
    assert payload[0]["score"] >= payload[-1]["score"]
    assert payload[0]["playbook_key"] == "ai_local_tool"
    assert "headless orchestration" in payload[0]["why"].lower()


def test_project_playbook_state_get_does_not_persist_suggested_selection(client) -> None:
    project = _create_project(client, "Playbook Read Only", "playbook-read-only")

    db = SessionLocal()
    try:
        existing = db.get(ProjectPlaybookSelection, project["id"])
        if existing is not None:
            db.delete(existing)
            db.commit()
    finally:
        db.close()

    response = client.get(f"/api/projects/{project['id']}/playbook")
    assert response.status_code == 200, response.text
    assert response.json()["playbook_key"]

    db = SessionLocal()
    try:
        selection = db.get(ProjectPlaybookSelection, project["id"])
        assert selection is None
    finally:
        db.close()
