from __future__ import annotations

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
