from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from codex_auth import auth_service
from codex_runner.app_server_runner import AppServerCodexRunner
from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerSettings
from codex_runner.cli_runner import CliCodexRunner
from codex_runner.dry_run_runner import DryRunRunner
from config import (
    DEFAULT_MANAGER_MODE,
    DEFAULT_RUNNER_MODE,
    WORKTREE_ROOT,
)
from events import EventService
from interview import select_questions
from models import Agent, AgentRun, InterviewQuestion, InterviewSession, PathReservation, Plan, Project, ProjectSettings, Task, utc_now
from planner import build_plan_markdown
from project_settings import (
    ResolvedRunSettings,
    get_or_create_project_settings,
    resolve_manager_settings,
    resolve_worker_settings,
    resolved_run_settings_payload,
    settings_summary,
)
from prompts import (
    MANAGER_DOC_UPDATE_SCHEMA,
    MANAGER_HANDOFF_SCHEMA,
    MANAGER_PLAN_SCHEMA,
    MANAGER_TASK_DECOMPOSITION_SCHEMA,
    MANAGER_WORKER_DECISION_SCHEMA,
    docs_manifest_path,
    manager_action_prompt,
    manager_message_prompt,
)
from schemas import ManagerDocFile, ManagerDocUpdate, ManagerHandoff, ManagerPlan, ManagerTaskDecomposition, ManagerTaskItem, ManagerWorkerDecision, ProjectSettingsUpdate, WorkerReport
from task_board import build_initial_tasks, can_assign_task, conflicting_agents


DOC_FILENAMES = [
    "PROJECT_BRIEF.md",
    "PRODUCT_VISION.md",
    "USER_GOALS.md",
    "MVP_SCOPE.md",
    "ARCHITECTURE_NOTES.md",
    "RISKS_AND_UNKNOWNS.md",
    "AGENT_PLAN.md",
    "TASK_BOARD.md",
]
TASK_OPEN_STATUSES = {"backlog", "assigned", "working", "waiting_on_paths", "needs_review", "blocked"}
TASK_STARTABLE_STATUSES = {"backlog", "assigned", "waiting_on_paths"}
TManagerModel = TypeVar("TManagerModel", bound=BaseModel)


