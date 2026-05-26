from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import sample_workspace
from main import app


def test_validation_coverage_routes_require_bridge_token() -> None:
    with TestClient(app) as raw_client:
        project = raw_client.post(
            "/api/projects",
            json={
                "name": "Validation Coverage Auth",
                "idea": "Protect validation coverage routes",
                "workspace_path": sample_workspace("validation-coverage-auth"),
                "provider": "codex",
                "runner_mode": "dry_run",
                "manager_mode": "auto",
            },
        ).json()

        listed = raw_client.get(f"/api/projects/{project['id']}/validation-coverage")
        assert listed.status_code == 401

        recomputed = raw_client.post(f"/api/projects/{project['id']}/validation-coverage/recompute")
        assert recomputed.status_code == 401
