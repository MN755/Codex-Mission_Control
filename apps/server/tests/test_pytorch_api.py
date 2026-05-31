from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from conftest import sample_workspace
from main import app


def _create_project(client) -> int:
    workspace = sample_workspace("pytorch-api")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    project = client.post(
        "/api/projects",
        json={
            "name": "PyTorch API Demo",
            "idea": "Expose PyTorch starter bundles through project routes",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    return project["id"]


def test_pytorch_feature_catalog_route_returns_all_supported_features(client, bridge_headers) -> None:
    project_id = _create_project(client)

    response = client.get(f"/api/projects/{project_id}/pytorch/features", headers=bridge_headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 8
    feature_ids = {item["feature_id"] for item in payload}
    assert "project_scaffold" in feature_ids
    assert "peft_finetuning" in feature_ids
    scaffold_entry = next(item for item in payload if item["feature_id"] == "project_scaffold")
    assert "classification" in scaffold_entry["variants"]
    assert "nlp" in scaffold_entry["variants"]


def test_pytorch_feature_bundle_route_returns_default_bundle(client, bridge_headers) -> None:
    project_id = _create_project(client)

    response = client.get(
        f"/api/projects/{project_id}/pytorch/features/project_scaffold",
        headers=bridge_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["feature_id"] == "project_scaffold"
    assert payload["variant"] == "classification"
    assert "pytorch_starters/model.py" in payload["files"]
    assert "artifacts/checkpoint.pt" in payload["files"]["pytorch_starters/train.py"]


def test_pytorch_feature_bundle_route_supports_explicit_variant(client, bridge_headers) -> None:
    project_id = _create_project(client)

    response = client.get(
        f"/api/projects/{project_id}/pytorch/features/distributed_training",
        params={"variant": "accelerate"},
        headers=bridge_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["variant"] == "accelerate"
    assert "Accelerator" in payload["files"]["pytorch_starters/distributed.py"]


def test_pytorch_feature_bundle_route_rejects_bad_feature_and_variant(client, bridge_headers) -> None:
    project_id = _create_project(client)

    missing_feature = client.get(
        f"/api/projects/{project_id}/pytorch/features/not_real",
        headers=bridge_headers,
    )
    assert missing_feature.status_code == 404
    assert "Unknown PyTorch feature bundle" in missing_feature.json()["detail"]

    bad_variant = client.get(
        f"/api/projects/{project_id}/pytorch/features/training_loop",
        params={"variant": "bad_variant"},
        headers=bridge_headers,
    )
    assert bad_variant.status_code == 400
    assert "Unsupported training loop variant" in bad_variant.json()["detail"]


def test_pytorch_feature_routes_require_bridge_token(client) -> None:
    project_id = _create_project(client)

    with TestClient(app) as raw_client:
        assert raw_client.get(f"/api/projects/{project_id}/pytorch/features").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/pytorch/features/project_scaffold").status_code == 401
