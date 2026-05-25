from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from bridge_formatter import (
    format_diagnostic_message,
    format_handoff_message,
    format_pending_decision_message,
    format_status_summary_message,
)
from conftest import sample_workspace, wait_for
from db import SessionLocal
from models import DecisionRecord, EvidenceBasedHandoff, ManagerQuestion, Project, ProjectEvent, utc_now


def _bridge_headers() -> dict[str, str]:
    token_path = Path(os.environ["MISSION_CONTROL_RUNTIME_ROOT"]) / "daemon.token"
    wait_for(token_path.exists)
    return {"X-Mission-Control-Token": token_path.read_text(encoding="utf-8").strip()}


def _create_project(client, name: str, workspace_name: str) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"{name} idea",
            "workspace_path": sample_workspace(workspace_name),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_bridge_formatter_status_summary_shape() -> None:
    payload = format_status_summary_message(
        message_id="status-1",
        project_id=1,
        orchestration_id=2,
        title="Mission Control status",
        summary="**Status:** Manager is waiting on an approval.",
        project_name="Bridge Demo",
        manager_status="Waiting for approval",
        mode="dry_run / deterministic",
        swarm="iterative / active",
        user_action_needed="yes",
        current_work=["Manager is reviewing the repo."],
        waiting_on_you=["Approve the safe command request."],
        next_expected_step="Resume the runner once approval is answered.",
        risk_level="medium",
        created_at=utc_now(),
        model_advisories=["Worker model `qwen2.5:7b` is a weaker local model and often underperforms on code-edit turns."],
    )
    assert payload["message_type"] == "blocked"
    assert payload["user_action_required"] is True
    assert "## Mission Control Status" in payload["fallback_markdown"]
    assert "**What Mission Control is doing:** Status: Manager is waiting on an approval." in payload["fallback_markdown"]
    assert "### What is blocking progress" not in payload["fallback_markdown"]
    assert "### Model advisories" in payload["fallback_markdown"]
    assert "### Waiting on you" in payload["fallback_markdown"]


def test_bridge_formatter_command_and_tool_approval_payloads() -> None:
    command = format_pending_decision_message(
        decision={
            "id": 1,
            "project_id": 10,
            "orchestration_id": 20,
            "decision_type": "command_approval",
            "title": "Approve local test command",
            "message": "Run a local test command before continuing.",
            "risk_level": "medium",
            "status": "pending",
            "options_json": [{"id": "approve_once", "label": "Approve once"}],
            "created_at": utc_now(),
            "presentation_json": {
                "command": "python -m pytest",
                "cwd": "C:/repo",
            },
        },
        requesting_agent="Verifier",
    )
    tool = format_pending_decision_message(
        decision={
            "id": 2,
            "project_id": 10,
            "orchestration_id": 20,
            "decision_type": "tool_approval",
            "title": "Approve diagnostics tool",
            "message": "Use a local diagnostics tool.",
            "risk_level": "low",
            "status": "pending",
            "options_json": [{"id": "approve_once", "label": "Approve once"}],
            "created_at": utc_now(),
            "presentation_json": {
                "tool_name": "mission_control_get_status",
                "requested_access": "project status",
            },
        },
        requesting_agent="Diagnostics",
    )
    assert command["source_type"] == "security"
    assert command["message_type"] == "approval_request"
    assert "**Command:** `python -m pytest`" in command["fallback_markdown"]
    assert "### Choose one" in command["fallback_markdown"]
    assert tool["source_type"] == "security"
    assert tool["machine_payload_json"]["tool_name"] == "mission_control_get_status"


