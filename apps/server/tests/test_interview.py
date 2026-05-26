from __future__ import annotations

from typing import Any

from manager import InterviewTurnPayload, InterviewTurnQuestion, InterviewUnderstandingPayload, service


def _create_project(client, *, name: str = "Adaptive Interview Demo", manager_mode: str = "auto", runner_mode: str = "dry_run") -> dict[str, Any]:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": "Build a local command center that interviews the user and coordinates work.",
            "workspace_path": f"/tmp/{name.lower().replace(' ', '-')}",
            "provider": "codex",
            "runner_mode": runner_mode,
            "manager_mode": manager_mode,
        },
    )
    assert response.status_code == 200
    return response.json()


def _question(category: str, index: int, *, allow_custom_answer: bool = False) -> InterviewTurnQuestion:
    return InterviewTurnQuestion(
        question=f"Question {index} for {category}?",
        why=f"The manager needs {category} clarified.",
        category=category,
        impact="medium",
        options=[
            {"id": f"option_{index}_a", "label": "Option A", "description": "First path."},
            {"id": f"option_{index}_b", "label": "Option B", "description": "Second path."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager recommend."},
        ],
        allow_custom_answer=allow_custom_answer,
        affects=["planning", "validation"],
    )


def _turn(summary: str, questions: list[InterviewTurnQuestion], *, more_questions_needed: bool, stop_reason: str | None = None) -> InterviewTurnPayload:
    return InterviewTurnPayload(
        understanding=InterviewUnderstandingPayload(
            summary=summary,
            known_facts={"project": [{"label": "Title", "value": "Adaptive Interview Demo"}]},
            unknowns={"priority": ["Unknowns still exist."]} if more_questions_needed else {},
            assumptions=[],
            constraints=["Local-first"],
            confidence_by_category={"product goal": 0.55},
        ),
        next_questions=questions,
        more_questions_needed=more_questions_needed,
        stop_reason=stop_reason,
    )


def test_zero_budget_interview_creates_assumptions_and_completes(client) -> None:
    project = _create_project(client)
    session = client.post(f"/api/projects/{project['id']}/interview/start", json={"question_budget": 0}).json()

    assert session["status"] == "completed"
    assert session["question_budget"] == 0
    assert session["questions_asked"] == 0
    assert session["questions"] == []
    assert "assumptions" in session["stop_reason"].lower()

    understanding = client.get(f"/api/projects/{project['id']}/understanding").json()
    assert understanding["assumptions_json"]
    assert "zero" in understanding["summary"].lower()


def test_manager_generated_questions_are_project_scoped_and_rich(client, monkeypatch) -> None:
    project = _create_project(client, runner_mode="auto")

    async def fake_resolve(*args, **kwargs):
        return (
            _turn(
                "Manager summary for the project.",
                [
                    _question("product goal", 1),
                    _question("target users", 2),
                    _question("MVP scope", 3),
                ],
                more_questions_needed=True,
            ),
            "codex",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve)

    response = client.post(f"/api/projects/{project['id']}/interview/start", json={"question_budget": 20})
    assert response.status_code == 200
    session = response.json()

    assert session["status"] == "in_progress"
    assert session["questions_asked"] == 3
    assert session["questions_generated"] == 3
    assert session["questions_answered"] == 0
    assert session["pending_questions"] == 3
    assert session["generation_budget_remaining"] == 17
    assert session["generation_sources"] == ["manager_ai"]
    assert all(question["project_id"] == project["id"] for question in session["questions"])
    assert all(question["why"] for question in session["questions"])
    assert all(question["category"] for question in session["questions"])
    assert all(question["impact"] == "medium" for question in session["questions"])


def test_answer_updates_understanding_and_stores_custom_answer(client, monkeypatch) -> None:
    project = _create_project(client, runner_mode="auto")

    async def fake_resolve(*args, **kwargs):
        return (
            _turn(
                "Manager summary for the project.",
                [_question("target users", 1, allow_custom_answer=True)],
                more_questions_needed=False,
                stop_reason="One answer is enough here.",
            ),
            "codex",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve)

    session = client.post(f"/api/projects/{project['id']}/interview/start", json={"question_budget": 6}).json()
    question = session["questions"][0]
    answered = client.post(
        f"/api/interview/questions/{question['id']}/answer",
        json={
            "project_id": project["id"],
            "option_id": question["options"][0]["id"],
            "selected_text": question["options"][0]["label"],
            "custom_answer": "The first version should help both engineers and reviewers.",
        },
    ).json()

    assert answered["status"] == "completed"
    assert answered["stopped_early"] is True
    assert answered["questions_generated"] == 1
    assert answered["questions_answered"] == 1
    assert answered["pending_questions"] == 0
    assert answered["questions"][0]["custom_answer"] == "The first version should help both engineers and reviewers."

    understanding = client.get(f"/api/projects/{project['id']}/understanding").json()
    assert "target users" in understanding["known_facts_json"]


def test_generate_next_respects_budget_and_filters_extra_questions(client, monkeypatch) -> None:
    project = _create_project(client, runner_mode="auto")
    calls = {"count": 0}

    async def fake_resolve(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return (
                _turn(
                    "Initial project summary.",
                    [
                        _question("product goal", 1),
                        _question("target users", 2),
                        _question("MVP scope", 3),
                        _question("core features", 4),
                        _question("testing/validation", 5),
                    ],
                    more_questions_needed=True,
                ),
                "codex",
            )
        return (
            _turn(
                "Updated summary after answers.",
                [
                    _question("platform/runtime", 6),
                    _question("handoff format", 7),
                    _question("future expansion", 8),
                ],
                more_questions_needed=True,
            ),
            "codex",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve)

    session = client.post(f"/api/projects/{project['id']}/interview/start", json={"question_budget": 7}).json()
    assert session["questions_asked"] == 5

    for question in session["questions"]:
        session = client.post(
            f"/api/interview/questions/{question['id']}/answer",
            json={
                "project_id": project["id"],
                "option_id": question["options"][0]["id"],
                "selected_text": question["options"][0]["label"],
            },
        ).json()

    next_session = client.post(f"/api/projects/{project['id']}/interview/generate-next").json()
    pending = [question for question in next_session["questions"] if question["status"] == "pending"]

    assert next_session["questions_asked"] == 7
    assert len(pending) == 2


def test_fallback_is_honestly_labeled_when_live_generation_fails(client, monkeypatch) -> None:
    project = _create_project(client, manager_mode="provider", runner_mode="auto")

    async def fail_runner(*args, **kwargs):
        raise RuntimeError("runner unavailable")

    monkeypatch.setattr(service.runners, "get_runner_for_settings", fail_runner)

    session = client.post(f"/api/projects/{project['id']}/interview/start", json={"question_budget": 6}).json()

    assert session["questions"]
    assert "fallback_generated" in session["generation_sources"]
    assert all(question["question_source"] == "fallback_generated" for question in session["questions"])


def test_canonical_answer_route_enforces_project_scope(client, monkeypatch) -> None:
    project_one = _create_project(client, name="Scope One", runner_mode="auto")
    project_two = _create_project(client, name="Scope Two", runner_mode="auto")

    async def fake_resolve(*args, **kwargs):
        return (
            _turn("Scoped summary.", [_question("product goal", 1)], more_questions_needed=True),
            "codex",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve)

    session = client.post(f"/api/projects/{project_one['id']}/interview/start", json={"question_budget": 6}).json()
    question = session["questions"][0]
    bad_answer = client.post(
        f"/api/interview/questions/{question['id']}/answer",
        json={
            "project_id": project_two["id"],
            "option_id": question["options"][0]["id"],
            "selected_text": question["options"][0]["label"],
        },
    )

    assert bad_answer.status_code == 404 or bad_answer.status_code == 400


def test_global_answer_route_canonicalizes_selected_text(client, monkeypatch) -> None:
    project = _create_project(client, name="Canonical Answer", runner_mode="auto")

    async def fake_resolve(*args, **kwargs):
        return (
            _turn("Scoped summary.", [_question("product goal", 1)], more_questions_needed=True),
            "codex",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve)

    session = client.post(f"/api/projects/{project['id']}/interview/start", json={"question_budget": 6}).json()
    question = session["questions"][0]
    answer = client.post(
        f"/api/interview/questions/{question['id']}/answer",
        json={
            "project_id": project["id"],
            "option_id": question["options"][0]["id"],
            "selected_text": "Fabricated answer text",
        },
    )

    assert answer.status_code == 200
    answered_question = answer.json()["questions"][0]
    assert answered_question["selected_option_id"] == question["options"][0]["id"]
    assert answered_question["selected_text"] == question["options"][0]["label"]


def test_global_answer_route_rejects_invalid_option_id(client, monkeypatch) -> None:
    project = _create_project(client, name="Invalid Global Answer", runner_mode="auto")

    async def fake_resolve(*args, **kwargs):
        return (
            _turn("Scoped summary.", [_question("product goal", 1)], more_questions_needed=True),
            "codex",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve)

    session = client.post(f"/api/projects/{project['id']}/interview/start", json={"question_budget": 6}).json()
    question = session["questions"][0]
    answer = client.post(
        f"/api/interview/questions/{question['id']}/answer",
        json={
            "project_id": project["id"],
            "option_id": "invented_option",
            "selected_text": question["options"][0]["label"],
        },
    )

    assert answer.status_code == 400
    assert "selected option" in answer.json()["detail"].lower()
