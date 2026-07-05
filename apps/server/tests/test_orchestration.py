from __future__ import annotations

import os
import shutil
import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bridge_formatter import format_status_summary_message
from bridge_messages import bridge_runtime_service
from conftest import sample_workspace, seed_imported_codebase_records, wait_for
from db import SessionLocal
from main import app
from models import Agent, AgentRun, ChangeRequest, OrchestrationSession, PendingDecision, Project, Task, utc_now


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


@pytest.fixture(autouse=True)
def _fast_orchestration_runtime(monkeypatch) -> None:
    def fake_initial_scan(db, project, *, depth: str | None = None):
        return seed_imported_codebase_records(db, project, scan_depth=depth or "standard")

    def fake_targeted_scan(db, project, *, target_paths=None, request_text=None, scan_reason=None):
        root = Path(project.workspace_path).resolve()
        indexed_areas: list[str] = []
        for raw in list(target_paths or []):
            candidate = (root / str(raw)).resolve()
            if not candidate.exists() or not candidate.is_relative_to(root):
                continue
            indexed_areas.append(candidate.relative_to(root).as_posix())
        return seed_imported_codebase_records(
            db,
            project,
            indexed_areas=indexed_areas,
            scan_depth="targeted",
        )

    from manager import service as manager_service
    from orchestration import coordinator

    async def fake_status_summary(db, project, orchestration=None):
        session = orchestration or coordinator.get_active_session_for_project(db, project)
        pending_count = len(coordinator.list_pending_decisions(db, session)) if session is not None else 0
        return format_status_summary_message(
            message_id=f"status-{project.id}-{session.id if session else 'project'}",
            project_id=project.id,
            orchestration_id=session.id if session else None,
            title="Mission Control status",
            summary="Status: fast bridge test stub.",
            project_name=project.name,
            manager_status="Waiting for dry-run command approval." if pending_count else "Ready to continue.",
            mode="dry_run / deterministic",
            swarm="not planned",
            user_action_needed="yes" if pending_count else "no",
            current_work=["Fast bridge test stub."],
            waiting_on_you=["Answer the pending decision."] if pending_count else [],
            next_expected_step="Continue the dry-run flow.",
            risk_level="medium" if pending_count else None,
            created_at=session.updated_at if session is not None else project.updated_at,
            orchestration_status=session.status if session is not None else project.status,
            current_blockers=[],
            handoff_readiness=project.handoff_status,
            active_agent_count=0,
            model_advisories=[],
        )

    original_start = coordinator.start_orchestration

    def fast_start_orchestration(
        db,
        *,
        project,
        source,
        user_request,
        orchestration_id=None,
        mode="unknown",
        metadata=None,
        schedule_background_turn=True,
    ):
        session = original_start(
            db,
            project=project,
            source=source,
            user_request=user_request,
            orchestration_id=orchestration_id,
            mode=mode,
            metadata=metadata,
            schedule_background_turn=False,
        )
        manager_service._create_approval(
            db,
            project,
            request_type="command",
            title="Approve simulated dry-run test command",
            reason_short="Run a simulated local test command so Mission Control can continue the bridge flow safely.",
            risk_level="medium",
            cwd=project.workspace_path,
            request_payload_json={"command": "python -m pytest", "scope": ["tests/"], "simulated": True},
        )
        coordinator.sync_pending_decisions(db, session)
        coordinator._update_session_status(
            db,
            session,
            status="waiting_for_user",
            manager_status="Waiting for dry-run command approval.",
        )
        coordinator._record_event(db, session, "background_turn_waiting_for_user", {"reason": "fast_test_stub"})
        return session

    async def fake_interview_context(db, project, session=None) -> dict:
        return {
            "project_title": project.name,
            "raw_idea": project.idea,
            "workspace_path": project.workspace_path,
            "docs_path": project.docs_path,
            "existing_docs_summary": [],
            "workspace_manifest_summary": {},
            "settings": {"provider": "codex", "runner_mode": "dry_run"},
            "available_tools": [],
            "provider_status": {"selected_provider": "codex", "authenticated": False, "available_models": []},
            "previous_answers": [],
            "known_facts": {},
            "unknowns": {},
            "assumptions": [],
            "constraints": [],
            "confidence_by_category": {},
        }

    monkeypatch.setattr("imported_codebase.import_service.initial_scan", fake_initial_scan)
    monkeypatch.setattr("imported_codebase.import_service.targeted_scan", fake_targeted_scan)
    monkeypatch.setattr(bridge_runtime_service, "get_status_summary", fake_status_summary)
    monkeypatch.setattr(coordinator, "start_orchestration", fast_start_orchestration)
    monkeypatch.setattr("manager.service._interview_context_payload", fake_interview_context)


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


