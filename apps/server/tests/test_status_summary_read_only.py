from __future__ import annotations

from db import SessionLocal, init_db
from models import Project, ProjectConfidence, ReviewGate
from tests.conftest import sample_workspace


def test_project_status_summary_stays_read_only_for_health_support(client, bridge_headers) -> None:
    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Status Summary Audit",
            idea="Read routes should not mutate health support tables.",
            workspace_path=sample_workspace("status-summary-read-only"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        before_confidence = db.query(ProjectConfidence).filter(ProjectConfidence.project_id == project.id).count()
        before_review_gates = db.query(ReviewGate).filter(ReviewGate.project_id == project.id).count()

        response = client.get(f"/api/projects/{project.id}/status-summary", headers=bridge_headers)
        assert response.status_code == 200

        after_confidence = db.query(ProjectConfidence).filter(ProjectConfidence.project_id == project.id).count()
        after_review_gates = db.query(ReviewGate).filter(ReviewGate.project_id == project.id).count()

        assert after_confidence == before_confidence == 0
        assert after_review_gates == before_review_gates == 0
    finally:
        db.close()
