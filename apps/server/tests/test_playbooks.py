from __future__ import annotations

from sqlalchemy import select

from conftest import sample_workspace
from db import SessionLocal
from models import DecisionRecord, ValidationRecipe


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
