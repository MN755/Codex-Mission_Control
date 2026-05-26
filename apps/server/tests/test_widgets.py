from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from conftest import sample_workspace
from db import SessionLocal
from models import AppEvent, AppProfile, DecisionRecord, PathLock, ProjectEvent, ProjectSettings


def create_project(client, name: str, workspace_name: str, workspace_path: str | None = None) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"{name} idea",
            "workspace_path": workspace_path or sample_workspace(workspace_name),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_widget_catalog_and_default_dashboard_instances_seed(client) -> None:
    catalog = client.get("/api/widgets/catalog").json()
    assert any(item["widget_type"] == "Needs Attention" and item["scope"] == "dashboard" for item in catalog)
    assert any(item["widget_type"] == "Swarm Budget" and item["scope"] == "project" for item in catalog)

    project_catalog = client.get("/api/widgets/catalog", params={"scope": "project"}).json()
    assert project_catalog
    assert all(item["scope"] == "project" for item in project_catalog)

    instances = client.get("/api/widgets/instances", params={"scope": "dashboard"}).json()
    enabled_types = {item["widget_type"] for item in instances if item["enabled"]}
    assert {
        "Needs Attention",
        "Active Builds",
        "Recent Handoffs",
        "Runner & Provider Status",
        "Swarm Budget Overview",
        "Project Health Overview",
    }.issubset(enabled_types)

    db = SessionLocal()
    try:
        profile = db.get(AppProfile, 1)
        assert profile is not None
        assert set(profile.dashboard_widgets_json or []).issuperset(enabled_types)
    finally:
        db.close()


def test_dashboard_widget_instances_seed_from_legacy_profile_preferences(client, bridge_headers) -> None:
    response = client.put(
        "/api/profile",
        json={
            "dashboard_widgets_json": ["Connected Accounts", "Diagnostics Summary"],
        },
        headers=bridge_headers,
    )
    assert response.status_code == 200

    instances = client.get("/api/widgets/instances", params={"scope": "dashboard"}).json()
    assert [item["widget_type"] for item in instances if item["enabled"]] == ["Connected Accounts", "Diagnostics Summary"]


def test_project_widget_instances_seed_from_legacy_workspace_preferences(client) -> None:
    project = create_project(client, "Legacy Widget Project", "legacy-widget-project")
    project_id = project["id"]

    db = SessionLocal()
    try:
        settings = ProjectSettings(project_id=project_id, workspace_widgets_json=["Repo Intelligence", "Validation Recipe"])
        db.add(settings)
        db.commit()
    finally:
        db.close()

    instances = client.get(f"/api/projects/{project_id}/widgets/instances").json()
    assert [item["widget_type"] for item in instances if item["enabled"]] == ["Repo Intelligence", "Validation Recipe"]


def test_dashboard_widget_instance_crud_publishes_app_events(client) -> None:
    created = client.post(
        "/api/widgets/instances",
        json={
            "scope": "dashboard",
            "widget_type": "Connected Accounts",
            "area": "dashboard_bottom",
            "size": "small",
        },
    )
    assert created.status_code == 200
    created_payload = created.json()
    instance_id = created_payload["id"]
    assert created_payload["widget_type"] == "Connected Accounts"

    updated = client.patch(
        f"/api/widgets/instances/{instance_id}",
        json={
            "collapsed": True,
            "size": "large",
            "order_index": 0,
        },
    )
    assert updated.status_code == 200
    updated_payload = updated.json()
    assert updated_payload["collapsed"] is True
    assert updated_payload["size"] == "large"

    deleted = client.delete(f"/api/widgets/instances/{instance_id}")
    assert deleted.status_code == 204

    db = SessionLocal()
    try:
        actions = [
            event.payload_json.get("action")
            for event in db.scalars(
                select(AppEvent)
                .where(AppEvent.event_type == "widget_instances_updated")
                .order_by(AppEvent.id.asc())
            )
        ]
        assert actions == ["created", "updated", "deleted"]
        profile = db.get(AppProfile, 1)
        assert profile is not None
        assert "Connected Accounts" not in (profile.dashboard_widgets_json or [])
    finally:
        db.close()


