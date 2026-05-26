from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import sample_workspace
from main import app


def test_change_request_creation_requires_bridge_token() -> None:
    with TestClient(app) as raw_client:
        project = raw_client.post(
            "/api/projects",
            json={
                "name": "Change Request Auth",
                "idea": "Lock down change request creation",
                "workspace_path": sample_workspace("change-request-auth"),
                "provider": "codex",
                "runner_mode": "dry_run",
                "manager_mode": "auto",
            },
        ).json()

        response = raw_client.post(
            f"/api/projects/{project['id']}/change-requests",
            json={"request_text": "Need a stealth roadmap too."},
        )

        assert response.status_code == 401
