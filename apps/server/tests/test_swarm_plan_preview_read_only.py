from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, func, select

from conftest import sample_workspace
from db import SessionLocal
from models import SwarmLaunchSimulation


def _create_project(client, name: str, workspace_name: str) -> dict:
    workspace_root = Path(sample_workspace(workspace_name))
    (workspace_root / "src").mkdir(parents=True, exist_ok=True)
    (workspace_root / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"Exercise {name}",
            "workspace_path": workspace_root.as_posix(),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _seed_swarm_plan(client, project_id: int) -> None:
    response = client.post(
        f"/api/projects/{project_id}/swarm/plan",
        json={"goal": "Keep the swarm read surfaces honest."},
    )
    assert response.status_code == 200, response.text


def _simulation_count(project_id: int) -> int:
    db = SessionLocal()
    try:
        return db.scalar(select(func.count(SwarmLaunchSimulation.id)).where(SwarmLaunchSimulation.project_id == project_id)) or 0
    finally:
        db.close()


def _clear_simulations(project_id: int) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(SwarmLaunchSimulation).where(SwarmLaunchSimulation.project_id == project_id))
        db.commit()
    finally:
        db.close()


def test_get_swarm_plan_stays_read_only(client) -> None:
    project = _create_project(client, "Swarm Plan Read Safety", "swarm-plan-read-safety")
    _seed_swarm_plan(client, project["id"])
    _clear_simulations(project["id"])

    response = client.get(f"/api/projects/{project['id']}/swarm/plan")

    assert response.status_code == 200, response.text
    assert _simulation_count(project["id"]) == 0


def test_workspace_payload_stays_read_only(client, bridge_headers) -> None:
    project = _create_project(client, "Workspace Read Safety", "workspace-read-safety")
    _seed_swarm_plan(client, project["id"])
    _clear_simulations(project["id"])

    response = client.get(f"/api/projects/{project['id']}/workspace", headers=bridge_headers)

    assert response.status_code == 200, response.text
    assert _simulation_count(project["id"]) == 0


def test_operator_snapshot_stays_read_only(client, bridge_headers) -> None:
    project = _create_project(client, "Operator Snapshot Read Safety", "operator-snapshot-read-safety")
    _seed_swarm_plan(client, project["id"])
    _clear_simulations(project["id"])

    response = client.get(f"/api/projects/{project['id']}/operator-snapshot", headers=bridge_headers)

    assert response.status_code == 200, response.text
    assert _simulation_count(project["id"]) == 0


def test_instincts_preview_stays_read_only(client, bridge_headers) -> None:
    project = _create_project(client, "Instinct Preview Read Safety", "instinct-preview-read-safety")
    _seed_swarm_plan(client, project["id"])
    _clear_simulations(project["id"])

    response = client.get(f"/api/projects/{project['id']}/instincts/preview", headers=bridge_headers)

    assert response.status_code == 200, response.text
    assert _simulation_count(project["id"]) == 0
