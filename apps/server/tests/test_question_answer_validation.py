from __future__ import annotations

import os
from pathlib import Path

import pytest

from bridge_formatter import format_status_summary_message
from bridge_messages import bridge_runtime_service
from conftest import sample_workspace, wait_for
from db import SessionLocal
from models import ManagerQuestion, PendingDecision, Project, utc_now


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


def _seed_manager_question(project_id: int, *, question: str = "Which path should Mission Control take?") -> int:
    db = SessionLocal()
    try:
        record = db.get(Project, project_id)
        assert record is not None
        pending = ManagerQuestion(
            project_id=record.id,
            question=question,
            options_json=[{"id": "safe", "label": "Safe path"}, {"id": "fast", "label": "Fast path"}],
            impact="medium",
            status="pending",
        )
        db.add(pending)
        db.commit()
        return pending.id
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _fast_status_summary(monkeypatch) -> None:
    async def fake_status_summary(db, project, orchestration=None):
        return format_status_summary_message(
            message_id=f"status-{project.id}",
            project_id=project.id,
            orchestration_id=orchestration.id if orchestration is not None else None,
            title="Mission Control status",
            summary="Status: fast question-answer test stub.",
            project_name=project.name,
            manager_status="Ready to continue.",
            mode="dry_run / deterministic",
            swarm="not planned",
            user_action_needed="no",
            current_work=["Fast question-answer test stub."],
            waiting_on_you=[],
            next_expected_step="Continue.",
            risk_level=None,
            created_at=utc_now(),
            orchestration_status=orchestration.status if orchestration is not None else project.status,
            current_blockers=[],
            handoff_readiness=project.handoff_status,
            active_agent_count=0,
            model_advisories=[],
        )

    monkeypatch.setattr(bridge_runtime_service, "get_status_summary", fake_status_summary)


def test_direct_question_answer_rejects_invalid_option(client) -> None:
    project = _create_project(client, "Direct Question Invalid", "direct-question-invalid")
    question_id = _seed_manager_question(project["id"])

    response = client.post(
        f"/api/projects/{project['id']}/questions/{question_id}/answer",
        json={"option_id": "bogus", "selected_text": "Bogus"},
    )

    assert response.status_code == 400
    assert "option id is not valid" in response.json()["detail"].lower()


def test_direct_question_answer_requires_project_id(client) -> None:
    project = _create_project(client, "Direct Question Scope", "direct-question-scope")
    question_id = _seed_manager_question(project["id"])

    response = client.post(
        f"/api/questions/{question_id}/answer",
        json={"option_id": "safe", "selected_text": "Safe path"},
    )

    assert response.status_code == 400
    assert "project_id is required" in response.json()["detail"].lower()


def test_direct_question_answer_canonicalizes_selected_text(client) -> None:
    project = _create_project(client, "Direct Question Canonical", "direct-question-canonical")
    question_id = _seed_manager_question(project["id"])

    response = client.post(
        f"/api/projects/{project['id']}/questions/{question_id}/answer",
        json={"option_id": "safe", "selected_text": "Destroy prod"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["selected_option_id"] == "safe"
    assert response.json()["selected_text"] == "Safe path"


def test_project_scoped_question_answer_rejects_mismatched_embedded_project_id(client) -> None:
    project = _create_project(client, "Direct Question Mismatch", "direct-question-mismatch")
    question_id = _seed_manager_question(project["id"])

    response = client.post(
        f"/api/projects/{project['id']}/questions/{question_id}/answer",
        json={"project_id": project["id"] + 1, "option_id": "safe", "selected_text": "Safe path"},
    )

    assert response.status_code == 404
    assert "question not found in this project" in response.json()["detail"].lower()


def test_project_action_question_resolve_rejects_invalid_option(client) -> None:
    project = _create_project(client, "Project Action Invalid", "project-action-invalid")
    question_id = _seed_manager_question(project["id"])

    response = client.post(
        f"/api/projects/{project['id']}/actions/question-{question_id}/resolve",
        json={"decision": "choose_option", "option_id": "bogus", "selected_text": "Bogus"},
    )

    assert response.status_code == 400
    assert "option id is not valid" in response.json()["detail"].lower()


def test_project_action_question_resolve_canonicalizes_selected_text(client) -> None:
    project = _create_project(client, "Project Action Canonical", "project-action-canonical")
    question_id = _seed_manager_question(project["id"])

    response = client.post(
        f"/api/projects/{project['id']}/actions/question-{question_id}/resolve",
        json={"decision": "choose_option", "option_id": "safe", "selected_text": "Destroy prod"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["selected_option_id"] == "safe"
    assert response.json()["selected_text"] == "Safe path"


def test_pending_decision_manager_question_canonicalizes_selected_text(client) -> None:
    project = _create_project(client, "Pending Decision Canonical", "pending-decision-canonical")
    _seed_manager_question(project["id"])

    decisions = client.get(f"/api/projects/{project['id']}/pending-decisions", headers=_bridge_headers()).json()
    decision_id = decisions[0]["id"]
    response = client.post(
        f"/api/decisions/{decision_id}/answer",
        headers=_bridge_headers(),
        params={"project_id": project["id"]},
        json={"option_id": "safe", "selected_text": "Destroy prod"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["decision"]["answer_json"]["option_id"] == "safe"
    assert payload["decision"]["answer_json"]["selected_text"] == "Safe path"

    db = SessionLocal()
    try:
        record = db.get(PendingDecision, decision_id)
        assert record is not None
        assert dict(record.answer_json or {})["selected_text"] == "Safe path"
    finally:
        db.close()
