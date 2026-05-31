from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from conftest import sample_workspace
from main import app


def _create_project(client) -> int:
    workspace = sample_workspace("tensorflow-api")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    project = client.post(
        "/api/projects",
        json={
            "name": "TensorFlow API Demo",
            "idea": "Expose TensorFlow starter bundles through project routes",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    return project["id"]


def test_tensorflow_feature_catalog_route_returns_all_supported_features(client, bridge_headers) -> None:
    project_id = _create_project(client)

    response = client.get(f"/api/projects/{project_id}/tensorflow/features", headers=bridge_headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 15
    feature_ids = {item["feature_id"] for item in payload}
    assert "keras_scaffold" in feature_ids
    assert "optimization_advisor" in feature_ids
    keras_entry = next(item for item in payload if item["feature_id"] == "keras_scaffold")
    assert "classification" in keras_entry["variants"]
    assert "time_series" in keras_entry["variants"]


def test_tensorflow_feature_bundle_route_returns_default_bundle(client, bridge_headers) -> None:
    project_id = _create_project(client)

    response = client.get(
        f"/api/projects/{project_id}/tensorflow/features/keras_scaffold",
        headers=bridge_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["feature_id"] == "keras_scaffold"
    assert payload["variant"] == "classification"
    assert "tensorflow_starters/model.py" in payload["files"]
    assert "artifacts/final.keras" in payload["files"]["tensorflow_starters/train.py"]


def test_tensorflow_feature_bundle_route_supports_explicit_variant(client, bridge_headers) -> None:
    project_id = _create_project(client)

    response = client.get(
        f"/api/projects/{project_id}/tensorflow/features/serving_api",
        params={"variant": "tensorflow_serving_fastapi"},
        headers=bridge_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["variant"] == "tensorflow_serving_fastapi"
    assert "tensorflow_starters/serving/models.config" in payload["files"]
    assert "FastAPI" in payload["files"]["tensorflow_starters/serving/api.py"]


def test_tensorflow_feature_bundle_route_rejects_bad_feature_and_variant(client, bridge_headers) -> None:
    project_id = _create_project(client)

    missing_feature = client.get(
        f"/api/projects/{project_id}/tensorflow/features/not_real",
        headers=bridge_headers,
    )
    assert missing_feature.status_code == 404
    assert "Unknown TensorFlow feature bundle" in missing_feature.json()["detail"]

    bad_variant = client.get(
        f"/api/projects/{project_id}/tensorflow/features/tf_data_pipeline",
        params={"variant": "bad_variant"},
        headers=bridge_headers,
    )
    assert bad_variant.status_code == 400
    assert "Unsupported tf.data variant" in bad_variant.json()["detail"]


def test_tensorflow_feature_routes_require_bridge_token(client) -> None:
    project_id = _create_project(client)

    with TestClient(app) as raw_client:
        assert raw_client.get(f"/api/projects/{project_id}/tensorflow/features").status_code == 401
        assert raw_client.get(f"/api/projects/{project_id}/tensorflow/features/keras_scaffold").status_code == 401
