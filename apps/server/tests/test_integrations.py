from __future__ import annotations

from pathlib import Path

from integration_registry import normalize_integration_registry
from tool_catalog import catalog_with_permissions


def test_tool_catalog_uses_integration_registry_for_github_and_vercel() -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "source_control": {
                    "family": "source_control",
                    "status": "connected",
                    "providers": ["github"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                },
                "hosting_deploy": {
                    "family": "hosting_deploy",
                    "status": "connected",
                    "providers": ["vercel"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                },
            }
        },
        {},
    )

    payload = catalog_with_permissions(
        provider="codex",
        connected_accounts={},
        integration_registry=registry,
        permission_overrides={},
    )
    tools = {item["id"]: item for item in payload}

    assert tools["github-wiki-creator"]["availability"] == "available"
    assert tools["github-deployment-creator"]["availability"] == "available"
    assert tools["deploy-with-vercel"]["availability"] == "available"


def test_project_integrations_and_action_preview_flow(client, bridge_headers, monkeypatch, tmp_path) -> None:
    workspace = str(tmp_path / "integrations-spine")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    Path(workspace, "vercel.json").write_text('{"framework":"nextjs"}\n', encoding="utf-8")
    Path(workspace, "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    Path(workspace, ".github").mkdir(exist_ok=True)
    Path(workspace, ".github", "workflows").mkdir(exist_ok=True)
    Path(workspace, ".github", "workflows", "ci.yml").write_text("name: ci\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"docker", "gh", "vercel", "playwright"} else None,
    )

    project = client.post(
        "/api/projects",
        json={
            "name": "Integration Spine Demo",
            "idea": "Validate cross-host integrations",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    catalog = client.get("/api/integrations/catalog", headers=bridge_headers)
    assert catalog.status_code == 200
    catalog_payload = {item["family"]: item for item in catalog.json()}
    assert "source_control" in catalog_payload
    assert "release_management" in catalog_payload

    project_integrations = client.get(f"/api/projects/{project_id}/integrations", headers=bridge_headers)
    assert project_integrations.status_code == 200
    families = {item["family"]: item for item in project_integrations.json()["families"]}
    assert families["source_control"]["status"] == "ready"
    assert families["containers"]["status"] == "ready"
    assert families["hosting_deploy"]["status"] == "ready"
    assert families["browser_testing"]["status"] == "ready"

    preview = client.post(
        f"/api/projects/{project_id}/integrations/source_control/actions/create/preview",
        json={"params": {"title": "Bridge it", "body": "Stop lying about status."}},
        headers=bridge_headers,
    )
    assert preview.status_code == 200
    assert "gh issue create" in preview.json()["command"]
    assert preview.json()["requires_confirmation"] is True

    execute = client.post(
        f"/api/projects/{project_id}/integrations/source_control/actions/create/execute",
        json={"params": {"title": "Bridge it", "body": "Stop lying about status."}, "confirmed": False},
        headers=bridge_headers,
    )
    assert execute.status_code == 200
    assert execute.json()["status"] == "approval_required"


def test_import_host_state_endpoint_persists_registry(client, bridge_headers, monkeypatch) -> None:
    monkeypatch.setattr(
        "manager.import_host_state",
        lambda _registry: normalize_integration_registry(
            {
                "connections": {
                    "source_control": {
                        "family": "source_control",
                        "status": "connected",
                        "providers": ["github"],
                        "connection_source": "codex_host",
                        "host_imported": True,
                    }
                },
                "host_imports": {"codex": {"source_control": {"detected": True, "paths": ["C:/Users/mike/.codex/plugins/github"]}}, "claude_code": {}},
            },
            {},
        ),
    )

    imported = client.post("/api/integrations/import-host-state", headers=bridge_headers)
    assert imported.status_code == 200
    payload = imported.json()
    assert payload["status"] == "completed"
    assert payload["connections"][0]["family"] == "source_control"
    assert payload["connections"][0]["host_imported"] is True
