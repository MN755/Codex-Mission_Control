from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from daemon_state import daemon_dashboard_url, ensure_daemon_token, read_daemon_metadata, resolve_backend_binding
from db import SessionLocal
from errors import MissionControlError
from imported_codebase import import_service
from manager import service
from models import (
    Agent,
    AgentRun,
    ApprovalRequest,
    ChangeRequest,
    ManagerQuestion,
    OrchestrationEvent,
    OrchestrationSession,
    PendingDecision,
    Project,
    ProjectEvent,
    Task,
    utc_now,
)
from security.path_validation import PathValidationError, resolve_local_path


ACTIVE_ORCHESTRATION_STATUSES = {"initializing", "planning", "waiting_for_user", "running", "paused"}
MAX_BACKGROUND_FAILURES = 3
OPEN_TASK_STATUSES = {"backlog", "assigned", "working", "waiting_on_paths", "needs_review", "blocked"}


class OrchestrationCoordinator:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._task_metadata: dict[int, dict[str, Any]] = {}

    @staticmethod
    def _is_ephemeral_test_workspace(raw_path: str | None) -> bool:
        normalized = str(raw_path or "").replace("\\", "/").lower()
        if "/.runtime-test-runs/" not in normalized and not normalized.endswith("/.runtime-test-runs"):
            return False
        current_runtime_root = str(os.environ.get("MISSION_CONTROL_RUNTIME_ROOT") or "").replace("\\", "/").lower().rstrip("/")
        if current_runtime_root and normalized.startswith(current_runtime_root):
            return False
        return True

    def on_startup(self) -> None:
        ensure_daemon_token()
        resume_after_restart: list[int] = []
        with SessionLocal() as db:
            active = list(
                db.scalars(
                    select(OrchestrationSession).where(
                        OrchestrationSession.status.in_(["initializing", "planning", "running", "waiting_for_user"])
                    )
                )
            )
            changed = False
            for session in active:
                project = db.get(Project, session.project_id)
                workspace_path = session.workspace_path or (project.workspace_path if project is not None else None)
                if self._is_ephemeral_test_workspace(workspace_path):
                    session.status = "paused"
                    session.manager_status = (
                        "Daemon restarted. Mission Control left this ephemeral test workspace paused instead of auto-resuming it."
                    )
                    self._record_event(
                        db,
                        session,
                        "orchestration_reconciled_after_restart",
                        {
                            "orchestration_id": session.id,
                            "status": session.status,
                            "auto_resumed": False,
                            "ephemeral_workspace": True,
                        },
                    )
                    changed = True
                    continue
                should_auto_resume = session.status in {"initializing", "planning", "running"}
                if should_auto_resume:
                    session.status = "planning"
                    session.manager_status = "Daemon restarted. Mission Control is automatically resuming background work."
                    resume_after_restart.append(session.id)
                else:
                    session.status = "waiting_for_user"
                    session.manager_status = "Daemon restarted. Mission Control is still waiting for a user decision."
                self._record_event(
                    db,
                    session,
                    "orchestration_reconciled_after_restart",
                    {
                        "orchestration_id": session.id,
                        "status": session.status,
                        "auto_resumed": should_auto_resume,
                    },
                )
                changed = True
            if changed:
                db.commit()
        for orchestration_id in resume_after_restart:
            self._schedule_background_turn(orchestration_id, "daemon_restart")

    async def on_shutdown(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        self._task_metadata.clear()
        if not tasks:
            return
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _serialize_session(self, session: OrchestrationSession) -> dict[str, Any]:
        return {
            "id": session.id,
            "project_id": session.project_id,
            "workspace_path": session.workspace_path,
            "source": session.source,
            "user_request": session.user_request,
            "status": session.status,
            "manager_status": session.manager_status,
            "mode": session.mode,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "completed_at": session.completed_at,
            "metadata_json": dict(session.metadata_json or {}),
        }

    def _serialize_event(self, event: OrchestrationEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "orchestration_id": event.orchestration_id,
            "project_id": event.project_id,
            "event_type": event.event_type,
            "payload_json": dict(event.payload_json or {}),
            "created_at": event.created_at,
        }

    def _serialize_pending_decision(self, decision: PendingDecision) -> dict[str, Any]:
        return {
            "id": decision.id,
            "project_id": decision.project_id,
            "orchestration_id": decision.orchestration_id,
            "decision_type": decision.decision_type,
            "title": decision.title,
            "message": decision.message,
            "risk_level": decision.risk_level,
            "options": list(decision.options_json or []),
            "recommended_option": decision.recommended_option,
            "status": decision.status,
            "created_at": decision.created_at,
            "presentation": dict(decision.presentation_json or {}) if decision.presentation_json else None,
            "related_agent_id": decision.requesting_agent_id,
            "related_task_id": decision.related_task_id,
        }

    def _normalize_workspace(self, workspace_path: str) -> Path:
        try:
            return resolve_local_path(workspace_path)
        except PathValidationError as exc:
            raise ValueError(str(exc)) from exc

    @staticmethod
    def _path_matches_workspace(raw_path: str | None, workspace: Path) -> bool:
        if not raw_path:
            return False
        try:
            return resolve_local_path(raw_path) == workspace
        except PathValidationError:
            return False

    @staticmethod
    def _classify_background_failure(exc: Exception) -> str:
        message = f"{type(exc).__name__}: {exc}".lower()
        if "approval denied" in message or "denied" in message and "approval" in message:
            return "approval_denied"
        if any(token in message for token in ("auth", "api key", "login", "token", "credential")):
            return "user_action_required"
        if any(token in message for token in ("database is locked", "timeout", "temporar", "connection", "network", "rate limit", "usage limit", "quota")):
            return "transient"
        if any(token in message for token in ("invalid", "schema", "json", "parse", "pathvalidationerror", "not found", "workspace")):
            return "input_error"
        if any(token in message for token in ("gpu", "cluster", "kubernetes", "pod pending", "infra", "resource unavailable")):
            return "infra_blocker"
        return "runner_bug"

    @staticmethod
    def _retryable_failure_classification(classification: str) -> bool:
        return classification in {"transient", "infra_blocker"}

    def _workspace_projects(self, db: Session, workspace: Path) -> list[Project]:
        candidates = list(
            db.scalars(
                select(Project).order_by(Project.archived_at.is_not(None), Project.last_opened_at.desc(), Project.updated_at.desc(), Project.id.desc())
            )
        )
        return [
            project
            for project in candidates
            if self._path_matches_workspace(project.workspace_path, workspace) or self._path_matches_workspace(project.source_path, workspace)
        ]

    def _active_session_for_workspace(self, db: Session, workspace: Path) -> OrchestrationSession | None:
        sessions = list(
            db.scalars(
                select(OrchestrationSession)
                .where(OrchestrationSession.status.in_(list(ACTIVE_ORCHESTRATION_STATUSES)))
                .order_by(OrchestrationSession.updated_at.desc(), OrchestrationSession.id.desc())
            )
        )
        for session in sessions:
            if self._path_matches_workspace(session.workspace_path, workspace):
                return session
        return None

    def _record_event(self, db: Session, session: OrchestrationSession, event_type: str, payload: dict[str, Any]) -> OrchestrationEvent:
        event = OrchestrationEvent(
            orchestration_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            payload_json=dict(payload or {}),
        )
        db.add(event)
        db.flush()
        service.events.publish(
            db,
            session.project_id,
            f"orchestration.{event_type}",
            {"orchestration_id": session.id, **dict(payload or {})},
        )
        return event

    def _reload_session_project(
        self,
        db: Session,
        orchestration_id: int,
    ) -> tuple[OrchestrationSession | None, Project | None]:
        session = db.get(OrchestrationSession, orchestration_id)
        if session is None:
            return None, None
        project = db.get(Project, session.project_id)
        return session, project

    def _update_session_status(
        self,
        db: Session,
        session: OrchestrationSession,
        *,
        status: str,
        manager_status: str,
        completed: bool = False,
    ) -> None:
        session.status = status
        session.manager_status = manager_status
        session.updated_at = utc_now()
        if completed:
            session.completed_at = session.completed_at or utc_now()
        db.flush()

    def _candidate_project_option(self, project: Project) -> dict[str, Any]:
        label = project.name
        description = f"{project.workspace_path} · status {project.status}"
        return {"id": str(project.id), "label": label, "description": description}

    def _ensure_attach_decision(
        self,
        db: Session,
        session: OrchestrationSession,
        projects: Sequence[Project],
    ) -> PendingDecision:
        existing = db.scalar(
            select(PendingDecision)
            .where(
                PendingDecision.orchestration_id == session.id,
                PendingDecision.source_kind == "attach_workspace",
                PendingDecision.status == "pending",
            )
            .order_by(PendingDecision.id.desc())
        )
        options = [self._candidate_project_option(project) for project in projects]
        presentation = {
            "card_type": "workspace_attach_choice",
            "title": "Mission Control found multiple existing projects for this workspace.",
            "subtitle": "Pick the project Mission Control should continue.",
            "risk_level": "medium",
            "scope": session.workspace_path,
            "short_reason": "One active orchestration per workspace is enforced, so Mission Control needs an explicit project target.",
            "details": [project["description"] for project in options],
            "buttons": options,
            "preferred_style": "codex_approval_card",
        }
        metadata = dict(session.metadata_json or {})
        metadata["candidate_project_ids"] = [project.id for project in projects]
        session.metadata_json = metadata
        if existing is None:
            existing = PendingDecision(
                project_id=session.project_id,
                orchestration_id=session.id,
                decision_type="manager_question",
                title="Choose which Mission Control project should own this workspace",
                message="This folder already maps to multiple Mission Control projects.",
                risk_level="medium",
                options_json=options,
                recommended_option=str(session.project_id),
                presentation_json=presentation,
                source_kind="attach_workspace",
                source_id=session.id,
            )
            db.add(existing)
        else:
            existing.project_id = session.project_id
            existing.options_json = options
            existing.recommended_option = str(session.project_id)
            existing.presentation_json = presentation
        db.flush()
        self._record_event(
            db,
            session,
            "pending_decision_created",
            {"decision_id": existing.id, "decision_type": existing.decision_type},
        )
        return existing

    def _attach_next_action(
        self,
        *,
        orchestration: dict[str, Any] | None,
        user_action_required: bool,
        pending_decision_id: int | None,
    ) -> str:
        if user_action_required and pending_decision_id is not None:
            return "answer_pending_decision"
        if orchestration is not None:
            return "resume_orchestration" if orchestration.get("status") == "paused" else "get_status_summary"
        return "start_orchestration"

    def _build_attach_response(
        self,
        db: Session,
        *,
        project: Project,
        orchestration: OrchestrationSession | None,
        attach_outcome: str,
        reused_existing_project: bool,
        reused_existing_orchestration: bool,
        user_action_required: bool,
        pending_decision_id: int | None,
        message: str,
    ) -> dict[str, Any]:
        project_card = service._serialize_project_card(db, project)
        orchestration_payload = self._serialize_session(orchestration) if orchestration is not None else None
        return {
            "project": project_card,
            "project_id": project.id,
            "project_name": project.name,
            "source_type": project.source_type,
            "workspace_path": project.workspace_path,
            "orchestration": orchestration_payload,
            "attach_outcome": attach_outcome,
            "next_action": self._attach_next_action(
                orchestration=orchestration_payload,
                user_action_required=user_action_required,
                pending_decision_id=pending_decision_id,
            ),
            "reused_existing_project": reused_existing_project,
            "reused_existing_orchestration": reused_existing_orchestration,
            "user_action_required": user_action_required,
            "pending_decision_id": pending_decision_id,
            "message": message,
            "status_summary_markdown": None,
        }

    def attach_workspace(
        self,
        db: Session,
        *,
        workspace_path: str,
        project_name: str | None,
        mode: str,
        read_only_first: bool,
        attach_policy: str,
        source: str = "codex_plugin",
    ) -> dict[str, Any]:
        workspace = self._normalize_workspace(workspace_path)
        if not workspace.exists():
            raise ValueError("Workspace path does not exist.")
        if not workspace.is_dir():
            raise ValueError("Workspace path must be a directory.")

        active = self._active_session_for_workspace(db, workspace)
        if active is not None:
            project = db.get(Project, active.project_id)
            if project is None:
                raise ValueError("Active orchestration references a missing project.")
            self.sync_pending_decisions(db, active)
            return self._build_attach_response(
                db,
                project=project,
                orchestration=active,
                attach_outcome="reused_existing_orchestration",
                reused_existing_project=True,
                reused_existing_orchestration=True,
                user_action_required=active.status == "waiting_for_user",
                pending_decision_id=self._latest_pending_decision_id(db, active.id),
                message="Mission Control is already orchestrating this workspace. Reusing the active orchestration session.",
            )

        matches = self._workspace_projects(db, workspace)
        preferred_name = project_name.strip() if project_name and project_name.strip() else workspace.name
        is_empty = not any(workspace.iterdir())

        if matches and attach_policy != "create_new":
            if len(matches) > 1:
                exact_name_matches = [project for project in matches if project.name.strip() == preferred_name]
                if project_name and len(exact_name_matches) == 1:
                    project = exact_name_matches[0]
                    return self._build_attach_response(
                        db,
                        project=project,
                        orchestration=None,
                        attach_outcome="reused_existing_project",
                        reused_existing_project=True,
                        reused_existing_orchestration=False,
                        user_action_required=False,
                        pending_decision_id=None,
                        message="Mission Control reused the existing project selected by the provided project_name hint.",
                    )
                if project_name and len(exact_name_matches) != 1:
                    raise ValueError("Multiple projects use this workspace and project_name did not match exactly one existing project.")
                chosen = matches[0]
                session = OrchestrationSession(
                    project_id=chosen.id,
                    workspace_path=workspace.as_posix(),
                    source=source,
                    user_request="",
                    status="waiting_for_user",
                    manager_status="Waiting for the workspace/project selection decision.",
                    metadata_json={
                        "read_only_first": read_only_first,
                        "attach_mode": mode,
                        "attach_policy": attach_policy,
                    },
                )
                db.add(session)
                db.flush()
                decision = self._ensure_attach_decision(db, session, matches)
                self._record_event(db, session, "workspace_attach_ambiguous", {"candidate_project_ids": [project.id for project in matches]})
                return self._build_attach_response(
                    db,
                    project=chosen,
                    orchestration=session,
                    attach_outcome="needs_project_selection",
                    reused_existing_project=True,
                    reused_existing_orchestration=False,
                    user_action_required=True,
                    pending_decision_id=decision.id,
                    message="Mission Control found multiple existing projects for this workspace and needs a selection before continuing.",
                )
            project = matches[0]
            return self._build_attach_response(
                db,
                project=project,
                orchestration=None,
                attach_outcome="reused_existing_project",
                reused_existing_project=True,
                reused_existing_orchestration=False,
                user_action_required=False,
                pending_decision_id=None,
                message="Mission Control reused the existing project for this workspace.",
            )

        if matches and attach_policy == "create_new":
            raise ValueError("Cannot create a new project for a workspace that is already linked to existing Mission Control projects.")

        if mode == "existing_codebase" or (mode == "auto" and not is_empty):
            project = service.create_project(
                db,
                name=preferred_name,
                idea=f"Imported existing codebase from {workspace.as_posix()}.",
                workspace_path=workspace.as_posix(),
                provider="codex",
                runner_mode="auto",
                manager_mode="auto",
            )
            import_service.configure_imported_project(db, project, folder_path=workspace.as_posix(), import_mode="linked")
            if read_only_first:
                import_service.initial_scan(db, project)
            attach_outcome = "imported_existing_codebase"
            message = "Mission Control imported the existing workspace as a read-first codebase project."
        else:
            project = service.create_project(
                db,
                name=preferred_name,
                idea=f"Create and orchestrate a new project in {workspace.as_posix()}.",
                workspace_path=workspace.as_posix(),
                provider="codex",
                runner_mode="auto",
                manager_mode="auto",
            )
            service.open_project(db, project)
            attach_outcome = "created_new_project"
            message = "Mission Control created a new project for this workspace."
        return self._build_attach_response(
            db,
            project=project,
            orchestration=None,
            attach_outcome=attach_outcome,
            reused_existing_project=False,
            reused_existing_orchestration=False,
            user_action_required=False,
            pending_decision_id=None,
            message=message,
        )

    def _latest_pending_decision_id(self, db: Session, orchestration_id: int) -> int | None:
        decision = db.scalar(
            select(PendingDecision)
            .where(PendingDecision.orchestration_id == orchestration_id, PendingDecision.status == "pending")
            .order_by(PendingDecision.created_at.desc(), PendingDecision.id.desc())
        )
        return decision.id if decision else None

    def _clear_stale_review_decisions_for_fresh_reset(self, db: Session, project: Project) -> int:
        cleared = 0
        stale_review_decisions = list(
            db.scalars(
                select(PendingDecision)
                .where(
                    PendingDecision.project_id == project.id,
                    PendingDecision.status == "pending",
                    (
                        (PendingDecision.source_kind == "task_review")
                        | (PendingDecision.decision_type == "handoff_review")
                    ),
                )
                .order_by(PendingDecision.created_at.asc(), PendingDecision.id.asc())
            )
        )
        stale_review_task_ids: set[int] = set()
        for decision in stale_review_decisions:
            task_id = int(decision.source_id or decision.related_task_id or 0)
            review_task = db.get(Task, task_id) if task_id else None
            if review_task is not None and review_task.project_id == project.id and review_task.status in OPEN_TASK_STATUSES:
                stale_review_task_ids.add(review_task.id)
                assigned_agent_id = review_task.assigned_agent_id
                service._release_reservations(
                    db,
                    project.id,
                    task_id=review_task.id,
                    agent_id=assigned_agent_id,
                    publish=False,
                )
                if assigned_agent_id is not None:
                    assigned_agent = db.get(Agent, assigned_agent_id)
                    if assigned_agent is not None and assigned_agent.current_task_id == review_task.id:
                        assigned_agent.current_task_id = None
                review_task.assigned_agent_id = None
                review_task.status = "backlog"
                review_task.waiting_reason = "Fresh benchmark reset requested; stale review gate cleared for rerun."
                review_task.failure_count = 0
            decision.status = "cancelled"
            decision.answered_at = utc_now()
            decision.answer_json = {
                "option_id": "request_changes",
                "selected_text": "Request changes",
                "free_text": "Fresh benchmark reset requested; stale review gate cleared for rerun.",
            }
            cleared += 1
        stale_review_tasks = list(
            db.scalars(
                select(Task)
                .where(Task.project_id == project.id, Task.status == "needs_review")
                .order_by(Task.priority.asc(), Task.id.asc())
            )
        )
        for review_task in stale_review_tasks:
            if review_task.id in stale_review_task_ids:
                continue
            assigned_agent_id = review_task.assigned_agent_id
            service._release_reservations(
                db,
                project.id,
                task_id=review_task.id,
                agent_id=assigned_agent_id,
                publish=False,
            )
            if assigned_agent_id is not None:
                assigned_agent = db.get(Agent, assigned_agent_id)
                if assigned_agent is not None and assigned_agent.current_task_id == review_task.id:
                    assigned_agent.current_task_id = None
            review_task.assigned_agent_id = None
            review_task.status = "backlog"
            review_task.waiting_reason = "Fresh benchmark reset requested; stale review task cleared for rerun."
            review_task.failure_count = 0
            cleared += 1
        if cleared:
            db.flush()
        return cleared

    def start_orchestration(
        self,
        db: Session,
        *,
        project: Project,
        source: str,
        user_request: str,
        orchestration_id: int | None = None,
        mode: str = "unknown",
        metadata: dict[str, Any] | None = None,
        schedule_background_turn: bool = True,
    ) -> OrchestrationSession:
        workspace = self._normalize_workspace(project.workspace_path)
        session = None
        if orchestration_id is not None:
            session = db.get(OrchestrationSession, orchestration_id)
        if session is None:
            session = self._active_session_for_workspace(db, workspace)
        if session is None:
            session = OrchestrationSession(
                project_id=project.id,
                workspace_path=workspace.as_posix(),
                source=source,
                user_request=user_request.strip(),
                status="initializing",
                manager_status="Preparing the background orchestration session.",
                mode=mode,
                metadata_json={
                    "request_history": [user_request.strip()] if user_request.strip() else [],
                    **dict(metadata or {}),
                },
            )
            db.add(session)
            db.flush()
            self._record_event(db, session, "orchestration_created", {"source": source})
        else:
            session_metadata = dict(session.metadata_json or {})
            history = [str(item) for item in session_metadata.get("request_history", []) if str(item).strip()]
            if user_request.strip():
                history.append(user_request.strip())
            session_metadata["request_history"] = history[-20:]
            session_metadata.update(dict(metadata or {}))
            session.metadata_json = session_metadata
            if user_request.strip():
                session.user_request = user_request.strip()
            session.source = source
            session.mode = mode
            session.updated_at = utc_now()
            self._record_event(db, session, "orchestration_request_appended", {"source": source})
        db.flush()
        normalized_request = " ".join(user_request.strip().split()) if user_request.strip() else ""
        fresh_reset_request = bool(normalized_request) and service._request_implies_fresh_benchmark_reset(normalized_request)
        if normalized_request and project.source_type != "idea":
            change_request = service.create_change_request(db, project, normalized_request)
            if fresh_reset_request and change_request.status != "new":
                change_request.status = "new"
                change_request.classification = "bugfix"
                change_request.impact_estimate = "large"
                change_request.updated_at = utc_now()
        if fresh_reset_request:
            cleared = self._clear_stale_review_decisions_for_fresh_reset(db, project)
            if cleared:
                self._record_event(
                    db,
                    session,
                    "fresh_benchmark_reset_cleared_stale_reviews",
                    {"cleared_pending_decisions": cleared},
                )
        if schedule_background_turn:
            session.status = "planning"
            session.manager_status = "Mission Control queued the first background turn."
            session.updated_at = utc_now()
            db.flush()
            self._schedule_background_turn(session.id, "user_request")
        return session

    def get_session(self, db: Session, orchestration_id: int) -> OrchestrationSession:
        session = db.get(OrchestrationSession, orchestration_id)
        if session is None:
            raise ValueError("Orchestration session not found.")
        return session

    def get_active_session_for_project(self, db: Session, project: Project) -> OrchestrationSession | None:
        return db.scalar(
            select(OrchestrationSession)
            .where(
                OrchestrationSession.project_id == project.id,
                OrchestrationSession.status.in_(list(ACTIVE_ORCHESTRATION_STATUSES)),
            )
            .order_by(OrchestrationSession.updated_at.desc(), OrchestrationSession.id.desc())
        )

    def pause_orchestration(self, db: Session, session: OrchestrationSession) -> OrchestrationSession:
        project = db.get(Project, session.project_id)
        if project is not None and project.status != "paused":
            service.pause_project(db, project)
        self._update_session_status(db, session, status="paused", manager_status="Background orchestration paused by the user.")
        self._record_event(db, session, "orchestration_paused", {})
        return session

    def complete_orchestration(
        self,
        db: Session,
        session: OrchestrationSession,
        *,
        manager_status: str,
        event_type: str = "orchestration_completed",
        payload: dict[str, Any] | None = None,
    ) -> OrchestrationSession:
        self._update_session_status(db, session, status="completed", manager_status=manager_status, completed=True)
        self._record_event(db, session, event_type, dict(payload or {}))
        return session

    def resume_orchestration(self, db: Session, session: OrchestrationSession) -> OrchestrationSession:
        project = db.get(Project, session.project_id)
        if project is None:
            raise ValueError("Project not found for this orchestration session.")
        if project.status == "paused":
            service.resume_project(db, project)
        self._update_session_status(db, session, status="planning", manager_status="Resuming background orchestration.")
        self._record_event(db, session, "orchestration_resumed", {})
        self._schedule_background_turn(session.id, "resume")
        return session

    def list_events(self, db: Session, session: OrchestrationSession) -> list[dict[str, Any]]:
        events = list(
            db.scalars(
                select(OrchestrationEvent)
                .where(OrchestrationEvent.orchestration_id == session.id)
                .order_by(OrchestrationEvent.created_at.asc(), OrchestrationEvent.id.asc())
            )
        )
        return [self._serialize_event(event) for event in events]

    def _pending_decision_from_question(self, db: Session, session: OrchestrationSession, question: ManagerQuestion) -> PendingDecision:
        decision = db.scalar(
            select(PendingDecision)
            .where(
                PendingDecision.orchestration_id == session.id,
                PendingDecision.source_kind == "manager_question",
                PendingDecision.source_id == question.id,
            )
            .order_by(PendingDecision.id.desc())
        )
        payload = service._serialize_question(question)
        options = list(payload.get("options_json") or [])
        if decision is None:
            decision = PendingDecision(
                project_id=session.project_id,
                orchestration_id=session.id,
                decision_type="manager_question",
                title="Mission Control Manager needs a decision",
                message=question.question,
                requesting_agent_id=question.related_agent_id,
                related_task_id=question.related_task_id,
                risk_level="high" if question.impact == "high" else "medium",
                options_json=options,
                recommended_option=question.manager_recommendation,
                source_kind="manager_question",
                source_id=question.id,
            )
            db.add(decision)
        decision.project_id = session.project_id
        decision.status = "pending" if question.status == "pending" else "answered"
        decision.message = question.question
        decision.requesting_agent_id = question.related_agent_id
        decision.related_task_id = question.related_task_id
        decision.options_json = options
        decision.recommended_option = question.manager_recommendation
        decision.presentation_json = {
            "card_type": "manager_question",
            "title": "Mission Control Manager needs a decision",
            "subtitle": question.question,
            "risk_level": "high" if question.impact == "high" else "medium",
            "short_reason": question.manager_recommendation or "Answering this will unblock the manager's next step.",
            "details": [option.get("description") for option in options if option.get("description")],
            "buttons": options,
            "preferred_style": "codex_approval_card",
        }
        if question.status != "pending":
            decision.answered_at = question.resolved_at
            decision.answer_json = {
                "option_id": question.selected_option_id,
                "selected_text": question.selected_text,
                "status": question.status,
            }
        db.flush()
        return decision

    def _approval_option_label(self, option_id: str) -> str:
        return {
            "approve_once": "Approve once",
            "deny": "Deny",
            "allow_for_project": "Always allow for this project",
        }.get(option_id, option_id.replace("_", " ").title())

    def _pending_decision_from_approval(self, db: Session, session: OrchestrationSession, approval: ApprovalRequest) -> PendingDecision:
        decision = db.scalar(
            select(PendingDecision)
            .where(
                PendingDecision.orchestration_id == session.id,
                PendingDecision.source_kind == "approval_request",
                PendingDecision.source_id == approval.id,
            )
            .order_by(PendingDecision.id.desc())
        )
        options = [
            {"id": "approve_once", "label": "Approve once", "description": "Allow this one execution only."},
            {"id": "deny", "label": "Deny", "description": "Reject this action and force a safer path."},
        ]
        if approval.request_type == "command":
            options.append(
                {
                    "id": "allow_for_project",
                    "label": "Always allow for this project",
                    "description": "Allow this class of action for the current project without asking again.",
                }
            )
        if decision is None:
            decision = PendingDecision(
                project_id=session.project_id,
                orchestration_id=session.id,
                decision_type="command_approval" if approval.request_type == "command" else "tool_approval",
                title=approval.title,
                message=approval.reason_short,
                requesting_agent_id=approval.requesting_agent_id,
                related_task_id=approval.task_id,
                risk_level=approval.risk_level,
                options_json=options,
                recommended_option="approve_once",
                source_kind="approval_request",
                source_id=approval.id,
            )
            db.add(decision)
        decision.project_id = session.project_id
        decision.status = "pending" if approval.status == "pending" else "answered"
        decision.title = approval.title
        decision.message = approval.reason_short
        decision.requesting_agent_id = approval.requesting_agent_id
        decision.related_task_id = approval.task_id
        decision.risk_level = approval.risk_level
        decision.options_json = options
        decision.recommended_option = "approve_once"
        request_payload = dict(approval.request_payload_json or {})
        decision.presentation_json = {
            "card_type": "approval_request",
            "title": approval.title,
            "subtitle": approval.reason_short,
            "risk_level": approval.risk_level,
            "command": request_payload.get("command"),
            "tool": request_payload.get("tool_name"),
            "cwd": approval.cwd,
            "short_reason": approval.reason_short,
            "details": request_payload,
            "buttons": options,
            "preferred_style": "codex_approval_card",
        }
        if approval.status != "pending":
            decision.answered_at = approval.resolved_at
            decision.answer_json = {
                "option_id": approval.status,
                "selected_text": self._approval_option_label(approval.status),
                "status": approval.status,
            }
        db.flush()
        return decision

    def _pending_decision_from_review_task(self, db: Session, session: OrchestrationSession, task: Task) -> PendingDecision:
        decision = db.scalar(
            select(PendingDecision)
            .where(
                PendingDecision.orchestration_id == session.id,
                PendingDecision.source_kind == "task_review",
                PendingDecision.source_id == task.id,
            )
            .order_by(PendingDecision.id.desc())
        )
        options = [
            {"id": "approve", "label": "Approve", "description": "Mark this reviewed task complete and let Mission Control continue."},
            {"id": "request_changes", "label": "Request changes", "description": "Send this task back to backlog so Mission Control can route follow-up work."},
        ]
        summary = task.goal or task.scope or "Mission Control paused because this task reached a review gate."
        message = f"Task \"{task.title}\" needs review before Mission Control can continue."
        if decision is None:
            decision = PendingDecision(
                project_id=session.project_id,
                orchestration_id=session.id,
                decision_type="handoff_review",
                title=f"Review required: {task.title}",
                message=message,
                requesting_agent_id=task.assigned_agent_id,
                related_task_id=task.id,
                risk_level="medium",
                options_json=options,
                recommended_option="approve",
                source_kind="task_review",
                source_id=task.id,
            )
            db.add(decision)
        decision.project_id = session.project_id
        decision.status = "pending" if task.status == "needs_review" else "answered"
        decision.title = f"Review required: {task.title}"
        decision.message = message
        decision.requesting_agent_id = task.assigned_agent_id
        decision.related_task_id = task.id
        decision.risk_level = "medium"
        decision.options_json = options
        decision.recommended_option = "approve"
        decision.presentation_json = {
            "card_type": "handoff_review",
            "title": f"Review required: {task.title}",
            "subtitle": message,
            "risk_level": "medium",
            "short_reason": summary,
            "details": [
                f"Role: {task.agent_role}" if task.agent_role else None,
                f"Milestone: {task.milestone}" if task.milestone else None,
                f"Waiting reason: {task.waiting_reason}" if task.waiting_reason else None,
            ],
            "buttons": options,
            "preferred_style": "codex_approval_card",
        }
        decision.presentation_json["details"] = [item for item in decision.presentation_json["details"] if item]
        db.flush()
        return decision

    def _stale_task_review_reason(self, db: Session, decision: PendingDecision) -> str | None:
        if decision.source_kind != "task_review" and decision.decision_type != "handoff_review":
            return None
        task_id = int(decision.source_id or decision.related_task_id or 0)
        if not task_id:
            return "review decision no longer references a task"
        task = db.get(Task, task_id)
        if task is None:
            return "review task no longer exists"
        active_run_id = db.scalar(
            select(AgentRun.id)
            .where(AgentRun.task_id == task.id, AgentRun.finished_at.is_(None))
            .order_by(AgentRun.id.desc())
            .limit(1)
        )
        if active_run_id is not None:
            return "review task has an active worker run"
        if task.status != "needs_review":
            return f"review task is {task.status}, not needs_review"
        return None

    def _cancel_stale_task_review_decision(self, decision: PendingDecision, reason: str) -> None:
        decision.status = "cancelled"
        decision.answered_at = utc_now()
        decision.answer_json = {
            "option_id": "cancelled",
            "selected_text": "Cancelled stale review decision",
            "free_text": reason,
            "source": "task_review_reconciliation",
        }

    def sync_pending_decisions(self, db: Session, session: OrchestrationSession) -> list[PendingDecision]:
        project = db.get(Project, session.project_id)
        if project is None:
            raise ValueError("Project not found for orchestration session.")
        pending_questions = list(
            db.scalars(
                select(ManagerQuestion)
                .where(ManagerQuestion.project_id == project.id)
                .order_by(ManagerQuestion.created_at.asc(), ManagerQuestion.id.asc())
            )
        )
        pending_approvals = list(
            db.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.project_id == project.id)
                .order_by(ApprovalRequest.created_at.asc(), ApprovalRequest.id.asc())
            )
        )
        review_tasks = list(
            db.scalars(
                select(Task)
                .where(Task.project_id == project.id, Task.status == "needs_review")
                .order_by(Task.created_at.asc(), Task.id.asc())
            )
        )
        active_keys: set[tuple[str, int]] = set()
        for question in pending_questions:
            active_keys.add(("manager_question", question.id))
            self._pending_decision_from_question(db, session, question)
        for approval in pending_approvals:
            active_keys.add(("approval_request", approval.id))
            self._pending_decision_from_approval(db, session, approval)
        for task in review_tasks:
            active_keys.add(("task_review", task.id))
            self._pending_decision_from_review_task(db, session, task)
        existing = list(
            db.scalars(
                select(PendingDecision)
                .where(PendingDecision.orchestration_id == session.id)
                .order_by(PendingDecision.created_at.asc(), PendingDecision.id.asc())
            )
        )
        for decision in existing:
            if decision.source_kind == "attach_workspace":
                continue
            if decision.status == "pending":
                stale_review_reason = self._stale_task_review_reason(db, decision)
                if stale_review_reason is not None:
                    self._cancel_stale_task_review_decision(decision, stale_review_reason)
                    continue
            key = (decision.source_kind or "", int(decision.source_id or 0))
            if key not in active_keys and decision.status == "pending":
                decision.status = "cancelled"
                decision.answered_at = utc_now()
        db.flush()
        return list(
            db.scalars(
                select(PendingDecision)
                .where(PendingDecision.orchestration_id == session.id)
                .order_by(PendingDecision.created_at.asc(), PendingDecision.id.asc())
            )
        )

    def list_pending_decisions(self, db: Session, session: OrchestrationSession) -> list[dict[str, Any]]:
        decisions = self.sync_pending_decisions(db, session)
        return [self._serialize_pending_decision(decision) for decision in decisions if decision.status == "pending"]

    def answer_pending_decision(
        self,
        db: Session,
        decision: PendingDecision,
        *,
        option_id: str,
        selected_text: str,
        free_text: str | None = None,
    ) -> PendingDecision:
        session = db.get(OrchestrationSession, decision.orchestration_id) if decision.orchestration_id is not None else None
        if session is None and decision.source_kind not in {"manager_question", "approval_request"}:
            raise MissionControlError(
                code="MC-ORCH-SESSION-NOT-FOUND-001",
                detail="Orchestration session not found for this decision.",
                breakpoint="decision.answer",
                project_id=decision.project_id,
                orchestration_id=decision.orchestration_id,
            )
        if decision.status != "pending":
            raise MissionControlError(
                code="MC-DECISION-EXPIRED-001",
                breakpoint="decision.answer",
                project_id=decision.project_id,
                orchestration_id=decision.orchestration_id,
                safe_details={"decision_status": decision.status},
            )
        if decision.source_kind == "manager_question" and decision.source_id is not None:
            question = db.get(ManagerQuestion, decision.source_id)
            if question is None:
                raise MissionControlError(
                    code="MC-MANAGER-QUESTION-FAILED-001",
                    detail="Manager question not found.",
                    breakpoint="manager.create_pending_decision",
                    project_id=decision.project_id,
                    orchestration_id=decision.orchestration_id,
                )
            resolved_question = service.answer_question(
                db,
                question.id,
                option_id=option_id,
                selected_text=selected_text,
                project_id=question.project_id,
            )
        elif decision.source_kind == "approval_request" and decision.source_id is not None:
            approval = db.get(ApprovalRequest, decision.source_id)
            if approval is None:
                raise MissionControlError(
                    code="MC-DECISION-NOT-FOUND-001",
                    detail="Approval request not found.",
                    breakpoint="decision.answer",
                    project_id=decision.project_id,
                    orchestration_id=decision.orchestration_id,
                )
            if option_id == "approve_once":
                service.approve_once(db, approval.id, project_id=approval.project_id)
            elif option_id == "deny":
                service.deny_approval(db, approval.id, project_id=approval.project_id)
            elif option_id in {"allow_for_project", "always_allow_if_safe"}:
                service.allow_approval_for_project(db, approval.id, project_id=approval.project_id)
            else:
                raise MissionControlError(
                    code="MC-DECISION-INVALID-OPTION-001",
                    detail="Unsupported approval resolution option.",
                    breakpoint="decision.validate_option",
                    project_id=decision.project_id,
                    orchestration_id=decision.orchestration_id,
                    safe_details={"received_option": option_id},
                )
        elif decision.source_kind == "attach_workspace":
            selected_project = db.get(Project, int(option_id))
            if selected_project is None:
                raise MissionControlError(
                    code="MC-WORKSPACE-AMBIGUOUS-001",
                    detail="Selected project was not found.",
                    breakpoint="workspace.attach",
                    project_id=decision.project_id,
                    orchestration_id=decision.orchestration_id,
                    safe_details={"received_option": option_id},
                )
            session.project_id = selected_project.id
            session.workspace_path = selected_project.workspace_path
            session.manager_status = f"Workspace selection recorded for {selected_project.name}."
            metadata = dict(session.metadata_json or {})
            metadata["selected_project_id"] = selected_project.id
            session.metadata_json = metadata
        elif decision.source_kind == "task_review" and decision.source_id is not None:
            task = db.get(Task, decision.source_id)
            if task is None:
                raise MissionControlError(
                    code="MC-REVIEW-TASK-NOT-FOUND-001",
                    detail="Review task not found.",
                    breakpoint="decision.answer",
                    project_id=decision.project_id,
                    orchestration_id=decision.orchestration_id,
                )
            if option_id == "approve":
                asyncio.run(service.complete_task_by_user(db, task))
            elif option_id == "request_changes":
                project = db.get(Project, task.project_id)
                if project is None:
                    raise MissionControlError(
                        code="MC-REVIEW-TASK-PROJECT-NOT-FOUND-001",
                        detail="Project not found for review task.",
                        breakpoint="decision.answer",
                        project_id=decision.project_id,
                        orchestration_id=decision.orchestration_id,
                    )
                run = db.scalar(
                    select(AgentRun)
                    .where(AgentRun.task_id == task.id, AgentRun.finished_at.is_(None))
                    .order_by(AgentRun.id.desc())
                )
                agent = db.get(Agent, task.assigned_agent_id) if task.assigned_agent_id else None
                if run is not None:
                    run.status = "stopped"
                    run.finished_at = utc_now()
                if agent is not None:
                    agent.current_task_id = None
                    agent.current_action = None
                    if agent.status not in {"done", "retired"}:
                        agent.status = "waiting"
                task.status = "backlog"
                task.assigned_agent_id = None
                task.waiting_reason = "Review requested changes before Mission Control can continue."
                service._release_reservations(db, project.id, task_id=task.id, agent_id=agent.id if agent is not None else None)
                service.events.publish(
                    db,
                    project.id,
                    "task.review_changes_requested",
                    {"task_id": task.id, "run_id": run.id if run is not None else None},
                )
                service._schedule_orchestration_follow_up(db, project, reason="task_review_changes_requested")
            else:
                raise MissionControlError(
                    code="MC-DECISION-INVALID-OPTION-001",
                    detail="Unsupported review resolution option.",
                    breakpoint="decision.validate_option",
                    project_id=decision.project_id,
                    orchestration_id=decision.orchestration_id,
                    safe_details={"received_option": option_id},
                )
        else:
            raise MissionControlError(
                code="MC-DECISION-NOT-FOUND-001",
                detail="Unsupported pending decision source.",
                breakpoint="decision.answer",
                project_id=decision.project_id,
                orchestration_id=decision.orchestration_id,
                safe_details={"source_kind": decision.source_kind},
            )
        decision.status = "answered"
        decision.answered_at = utc_now()
        canonical_option_id = option_id
        canonical_selected_text = selected_text
        if decision.source_kind == "manager_question" and decision.source_id is not None:
            canonical_option_id = resolved_question.selected_option_id or option_id
            canonical_selected_text = resolved_question.selected_text or selected_text
        decision.answer_json = {
            "option_id": canonical_option_id,
            "selected_text": canonical_selected_text,
            "free_text": free_text,
        }
        if session is not None:
            self._record_event(
                db,
                session,
                "pending_decision_answered",
                {"decision_id": decision.id, "decision_type": decision.decision_type, "option_id": option_id},
            )
            self.sync_pending_decisions(db, session)
            if session.status != "completed":
                self._update_session_status(db, session, status="planning", manager_status="Decision recorded. Mission Control is continuing the orchestration.")
                self._schedule_background_turn(session.id, "decision_answered")
        return decision

    def _session_project_action_type(self, db: Session, session: OrchestrationSession, project: Project) -> str:
        action = asyncio.run(service.get_project_action(db, project))
        return str(action.get("type") or "no_action")

    async def get_status(self, db: Session, session: OrchestrationSession) -> dict[str, Any]:
        project = db.get(Project, session.project_id)
        if project is None:
            raise ValueError("Project not found for this orchestration session.")
        pending = self.sync_pending_decisions(db, session)
        current_action = await service.get_project_action(db, project)
        recent_events = self.list_events(db, session)[-8:]
        manager_agent = db.scalar(
            select(Agent)
            .where(Agent.project_id == project.id, Agent.kind == "manager")
            .order_by(Agent.id.asc())
        )
        manager_payload = self._serialize_runtime_agent(manager_agent)
        active_agents = [
            self._serialize_runtime_agent(agent)
            for agent in db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind != "manager").order_by(Agent.id.asc()))
            if agent.status not in {"idle", "retired", "stopped"}
        ]
        blockers: list[str] = []
        if current_action.get("type") in {"blocker", "degraded", "paused"} and current_action.get("message"):
            blockers.append(str(current_action["message"]))
        blockers.extend(
            decision.message
            for decision in pending
            if decision.status == "pending" and decision.risk_level in {"high", "critical"}
        )
        metadata = dict(session.metadata_json or {})
        if metadata.get("last_background_error") and int(metadata.get("background_failure_count") or 0) > 0:
            blockers.append(f"Last background error: {metadata['last_background_error']}")
        handoff = service.get_project_handoff_summary(db, project)
        derived_status, derived_manager_status = self._derive_runtime_state(
            db,
            session,
            project,
            pending,
            handoff_status=handoff["status"],
            current_action=current_action,
            manager_fallback=session.manager_status,
        )
        background_runtime = self._background_runtime_snapshot(session.id, metadata=metadata)
        return {
            "orchestration_id": session.id,
            "project_id": project.id,
            "project_name": project.name,
            "orchestration_status": derived_status,
            "manager_status": derived_manager_status,
            "current_phase": project.latest_milestone or project.status,
            "manager": manager_payload,
            "active_agents": active_agents,
            "pending_decisions_count": len([decision for decision in pending if decision.status == "pending"]),
            "recent_events": [
                {
                    "id": event["id"],
                    "type": event["event_type"],
                    "created_at": event["created_at"],
                    "summary": event["payload_json"],
                }
                for event in recent_events
            ],
            "current_blockers": blockers[:5],
            "next_expected_action": self._next_expected_action(current_action, pending, project, background_runtime=background_runtime),
            "user_action_required": any(decision.status == "pending" for decision in pending),
            "handoff_readiness": handoff["status"],
            "runner_inventory": service.runners.inventory_preview(),
            "background_runtime": background_runtime,
        }

    def _serialize_runtime_agent(self, agent: Agent | None) -> dict[str, Any]:
        if agent is None:
            return {}
        current_task_title = None
        if agent.current_task is not None and agent.current_task.title:
            current_task_title = agent.current_task.title
        return {
            "id": agent.id,
            "name": agent.name,
            "status": agent.status,
            "mission": agent.mission,
            "runner_type": agent.active_runner_type,
            "active_model": agent.active_model,
            "active_reasoning_effort": agent.active_reasoning_effort,
            "current_action": agent.current_action,
            "current_task_title": current_task_title,
        }

    def _next_expected_action(
        self,
        current_action: dict[str, Any],
        decisions: Sequence[PendingDecision],
        project: Project,
        *,
        background_runtime: dict[str, Any] | None = None,
    ) -> str:
        if any(decision.status == "pending" for decision in decisions):
            return "Waiting for the user to answer a Mission Control decision."
        if background_runtime and background_runtime.get("retry_scheduled"):
            return "Mission Control queued a retry after a recoverable background error."
        if background_runtime and background_runtime.get("turn_active"):
            return "Mission Control is actively running a background manager turn."
        if current_action.get("type") == "handoff_ready":
            return "Generate or review the final Mission Control handoff."
        if project.status == "paused":
            return "Resume the project to continue background orchestration."
        return "Mission Control Manager will continue routing the next safe background step."

    def _derive_runtime_state(
        self,
        db: Session,
        session: OrchestrationSession,
        project: Project,
        pending: Sequence[PendingDecision],
        *,
        handoff_status: str,
        current_action: dict[str, Any] | None = None,
        manager_fallback: str | None = None,
    ) -> tuple[str, str]:
        if any(decision.status == "pending" for decision in pending):
            return "waiting_for_user", "Mission Control is waiting for a user decision before it can continue."
        if project.status == "paused":
            return "paused", "Mission Control is paused until the project is resumed."
        if handoff_status in {"ready", "needs_review"} and project.handoff_status == "ready":
            return "completed", "Mission Control finished this orchestration and produced a handoff."
        active_workers = int(
            db.scalar(
                select(func.count(Agent.id)).where(
                    Agent.project_id == project.id,
                    Agent.kind == "worker",
                    Agent.status.in_(["starting", "working"]),
                )
            )
            or 0
        )
        runnable_tasks = list(
            db.scalars(
                select(Task).where(
                    Task.project_id == project.id,
                    Task.status.in_(["backlog", "assigned", "waiting_on_paths", "needs_review"]),
                )
            )
        )
        open_task_count = int(
            db.scalar(
                select(func.count(Task.id)).where(
                    Task.project_id == project.id,
                    Task.status.in_(["backlog", "assigned", "working", "waiting_on_paths", "needs_review"]),
                )
            )
            or 0
        )
        if active_workers > 0:
            return "running", manager_fallback or session.manager_status or "Mission Control has active workers in flight."
        if any(task.status == "waiting_on_paths" for task in runnable_tasks):
            return "planning", "Mission Control is waiting for overlapping path ownership to clear before launching the next worker."
        review_tasks = [task for task in runnable_tasks if task.status == "needs_review"]
        review_blocked_only = review_tasks and not any(
            task.status in {"backlog", "assigned", "waiting_on_paths"} and service._dependencies_met(db, task)
            for task in runnable_tasks
        )
        if review_blocked_only:
            review_count = len(review_tasks)
            noun = "task" if review_count == 1 else "tasks"
            return "waiting_for_user", f"Mission Control is waiting for review on {review_count} {noun} before it can continue."
        if current_action and current_action.get("type") in {"blocker", "degraded", "paused"} and current_action.get("message"):
            return "planning", str(current_action["message"])
        if any(service._dependencies_met(db, task) for task in runnable_tasks):
            return "planning", "Mission Control has runnable work queued and is routing the next safe background step."
        if open_task_count > 0:
            return "planning", "Mission Control still has open work, but nothing is safely runnable yet."
        return "planning", manager_fallback or "Mission Control is wrapping evidence and preparing the next status update."

    def get_handoff(self, db: Session, session: OrchestrationSession) -> dict[str, Any]:
        project = db.get(Project, session.project_id)
        if project is None:
            raise MissionControlError(
                code="MC-HANDOFF-RENDER-FAILED-001",
                detail="Project not found for this orchestration session.",
                breakpoint="handoff.render_chat_summary",
                orchestration_id=session.id,
                project_id=session.project_id,
            )
        handoff = service.get_project_handoff_summary(db, project)
        if handoff["status"] == "not_ready":
            return {
                "ready": False,
                "status": handoff["status"],
                "message": "Mission Control has not produced a handoff yet.",
                "handoff": None,
            }
        return {
            "ready": True,
            "status": handoff["status"],
            "message": "Mission Control has a handoff ready for review.",
            "handoff": handoff,
        }

    async def daemon_status(self, db: Session) -> dict[str, Any]:
        metadata = read_daemon_metadata()
        binding = resolve_backend_binding()
        metadata_status = str(metadata.get("status") or "unknown")
        active_count = int(
            db.scalar(
                select(func.count(OrchestrationSession.id)).where(OrchestrationSession.status.in_(list(ACTIVE_ORCHESTRATION_STATUSES)))
            )
            or 0
        )
        return {
            "status": "ok",
            "metadata_status": metadata_status,
            "mode": binding.get("mode", "web"),
            "host": binding.get("host", "127.0.0.1"),
            "port": int(binding.get("port", 8010)),
            "pid": int(metadata.get("pid", 0)),
            "started_at": datetime.fromisoformat(str(metadata.get("started_at"))),
            "token_configured": ensure_daemon_token() is not None,
            "active_orchestrations": active_count,
            "runner_inventory": service.runners.inventory_preview(),
            "background_runtime": self._all_background_runtime_snapshots(),
            "retrying_orchestrations": sum(1 for item in self._all_background_runtime_snapshots() if item.get("retry_scheduled")),
            "active_background_turns": sum(1 for item in self._all_background_runtime_snapshots() if item.get("turn_active")),
            "dashboard_url": daemon_dashboard_url(),
            "repo_root": str(metadata.get("repo_root") or ""),
            "runtime_root": str(metadata.get("runtime_root") or ""),
            "launcher_root": str(metadata.get("launcher_root") or ""),
            "notes": [
                "Mission Control daemon endpoints are localhost-only and bridge-token guarded.",
                f"Backend binding source: {binding.get('source')}.",
                f"Daemon metadata status: {metadata_status}.",
            ],
        }

    def _schedule_background_turn(self, orchestration_id: int, reason: str) -> None:
        task = self._tasks.get(orchestration_id)
        if task is not None and not task.done():
            metadata = dict(self._task_metadata.get(orchestration_id) or {})
            metadata["queued_reason"] = reason
            metadata["queued_at"] = utc_now().isoformat()
            self._task_metadata[orchestration_id] = metadata
            return
        self._task_metadata[orchestration_id] = {
            "reason": reason,
            "scheduled_at": utc_now().isoformat(),
            "retry_scheduled": reason == "retry_after_error",
            "delay_seconds": 0.1,
        }
        task = asyncio.create_task(self._run_background_turn_deferred(orchestration_id, reason))
        task.add_done_callback(lambda completed, orchestration_id=orchestration_id: self._background_task_done(orchestration_id, completed))
        self._tasks[orchestration_id] = task

    def _background_task_done(self, orchestration_id: int, task: asyncio.Task[None]) -> None:
        queued_reason: str | None = None
        if self._tasks.get(orchestration_id) is task:
            task_meta = dict(self._task_metadata.get(orchestration_id) or {})
            queued_reason = str(task_meta.get("queued_reason") or "").strip() or None
            self._tasks.pop(orchestration_id, None)
            self._task_metadata.pop(orchestration_id, None)
        if task.cancelled():
            return
        # Consume exceptions here. _run_background_turn records user-visible
        # failure/retry state, so the event loop should not emit noisy warnings.
        try:
            task.exception()
        except asyncio.CancelledError:
            return
        if queued_reason:
            self._schedule_background_turn(orchestration_id, queued_reason)

    async def _run_background_turn_deferred(self, orchestration_id: int, reason: str) -> None:
        # FastAPI commits the request-scoped DB session after the handler returns.
        # Let that transaction close before the background turn opens its own
        # SQLite writer, otherwise local tests and desktop installs can deadlock
        # on "database is locked" while answering a decision.
        await asyncio.sleep(0.1)
        await self._run_background_turn(orchestration_id, reason)

    def _schedule_background_retry(self, orchestration_id: int, reason: str, delay: float, *, failure_classification: str = "transient") -> None:
        self._task_metadata[orchestration_id] = {
            "reason": reason,
            "scheduled_at": utc_now().isoformat(),
            "retry_scheduled": True,
            "delay_seconds": delay,
            "failure_classification": failure_classification,
        }
        task = asyncio.create_task(self._run_background_turn_retry_deferred(orchestration_id, reason, delay))
        task.add_done_callback(lambda completed, orchestration_id=orchestration_id: self._background_task_done(orchestration_id, completed))
        self._tasks[orchestration_id] = task

    async def _run_background_turn_retry_deferred(self, orchestration_id: int, reason: str, delay: float) -> None:
        await asyncio.sleep(delay)
        metadata = dict(self._task_metadata.get(orchestration_id) or {})
        metadata["retry_scheduled"] = False
        metadata["reason"] = reason
        metadata["scheduled_at"] = utc_now().isoformat()
        metadata["delay_seconds"] = 0
        self._task_metadata[orchestration_id] = metadata
        await self._run_background_turn(orchestration_id, reason)

    def _background_runtime_snapshot(self, orchestration_id: int, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        task = self._tasks.get(orchestration_id)
        task_meta = dict(self._task_metadata.get(orchestration_id) or {})
        session_meta = dict(metadata or {})
        return {
            "orchestration_id": orchestration_id,
            "turn_active": bool(task and not task.done() and not task_meta.get("retry_scheduled")),
            "retry_scheduled": bool(task and not task.done() and task_meta.get("retry_scheduled")),
            "reason": task_meta.get("reason"),
            "queued_reason": task_meta.get("queued_reason"),
            "queued_at": task_meta.get("queued_at"),
            "scheduled_at": task_meta.get("scheduled_at"),
            "delay_seconds": task_meta.get("delay_seconds"),
            "failure_classification": task_meta.get("failure_classification"),
            "failure_count": int(session_meta.get("background_failure_count") or 0),
            "last_error": session_meta.get("last_background_error"),
        }

    def _all_background_runtime_snapshots(self) -> list[dict[str, Any]]:
        return [self._background_runtime_snapshot(orchestration_id) for orchestration_id in sorted(self._tasks)]

    async def _bootstrap_live_execution(self, db: Session, session: OrchestrationSession, project: Project) -> None:
        if session.mode != "codex_cli":
            return
        if project.source_type == "idea":
            return
        orchestration_id = session.id
        request_text = session.user_request.strip()
        if request_text:
            service.create_change_request(db, project, request_text)
        latest_follow_up_request = db.scalar(
            select(ChangeRequest)
            .where(ChangeRequest.project_id == project.id, ChangeRequest.status != "rejected")
            .order_by(ChangeRequest.updated_at.desc(), ChangeRequest.id.desc())
            .limit(1)
        )
        fresh_benchmark_reset_requested = latest_follow_up_request is not None and service._request_implies_fresh_benchmark_reset(
            latest_follow_up_request.request_text
        )
        if fresh_benchmark_reset_requested:
            self._clear_stale_review_decisions_for_fresh_reset(db, project)
        has_tasks = db.scalar(select(Task.id).where(Task.project_id == project.id).limit(1)) is not None
        has_open_tasks = db.scalar(
            select(Task.id).where(Task.project_id == project.id, Task.status.in_(list(OPEN_TASK_STATUSES))).limit(1)
        ) is not None
        has_pending = db.scalar(
            select(PendingDecision.id).where(PendingDecision.project_id == project.id, PendingDecision.status == "pending").limit(1)
        )
        if has_pending is not None:
            return
        latest_task_update = db.scalar(
            select(func.max(Task.updated_at)).where(Task.project_id == project.id)
        )
        productive_open_task_count = service._productive_open_task_count(
            db,
            project,
            list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc()))),
        )
        target_parallel_task_count = service._target_parallel_open_task_count(db, project)
        has_recent_follow_up_request = latest_follow_up_request is not None and (
            latest_task_update is None or latest_follow_up_request.updated_at >= latest_task_update
        )
        has_standing_follow_up_request = (
            latest_follow_up_request is not None
            and not has_open_tasks
            and project.handoff_status != "ready"
        )
        has_untriaged_follow_up_request = latest_follow_up_request is not None and latest_follow_up_request.status == "new"
        needs_parallel_replenishment = fresh_benchmark_reset_requested or (
            has_open_tasks
            and (bool(request_text) or has_recent_follow_up_request or has_untriaged_follow_up_request)
            and productive_open_task_count < target_parallel_task_count
        )
        should_generate_initial_backlog = not has_tasks
        should_generate_follow_up_backlog = has_tasks and (
            fresh_benchmark_reset_requested
            or
            needs_parallel_replenishment
            or (
                not has_open_tasks
                and (bool(request_text) or has_recent_follow_up_request or has_standing_follow_up_request or has_untriaged_follow_up_request)
            )
        )
        if not (should_generate_initial_backlog or should_generate_follow_up_backlog):
            return
        workers = service.initialize_build_roster(db, project)
        worker_count = len(workers)
        # Release the transaction before manager planning or worker startup so
        # bootstrapping does not keep SQLite pinned across live runner awaits.
        db.commit()
        phase_db = SessionLocal()
        try:
            session, project = self._reload_session_project(phase_db, orchestration_id)
            if session is None or project is None:
                return
            tasks, manager_mode_used = await service.generate_tasks(phase_db, project)
            task_count = len(tasks)
            phase_db.commit()
        finally:
            phase_db.close()

        launch_db = SessionLocal()
        try:
            session, project = self._reload_session_project(launch_db, orchestration_id)
            if session is None or project is None:
                return
            started_count = await service.start_idle_agents(launch_db, project)
            provider_backoff = service._provider_backoff_state(launch_db, project)
            event_type = "live_execution_bootstrapped"
            event_payload = {
                "task_count": task_count,
                "worker_count": worker_count,
                "workers_started": started_count,
                "manager_mode_used": manager_mode_used,
            }
            if provider_backoff is not None and started_count == 0:
                event_type = "provider_backoff_active"
                event_payload["provider_backoff_until"] = provider_backoff["until"].isoformat()
                event_payload["provider_backoff_summary"] = provider_backoff["summary"]
            self._record_event(
                launch_db,
                session,
                event_type,
                event_payload,
            )
            launch_db.commit()
        finally:
            launch_db.close()

    async def _run_background_turn(self, orchestration_id: int, reason: str) -> None:
        db = SessionLocal()
        try:
            session = db.get(OrchestrationSession, orchestration_id)
            if session is None or session.status in {"completed", "failed", "paused"}:
                return
            project = db.get(Project, session.project_id)
            if project is None:
                self._update_session_status(db, session, status="failed", manager_status="Project could not be loaded for orchestration.")
                self._record_event(db, session, "orchestration_failed", {"reason": "project_missing"})
                db.commit()
                return
            if project.status == "paused":
                if session.status != "paused":
                    self._update_session_status(
                        db,
                        session,
                        status="paused",
                        manager_status="Project is paused. Mission Control will not run background turns until you resume it.",
                    )
                    self._record_event(
                        db,
                        session,
                        "background_turn_skipped",
                        {"reason": "project_paused"},
                    )
                    db.commit()
                return
            self._update_session_status(db, session, status="planning", manager_status="Mission Control Manager is reviewing the workspace.")
            self._record_event(db, session, "background_turn_started", {"reason": reason})
            service.open_project(db, project)
            metadata = dict(session.metadata_json or {})
            if project.source_type == "existing_folder" and metadata.get("read_only_first") and project.scan_status != "completed":
                import_service.initial_scan(db, project)
                self._record_event(db, session, "workspace_scanned", {"scan_status": project.scan_status})
            # Release request/setup writes before the manager or worker layers do
            # any live async work. Otherwise the background turn keeps a
            # long-lived SQLite transaction open while provider calls are in
            # flight.
            db.commit()
            db.close()
            db = SessionLocal()
            session, project = self._reload_session_project(db, orchestration_id)
            if session is None or project is None:
                return
            manager_message = None
            if reason == "user_request" and session.user_request.strip():
                manager_message = await service.manager_message(db, project, session.user_request.strip())
                db.commit()
                db.close()
                db = SessionLocal()
                session, project = self._reload_session_project(db, orchestration_id)
                if session is None or project is None:
                    return
                await self._bootstrap_live_execution(db, session, project)
                db.close()
                db = SessionLocal()
                session, project = self._reload_session_project(db, orchestration_id)
                if session is None or project is None:
                    return
            else:
                await self._bootstrap_live_execution(db, session, project)
                db.commit()
                db.close()
                db = SessionLocal()
                session, project = self._reload_session_project(db, orchestration_id)
                if session is None or project is None:
                    return
                manager_message = await service.manager_ask_next(db, project)
            db.commit()
            db.close()
            db = SessionLocal()
            session, project = self._reload_session_project(db, orchestration_id)
            if session is None or project is None:
                return
            pending = self.sync_pending_decisions(db, session)
            handoff = service.get_project_handoff_summary(db, project)
            reply = manager_message.get("message", {}).get("content_markdown") if manager_message else None
            derived_status, derived_manager_status = self._derive_runtime_state(
                db,
                session,
                project,
                pending,
                handoff_status=handoff["status"],
                current_action=service._derive_current_action_preview(
                    db,
                    project,
                    service._workspace_degraded_notices_preview(project),
                ),
                manager_fallback=(reply or "Mission Control is continuing in the background.")[:240],
            )
            self._update_session_status(
                db,
                session,
                status=derived_status,
                manager_status=derived_manager_status,
                completed=derived_status == "completed",
            )
            if derived_status == "completed":
                self._record_event(db, session, "handoff_ready", {"status": handoff["status"]})
            metadata = dict(session.metadata_json or {})
            if metadata.get("background_failure_count") or metadata.get("last_background_error"):
                metadata["background_failure_count"] = 0
                metadata.pop("last_background_error", None)
                session.metadata_json = metadata
            self._record_event(
                db,
                session,
                "background_turn_completed",
                {
                    "reason": reason,
                    "status": session.status,
                },
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            session = db.get(OrchestrationSession, orchestration_id)
            if session is not None:
                failure_classification = self._classify_background_failure(exc)
                metadata = dict(session.metadata_json or {})
                failure_count = int(metadata.get("background_failure_count") or 0) + 1
                metadata["background_failure_count"] = failure_count
                metadata["last_background_error"] = f"{type(exc).__name__}: {exc}"[:500]
                metadata["last_background_failure_classification"] = failure_classification
                session.metadata_json = metadata
                retryable = self._retryable_failure_classification(failure_classification)
                if retryable and failure_count < MAX_BACKGROUND_FAILURES:
                    self._update_session_status(
                        db,
                        session,
                        status="planning",
                        manager_status=(
                            "Mission Control hit a recoverable background error and queued a retry. "
                            f"Attempt {failure_count}/{MAX_BACKGROUND_FAILURES}: {type(exc).__name__}."
                        ),
                    )
                    self._record_event(
                        db,
                        session,
                        "background_turn_retry_scheduled",
                        {
                            "reason": str(exc),
                            "failure_count": failure_count,
                            "max_failures": MAX_BACKGROUND_FAILURES,
                            "failure_classification": failure_classification,
                        },
                    )
                    db.commit()
                    self._schedule_background_retry(
                        orchestration_id,
                        "retry_after_error",
                        min(2.0 * failure_count, 5.0),
                        failure_classification=failure_classification,
                    )
                else:
                    terminal_status = "paused" if failure_classification in {"approval_denied", "user_action_required"} else "failed"
                    self._update_session_status(
                        db,
                        session,
                        status=terminal_status,
                        manager_status=f"Mission Control background turn failed [{failure_classification}]: {exc}",
                    )
                    self._record_event(
                        db,
                        session,
                        "orchestration_failed",
                        {
                            "reason": str(exc),
                            "failure_count": failure_count,
                            "failure_classification": failure_classification,
                        },
                    )
                    db.commit()
        finally:
            db.close()


coordinator = OrchestrationCoordinator()
