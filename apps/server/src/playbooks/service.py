from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    DecisionRecord,
    Project,
    ProjectPlaybook,
    ProjectPlaybookSelection,
    ValidationRecipe,
    utc_now,
)


DEFAULT_PLAYBOOKS: list[dict[str, Any]] = [
    {
        "key": "local_desktop_app",
        "name": "Local Desktop App",
        "description": "Local-first desktop workflow with packaging, setup, and usability checks.",
        "suggested_interview_categories_json": ["platform/runtime", "UI/UX style", "testing/validation", "deployment/distribution"],
        "suggested_swarm_mode": "balanced",
        "suggested_agent_archetypes_json": ["frontend", "backend", "test", "docs"],
        "suggested_validation_recipe_json": [{"title": "Launch app locally", "type": "manual_smoke"}],
        "common_risks_json": ["Packaging drift", "Platform-specific file paths", "Installer/runtime confusion"],
        "suggested_docs_json": ["README.md", "docs/WORKFLOW.md"],
        "typical_structure_json": ["apps/desktop", "apps/server", "docs", "scripts"],
    },
    {
        "key": "fastapi_react_web_app",
        "name": "FastAPI + React Web App",
        "description": "Split frontend/backend web app with API contracts, local state, and validation coverage.",
        "suggested_interview_categories_json": ["MVP scope", "data/storage", "authentication/security", "testing/validation"],
        "suggested_swarm_mode": "balanced",
        "suggested_agent_archetypes_json": ["frontend", "backend", "integration", "test"],
        "suggested_validation_recipe_json": [{"title": "Backend tests", "type": "pytest"}, {"title": "Frontend build", "type": "vite_build"}],
        "common_risks_json": ["API contract drift", "Frontend/backend scope mismatch", "Validation gaps across layers"],
        "suggested_docs_json": ["docs/ARCHITECTURE.md", "README.md"],
        "typical_structure_json": ["apps/dashboard", "apps/server", "docs"],
    },
    {
        "key": "browser_extension",
        "name": "Browser Extension",
        "description": "Extension workflow with permissions, browser-specific behavior, and packaging concerns.",
        "suggested_interview_categories_json": ["platform/runtime", "integrations/connectors", "authentication/security"],
        "suggested_swarm_mode": "high_quality",
        "suggested_agent_archetypes_json": ["frontend", "security", "test", "docs"],
        "suggested_validation_recipe_json": [{"title": "Permission review", "type": "security_review"}],
        "common_risks_json": ["Excessive permissions", "Browser compatibility", "Packaging drift"],
        "suggested_docs_json": ["README.md", "docs/SECURITY.md"],
        "typical_structure_json": ["extension", "src", "docs"],
    },
    {
        "key": "minecraft_mod",
        "name": "Minecraft Mod",
        "description": "Gameplay mod workflow with loader compatibility, packaging, and versioning risks.",
        "suggested_interview_categories_json": ["platform/runtime", "performance constraints", "future expansion"],
        "suggested_swarm_mode": "research_planning",
        "suggested_agent_archetypes_json": ["research", "feature", "test"],
        "suggested_validation_recipe_json": [{"title": "Loader compatibility check", "type": "manual_smoke"}],
        "common_risks_json": ["Version compatibility", "Loader API drift", "Mod packaging errors"],
        "suggested_docs_json": ["README.md"],
        "typical_structure_json": ["src", "gradle", "docs"],
    },
    {
        "key": "data_ingestion_pipeline",
        "name": "Data Ingestion Pipeline",
        "description": "Pipeline-oriented project with data quality, retry, and backfill concerns.",
        "suggested_interview_categories_json": ["data/storage", "integrations/connectors", "performance constraints"],
        "suggested_swarm_mode": "high_quality",
        "suggested_agent_archetypes_json": ["backend", "data", "test", "ops"],
        "suggested_validation_recipe_json": [{"title": "Sample ingest", "type": "smoke_check"}],
        "common_risks_json": ["Silent data loss", "Backfill cost", "Schema drift"],
        "suggested_docs_json": ["docs/ARCHITECTURE.md"],
        "typical_structure_json": ["pipeline", "scripts", "docs"],
    },
    {
        "key": "ai_local_tool",
        "name": "AI Local Tool",
        "description": "Local AI workflow with model/runner selection, fallback behavior, and prompt safety.",
        "suggested_interview_categories_json": ["agent/tool behavior", "privacy/local-first constraints", "testing/validation"],
        "suggested_swarm_mode": "research_planning",
        "suggested_agent_archetypes_json": ["planner", "backend", "test", "docs"],
        "suggested_validation_recipe_json": [{"title": "Dry-run and live-run comparison", "type": "comparison"}],
        "common_risks_json": ["Fake execution claims", "Prompt drift", "Hidden API dependencies"],
        "suggested_docs_json": ["docs/CODEX_INTEGRATION.md"],
        "typical_structure_json": ["apps", "docs", "scripts"],
    },
    {
        "key": "osint_dashboard",
        "name": "OSINT Dashboard",
        "description": "Dashboard-centric research tooling with source traceability and validation needs.",
        "suggested_interview_categories_json": ["target users", "integrations/connectors", "testing/validation"],
        "suggested_swarm_mode": "documentation_heavy",
        "suggested_agent_archetypes_json": ["frontend", "backend", "docs", "reviewer"],
        "suggested_validation_recipe_json": [{"title": "Source traceability spot-check", "type": "manual_review"}],
        "common_risks_json": ["Unverifiable claims", "Scope creep into ingestion", "UI-heavy research debt"],
        "suggested_docs_json": ["docs/WORKFLOW.md"],
        "typical_structure_json": ["apps/dashboard", "apps/server", "docs"],
    },
    {
        "key": "static_docs_site",
        "name": "Static Docs Site",
        "description": "Content-first static documentation site with navigation, search, and publishing validation.",
        "suggested_interview_categories_json": ["UI/UX style", "testing/validation", "deployment/distribution"],
        "suggested_swarm_mode": "documentation_heavy",
        "suggested_agent_archetypes_json": ["docs", "frontend", "reviewer"],
        "suggested_validation_recipe_json": [{"title": "Link check", "type": "docs_review"}],
        "common_risks_json": ["Broken navigation", "Stale examples", "Publishing mismatch"],
        "suggested_docs_json": ["README.md", "docs/WORKFLOW.md"],
        "typical_structure_json": ["docs", "src", "public"],
    },
    {
        "key": "existing_repo_cleanup",
        "name": "Existing Repo Cleanup",
        "description": "Refactor and cleanup pass for an existing repository with high review sensitivity.",
        "suggested_interview_categories_json": ["MVP scope", "testing/validation", "future expansion"],
        "suggested_swarm_mode": "massive_codebase",
        "suggested_agent_archetypes_json": ["research", "architect", "reviewer", "test"],
        "suggested_validation_recipe_json": [{"title": "Regression pass", "type": "test_run"}],
        "common_risks_json": ["Refactor regressions", "Unclear ownership", "Cleanup becoming rewrite"],
        "suggested_docs_json": ["docs/ARCHITECTURE.md"],
        "typical_structure_json": ["src", "tests", "docs"],
    },
    {
        "key": "generic_custom",
        "name": "Generic Custom",
        "description": "Fallback playbook when the project is real but does not fit a narrower pattern yet.",
        "suggested_interview_categories_json": ["product goal", "MVP scope", "testing/validation"],
        "suggested_swarm_mode": "balanced",
        "suggested_agent_archetypes_json": ["planner", "feature", "test"],
        "suggested_validation_recipe_json": [{"title": "Basic smoke validation", "type": "smoke_check"}],
        "common_risks_json": ["Unknown domain fit", "Spec ambiguity", "Validation assumptions"],
        "suggested_docs_json": ["README.md"],
        "typical_structure_json": ["src", "docs"],
    },
]


