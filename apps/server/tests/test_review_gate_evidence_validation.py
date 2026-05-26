from __future__ import annotations

import pytest

from conftest import sample_workspace
from db import SessionLocal, init_db
from manager import service
from models import HandoffEvidence, Project


def _seed_project_pair() -> tuple[int, int]:
    init_db()
    db = SessionLocal()
    try:
        project_one = Project(
            name="Review Gate Evidence One",
            idea="Keep review gate evidence scoped.",
            workspace_path=sample_workspace("review-gate-evidence-one"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        project_two = Project(
            name="Review Gate Evidence Two",
            idea="Provide foreign evidence refs.",
            workspace_path=sample_workspace("review-gate-evidence-two"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add_all([project_one, project_two])
        db.flush()

        foreign_evidence = HandoffEvidence(
            project_id=project_two.id,
            evidence_type="test",
            claim="Foreign evidence",
            summary="Cross-project evidence fixture.",
            source_path="reports/foreign.txt",
            status="fresh",
        )
        db.add(foreign_evidence)
        db.commit()
        return project_one.id, foreign_evidence.id
    finally:
        db.close()


def test_create_review_gate_rejects_foreign_and_missing_evidence() -> None:
    project_one_id, foreign_evidence_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None

        with pytest.raises(ValueError, match="evidence"):
            service.create_review_gate(
                db,
                scoped_project,
                {"gate_type": "quality", "title": "Bad foreign evidence", "evidence_ids_json": [foreign_evidence_id]},
            )

        with pytest.raises(ValueError, match="evidence"):
            service.create_review_gate(
                db,
                scoped_project,
                {"gate_type": "quality", "title": "Bad missing evidence", "evidence_ids_json": [999_999]},
            )
    finally:
        db.close()


def test_update_review_gate_rejects_foreign_and_missing_evidence() -> None:
    project_one_id, foreign_evidence_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None

        gate = service.create_review_gate(db, scoped_project, {"gate_type": "quality", "title": "Scoped gate"})

        with pytest.raises(ValueError, match="evidence"):
            service.update_review_gate(db, gate.id, {"evidence_ids_json": [foreign_evidence_id]})

        with pytest.raises(ValueError, match="evidence"):
            service.update_review_gate(db, gate.id, {"evidence_ids_json": [999_998]})
    finally:
        db.close()
