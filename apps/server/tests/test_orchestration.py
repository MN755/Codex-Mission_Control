from __future__ import annotations

import os
import shutil
import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import sample_workspace, wait_for
from main import app


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
    assert "background_runtime" in payload
    assert "active_background_turns" in payload
    assert "retrying_orchestrations" in payload


def test_background_retries_are_tracked_and_shutdown_cancels() -> None:
    from orchestration import coordinator

    async def run_test() -> None:
        coordinator._schedule_background_retry(999999, "retry_after_error", 30.0)
        snapshot = coordinator._background_runtime_snapshot(999999)
        assert snapshot["retry_scheduled"] is True
        assert snapshot["delay_seconds"] == 30.0
        await coordinator.on_shutdown()
        assert coordinator._background_runtime_snapshot(999999)["retry_scheduled"] is False

    asyncio.run(run_test())


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


def test_manager_ask_next_bootstraps_greenfield_intake(client) -> None:
    workspace = _fresh_workspace("greenfield-intake")
    project = _create_project(client, "Greenfield Intake", workspace.as_posix(), runner_mode="dry_run")

    response = client.post(f"/api/projects/{project['id']}/manager/ask-next")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "Mission Control started intake" in payload["content_markdown"]
    assert "First question:" in payload["content_markdown"]

    pending = client.get(f"/api/projects/{project['id']}/questions/pending")
    assert pending.status_code == 200, pending.text
    pending_payload = pending.json()
    assert len(pending_payload) == 1
    assert pending_payload[0]["question"]
    assert pending_payload[0]["question_markdown"]
    assert pending_payload[0]["question"] in payload["content_markdown"]

    refreshed = client.get(f"/api/projects/{project['id']}").json()
    assert refreshed["status"] == "interview_in_progress"


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


