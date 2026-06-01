from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from conftest import sample_workspace
from main import app


def _create_project(client) -> int:
    workspace = sample_workspace("spatial3d-api")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    project = client.post(
        "/api/projects",
        json={
            "name": "Spatial API Demo",
            "idea": "Expose spatial 3D starter bundles through project routes",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    return project["id"]


def test_spatial3d_feature_catalog_route_returns_all_supported_features(client, bridge_headers) -> None:
    project_id = _create_project(client)

    response = client.get(f"/api/projects/{project_id}/spatial/features", headers=bridge_headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 20
    feature_ids = {item["feature_id"] for item in payload}
    assert "asset_pipeline" in feature_ids
    assert "research_to_code" in feature_ids


def test_spatial3d_feature_bundle_route_returns_default_bundle(client, bridge_headers) -> None:
    project_id = _create_project(client)

    response = client.get(
        f"/api/projects/{project_id}/spatial/features/blender_integration",
        headers=bridge_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["feature_id"] == "blender_integration"
    assert payload["variant"] == "default"
    assert "spatial3d_starters/blender_scene_check.py" in payload["files"]
    assert "bpy" in payload["files"]["spatial3d_starters/blender_scene_check.py"]


def test_spatial3d_feature_bundle_route_rejects_bad_feature_and_variant(client, bridge_headers) -> None:
    project_id = _create_project(client)

    missing_feature = client.get(
        f"/api/projects/{project_id}/spatial/features/not_real",
        headers=bridge_headers,
    )
    assert missing_feature.status_code == 404
    assert "Unknown spatial 3D feature bundle" in missing_feature.json()["detail"]

    bad_variant = client.get(
        f"/api/projects/{project_id}/spatial/features/asset_pipeline",
        params={"variant": "bad"},
        headers=bridge_headers,
    )
    assert bad_variant.status_code == 400
    assert "Unsupported spatial 3D feature variant" in bad_variant.json()["detail"]


def test_spatial3d_feature_routes_require_bridge_token(client) -> None:
    project_id = _create_project(client)

    with TestClient(app) as raw_client:
        assert raw_client.get(f"/api/projects/{project_id}/spatial/features").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/spatial/features/asset_pipeline").status_code == 401