def test_bridge_formatter_manager_question_handoff_and_redaction() -> None:
    question = format_pending_decision_message(
        decision={
            "id": 3,
            "project_id": 10,
            "orchestration_id": 20,
            "decision_type": "manager_question",
            "title": "Manager needs a decision",
            "message": "Should the repo preserve the current architecture?",
            "risk_level": "medium",
            "status": "pending",
            "options_json": [{"id": "preserve", "label": "Preserve"}],
            "created_at": utc_now(),
            "presentation_json": {
                "question": "Should the repo preserve the current architecture?",
            },
        },
    )
    handoff = format_handoff_message(
        message_id="handoff-1",
        project_id=10,
        orchestration_id=20,
        handoff_status="needs_review",
        confidence_level="medium",
        evidence_level="partial",
        what_changed=["Updated backend bridge runtime."],
        how_to_run=["python -m pytest apps/server/tests/test_bridge_runtime.py"],
        validation_items=["Tests not run."],
        known_limitations=["No MCP transport was exercised in this test."],
        next_tasks=["Wire the MCP server to these service functions."],
        important_files=["apps/server/src/bridge_messages.py"],
        dry_run=True,
        created_at=utc_now(),
    )
    diagnostic = format_diagnostic_message(
        message_id="diag-1",
        title="Plugin diagnostics",
        summary="OPENAI_API_KEY=sk-proj-secret-value should never leak.",
        markdown="Authorization: Bearer super-secret-token",
        machine_payload_json={"token": "ghp_abcdefghijklmnopqrstuvwxyz"},
        created_at=utc_now(),
    )
    assert question["message_type"] == "manager_question"
    assert "**Question:**" in question["fallback_markdown"]
    assert "### Why this blocks progress" in question["fallback_markdown"]
    assert "### Choose one" in question["fallback_markdown"]
    assert handoff["user_action_required"] is True
    assert "Validation / evidence" in handoff["fallback_markdown"]
    assert "Review state" in handoff["fallback_markdown"]
    assert diagnostic["redaction_status"] == "redacted"
    assert "sk-proj-secret-value" not in diagnostic["summary"]
    assert "super-secret-token" not in diagnostic["fallback_markdown"]


def test_headless_diagnostic_summary_route_formats_sections_and_redacts(monkeypatch, client) -> None:
    async def fake_health() -> dict:
        return {
            "status": "broken",
            "checks": [
                {"label": "Daemon reachable", "status": "ready", "summary": "Daemon responded from localhost."},
                {"label": "Bridge auth", "status": "broken", "summary": "OPENAI_API_KEY=sk-proj-secret-value leaked in logs."},
            ],
            "recommended_next_steps": ["Restart the local bridge after checking the token file."],
            "safe_troubleshooting_commands": ["codex login status", "set OPENAI_API_KEY=should-not-leak"],
            "notes": ["Authorization: Bearer super-secret-token should never be shown."],
            "checked_at": utc_now(),
        }

    monkeypatch.setattr("bridge_messages.mission_control_plugin_health", fake_health)
    response = client.get("/api/headless/diagnostic-summary", headers=_bridge_headers())
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["message_type"] == "diagnostic_summary"
    assert payload["user_action_required"] is True
    assert "## Mission Control Diagnostics" in payload["fallback_markdown"]
    assert "### What works" in payload["fallback_markdown"]
    assert "### What needs attention" in payload["fallback_markdown"]
    assert "### Safe commands" in payload["fallback_markdown"]
    assert "sk-proj-secret-value" not in payload["fallback_markdown"]
    assert "super-secret-token" not in payload["fallback_markdown"]


def test_pending_decision_bridge_routes_and_answer_flow(client) -> None:
    project = _create_project(client, "Bridge Decisions", "bridge-decisions")
    db = SessionLocal()
    try:
        record = db.get(Project, project["id"])
        assert record is not None
        question = ManagerQuestion(
            project_id=record.id,
            question="Should Mission Control preserve the current architecture?",
            options_json=[
                {"id": "preserve", "label": "Preserve it", "description": "Keep the current architecture intact."},
                {"id": "change", "label": "Change it", "description": "Allow structural changes."},
            ],
            impact="high",
            status="pending",
        )
        db.add(question)
        db.commit()
    finally:
        db.close()

    decisions_response = client.get(f"/api/projects/{project['id']}/pending-decisions", headers=_bridge_headers())
    assert decisions_response.status_code == 200, decisions_response.text
    decisions = decisions_response.json()
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision["decision_type"] == "manager_question"

    bridge_message = client.get(
        f"/api/decisions/{decision['id']}/bridge-message",
        headers=_bridge_headers(),
        params={"project_id": project["id"]},
    )
    assert bridge_message.status_code == 200, bridge_message.text
    assert bridge_message.json()["message_type"] == "manager_question"

    answer = client.post(
        f"/api/decisions/{decision['id']}/answer",
        headers=_bridge_headers(),
        params={"project_id": project["id"]},
        json={"option_id": "preserve", "selected_text": "Preserve it"},
    )
    assert answer.status_code == 200, answer.text
    payload = answer.json()
    assert payload["decision"]["status"] == "answered"
    assert payload["next_status_summary"] is not None


