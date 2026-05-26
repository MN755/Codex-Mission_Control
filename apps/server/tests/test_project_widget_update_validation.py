from __future__ import annotations


def test_project_widget_updates_reject_invalid_widget_names(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Project Widget Update Validation",
            "idea": "Reject invalid widget updates.",
            "workspace_path": ".",
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    seed = client.post(
        f"/api/projects/{project_id}/widgets",
        json={"widgets": ["Repo Intelligence"]},
    )
    assert seed.status_code == 200

    nonexistent = client.post(
        f"/api/projects/{project_id}/widgets",
        json={"widgets": ["Not A Widget"]},
    )
    assert nonexistent.status_code == 400
    assert "Unknown project widget" in nonexistent.json()["detail"]

    wrong_scope = client.post(
        f"/api/projects/{project_id}/widgets",
        json={"widgets": ["Connected Accounts"]},
    )
    assert wrong_scope.status_code == 400
    assert "Connected Accounts" in wrong_scope.json()["detail"]

    instances = client.get(f"/api/projects/{project_id}/widgets/instances").json()
    enabled = [item["widget_type"] for item in instances if item["enabled"]]
    assert enabled == ["Repo Intelligence"]
