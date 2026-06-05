from __future__ import annotations

from datetime import datetime, timezone

import pytest

from db import SessionLocal, init_db
from models import Project
from conftest import sample_workspace


def test_dashboard_summary_prefers_pinned_and_limits_sidebar(client) -> None:
    project_ids: list[int] = []
    for index in range(4):
      response = client.post(
          "/api/projects",
          json={
              "name": f"Project {index}",
              "idea": f"Idea {index}",
              "workspace_path": sample_workspace(f"dashboard-{index}"),
              "provider": "codex",
              "runner_mode": "dry_run",
              "manager_mode": "auto",
          },
      )
      project_ids.append(response.json()["id"])

    client.post(f"/api/projects/{project_ids[2]}/pin")
    client.post(f"/api/projects/{project_ids[3]}/archive")
    summary = client.get("/api/dashboard/summary").json()

    assert len(summary["sidebar_projects"]) == 3
    assert summary["sidebar_projects"][0]["id"] == project_ids[2]
    assert summary["archive_count"] >= 1


@pytest.fixture(autouse=True)
def _fast_command_center_dependencies(monkeypatch, tmp_path) -> None:
    async def fake_system_status(db, project=None, **kwargs):
        return {
            "selected_provider": "codex",
            "selected_provider_label": "Codex",
            "effective_runner_mode": "dry_run",
            "cli_detected": True,
            "authenticated": True,
            "app_server_handshake_status": "unsupported",
        }

    async def fake_widget_summary(db):
        return {"instances": [], "catalog": [], "data": []}

    diagnostic_root = tmp_path / "diagnostics"
    diagnostic_root.mkdir(parents=True, exist_ok=True)
    report_index: list[dict] = []

    def fake_run_diagnostics(db):
        markdown_path = diagnostic_root / "diagnostic-test.md"
        json_path = diagnostic_root / "diagnostic-test.json"
        bundle_path = diagnostic_root / "diagnostic-test-bundle.zip"
        markdown_path.write_text("# Diagnostic\n", encoding="utf-8")
        json_path.write_text('{"ok": true}\n', encoding="utf-8")
        bundle_path.write_text("bundle\n", encoding="utf-8")
        created_at = datetime.now(timezone.utc)
        payload = {
            "path": str(markdown_path),
            "json_path": str(json_path),
            "bundle_path": str(bundle_path),
            "summary": "Fast test diagnostic report.",
            "error_code": None,
            "recommended_fixes": [],
            "project_id": None,
            "project_name": None,
            "workspace_path": None,
            "platform_profile": {"platform_label": "Windows Test Rig"},
            "performance_profile": {"recommended_swarm_max_agents": 4},
            "safe_debug_commands": ["python -m pytest apps/server/tests/test_command_center.py -q"],
            "problem": None,
        }
        report_index[:] = [{**payload, "created_at": created_at}]
        return payload

    monkeypatch.setattr("manager.service.get_tool_catalog", lambda db: [
        {
            "id": "file-search",
            "name": "File Search",
            "category": "Core tools",
            "summary": "Search the local workspace quickly.",
            "availability": "available",
            "permission_policy": "ask_once_per_project",
            "risk_level": "low",
            "notes": [],
        }
    ])
    monkeypatch.setattr("manager.service.get_system_status", fake_system_status)
    monkeypatch.setattr("manager.service.get_dashboard_widget_summary", fake_widget_summary)
    monkeypatch.setattr("main.startup_service.run_diagnostics", fake_run_diagnostics)
    monkeypatch.setattr("manager.service.recent_diagnostic_reports", lambda project=None: list(report_index) if project is None else [])


def test_archive_and_pin_flows_mutate_the_correct_project(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Archive Flow",
            "idea": "Archive and pin flow",
            "workspace_path": sample_workspace("archive-flow"),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()

    pinned = client.post(f"/api/projects/{project['id']}/pin").json()
    assert pinned["pinned"] is True

    archived = client.post(f"/api/projects/{project['id']}/archive").json()
    assert archived["archived_at"] is not None
    assert archived["display_status"] == "archived"

    unarchived = client.post(f"/api/projects/{project['id']}/unarchive").json()
    assert unarchived["archived_at"] is None

    unpinned = client.post(f"/api/projects/{project['id']}/unpin").json()
    assert unpinned["pinned"] is False


def test_handoffs_and_tools_and_diagnostics_endpoints(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Handoff Demo",
            "idea": "Collect handoff summaries",
            "workspace_path": sample_workspace("handoff-demo"),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()

    init_db()
    db = SessionLocal()
    try:
        stored = db.get(Project, project["id"])
        assert stored is not None
        stored.status = "handoff_ready"
        stored.handoff_status = "ready"
        stored.final_report_json = {
            "summary_markdown": "Shipped the first handoff slice.",
            "how_to_run": ["npm run dev"],
            "known_limitations": ["Local only."],
            "tests_builds_run": ["pytest"],
        }
        db.commit()
    finally:
        db.close()

    handoffs = client.get("/api/handoffs").json()
    assert any(item["project_id"] == project["id"] for item in handoffs)

    tools = client.get("/api/tools").json()
    assert any(item["name"] == "File Search" for item in tools)
    updated_permission = client.put("/api/tools/file-search/permission", json={"permission_policy": "allow_for_project"}).json()
    assert updated_permission["permission_policy"] == "allow_for_project"

    client.post("/api/startup/diagnostics")
    reports = client.get("/api/diagnostics/reports").json()
    assert reports
    assert reports[0]["path"].endswith(".md")
    scoped_reports = client.get(f"/api/diagnostics/reports?project_id={project['id']}").json()
    assert scoped_reports == []