def test_create_project_marks_non_empty_workspace_as_existing_codebase(client) -> None:
    workspace = _fresh_workspace("project-existing")
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    response = client.post(
        "/api/projects",
        json={
            "name": "Existing Project",
            "idea": "Fix the failing tests in this repo.",
            "workspace_path": workspace.as_posix(),
            "provider": "ollama",
            "runner_mode": "auto",
            "manager_mode": "auto",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source_type"] == "existing_folder"
    assert payload["scan_status"] == "completed"


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


def test_attach_workspace_uses_project_name_hint_when_workspace_has_duplicates(client) -> None:
    workspace = _fresh_workspace("attach-duplicate-hint")
    alpha = _create_project(client, "Alpha", workspace.as_posix(), runner_mode="dry_run")
    _create_project(client, "Beta", workspace.as_posix(), runner_mode="dry_run")

    response = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Alpha",
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["attach_outcome"] == "reused_existing_project"
    assert payload["project_id"] == alpha["id"]
    assert payload["project_name"] == "Alpha"


def test_attach_workspace_rejects_unknown_project_name_hint_for_duplicate_workspace(client) -> None:
    workspace = _fresh_workspace("attach-duplicate-miss")
    _create_project(client, "Alpha", workspace.as_posix(), runner_mode="dry_run")
    _create_project(client, "Beta", workspace.as_posix(), runner_mode="dry_run")

    response = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Gamma",
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert response.status_code == 400
    assert "did not match exactly one existing project" in response.json()["detail"].lower()


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
    decisions_response = client.get(f"/api/orchestrations/{session_id}/pending-decisions", headers=_bridge_headers(), params={"project_id": project["id"]})
    assert decisions_response.status_code == 200, decisions_response.text
    decisions = decisions_response.json()
    assert decisions
    decision = decisions[0]
    option = decision["options"][0]
    answer = client.post(
        f"/api/decisions/{decision['id']}/answer",
        headers=_bridge_headers(),
        params={"project_id": project["id"]},
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
    decisions = client.get(f"/api/orchestrations/{session_id}/pending-decisions", headers=_bridge_headers(), params={"project_id": project["id"]}).json()
    assert decisions
    response = client.post(
        f"/api/decisions/{decisions[0]['id']}/answer",
        headers=_bridge_headers(),
        params={"project_id": project["id"]},
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


def test_task_generation_for_existing_codebase_is_codebase_aware(client) -> None:
    workspace = _fresh_workspace("existing-codebase-tasks")
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "tests").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (workspace / "tests" / "test_math_utils.py").write_text("from src.math_utils import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
    project = _create_project(client, "Existing Task Breakdown", workspace.as_posix(), runner_mode="auto")

    generated = client.post(f"/api/projects/{project['id']}/tasks/generate")
    assert generated.status_code == 200, generated.text
    assert generated.json()["manager_mode_used"] == "deterministic"

    tasks = client.get(f"/api/projects/{project['id']}/tasks")
    assert tasks.status_code == 200, tasks.text
    task_payload = tasks.json()
    titles = [item["title"] for item in task_payload]
    assert any("Reproduce the failing behavior" in title for title in titles)
    assert any("smallest safe code fix" in title for title in titles)
    assert task_payload[0]["agent_role"] == "Validation Specialist"
    assert "tests" in task_payload[0]["allowed_paths_json"]


def test_start_task_bootstraps_worker_roster_for_existing_codebase(client) -> None:
    workspace = _fresh_workspace("start-task-bootstrap")
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "tests").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (workspace / "tests" / "test_math_utils.py").write_text("from src.math_utils import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
    project = _create_project(client, "Bootstrap Workers", workspace.as_posix(), runner_mode="dry_run")
    generated = client.post(f"/api/projects/{project['id']}/tasks/generate")
    assert generated.status_code == 200, generated.text
    tasks = client.get(f"/api/projects/{project['id']}/tasks").json()

    workers_before = client.get(f"/api/projects/{project['id']}/agents").json()
    assert [item for item in workers_before if item["kind"] == "worker"] == []

    started = client.post(f"/api/tasks/{tasks[0]['id']}/start", params={"project_id": project["id"]})
    assert started.status_code == 200, started.text
    assert started.json()["ok"] is True
    assert started.json()["run_id"] is not None

    workers_after = client.get(f"/api/projects/{project['id']}/agents").json()
    assert any(item["kind"] == "worker" for item in workers_after)


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
    status = client.get(f"/api/orchestrations/{session_id}/status", headers=_bridge_headers(), params={"project_id": project["id"]})
    assert status.status_code == 200, status.text
    payload = status.json()
    assert payload["project_id"] == project["id"]
    assert payload["pending_decisions_count"] >= 1
    assert payload["user_action_required"] is True
    assert "background_runtime" in payload


def test_orchestration_handoff_returns_not_ready_state(client) -> None:
    workspace = _fresh_workspace("handoff-not-ready")
    project = _create_project(client, "No Handoff Yet", workspace.as_posix())
    orchestration = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={"project_id": project["id"], "user_request": "Start background orchestration.", "source": "codex_plugin"},
    )
    session_id = orchestration.json()["id"]
    handoff = client.get(f"/api/orchestrations/{session_id}/handoff", headers=_bridge_headers(), params={"project_id": project["id"]})
    assert handoff.status_code == 200, handoff.text
    payload = handoff.json()
    assert payload["ready"] is False
    assert payload["status"] == "not_ready"


def test_direct_orchestration_runs_initial_turn_inline_for_live_mode(client, monkeypatch) -> None:
    from db import SessionLocal
    from orchestration import coordinator

    workspace = _fresh_workspace("live-inline-orchestration")
    project = _create_project(client, "Live Inline Orchestration", workspace.as_posix(), runner_mode="auto")
    called: dict[str, object] = {}

    async def fake_run_background_turn(orchestration_id: int, reason: str) -> None:
        db = SessionLocal()
        try:
            session = coordinator.get_session(db, orchestration_id)
            coordinator._update_session_status(
                db,
                session,
                status="running",
                manager_status="Inline provider turn completed.",
            )
            db.commit()
        finally:
            db.close()
        called["orchestration_id"] = orchestration_id
        called["reason"] = reason

    monkeypatch.setattr("main.coordinator._run_background_turn", fake_run_background_turn)

    orchestration = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={"project_id": project["id"], "user_request": "Start live orchestration.", "source": "test", "mode": "codex_cli"},
    )
    assert orchestration.status_code == 200, orchestration.text
    payload = orchestration.json()
    assert payload["status"] == "running"
    assert payload["manager_status"] == "Inline provider turn completed."
    assert called["reason"] == "user_request"
    assert called["orchestration_id"] == payload["id"]


def test_bridge_routes_require_token(client) -> None:
    workspace = _fresh_workspace("token-guard")
    with TestClient(app) as raw_client:
        response = raw_client.post(
            "/api/orchestrations/attach-workspace",
            json={"workspace_path": workspace.as_posix(), "project_name": "Token Guard", "mode": "auto", "read_only_first": True, "attach_policy": "reuse_existing"},
        )
        assert response.status_code == 401
        status = raw_client.get("/api/daemon/status")
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
