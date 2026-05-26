from __future__ import annotations

import pytest

from conftest import sample_workspace
from db import SessionLocal, init_db
from manager import service
from models import Agent, Project, Task


def _seed_project_pair() -> tuple[int, int, int]:
    init_db()
    db = SessionLocal()
    try:
        project_one = Project(
            name="Review Gate Tasks One",
            idea="Keep review gate task refs scoped.",
            workspace_path=sample_workspace("review-gate-task-one"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        project_two = Project(
            name="Review Gate Tasks Two",
            idea="Provide foreign task refs.",
            workspace_path=sample_workspace("review-gate-task-two"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add_all([project_one, project_two])
        db.flush()

        agent_one = Agent(
            project_id=project_one.id,
            name="Worker One",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project_one.workspace_path,
        )
        agent_two = Agent(
            project_id=project_two.id,
            name="Worker Two",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project_two.workspace_path,
        )
        db.add_all([agent_one, agent_two])
        db.flush()

        foreign_task = Task(
            project_id=project_two.id,
            assigned_agent_id=agent_two.id,
            title="Foreign task",
            goal="Trigger invalid review gate task refs.",
            scope="Cross-project fixture.",
            agent_role="Implementation",
            milestone="Validation",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Stay scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(foreign_task)
        db.commit()
        return project_one.id, project_two.id, foreign_task.id
    finally:
        db.close()


def test_create_review_gate_rejects_foreign_and_missing_task() -> None:
    project_one_id, _, foreign_task_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None

        with pytest.raises(ValueError, match="related task"):
            service.create_review_gate(
                db,
                scoped_project,
                {"gate_type": "quality", "title": "Bad foreign task", "related_task_id": foreign_task_id},
            )

        with pytest.raises(ValueError, match="related task"):
            service.create_review_gate(
                db,
                scoped_project,
                {"gate_type": "quality", "title": "Bad missing task", "related_task_id": 999_999},
            )
    finally:
        db.close()


def test_update_review_gate_rejects_foreign_and_missing_task() -> None:
    project_one_id, _, foreign_task_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None

        gate = service.create_review_gate(db, scoped_project, {"gate_type": "quality", "title": "Scoped gate"})

        with pytest.raises(ValueError, match="related task"):
            service.update_review_gate(db, gate.id, {"related_task_id": foreign_task_id})

        with pytest.raises(ValueError, match="related task"):
            service.update_review_gate(db, gate.id, {"related_task_id": 999_998})
    finally:
        db.close()
