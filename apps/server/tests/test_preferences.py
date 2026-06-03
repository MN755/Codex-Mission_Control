from __future__ import annotations

from sqlalchemy import select

from conftest import sample_workspace
from db import SessionLocal
from models import UserPreference


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


def test_delete_global_preference_removes_row_and_hides_it_from_listing(client) -> None:
    created = client.put("/api/preferences/editor_theme", json={"value_json": "dark", "source": "user", "editable": True})
    assert created.status_code == 200, created.text

    deleted = client.delete("/api/preferences/editor_theme")
    assert deleted.status_code == 204, deleted.text

    listed = client.get("/api/preferences")
    assert listed.status_code == 200, listed.text
    assert listed.json() == []

    db = SessionLocal()
    try:
        assert db.scalar(select(UserPreference).where(UserPreference.key == "editor_theme")) is None
    finally:
        db.close()


def test_delete_project_preference_restores_global_fallback(client) -> None:
    project = _create_project(client, "Preference Fallback", "preference-fallback")
    client.put("/api/preferences/review_depth", json={"value_json": "standard", "source": "user", "editable": True})
    override = client.put(
        f"/api/projects/{project['id']}/preferences/review_depth",
        json={"value_json": "strict", "source": "user", "editable": True},
    )
    assert override.status_code == 200, override.text

    deleted = client.delete(f"/api/projects/{project['id']}/preferences/review_depth")
    assert deleted.status_code == 204, deleted.text

    effective = client.get(f"/api/projects/{project['id']}/preferences/effective")
    assert effective.status_code == 200, effective.text
    payload = effective.json()
    assert len(payload) == 1
    assert payload[0]["key"] == "review_depth"
    assert payload[0]["value_json"] == "standard"
    assert payload[0]["scope"] == "global"
    assert payload[0]["inherited"] is True


def test_effective_preferences_marks_inherited_and_project_override(client) -> None:
    project = _create_project(client, "Preference Effective", "preference-effective")
    client.put("/api/preferences/review_depth", json={"value_json": "standard", "source": "user", "editable": True})
    client.put("/api/preferences/docs_depth", json={"value_json": "publishable", "source": "setup", "editable": False})
    client.put(
        f"/api/projects/{project['id']}/preferences/review_depth",
        json={"value_json": "strict", "source": "manager_observed", "editable": True},
    )

    response = client.get(f"/api/projects/{project['id']}/preferences/effective")
    assert response.status_code == 200, response.text
    payload = {item["key"]: item for item in response.json()}

    assert payload["review_depth"]["scope"] == "project"
    assert payload["review_depth"]["value_json"] == "strict"
    assert payload["review_depth"]["inherited"] is False
    assert payload["docs_depth"]["scope"] == "global"
    assert payload["docs_depth"]["inherited"] is True


def test_preference_summary_reports_counts_for_global_and_project_views(client) -> None:
    project = _create_project(client, "Preference Summary", "preference-summary")
    client.put("/api/preferences/review_depth", json={"value_json": "standard", "source": "user", "editable": True})
    client.put("/api/preferences/docs_depth", json={"value_json": "publishable", "source": "setup", "editable": False})
    client.put(
        f"/api/projects/{project['id']}/preferences/review_depth",
        json={"value_json": "strict", "source": "manager_observed", "editable": True},
    )

    global_summary = client.get("/api/preferences/summary")
    assert global_summary.status_code == 200, global_summary.text
    global_payload = global_summary.json()
    assert global_payload["scope"] == "global"
    assert global_payload["item_count"] == 2
    assert global_payload["editable_count"] == 1
    assert global_payload["inherited_count"] == 0
    assert global_payload["project_override_count"] == 0

    project_summary = client.get(f"/api/projects/{project['id']}/preferences/summary")
    assert project_summary.status_code == 200, project_summary.text
    project_payload = project_summary.json()
    assert project_payload["scope"] == "project"
    assert project_payload["project_id"] == project["id"]
    assert project_payload["item_count"] == 2
    assert project_payload["editable_count"] == 1
    assert project_payload["inherited_count"] == 1
    assert project_payload["project_override_count"] == 1


def test_preference_routes_reject_blank_keys(client) -> None:
    global_response = client.put("/api/preferences/%20%20", json={"value_json": "dark", "source": "user", "editable": True})
    assert global_response.status_code == 400
    assert "cannot be blank" in global_response.json()["detail"].lower()

    project = _create_project(client, "Preference Blank Key", "preference-blank-key")
    project_response = client.put(
        f"/api/projects/{project['id']}/preferences/%20%20",
        json={"value_json": "strict", "source": "user", "editable": True},
    )
    assert project_response.status_code == 400
    assert "cannot be blank" in project_response.json()["detail"].lower()