class PlaybookService:
    def _playbook_snapshot(
        self,
        payload: dict[str, Any],
        override: ProjectPlaybook | None = None,
        *,
        synthetic_id: int,
    ) -> ProjectPlaybook:
        timestamp = utc_now()
        return ProjectPlaybook(
            id=override.id if override is not None else synthetic_id,
            key=str(override.key if override is not None else payload["key"]),
            name=str(override.name if override is not None else payload["name"]),
            description=str(override.description if override is not None else payload["description"]),
            suggested_interview_categories_json=list(
                override.suggested_interview_categories_json
                if override is not None
                else payload.get("suggested_interview_categories_json", [])
            ),
            suggested_swarm_mode=override.suggested_swarm_mode if override is not None else payload.get("suggested_swarm_mode"),
            suggested_agent_archetypes_json=list(
                override.suggested_agent_archetypes_json
                if override is not None
                else payload.get("suggested_agent_archetypes_json", [])
            ),
            suggested_validation_recipe_json=list(
                override.suggested_validation_recipe_json
                if override is not None
                else payload.get("suggested_validation_recipe_json", [])
            ),
            common_risks_json=list(override.common_risks_json if override is not None else payload.get("common_risks_json", [])),
            suggested_docs_json=list(override.suggested_docs_json if override is not None else payload.get("suggested_docs_json", [])),
            typical_structure_json=list(
                override.typical_structure_json if override is not None else payload.get("typical_structure_json", [])
            ),
            created_at=override.created_at if override is not None else timestamp,
            updated_at=override.updated_at if override is not None else timestamp,
        )

    def _playbook_views(self, db: Session) -> list[ProjectPlaybook]:
        existing = {item.key: item for item in db.scalars(select(ProjectPlaybook).order_by(ProjectPlaybook.key.asc()))}
        merged: list[ProjectPlaybook] = []
        seen: set[str] = set()
        for index, payload in enumerate(DEFAULT_PLAYBOOKS, start=1):
            playbook_key = str(payload["key"])
            merged.append(self._playbook_snapshot(payload, existing.get(playbook_key), synthetic_id=-index))
            seen.add(playbook_key)
        for playbook_key, record in existing.items():
            if playbook_key in seen:
                continue
            merged.append(self._playbook_snapshot({"key": playbook_key}, record, synthetic_id=record.id))
        return sorted(merged, key=lambda item: item.name.lower())

    def list_playbooks(self, db: Session) -> list[ProjectPlaybook]:
        return self._playbook_views(db)

    def get_playbook(self, db: Session, playbook_key: str) -> ProjectPlaybook | None:
        return next((item for item in self._playbook_views(db) if item.key == playbook_key), None)

    def _selection(self, db: Session, project_id: int) -> ProjectPlaybookSelection | None:
        return db.get(ProjectPlaybookSelection, project_id)

    def _score_playbook(self, project: Project, playbook: ProjectPlaybook) -> tuple[int, str]:
        text = f"{project.name}\n{project.idea}\n{project.workspace_path}".lower()
        reasons: list[str] = []
        score = 0
        if playbook.key == "fastapi_react_web_app" and any(token in text for token in ("fastapi", "react", "vite", "dashboard", "api", "web")):
            score += 5
            reasons.append("Project signals match a split frontend/backend web stack.")
        if playbook.key == "local_desktop_app" and any(token in text for token in ("desktop", "local-first", "packaging", "installer")):
            score += 4
            reasons.append("Project signals emphasize local-first desktop behavior.")
        if playbook.key == "ai_local_tool" and any(token in text for token in ("agent", "codex", "model", "runner", "llm", "local tool")):
            score += 5
            reasons.append("Project signals center on local AI/tooling behavior.")
        if playbook.key == "existing_repo_cleanup" and any(token in text for token in ("cleanup", "refactor", "existing repo", "legacy")):
            score += 4
            reasons.append("Project looks like a cleanup/refactor pass instead of a greenfield build.")
        if playbook.key == "static_docs_site" and any(token in text for token in ("docs", "documentation", "guide", "site")):
            score += 3
            reasons.append("Documentation appears to be a first-class deliverable.")
        if playbook.key == "generic_custom":
            score += 1
            reasons.append("Fallback when the repo is real but not neatly classified yet.")
        return score, " ".join(reasons)

    def suggest_playbook(self, db: Session, project: Project, *, persist: bool = True) -> dict[str, Any]:
        playbooks = self.list_playbooks(db)
        scored = sorted(
            ((self._score_playbook(project, playbook), playbook) for playbook in playbooks),
            key=lambda item: (item[0][0], item[1].name),
        )
        (score, reason), chosen = scored[-1]
        if score <= 0:
            chosen = next((item for item in playbooks if item.key == "generic_custom"), playbooks[0])
            reason = "No stronger pattern matched the current project signals."

        selection = self._selection(db, project.id)
        if persist:
            if selection is None:
                selection = ProjectPlaybookSelection(project_id=project.id)
                db.add(selection)
            if selection.status != "applied":
                selection.playbook_key = chosen.key
                selection.status = "suggested"
                selection.suggestion_reason = reason
            db.flush()
        return {
            "project_id": project.id,
            "playbook_key": chosen.key,
            "status": selection.status if selection is not None else "suggested",
            "why": reason or "Manager will use the generic playbook until project signals become clearer.",
            "playbook": chosen,
        }

    def apply_playbook(self, db: Session, project: Project, playbook_key: str) -> dict[str, Any]:
        playbook = self.get_playbook(db, playbook_key)
        if playbook is None:
            raise ValueError("Playbook not found")
        selection = self._selection(db, project.id)
        if selection is None:
            selection = ProjectPlaybookSelection(project_id=project.id)
            db.add(selection)
        selection.playbook_key = playbook.key
        selection.status = "applied"
        selection.suggestion_reason = selection.suggestion_reason or f"Applied {playbook.name}."

        recipe_name = f"{playbook.name} validation recipe"
        recipe = db.scalar(
            select(ValidationRecipe)
            .where(ValidationRecipe.project_id == project.id, ValidationRecipe.name == recipe_name)
            .order_by(ValidationRecipe.id.asc())
        )
        if recipe is None:
            recipe = ValidationRecipe(project_id=project.id, name=recipe_name)
            db.add(recipe)
        recipe.steps_json = list(playbook.suggested_validation_recipe_json or [])
        recipe.status = "draft"

        decision = DecisionRecord(
            project_id=project.id,
            decision_type="playbook",
            title=f"Apply playbook: {playbook.name}",
            decision=f"Mission Control will use the {playbook.name} playbook as the planning baseline.",
            reason=selection.suggestion_reason or playbook.description,
            made_by="manager",
            impact_area_json=["planning", "validation", "swarm"],
            reversible=True,
        )
        db.add(decision)
        project.updated_at = utc_now()
        db.flush()
        return {
            "project_id": project.id,
            "playbook_key": playbook.key,
            "status": selection.status,
            "why": selection.suggestion_reason or playbook.description,
            "playbook": playbook,
        }

    def project_playbook_state(self, db: Session, project: Project) -> dict[str, Any]:
        selection = self._selection(db, project.id)
        if selection is None:
            return self.suggest_playbook(db, project, persist=True)
        playbook = self.get_playbook(db, selection.playbook_key) if selection.playbook_key else None
        if playbook is None:
            return self.suggest_playbook(db, project, persist=True)
        return {
            "project_id": project.id,
            "playbook_key": selection.playbook_key,
            "status": selection.status,
            "why": selection.suggestion_reason or playbook.description,
            "playbook": playbook,
        }


playbook_service = PlaybookService()