def test_repo_intelligence_widget_scans_workspace_safely(client) -> None:
    workspace_root = Path(sample_workspace("repo-intel"))
    (workspace_root / "src").mkdir(parents=True, exist_ok=True)
    (workspace_root / "docs").mkdir(parents=True, exist_ok=True)
    (workspace_root / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {
                    "react": "^19.0.0",
                    "vite": "^6.0.0",
                },
                "scripts": {
                    "build": "vite build",
                    "test": "vitest run",
                },
            }
        ),
        encoding="utf-8",
    )
    (workspace_root / "package-lock.json").write_text("{}", encoding="utf-8")
    (workspace_root / "src" / "main.tsx").write_text("export const main = true;\n", encoding="utf-8")
    (workspace_root / "README.md").write_text("# Repo Intelligence\n", encoding="utf-8")
    (workspace_root / "Dockerfile").write_text("FROM node:20\n", encoding="utf-8")

    project = create_project(client, "Repo Intelligence", "repo-intel", workspace_root.as_posix())
    instance = client.post(
        f"/api/projects/{project['id']}/widgets/add",
        json={"widget_type": "Repo Intelligence"},
    ).json()

    data = client.get(f"/api/widgets/instances/{instance['id']}/data").json()
    assert data["status"] == "ready"
    assert "TypeScript" in data["data_json"]["languages"]
    assert "React" in data["data_json"]["frameworks"]
    assert "Vite" in data["data_json"]["frameworks"]
    assert "npm" in data["data_json"]["package_managers"]
    assert "src/main.tsx" in data["data_json"]["entry_points"]
    assert any(command.startswith("npm run build") for command in data["data_json"]["build_commands"])
    assert "README.md" in data["data_json"]["docs_found"]
    assert "Dockerfile" in data["data_json"]["deployment_config"]


def test_project_widget_data_is_project_scoped_and_emits_project_events(client) -> None:
    project_one = create_project(client, "Decision One", "decision-one")
    project_two = create_project(client, "Decision Two", "decision-two")

    first_instance = client.post(
        f"/api/projects/{project_one['id']}/widgets/add",
        json={"widget_type": "Decision Ledger"},
    ).json()
    second_instance = client.post(
        f"/api/projects/{project_two['id']}/widgets/add",
        json={"widget_type": "Decision Ledger"},
    ).json()

    db = SessionLocal()
    try:
        db.add(
            DecisionRecord(
                project_id=project_one["id"],
                decision_type="architecture",
                title="Use local widget grid",
                decision="Move dashboard summaries into scoped widgets.",
                reason="Keeps dashboard and workspace modular without making Manager Chat another panel zoo.",
                made_by="manager",
                impact_area_json=["dashboard", "workspace"],
                reversible=True,
            )
        )
        db.add(
            PathLock(
                project_id=project_one["id"],
                path_pattern="apps/dashboard/src/pages/*",
                owner_agent_id=None,
                owner_task_id=None,
                reason="Feature agent owns dashboard widget integration.",
                status="active",
            )
        )
        db.commit()
    finally:
        db.close()

    first_data = client.get(f"/api/widgets/instances/{first_instance['id']}/data").json()
    second_data = client.get(f"/api/widgets/instances/{second_instance['id']}/data").json()
    assert first_data["status"] == "ready"
    assert first_data["data_json"]["items"][0]["title"] == "Use local widget grid"
    assert second_data["status"] == "empty"

    summary = client.get(f"/api/projects/{project_one['id']}/widgets/summary").json()
    assert summary["scope"] == "project"
    assert summary["project_id"] == project_one["id"]
    assert any(item["widget_type"] == "Decision Ledger" for item in summary["instances"])

    db = SessionLocal()
    try:
        project_events = list(
            db.scalars(
                select(ProjectEvent)
                .where(
                    ProjectEvent.project_id == project_one["id"],
                    ProjectEvent.event_type == "widget_instances_updated",
                )
                .order_by(ProjectEvent.id.asc())
            )
        )
        assert project_events
        mirrored_app_events = list(
            db.scalars(
                select(AppEvent)
                .where(
                    AppEvent.event_type == "widget_instances_updated",
                )
                .order_by(AppEvent.id.asc())
            )
        )
        assert any(event.payload_json.get("project_id") == project_one["id"] for event in mirrored_app_events)
    finally:
        db.close()


