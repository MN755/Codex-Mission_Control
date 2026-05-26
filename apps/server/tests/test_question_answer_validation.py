from __future__ import annotations

from db import SessionLocal
from models import ManagerQuestion
from conftest import sample_workspace


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


def _seed_question(project_id: int, prompt: str) -> int:
    db = SessionLocal()
    try:
        question = ManagerQuestion(
            project_id=project_id,
            question=prompt,
            options_json=[{"id": "safe", "label": "Safe path"}],
            impact="medium",
            status="pending",
        )
        db.add(question)
        db.commit()
        return question.id
    finally:
        db.close()


def test_project_action_rejects_invalid_manager_question_option(client) -> None:
    project = _create_project(client, "Action Validation", "action-validation")
    question_id = _seed_question(project["id"], "Choose a path?")

    response = client.post(
        f"/api/projects/{project['id']}/actions/question-{question_id}/resolve",
        json={"decision": "choose_option", "option_id": "bogus", "selected_text": "Bogus"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Question option is not valid."


def test_direct_question_answer_canonicalizes_selected_text(client) -> None:
    project = _create_project(client, "Direct Canonicalization", "direct-canonicalization")
    question_id = _seed_question(project["id"], "Choose a direct path?")

    response = client.post(
        f"/api/questions/{question_id}/answer",
        json={"project_id": project["id"], "option_id": "safe", "selected_text": "Destroy prod"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["selected_option_id"] == "safe"
    assert response.json()["selected_text"] == "Safe path"


def test_project_action_canonicalizes_selected_text(client) -> None:
    project = _create_project(client, "Action Canonicalization", "action-canonicalization")
    question_id = _seed_question(project["id"], "Choose an action path?")

    response = client.post(
        f"/api/projects/{project['id']}/actions/question-{question_id}/resolve",
        json={"decision": "choose_option", "option_id": "safe", "selected_text": "Destroy prod"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["selected_option_id"] == "safe"
    assert response.json()["selected_text"] == "Safe path"


def test_pending_decision_answer_canonicalizes_selected_text(client) -> None:
    project = _create_project(client, "Decision Canonicalization", "decision-canonicalization")
    _seed_question(project["id"], "Choose a bridge path?")

    decisions = client.get(f"/api/projects/{project['id']}/pending-decisions")
    assert decisions.status_code == 200, decisions.text
    decision_id = decisions.json()[0]["id"]

    response = client.post(
        f"/api/decisions/{decision_id}/answer",
        params={"project_id": project["id"]},
        json={"option_id": "safe", "selected_text": "Destroy prod"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["decision"]["answer_json"]["option_id"] == "safe"
    assert payload["decision"]["answer_json"]["selected_text"] == "Safe path"
