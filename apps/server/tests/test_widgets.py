from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from conftest import sample_workspace
from db import SessionLocal
from models import AppEvent, AppProfile, DecisionRecord, PathLock, ProjectEvent, ProjectSettings, WidgetDefinition, WidgetInstance


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


def test_widget_catalog_reads_are_read_only_and_dashboard_instances_stay_empty(client) -> None:
    catalog = client.get("/api/widgets/catalog").json()
    assert any(item["widget_type"] == "Needs Attention" and item["scope"] == "dashboard" for item in catalog)
    assert any(item["widget_type"] == "Swarm Budget" and item["scope"] == "project" for item in catalog)

    project_catalog = client.get("/api/widgets/catalog", params={"scope": "project"}).json()
    assert project_catalog
    assert all(item["scope"] == "project" for item in project_catalog)

    instances = client.get("/api/widgets/instances", params={"scope": "dashboard"}).json()
    assert instances == []

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(WidgetDefinition.id))) == 0
        assert db.scalar(select(func.count(WidgetInstance.id))) == 0
        profile = db.scalar(select(AppProfile).order_by(AppProfile.updated_at.desc(), AppProfile.id.desc()))
        assert profile is not None
        assert profile.dashboard_widgets_json == []
    finally:
        db.close()


def test_widget_catalog_read_preserves_existing_definition_edits(client) -> None:
    db = SessionLocal()
    try:
        definition = WidgetDefinition(
            widget_type="Connected Accounts",
            title="CUSTOM TITLE",
            description="Custom dashboard widget description.",
            scope="dashboard",
            default_area="dashboard_main",
            default_size="small",
            category="diagnostics",
            requires_project=False,
            requires_tool=None,
            coming_soon=False,
            risk_level="low",
        )
        db.add(definition)
        db.commit()
    finally:
        db.close()

    catalog = client.get("/api/widgets/catalog").json()
    customized = next(item for item in catalog if item["widget_type"] == "Connected Accounts")
    assert customized["title"] == "CUSTOM TITLE"

    db = SessionLocal()
    try:
        stored = db.scalar(select(WidgetDefinition).where(WidgetDefinition.widget_type == "Connected Accounts"))
        assert stored is not None
        assert stored.title == "CUSTOM TITLE"
    finally:
        db.close()


def test_dashboard_widget_instances_read_does_not_seed_from_legacy_profile_preferences(client, bridge_headers) -> None:
    response = client.put(
        "/api/profile",
        json={
            "dashboard_widgets_json": ["Connected Accounts", "Diagnostics Summary"],
        },
        headers=bridge_headers,
    )
    assert response.status_code == 200

    instances = client.get("/api/widgets/instances", params={"scope": "dashboard"}).json()
    assert instances == []


def test_profile_get_is_read_only(client, bridge_headers) -> None:
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AppProfile.id))) == 0
    finally:
        db.close()

    response = client.get("/api/profile", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["selected_provider"] == "codex"
    assert payload["dashboard_widgets_json"] == []

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AppProfile.id))) == 0
    finally:
        db.close()


def test_profile_summary_get_is_read_only(client, bridge_headers) -> None:
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AppProfile.id))) == 0
    finally:
        db.close()

    response = client.get("/api/profile/summary", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["exists"] is False
    assert payload["display_name"] == "Operator"
    assert payload["selected_provider"] == "codex"
    assert payload["dashboard_widget_count"] == 0

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AppProfile.id))) == 0
    finally:
        db.close()


def test_project_widget_instances_read_does_not_seed_from_legacy_workspace_preferences(client) -> None:
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
    assert instances == []


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
        profile = db.scalar(select(AppProfile).order_by(AppProfile.updated_at.desc(), AppProfile.id.desc()))
        assert profile is not None
        assert "Connected Accounts" not in (profile.dashboard_widgets_json or [])
    finally:
        db.close()


def test_profile_summary_prefers_latest_row_and_cleans_duplicates(client) -> None:
    db = SessionLocal()
    try:
        stale = AppProfile(
            id=1,
            display_name="Stale",
            selected_provider="codex",
            preferred_provider_choice="codex",
            notification_preferences_json={},
            dashboard_widgets_json=["Connected Accounts"],
        )
        fresh = AppProfile(
            id=2,
            display_name="Fresh",
            selected_provider="ollama",
            preferred_provider_choice="ollama",
            provider_endpoint="http://localhost:11434",
            adapter_command="python",
            notification_preferences_json={"desktop_toasts": True, "sound": False},
            dashboard_widgets_json=["Connected Accounts", "Diagnostics Summary"],
        )
        db.add_all([stale, fresh])
        db.commit()
        fresh.updated_at = fresh.updated_at.replace(year=fresh.updated_at.year + 1)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/profile/summary")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["exists"] is True
    assert payload["display_name"] == "Fresh"
    assert payload["selected_provider"] == "ollama"
    assert payload["dashboard_widget_count"] == 2
    assert payload["enabled_notification_count"] == 1
    assert payload["has_provider_endpoint"] is True
    assert payload["has_adapter"] is True

    db = SessionLocal()
    try:
        rows = list(db.scalars(select(AppProfile).order_by(AppProfile.id.asc())))
        assert len(rows) == 1
        assert rows[0].display_name == "Fresh"
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

    data = client.get(f"/api/projects/{project['id']}/widgets/instances/{instance['id']}/data").json()
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

    first_data = client.get(
        f"/api/projects/{project_one['id']}/widgets/instances/{first_instance['id']}/data",
    ).json()
    second_data = client.get(
        f"/api/projects/{project_two['id']}/widgets/instances/{second_instance['id']}/data",
    ).json()
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