def test_profile_rejects_unknown_and_wrong_scope_dashboard_widgets(client, bridge_headers) -> None:
    seeded = client.put(
        "/api/profile",
        json={"dashboard_widgets_json": ["Needs Attention", "Recent Handoffs"]},
        headers=bridge_headers,
    )
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["dashboard_widgets_json"] == ["Needs Attention", "Recent Handoffs"]

    wrong_scope = client.put(
        "/api/profile",
        json={"dashboard_widgets_json": ["Validation Recipe"]},
        headers=bridge_headers,
    )
    assert wrong_scope.status_code == 400, wrong_scope.text
    assert "dashboard widgets" in wrong_scope.json()["detail"].lower()

    unknown = client.put(
        "/api/profile",
        json={"dashboard_widgets_json": ["Ghost Widget"]},
        headers=bridge_headers,
    )
    assert unknown.status_code == 400, unknown.text
    assert "ghost widget" in unknown.json()["detail"].lower()

    profile = client.get("/api/profile", headers=bridge_headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["dashboard_widgets_json"] == ["Needs Attention", "Recent Handoffs"]


def test_settings_reject_unknown_and_wrong_scope_project_widgets(client, bridge_headers) -> None:
    project = create_project(client, "Project Widget Settings Validation", "project-widget-settings-validation")

    seeded = client.put(
        "/api/settings",
        params={"project_id": project["id"]},
        json={"workspace_widgets_json": ["Validation Recipe", "Manager Assumptions"]},
        headers=bridge_headers,
    )
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["workspace_widgets_json"] == ["Validation Recipe", "Manager Assumptions"]

    wrong_scope = client.put(
        "/api/settings",
        params={"project_id": project["id"]},
        json={"workspace_widgets_json": ["Needs Attention"]},
        headers=bridge_headers,
    )
    assert wrong_scope.status_code == 400, wrong_scope.text
    assert "workspace widgets" in wrong_scope.json()["detail"].lower()

    unknown = client.put(
        "/api/settings",
        params={"project_id": project["id"]},
        json={"workspace_widgets_json": ["Ghost Widget"]},
        headers=bridge_headers,
    )
    assert unknown.status_code == 400, unknown.text
    assert "ghost widget" in unknown.json()["detail"].lower()

    settings = client.get("/api/settings", params={"project_id": project["id"]}, headers=bridge_headers)
    assert settings.status_code == 200, settings.text
    assert settings.json()["workspace_widgets_json"] == ["Validation Recipe", "Manager Assumptions"]


def test_project_widget_update_rejects_invalid_names_without_clearing_existing_widgets(client, bridge_headers) -> None:
    project = create_project(client, "Project Widget Update Validation", "project-widget-update-validation")

    seeded = client.post(
        f"/api/projects/{project['id']}/widgets",
        json={"widgets": ["Validation Recipe"]},
        headers=bridge_headers,
    )
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["workspace_widgets_json"] == ["Validation Recipe"]

    wrong_scope = client.post(
        f"/api/projects/{project['id']}/widgets",
        json={"widgets": ["Needs Attention"]},
        headers=bridge_headers,
    )
    assert wrong_scope.status_code == 400, wrong_scope.text
    assert "project widgets" in wrong_scope.json()["detail"].lower()

    unknown = client.post(
        f"/api/projects/{project['id']}/widgets",
        json={"widgets": ["Ghost Widget"]},
        headers=bridge_headers,
    )
    assert unknown.status_code == 400, unknown.text
    assert "ghost widget" in unknown.json()["detail"].lower()

    settings = client.get("/api/settings", params={"project_id": project["id"]}, headers=bridge_headers)
    assert settings.status_code == 200, settings.text
    assert settings.json()["workspace_widgets_json"] == ["Validation Recipe"]
