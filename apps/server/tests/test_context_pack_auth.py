from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from conftest import sample_workspace
from daemon_state import ensure_daemon_token
from main import app


def test_context_pack_reads_require_bridge_token() -> None:
    with TestClient(app) as raw_client:
        bridge_headers = {"X-Mission-Control-Token": ensure_daemon_token()}
        project = raw_client.post(
            "/api/projects",
            json={
                "name": "Context Pack Auth",
                "idea": "Lock down context pack reads",
                "workspace_path": sample_workspace("context-pack-auth"),
                "provider": "codex",
                "runner_mode": "dry_run",
                "manager_mode": "auto",
            },
        ).json()

        workspace = Path(project["workspace_path"])
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "README.md").write_text("# Context pack auth\n", encoding="utf-8")

        pack = raw_client.post(
            f"/api/projects/{project['id']}/context-packs/build",
            headers=bridge_headers,
            json={"title": "Scoped Pack", "goal": "Summarize the repo."},
        ).json()

        listed = raw_client.get(f"/api/projects/{project['id']}/context-packs")
        assert listed.status_code == 401

        fetched = raw_client.get(
            f"/api/context-packs/{pack['id']}",
            params={"project_id": project["id"]},
        )
        assert fetched.status_code == 401