def test_project_widget_instance_routes_require_matching_project_context(client) -> None:
    project_one = create_project(client, "Scoped Widgets One", "scoped-widgets-one")
    project_two = create_project(client, "Scoped Widgets Two", "scoped-widgets-two")

    instance = client.post(
        f"/api/projects/{project_one['id']}/widgets/add",
        json={"widget_type": "Decision Ledger"},
    ).json()

    missing_project = client.patch(
        f"/api/widgets/instances/{instance['id']}",
        json={"collapsed": True},
    )
    assert missing_project.status_code == 400
    assert "require project_id" in missing_project.json()["detail"].lower()

    wrong_project = client.get(
        f"/api/projects/{project_two['id']}/widgets/instances/{instance['id']}/data",
    )
    assert wrong_project.status_code == 404

    updated = client.patch(
        f"/api/projects/{project_one['id']}/widgets/instances/{instance['id']}",
        json={"collapsed": True},
    )
    assert updated.status_code == 200
    assert updated.json()["collapsed"] is True

    wrong_project_update = client.patch(
        f"/api/projects/{project_two['id']}/widgets/instances/{instance['id']}",
        json={"collapsed": False},
    )
    assert wrong_project_update.status_code == 404

    deleted = client.delete(
        f"/api/projects/{project_one['id']}/widgets/instances/{instance['id']}",
    )
    assert deleted.status_code == 204

    wrong_project_delete = client.delete(
        f"/api/projects/{project_two['id']}/widgets/instances/{instance['id']}",
    )
    assert wrong_project_delete.status_code == 404


def test_readding_disabled_widget_applies_new_layout_and_config(client) -> None:
    project = create_project(client, "Widget Reenable", "widget-reenable")
    created = client.post(
        f"/api/projects/{project['id']}/widgets/add",
        json={"widget_type": "Decision Ledger"},
    )
    assert created.status_code == 200, created.text
    instance = created.json()

    disabled = client.patch(
        f"/api/projects/{project['id']}/widgets/instances/{instance['id']}",
        json={"enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["enabled"] is False

    readded = client.post(
        "/api/widgets/instances",
        json={
            "scope": "project",
            "project_id": project["id"],
            "widget_type": "Decision Ledger",
            "area": "project_right_sidebar",
            "size": "large",
            "order_index": 5,
            "collapsed": True,
            "enabled": True,
            "config_json": {"b": 2},
        },
    )
    assert readded.status_code == 200, readded.text
    payload = readded.json()
    assert payload["id"] == instance["id"]
    assert payload["enabled"] is True
    assert payload["area"] == "project_right_sidebar"
    assert payload["size"] == "large"
    assert payload["order_index"] == 0
    assert payload["collapsed"] is True
    assert payload["config_json"] == {"b": 2}


def test_widget_update_rejects_scope_incompatible_area_assignment(client) -> None:
    created = client.post(
        "/api/widgets/instances",
        json={
            "scope": "dashboard",
            "widget_type": "Connected Accounts",
            "area": "dashboard_main",
            "size": "small",
        },
    )
    assert created.status_code == 200, created.text
    instance = created.json()

    moved = client.patch(
        f"/api/widgets/instances/{instance['id']}",
        json={"area": "project_right_sidebar"},
    )
    assert moved.status_code == 400
    assert "not valid for dashboard widgets" in moved.json()["detail"].lower()


def test_dashboard_widget_creation_rejects_project_id(client) -> None:
    project = create_project(client, "Dashboard Scope Guard", "dashboard-scope-guard")
    response = client.post(
        "/api/widgets/instances",
        json={
            "scope": "dashboard",
            "project_id": project["id"],
            "widget_type": "Connected Accounts",
            "area": "dashboard_bottom",
            "size": "small",
        },
    )
    assert response.status_code == 400
    assert "do not accept project_id" in response.json()["detail"].lower()


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


def test_partial_project_settings_update_preserves_omitted_fields(client, bridge_headers) -> None:
    project = create_project(client, "Partial Settings", "partial-settings")
    seeded = client.put(
        "/api/settings",
        params={"project_id": project["id"]},
        json={
            "provider": "ollama",
            "manager_model": "manager-x",
            "default_worker_model": "worker-y",
            "runner_mode": "dry_run",
            "sandbox_mode": "read-only",
            "approval_policy": "never",
            "workspace_widgets_json": ["Validation Recipe"],
            "approval_overrides_json": {"cmd:test": {"status": "approved_once"}},
        },
        headers=bridge_headers,
    )
    assert seeded.status_code == 200, seeded.text

    updated = client.put(
        "/api/settings",
        params={"project_id": project["id"]},
        json={"provider": "codex"},
        headers=bridge_headers,
    )
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["provider"] == "codex"
    assert payload["manager_model"] == "manager-x"
    assert payload["default_worker_model"] == "worker-y"
    assert payload["runner_mode"] == "dry_run"
    assert payload["sandbox_mode"] == "read-only"
    assert payload["approval_policy"] == "never"
    assert payload["workspace_widgets_json"] == ["Validation Recipe"]
    assert payload["approval_overrides_json"] == {"cmd:test": {"status": "approved_once"}}


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
