from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    Agent,
    ContextPack,
    ContextPackSection,
    DecisionRecord,
    ManagerAssumption,
    Project,
    ProjectPlaybook,
    ProjectPlaybookSelection,
    RiskRecord,
    Task,
    UserPreference,
)


class ContextPackService:
    def _validate_agent(self, db: Session, project: Project, agent_id: int | None) -> Agent | None:
        if agent_id is None:
            return None
        agent = db.get(Agent, agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        if agent.project_id != project.id:
            raise HTTPException(status_code=404, detail="Agent not found in this project")
        return agent

    def _validate_task(self, db: Session, project: Project, task_id: int | None) -> Task | None:
        if task_id is None:
            return None
        task = db.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.project_id != project.id:
            raise HTTPException(status_code=404, detail="Task not found in this project")
        return task

    def _existing_doc_candidates(self, project: Project) -> list[str]:
        docs: list[str] = []
        if project.docs_path:
            docs_root = Path(project.docs_path)
            for name in [
                "PROJECT_BRIEF.md",
                "ARCHITECTURE_NOTES.md",
                "MVP_SCOPE.md",
                "TASK_BOARD.md",
                "RISKS_AND_UNKNOWNS.md",
            ]:
                candidate = docs_root / name
                if candidate.exists():
                    docs.append(str(candidate))
        workspace_root = Path(project.workspace_path)
        for name in ["README.md", "docs/ARCHITECTURE.md", "docs/WORKFLOW.md", "docs/INTELLIGENCE_LAYER.md"]:
            candidate = workspace_root / name
            if candidate.exists():
                docs.append(str(candidate))
        return docs[:8]

    def _context_pack_warnings(self, pack: ContextPack) -> list[str]:
        warnings: list[str] = []
        if len(pack.included_files_json or []) > 6:
            warnings.append("Context pack is broad enough to risk prompt bloat.")
        if any(item in {"src", ".", "*"} for item in (pack.included_files_json or [])):
            warnings.append("Context pack includes a very broad path. Narrow it before large swarms.")
        if len(pack.included_docs_json or []) > 5:
            warnings.append("Context pack includes many docs. Consider trimming to the decisive ones.")
        return warnings

    def _serialize_pack(self, pack: ContextPack, sections: list[ContextPackSection]) -> dict[str, Any]:
        return {
            "id": pack.id,
            "project_id": pack.project_id,
            "agent_id": pack.agent_id,
            "task_id": pack.task_id,
            "title": pack.title,
            "goal": pack.goal,
            "included_docs_json": list(pack.included_docs_json or []),
            "included_files_json": list(pack.included_files_json or []),
            "excluded_files_json": list(pack.excluded_files_json or []),
            "known_decisions_json": list(pack.known_decisions_json or []),
            "relevant_assumptions_json": list(pack.relevant_assumptions_json or []),
            "validation_steps_json": list(pack.validation_steps_json or []),
            "token_budget_hint": pack.token_budget_hint,
            "warnings_json": self._context_pack_warnings(pack),
            "sections": [
                {
                    "id": section.id,
                    "context_pack_id": section.context_pack_id,
                    "section_type": section.section_type,
                    "title": section.title,
                    "content_markdown": section.content_markdown,
                    "source_refs_json": list(section.source_refs_json or []),
                    "created_at": section.created_at,
                }
                for section in sections
            ],
            "created_at": pack.created_at,
            "updated_at": pack.updated_at,
        }

    def build_context_pack(
        self,
        db: Session,
        project: Project,
        *,
        agent_id: int | None = None,
        task_id: int | None = None,
        title: str | None = None,
        goal: str | None = None,
        token_budget_hint: int | None = None,
    ) -> dict[str, Any]:
        agent = self._validate_agent(db, project, agent_id)
        task = self._validate_task(db, project, task_id)
        included_files = list(task.allowed_paths_json or []) if task is not None else ["apps/server/src", "apps/dashboard/src"]
        excluded_files = list(task.forbidden_paths_json or []) if task is not None else []
        decisions = list(
            db.scalars(
                select(DecisionRecord)
                .where(DecisionRecord.project_id == project.id)
                .order_by(DecisionRecord.created_at.desc(), DecisionRecord.id.desc())
            )
        )[:5]
        assumptions = list(
            db.scalars(
                select(ManagerAssumption)
                .where(ManagerAssumption.project_id == project.id, ManagerAssumption.status == "active")
                .order_by(ManagerAssumption.created_at.desc(), ManagerAssumption.id.desc())
            )
        )[:5]
        risks = list(
            db.scalars(
                select(RiskRecord)
                .where(RiskRecord.project_id == project.id, RiskRecord.status.in_(["open", "monitoring", "accepted"]))
                .order_by(RiskRecord.severity.desc(), RiskRecord.updated_at.desc(), RiskRecord.id.desc())
            )
        )[:5]
        preferences = list(
            db.scalars(
                select(UserPreference)
                .where(
                    (UserPreference.scope == "global")
                    | ((UserPreference.scope == "project") & (UserPreference.project_id == project.id))
                )
                .order_by(UserPreference.scope.asc(), UserPreference.key.asc())
            )
        )[:6]
        playbook_selection = db.get(ProjectPlaybookSelection, project.id)
        playbook = (
            db.scalar(select(ProjectPlaybook).where(ProjectPlaybook.key == playbook_selection.playbook_key))
            if playbook_selection and playbook_selection.playbook_key
            else None
        )
        docs = self._existing_doc_candidates(project)
        validation_steps = list(task.validation_steps_json or []) if task is not None else ["Record what was validated and what remains manual."]

        pack = ContextPack(
            project_id=project.id,
            agent_id=agent.id if agent is not None else None,
            task_id=task.id if task is not None else None,
            title=title or (f"{task.title} context" if task is not None else "Project context pack"),
            goal=goal or (task.goal if task is not None else project.idea),
            included_docs_json=docs,
            included_files_json=included_files,
            excluded_files_json=excluded_files,
            known_decisions_json=[f"{item.title}: {item.decision}" for item in decisions],
            relevant_assumptions_json=[item.assumption for item in assumptions],
            validation_steps_json=validation_steps,
            token_budget_hint=token_budget_hint or max(1200, 400 * max(1, len(included_files))),
        )
        db.add(pack)
        db.flush()

        sections: list[ContextPackSection] = []

        def add_section(section_type: str, heading: str, content: str, source_refs: list[str]) -> None:
            section = ContextPackSection(
                context_pack_id=pack.id,
                section_type=section_type,
                title=heading,
                content_markdown=content.strip(),
                source_refs_json=source_refs,
            )
            db.add(section)
            db.flush()
            sections.append(section)

        add_section(
            "mission",
            "Mission",
            "\n".join(
                [
                    f"Project: **{project.name}**",
                    f"Goal: {pack.goal}",
                    f"Assigned agent: {agent.name if agent is not None else 'Unassigned'}",
                    f"Task: {task.title if task is not None else 'No specific task'}",
                    f"Applied playbook: {playbook.name if playbook is not None else 'None'}",
                ]
            ),
            ["project", f"task:{task.id}" if task is not None else "task:none"],
        )
        add_section(
            "boundaries",
            "Boundaries",
            "\n".join(
                [
                    "Allowed paths:",
                    *([f"- `{item}`" for item in included_files] or ["- No explicit path hints were provided."]),
                    "Forbidden paths:",
                    *([f"- `{item}`" for item in excluded_files] or ["- No forbidden paths were recorded."]),
                ]
            ),
            [f"path:{item}" for item in included_files + excluded_files],
        )
        add_section(
            "decisions",
            "Known Decisions",
            "\n".join([f"- {item.title}: {item.decision}" for item in decisions]) or "- No explicit decisions were recorded yet.",
            [f"decision:{item.id}" for item in decisions],
        )
        add_section(
            "assumptions",
            "Assumptions And Preferences",
            "\n".join(
                [f"- Assumption: {item.assumption}" for item in assumptions]
                + [f"- Preference `{item.key}`: {item.value_json}" for item in preferences]
            )
            or "- No active assumptions or preferences were recorded.",
            [f"assumption:{item.id}" for item in assumptions] + [f"preference:{item.id}" for item in preferences],
        )
        add_section(
            "risks",
            "Top Risks",
            "\n".join(
                [
                    f"- {item.title} ({item.severity}/{item.likelihood}): {item.mitigation or 'No mitigation recorded yet.'}"
                    for item in risks
                ]
            )
            or "- No open risks are recorded right now.",
            [f"risk:{item.id}" for item in risks],
        )
        add_section(
            "validation",
            "Validation",
            "\n".join([f"- {item}" for item in validation_steps] + ["- Return a completion report with changed files, tests, blockers, and risks."]),
            [f"task:{task.id}" if task is not None else "task:none"],
        )
        db.flush()
        return self._serialize_pack(pack, sections)

    def list_context_packs(self, db: Session, project: Project) -> list[dict[str, Any]]:
        packs = list(
            db.scalars(
                select(ContextPack)
                .where(ContextPack.project_id == project.id)
                .order_by(ContextPack.created_at.desc(), ContextPack.id.desc())
            )
        )
        return [self.get_context_pack(db, pack.id) for pack in packs]

    def get_context_pack(self, db: Session, context_pack_id: int) -> dict[str, Any]:
        pack = db.get(ContextPack, context_pack_id)
        if pack is None:
            raise ValueError("Context pack not found")
        sections = list(
            db.scalars(
                select(ContextPackSection)
                .where(ContextPackSection.context_pack_id == context_pack_id)
                .order_by(ContextPackSection.id.asc())
            )
        )
        return self._serialize_pack(pack, sections)

    def render_markdown(self, pack_payload: dict[str, Any]) -> str:
        sections = pack_payload.get("sections") or []
        lines = [
            f"# {pack_payload['title']}",
            "",
            f"Goal: {pack_payload['goal']}",
            "",
        ]
        for section in sections:
            lines.append(f"## {section['title']}")
            lines.append(str(section["content_markdown"]).strip())
            lines.append("")
        return "\n".join(lines).strip()


context_pack_service = ContextPackService()
