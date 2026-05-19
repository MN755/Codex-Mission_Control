from __future__ import annotations

import os
import shutil
from pathlib import Path

from conftest import sample_workspace, wait_for


def _bridge_headers() -> dict[str, str]:
    token_path = Path(os.environ["MISSION_CONTROL_RUNTIME_ROOT"]) / "daemon.token"
    wait_for(token_path.exists)
    return {"X-Mission-Control-Token": token_path.read_text(encoding="utf-8").strip()}


def _fresh_workspace(name: str) -> Path:
    workspace = Path(sample_workspace(name))
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _create_project(client, name: str, workspace_path: str, *, runner_mode: str = "auto") -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"Build {name}",
            "workspace_path": workspace_path,
            "provider": "codex",
            "runner_mode": runner_mode,
            "manager_mode": "auto",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_daemon_status_reports_runner_inventory(client) -> None:
    response = client.get("/api/daemon/status", headers=_bridge_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["token_configured"] is True
    assert any(item["runner_type"] == "dry_run" and item["availability"] for item in payload["runner_inventory"])


def test_attach_workspace_creates_new_project_for_empty_folder(client) -> None:
    workspace = _fresh_workspace("attach-empty")
    response = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Empty Attach",
            "mode": "auto",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["attach_outcome"] == "created_new_project"
    assert payload["project"]["workspace_path"] == workspace.as_posix()
    assert "## Mission Control Status" in payload["status_summary_markdown"]


def test_attach_missing_workspace_returns_clean_error(client) -> None:
    workspace = Path(sample_workspace("missing-workspace"))
    if workspace.exists():
        shutil.rmtree(workspace)
    response = client.post(
        "/api/headless/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Missing Attach",
            "mode": "auto",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"].lower()


def test_attach_workspace_imports_existing_codebase_folder(client) -> None:
    workspace = _fresh_workspace("attach-existing")
    (workspace / "README.md").write_text("# Existing codebase\n", encoding="utf-8")
    response = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Imported Attach",
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["attach_outcome"] == "imported_existing_codebase"
    project = client.get(f"/api/projects/{payload['project']['id']}").json()
    assert project["source_type"] == "existing_folder"
    assert project["scan_status"] == "completed"


def test_attach_workspace_rejects_non_local_path_inputs(client) -> None:
    response = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": "https://example.com/not-a-workspace",
            "project_name": "Bad Attach",
            "mode": "auto",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert response.status_code == 400
    assert "local filesystem" in response.json()["detail"].lower()


def test_attach_known_folder_reuses_existing_project(client) -> None:
    workspace = _fresh_workspace("attach-known")
    first = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={"workspace_path": workspace.as_posix(), "project_name": "Known Attach", "mode": "auto", "read_only_first": True, "attach_policy": "reuse_existing"},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={"workspace_path": workspace.as_posix(), "project_name": "Known Attach", "mode": "auto", "read_only_first": True, "attach_policy": "reuse_existing"},
    )
    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["attach_outcome"] == "reused_existing_project"
    assert payload["reused_existing_project"] is True


def test_one_active_orchestration_per_workspace_is_enforced(client) -> None:
    workspace = _fresh_workspace("attach-active")
    attach = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={"workspace_path": workspace.as_posix(), "project_name": "Active Attach", "mode": "auto", "read_only_first": True, "attach_policy": "reuse_existing"},
    )
    project_id = attach.json()["project"]["id"]
    start = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={"project_id": project_id, "user_request": "Use Mission Control to manage this repo.", "source": "codex_plugin"},
    )
    assert start.status_code == 200, start.text
    session_id = start.json()["id"]
    second_attach = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={"workspace_path": workspace.as_posix(), "project_name": "Active Attach", "mode": "auto", "read_only_first": True, "attach_policy": "reuse_existing"},
    )
    assert second_attach.status_code == 200, second_attach.text
    payload = second_attach.json()
    assert payload["reused_existing_orchestration"] is True
    assert payload["orchestration"]["id"] == session_id


def test_pending_decisions_can_be_listed_and_answered(client) -> None:
    workspace = _fresh_workspace("pending-decisions")
    project = _create_project(client, "Pending Decisions", workspace.as_posix(), runner_mode="dry_run")
    open_response = client.post(f"/api/projects/{project['id']}/open")
    assert open_response.status_code == 200, open_response.text
    orchestration = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={"project_id": project["id"], "user_request": "Run this through Mission Control.", "source": "codex_plugin"},
    )
    assert orchestration.status_code == 200, orchestration.text
    session_id = orchestration.json()["id"]
    decisions_response = client.get(f"/api/orchestrations/{session_id}/pending-decisions", headers=_bridge_headers())
    assert decisions_response.status_code == 200, decisions_response.text
    decisions = decisions_response.json()
    assert decisions
    decision = decisions[0]
    option = decision["options"][0]
    answer = client.post(
        f"/api/decisions/{decision['id']}/answer",
        headers=_bridge_headers(),
        json={"option_id": option["id"], "selected_text": option["label"]},
    )
    assert answer.status_code == 200, answer.text
    answered = answer.json()
    assert answered["decision"]["status"] == "answered"
    assert "next_status_summary" in answered


