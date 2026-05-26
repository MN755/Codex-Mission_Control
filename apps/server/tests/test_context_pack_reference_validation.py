from __future__ import annotations

import pytest

from conftest import sample_workspace
from context_packs.service import context_pack_service
from db import SessionLocal, init_db
from models import Agent, Project, Task


def _seed_projects() -> tuple[Project, Agent, Task]:
    init_db()
    db = SessionLocal()
    try:
        primary = Project(
            name="Primary",
            idea="Primary idea",
            workspace_path=sample_workspace("context-pack-primary"),
            status="draft",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        foreign = Project(
            name="Foreign",
            idea="Foreign idea",
            workspace_path=sample_workspace("context-pack-foreign"),
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
        db.refresh(foreign_agent)
        db.refresh(foreign_task)
        return primary, foreign_agent, foreign_task
    finally:
        db.close()


def test_build_context_pack_rejects_nonexistent_refs() -> None:
    primary, _foreign_agent, _foreign_task = _seed_projects()

    db = SessionLocal()
    try:
        primary = db.get(Project, primary.id)
        assert primary is not None
        with pytest.raises(ValueError, match="agent not found"):
            context_pack_service.build_context_pack(db, primary, agent_id=999)
        with pytest.raises(ValueError, match="task not found"):
            context_pack_service.build_context_pack(db, primary, task_id=999)
    finally:
        db.close()


def test_build_context_pack_rejects_foreign_refs() -> None:
    primary, foreign_agent, foreign_task = _seed_projects()

    db = SessionLocal()
    try:
        primary = db.get(Project, primary.id)
        assert primary is not None
        with pytest.raises(ValueError, match="does not belong to this project"):
            context_pack_service.build_context_pack(db, primary, agent_id=foreign_agent.id)
        with pytest.raises(ValueError, match="does not belong to this project"):
            context_pack_service.build_context_pack(db, primary, task_id=foreign_task.id)
    finally:
        db.close()