def test_daemon_status_uses_runner_inventory_preview_without_live_probe(client, monkeypatch) -> None:
    from manager import service

    async def fail_inventory() -> list[dict[str, object]]:
        raise AssertionError("daemon/status should not perform live runner inventory probes")

    monkeypatch.setattr(service.runners, "inventory", fail_inventory)
    monkeypatch.setattr(
        service.runners,
        "inventory_preview",
        lambda: [
            {
                "runner_type": "dry_run",
                "availability": True,
                "config_status": "ready",
                "supports_background": True,
                "supports_streaming": True,
                "supports_approvals": True,
                "notes": ["preview"],
            }
        ],
    )

    response = client.get("/api/daemon/status", headers=_bridge_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["runner_inventory"] == [
        {
            "runner_type": "dry_run",
            "availability": True,
            "config_status": "ready",
            "supports_background": True,
            "supports_streaming": True,
            "supports_approvals": True,
            "notes": ["preview"],
        }
    ]


def test_background_retries_are_tracked_and_shutdown_cancels() -> None:
    from orchestration import coordinator

    async def run_test() -> None:
        coordinator._schedule_background_retry(999999, "retry_after_error", 30.0)
        snapshot = coordinator._background_runtime_snapshot(999999)
        assert snapshot["retry_scheduled"] is True
        assert snapshot["delay_seconds"] == 30.0
        assert snapshot["failure_classification"] == "transient"
        await coordinator.on_shutdown()
        assert coordinator._background_runtime_snapshot(999999)["retry_scheduled"] is False

    asyncio.run(run_test())


def test_background_turn_requests_queue_follow_up_when_current_turn_is_active(monkeypatch) -> None:
    from orchestration import coordinator

    async def run_test() -> None:
        started: list[tuple[int, str]] = []
        blocker = asyncio.Event()
        deferred_blocker = asyncio.Event()
        orchestration_id = 424242

        async def fake_run_background_turn_deferred(target_id: int, reason: str) -> None:
            started.append((target_id, reason))
            await deferred_blocker.wait()

        monkeypatch.setattr(coordinator, "_run_background_turn_deferred", fake_run_background_turn_deferred)

        active_task = asyncio.create_task(blocker.wait())
        coordinator._tasks[orchestration_id] = active_task
        coordinator._task_metadata[orchestration_id] = {
            "reason": "resume",
            "scheduled_at": "2026-06-13T20:00:00+00:00",
            "retry_scheduled": False,
            "delay_seconds": 0.1,
        }

        coordinator._schedule_background_turn(orchestration_id, "worker_report_recorded")
        queued_snapshot = coordinator._background_runtime_snapshot(orchestration_id)
        assert queued_snapshot["turn_active"] is True
        assert queued_snapshot["queued_reason"] == "worker_report_recorded"

        blocker.set()
        await active_task
        coordinator._background_task_done(orchestration_id, active_task)
        await asyncio.sleep(0)

        assert started == [(orchestration_id, "worker_report_recorded")]
        resumed_snapshot = coordinator._background_runtime_snapshot(orchestration_id)
        assert resumed_snapshot["turn_active"] is True
        assert resumed_snapshot["reason"] == "worker_report_recorded"
        assert resumed_snapshot["queued_reason"] is None

        deferred_blocker.set()
        await coordinator.on_shutdown()

    asyncio.run(run_test())


def test_background_turn_does_not_retry_user_action_required_failures(client, monkeypatch) -> None:
    from db import SessionLocal
    from models import OrchestrationSession, Project
    from orchestration import coordinator

    workspace = _fresh_workspace("user-action-required-background-failure")

    async def fake_manager_ask_next(db, project):
        raise RuntimeError("Auth token missing for provider login.")

    monkeypatch.setattr("orchestration.service.manager_ask_next", fake_manager_ask_next)

    db = SessionLocal()
    try:
        project = Project(
            name="Auth Required Runtime",
            idea="Do not auto-retry auth failures forever.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Continue planning.",
            status="planning",
            manager_status="Running.",
            metadata_json={},
        )
        db.add(session)
        db.commit()
        orchestration_id = session.id
    finally:
        db.close()

    asyncio.run(coordinator._run_background_turn(orchestration_id, "retry_after_error"))

    db = SessionLocal()
    try:
        refreshed = coordinator.get_session(db, orchestration_id)
        assert refreshed is not None
        assert refreshed.status == "paused"
        assert refreshed.metadata_json["last_background_failure_classification"] == "user_action_required"
        assert coordinator._background_runtime_snapshot(orchestration_id, metadata=refreshed.metadata_json)["retry_scheduled"] is False
        events = coordinator.list_events(db, refreshed)
        assert any(event["payload_json"].get("failure_classification") == "user_action_required" for event in events if event["event_type"] == "orchestration_failed")
    finally:
        db.close()


def test_background_turn_does_not_resume_paused_project(client, monkeypatch) -> None:
    from db import SessionLocal
    from models import OrchestrationSession, Project
    from orchestration import coordinator

    workspace = _fresh_workspace("paused-background-retry")
    called = {"manager": 0}

    async def fake_manager_ask_next(db, project):
        called["manager"] += 1
        return {"message": {"content_markdown": "should not run"}}

    monkeypatch.setattr("orchestration.service.manager_ask_next", fake_manager_ask_next)

    db = SessionLocal()
    try:
        project = Project(
            name="Paused Runtime",
            idea="Retry should not resume a paused project.",
            workspace_path=workspace.as_posix(),
            status="paused",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Retry after error.",
            status="planning",
            manager_status="Retry queued.",
            metadata_json={"background_failure_count": 1, "last_background_error": "boom"},
        )
        db.add(session)
        db.commit()
        orchestration_id = session.id
    finally:
        db.close()

    asyncio.run(coordinator._run_background_turn(orchestration_id, "retry_after_error"))

    db = SessionLocal()
    try:
        refreshed = coordinator.get_session(db, orchestration_id)
        assert refreshed is not None
        assert refreshed.status == "paused"
        assert "will not run background turns" in refreshed.manager_status
        assert called["manager"] == 0
        events = coordinator.list_events(db, refreshed)
        assert any(event["event_type"] == "background_turn_skipped" for event in events)
    finally:
        db.close()


def test_on_startup_auto_resumes_safe_orchestrations_after_daemon_restart(monkeypatch) -> None:
    from db import SessionLocal
    from models import OrchestrationSession, Project
    from orchestration import coordinator

    workspace = _fresh_workspace("startup-auto-resume")
    scheduled: list[tuple[int, str]] = []

    monkeypatch.setattr(coordinator, "_schedule_background_turn", lambda orchestration_id, reason: scheduled.append((orchestration_id, reason)))

    db = SessionLocal()
    try:
        project = Project(
            name="Startup Auto Resume",
            idea="Resume safe work after daemon restart.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Continue running safely.",
            status="running",
            manager_status="Was running before restart.",
            metadata_json={},
        )
        db.add(session)
        db.commit()
        orchestration_id = session.id
    finally:
        db.close()

    coordinator.on_startup()

    db = SessionLocal()
    try:
        refreshed = coordinator.get_session(db, orchestration_id)
        assert refreshed.status == "planning"
        assert "automatically resuming" in refreshed.manager_status.lower()
        events = coordinator.list_events(db, refreshed)
        reconciled = [event for event in events if event["event_type"] == "orchestration_reconciled_after_restart"]
        assert reconciled
        assert reconciled[-1]["payload_json"]["auto_resumed"] is True
        assert scheduled == [(orchestration_id, "daemon_restart")]
    finally:
        db.close()


def test_on_startup_preserves_waiting_for_user_sessions_after_daemon_restart(monkeypatch) -> None:
    from db import SessionLocal
    from models import OrchestrationSession, Project
    from orchestration import coordinator

    workspace = _fresh_workspace("startup-await-user")
    scheduled: list[tuple[int, str]] = []

    monkeypatch.setattr(coordinator, "_schedule_background_turn", lambda orchestration_id, reason: scheduled.append((orchestration_id, reason)))

    db = SessionLocal()
    try:
        project = Project(
            name="Startup Wait For User",
            idea="Do not auto-resume decision-blocked work.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Need user approval.",
            status="waiting_for_user",
            manager_status="Waiting on an approval.",
            metadata_json={},
        )
        db.add(session)
        db.commit()
        orchestration_id = session.id
    finally:
        db.close()

    coordinator.on_startup()

    db = SessionLocal()
    try:
        refreshed = coordinator.get_session(db, orchestration_id)
        assert refreshed.status == "waiting_for_user"
        assert "waiting for a user decision" in refreshed.manager_status.lower()
        events = coordinator.list_events(db, refreshed)
        reconciled = [event for event in events if event["event_type"] == "orchestration_reconciled_after_restart"]
        assert reconciled
        assert reconciled[-1]["payload_json"]["auto_resumed"] is False
        assert scheduled == []
    finally:
        db.close()


def test_on_startup_does_not_auto_resume_external_test_runtime_workspaces(monkeypatch) -> None:
    from db import SessionLocal
    from models import OrchestrationSession, Project
    from orchestration import coordinator

    workspace = (Path(__file__).resolve().parents[1] / ".runtime-test-runs" / "external-runtime" / "startup-foreign").resolve()
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    scheduled: list[tuple[int, str]] = []

    monkeypatch.setattr(coordinator, "_schedule_background_turn", lambda orchestration_id, reason: scheduled.append((orchestration_id, reason)))

    db = SessionLocal()
    try:
        project = Project(
            name="Foreign Test Runtime",
            idea="Do not auto-resume stale pytest artifact workspaces from another runtime root.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Continue stale test artifact work.",
            status="running",
            manager_status="Was running before restart.",
            metadata_json={},
        )
        db.add(session)
        db.commit()
        orchestration_id = session.id
    finally:
        db.close()

    coordinator.on_startup()

    db = SessionLocal()
    try:
        refreshed = coordinator.get_session(db, orchestration_id)
        assert refreshed.status == "paused"
        assert "ephemeral test workspace" in refreshed.manager_status.lower()
        events = coordinator.list_events(db, refreshed)
        reconciled = [event for event in events if event["event_type"] == "orchestration_reconciled_after_restart"]
        assert reconciled
        assert reconciled[-1]["payload_json"]["auto_resumed"] is False
        assert reconciled[-1]["payload_json"]["ephemeral_workspace"] is True
        assert scheduled == []
    finally:
        db.close()


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
        json={"project_id": project_id, "user_request": "Use Mission Control to manage this repo.", "source": "codex_plugin", "mode": "dry_run"},
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


def test_live_create_orchestration_returns_without_running_background_turn_inline(client, monkeypatch) -> None:
    from orchestration import coordinator

    workspace = _fresh_workspace("live-create-no-inline-turn")
    project = _create_project(client, "Live Create No Inline Turn", workspace.as_posix(), runner_mode="cli")
    open_response = client.post(f"/api/projects/{project['id']}/open")
    assert open_response.status_code == 200, open_response.text

    called: list[tuple[int, str]] = []

    async def fail_if_run_inline(orchestration_id: int, reason: str) -> None:
        called.append((orchestration_id, reason))
        raise AssertionError("create_orchestration should not run the first live background turn inline")

    monkeypatch.setattr(coordinator, "_run_background_turn", fail_if_run_inline)

    orchestration = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={"project_id": project["id"], "user_request": "Run this through Mission Control live.", "source": "codex_plugin", "mode": "codex_cli"},
    )

    assert orchestration.status_code == 200, orchestration.text
    assert called == []


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

    started = client.post(f"/api/projects/{project['id']}/tasks/{tasks[0]['id']}/start")
    assert started.status_code == 200, started.text
    assert started.json()["ok"] is True
    assert started.json()["run_id"] is not None

    workers_after = client.get(f"/api/projects/{project['id']}/agents").json()
    assert any(item["kind"] == "worker" for item in workers_after)


