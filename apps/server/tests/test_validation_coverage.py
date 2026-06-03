from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from conftest import sample_workspace
from db import SessionLocal
from models import Project, ValidationCoverageArea, utc_now


def _create_project(client, name: str, workspace_name: str) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"{name} idea",
            "workspace_path": sample_workspace(workspace_name),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _seed_duplicate_coverage_rows(project_id: int) -> None:
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        assert project is not None
        older = utc_now() - timedelta(days=1)
        newer = utc_now()
        db.add_all(
            [
                ValidationCoverageArea(
                    project_id=project_id,
                    area="frontend",
                    coverage_status="planned",
                    evidence_summary="Older row",
                    related_validation_step_id=None,
                    last_updated=older,
                ),
                ValidationCoverageArea(
                    project_id=project_id,
                    area="frontend",
                    coverage_status="validated",
                    evidence_summary="Newer row",
                    related_validation_step_id=None,
                    last_updated=newer,
                ),
            ]
        )
        project.updated_at = newer
        db.commit()
    finally:
        db.close()


def test_validation_coverage_get_dedupes_duplicate_area_rows(client) -> None:
    project = _create_project(client, "Coverage Dedupe Read", "coverage-dedupe-read")
    _seed_duplicate_coverage_rows(project["id"])

    response = client.get(f"/api/projects/{project['id']}/validation-coverage")
    assert response.status_code == 200, response.text
    payload = [item for item in response.json() if item["area"] == "frontend"]
    assert len(payload) == 1
    assert payload[0]["coverage_status"] == "validated"
    assert payload[0]["evidence_summary"] == "Newer row"


def test_validation_coverage_recompute_cleans_duplicate_area_rows(client) -> None:
    project = _create_project(client, "Coverage Dedupe Recompute", "coverage-dedupe-recompute")
    _seed_duplicate_coverage_rows(project["id"])

    response = client.post(f"/api/projects/{project['id']}/validation-coverage/recompute")
    assert response.status_code == 200, response.text

    db = SessionLocal()
    try:
        rows = list(
            db.scalars(
                select(ValidationCoverageArea)
                .where(ValidationCoverageArea.project_id == project["id"], ValidationCoverageArea.area == "frontend")
                .order_by(ValidationCoverageArea.id.asc())
            )
        )
        assert len(rows) == 1
    finally:
        db.close()
