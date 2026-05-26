from __future__ import annotations

from db import SessionLocal
from models import InterviewQuestion, InterviewSession
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


def _seed_interview_question(project_id: int) -> int:
    db = SessionLocal()
    try:
        session = InterviewSession(
            project_id=project_id,
            question_count=1,
            question_budget=1,
            questions_asked=1,
            current_index=1,
            status="in_progress",
            manager_mode="deterministic",
            stopped_early=False,
            confidence_json={},
            known_facts_json={},
            unknowns_json={},
        )
        db.add(session)
        db.flush()
        question = InterviewQuestion(
            session_id=session.id,
            project_id=project_id,
            index=1,
            question="Should Mission Control continue?",
            impact="medium",
            options_json=[{"id": "yes", "label": "Yes", "description": "affirm"}],
            allow_custom_answer=False,
            status="pending",
        )
        db.add(question)
        db.commit()
        return question.id
    finally:
        db.close()


def test_project_interview_answer_rejects_invalid_option(client) -> None:
    project = _create_project(client, "Interview Validation", "interview-validation")
    question_id = _seed_interview_question(project["id"])

    response = client.post(
        f"/api/projects/{project['id']}/interview/answer",
        json={"question_id": question_id, "option_id": "bogus", "selected_text": "Bogus"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Interview option is not valid."


def test_project_interview_answer_canonicalizes_selected_text(client) -> None:
    project = _create_project(client, "Interview Canonicalization", "interview-canonicalization")
    question_id = _seed_interview_question(project["id"])

    response = client.post(
        f"/api/projects/{project['id']}/interview/answer",
        json={"question_id": question_id, "option_id": "yes", "selected_text": "Nope"},
    )

    assert response.status_code == 200, response.text
    answered = response.json()["questions"][0]
    assert answered["selected_option_id"] == "yes"
    assert answered["selected_text"] == "Yes"
