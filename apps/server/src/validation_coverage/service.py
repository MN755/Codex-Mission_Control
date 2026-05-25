from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AgentPerformanceRecord, Project, RepoIntelligenceSummary, Task, ValidationCoverageArea, ValidationRecipe


VALIDATION_AREAS = [
    "frontend",
    "backend",
    "database",
    "auth",
    "security",
    "docs",
    "deployment",
    "integrations",
    "tests",
    "packaging",
]


class ValidationCoverageService:
    def list_coverage(self, db: Session, project: Project) -> list[ValidationCoverageArea]:
        return list(
            db.scalars(
                select(ValidationCoverageArea)
                .where(ValidationCoverageArea.project_id == project.id)
                .order_by(ValidationCoverageArea.area.asc(), ValidationCoverageArea.id.asc())
            )
        )

    def _upsert_area(self, db: Session, project_id: int, area: str) -> ValidationCoverageArea:
        record = db.scalar(
            select(ValidationCoverageArea)
            .where(ValidationCoverageArea.project_id == project_id, ValidationCoverageArea.area == area)
            .order_by(ValidationCoverageArea.id.asc())
        )
        if record is None:
            record = ValidationCoverageArea(project_id=project_id, area=area)
            db.add(record)
            db.flush()
        return record

    def _compute_area_payloads(self, db: Session, project: Project) -> list[dict[str, Any]]:
        existing = {
            item.area: item
            for item in self.list_coverage(db, project)
        }
        recipe_id = None
        recipes = list(db.scalars(select(ValidationRecipe).where(ValidationRecipe.project_id == project.id).order_by(ValidationRecipe.id.asc())))
        if recipes:
            recipe_id = recipes[0].id
        repo = project.repo_intelligence
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.id.asc())))
        performance = list(
            db.scalars(
                select(AgentPerformanceRecord)
                .where(AgentPerformanceRecord.project_id == project.id)
                .order_by(AgentPerformanceRecord.created_at.desc(), AgentPerformanceRecord.id.desc())
            )
        )
        project_text = f"{project.name}\n{project.idea}\n{project.workspace_path}".lower()
        done_tasks = [task for task in tasks if task.status == "done"]
        task_titles = " ".join(task.title.lower() for task in tasks)
        evidence_lines = {
            "frontend": "Frontend paths or UI tasks exist.",
            "backend": "Backend paths or service tasks exist.",
            "database": "Data or database paths exist.",
            "auth": "Auth/security language appears in the project scope.",
            "security": "Security-sensitive behavior appears in scope or reviews.",
            "docs": "Docs or README work exists.",
            "deployment": "Deployment or packaging files appear in the repo.",
            "integrations": "Integration or connector work appears in scope.",
            "tests": "Tests or validation recipes exist.",
            "packaging": "Packaging or desktop distribution work appears in scope.",
        }

        def repo_has(token: str) -> bool:
            if repo is None:
                return False
            return any(token in item.lower() for item in (repo.important_folders_json or []) + (repo.deployment_config_json or []) + (repo.docs_found_json or []))

        def infer_status(area: str) -> tuple[str, str | None, int | None]:
            if area == "frontend":
                if any(path for task in done_tasks for path in task.allowed_paths_json if "dashboard" in path.lower() or "src" == path.lower()):
                    return "validated", "Frontend task completed with explicit task ownership.", recipe_id
                if "react" in project_text or repo_has("dashboard"):
                    return "planned", evidence_lines[area], recipe_id
            if area == "backend":
                if any(path for task in done_tasks for path in task.allowed_paths_json if any(token in path.lower() for token in ("server", "api", "backend"))):
                    return "validated", "Backend task completed with explicit task ownership.", recipe_id
                if "fastapi" in project_text or repo_has("server"):
                    return "planned", evidence_lines[area], recipe_id
            if area == "database":
                if any(token in project_text for token in ("sqlite", "database", "db")) or repo_has("database"):
                    return ("partial" if done_tasks else "planned"), evidence_lines[area], recipe_id
            if area == "auth":
                if "auth" in project_text or "login" in project_text:
                    return ("partial" if done_tasks else "planned"), evidence_lines[area], recipe_id
            if area == "security":
                if any(record.task_category == "security" or record.outcome == "needs_review" for record in performance):
                    return "partial", evidence_lines[area], recipe_id
                if "security" in project_text or "approval" in project_text:
                    return "planned", evidence_lines[area], recipe_id
            if area == "docs":
                if project.docs_path or repo_has("readme") or "docs" in task_titles:
                    return ("validated" if any(task for task in done_tasks if "doc" in task.title.lower()) else "planned"), evidence_lines[area], recipe_id
            if area == "deployment":
                if repo_has("dockerfile") or ".github" in project_text or "deploy" in project_text:
                    return ("partial" if done_tasks else "planned"), evidence_lines[area], recipe_id
            if area == "integrations":
                if "integration" in task_titles or "connector" in project_text:
                    return ("partial" if done_tasks else "planned"), evidence_lines[area], recipe_id
            if area == "tests":
                if any(record.tests_passed for record in performance):
                    return "validated", "Test evidence exists in agent performance records.", recipe_id
                if recipes or "test" in task_titles:
                    return "planned", evidence_lines[area], recipe_id
            if area == "packaging":
                if any(token in project_text for token in ("desktop", "package", "packaging", "installer")):
                    return ("partial" if done_tasks else "planned"), evidence_lines[area], recipe_id
            return "none", None, recipe_id

        return [
            {
                "id": existing[area].id if area in existing else 0,
                "project_id": project.id,
                "area": area,
                "coverage_status": infer_status(area)[0],
                "evidence_summary": infer_status(area)[1],
                "related_validation_step_id": infer_status(area)[2],
                "last_updated": existing[area].last_updated if area in existing else project.updated_at,
            }
            for area in VALIDATION_AREAS
        ]

    def preview_coverage(self, db: Session, project: Project) -> list[dict[str, Any]]:
        return self._compute_area_payloads(db, project)

    def recompute(self, db: Session, project: Project) -> list[ValidationCoverageArea]:
        results: list[ValidationCoverageArea] = []
        for payload in self._compute_area_payloads(db, project):
            record = self._upsert_area(db, project.id, str(payload["area"]))
            record.coverage_status = str(payload["coverage_status"])
            record.evidence_summary = payload["evidence_summary"]
            record.related_validation_step_id = payload["related_validation_step_id"]
            db.flush()
            results.append(record)
        return results

    def coverage_summary(self, db: Session, project: Project) -> dict[str, Any]:
        items = self.list_coverage(db, project)
        if not items:
            preview = self.preview_coverage(db, project)
            gaps = [item["area"] for item in preview if item["coverage_status"] in {"none", "failed"}]
            return {
                "items": preview,
                "gaps": gaps,
            }
        gaps = [item.area for item in items if item.coverage_status in {"none", "failed"}]
        return {
            "items": items,
            "gaps": gaps,
        }


validation_coverage_service = ValidationCoverageService()
