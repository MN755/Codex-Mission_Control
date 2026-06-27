from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from bridge_formatter import format_status_summary_message
from bridge_messages import bridge_runtime_service
from conftest import sample_workspace, seed_imported_codebase_records, wait_for
from db import SessionLocal
from errors import MissionControlError
from manager import service
from models import Project, ProjectEvent


def _bridge_headers() -> dict[str, str]:
    token_path = Path(os.environ["MISSION_CONTROL_RUNTIME_ROOT"]) / "daemon.token"
    wait_for(token_path.exists)
    return {"X-Mission-Control-Token": token_path.read_text(encoding="utf-8").strip()}


def _prepare_repo_workspace(name: str) -> Path:
    workspace = Path(sample_workspace(name))
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# Repo under Mission Control\n", encoding="utf-8")
    tests_dir = workspace / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_sample.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    return workspace


def _set_project_to_dry_run(client, project_id: int) -> None:
    settings = client.get("/api/settings", params={"project_id": project_id})
    assert settings.status_code == 200, settings.text
    payload = settings.json()
    payload["runner_mode"] = "dry_run"
    response = client.put("/api/settings", params={"project_id": project_id}, json=payload)
    assert response.status_code == 200, response.text


@pytest.fixture(autouse=True)
def _fast_headless_runtime(monkeypatch) -> None:
    from orchestration import coordinator

    def fake_initial_scan(db, project, *, depth: str | None = None):
        return seed_imported_codebase_records(db, project, scan_depth=depth or "standard")

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
        service._create_approval(
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

    monkeypatch.setattr("imported_codebase.import_service.initial_scan", fake_initial_scan)
    monkeypatch.setattr(bridge_runtime_service, "get_status_summary", fake_status_summary)
    monkeypatch.setattr(coordinator, "start_orchestration", fast_start_orchestration)


def test_headless_happy_path_acceptance(client) -> None:
    workspace = _prepare_repo_workspace("headless-happy-path")
    attach = client.post(
        "/api/headless/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Headless Happy Path",
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert attach.status_code == 200, attach.text
    attach_payload = attach.json()
    project_id = attach_payload["project"]["id"]
    assert attach_payload["attach_outcome"] == "imported_existing_codebase"

    _set_project_to_dry_run(client, project_id)

    opened = client.post(f"/api/projects/{project_id}/open")
    assert opened.status_code == 200, opened.text

    orchestration = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={
            "project_id": project_id,
            "user_request": "Use Mission Control for this repo and fix the failing tests.",
            "source": "codex_plugin",
        },
    )
    assert orchestration.status_code == 200, orchestration.text
    orchestration_id = orchestration.json()["id"]

    wait_for(
        lambda: bool(
            client.get(
                f"/api/orchestrations/{orchestration_id}/pending-decisions",
                headers=_bridge_headers(),
                params={"project_id": project_id},
            ).json()
        )
    )

    status_summary = client.get(
        f"/api/orchestrations/{orchestration_id}/status-summary",
        headers=_bridge_headers(),
        params={"project_id": project_id},
    )
    assert status_summary.status_code == 200, status_summary.text
    status_payload = status_summary.json()
    assert status_payload["message_type"] in {"blocked", "status_update"}
    assert status_payload["user_action_required"] is True
    assert "## Mission Control Status" in status_payload["fallback_markdown"]
    assert "### Current work" in status_payload["fallback_markdown"]
    assert "### Waiting on you" in status_payload["fallback_markdown"]
    assert "### Next expected step" in status_payload["fallback_markdown"]

    project_status_summary = client.get(
        f"/api/projects/{project_id}/orchestrations/{orchestration_id}/status-summary",
        headers=_bridge_headers(),
    )
    assert project_status_summary.status_code == 200, project_status_summary.text
    assert project_status_summary.json()["message_type"] == status_payload["message_type"]

    decisions_response = client.get(
        f"/api/orchestrations/{orchestration_id}/pending-decisions",
        headers=_bridge_headers(),
        params={"project_id": project_id},
    )
    assert decisions_response.status_code == 200, decisions_response.text
    decisions = decisions_response.json()
    approval = next((item for item in decisions if item["decision_type"] == "command_approval"), None)
    if approval is None:
        db = SessionLocal()
        try:
            project = db.get(Project, project_id)
            assert project is not None
            service._create_approval(
                db,
                project,
                request_type="command",
                title="Approve simulated dry-run test command",
                reason_short="Run a simulated local test command so Mission Control can continue the headless bridge flow safely.",
                risk_level="medium",
                cwd=project.workspace_path,
                request_payload_json={"command": "python -m pytest", "scope": ["tests/"], "simulated": True},
            )
            db.commit()
        finally:
            db.close()
        decisions = client.get(
            f"/api/orchestrations/{orchestration_id}/pending-decisions",
            headers=_bridge_headers(),
            params={"project_id": project_id},
        ).json()
        approval = next(item for item in decisions if item["decision_type"] == "command_approval")

    for decision in decisions:
        if decision["id"] == approval["id"] or not decision.get("options"):
            continue
        option = decision["options"][0]
        response = client.post(
            f"/api/projects/{project_id}/decisions/{decision['id']}/answer",
            headers=_bridge_headers(),
            json={"option_id": option["id"], "selected_text": option["label"]},
        )
        assert response.status_code == 200, response.text

    approval_message = client.get(
        f"/api/decisions/{approval['id']}/bridge-message",
        headers=_bridge_headers(),
        params={"project_id": project_id},
    )
    assert approval_message.status_code == 200, approval_message.text
    approval_payload = approval_message.json()
    assert approval_payload["message_type"] == "approval_request"
    assert "##" in approval_payload["fallback_markdown"]
    assert "**Command:**" in approval_payload["fallback_markdown"]
    assert "### Choose one" in approval_payload["fallback_markdown"]

    answered = client.post(
        f"/api/projects/{project_id}/decisions/{approval['id']}/answer",
        headers=_bridge_headers(),
        json={"option_id": "approve_once", "selected_text": "Approve once"},
    )
    assert answered.status_code == 200, answered.text
    answered_payload = answered.json()
    assert answered_payload["decision"]["status"] == "answered"
    assert answered_payload["next_status_summary"] is not None
    assert answered_payload["next_status_summary"]["user_action_required"] is False

    db = SessionLocal()
    try:
        db.add(
            ProjectEvent(
                project_id=project_id,
                event_type="validation_log",
                payload_json={
                    "message": "Validation saw Authorization: Bearer super-secret-token and OPENAI_API_KEY=sk-proj-secret-value",
                    "raw_log": "never show this raw log",
                },
            )
        )
        db.commit()
    finally:
        db.close()

    digest = client.get(
        f"/api/orchestrations/{orchestration_id}/event-digest",
        headers=_bridge_headers(),
        params={"window": "since_orchestration_start", "project_id": project_id},
    )
    assert digest.status_code == 200, digest.text
    digest_payload = digest.json()
    assert digest_payload["message_type"] == "event_digest"
    assert "## Mission Control event digest" in digest_payload["fallback_markdown"]
    assert "super-secret-token" not in digest_payload["fallback_markdown"]
    assert "sk-proj-secret-value" not in digest_payload["fallback_markdown"]
    assert "raw_log" not in digest_payload["fallback_markdown"]

    project_digest = client.get(
        f"/api/projects/{project_id}/orchestrations/{orchestration_id}/event-digest",
        headers=_bridge_headers(),
        params={"window": "since_orchestration_start"},
    )
    assert project_digest.status_code == 200, project_digest.text
    assert project_digest.json()["message_type"] == digest_payload["message_type"]

    evidence = client.post(
        f"/api/projects/{project_id}/handoff/evidence",
        headers=_bridge_headers(),
        json={
            "evidence_type": "test_result",
            "claim": "OPENAI_API_KEY=sk-proj-secret-value pytest run",
            "summary": "Authorization: Bearer super-secret-token should be redacted in chat output.",
            "command": "python -m pytest",
            "status": "not_run",
            "metadata_json": {"note": "Dry-run evidence seed"},
        },
    )
    assert evidence.status_code == 200, evidence.text

    handoff_generate = client.post(
        f"/api/projects/{project_id}/handoff/generate",
        headers=_bridge_headers(),
    )
    assert handoff_generate.status_code == 200, handoff_generate.text
    assert handoff_generate.json()["dry_run"] is True

    handoff_summary = client.get(
        f"/api/orchestrations/{orchestration_id}/handoff-summary",
        headers=_bridge_headers(),
        params={"project_id": project_id},
    )
    assert handoff_summary.status_code == 200, handoff_summary.text
    handoff_payload = handoff_summary.json()
    assert handoff_payload["message_type"] == "handoff_ready"
    assert "## Mission Control handoff" in handoff_payload["fallback_markdown"]
    assert "### Validation / evidence" in handoff_payload["fallback_markdown"]
    assert "dry-run" in handoff_payload["fallback_markdown"].lower()
    assert "sk-proj-secret-value" not in handoff_payload["fallback_markdown"]
    assert "super-secret-token" not in handoff_payload["fallback_markdown"]

    project_handoff_summary = client.get(
        f"/api/projects/{project_id}/orchestrations/{orchestration_id}/handoff-summary",
        headers=_bridge_headers(),
    )
    assert project_handoff_summary.status_code == 200, project_handoff_summary.text
    assert project_handoff_summary.json()["message_type"] == handoff_payload["message_type"]


def test_headless_attach_workspace_alias_returns_bridge_fields(client) -> None:
    workspace = _prepare_repo_workspace("headless-attach-alias")
    response = client.post(
        "/api/headless/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Headless Alias",
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == payload["project"]["id"]
    assert payload["project_name"] == payload["project"]["name"]
    assert payload["source_type"] == "existing_folder"
    assert payload["next_action"] == "start_orchestration"


def test_headless_happy_path_demo_endpoint(client) -> None:
    workspace = _prepare_repo_workspace("headless-happy-path-demo")
    response = client.post(
        "/api/headless/happy-path-demo",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Happy Path Demo",
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
            "user_request": "Use Mission Control for this repo and fix the failing tests.",
            "create_pending_decision": True,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["attach"]["project_id"] == payload["attach"]["project"]["id"]
    assert payload["orchestration"]["source"] == "test"
    assert payload["orchestration"]["mode"] == "dry_run"
    assert payload["initial_status_summary"]["message_type"] in {"blocked", "status_update"}
    assert payload["pending_decision"]["status"] == "pending"
    assert payload["decision_bridge_message"]["message_type"] in {"approval_request", "manager_question"}
    assert payload["answer_result"] is None
    assert payload["event_digest"] is None
    assert payload["handoff_summary"] is None


def test_full_headless_happy_path_approve_flow(client) -> None:
    workspace = _prepare_repo_workspace("headless-approve-flow")
    start = client.post(
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
    assert start.status_code == 200, start.text
    payload = start.json()
    orchestration_id = payload["orchestration"]["id"]
    approval = next(item for item in payload["pending_decisions"] if item["decision_type"] == "command_approval")
    answered = client.post(
        f"/api/decisions/{approval['id']}/answer",
        headers=_bridge_headers(),
        params={"project_id": payload["project"]["id"]},
        json={"option_id": "approve_once", "selected_text": "Approve once"},
    )
    assert answered.status_code == 200, answered.text
    answer_payload = answered.json()
    assert answer_payload["decision"]["status"] == "answered"
    assert answer_payload["next_status_summary"]["user_action_required"] is False

    audit_log = client.get(
        f"/api/projects/{payload['project']['id']}/security/audit-log",
        headers=_bridge_headers(),
    )
    assert audit_log.status_code == 200, audit_log.text
    audit_entries = audit_log.json()
    assert audit_entries
    assert audit_entries[0]["decision"] == "approved"
    assert audit_entries[0]["action_type"] == "command_approval"

    digest = client.get(
        f"/api/orchestrations/{orchestration_id}/event-digest",
        headers=_bridge_headers(),
        params={"window": "since_orchestration_start", "project_id": payload["project"]["id"]},
    )
    assert digest.status_code == 200, digest.text
    assert "dry run validation simulated" in digest.json()["fallback_markdown"].lower()

    handoff = client.get(f"/api/orchestrations/{orchestration_id}/handoff-summary", headers=_bridge_headers(), params={"project_id": payload["project"]["id"]})
    assert handoff.status_code == 200, handoff.text
    handoff_payload = handoff.json()
    assert "dry-run" in handoff_payload["fallback_markdown"].lower()
    assert "not run" in handoff_payload["fallback_markdown"].lower()


def test_start_headless_task_honors_project_id_when_workspace_is_also_provided(client) -> None:
    workspace = _prepare_repo_workspace("headless-project-id-match")
    first = client.post(
        "/api/projects",
        json={
            "name": "Project Id Match",
            "idea": "Honor the explicit project id",
            "workspace_path": workspace.as_posix(),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    )
    assert first.status_code == 200, first.text
    project = first.json()

    second = client.post(
        "/api/projects",
        json={
            "name": "Project Id Match Duplicate",
            "idea": "Same workspace, different project",
            "workspace_path": workspace.as_posix(),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    )
    assert second.status_code == 200, second.text

    start = client.post(
        "/api/headless/start-task",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_id": project["id"],
            "user_request": "Use Mission Control for this repo and fix the failing tests.",
            "strategy": "balanced",
            "mode": "dry_run",
            "interview_mode": "skip",
            "attach_policy": "reuse_existing",
        },
    )
    assert start.status_code == 200, start.text
    assert start.json()["project"]["id"] == project["id"]


def test_full_headless_happy_path_deny_flow(client) -> None:
    workspace = _prepare_repo_workspace("headless-deny-flow")
    start = client.post(
        "/api/headless/start-task",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "user_request": "Use Mission Control for this repo and fix the failing tests.",
            "strategy": "safe_mode",
            "mode": "dry_run",
            "interview_mode": "skip",
        },
    )
    assert start.status_code == 200, start.text
    payload = start.json()
    orchestration_id = payload["orchestration"]["id"]
    approval = next(item for item in payload["pending_decisions"] if item["decision_type"] == "command_approval")
    answered = client.post(
        f"/api/decisions/{approval['id']}/answer",
        headers=_bridge_headers(),
        params={"project_id": payload["project"]["id"]},
        json={"option_id": "deny", "selected_text": "Deny"},
    )
    assert answered.status_code == 200, answered.text
    answer_payload = answered.json()
    assert answer_payload["decision"]["status"] == "answered"
    assert answer_payload["next_status_summary"]["user_action_required"] is False

    audit_log = client.get(
        f"/api/projects/{payload['project']['id']}/security/audit-log",
        headers=_bridge_headers(),
    )
    assert audit_log.status_code == 200, audit_log.text
    audit_entries = audit_log.json()
    assert audit_entries
    assert audit_entries[0]["decision"] == "denied"
    assert audit_entries[0]["action_type"] == "command_approval"

    handoff = client.get(f"/api/orchestrations/{orchestration_id}/handoff-summary", headers=_bridge_headers(), params={"project_id": payload["project"]["id"]})
    assert handoff.status_code == 200, handoff.text
    handoff_markdown = handoff.json()["fallback_markdown"].lower()
    assert "dry-run" in handoff_markdown
    assert "not run" in handoff_markdown
    assert "denied" in handoff_markdown or "limitations" in handoff_markdown


def test_real_codex_headless_approval_resumes_background_turn_without_dry_run_shortcut(monkeypatch, client) -> None:
    from orchestration import coordinator

    workspace = _prepare_repo_workspace("headless-real-codex-flow")
    scheduled: list[tuple[int, str]] = []

    def fake_schedule_background_turn(orchestration_id: int, reason: str) -> None:
        scheduled.append((orchestration_id, reason))

    monkeypatch.setattr(coordinator, "_schedule_background_turn", fake_schedule_background_turn)

    db = SessionLocal()
    try:
        project = service.create_project(
            db,
            name="Headless Real Codex",
            idea="Run a real Codex CLI approval flow.",
            workspace_path=workspace.as_posix(),
            provider="codex",
            runner_mode="auto",
            manager_mode="auto",
        )
        session = coordinator.start_orchestration(
            db,
            project=project,
            source="codex_plugin",
            user_request="Use Mission Control for this repo with real Codex agents and fix the failing tests.",
            mode="codex_cli",
            metadata={"headless_happy_path": True, "simulated": False},
            schedule_background_turn=False,
        )
        service._create_approval(
            db,
            project,
            request_type="command",
            title="Approve real validation command",
            reason_short="Run the real pytest validation command before the Codex worker handoff.",
            risk_level="medium",
            cwd=project.workspace_path,
            request_payload_json={"command": "python -m pytest", "scope": ["tests/"]},
        )
        pending = coordinator.sync_pending_decisions(db, session)
        decision = next(item for item in pending if item.decision_type == "command_approval")
        coordinator._update_session_status(
            db,
            session,
            status="waiting_for_user",
            manager_status="Codex CLI orchestration is waiting for command approval.",
        )

        answered_decision, next_summary = asyncio.run(
            bridge_runtime_service.answer_decision(
                db,
                decision,
                option_id="approve_once",
                selected_text="Approve once",
            )
        )
        db.commit()
        db.expire_all()

        refreshed_session = coordinator.get_session(db, session.id)
        handoff = service.get_project_handoff_summary(db, project)
        event_types = [event["event_type"] for event in coordinator.list_events(db, refreshed_session)]

        assert answered_decision["status"] == "answered"
        assert next_summary is not None
        assert refreshed_session.status == "planning"
        assert refreshed_session.manager_status == "Decision recorded. Mission Control is continuing the orchestration."
        assert "dry_run_validation_simulated" not in event_types
        assert "dry_run_happy_path_completed" not in event_types
        assert handoff["status"] == "not_ready"
        assert scheduled == [(session.id, "decision_answered")]
    finally:
        db.close()


def test_live_headless_start_task_schedules_background_turn_instead_of_running_inline(monkeypatch) -> None:
    from orchestration import OrchestrationCoordinator, coordinator

    workspace = _prepare_repo_workspace("headless-live-background-start")
    scheduled: list[tuple[int, str]] = []

    async def fake_resolve_mode(_requested_mode: str) -> str:
        return "codex_cli"

    async def fake_status_summary(db, project, orchestration=None):
        raise AssertionError("Live headless starts should use the queued fast summary instead of the full status summary.")

    def fake_schedule_background_turn(orchestration_id: int, reason: str) -> None:
        scheduled.append((orchestration_id, reason))

    def passthrough_start_orchestration(
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
        return OrchestrationCoordinator.start_orchestration(
            coordinator,
            db,
            project=project,
            source=source,
            user_request=user_request,
            orchestration_id=orchestration_id,
            mode=mode,
            metadata=metadata,
            schedule_background_turn=schedule_background_turn,
        )

    monkeypatch.setattr(bridge_runtime_service, "_resolve_orchestration_mode", fake_resolve_mode)
    monkeypatch.setattr(bridge_runtime_service, "get_status_summary", fake_status_summary)
    monkeypatch.setattr(coordinator, "_schedule_background_turn", fake_schedule_background_turn)
    monkeypatch.setattr(coordinator, "start_orchestration", passthrough_start_orchestration)

    db = SessionLocal()
    try:
        project = service.create_project(
            db,
            name="Headless Live Background Start",
            idea="Return quickly for live Codex headless starts.",
            workspace_path=workspace.as_posix(),
            provider="codex",
            runner_mode="auto",
            manager_mode="auto",
        )
        result = asyncio.run(
            bridge_runtime_service.start_headless_task(
                db,
                workspace_path=None,
                project_id=project.id,
                user_request="Use Mission Control for this repo and implement the next safe feature.",
                strategy="balanced",
                mode="codex_cli",
                interview_mode="skip",
                attach_policy="reuse_existing",
            )
        )
        db.commit()

        assert result["mode_used"] == "codex_cli"
        assert result["pending_decisions"] == []
        assert result["next_action"] == "get_status_summary"
        assert result["user_action_required"] is False
        assert result["orchestration"]["status"] == "planning"
        assert result["status_summary"]["message_type"] == "status_update"
        assert "queued the first live background turn" in result["status_summary"]["fallback_markdown"].lower()
        assert scheduled == [(result["orchestration"]["id"], "user_request")]
    finally:
        db.close()


def test_live_headless_start_task_promotes_imported_repo_out_of_read_only(monkeypatch) -> None:
    from orchestration import OrchestrationCoordinator, coordinator

    workspace = _prepare_repo_workspace("headless-live-write-promotion")
    scheduled: list[tuple[int, str]] = []

    async def fake_resolve_mode(_requested_mode: str) -> str:
        return "codex_cli"

    def fake_schedule_background_turn(orchestration_id: int, reason: str) -> None:
        scheduled.append((orchestration_id, reason))

    def passthrough_start_orchestration(
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
        return OrchestrationCoordinator.start_orchestration(
            coordinator,
            db,
            project=project,
            source=source,
            user_request=user_request,
            orchestration_id=orchestration_id,
            mode=mode,
            metadata=metadata,
            schedule_background_turn=schedule_background_turn,
        )

    monkeypatch.setattr(bridge_runtime_service, "_resolve_orchestration_mode", fake_resolve_mode)
    monkeypatch.setattr(coordinator, "_schedule_background_turn", fake_schedule_background_turn)
    monkeypatch.setattr(coordinator, "start_orchestration", passthrough_start_orchestration)

    db = SessionLocal()
    try:
        result = asyncio.run(
            bridge_runtime_service.start_headless_task(
                db,
                workspace_path=workspace.as_posix(),
                project_id=None,
                user_request="Create a writable live Codex orchestration for this imported repo.",
                strategy="balanced",
                mode="codex_cli",
                interview_mode="skip",
                attach_policy="reuse_existing",
            )
        )
        db.commit()

        project = db.get(Project, int(result["project"]["id"]))
        assert project is not None
        assert project.source_type == "existing_folder"
        assert project.write_permission_status == "write_allowed"
        assert project.settings is not None
        assert project.settings.sandbox_mode == "workspace-write"
        assert project.settings.approval_policy == "on-request"
        assert scheduled == [(result["orchestration"]["id"], "user_request")]
    finally:
        db.close()


def test_explicit_codex_cli_mode_rejects_dry_run_fallback(monkeypatch) -> None:
    async def fake_inventory() -> list[dict[str, object]]:
        return [
            {"runner_type": "dry_run", "availability": True},
            {"runner_type": "codex_cli", "availability": False},
        ]

    monkeypatch.setattr(service.runners, "inventory", fake_inventory)

    with pytest.raises(MissionControlError) as excinfo:
        asyncio.run(bridge_runtime_service._resolve_orchestration_mode("codex_cli"))

    assert excinfo.value.code == "MC-RUNNER-SELECTION-FAILED-001"
    assert "explicitly requested" in str(excinfo.value.detail).lower()