def test_project_usage_summary_reports_model_and_context_usage(client) -> None:
    workspace = _fresh_workspace("project-usage-summary")
    project = _create_project(client, "Usage Summary", workspace.as_posix(), runner_mode="dry_run")

    db = SessionLocal()
    try:
        manager = db.query(Agent).filter(Agent.project_id == project["id"], Agent.kind == "manager").one()
        manager.status = "working"
        manager.active_model = "gpt-4.3"
        manager.active_runner_type = "codex_cli"
        manager.active_usage_json = {
            "source": "prompt_estimate",
            "estimated": True,
            "sample_count": 1,
            "estimated_input_tokens": 200,
            "estimated_context_tokens": 200,
            "peak_context_tokens": 200,
            "peak_context_utilization": None,
            "context_window_tokens": None,
        }

        worker = Agent(
            project_id=project["id"],
            name="Usage Worker",
            role="Feature specialist",
            kind="worker",
            status="working",
            workspace_path=project["workspace_path"],
            active_model="gpt-5.4-mini",
            active_reasoning_effort="low",
            active_runner_type="codex_cli",
            active_usage_json={
                "source": "usage",
                "estimated": False,
                "sample_count": 1,
                "input_tokens": 120,
                "output_tokens": 20,
                "total_tokens": 140,
                "context_tokens": 120,
                "peak_context_tokens": 120,
                "context_window_tokens": 1000,
                "peak_context_utilization": 0.12,
            },
        )
        db.add(worker)
        db.flush()

        task = Task(
            project_id=project["id"],
            assigned_agent_id=worker.id,
            title="Track worker usage",
            goal="Persist token telemetry.",
            scope="Usage monitoring path.",
            agent_role="Feature specialist",
            milestone="Telemetry",
            allowed_paths_json=["apps/server/src/manager.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_usage_tracking.py -q"],
            success_criteria_json=["Usage summary route returns normalized totals."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add(task)
        db.flush()

        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=task.id,
                runner_type="codex_cli",
                process_ref="run-active",
                status="working",
                effective_settings_json={"provider": "codex", "model": "gpt-5.4-mini"},
                usage_json={
                    "source": "usage",
                    "estimated": False,
                    "sample_count": 1,
                    "input_tokens": 120,
                    "output_tokens": 20,
                    "total_tokens": 140,
                    "context_tokens": 120,
                    "peak_context_tokens": 120,
                    "context_window_tokens": 1000,
                    "peak_context_utilization": 0.12,
                },
            )
        )
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=None,
                runner_type="codex_cli",
                process_ref="run-finished",
                status="done",
                finished_at=utc_now(),
                effective_settings_json={"provider": "codex", "model": "gpt-5.4-mini"},
                usage_json={
                    "source": "usage",
                    "estimated": False,
                    "sample_count": 1,
                    "input_tokens": 200,
                    "output_tokens": 50,
                    "total_tokens": 250,
                    "context_tokens": 140,
                    "peak_context_tokens": 140,
                    "context_window_tokens": 1000,
                    "peak_context_utilization": 0.14,
                },
            )
        )
        db.commit()
    finally:
        db.close()

    agents_payload = client.get(f"/api/projects/{project['id']}/agents").json()
    worker_payload = next(item for item in agents_payload if item["name"] == "Usage Worker")
    assert worker_payload["active_usage_json"]["input_tokens"] == 120
    assert worker_payload["active_usage_json"]["peak_context_tokens"] == 120

    summary = client.get(f"/api/projects/{project['id']}/usage-summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["project_id"] == project["id"]
    assert any(item["name"] == "Manager AI" for item in payload["active_agents"])
    codex_bucket = next(item for item in payload["by_model"] if item["model"] == "gpt-5.4-mini")
    assert codex_bucket["run_count"] == 2
    assert codex_bucket["active_run_count"] == 1
    assert codex_bucket["input_tokens"] == 320
    assert codex_bucket["output_tokens"] == 70
    assert codex_bucket["total_tokens"] == 390
    assert codex_bucket["context_tokens"] == 260
    assert codex_bucket["peak_context_tokens"] == 140
    assert codex_bucket["context_window_tokens"] == 1000
    assert codex_bucket["peak_context_utilization"] == 0.14
    manager_bucket = next(item for item in payload["by_model"] if item["model"] == "gpt-4.3")
    assert manager_bucket["active_agent_count"] == 1
    assert manager_bucket["estimated_input_tokens"] == 200
    assert manager_bucket["estimated_context_tokens"] == 200
    assert "Estimated prompt/context token counts are used until providers emit concrete usage." in payload["notes"]


def test_start_task_returns_existing_active_run_instead_of_stamping_waiting_on_paths(client) -> None:
    workspace = _fresh_workspace("start-task-active-run")
    project = _create_project(client, "Active Run Repair", workspace.as_posix(), runner_mode="dry_run")

    db = SessionLocal()
    try:
        worker = Agent(
            project_id=project["id"],
            name="Execution Planner",
            role="Implementation",
            kind="worker",
            status="waiting",
            workspace_path=project["workspace_path"],
        )
        db.add(worker)
        db.flush()
        task = Task(
            project_id=project["id"],
            assigned_agent_id=worker.id,
            title="Repair stale task state",
            goal="Preserve the active run instead of marking the task blocked.",
            scope="Keep the task route idempotent for already-live work.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Start route returns the existing run."],
            estimated_complexity="small",
            dependencies_json=[],
            status="waiting_on_paths",
            waiting_reason="Another agent owns overlapping paths.",
            priority=10,
        )
        db.add(task)
        db.flush()
        worker.current_task_id = task.id
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="codex_cli",
            process_ref="live-run",
            status="working",
        )
        db.add(run)
        db.commit()
        task_id = task.id
        run_id = run.id
        worker_id = worker.id
    finally:
        db.close()

    generic = client.post(f"/api/tasks/{task_id}/start", params={"project_id": project["id"]})
    assert generic.status_code == 200, generic.text
    assert generic.json() == {"ok": True, "message": "Task is already running.", "run_id": run_id}

    scoped = client.post(f"/api/projects/{project['id']}/tasks/{task_id}/start")
    assert scoped.status_code == 200, scoped.text
    assert scoped.json() == {"ok": True, "message": "Task is already running.", "run_id": run_id}

    db = SessionLocal()
    try:
        persisted_task = db.get(Task, task_id)
        persisted_worker = db.get(Agent, worker_id)
        assert persisted_task is not None
        assert persisted_worker is not None
        assert persisted_task.status == "working"
        assert persisted_task.waiting_reason is None
        assert persisted_task.assigned_agent_id == worker_id
        assert persisted_worker.status == "working"
        assert persisted_worker.current_task_id == task_id
    finally:
        db.close()


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


