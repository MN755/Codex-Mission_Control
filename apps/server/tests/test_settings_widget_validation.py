from __future__ import annotations


def test_settings_reject_invalid_project_widget_names(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Settings Widget Validation",
            "idea": "Reject invalid workspace widgets.",
            "workspace_path": ".",
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()

    payload = {
        "provider": "codex",
        "runner_mode": "auto",
        "sandbox_mode": "workspace-write",
        "approval_policy": "on-request",
    }

    nonexistent = client.put(
        f"/api/settings?project_id={project['id']}",
        json={**payload, "workspace_widgets_json": ["Not A Widget"]},
    )
    assert nonexistent.status_code == 400
    assert "Unknown project widget" in nonexistent.json()["detail"]

    wrong_scope = client.put(
        f"/api/settings?project_id={project['id']}",
        json={**payload, "workspace_widgets_json": ["Connected Accounts"]},
    )
    assert wrong_scope.status_code == 400
    assert "Connected Accounts" in wrong_scope.json()["detail"]
