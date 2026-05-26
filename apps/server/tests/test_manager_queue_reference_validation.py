from __future__ import annotations

import pytest

from conftest import sample_workspace
from db import SessionLocal, init_db
from manager import MissionControlService
from models import Agent, Project, Task


def _seed_projects() -> tuple[Project, Project, Agent, Task]:
    init_db()
    db = SessionLocal()
    try:
        primary = Project(
            name="Primary",
            idea="Primary idea",
            workspace_path=sample_workspace("queue-primary"),
            status="draft",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        foreign = Project(
            name="Foreign",
            idea="Foreign idea",
            workspace_path=sample_workspace("queue-foreign"),
            status="draft",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add_all([primary, foreign])
        db.flush()
        foreign_agent = Agent(
            project_id=foreign.id,
            name="Foreign Agent",
            role="Worker",
            kind="worker",
            status="idle",
            workspace_path=foreign.workspace_path,
        )
        foreign_task = Task(
            project_id=foreign.id,
            title="Foreign Task",
            goal="Goal",
            scope="Scope",
            agent_role="Worker",
            milestone="M1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=1,
        )
        db.add_all([foreign_agent, foreign_task])
        db.commit()
        db.refresh(primary)
        db.refresh(foreign)
        db.refresh(foreign_agent)
        db.refresh(foreign_task)
        return primary, foreign, foreign_agent, foreign_task
    finally:
        db.close()


def test_record_manager_message_rejects_invalid_refs() -> None:
    service = MissionControlService()
    primary, _foreign, foreign_agent, foreign_task = _seed_projects()

    db = SessionLocal()
    try:
        primary = db.get(Project, primary.id)
        assert primary is not None

        with pytest.raises(ValueError, match="does not belong to this project"):
            service._record_manager_message(
                db,
                primary,
                role="system",
                message_type="system_notice",
                content_markdown="bad refs",
                related_agent_id=foreign_agent.id,
            )

        with pytest.raises(ValueError, match="not found"):
            service._record_manager_message(
                db,
                primary,
                role="system",
                message_type="system_notice",
                content_markdown="bad refs",
                related_task_id=999,
            )

        with pytest.raises(ValueError, match="does not belong to this project"):
            service._record_manager_message(
                db,
                primary,
                role="system",
                message_type="system_notice",
                content_markdown="bad refs",
                related_task_id=foreign_task.id,
            )
    finally:
        db.close()


def test_create_question_rejects_invalid_refs() -> None:
    service = MissionControlService()
    primary, _foreign, foreign_agent, foreign_task = _seed_projects()

    db = SessionLocal()
    try:
        primary = db.get(Project, primary.id)
        assert primary is not None

        with pytest.raises(ValueError, match="does not belong to this project"):
            service._create_question(
                db,
                primary,
                question="What now?",
                options_json=[{"id": "a", "label": "A"}],
                impact="medium",
                related_agent_id=foreign_agent.id,
            )

        with pytest.raises(ValueError, match="not found"):
            service._create_question(
                db,
                primary,
                question="What now?",
                options_json=[{"id": "a", "label": "A"}],
                impact="medium",
                related_task_id=999,
            )

        with pytest.raises(ValueError, match="does not belong to this project"):
            service._create_question(
                db,
                primary,
                question="What now?",
                options_json=[{"id": "a", "label": "A"}],
                impact="medium",
                related_task_id=foreign_task.id,
            )
    finally:
        db.close()
