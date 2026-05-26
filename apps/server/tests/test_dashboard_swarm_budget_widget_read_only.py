from __future__ import annotations

from db import SessionLocal, init_db
from models import Project, ProjectConfidence, ReviewGate
from tests.conftest import sample_workspace


def test_swarm_budget_overview_widget_data_stays_read_only(client, bridge_headers) -> None:
    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Swarm Budget Widget Audit",
            idea="Dashboard widget reads should not seed support rows.",
            workspace_path=sample_workspace("dashboard-swarm-budget-widget"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        created = client.post(
            "/api/widgets/instances",
            headers=bridge_headers,
            json={"scope": "dashboard", "widget_type": "Swarm Budget Overview", "area": "dashboard_main"},
        )
        assert created.status_code == 200
        instance_id = created.json()["id"]

        before_confidence = db.query(ProjectConfidence).filter(ProjectConfidence.project_id == project.id).count()
        before_review_gates = db.query(ReviewGate).filter(ReviewGate.project_id == project.id).count()

        response = client.get(f"/api/widgets/instances/{instance_id}/data", headers=bridge_headers)
        assert response.status_code == 200

        after_confidence = db.query(ProjectConfidence).filter(ProjectConfidence.project_id == project.id).count()
        after_review_gates = db.query(ReviewGate).filter(ReviewGate.project_id == project.id).count()

        assert after_confidence == before_confidence == 0
        assert after_review_gates == before_review_gates == 0
    finally:
        db.close()