def _dump_model(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _validate_model(schema: type[TManagerModel], payload: dict[str, Any]) -> TManagerModel:
    if hasattr(schema, "model_validate"):
        return schema.model_validate(payload)  # type: ignore[attr-defined]
    return schema.parse_obj(payload)  # type: ignore[attr-defined]


class InterviewGeneration(BaseModel):
    questions: list[dict[str, Any]]


class RunnerRegistry:
    def __init__(self) -> None:
        self.runners: dict[str, BaseCodexRunner] = {
            "dry_run": DryRunRunner(),
            "cli": CliCodexRunner(),
            "app_server": AppServerCodexRunner(),
        }
        self._auto_app_server_enabled: bool | None = None
        self._cli_enabled: bool | None = None

    async def cli_available(self) -> bool:
        if self._cli_enabled is None:
            self._cli_enabled = await self.runners["cli"].handshake()
        return self._cli_enabled

    async def app_server_available(self) -> bool:
        if self._auto_app_server_enabled is None:
            self._auto_app_server_enabled = await self.runners["app_server"].handshake()
        return self._auto_app_server_enabled

    async def effective_auto_mode(self) -> str:
        if await self.app_server_available():
            return "app_server"
        if await self.cli_available():
            return "cli"
        return "unavailable"

    async def get_runner(self, runner_mode: str) -> BaseCodexRunner:
        if runner_mode == "auto":
            if await self.app_server_available():
                return self.runners["app_server"]
            return self.runners["cli"]
        return self.runners[runner_mode]


class MissionControlService:
    def __init__(self) -> None:
        self.events = EventService()
        self.runners = RunnerRegistry()
        self.active_monitors: dict[int, asyncio.Task] = {}

    def _project_docs_dir(self, project: Project) -> Path:
        return Path(project.workspace_path) / "mission-control"

    def _ensure_project_workspace(self, project: Project) -> Path:
        docs_dir = self._project_docs_dir(project)
        docs_dir.mkdir(parents=True, exist_ok=True)
        project.docs_path = str(docs_dir)
        return docs_dir

    def _latest_plan(self, db: Session, project_id: int) -> Plan | None:
        return db.scalar(select(Plan).where(Plan.project_id == project_id).order_by(Plan.version.desc()))

    def _latest_session(self, db: Session, project_id: int) -> InterviewSession | None:
        return db.scalar(select(InterviewSession).where(InterviewSession.project_id == project_id).order_by(InterviewSession.id.desc()))

    def _manager_agent(self, db: Session, project_id: int) -> Agent:
        manager_agent = db.scalar(select(Agent).where(Agent.project_id == project_id, Agent.kind == "manager"))
        if not manager_agent:
            raise ValueError("Manager agent not found")
        return manager_agent

    def _project_settings(self, db: Session, project: Project) -> ProjectSettings:
        return get_or_create_project_settings(db, project)

    @staticmethod
    def _runner_settings_payload(resolved: ResolvedRunSettings) -> RunnerSettings:
        return RunnerSettings(
            sandbox_mode=resolved.sandbox_mode,
            approval_policy=resolved.approval_policy,
            model=resolved.model,
            reasoning_effort=resolved.reasoning_effort,
        )

    @staticmethod
    def _cache_agent_run_profile(agent: Agent, resolved: ResolvedRunSettings, *, runner_type: str, action: str) -> None:
        agent.active_model = resolved.effective_model_label
        agent.active_reasoning_effort = resolved.effective_reasoning_label
        agent.active_runner_type = runner_type
        agent.current_action = action

    def _task_board_markdown(self, tasks: list[Task]) -> str:
        grouped: dict[str, list[str]] = {}
        for task in sorted(tasks, key=lambda item: (item.priority, item.id)):
            grouped.setdefault(task.status, []).append(f"- #{task.id} {task.title}")
        sections = ["# Task Board", ""]
        for status, items in grouped.items():
            sections.append(f"## {status.replace('_', ' ').title()}")
            sections.extend(items or ["- None"])
            sections.append("")
        return "\n".join(sections).strip() + "\n"

    def _render_docs(self, project: Project, plan: ManagerPlan | None = None, questions: list[InterviewQuestion] | None = None) -> dict[str, str]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        answers = [question.selected_text for question in questions or [] if question.selected_text]
        answer_preview = ", ".join(answers[:6]) or "Interview still pending."
        summary = plan.refined_summary if plan else project.idea
        scope = plan.mvp_scope if plan else ["Keep the first version local, usable, and tightly scoped."]
        milestones = plan.milestones if plan else ["Clarify the slice", "Build the vertical slice", "Validate and hand off"]
        risks = plan.risks if plan else ["Local tooling assumptions may change.", "Scope can drift if the first slice stays vague."]
        definitions = plan.definition_of_done if plan else ["The main workflow works locally.", "Known limitations are documented."]
        return {
            "PROJECT_BRIEF.md": f"# {project.name}\n\n## Idea\n{project.idea}\n\n## Refined summary\n{summary}\n\n## Generated\n{now}\n",
            "PRODUCT_VISION.md": "# Product Vision\n\n" + "\n".join(f"- {line}" for line in scope) + "\n",
            "USER_GOALS.md": f"# User Goals\n\n- Interview signals: {answer_preview}\n- Land a usable vertical slice quickly.\n- Keep the workflow trustworthy.\n",
            "MVP_SCOPE.md": "# MVP Scope\n\n" + "\n".join(f"- {line}" for line in scope) + "\n",
            "ARCHITECTURE_NOTES.md": "# Architecture Notes\n\n" + "\n".join(f"- {line}" for line in (plan.recommended_architecture if plan else ["Keep the app local-first.", "Separate manager logic from worker execution."])) + "\n",
            "RISKS_AND_UNKNOWNS.md": "# Risks and Unknowns\n\n" + "\n".join(f"- {line}" for line in risks) + "\n",
            "AGENT_PLAN.md": "# Agent Plan\n\n" + "\n".join(f"- {line}" for line in milestones) + "\n",
            "TASK_BOARD.md": "# Task Board\n\n- Task generation happens after plan approval.\n- Path ownership prevents overlapping edits.\n- Validation and handoff tasks stay explicit.\n",
        }

    def _deterministic_doc_update(self, project: Project, questions: list[InterviewQuestion], plan: ManagerPlan | None) -> ManagerDocUpdate:
        files = [
            ManagerDocFile(filename=filename, content=content)
            for filename, content in self._render_docs(project, plan=plan, questions=questions).items()
        ]
        return ManagerDocUpdate(
            summary_markdown=f"Generated {len(files)} planning docs for **{project.name}** with the latest project summary and scope.",
            files=files,
        )

    def _deterministic_interview_payload(self, question_count: int) -> dict[str, Any]:
        templates = select_questions(question_count)
        return {
            "questions": [
                {
                    "question": template.question,
                    "options": template.options,
                }
                for template in templates
            ]
        }

    def _deterministic_plan(self, project: Project, questions: list[InterviewQuestion], action_bias: str | None = None, note: str | None = None) -> ManagerPlan:
        content_markdown, summary_json = build_plan_markdown(project, questions, action_bias=action_bias, note=note)
        return ManagerPlan(
            refined_summary=summary_json["refined_summary"],
            mvp_scope=summary_json["mvp_scope"],
            milestones=summary_json["milestones"],
            recommended_architecture=summary_json["recommended_architecture"],
            agent_roster=summary_json["agent_roster"],
            task_breakdown=summary_json["task_breakdown"],
            validation_plan=summary_json["validation_plan"],
            risks=summary_json["risks"],
            definition_of_done=summary_json["definition_of_done"],
            content_markdown=content_markdown,
            summary_json=summary_json,
        )

    def _deterministic_task_decomposition(self, project: Project, plan: Plan | None) -> ManagerTaskDecomposition:
        items = []
        for payload in build_initial_tasks(project):
            items.append(
                ManagerTaskItem(
                    title=payload["title"],
                    goal=payload["goal"],
                    scope=payload["scope"],
                    agent_role=payload.get("agent_role") or "Primary implementation",
                    milestone=payload.get("milestone") or "Milestone 1 - Runnable vertical slice",
                    priority=payload["priority"],
                    allowed_paths=payload["allowed_paths_json"],
                    forbidden_paths=payload["forbidden_paths_json"],
                    validation_steps=payload["validation_steps_json"],
                    success_criteria=payload.get("success_criteria_json", []),
                    estimated_complexity=payload.get("estimated_complexity", "medium"),
                    dependencies=payload.get("dependencies_json", []),
                    status="backlog",
                )
            )
        return ManagerTaskDecomposition(
            summary_markdown="Generated a milestone-based task breakdown with a runnable vertical slice first and explicit validation work last.",
            milestones=[
                "Milestone 1 - Runnable vertical slice",
                "Milestone 2 - Validation and handoff",
            ],
            tasks=items,
        )

    def _build_synthetic_worker_report(self, agent: Agent, task: Task | None, status: str, raw_payload: dict[str, Any] | None) -> WorkerReport:
        raw_payload = raw_payload or {}
        task_id = str(task.id if task else raw_payload.get("task_id") or "unknown")
        summary = raw_payload.get("summary") or f"Run finished with status {status}."
        report_status = raw_payload.get("status") or ("error" if status == "error" else "done")
        try:
            return _validate_model(
                WorkerReport,
                {
                    "agent": raw_payload.get("agent") or agent.name,
                    "task_id": task_id,
                    "status": report_status,
                    "summary": summary,
                    "files_changed": raw_payload.get("files_changed") or [],
                    "tests_run": raw_payload.get("tests_run") or [],
                    "blockers": raw_payload.get("blockers") or [],
                    "risks": raw_payload.get("risks") or [],
                    "recommended_next_task": raw_payload.get("recommended_next_task") or "",
                },
            )
        except ValidationError:
            return WorkerReport(
                agent=agent.name,
                task_id=task_id,
                status="error" if status == "error" else "done",
                summary=summary,
                files_changed=[],
                tests_run=[],
                blockers=[],
                risks=["Report payload could not be validated."],
                recommended_next_task="",
            )

    def _deterministic_worker_decision(
        self,
        db: Session,
        project: Project,
        agent: Agent,
        task: Task | None,
        report: WorkerReport,
    ) -> ManagerWorkerDecision:
        if not task:
            return ManagerWorkerDecision(decision_type="wait", summary_markdown="No follow-up task was attached to this run.")
        if report.status == "needs_review":
            return ManagerWorkerDecision(
                decision_type="escalate_to_user",
                summary_markdown=f"Task **{task.title}** needs review before more work is routed.",
                escalation_message=report.summary,
            )
        if report.status == "error":
            if task.failure_count < 2 and agent.failure_count < 3:
                return ManagerWorkerDecision(
                    decision_type="request_fix",
                    summary_markdown=f"Retry **{task.title}** once with a tighter fix pass.",
                    task_id=task.id,
                    assign_to_agent_id=agent.id,
                )
            return ManagerWorkerDecision(
                decision_type="escalate_to_user",
                summary_markdown=f"Repeated errors on **{task.title}** require user attention.",
                escalation_message=report.summary,
            )
        if report.status == "blocked":
            validation_agent = db.scalar(
                select(Agent)
                .where(Agent.project_id == project.id, Agent.kind == "worker")
                .order_by(Agent.id.asc())
            )
            if validation_agent and task.failure_count < 2:
                return ManagerWorkerDecision(
                    decision_type="request_fix",
                    summary_markdown=f"Create a follow-up unblock task for **{task.title}**.",
                    assign_to_agent_id=validation_agent.id,
                    follow_up_title=f"Unblock: {task.title}",
                    follow_up_goal=report.blockers[0] if report.blockers else f"Resolve the blocker reported by {agent.name}.",
                )
            return ManagerWorkerDecision(
                decision_type="escalate_to_user",
                summary_markdown=f"Task **{task.title}** is blocked and needs user input.",
                escalation_message=report.blockers[0] if report.blockers else report.summary,
            )
        next_task = self._find_next_safe_task(db, project, agent)
        if next_task:
            return ManagerWorkerDecision(
                decision_type="assign_next_task",
                summary_markdown=f"Route **{next_task.title}** to {agent.name}.",
                task_id=next_task.id,
                assign_to_agent_id=agent.id,
            )
        return ManagerWorkerDecision(
            decision_type="wait",
            summary_markdown=f"No safe backlog task is ready after **{task.title}**. Hold {agent.name} in waiting state.",
        )

    def _deterministic_handoff(self, project: Project, tasks: list[Task], runs: list[AgentRun]) -> ManagerHandoff:
        tests_run = sorted({entry for run in runs for entry in (run.report_json or {}).get("tests_run", [])})
        done_titles = [task.title for task in tasks if task.status == "done"]
        risks = sorted({entry for run in runs for entry in (run.report_json or {}).get("risks", []) if entry})
        return ManagerHandoff(
            summary_markdown=f"{project.name} reached handoff readiness with all tracked tasks in a terminal done state.",
            what_was_built=done_titles or ["Completed the tracked MVP task set."],
            how_to_run=[
                "Backend: cd apps/server && python -m uvicorn main:app --app-dir src --reload",
                "Frontend: cd apps/dashboard && npm run dev",
                "Use dry_run mode for offline orchestration testing.",
            ],
            how_to_use=[
                "Open Project Intake and create or resume a project.",
                "Run the interview, approve the plan, then monitor workers in Build Monitor.",
                "Use the manager chat or next-step controls for follow-up changes.",
            ],
            tests_builds_run=tests_run or ["No automated tests were recorded by the backend."],
            known_limitations=[
                "App-server integration remains experimental.",
                "Manager Codex turns depend on the local Codex environment and may fall back deterministically.",
            ],
            remaining_risks=risks or ["Validation depth depends on the selected workspace tooling."],
            suggested_next_improvements=[
                "Deepen manager task decomposition for larger projects.",
                "Strengthen app-server parity with the CLI runner.",
                "Add richer review workflows for needs-review tasks.",
            ],
        )

    async def _resolve_manager_model(
        self,
        db: Session,
        project: Project,
        *,
        action_name: str,
        objective: str,
        response_schema: dict[str, Any],
        payload: dict[str, Any],
        model_schema: type[TManagerModel],
        fallback_factory: Callable[[], TManagerModel],
    ) -> tuple[TManagerModel, str]:
        manager_agent = self._manager_agent(db, project.id)
        settings_record = self._project_settings(db, project)
        resolved_settings = resolve_manager_settings(project, settings_record)
        latest_plan = self._latest_plan(db, project.id)
        docs_path = project.docs_path or str(self._project_docs_dir(project))
        requested_mode = project.manager_mode or DEFAULT_MANAGER_MODE

        if requested_mode == "deterministic" or resolved_settings.runner_mode == "dry_run":
            manager_agent.active_model = resolved_settings.effective_model_label
            manager_agent.active_reasoning_effort = resolved_settings.effective_reasoning_label
            manager_agent.active_runner_type = resolved_settings.runner_mode
            manager_agent.current_action = action_name
            self.events.publish(db, project.id, "manager.mode.deterministic", {"action": action_name})
            return fallback_factory(), "deterministic"

        try_codex = requested_mode in {"codex", "auto"}
        if try_codex:
            try:
                runner = await self.runners.get_runner(resolved_settings.runner_mode)
                prompt = manager_action_prompt(
                    project,
                    docs_path,
                    action=action_name,
                    objective=objective,
                    response_schema=response_schema,
                    payload=payload,
                    plan_markdown=latest_plan.content_markdown if latest_plan else None,
                )
                manager_agent.status = "working"
                self._cache_agent_run_profile(manager_agent, resolved_settings, runner_type=runner.runner_type, action=action_name)
                handle, last_payload = await runner.run_manager_turn(
                    RunnerContext(
                        project=project,
                        agent=manager_agent,
                        task=None,
                        docs_path=docs_path,
                        plan_markdown=latest_plan.content_markdown if latest_plan else None,
                        settings=self._runner_settings_payload(resolved_settings),
                    ),
                    prompt,
                )
                manager_agent.status = "idle"
                if handle.session_ref:
                    manager_agent.session_ref = handle.session_ref
                self.events.publish(
                    db,
                    project.id,
                    "manager.mode.codex",
                    {
                        "action": action_name,
                        "runner": handle.runner_type,
                        "logs_path": handle.logs_path,
                        "effective_settings": resolved_run_settings_payload(resolved_settings),
                    },
                )
                text = ""
                if last_payload and isinstance(last_payload.get("item"), dict):
                    text = last_payload["item"].get("text", "")
                elif last_payload:
                    text = str(last_payload.get("text", ""))
                parsed, repaired = runner.try_parse_json_payload(text)
                if repaired:
                    self.events.publish(db, project.id, "manager.parse_repair_attempted", {"action": action_name})
                if parsed is not None:
                    return _validate_model(model_schema, parsed), "codex"
                self.events.publish(db, project.id, "manager.parse_failed", {"action": action_name})
            except (ValidationError, ValueError, RuntimeError) as exc:
                self.events.publish(db, project.id, "manager.parse_failed", {"action": action_name, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                self.events.publish(db, project.id, "manager.parse_failed", {"action": action_name, "error": str(exc)})
            self.events.publish(db, project.id, "manager.mode.fallback", {"action": action_name})

        manager_agent.active_model = resolved_settings.effective_model_label
        manager_agent.active_reasoning_effort = resolved_settings.effective_reasoning_label
        manager_agent.active_runner_type = resolved_settings.runner_mode
        manager_agent.current_action = action_name
        self.events.publish(db, project.id, "manager.mode.deterministic", {"action": action_name})
        return fallback_factory(), "deterministic"

    async def get_system_status(self, db: Session, project: Project | None = None) -> dict[str, Any]:
        from system_status import detect_codex_status

        status = detect_codex_status()
        status["current_auth_job"] = auth_service.job_payload(auth_service.current_job())
        status["app_server_handshake_status"] = "available" if await self.runners.app_server_available() else "unavailable"
        active_runs = list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.finished_at.is_(None))
                .order_by(AgentRun.started_at.desc())
            )
        )
        status["active_runs"] = [
            {
                "run_id": run.id,
                "agent_id": run.agent_id,
                "task_id": run.task_id,
                "runner_type": run.runner_type,
                "status": run.status,
                "effective_settings": run.effective_settings_json or {},
            }
            for run in active_runs
        ]
        if project:
            settings = self._project_settings(db, project)
            status["current_settings_summary"] = settings_summary(settings)
            status["selected_manager_model"] = settings.manager_model
            status["selected_default_worker_model"] = settings.default_worker_model
            status["effective_runner_mode"] = (
                await self.runners.effective_auto_mode()
                if settings.runner_mode == "auto"
                else settings.runner_mode
            )
        else:
            status["effective_runner_mode"] = await self.runners.effective_auto_mode()
        return status

    def auth_state(self) -> dict[str, Any]:
        from system_status import detect_codex_status

        status = detect_codex_status()
        return {
            "authenticated": status["authenticated"],
            "auth_mode": status["auth_mode"],
            "login_status": status["login_status"],
            "cli_detected": status["cli_detected"],
            "current_job": auth_service.job_payload(auth_service.current_job()),
            "chatgpt_supported": status["cli_detected"],
            "device_auth_supported": status["cli_detected"],
            "api_key_supported": status["cli_detected"],
            "notes": [
                "ChatGPT sign-in is the recommended path and keeps usage tied to your local Codex session.",
                "API key login is optional and can use API billing depending on your account.",
            ],
        }

    def create_project(self, db: Session, *, name: str, idea: str, workspace_path: str, runner_mode: str, manager_mode: str) -> Project:
        project = Project(
            name=name,
            idea=idea,
            workspace_path=workspace_path,
            status="draft",
            runner_mode=runner_mode or DEFAULT_RUNNER_MODE,
            manager_mode=manager_mode or DEFAULT_MANAGER_MODE,
        )
        db.add(project)
        db.flush()
        self._project_settings(db, project)
        manager_agent = Agent(
            project_id=project.id,
            name="Manager AI",
            role="Project orchestration, planning, routing, and final handoff",
            kind="manager",
            status="idle",
            workspace_path=workspace_path,
            failure_count=0,
            locked_paths_json=[],
        )
        db.add(manager_agent)
        db.flush()
        self.events.publish(db, project.id, "project.created", {"project_id": project.id, "name": project.name})
        return project

    def update_settings(self, db: Session, project: Project, payload: ProjectSettingsUpdate) -> ProjectSettings:
        settings = get_or_create_project_settings(db, project)
        settings.manager_model = payload.manager_model.strip() if payload.manager_model and payload.manager_model.strip() else None
        settings.default_worker_model = payload.default_worker_model.strip() if payload.default_worker_model and payload.default_worker_model.strip() else None
        settings.manager_reasoning_effort = payload.manager_reasoning_effort
        settings.default_worker_reasoning_effort = payload.default_worker_reasoning_effort
        settings.per_role_model_overrides_json = {
            key: value.strip()
            for key, value in payload.per_role_model_overrides_json.items()
            if key.strip() and value.strip()
        }
        settings.per_role_reasoning_overrides_json = {
            key: value
            for key, value in payload.per_role_reasoning_overrides_json.items()
            if key.strip() and value
        }
        settings.runner_mode = payload.runner_mode
        settings.sandbox_mode = payload.sandbox_mode
        settings.approval_policy = payload.approval_policy
        project.runner_mode = payload.runner_mode
        self.events.publish(
            db,
            project.id,
            "settings.updated",
            {
                "project_id": project.id,
                "runner_mode": settings.runner_mode,
                "manager_model": settings.manager_model or "Codex default",
                "default_worker_model": settings.default_worker_model or "Codex default",
            },
        )
        db.flush()
        return settings

    async def generate_project_docs(self, db: Session, project: Project) -> dict[str, Any]:
        docs_dir = self._ensure_project_workspace(project)
        latest_plan_record = self._latest_plan(db, project.id)
        latest_session = self._latest_session(db, project.id)
        deterministic_plan = None
        if latest_plan_record and latest_plan_record.summary_json:
            deterministic_plan = ManagerPlan(
                refined_summary=latest_plan_record.summary_json.get("refined_summary", project.idea),
                mvp_scope=latest_plan_record.summary_json.get("mvp_scope", []),
                milestones=latest_plan_record.summary_json.get("milestones", []),
                recommended_architecture=latest_plan_record.summary_json.get("recommended_architecture", []),
                agent_roster=latest_plan_record.summary_json.get("agent_roster", []),
                task_breakdown=latest_plan_record.summary_json.get("task_breakdown", []),
                validation_plan=latest_plan_record.summary_json.get("validation_plan", []),
                risks=latest_plan_record.summary_json.get("risks", []),
                definition_of_done=latest_plan_record.summary_json.get("definition_of_done", []),
                content_markdown=latest_plan_record.content_markdown,
                summary_json=latest_plan_record.summary_json,
            )
        questions = list(sorted(latest_session.questions, key=lambda item: item.index)) if latest_session else []
        doc_update, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="docs.generate",
            objective="Generate or rewrite the local planning docs for the current project state.",
            response_schema=MANAGER_DOC_UPDATE_SCHEMA,
            payload={
                "project_name": project.name,
                "project_idea": project.idea,
                "interview_answers": [question.selected_text for question in questions if question.selected_text],
            },
            model_schema=ManagerDocUpdate,
            fallback_factory=lambda: self._deterministic_doc_update(project, questions, deterministic_plan),
        )
        files_written: list[str] = []
        for item in doc_update.files:
            (docs_dir / item.filename).write_text(item.content, encoding="utf-8")
            files_written.append(item.filename)
        docs_manifest_path(project).write_text(
            json.dumps(
                {
                    "generated_at": utc_now().isoformat(),
                    "files": sorted(files_written),
                    "manager_mode_used": manager_mode_used,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        project.status = "docs_ready"
        project.updated_at = utc_now()
        self.events.publish(
            db,
            project.id,
            "docs.generated",
            {"docs_path": str(docs_dir), "files": sorted(files_written), "manager_mode_used": manager_mode_used},
        )
        return {
            "docs_path": str(docs_dir),
            "files": sorted(files_written),
            "used_live_manager": manager_mode_used == "codex",
            "manager_mode_used": manager_mode_used,
        }

    async def start_interview(self, db: Session, project: Project, question_count: int) -> InterviewSession:
        previous_sessions = list(db.scalars(select(InterviewSession).where(InterviewSession.project_id == project.id)))
        for previous in previous_sessions:
            previous.status = "superseded"

        payload, _ = await self._resolve_manager_model(
            db,
            project,
            action_name="interview.generate",
            objective="Generate concise multiple-choice interview questions for project refinement.",
            response_schema={"questions": [{"question": "string", "options": [{"id": "string", "label": "string", "description": "string"}]}]},
            payload={"question_count": question_count, "idea": project.idea},
            model_schema=InterviewGeneration,
            fallback_factory=lambda: InterviewGeneration(questions=self._deterministic_interview_payload(question_count)["questions"]),
        )
        generated_questions = payload.questions or self._deterministic_interview_payload(question_count)["questions"]

        session = InterviewSession(project_id=project.id, question_count=question_count, current_index=0, status="in_progress")
        db.add(session)
        db.flush()
        for index, template in enumerate(generated_questions):
            db.add(
                InterviewQuestion(
                    session_id=session.id,
                    index=index,
                    question=template["question"],
                    options_json=template["options"],
                )
            )
        project.status = "interview_in_progress"
        self.events.publish(db, project.id, "interview.started", {"session_id": session.id, "question_count": question_count})
        return session

    def answer_interview(self, db: Session, session: InterviewSession, question_id: int, option_id: str, selected_text: str) -> InterviewSession:
        question = db.get(InterviewQuestion, question_id)
        if not question or question.session_id != session.id:
            raise ValueError("Question not found")
        question.selected_option = option_id
        question.selected_text = selected_text
        question.rationale = f"Selected during interview flow: {selected_text}"
        answered = len([item for item in session.questions if item.selected_option])
        session.current_index = min(answered, session.question_count - 1)
        if answered >= session.question_count:
            session.status = "completed"
            project = db.get(Project, session.project_id)
            if project:
                project.status = "interview_complete"
        self.events.publish(db, session.project_id, "interview.answered", {"session_id": session.id, "question_id": question_id, "option_id": option_id})
        return session

    async def generate_plan(self, db: Session, project: Project, action_bias: str | None = None, note: str | None = None) -> Plan:
        latest_session = self._latest_session(db, project.id)
        if not latest_session:
            raise ValueError("Interview session required before plan generation")
        questions = list(sorted(latest_session.questions, key=lambda item: item.index))
        manager_plan, _ = await self._resolve_manager_model(
            db,
            project,
            action_name="plan.generate",
            objective="Synthesize the interview into a practical MVP plan.",
            response_schema=MANAGER_PLAN_SCHEMA,
            payload={
                "project_name": project.name,
                "project_idea": project.idea,
                "answers": [question.selected_text for question in questions if question.selected_text],
                "action_bias": action_bias,
                "note": note,
            },
            model_schema=ManagerPlan,
            fallback_factory=lambda: self._deterministic_plan(project, questions, action_bias=action_bias, note=note),
        )
        next_version = (db.scalar(select(func.max(Plan.version)).where(Plan.project_id == project.id)) or 0) + 1
        for old_plan in db.scalars(select(Plan).where(Plan.project_id == project.id)):
            old_plan.status = "superseded"
        plan = Plan(
            project_id=project.id,
            version=next_version,
            content_markdown=manager_plan.content_markdown,
            status="pending_approval",
            summary_json=manager_plan.summary_json,
        )
        db.add(plan)
        project.status = "plan_ready"
        self.events.publish(db, project.id, "plan.generated", {"plan_id": plan.id, "version": next_version})
        return plan

    def initialize_build_roster(self, db: Session, project: Project) -> list[Agent]:
        existing_workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker")))
        if existing_workers:
            return existing_workers

        project_root_name = Path(project.workspace_path).name or f"project-{project.id}"
        worktree_base = WORKTREE_ROOT / f"{project.id}-{project_root_name}"
        worktree_base.mkdir(parents=True, exist_ok=True)
        roles = [
            ("Builder Agent A", "Primary implementation"),
            ("Builder Agent B", "Secondary implementation"),
            ("Validation Agent", "Validation, docs, and handoff"),
        ]
        created: list[Agent] = []
        for index, (name, role) in enumerate(roles, start=1):
            workspace = worktree_base / f"agent-{index}"
            workspace.mkdir(parents=True, exist_ok=True)
            agent = Agent(
                project_id=project.id,
                name=name,
                role=role,
                kind="worker",
                status="idle",
                workspace_path=str(workspace),
                locked_paths_json=[],
                failure_count=0,
            )
            db.add(agent)
            created.append(agent)
        db.flush()
        return created

    async def generate_tasks(self, db: Session, project: Project) -> tuple[list[Task], str]:
        latest_plan = self._latest_plan(db, project.id)
        decomposition, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="tasks.decompose",
            objective="Break the approved plan into milestone-based worker tasks with non-overlapping path hints.",
            response_schema=MANAGER_TASK_DECOMPOSITION_SCHEMA,
            payload={
                "plan_summary": latest_plan.summary_json if latest_plan else {},
                "plan_markdown": latest_plan.content_markdown if latest_plan else "",
            },
            model_schema=ManagerTaskDecomposition,
            fallback_factory=lambda: self._deterministic_task_decomposition(project, latest_plan),
        )
        tasks = self._upsert_tasks_from_decomposition(db, project, decomposition)
        self.events.publish(db, project.id, "tasks.generated", {"count": len(tasks), "manager_mode_used": manager_mode_used})
        self._write_task_board_doc(db, project)
        return tasks, manager_mode_used

    def _upsert_tasks_from_decomposition(self, db: Session, project: Project, decomposition: ManagerTaskDecomposition) -> list[Task]:
        existing = {task.title: task for task in db.scalars(select(Task).where(Task.project_id == project.id))}
        ordered: list[Task] = []
        index_map: dict[int, Task] = {}
        for index, item in enumerate(decomposition.tasks, start=1):
            task = existing.get(item.title)
            if task is None:
                task = Task(project_id=project.id, title=item.title, goal=item.goal, scope=item.scope)
                db.add(task)
            if task.status in {"backlog", "assigned", "waiting_on_paths"}:
                task.goal = item.goal
                task.scope = item.scope
                task.agent_role = item.agent_role
                task.milestone = item.milestone
                task.allowed_paths_json = item.allowed_paths
                task.forbidden_paths_json = item.forbidden_paths
                task.validation_steps_json = item.validation_steps
                task.success_criteria_json = item.success_criteria
                task.estimated_complexity = item.estimated_complexity
                task.priority = item.priority
                task.status = item.status
                task.waiting_reason = None
            ordered.append(task)
            index_map[index] = task
        db.flush()
        for index, item in enumerate(decomposition.tasks, start=1):
            resolved = [index_map[dependency].id for dependency in item.dependencies if dependency in index_map]
            index_map[index].dependencies_json = resolved
        db.flush()
        return ordered

    async def approve_plan(self, db: Session, project: Project, action: str, note: str | None) -> Plan:
        latest_plan = self._latest_plan(db, project.id)
        if not latest_plan:
            raise ValueError("Plan not found")
        if action != "approve_build":
            return await self.generate_plan(db, project, action_bias=action, note=note)

        latest_plan.status = "approved"
        project.status = "building"
        self.initialize_build_roster(db, project)
        await self.generate_tasks(db, project)
        self.events.publish(db, project.id, "plan.approved", {"plan_id": latest_plan.id, "action": action})
        await self.start_idle_agents(db, project)
        return latest_plan

    def _agent_matches_task(self, agent: Agent, task: Task) -> bool:
        if agent.kind != "worker":
            return False
        if not task.agent_role:
            return True
        agent_name = agent.name.lower()
        agent_role = agent.role.lower()
        task_role = task.agent_role.lower()
        if "validation" in task_role:
            return "validation" in agent_role
        if "secondary" in task_role:
            return "secondary" in agent_role or "agent b" in agent_name
        if "primary" in task_role:
            return "primary" in agent_role or "agent a" in agent_name
        return task_role in agent_role or task_role in agent_name

    def _dependencies_met(self, db: Session, task: Task) -> bool:
        if not task.dependencies_json:
            return True
        dependency_tasks = list(db.scalars(select(Task).where(Task.id.in_(task.dependencies_json))))
        return len(dependency_tasks) == len(task.dependencies_json) and all(item.status == "done" for item in dependency_tasks)

    def _is_git_workspace(self, project: Project) -> bool:
        return (Path(project.workspace_path) / ".git").exists()

    def _active_reservations(self, db: Session, project_id: int) -> list[PathReservation]:
        return list(
            db.scalars(
                select(PathReservation)
                .where(PathReservation.project_id == project_id, PathReservation.released_at.is_(None))
                .order_by(PathReservation.id.asc())
            )
        )

    def _refresh_agent_locks(self, db: Session, project_id: int) -> None:
        reservations = self._active_reservations(db, project_id)
        reserved_by_agent: dict[int, list[str]] = {}
        for reservation in reservations:
            reserved_by_agent.setdefault(reservation.agent_id, []).append(reservation.path)
        for agent in db.scalars(select(Agent).where(Agent.project_id == project_id, Agent.kind == "worker")):
            agent.locked_paths_json = reserved_by_agent.get(agent.id, [])

    def _reserve_task_paths(self, db: Session, project: Project, agent: Agent, task: Task) -> None:
        self._release_reservations(db, project.id, task_id=task.id, agent_id=agent.id, publish=False)
        for path in task.allowed_paths_json:
            db.add(PathReservation(project_id=project.id, task_id=task.id, agent_id=agent.id, path=path))
        db.flush()
        self._refresh_agent_locks(db, project.id)
        self.events.publish(db, project.id, "paths.reserved", {"agent_id": agent.id, "task_id": task.id, "paths": task.allowed_paths_json})

    def _release_reservations(
        self,
        db: Session,
        project_id: int,
        *,
        task_id: int | None = None,
        agent_id: int | None = None,
        publish: bool = True,
    ) -> None:
        query = select(PathReservation).where(PathReservation.project_id == project_id, PathReservation.released_at.is_(None))
        if task_id is not None:
            query = query.where(PathReservation.task_id == task_id)
        if agent_id is not None:
            query = query.where(PathReservation.agent_id == agent_id)
        released = list(db.scalars(query))
        if not released:
            return
        now = utc_now()
        for reservation in released:
            reservation.released_at = now
        self._refresh_agent_locks(db, project_id)
        if publish:
            self.events.publish(
                db,
                project_id,
                "paths.released",
                {"task_id": task_id, "agent_id": agent_id, "paths": [reservation.path for reservation in released]},
            )

    def list_reservations(self, db: Session, project_id: int) -> list[PathReservation]:
        return self._active_reservations(db, project_id)

    def _set_waiting_on_paths(self, db: Session, project: Project, task: Task, workers: list[Agent]) -> None:
        blockers = conflicting_agents(task, workers)
        if not blockers:
            task.waiting_reason = None
            if task.status == "waiting_on_paths":
                task.status = "backlog"
            return
        task.status = "waiting_on_paths"
        task.waiting_reason = "; ".join(
            f"{other.name} owns {', '.join(other.locked_paths_json or [])}" for other in blockers
        )
        self.events.publish(
            db,
            project.id,
            "task.waiting_on_paths",
            {"task_id": task.id, "blocking_agents": [other.id for other in blockers], "reason": task.waiting_reason},
        )

    def _find_next_safe_task(self, db: Session, project: Project, agent: Agent) -> Task | None:
        workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker").order_by(Agent.id.asc())))
        for task in db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())):
            if task.id == agent.current_task_id:
                continue
            if task.status not in TASK_STARTABLE_STATUSES:
                continue
            if not self._agent_matches_task(agent, task):
                continue
            if not self._dependencies_met(db, task):
                continue
            if can_assign_task(agent, task, workers, self._is_git_workspace(project)):
                return task
        return None

    async def start_idle_agents(self, db: Session, project: Project) -> None:
        workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker").order_by(Agent.id.asc())))
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        is_git_workspace = self._is_git_workspace(project)
        for task in tasks:
            if task.status in TASK_STARTABLE_STATUSES and not self._dependencies_met(db, task):
                task.status = "assigned"
                task.waiting_reason = "Waiting for task dependencies to finish."
        for agent in workers:
            if agent.status not in {"idle", "waiting", "done", "stopped"}:
                continue
            for task in tasks:
                if task.status not in TASK_STARTABLE_STATUSES:
                    continue
                if not self._agent_matches_task(agent, task) or not self._dependencies_met(db, task):
                    continue
                if can_assign_task(agent, task, workers, is_git_workspace):
                    await self.start_agent_task(db, project, agent, task)
                    break
                self._set_waiting_on_paths(db, project, task, workers)

    async def start_agent_task(self, db: Session, project: Project, agent: Agent, task: Task) -> AgentRun:
        settings_record = self._project_settings(db, project)
        resolved_settings = resolve_worker_settings(project, settings_record, agent)
        latest_plan = self._latest_plan(db, project.id)
        runner = await self.runners.get_runner(resolved_settings.runner_mode)
        context = RunnerContext(
            project=project,
            agent=agent,
            task=task,
            docs_path=project.docs_path or str(self._project_docs_dir(project)),
            plan_markdown=latest_plan.content_markdown if latest_plan else None,
            settings=self._runner_settings_payload(resolved_settings),
        )
        handle = await runner.start_task(context)
        agent.status = "starting"
        agent.current_task_id = task.id
        self._cache_agent_run_profile(agent, resolved_settings, runner_type=handle.runner_type, action=task.title)
        task.status = "working"
        task.assigned_agent_id = agent.id
        task.waiting_reason = None
        self._reserve_task_paths(db, project, agent, task)
        run = AgentRun(
            agent_id=agent.id,
            task_id=task.id,
            runner_type=handle.runner_type,
            process_ref=handle.id,
            status="starting",
            logs_path=handle.logs_path,
            stdout_path=handle.stdout_path,
            stderr_path=handle.stderr_path,
            event_log_path=handle.event_log_path,
            manager_action="worker_task",
            effective_settings_json=resolved_run_settings_payload(resolved_settings),
        )
        db.add(run)
        db.flush()
        self.events.publish(
            db,
            project.id,
            "agent.started",
            {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "task_id": task.id,
                "task_title": task.title,
                "runner": handle.runner_type,
                "reserved_paths": task.allowed_paths_json,
                "effective_settings": resolved_run_settings_payload(resolved_settings),
            },
        )
        self.active_monitors[run.id] = asyncio.create_task(self._monitor_run(run.id))
        return run

    async def _monitor_run(self, run_id: int) -> None:
        from db import session_scope

        while True:
            await asyncio.sleep(0.6)
            with session_scope() as db:
                run = db.get(AgentRun, run_id)
                if not run:
                    return
                agent = db.get(Agent, run.agent_id)
                if not agent:
                    return
                project = db.get(Project, agent.project_id)
                if not project:
                    return
                runner = await self.runners.get_runner(run.runner_type)
                events = await runner.read_events(run.process_ref or "")
                for event in events:
                    self.events.publish(db, project.id, f"runner.{event.get('type', 'unknown')}", {"agent_id": agent.id, "task_id": run.task_id, "event": event})
                    if event.get("type") == "thread.started":
                        agent.session_ref = event.get("thread_id")
                    if event.get("type") == "turn.started":
                        agent.status = "working"
                        run.status = "working"
                    effective_settings = event.get("effective_settings")
                    if isinstance(effective_settings, dict):
                        run.effective_settings_json = effective_settings
                        agent.active_model = str(effective_settings.get("model") or agent.active_model or "Codex default")
                        agent.active_reasoning_effort = str(effective_settings.get("reasoning_effort") or agent.active_reasoning_effort or "Codex default")
                        agent.active_runner_type = run.runner_type
                    item = event.get("item")
                    if isinstance(item, dict) and item.get("type") == "agent_message":
                        report = runner.try_parse_report(item.get("text"))
                        if report:
                            run.report_json = report
                    if event.get("type") in {"turn.completed", "turn.failed", "error"}:
                        run.status = await runner.get_status(run.process_ref or "")
                status = await runner.get_status(run.process_ref or "")
                if hasattr(runner, "runs") and run.process_ref in getattr(runner, "runs"):
                    state = getattr(runner, "runs")[run.process_ref]
                    run.exit_code = getattr(state, "exit_code", None)
                    if getattr(state, "session_ref", None) and not agent.session_ref:
                        agent.session_ref = state.session_ref
                if status in {"done", "error", "blocked", "needs_review", "stopped"}:
                    await self._finalize_run(db, project, agent, run, status)
                    return

    async def _finalize_run(self, db: Session, project: Project, agent: Agent, run: AgentRun, status: str) -> None:
        task = db.get(Task, run.task_id) if run.task_id else None
        run.finished_at = utc_now()
        if task:
            report = self._build_synthetic_worker_report(agent, task, status, run.report_json)
            await self.ingest_worker_report(db, run, report)
            return
        agent.status = "waiting"
        agent.current_action = None
        run.status = status
        self.events.publish(db, project.id, "agent.finished", {"agent_id": agent.id, "task_id": run.task_id, "status": status})

    async def ingest_worker_report(self, db: Session, run: AgentRun, report: WorkerReport) -> ManagerWorkerDecision:
        agent = db.get(Agent, run.agent_id)
        if not agent:
            raise ValueError("Agent not found")
        project = db.get(Project, agent.project_id)
        if not project:
            raise ValueError("Project not found")
        task = db.get(Task, run.task_id) if run.task_id else None
        run.report_json = _dump_model(report)
        run.status = report.status
        run.finished_at = run.finished_at or utc_now()
        agent.current_task_id = None
        agent.last_report_summary = report.summary
        agent.current_action = None
        if report.status == "done":
            agent.failure_count = 0
            if task:
                task.failure_count = 0
                task.status = "done"
        elif report.status == "needs_review":
            agent.failure_count = 0
            if task:
                task.status = "needs_review"
        else:
            agent.failure_count += 1
            if task:
                task.failure_count += 1
                task.status = "blocked" if report.status == "blocked" else "assigned"
        self._release_reservations(db, project.id, task_id=task.id if task else None, agent_id=agent.id)
        agent.status = "waiting"
        self.events.publish(db, project.id, "worker.report.received", {"run_id": run.id, "task_id": run.task_id, "status": report.status, "summary": report.summary})
        decision, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="worker.decide_next",
            objective="Decide the next action after a worker completion report.",
            response_schema=MANAGER_WORKER_DECISION_SCHEMA,
            payload={
                "agent": agent.name,
                "task": {"id": task.id if task else None, "title": task.title if task else None},
                "report": _dump_model(report),
                "open_tasks": [
                    {"id": item.id, "title": item.title, "status": item.status}
                    for item in db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc()))
                ],
            },
            model_schema=ManagerWorkerDecision,
            fallback_factory=lambda: self._deterministic_worker_decision(db, project, agent, task, report),
        )
        await self._apply_worker_decision(db, project, agent, task, decision)
        self.events.publish(
            db,
            project.id,
            "manager.worker_decision",
            {"run_id": run.id, "decision": _dump_model(decision), "manager_mode_used": manager_mode_used},
        )
        await self._maybe_finalize_handoff(db, project)
        if project.status != "handoff_ready":
            await self.start_idle_agents(db, project)
        self._write_task_board_doc(db, project)
        return decision

    async def _apply_worker_decision(self, db: Session, project: Project, agent: Agent, task: Task | None, decision: ManagerWorkerDecision) -> None:
        immediate_task: Task | None = None
        agent.current_action = decision.summary_markdown
        if decision.decision_type == "assign_next_task" and decision.task_id:
            immediate_task = db.get(Task, decision.task_id)
            if immediate_task:
                immediate_task.status = "assigned"
                immediate_task.assigned_agent_id = decision.assign_to_agent_id or agent.id
        elif decision.decision_type == "request_fix":
            if decision.follow_up_title and decision.follow_up_goal:
                fix_task = Task(
                    project_id=project.id,
                    assigned_agent_id=decision.assign_to_agent_id,
                    title=decision.follow_up_title,
                    goal=decision.follow_up_goal,
                    scope="Resolve a blocker or error before the main flow can continue.",
                    agent_role="Validation, docs, and handoff" if decision.assign_to_agent_id else "Primary implementation",
                    milestone=(task.milestone if task else "Milestone 2 - Validation and handoff") if task else "Milestone 2 - Validation and handoff",
                    allowed_paths_json=task.allowed_paths_json[:] if task else ["docs", "tests"],
                    forbidden_paths_json=task.forbidden_paths_json[:] if task else [],
                    validation_steps_json=["Confirm the blocker is removed", "Record what changed"],
                    success_criteria_json=["The blocking issue is resolved or clearly isolated."],
                    estimated_complexity="small",
                    dependencies_json=[],
                    status="backlog",
                    priority=(task.priority + 1 if task else 50),
                )
                db.add(fix_task)
            elif task and task.failure_count < 2:
                task.status = "assigned"
                task.waiting_reason = "Manager requested one fix retry."
                immediate_task = task
            elif task:
                task.status = "blocked"
        elif decision.decision_type == "mark_blocked" and task:
            task.status = "blocked"
        elif decision.decision_type == "mark_done" and task:
            task.status = "done"
        elif decision.decision_type == "retire_agent":
            agent.status = "done"
        elif decision.decision_type == "escalate_to_user":
            agent.status = "waiting"
            self.events.publish(db, project.id, "manager.escalation", {"agent_id": agent.id, "task_id": task.id if task else None, "message": decision.escalation_message or decision.summary_markdown})
        else:
            agent.status = "waiting"

        if immediate_task and agent.status in {"idle", "waiting", "done", "stopped"}:
            workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker")))
            if can_assign_task(agent, immediate_task, workers, self._is_git_workspace(project)) and self._dependencies_met(db, immediate_task):
                await self.start_agent_task(db, project, agent, immediate_task)

    async def _maybe_finalize_handoff(self, db: Session, project: Project) -> None:
        open_tasks = list(db.scalars(select(Task).where(Task.project_id == project.id, Task.status.in_(list(TASK_OPEN_STATUSES)))))
        if open_tasks:
            return
        settings_record = self._project_settings(db, project)
        project_agent_ids = [project_agent.id for project_agent in db.scalars(select(Agent).where(Agent.project_id == project.id))]
        completed_runs = list(db.scalars(select(AgentRun).where(AgentRun.agent_id.in_(project_agent_ids))))
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        handoff, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="handoff.generate",
            objective="Generate the final handoff summary, run instructions, and known limitations.",
            response_schema=MANAGER_HANDOFF_SCHEMA,
            payload={
                "tasks": [{"title": task.title, "status": task.status} for task in tasks],
                "runs": [run.report_json or {} for run in completed_runs],
            },
            model_schema=ManagerHandoff,
            fallback_factory=lambda: self._deterministic_handoff(project, tasks, completed_runs),
        )
        project.status = "handoff_ready"
        project.final_report_json = _dump_model(handoff) | {
            "manager_mode_used": manager_mode_used,
            "models_used": {
                "manager_model": settings_record.manager_model or "Codex default",
                "default_worker_model": settings_record.default_worker_model or "Codex default",
                "manager_reasoning_effort": settings_record.manager_reasoning_effort or "Codex default",
                "default_worker_reasoning_effort": settings_record.default_worker_reasoning_effort or "Codex default",
                "role_model_overrides": settings_record.per_role_model_overrides_json or {},
                "role_reasoning_overrides": settings_record.per_role_reasoning_overrides_json or {},
                "effective_runs": [run.effective_settings_json or {} for run in completed_runs if run.effective_settings_json],
            },
        }
        self.events.publish(db, project.id, "project.handoff_ready", {"project_id": project.id})

    async def stop_agent(self, db: Session, agent: Agent) -> None:
        run = db.scalar(
            select(AgentRun)
            .where(AgentRun.agent_id == agent.id, AgentRun.finished_at.is_(None))
            .order_by(AgentRun.id.desc())
        )
        if not run:
            agent.status = "stopped"
            agent.current_action = None
            self._release_reservations(db, agent.project_id, agent_id=agent.id)
            return
        runner = await self.runners.get_runner(run.runner_type)
        await runner.stop_run(run.process_ref or "")
        agent.status = "stopped"
        agent.current_task_id = None
        agent.current_action = None
        run.status = "stopped"
        run.finished_at = utc_now()
        self._release_reservations(db, agent.project_id, task_id=run.task_id, agent_id=agent.id)
        self.events.publish(db, agent.project_id, "agent.stopped", {"agent_id": agent.id})

    async def pause_agent(self, db: Session, agent: Agent) -> None:
        await self.stop_agent(db, agent)
        agent.status = "waiting"
        self.events.publish(db, agent.project_id, "agent.paused", {"agent_id": agent.id})

    def read_logs(self, db: Session, agent: Agent) -> tuple[str | None, str]:
        run = db.scalar(select(AgentRun).where(AgentRun.agent_id == agent.id).order_by(AgentRun.id.desc()))
        if not run or not run.logs_path:
            return None, ""
        path = Path(run.logs_path)
        if not path.exists():
            return str(path), ""
        return str(path), path.read_text(encoding="utf-8", errors="ignore")

    async def manager_message(self, db: Session, project: Project, message: str) -> str:
        manager_agent = self._manager_agent(db, project.id)
        settings_record = self._project_settings(db, project)
        resolved_settings = resolve_manager_settings(project, settings_record)
        latest_plan = self._latest_plan(db, project.id)
        if project.manager_mode == "deterministic" or resolved_settings.runner_mode == "dry_run":
            reply = f"Manager summary: project is **{project.status}**. Open tasks: {db.scalar(select(func.count(Task.id)).where(Task.project_id == project.id, Task.status.in_(list(TASK_OPEN_STATUSES))))}."
            manager_agent.active_model = resolved_settings.effective_model_label
            manager_agent.active_reasoning_effort = resolved_settings.effective_reasoning_label
            manager_agent.active_runner_type = resolved_settings.runner_mode
            manager_agent.current_action = "message"
            self.events.publish(db, project.id, "manager.mode.deterministic", {"action": "message"})
            self.events.publish(db, project.id, "manager.message", {"message": message, "reply": reply})
            return reply
        try:
            runner = await self.runners.get_runner(resolved_settings.runner_mode)
            manager_agent.status = "working"
            self._cache_agent_run_profile(manager_agent, resolved_settings, runner_type=runner.runner_type, action="message")
            handle, last_payload = await runner.run_manager_turn(
                RunnerContext(
                    project=project,
                    agent=manager_agent,
                    task=None,
                    docs_path=project.docs_path or str(self._project_docs_dir(project)),
                    plan_markdown=latest_plan.content_markdown if latest_plan else None,
                    settings=self._runner_settings_payload(resolved_settings),
                ),
                manager_message_prompt(project, project.docs_path or str(self._project_docs_dir(project)), message),
            )
            manager_agent.status = "idle"
            manager_agent.current_action = None
            if handle.session_ref:
                manager_agent.session_ref = handle.session_ref
            reply = ""
            if last_payload and isinstance(last_payload.get("item"), dict):
                reply = last_payload["item"].get("text", "")
            elif last_payload:
                reply = str(last_payload.get("text", ""))
            if reply:
                self.events.publish(
                    db,
                    project.id,
                    "manager.mode.codex",
                    {
                        "action": "message",
                        "runner": handle.runner_type,
                        "effective_settings": resolved_run_settings_payload(resolved_settings),
                    },
                )
                self.events.publish(db, project.id, "manager.message", {"message": message, "reply": reply, "logs_path": handle.logs_path})
                return reply
        except Exception as exc:  # noqa: BLE001
            self.events.publish(db, project.id, "manager.mode.fallback", {"action": "message", "error": str(exc)})
        manager_agent.status = "idle"
        manager_agent.active_model = resolved_settings.effective_model_label
        manager_agent.active_reasoning_effort = resolved_settings.effective_reasoning_label
        manager_agent.active_runner_type = resolved_settings.runner_mode
        manager_agent.current_action = "message"
        reply = f"Manager fallback: project is **{project.status}**. Ask for next tasks or start idle agents to continue the build."
        self.events.publish(db, project.id, "manager.mode.deterministic", {"action": "message"})
        self.events.publish(db, project.id, "manager.message", {"message": message, "reply": reply})
        return reply

    async def manager_next_step(self, db: Session, project: Project) -> ManagerWorkerDecision:
        workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker").order_by(Agent.id.asc())))
        fallback_decision = ManagerWorkerDecision(decision_type="wait", summary_markdown="No safe backlog task is ready.")
        for agent in workers:
            if agent.status not in {"idle", "waiting", "done", "stopped"}:
                continue
            task = self._find_next_safe_task(db, project, agent)
            if task:
                fallback_decision = ManagerWorkerDecision(
                    decision_type="assign_next_task",
                    summary_markdown=f"Route **{task.title}** to {agent.name}.",
                    task_id=task.id,
                    assign_to_agent_id=agent.id,
                )
                break
        decision, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="manager.next_step",
            objective="Re-evaluate the backlog and choose the next safe task assignment.",
            response_schema=MANAGER_WORKER_DECISION_SCHEMA,
            payload={
                "workers": [{"id": agent.id, "name": agent.name, "status": agent.status} for agent in workers],
                "tasks": [
                    {"id": task.id, "title": task.title, "status": task.status, "waiting_reason": task.waiting_reason}
                    for task in db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc()))
                ],
            },
            model_schema=ManagerWorkerDecision,
            fallback_factory=lambda: fallback_decision,
        )
        self.events.publish(db, project.id, "manager.worker_decision", {"decision": _dump_model(decision), "manager_mode_used": manager_mode_used})
        await self.start_idle_agents(db, project)
        return decision

    def _write_task_board_doc(self, db: Session, project: Project) -> None:
        docs_dir = self._ensure_project_workspace(project)
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        (docs_dir / "TASK_BOARD.md").write_text(self._task_board_markdown(tasks), encoding="utf-8")


service = MissionControlService()
