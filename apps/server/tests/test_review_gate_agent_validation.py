from __future__ import annotations

import pytest

from conftest import sample_workspace
from db import SessionLocal, init_db
from manager import service
from models import Agent, Project


def _seed_project_pair() -> tuple[int, int]:
    init_db()
    db = SessionLocal()
    try:
        project_one = Project(
            name="Review Gate Agents One",
            idea="Keep review gate agent refs scoped.",
            workspace_path=sample_workspace("review-gate-agent-one"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        project_two = Project(
            name="Review Gate Agents Two",
            idea="Provide foreign agent refs.",
            workspace_path=sample_workspace("review-gate-agent-two"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add_all([project_one, project_two])
        db.flush()

        foreign_agent = Agent(
            project_id=project_two.id,
            name="Worker Two",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project_two.workspace_path,
        )
        db.add(foreign_agent)
        db.commit()
        return project_one.id, foreign_agent.id
    finally:
        db.close()


def test_create_review_gate_rejects_foreign_and_missing_agent() -> None:
    project_one_id, foreign_agent_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None

        with pytest.raises(ValueError, match="related agent"):
            service.create_review_gate(
                db,
                scoped_project,
                {"gate_type": "quality", "title": "Bad foreign agent", "related_agent_id": foreign_agent_id},
            )

        with pytest.raises(ValueError, match="related agent"):
            service.create_review_gate(
                db,
                scoped_project,
                {"gate_type": "quality", "title": "Bad missing agent", "related_agent_id": 999_999},
            )
    finally:
        db.close()


def test_update_review_gate_rejects_foreign_and_missing_agent() -> None:
    project_one_id, foreign_agent_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None

        gate = service.create_review_gate(db, scoped_project, {"gate_type": "quality", "title": "Scoped gate"})

        with pytest.raises(ValueError, match="related agent"):
            service.update_review_gate(db, gate.id, {"related_agent_id": foreign_agent_id})

        with pytest.raises(ValueError, match="related agent"):
            service.update_review_gate(db, gate.id, {"related_agent_id": 999_998})
    finally:
        db.close()