def test_pending_decision_rejects_invalid_option(client) -> None:
    project = _create_project(client, "Invalid Decision", "invalid-decision")
    db = SessionLocal()
    try:
        record = db.get(Project, project["id"])
        assert record is not None
        question = ManagerQuestion(
            project_id=record.id,
            question="Which path should Mission Control take?",
            options_json=[{"id": "safe", "label": "Safe path"}],
            impact="medium",
            status="pending",
        )
        db.add(question)
        db.commit()
    finally:
        db.close()

    decisions = client.get(f"/api/projects/{project['id']}/pending-decisions", headers=_bridge_headers()).json()
    decision_id = decisions[0]["id"]
    response = client.post(
        f"/api/decisions/{decision_id}/answer",
        headers=_bridge_headers(),
        params={"project_id": project["id"]},
        json={"option_id": "reckless", "selected_text": "Reckless path"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "MC-DECISION-INVALID-OPTION-001"


def test_event_digest_endpoints_are_compact_and_redacted(client) -> None:
    project = _create_project(client, "Digest Demo", "digest-demo")
    db = SessionLocal()
    try:
        db.add_all(
            [
                ProjectEvent(
                    project_id=project["id"],
                    event_type="manager_status",
                    payload_json={"message": "Manager reviewed OPENAI_API_KEY=sk-proj-secret-value"},
                ),
                ProjectEvent(
                    project_id=project["id"],
                    event_type="agent_update",
                    payload_json={"status": "working", "raw_log": "this should never be rendered"},
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    digest = client.get(f"/api/projects/{project['id']}/event-digest", headers=_bridge_headers())
    assert digest.status_code == 200, digest.text
    payload = digest.json()
    assert payload["message_type"] == "event_digest"
    assert "raw_log" not in payload["fallback_markdown"]
    assert "sk-proj-secret-value" not in payload["fallback_markdown"]
    assert "### Manager" in payload["fallback_markdown"]
    assert "### Agents" in payload["fallback_markdown"]


def test_empty_event_digest_and_handoff_summary_are_honest(client) -> None:
    project = _create_project(client, "Quiet Project", "quiet-project")
    db = SessionLocal()
    try:
        for event in db.query(ProjectEvent).filter(ProjectEvent.project_id == project["id"]).all():
            db.delete(event)
        db.commit()
    finally:
        db.close()

    digest = client.get(
        f"/api/projects/{project['id']}/event-digest",
        headers=_bridge_headers(),
        params={"window": "last_5_minutes"},
    )
    assert digest.status_code == 200, digest.text
    assert "No events yet." in digest.json()["fallback_markdown"]

    handoff = client.get(f"/api/projects/{project['id']}/handoff-summary", headers=_bridge_headers())
    assert handoff.status_code == 200, handoff.text
    assert "Validation not run." in handoff.json()["fallback_markdown"]


def test_handoff_summary_uses_recorded_evidence(client) -> None:
    project = _create_project(client, "Handoff Demo", "handoff-demo")
    db = SessionLocal()
    try:
        record = db.get(Project, project["id"])
        assert record is not None
        handoff = EvidenceBasedHandoff(
            project_id=record.id,
            title="Bridge runtime handoff",
            summary="Bridge runtime work is ready for review.",
            what_was_built="- Added pending decision bridge routes\n- Added status and handoff summaries",
            how_to_run="- python -m pytest apps/server/tests/test_bridge_runtime.py",
            how_to_use="Use the Codex bridge routes.",
            tests_run_json=[{"name": "bridge runtime tests", "status": "passed"}],
            known_limitations_json=["MCP transport wiring is still mocked in tests."],
            suggested_next_steps_json=["Connect the MCP layer to these services."],
            evidence_ids_json=[],
            confidence_level="high",
            dry_run=False,
            created_at=utc_now() - timedelta(minutes=1),
        )
        db.add(handoff)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/projects/{project['id']}/handoff-summary", headers=_bridge_headers())
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "bridge runtime tests: passed" in payload["fallback_markdown"]
    assert payload["machine_payload_json"]["dry_run"] is False


def test_safe_mode_endpoints_return_bridge_message(client) -> None:
    project = _create_project(client, "Safe Mode Demo", "safe-mode-demo")

    enabled = client.post(f"/api/projects/{project['id']}/safe-mode", headers=_bridge_headers())
    assert enabled.status_code == 200, enabled.text
    payload = enabled.json()
    assert payload["enabled"] is True
    assert payload["require_all_command_approvals"] is True
    assert payload["bridge_message"]["summary"] == "Safe mode enabled."

    fetched = client.get(f"/api/projects/{project['id']}/safe-mode", headers=_bridge_headers())
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["enabled"] is True


def test_resume_workspace_reports_found_and_not_found_states(client) -> None:
    project = _create_project(client, "Resume Demo", "resume-demo")

    found = client.post(
        "/api/mission-control/resume-workspace",
        headers=_bridge_headers(),
        json={"workspace_path": project["workspace_path"], "attach_policy": "reuse_existing"},
    )
    assert found.status_code == 200, found.text
    assert found.json()["status"] == "found_project_only"

    missing = client.post(
        "/api/mission-control/resume-workspace",
        headers=_bridge_headers(),
        json={"workspace_path": "C:/missing/workspace", "attach_policy": "ask"},
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["status"] == "not_found"


def test_resume_workspace_requires_selection_when_duplicates_exist(client) -> None:
    workspace = Path(sample_workspace("resume-duplicate"))
    workspace.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": "Resume Duplicate",
        "idea": "Duplicate workspace attach",
        "workspace_path": workspace.as_posix(),
        "provider": "codex",
        "runner_mode": "dry_run",
        "manager_mode": "deterministic",
    }
    first = client.post("/api/projects", json=payload)
    assert first.status_code == 200, first.text
    second = client.post("/api/projects", json={**payload, "name": "Resume Duplicate 2"})
    assert second.status_code == 200, second.text

    response = client.post(
        "/api/mission-control/resume-workspace",
        headers=_bridge_headers(),
        json={"workspace_path": workspace.as_posix(), "attach_policy": "reuse_existing"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "needs_selection"
    assert response.json()["user_action_required"] is True


def test_resume_workspace_rejects_non_local_path_inputs(client) -> None:
    response = client.post(
        "/api/mission-control/resume-workspace",
        headers=_bridge_headers(),
        json={"workspace_path": "file:///tmp/not-local", "attach_policy": "reuse_existing"},
    )
    assert response.status_code == 400
    assert "local filesystem" in response.json()["detail"].lower()


def test_bridge_support_endpoints_cover_decisions_snapshots_and_recovery(client) -> None:
    project = _create_project(client, "Bridge Support", "bridge-support")
    db = SessionLocal()
    try:
        db.add(
            DecisionRecord(
                project_id=project["id"],
                decision_type="manager_question",
                title="Keep current architecture",
                decision="preserve",
                reason="User approved the current structure.",
                made_by="user",
                impact_area_json=["requirements"],
                reversible=True,
            )
        )
        db.commit()
    finally:
        db.close()

    ledger = client.get(f"/api/projects/{project['id']}/decision-ledger", headers=_bridge_headers())
    assert ledger.status_code == 200, ledger.text
    assert ledger.json()[0]["title"] == "Keep current architecture"

    locks = client.get(f"/api/projects/{project['id']}/path-locks", headers=_bridge_headers())
    assert locks.status_code == 200, locks.text
    assert isinstance(locks.json(), list)

    contracts = client.get(f"/api/projects/{project['id']}/agent-contracts", headers=_bridge_headers())
    assert contracts.status_code == 200, contracts.text
    assert isinstance(contracts.json(), list)

    snapshot = client.post(
        f"/api/projects/{project['id']}/snapshots",
        headers=_bridge_headers(),
        json={"label": "Before risky change", "description": "Checkpoint before recovery work."},
    )
    assert snapshot.status_code == 200, snapshot.text
    snapshot_payload = snapshot.json()
    assert snapshot_payload["label"] == "Before risky change"

    restore = client.get(
        f"/api/projects/{project['id']}/snapshots/{snapshot_payload['id']}/restore-plan",
        headers=_bridge_headers(),
    )
    assert restore.status_code == 200, restore.text
    assert "summary" in restore.json()

    recovery = client.post(
        f"/api/projects/{project['id']}/recovery-plans",
        headers=_bridge_headers(),
        json={
            "trigger_type": "agent_stuck",
            "trigger_summary": "Verifier has been blocked for too long.",
            "suggested_actions_json": ["pause_project", "ask_user"],
        },
    )
    assert recovery.status_code == 200, recovery.text
    assert recovery.json()["status"] == "proposed"

    recovery_list = client.get(f"/api/projects/{project['id']}/recovery-plans", headers=_bridge_headers())
    assert recovery_list.status_code == 200, recovery_list.text
    assert recovery_list.json()[0]["trigger_type"] == "agent_stuck"
