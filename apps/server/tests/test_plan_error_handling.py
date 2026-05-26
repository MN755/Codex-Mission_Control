from __future__ import annotations

from conftest import sample_workspace


def create_project(client, name: str, workspace_name: str) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"Build {name}",
            "workspace_path": sample_workspace(workspace_name),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_generate_plan_returns_client_error_when_interview_is_missing(client) -> None:
    project = create_project(client, "Missing Interview", "missing-interview")

    response = client.post(
        f"/api/projects/{project['id']}/plan/generate",
        json={"force_rebuild": False},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Interview session required before plan generation"


def test_approve_plan_returns_not_found_when_plan_is_missing(client) -> None:
    project = create_project(client, "Missing Plan", "missing-plan")

    response = client.post(
        f"/api/projects/{project['id']}/plan/approve",
        json={"action": "approve_build"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Plan not found"
