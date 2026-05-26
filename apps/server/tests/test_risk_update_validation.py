from __future__ import annotations

from conftest import sample_workspace


def _create_project(client, name: str, workspace_name: str) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"{name} idea",
            "workspace_path": sample_workspace(workspace_name),
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_patch_risk_rejects_nonexistent_related_refs(client) -> None:
    project = _create_project(client, "Risk Target", "risk-target")
    create_risk = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "Missing refs",
            "description": "Track missing refs.",
            "severity": "low",
            "likelihood": "low",
            "mitigation": "Validate them.",
        },
    )
    assert create_risk.status_code == 200, create_risk.text
    risk_id = create_risk.json()["id"]

    missing_agent = client.patch(f"/api/risks/{risk_id}", json={"owner_agent_id": 999})
    assert missing_agent.status_code == 404
    assert "not found" in missing_agent.json()["detail"].lower()

    missing_task = client.patch(f"/api/risks/{risk_id}", json={"related_task_id": 999})
    assert missing_task.status_code == 404
    assert "not found" in missing_task.json()["detail"].lower()