def test_task_start_routes_return_clean_error_when_worker_launch_is_rejected(client, monkeypatch) -> None:
    from main import service as main_service

    workspace = _fresh_workspace("task-start-launch-rejected")
    db = SessionLocal()
    try:
        project = Project(
            name="Task Start Launch Rejected",
            idea="Do not bubble worker launch validation failures into route-level 500s.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Worker A",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Launch rejected task",
            goal="Exercise the route-level worker launch rejection path.",
            scope="A simple task for the start route.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Route returns a clean failure payload."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.commit()
        project_id = project.id
        task_id = task.id
    finally:
        db.close()

    async def fake_start_agent_task(db, project, agent, task):
        raise ValueError("Remote execution dispatch is blocked: launch_package_missing")

    monkeypatch.setattr(main_service, "start_agent_task", fake_start_agent_task)

    generic = client.post(f"/api/tasks/{task_id}/start", params={"project_id": project_id})
    assert generic.status_code == 200, generic.text
    assert generic.json() == {
        "ok": False,
        "message": "Remote execution dispatch is blocked: launch_package_missing",
        "run_id": None,
    }

    scoped = client.post(f"/api/projects/{project_id}/tasks/{task_id}/start")
    assert scoped.status_code == 200, scoped.text
    assert scoped.json() == {
        "ok": False,
        "message": "Remote execution dispatch is blocked: launch_package_missing",
        "run_id": None,
    }


def test_task_start_routes_skip_worker_claim_race_and_launch_next_candidate(client, monkeypatch) -> None:
    from main import service as main_service

    workspace = _fresh_workspace("task-start-worker-claim-race")
    db = SessionLocal()
    try:
        project = Project(
            name="Task Start Worker Claim Race",
            idea="Skip a worker that another turn claimed and launch with the next compatible candidate.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        first_worker = Agent(
            project_id=project.id,
            name="Worker A",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        second_worker = Agent(
            project_id=project.id,
            name="Worker B",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Launch after worker race",
            goal="Exercise the route-level worker-claim race recovery.",
            scope="A simple task for the start route.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Route recovers and starts with another worker."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([first_worker, second_worker, task])
        db.commit()
        project_id = project.id
        task_id = task.id
        first_worker_id = first_worker.id
        second_worker_id = second_worker.id
    finally:
        db.close()

    async def fake_start_agent_task(db, project, agent, task):
        if agent.id == first_worker_id:
            raise ValueError("Agent already has an active unfinished run.")
        agent.status = "starting"
        agent.current_task_id = task.id
        task.status = "working"
        task.assigned_agent_id = agent.id
        run = AgentRun(
            agent_id=agent.id,
            task_id=task.id,
            runner_type="dry_run",
            process_ref="route-race-recovery",
            status="starting",
        )
        db.add(run)
        db.flush()
        return run

    monkeypatch.setattr(main_service, "start_agent_task", fake_start_agent_task)

    generic = client.post(f"/api/tasks/{task_id}/start", params={"project_id": project_id})
    assert generic.status_code == 200, generic.text
    assert generic.json()["ok"] is True
    assert generic.json()["run_id"] is not None

    db = SessionLocal()
    try:
        persisted_task = db.get(Task, task_id)
        persisted_first_worker = db.get(Agent, first_worker_id)
        persisted_second_worker = db.get(Agent, second_worker_id)
        assert persisted_task is not None
        assert persisted_first_worker is not None
        assert persisted_second_worker is not None
        assert persisted_task.status == "working"
        assert persisted_task.assigned_agent_id == second_worker_id
        assert persisted_first_worker.current_task_id is None
        assert persisted_second_worker.current_task_id == task_id
    finally:
        db.close()


def test_task_start_routes_wait_cleanly_when_task_claim_is_in_flight(client, monkeypatch) -> None:
    from main import service as main_service

    workspace = _fresh_workspace("task-start-in-flight-claim")
    db = SessionLocal()
    try:
        project = Project(
            name="Task Start In Flight Claim",
            idea="If another turn has already claimed the worker, return a wait-style response instead of corrupting task state.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Worker A",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        active_task = Task(
            project_id=project.id,
            title="Already running elsewhere",
            goal="Create an active unfinished run for the worker.",
            scope="Separate task.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/other.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Active run exists."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=5,
        )
        task = Task(
            project_id=project.id,
            title="In-flight claimed task",
            goal="Exercise the route-level claimed-task wait path.",
            scope="A simple task for the start route.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Route returns a clean wait response."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, active_task, task])
        db.flush()
        worker.current_task_id = active_task.id
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=active_task.id,
                runner_type="dry_run",
                process_ref="already-running",
                status="working",
            )
        )
        db.commit()
        project_id = project.id
        task_id = task.id
        worker_id = worker.id
    finally:
        db.close()

    async def fake_start_agent_task(db, project, agent, task):
        agent.status = "starting"
        agent.current_task_id = task.id
        task.status = "working"
        task.assigned_agent_id = agent.id
        db.flush()
        raise ValueError("Agent already has an active unfinished run.")

    monkeypatch.setattr(main_service, "start_agent_task", fake_start_agent_task)

    generic = client.post(f"/api/tasks/{task_id}/start", params={"project_id": project_id})
    assert generic.status_code == 200, generic.text
    assert generic.json() == {"ok": False, "message": "No idle worker is available.", "run_id": None}

    scoped = client.post(f"/api/projects/{project_id}/tasks/{task_id}/start")
    assert scoped.status_code == 200, scoped.text
    assert scoped.json() == {"ok": False, "message": "No idle worker is available.", "run_id": None}

    db = SessionLocal()
    try:
        persisted_task = db.get(Task, task_id)
        persisted_worker = db.get(Agent, worker_id)
        assert persisted_task is not None
        assert persisted_worker is not None
        assert persisted_task.status in {"backlog", "working"}
        assert persisted_task.waiting_reason != "Another agent owns overlapping paths."
    finally:
        db.close()


def test_start_task_routes_fall_back_to_scheduler_recovery(client, monkeypatch) -> None:
    from main import service as main_service

    workspace = _fresh_workspace("task-start-scheduler-recovery")
    db = SessionLocal()
    try:
        project = Project(
            name="Task Start Scheduler Recovery",
            idea="The direct task-start route should recover through the scheduler when a worker state needs reconciliation.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Worker A",
            role="Implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Recover through scheduler",
            goal="Launch the queued task through the scheduler fallback path.",
            scope="Route-level fallback only.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Route starts the task after scheduler recovery."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.commit()
        project_id = project.id
        task_id = task.id
        worker_id = worker.id
    finally:
        db.close()

    original_start_agent_task = main_service.start_agent_task

    async def fake_start_idle_agents(db, project):
        worker = db.get(Agent, worker_id)
        task = db.get(Task, task_id)
        assert worker is not None
        assert task is not None
        worker.status = "waiting"
        await original_start_agent_task(db, project, worker, task)
        return 1

    monkeypatch.setattr(main_service, "start_idle_agents", fake_start_idle_agents)

    generic = client.post(f"/api/tasks/{task_id}/start", params={"project_id": project_id})
    assert generic.status_code == 200, generic.text
    assert generic.json()["ok"] is True
    assert generic.json()["run_id"] is not None

    db = SessionLocal()
    try:
        persisted_task = db.get(Task, task_id)
        persisted_worker = db.get(Agent, worker_id)
        assert persisted_task is not None
        assert persisted_worker is not None
        assert persisted_task.status == "working"
        assert persisted_task.assigned_agent_id == worker_id
        assert persisted_worker.status in {"starting", "working"}
        assert persisted_worker.current_task_id == task_id
    finally:
        db.close()


def test_orchestration_status_includes_manager_and_agent_runtime_details(client) -> None:
    workspace = _fresh_workspace("status-runtime-details")

    db = SessionLocal()
    try:
        project = Project(
            name="Runtime Detail Status",
            idea="Expose live manager and worker details.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="auto",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Keep the orchestration moving.",
            status="running",
            manager_status="Mission Control is routing the next background step.",
            metadata_json={},
        )
        db.add(session)
        db.flush()
        manager = Agent(
            project_id=project.id,
            name="Mission Control Manager",
            role="Manager",
            kind="manager",
            status="running",
            workspace_path=workspace.as_posix(),
            active_runner_type="codex_cli",
            active_model="gpt-5-codex",
            current_action="Reviewing worker output and queueing the next safe task.",
        )
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Engineer",
            kind="worker",
            status="working",
            workspace_path=workspace.as_posix(),
            mission="Harden daemon routing paths.",
            active_runner_type="codex_cli",
            active_model="gpt-5-codex",
            current_action="Fixing the daemon listener drop under load.",
        )
        db.add_all([manager, worker])
        db.commit()
        project_id = project.id
        session_id = session.id
    finally:
        db.close()

    response = client.get(f"/api/orchestrations/{session_id}/status", headers=_bridge_headers(), params={"project_id": project_id})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["manager"]["name"] == "Mission Control Manager"
    assert payload["manager"]["active_model"] == "gpt-5-codex"
    assert payload["manager"]["runner_type"] == "codex_cli"
    assert payload["active_agents"][0]["name"] == "Service Flow Builder"
    assert payload["active_agents"][0]["active_model"] == "gpt-5-codex"
    assert payload["active_agents"][0]["current_action"] == "Fixing the daemon listener drop under load."


def test_orchestration_handoff_returns_not_ready_state(client) -> None:
    workspace = _fresh_workspace("handoff-not-ready")
    project = _create_project(client, "No Handoff Yet", workspace.as_posix(), runner_mode="dry_run")
    orchestration = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={"project_id": project["id"], "user_request": "Start background orchestration.", "source": "codex_plugin", "mode": "dry_run"},
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


def test_bootstrap_live_execution_reopens_follow_up_scope_after_completed_tasks(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import ChangeRequest, OrchestrationSession, Project, Task
    from orchestration import coordinator
    from sqlalchemy import select

    workspace = _fresh_workspace("follow-up-live-bootstrap")
    generated: dict[str, object] = {"called": False}

    async def fake_manager_message(db, project, request_text):
        return {"message": {"content_markdown": f"Queued: {request_text}"}}

    async def fake_generate_tasks(db, project):
        generated["called"] = True
        project.status = "building"
        project.handoff_status = "not_ready"
        project.final_report_json = None
        task = Task(
            project_id=project.id,
            title="Reopened follow-up batch",
            goal="Represent the new follow-up scope with fresh backlog work.",
            scope="Only the newly requested existing-repo change.",
            agent_role="Primary implementation",
            milestone="Follow-up batch",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Mission Control reopened the project with a backlog task."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(task)
        db.flush()
        return [task], "deterministic"

    async def fake_start_idle_agents(db, project):
        return 0

    monkeypatch.setattr("orchestration.service.manager_message", fake_manager_message)
    monkeypatch.setattr("orchestration.service.generate_tasks", fake_generate_tasks)
    monkeypatch.setattr("orchestration.service.start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr("orchestration.service.initialize_build_roster", lambda db, project: [])

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Follow Up Live Bootstrap",
            idea="Reopen a completed imported repo from a live follow-up request.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="handoff_ready",
            handoff_status="ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json={"summary_markdown": "Old handoff"},
        )
        completed_task = Task(
            project_id=1,
            title="Old completed task",
            goal="Finish the original imported-repo scope.",
            scope="Legacy completed scope.",
            agent_role="Primary implementation",
            milestone="Initial batch",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Original scope shipped."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add(project)
        db.flush()
        completed_task.project_id = project.id
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Implement a fresh follow-up feature in the imported repo.",
            status="initializing",
            manager_status="Starting.",
            mode="codex_cli",
            metadata_json={},
        )
        db.add_all([completed_task, session])
        db.commit()
        project_id = project.id
        orchestration_id = session.id
    finally:
        db.close()

    asyncio.run(coordinator._run_background_turn(orchestration_id, "user_request"))

    db = SessionLocal()
    try:
        refreshed_project = db.scalar(select(Project).where(Project.id == project_id))
        refreshed_session = coordinator.get_session(db, orchestration_id)
        assert refreshed_project is not None
        assert refreshed_session is not None
        assert generated["called"] is True
        assert refreshed_project.status == "building"
        assert refreshed_project.handoff_status == "not_ready"
        assert refreshed_project.final_report_json is None
        tasks = list(db.scalars(select(Task).where(Task.project_id == refreshed_project.id).order_by(Task.id.asc())))
        assert any(task.title == "Reopened follow-up batch" and task.status == "backlog" for task in tasks)
        requests = list(
            db.scalars(
                select(ChangeRequest)
                .where(ChangeRequest.project_id == refreshed_project.id)
                .order_by(ChangeRequest.id.asc())
            )
        )
        assert requests
        assert requests[-1].request_text == "Implement a fresh follow-up feature in the imported repo."
    finally:
        db.close()


def test_background_turn_reopens_follow_up_scope_after_completed_tasks(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import ChangeRequest, OrchestrationSession, Project, Task
    from orchestration import coordinator
    from sqlalchemy import select

    workspace = _fresh_workspace("follow-up-background-bootstrap")
    generated: dict[str, object] = {"called": False}

    async def fake_manager_ask_next(db, project):
        return {"message": {"content_markdown": "Open the next narrow cleanup batch."}}

    async def fake_generate_tasks(db, project):
        generated["called"] = True
        task = Task(
            project_id=project.id,
            title="New Post-Checkpoint Batch",
            goal="Represent the reopened follow-up scope with fresh backlog work.",
            scope="Only the newly identified remaining residue cleanup.",
            agent_role="Primary implementation",
            milestone="Follow-up batch",
            allowed_paths_json=["scripts"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Mission Control reopened the project with a backlog task."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(task)
        db.flush()
        return [task], "deterministic"

    async def fake_start_idle_agents(db, project):
        return 0

    monkeypatch.setattr("orchestration.service.manager_ask_next", fake_manager_ask_next)
    monkeypatch.setattr("orchestration.service.generate_tasks", fake_generate_tasks)
    monkeypatch.setattr("orchestration.service.start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr("orchestration.service.initialize_build_roster", lambda db, project: [])

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Follow Up Background Bootstrap",
            idea="Reopen completed imported-repo work after a recorded worker checkpoint.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        completed_task = Task(
            project_id=1,
            title="Completed checkpoint task",
            goal="Finish the previous existing-repo batch.",
            scope="Legacy completed scope.",
            agent_role="Primary implementation",
            milestone="Checkpoint batch",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Previous scope shipped."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add(project)
        db.flush()
        completed_task.project_id = project.id
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Keep the live codex_cli campaign going until the remaining residue batch is opened.",
            status="planning",
            manager_status="Continuing after recorded worker progress.",
            mode="codex_cli",
            metadata_json={},
        )
        db.add_all([completed_task, session])
        db.commit()
        project_id = project.id
        orchestration_id = session.id
    finally:
        db.close()

    asyncio.run(coordinator._run_background_turn(orchestration_id, "worker_report_recorded"))

    db = SessionLocal()
    try:
        refreshed_project = db.scalar(select(Project).where(Project.id == project_id))
        refreshed_session = coordinator.get_session(db, orchestration_id)
        assert refreshed_project is not None
        assert refreshed_session is not None
        assert generated["called"] is True
        tasks = list(db.scalars(select(Task).where(Task.project_id == refreshed_project.id).order_by(Task.id.asc())))
        assert any(task.title == "New Post-Checkpoint Batch" and task.status == "backlog" for task in tasks)
        requests = list(
            db.scalars(
                select(ChangeRequest)
                .where(ChangeRequest.project_id == refreshed_project.id)
                .order_by(ChangeRequest.id.asc())
            )
        )
        assert requests
        assert requests[-1].request_text == "Keep the live codex_cli campaign going until the remaining residue batch is opened."
    finally:
        db.close()


def test_bootstrap_live_execution_replenishes_parallel_backlog_for_new_request(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import OrchestrationSession, Project, Task
    from orchestration import coordinator
    from sqlalchemy import select

    workspace = _fresh_workspace("parallel-replenishment-live-bootstrap")
    generated: dict[str, object] = {"called": False}

    async def fake_manager_message(db, project, request_text):
        return {"message": {"content_markdown": f"Queued: {request_text}"}}

    async def fake_generate_tasks(db, project):
        generated["called"] = True
        task = Task(
            project_id=project.id,
            title="Fresh benchmark lane",
            goal="Replenish the live backlog with a new bounded lane.",
            scope="Only the new benchmark lane.",
            agent_role="Primary implementation",
            milestone="Benchmark reset",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["A fresh backlog lane exists."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(task)
        db.flush()
        return [task], "deterministic"

    async def fake_start_idle_agents(db, project):
        return 0

    monkeypatch.setattr("orchestration.service.manager_message", fake_manager_message)
    monkeypatch.setattr("orchestration.service.generate_tasks", fake_generate_tasks)
    monkeypatch.setattr("orchestration.service.start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr("orchestration.service.initialize_build_roster", lambda db, project: [])

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Parallel Replenishment Live Bootstrap",
            idea="Do not ignore a new live benchmark request just because one old backlog task still exists.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        existing_backlog = Task(
            project_id=1,
            title="Old narrow lane",
            goal="Represents thin leftover backlog.",
            scope="Legacy lane.",
            agent_role="Primary implementation",
            milestone="Legacy",
            allowed_paths_json=["docs"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Legacy lane remains open."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add(project)
        db.flush()
        existing_backlog.project_id = project.id
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Start a fresh benchmark attempt and refill the backlog with parallel lanes.",
            status="planning",
            manager_status="Continuing after a thin backlog state.",
            mode="codex_cli",
            metadata_json={},
        )
        db.add_all([existing_backlog, session])
        db.commit()
        project_id = project.id
        orchestration_id = session.id
    finally:
        db.close()

    asyncio.run(coordinator._run_background_turn(orchestration_id, "user_request"))

    db = SessionLocal()
    try:
        refreshed_project = db.scalar(select(Project).where(Project.id == project_id))
        tasks = list(db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.id.asc())))
        assert refreshed_project is not None
        assert generated["called"] is True
        assert any(task.title == "Fresh benchmark lane" for task in tasks)
    finally:
        db.close()


def test_bootstrap_live_execution_forces_regeneration_for_fresh_benchmark_reset(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import OrchestrationSession, Project, Task
    from orchestration import coordinator
    from sqlalchemy import select

    workspace = _fresh_workspace("fresh-benchmark-reset-bootstrap")
    generated: dict[str, object] = {"called": False}

    async def fake_manager_message(db, project, request_text):
        return {"message": {"content_markdown": f"Queued: {request_text}"}}

    async def fake_generate_tasks(db, project):
        generated["called"] = True
        task = Task(
            project_id=project.id,
            title="Fresh reset lane",
            goal="Rebuild the backlog from the fresh benchmark reset request.",
            scope="Only the regenerated lane.",
            agent_role="Service Flow Builder",
            milestone="Fresh benchmark reset",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["The fresh reset forces backlog regeneration."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(task)
        db.flush()
        return [task], "deterministic"

    async def fake_start_idle_agents(db, project):
        return 0

    monkeypatch.setattr("orchestration.service.manager_message", fake_manager_message)
    monkeypatch.setattr("orchestration.service.generate_tasks", fake_generate_tasks)
    monkeypatch.setattr("orchestration.service.start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr("orchestration.service.initialize_build_roster", lambda db, project: [])
    monkeypatch.setattr("orchestration.service._productive_open_task_count", lambda db, project, existing_tasks=None: 1)
    monkeypatch.setattr("orchestration.service._target_parallel_open_task_count", lambda db, project, existing_tasks=None: 1)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Fresh Benchmark Reset Bootstrap",
            idea="A fresh benchmark reset must regenerate backlog even when the old open-task count looks full on paper.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        stale_open_task = Task(
            project_id=1,
            title="Old stale lane",
            goal="Legacy stale lane.",
            scope="Old stale scope.",
            agent_role="Execution Planner",
            milestone="Legacy",
            allowed_paths_json=["docs"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Legacy lane remains open."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=20,
        )
        db.add(project)
        db.flush()
        stale_open_task.project_id = project.id
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Fresh benchmark reset after Mission Control runtime update. Start from zero and ignore prior counts.",
            status="planning",
            manager_status="Trying to recover from stale backlog state.",
            mode="codex_cli",
            metadata_json={},
        )
        db.add_all([stale_open_task, session])
        db.commit()
        project_id = project.id
        orchestration_id = session.id
    finally:
        db.close()

    asyncio.run(coordinator._run_background_turn(orchestration_id, "user_request"))

    db = SessionLocal()
    try:
        refreshed_project = db.scalar(select(Project).where(Project.id == project_id))
        tasks = list(db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.id.asc())))
        assert refreshed_project is not None
        assert generated["called"] is True
        assert any(task.title == "Fresh reset lane" for task in tasks)
    finally:
        db.close()


def test_bootstrap_live_execution_clears_stale_review_decisions_for_fresh_benchmark_reset(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import OrchestrationSession, PendingDecision, Project, Task
    from orchestration import coordinator
    from sqlalchemy import select

    workspace = _fresh_workspace("fresh-benchmark-reset-clears-review-decisions")
    generated: dict[str, object] = {"called": False}

    async def fake_manager_message(db, project, request_text):
        return {"message": {"content_markdown": f"Queued: {request_text}"}}

    async def fake_generate_tasks(db, project):
        generated["called"] = True
        task = db.scalar(select(Task).where(Task.project_id == project.id, Task.title == "Apps Mcp Server Defect Batch"))
        assert task is not None
        return [task], "deterministic"

    async def fake_start_idle_agents(db, project):
        return 0

    monkeypatch.setattr("orchestration.service.manager_message", fake_manager_message)
    monkeypatch.setattr("orchestration.service.generate_tasks", fake_generate_tasks)
    monkeypatch.setattr("orchestration.service.start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr("orchestration.service.initialize_build_roster", lambda db, project: [])
    monkeypatch.setattr("orchestration.service._productive_open_task_count", lambda db, project, existing_tasks=None: 0)
    monkeypatch.setattr("orchestration.service._target_parallel_open_task_count", lambda db, project, existing_tasks=None: 1)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Fresh Benchmark Reset Clears Review Decisions",
            idea="A fresh benchmark reset should cancel stale handoff review debt before bootstrap exits early.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        review_task = Task(
            project_id=project.id,
            assigned_agent_id=None,
            title="Apps Mcp Server Defect Batch",
            goal="Old retained review lane.",
            scope="Legacy review gate.",
            agent_role="Apps Mcp Server Subsystem Builder",
            milestone="Legacy batch",
            allowed_paths_json=["apps/mcp-server"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Legacy review debt remains pending."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            waiting_reason="Runner completion envelope validation failed.",
            failure_count=2,
            priority=20,
        )
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Fresh benchmark reset after Mission Control runtime update. Start from zero and ignore prior counts.",
            status="planning",
            manager_status="Trying to recover from stale review debt.",
            mode="codex_cli",
            metadata_json={},
        )
        db.add_all([review_task, session])
        db.flush()
        pending = PendingDecision(
            project_id=project.id,
            orchestration_id=session.id,
            decision_type="handoff_review",
            title="Review required: Apps Mcp Server Defect Batch",
            message="Task needs review before Mission Control can continue.",
            requesting_agent_id=None,
            related_task_id=review_task.id,
            risk_level="medium",
            options_json=[
                {"id": "approve", "label": "Approve", "description": "Mark this reviewed task complete and let Mission Control continue."},
                {"id": "request_changes", "label": "Request changes", "description": "Send this task back to backlog so Mission Control can route follow-up work."},
            ],
            recommended_option="approve",
            status="pending",
            source_kind="task_review",
            source_id=review_task.id,
        )
        request = ChangeRequest(
            project_id=project.id,
            request_text="Fresh benchmark reset after Mission Control runtime update. Start from zero and ignore prior counts.",
            classification="bugfix",
            impact_estimate="large",
            status="new",
        )
        db.add_all([pending, request])
        db.commit()
        project_id = project.id
        orchestration_id = session.id
        pending_id = pending.id
        review_task_id = review_task.id
    finally:
        db.close()

    asyncio.run(coordinator._run_background_turn(orchestration_id, "user_request"))

    db = SessionLocal()
    try:
        refreshed_task = db.get(Task, review_task_id)
        refreshed_pending = db.get(PendingDecision, pending_id)
        assert refreshed_task is not None
        assert refreshed_pending is not None
        assert generated["called"] is True
        assert refreshed_task.status == "backlog"
        assert refreshed_task.assigned_agent_id is None
        assert refreshed_task.failure_count == 0
        assert refreshed_pending.status == "cancelled"
        assert refreshed_pending.answered_at is not None
    finally:
        db.close()


def test_start_orchestration_clears_stale_review_decisions_for_fresh_benchmark_reset(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import ChangeRequest, OrchestrationSession, PendingDecision, Project, Task
    from orchestration import coordinator

    workspace = _fresh_workspace("start-orchestration-clears-review-decisions")

    monkeypatch.setattr(coordinator, "_schedule_background_turn", lambda *args, **kwargs: None)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Start Fresh Reset Clears Review Decisions",
            idea="A fresh benchmark reset should not expose stale review debt in the immediate start response.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        review_task = Task(
            project_id=project.id,
            assigned_agent_id=None,
            title="Apps Mcp Server Tests Defect Batch",
            goal="Old review lane.",
            scope="Legacy review gate.",
            agent_role="Apps Mcp Server Tests Subsystem Builder",
            milestone="Legacy batch",
            allowed_paths_json=["apps/mcp-server/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Legacy review debt remains pending."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            waiting_reason="Old review debt.",
            failure_count=2,
            priority=20,
        )
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Previous request.",
            status="waiting_for_user",
            manager_status="Waiting on stale review debt.",
            mode="codex_cli",
            metadata_json={},
        )
        db.add_all([review_task, session])
        db.flush()
        pending = PendingDecision(
            project_id=project.id,
            orchestration_id=session.id,
            decision_type="handoff_review",
            title="Review required: Apps Mcp Server Tests Defect Batch",
            message="Task needs review before Mission Control can continue.",
            requesting_agent_id=None,
            related_task_id=review_task.id,
            risk_level="medium",
            options_json=[
                {"id": "approve", "label": "Approve", "description": "Mark this reviewed task complete and let Mission Control continue."},
                {"id": "request_changes", "label": "Request changes", "description": "Send this task back to backlog so Mission Control can route follow-up work."},
            ],
            recommended_option="approve",
            status="pending",
            source_kind="task_review",
            source_id=review_task.id,
        )
        bare_review_task = Task(
            project_id=project.id,
            assigned_agent_id=None,
            title="Apps Dashboard Public Defect Batch",
            goal="Old review lane with no pending row yet.",
            scope="Legacy review task.",
            agent_role="Apps Dashboard Public Subsystem Builder",
            milestone="Legacy batch",
            allowed_paths_json=["apps/dashboard/public"],
            forbidden_paths_json=[],
            validation_steps_json=["npm run test"],
            success_criteria_json=["Legacy review debt remains pending."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            waiting_reason="Old review task without decision.",
            failure_count=1,
            priority=30,
        )
        request_text = "Fresh benchmark reset after Mission Control code changes. Reset to 0 and find, fix, validate, deduplicate, and report 50 distinct issues."
        previous_request = ChangeRequest(
            project_id=project.id,
            request_text=request_text,
            classification="bugfix",
            impact_estimate="large",
            status="accepted",
        )
        db.add_all([pending, bare_review_task, previous_request])
        db.commit()

        coordinator.start_orchestration(
            db,
            project=project,
            source="test",
            user_request=request_text,
            orchestration_id=session.id,
            mode="codex_cli",
        )
        db.commit()

        db.refresh(review_task)
        db.refresh(bare_review_task)
        db.refresh(pending)
        db.refresh(previous_request)
        assert review_task.status == "backlog"
        assert review_task.assigned_agent_id is None
        assert review_task.failure_count == 0
        assert bare_review_task.status == "backlog"
        assert bare_review_task.assigned_agent_id is None
        assert bare_review_task.failure_count == 0
        assert pending.status == "cancelled"
        assert pending.answered_at is not None
        assert previous_request.status == "new"
    finally:
        db.close()


def test_background_turn_reopens_db_sessions_between_bootstrap_phases(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import OrchestrationSession, Project, Task
    from orchestration import coordinator
    from sqlalchemy import select

    workspace = _fresh_workspace("background-turn-session-reopen")
    seen_sequences: dict[str, int | None] = {"generate": None, "start": None, "ask_next": None}

    import orchestration as orchestration_module

    real_session_local = orchestration_module.SessionLocal
    sequence = {"value": 0}

    def tracked_session_local():
        session = real_session_local()
        sequence["value"] += 1
        setattr(session, "_mc_sequence", sequence["value"])
        return session

    async def fake_generate_tasks(db, project):
        seen_sequences["generate"] = getattr(db, "_mc_sequence", None)
        task = Task(
            project_id=project.id,
            title="Fresh live lane",
            goal="Represent a fresh live lane after the session boundary.",
            scope="Only the reopened live lane.",
            agent_role="Primary implementation",
            milestone="Live follow-up",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["A fresh live lane exists."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(task)
        db.flush()
        return [task], "deterministic"

    async def fake_start_idle_agents(db, project):
        seen_sequences["start"] = getattr(db, "_mc_sequence", None)
        return 0

    async def fake_manager_ask_next(db, project):
        seen_sequences["ask_next"] = getattr(db, "_mc_sequence", None)
        return {"message": {"content_markdown": "Continue the next live lane."}}

    monkeypatch.setattr(orchestration_module, "SessionLocal", tracked_session_local)
    monkeypatch.setattr("orchestration.service.generate_tasks", fake_generate_tasks)
    monkeypatch.setattr("orchestration.service.start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr("orchestration.service.manager_ask_next", fake_manager_ask_next)
    monkeypatch.setattr("orchestration.service.initialize_build_roster", lambda db, project: [])

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Background Turn Session Reopen",
            idea="Close and reopen DB sessions between bootstrap phases so SQLite is not pinned across async work.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        session = OrchestrationSession(
            project_id=1,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="",
            status="planning",
            manager_status="Continuing after restart.",
            mode="codex_cli",
            metadata_json={},
        )
        db.add(project)
        db.flush()
        session.project_id = project.id
        db.add(session)
        db.commit()
        orchestration_id = session.id
        project_id = project.id
    finally:
        db.close()

    asyncio.run(coordinator._run_background_turn(orchestration_id, "daemon_restart"))

    db = SessionLocal()
    try:
        refreshed_project = db.scalar(select(Project).where(Project.id == project_id))
        assert refreshed_project is not None
        assert seen_sequences["generate"] is not None
        assert seen_sequences["start"] is not None
        assert seen_sequences["ask_next"] is not None
        assert seen_sequences["generate"] != seen_sequences["start"]
        assert seen_sequences["start"] != seen_sequences["ask_next"]
    finally:
        db.close()


def test_bootstrap_live_execution_records_provider_backoff_event(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import OrchestrationSession, Project, Task
    from orchestration import coordinator
    from sqlalchemy import select

    workspace = _fresh_workspace("provider-backoff-bootstrap")

    async def fake_generate_tasks(db, project):
        task = Task(
            project_id=project.id,
            title="Apps Server Defect Batch",
            goal="Keep the server lane ready for the next provider window.",
            scope="Server-only lane.",
            agent_role="Apps Server Subsystem Builder",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["A runnable lane exists once provider quota recovers."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(task)
        db.flush()
        return [task], "deterministic"

    async def fake_start_idle_agents(db, project):
        return 0

    monkeypatch.setattr("orchestration.service.generate_tasks", fake_generate_tasks)
    monkeypatch.setattr("orchestration.service.start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr("orchestration.service.initialize_build_roster", lambda db, project: [])
    monkeypatch.setattr(
        "orchestration.service._provider_backoff_state",
        lambda db, project: {
            "until": project.created_at + timedelta(minutes=15),
            "remaining_seconds": 900,
            "summary": "You've hit your usage limit. Try again later.",
        },
    )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Provider Backoff Bootstrap",
            idea="Record provider quota backoff honestly instead of emitting another fake bootstrap lap.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        session = OrchestrationSession(
            project_id=1,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Continue the benchmark when the provider window reopens.",
            status="planning",
            manager_status="Mission Control Manager is reviewing the workspace.",
            mode="codex_cli",
            metadata_json={},
        )
        db.add(project)
        db.flush()
        session.project_id = project.id
        db.add(session)
        db.commit()
        orchestration_id = session.id
        project_id = project.id
    finally:
        db.close()

    asyncio.run(coordinator._run_background_turn(orchestration_id, "worker_report_recorded"))

    db = SessionLocal()
    try:
        refreshed = db.scalar(select(OrchestrationSession).where(OrchestrationSession.id == orchestration_id))
        assert refreshed is not None
        assert "provider usage limit" in refreshed.manager_status.lower()
        events = coordinator.list_events(db, refreshed)
        assert any(event["event_type"] == "provider_backoff_active" for event in events)
        assert not any(event["event_type"] == "live_execution_bootstrapped" for event in events)
        project = db.scalar(select(Project).where(Project.id == project_id))
        assert project is not None
    finally:
        db.close()


def test_derive_runtime_state_waits_for_user_when_only_review_tasks_remain() -> None:
    from db import SessionLocal, init_db
    from models import OrchestrationSession, Project, Task
    from orchestration import coordinator

    workspace = _fresh_workspace("review-only-runtime-state")

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Review Only Runtime State",
            idea="Do not pretend review-only work is runnable background work.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="needs_review",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Continue the imported-repo repair batch.",
            status="planning",
            manager_status="Mission Control has runnable work queued and is routing the next safe background step.",
            mode="codex_cli",
            metadata_json={},
        )
        review_task = Task(
            project_id=project.id,
            title="Review the current repair batch",
            goal="Confirm the batch before continuing.",
            scope="Review-only lane.",
            agent_role="Validation Specialist",
            milestone="Review gate",
            allowed_paths_json=["apps/server/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Review is acknowledged before more work starts."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            priority=10,
        )
        blocked_follow_up = Task(
            project_id=project.id,
            title="Refresh campaign state after review",
            goal="Proceed only after the review gate clears.",
            scope="Follow-up after review.",
            agent_role="Handoff Writer",
            milestone="Follow-up",
            allowed_paths_json=["docs"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Follow-up waits for review."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            waiting_reason="Waiting for task dependencies to finish.",
            priority=20,
        )
        db.add_all([session, review_task, blocked_follow_up])
        db.flush()
        blocked_follow_up.dependencies_json = [review_task.id]
        db.commit()

        status, message = coordinator._derive_runtime_state(
            db,
            session,
            project,
            [],
            handoff_status="needs_review",
            current_action={"type": "info", "message": "No safe backlog task is ready."},
            manager_fallback="No safe backlog task is ready.",
        )

        assert status == "waiting_for_user"
        assert "waiting for review" in message.lower()
    finally:
        db.close()


def test_sync_pending_decisions_creates_review_cards_for_needs_review_tasks() -> None:
    from db import SessionLocal, init_db
    from models import OrchestrationSession, PendingDecision, Project, Task
    from orchestration import coordinator
    from sqlalchemy import select

    workspace = _fresh_workspace("review-task-pending-decisions")

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Review Decision Mirroring",
            idea="Mirror needs_review tasks into pending decisions.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="needs_review",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Continue the review-gated batch.",
            status="planning",
            manager_status="Review is required.",
            mode="codex_cli",
            metadata_json={},
        )
        task = Task(
            project_id=project.id,
            title="Review the timeout-lane repair batch",
            goal="Confirm the repair batch before more work starts.",
            scope="Review-only lane.",
            agent_role="Validation Specialist",
            milestone="Review gate",
            allowed_paths_json=["apps/server/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Review is acknowledged before more work starts."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            priority=10,
        )
        db.add_all([session, task])
        db.commit()

        pending = coordinator.list_pending_decisions(db, session)

        assert len(pending) == 1
        assert pending[0]["decision_type"] == "handoff_review"
        assert pending[0]["recommended_option"] == "approve"
        assert {item["id"] for item in pending[0]["options"]} == {"approve", "request_changes"}

        mirrored = db.scalar(
            select(PendingDecision)
            .where(PendingDecision.orchestration_id == session.id, PendingDecision.source_kind == "task_review")
            .order_by(PendingDecision.id.desc())
        )
        assert mirrored is not None
        assert mirrored.related_task_id == task.id
        assert mirrored.status == "pending"
    finally:
        db.close()


def test_sync_pending_decisions_cancels_stale_review_card_for_active_run() -> None:
    from db import SessionLocal, init_db
    from orchestration import coordinator

    workspace = _fresh_workspace("stale-review-active-run")

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Stale Review Active Run",
            idea="Do not keep obsolete review cards after a task resumes.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="needs_review",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Continue after stale review.",
            status="planning",
            manager_status="A worker resumed the task.",
            mode="codex_cli",
            metadata_json={},
        )
        worker = Agent(
            project_id=project.id,
            name="Review Worker",
            kind="worker",
            role="Fixer",
            status="working",
            workspace_path=workspace.as_posix(),
            mission="Resume stale review work.",
            current_action="Working on resumed task.",
        )
        task = Task(
            project_id=project.id,
            title="Apps MCP Server Tests Defect Batch",
            goal="Fix the test defect batch.",
            scope="apps/mcp-server/tests",
            agent_role="Fixer",
            milestone="Benchmark",
            allowed_paths_json=["apps/mcp-server/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest apps/mcp-server/tests"],
            success_criteria_json=["Task has active work, not pending review."],
            estimated_complexity="medium",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([session, worker, task])
        db.flush()
        worker.current_task_id = task.id
        task.assigned_agent_id = worker.id
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=task.id,
                runner_type="cli",
                process_ref="active-review-retry",
                status="working",
            )
        )
        stale = PendingDecision(
            project_id=project.id,
            orchestration_id=session.id,
            decision_type="handoff_review",
            title=f"Review required: {task.title}",
            message="Old review gate should not survive resumed work.",
            requesting_agent_id=worker.id,
            related_task_id=task.id,
            risk_level="medium",
            options_json=[{"id": "approve", "label": "Approve"}],
            recommended_option="approve",
            source_kind="task_review",
            source_id=task.id,
            status="pending",
        )
        db.add(stale)
        db.commit()

        coordinator_pending = coordinator.list_pending_decisions(db, session)
        bridge_pending = bridge_runtime_service.get_pending_decisions(db, project=project)

        db.refresh(stale)
        assert coordinator_pending == []
        assert bridge_pending == []
        assert stale.status == "cancelled"
        assert stale.answer_json["source"] == "task_review_reconciliation"
        assert "active worker run" in stale.answer_json["free_text"]
    finally:
        db.close()


def test_answer_pending_decision_approve_review_task_marks_task_done(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import OrchestrationSession, Project, Task
    from orchestration import coordinator

    workspace = _fresh_workspace("approve-review-task")

    async def _skip_finalize_handoff(db, project) -> None:
        return None

    monkeypatch.setattr("manager.service._maybe_finalize_handoff", _skip_finalize_handoff)
    monkeypatch.setattr(coordinator, "_schedule_background_turn", lambda orchestration_id, reason: None)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Approve Review Task",
            idea="Approving a review card should complete the task.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="needs_review",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Approve the review gate.",
            status="waiting_for_user",
            manager_status="Waiting for review.",
            mode="codex_cli",
            metadata_json={},
        )
        task = Task(
            project_id=project.id,
            title="Review the validated timeout fix",
            goal="Clear the review gate.",
            scope="Review-only lane.",
            agent_role="Validation Specialist",
            milestone="Review gate",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["The review task is completed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            priority=10,
        )
        db.add_all([session, task])
        db.commit()

        decision = coordinator.sync_pending_decisions(db, session)[0]

        coordinator.answer_pending_decision(
            db,
            decision,
            option_id="approve",
            selected_text="Approve",
        )
        db.commit()
        db.refresh(task)
        db.refresh(decision)

        assert task.status == "done"
        assert task.assigned_agent_id is None
        assert decision.status == "answered"
        assert decision.answer_json["option_id"] == "approve"
    finally:
        db.close()


def test_answer_pending_decision_request_changes_requeues_review_task(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import OrchestrationSession, Project, Task
    from orchestration import coordinator

    workspace = _fresh_workspace("request-review-changes")

    monkeypatch.setattr(coordinator, "_schedule_background_turn", lambda orchestration_id, reason: None)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Request Review Changes",
            idea="Requesting changes should requeue the task.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="needs_review",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="Bounce the review task back.",
            status="waiting_for_user",
            manager_status="Waiting for review.",
            mode="codex_cli",
            metadata_json={},
        )
        task = Task(
            project_id=project.id,
            title="Review the recursive improvement lane",
            goal="Send it back if the review is not accepted.",
            scope="Review-only lane.",
            agent_role="Execution Planner",
            milestone="Review gate",
            allowed_paths_json=["docs"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["The review task can be reworked."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            priority=10,
        )
        db.add_all([session, task])
        db.commit()

        decision = coordinator.sync_pending_decisions(db, session)[0]

        coordinator.answer_pending_decision(
            db,
            decision,
            option_id="request_changes",
            selected_text="Request changes",
        )
        db.commit()
        db.refresh(task)
        db.refresh(decision)

        assert task.status == "backlog"
        assert task.assigned_agent_id is None
        assert task.waiting_reason == "Review requested changes before Mission Control can continue."
        assert decision.status == "answered"
        assert decision.answer_json["option_id"] == "request_changes"
    finally:
        db.close()


def test_bootstrap_live_execution_reopens_backlog_from_recent_change_request_without_session_text(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import ChangeRequest, OrchestrationSession, Project, Task
    from orchestration import coordinator
    from sqlalchemy import select

    workspace = _fresh_workspace("follow-up-bootstrap-without-session-text")
    generated: dict[str, object] = {"called": False}

    async def fake_generate_tasks(db, project):
        generated["called"] = True
        task = Task(
            project_id=project.id,
            title="Fresh repo analysis after idle checkpoint",
            goal="Open the next evidence-backed repo-analysis batch.",
            scope="Read-first repo analysis only.",
            agent_role="execution_planner",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/**", "mission-control/**", "docs/**", "README.md"],
            forbidden_paths_json=["apps/dashboard/**"],
            validation_steps_json=["Run the bounded analysis workflow."],
            success_criteria_json=["A fresh next batch exists."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(task)
        db.flush()
        return [task], "codex"

    async def fake_start_idle_agents(db, project):
        return 0

    monkeypatch.setattr("orchestration.service.generate_tasks", fake_generate_tasks)
    monkeypatch.setattr("orchestration.service.start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr("orchestration.service.initialize_build_roster", lambda db, project: [])

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Recent Change Request Bootstrap",
            idea="Reopen the next batch from a saved request even when the session text is blank.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="needs_review",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        completed_task = Task(
            project_id=1,
            title="Completed checkpoint task",
            goal="Finish the previous batch.",
            scope="Legacy completed scope.",
            agent_role="Primary implementation",
            milestone="Checkpoint batch",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Previous scope shipped."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add(project)
        db.flush()
        completed_task.project_id = project.id
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="",
            status="planning",
            manager_status="Continuing after a completed batch.",
            mode="codex_cli",
            metadata_json={},
        )
        db.add_all([completed_task, session])
        db.flush()
        request = ChangeRequest(
            project_id=project.id,
            request_text="Open the next fresh repo-analysis batch from the current 39-fix baseline.",
            classification="feature",
            impact_estimate="medium",
            status="pending",
        )
        db.add(request)
        db.commit()
        project_id = project.id
        orchestration_id = session.id
    finally:
        db.close()


def test_bootstrap_live_execution_reopens_backlog_from_standing_change_request_after_newer_task_updates(monkeypatch) -> None:
    from db import SessionLocal, init_db
    from models import ChangeRequest, OrchestrationSession, Project, Task
    from orchestration import coordinator
    from sqlalchemy import select

    workspace = _fresh_workspace("follow-up-bootstrap-standing-request")
    generated: dict[str, object] = {"called": False}

    async def fake_generate_tasks(db, project):
        generated["called"] = True
        task = Task(
            project_id=project.id,
            title="Fresh repo analysis from standing request",
            goal="Open the next batch from the still-active standing request.",
            scope="Read-first repo analysis only.",
            agent_role="execution_planner",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/**", "mission-control/**", "docs/**", "README.md"],
            forbidden_paths_json=["apps/dashboard/**"],
            validation_steps_json=["Run the bounded analysis workflow."],
            success_criteria_json=["A fresh next batch exists."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(task)
        db.flush()
        return [task], "codex"

    async def fake_start_idle_agents(db, project):
        return 0

    monkeypatch.setattr("orchestration.service.generate_tasks", fake_generate_tasks)
    monkeypatch.setattr("orchestration.service.start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr("orchestration.service.initialize_build_roster", lambda db, project: [])

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Standing Change Request Bootstrap",
            idea="Reopen the next batch from a standing request even after newer task updates.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        completed_task = Task(
            project_id=1,
            title="Completed checkpoint task",
            goal="Finish the previous batch.",
            scope="Legacy completed scope.",
            agent_role="Primary implementation",
            milestone="Checkpoint batch",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_orchestration.py -q"],
            success_criteria_json=["Previous scope shipped."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add(project)
        db.flush()
        completed_task.project_id = project.id
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=workspace.as_posix(),
            source="test",
            user_request="",
            status="planning",
            manager_status="Continuing after a completed batch.",
            mode="codex_cli",
            metadata_json={},
        )
        request = ChangeRequest(
            project_id=project.id,
            request_text="Keep the repo-analysis and bug-fix campaign going until the user says stop.",
            classification="feature",
            impact_estimate="large",
            status="triaged",
        )
        db.add_all([completed_task, session, request])
        db.flush()
        request.updated_at = project.created_at
        completed_task.updated_at = session.created_at
        db.commit()
        project_id = project.id
        orchestration_id = session.id
    finally:
        db.close()

    asyncio.run(coordinator._run_background_turn(orchestration_id, "worker_report_recorded"))

    db = SessionLocal()
    try:
        tasks = list(db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.id.asc())))
        assert generated["called"] is True
        assert [task.title for task in tasks] == [
            "Completed checkpoint task",
            "Fresh repo analysis from standing request",
        ]
        assert tasks[-1].status == "backlog"
    finally:
        db.close()


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