def test_invalid_pending_decision_answer_is_rejected(client) -> None:
    workspace = _fresh_workspace("invalid-decision-answer")
    project = _create_project(client, "Invalid Decision Answer", workspace.as_posix(), runner_mode="dry_run")
    client.post(f"/api/projects/{project['id']}/open")
    orchestration = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={"project_id": project["id"], "user_request": "Run this through Mission Control.", "source": "codex_plugin"},
    )
    session_id = orchestration.json()["id"]
    decisions = client.get(f"/api/orchestrations/{session_id}/pending-decisions", headers=_bridge_headers()).json()
    assert decisions
    response = client.post(
        f"/api/decisions/{decisions[0]['id']}/answer",
        headers=_bridge_headers(),
        json={"option_id": "definitely_not_allowed", "selected_text": "Nope"},
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


def test_headless_start_task_creates_waiting_dry_run_flow(client) -> None:
    workspace = _fresh_workspace("headless-start-task")
    (workspace / "README.md").write_text("# Existing codebase\n", encoding="utf-8")
    response = client.post(
        "/api/headless/start-task",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "user_request": "Use Mission Control for this repo and fix the failing tests.",
            "strategy": "balanced",
            "mode": "dry_run",
            "interview_mode": "skip",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode_used"] == "dry_run"
    assert payload["orchestration"]["status"] == "waiting_for_user"
    assert payload["status_summary"]["user_action_required"] is True
    assert any(item["decision_type"] == "command_approval" for item in payload["pending_decisions"])


def test_orchestration_status_reports_pending_decision_count(client) -> None:
    workspace = _fresh_workspace("status-pending")
    project = _create_project(client, "Status Pending", workspace.as_posix(), runner_mode="dry_run")
    client.post(f"/api/projects/{project['id']}/open")
    orchestration = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={"project_id": project["id"], "user_request": "Manage this project in the background.", "source": "codex_plugin"},
    )
    session_id = orchestration.json()["id"]
    status = client.get(f"/api/orchestrations/{session_id}/status", headers=_bridge_headers())
    assert status.status_code == 200, status.text
    payload = status.json()
    assert payload["project_id"] == project["id"]
    assert payload["pending_decisions_count"] >= 1
    assert payload["user_action_required"] is True


def test_orchestration_handoff_returns_not_ready_state(client) -> None:
    workspace = _fresh_workspace("handoff-not-ready")
    project = _create_project(client, "No Handoff Yet", workspace.as_posix())
    orchestration = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={"project_id": project["id"], "user_request": "Start background orchestration.", "source": "codex_plugin"},
    )
    session_id = orchestration.json()["id"]
    handoff = client.get(f"/api/orchestrations/{session_id}/handoff", headers=_bridge_headers())
    assert handoff.status_code == 200, handoff.text
    payload = handoff.json()
    assert payload["ready"] is False
    assert payload["status"] == "not_ready"


def test_bridge_routes_require_token(client) -> None:
    workspace = _fresh_workspace("token-guard")
    response = client.post(
        "/api/orchestrations/attach-workspace",
        json={"workspace_path": workspace.as_posix(), "project_name": "Token Guard", "mode": "auto", "read_only_first": True, "attach_policy": "reuse_existing"},
    )
    assert response.status_code == 401
    status = client.get("/api/daemon/status")
    assert status.status_code == 401


def test_targeted_scan_ignores_parent_escape_targets(client) -> None:
    workspace = _fresh_workspace("targeted-scan")
    (workspace / "README.md").write_text("# Existing codebase\n", encoding="utf-8")
    (workspace / "src").mkdir(exist_ok=True)
    (workspace / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    attach = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Targeted Scan",
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert attach.status_code == 200, attach.text
    project_id = attach.json()["project"]["id"]

    scan = client.post(
        f"/api/projects/{project_id}/scan-codebase/targeted",
        json={"target_paths": ["src", "../escape", "C:/outside"]},
    )
    assert scan.status_code == 200, scan.text
    payload = scan.json()
    assert payload["indexed_areas_json"] == ["src"]
