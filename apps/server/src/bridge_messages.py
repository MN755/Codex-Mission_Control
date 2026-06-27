from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from bridge_formatter import (
    format_diagnostic_summary_message,
    format_event_digest_message,
    format_handoff_message,
    format_pending_decision_message,
    format_safe_mode_message,
    format_status_summary_message,
)
from config import DEFAULT_APPROVAL_POLICY, DEFAULT_SANDBOX
from errors import MissionControlError
from imported_codebase import import_service
from manager import service
from models import (
    Agent,
    AgentRun,
    ApprovalRequest,
    EvidenceBasedHandoff,
    ImportedCodebaseSafety,
    ManagerMessage,
    ManagerQuestion,
    OrchestrationEvent,
    OrchestrationSession,
    PendingDecision,
    Project,
    ProjectEvent,
    ProjectTimelineEvent,
    SubagentBatch,
    Task,
    utc_now,
)
from orchestration import ACTIVE_ORCHESTRATION_STATUSES, coordinator
from plugin_health import mission_control_plugin_health
from project_settings import get_or_create_project_settings
from security.path_validation import PathValidationError, resolve_local_path
from security.redaction import redact_text, redact_value
from security.service import security_service
from subagent_planner import subagent_planner_service


ACTIVE_AGENT_STATUSES = {"starting", "working", "waiting", "needs_review", "blocked"}


class BridgeRuntimeService:
    @staticmethod
    def _promote_project_for_live_run(db: Session, project: Project) -> None:
        if project.source_type != "existing_folder":
            return
        settings = get_or_create_project_settings(db, project)
        if settings.sandbox_mode == "read-only":
            settings.sandbox_mode = DEFAULT_SANDBOX
        if settings.approval_policy == "untrusted":
            settings.approval_policy = DEFAULT_APPROVAL_POLICY
        if project.write_permission_status == "read_only":
            project.write_permission_status = "write_allowed"
        safety = import_service.ensure_safety(db, project, create_if_missing=False)
        if safety is not None and safety.write_permission_status == "read_only":
            safety.write_permission_status = "write_allowed"
            safety.updated_at = utc_now()

    @staticmethod
    def _audit_decision_for_pending_decision(decision_type: str, option_id: str) -> str | None:
        if decision_type not in {"command_approval", "tool_approval"}:
            return None
        if option_id == "approve_once":
            return "approved"
        if option_id in {"deny", "denied"}:
            return "denied"
        if option_id in {"allow_for_project", "always_allow_if_safe"}:
            return "allowed_for_project"
        if option_id in {"expired", "auto_approved", "blocked"}:
            return option_id
        return None

    def _error(
        self,
        code: str,
        *,
        detail: str | None = None,
        breakpoint: str | None = None,
        project_id: int | None = None,
        orchestration_id: int | None = None,
        safe_details: dict[str, Any] | None = None,
        caused_by: Exception | None = None,
    ) -> MissionControlError:
        return MissionControlError(
            code=code,
            detail=detail,
            breakpoint=breakpoint,
            project_id=project_id,
            orchestration_id=orchestration_id,
            safe_details=safe_details or {},
            caused_by=caused_by,
        )

    def _runner_available(self, inventory: Sequence[dict[str, Any]], runner_type: str) -> bool:
        return any(str(item.get("runner_type")) == runner_type and bool(item.get("availability")) for item in inventory)

    async def _resolve_orchestration_mode(self, requested_mode: str) -> str:
        normalized = str(requested_mode or "auto").strip().lower()
        if normalized == "dry_run":
            return "dry_run"
        inventory = [dict(item) for item in list(await service.runners.inventory())]
        codex_ready = self._runner_available(inventory, "codex_cli")
        if normalized == "codex_cli":
            if codex_ready:
                return "codex_cli"
            raise self._error(
                "MC-RUNNER-SELECTION-FAILED-001",
                detail="Codex CLI was explicitly requested, but no authenticated local Codex runner is available.",
                breakpoint="runner.select",
                safe_details={
                    "requested_mode": normalized,
                    "available_runners": [
                        str(item.get("runner_type"))
                        for item in inventory
                        if bool(item.get("availability"))
                    ],
                },
            )
        if normalized == "auto":
            return "codex_cli" if codex_ready else "dry_run"
        return "unknown"

    def get_attach_status_summary(
        self,
        *,
        project: Project,
        attached: dict[str, Any],
        orchestration: OrchestrationSession | None = None,
    ) -> dict[str, Any]:
        attach_outcome = str(attached.get("attach_outcome") or "attached")
        message = str(attached.get("message") or "Mission Control attached the workspace.")
        user_action_required = bool(attached.get("user_action_required"))
        current_work = [message]
        waiting_on_you: list[str] = []
        if orchestration is not None and orchestration.manager_status:
            current_work.append(str(orchestration.manager_status))
        if user_action_required:
            waiting_on_you.append("Answer the pending attach or approval decision so Mission Control can continue.")
        return format_status_summary_message(
            message_id=f"attach-status-{project.id}-{orchestration.id if orchestration is not None else 'project'}",
            project_id=project.id,
            orchestration_id=orchestration.id if orchestration is not None else None,
            title="Mission Control status",
            summary=message,
            project_name=project.name,
            manager_status=message,
            mode=f"{attach_outcome} / {project.manager_mode}",
            swarm="not planned",
            user_action_needed="yes" if user_action_required else "no",
            current_work=current_work[:4],
            waiting_on_you=waiting_on_you,
            next_expected_step=(
                "Answer the pending decision before starting the task."
                if user_action_required
                else "Start a Mission Control task for this attached workspace."
            ),
            risk_level="medium" if user_action_required else None,
            created_at=utc_now(),
            orchestration_status=orchestration.status if orchestration is not None else project.status,
            current_blockers=[message] if user_action_required else [],
            handoff_readiness=str(project.handoff_status or "not_ready"),
            active_agent_count=0,
            model_advisories=[],
        )

    def _latest_project_orchestration(self, db: Session, project: Project) -> OrchestrationSession | None:
        return db.scalar(
            select(OrchestrationSession)
            .where(OrchestrationSession.project_id == project.id)
            .order_by(
                OrchestrationSession.status.in_(list(ACTIVE_ORCHESTRATION_STATUSES)).desc(),
                OrchestrationSession.updated_at.desc(),
                OrchestrationSession.id.desc(),
            )
        )

    @staticmethod
    def _path_matches_workspace(raw_path: str | None, workspace: Path) -> bool:
        if not raw_path:
            return False
        try:
            return resolve_local_path(raw_path) == workspace
        except PathValidationError:
            return False

    def _workspace_projects(self, db: Session, workspace: Path) -> list[Project]:
        candidates = list(db.scalars(select(Project).order_by(Project.updated_at.desc(), Project.id.desc())))
        return [
            project
            for project in candidates
            if self._path_matches_workspace(project.workspace_path, workspace) or self._path_matches_workspace(project.source_path, workspace)
        ]

    def _latest_workspace_orchestration(self, db: Session, workspace: Path) -> OrchestrationSession | None:
        sessions = list(
            db.scalars(
                select(OrchestrationSession).order_by(
                    OrchestrationSession.status.in_(list(ACTIVE_ORCHESTRATION_STATUSES)).desc(),
                    OrchestrationSession.updated_at.desc(),
                    OrchestrationSession.id.desc(),
                )
            )
        )
        for session in sessions:
            if self._path_matches_workspace(session.workspace_path, workspace):
                return session
        return None

    def _preferred_option(self, decision: dict[str, Any]) -> dict[str, Any] | None:
        options = [item for item in list(decision.get("options_json") or decision.get("options") or []) if item.get("id")]
        if not options:
            return None
        recommended = str(decision.get("recommended_option") or "").strip()
        if recommended:
            match = next((item for item in options if str(item.get("id")) == recommended), None)
            if match is not None:
                return match
        return options[0]

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
        return coordinator.attach_workspace(
            db,
            workspace_path=workspace_path,
            project_name=project_name,
            mode=mode,
            read_only_first=read_only_first,
            attach_policy=attach_policy,
            source=source,
        )

    def start_orchestration(
        self,
        db: Session,
        *,
        project: Project,
        source: str,
        user_request: str,
        orchestration_id: int | None = None,
        mode: str = "unknown",
        metadata_json: dict[str, Any] | None = None,
        schedule_background_turn: bool = True,
    ) -> dict[str, Any]:
        session = coordinator.start_orchestration(
            db,
            project=project,
            source=source,
            user_request=user_request,
            orchestration_id=orchestration_id,
            mode=mode,
            metadata=metadata_json,
            schedule_background_turn=schedule_background_turn,
        )
        return coordinator._serialize_session(session)

    def create_orchestration(
        self,
        db: Session,
        *,
        project: Project,
        source: str,
        user_request: str,
        orchestration_id: int | None = None,
        mode: str = "unknown",
        metadata_json: dict[str, Any] | None = None,
        schedule_background_turn: bool = True,
    ) -> dict[str, Any]:
        return self.start_orchestration(
            db,
            project=project,
            source=source,
            user_request=user_request,
            orchestration_id=orchestration_id,
            mode=mode,
            metadata_json=metadata_json,
            schedule_background_turn=schedule_background_turn,
        )

    def _serialize_pending_decision(self, decision: PendingDecision) -> dict[str, Any]:
        options = list(decision.options_json or [])
        presentation = dict(decision.presentation_json or {}) if decision.presentation_json else None
        return {
            "id": decision.id,
            "project_id": decision.project_id,
            "orchestration_id": decision.orchestration_id,
            "decision_type": decision.decision_type,
            "title": decision.title,
            "message": decision.message,
            "requesting_agent_id": decision.requesting_agent_id,
            "related_agent_id": decision.requesting_agent_id,
            "related_task_id": decision.related_task_id,
            "risk_level": decision.risk_level,
            "options": options,
            "options_json": options,
            "recommended_option": decision.recommended_option,
            "status": decision.status,
            "created_at": decision.created_at,
            "answered_at": decision.answered_at,
            "answer_json": dict(decision.answer_json or {}) if decision.answer_json else None,
            "presentation": presentation,
            "presentation_json": presentation,
        }

    def _approval_options(self, approval: ApprovalRequest) -> list[dict[str, Any]]:
        options = [
            {"id": "approve_once", "label": "Approve once", "description": "Allow this exact action one time."},
            {"id": "deny", "label": "Deny", "description": "Reject this action and keep the current safeguards in place."},
        ]
        if approval.request_type == "command" and security_service.may_allow_for_project(approval.risk_level):
            options.append(
                {
                    "id": "always_allow_if_safe",
                    "label": "Always allow if safe",
                    "description": "Allow this class of action for the current project when Mission Control policy permits it.",
                }
            )
        return options

    def _dedupe_pending_decision_matches(
        self,
        db: Session,
        *,
        source_kind: str,
        source_id: int,
    ) -> PendingDecision | None:
        matches = list(
            db.scalars(
                select(PendingDecision)
                .where(PendingDecision.source_kind == source_kind, PendingDecision.source_id == source_id)
                .order_by(PendingDecision.answered_at.desc(), PendingDecision.created_at.desc(), PendingDecision.id.desc())
            )
        )
        current = matches[0] if matches else None
        for duplicate in matches[1:]:
            db.delete(duplicate)
        return current

    def _sync_question_decision(
        self,
        db: Session,
        project: Project,
        question: ManagerQuestion,
        orchestration: OrchestrationSession | None,
    ) -> PendingDecision:
        record = self._dedupe_pending_decision_matches(
            db,
            source_kind="manager_question",
            source_id=question.id,
        )
        if record is None:
            record = PendingDecision(
                project_id=project.id,
                orchestration_id=orchestration.id if orchestration else None,
                decision_type="manager_question",
                title="Mission Control Manager needs a decision",
                message=question.question,
                requesting_agent_id=question.related_agent_id,
                related_task_id=question.related_task_id,
                risk_level="high" if question.impact == "high" else "medium",
                options_json=list(question.options_json or []),
                recommended_option=question.selected_option_id,
                source_kind="manager_question",
                source_id=question.id,
            )
            db.add(record)
        record.project_id = project.id
        record.orchestration_id = orchestration.id if orchestration else record.orchestration_id
        record.decision_type = "manager_question"
        record.title = "Mission Control Manager needs a decision"
        record.message = question.question
        record.requesting_agent_id = question.related_agent_id
        record.related_task_id = question.related_task_id
        record.risk_level = "high" if question.impact == "high" else "medium"
        record.options_json = list(question.options_json or [])
        record.recommended_option = question.selected_option_id or None
        record.status = "pending" if question.status == "pending" else "answered"
        record.answered_at = question.resolved_at
        record.answer_json = (
            {
                "option_id": question.selected_option_id,
                "selected_text": question.selected_text,
                "status": question.status,
            }
            if question.status != "pending"
            else None
        )
        record.presentation_json = {
            "card_type": "manager_question",
            "title": "Mission Control Manager needs a decision",
            "question": question.question,
            "impact": question.impact,
            "options": list(question.options_json or []),
            "recommended_option": question.selected_option_id,
            "auto_decide_at": question.auto_decide_at.isoformat() if question.auto_decide_at else None,
            "fallback_markdown": question.question,
        }
        db.flush()
        return record

    def _sync_approval_decision(
        self,
        db: Session,
        project: Project,
        approval: ApprovalRequest,
        orchestration: OrchestrationSession | None,
    ) -> PendingDecision:
        record = self._dedupe_pending_decision_matches(
            db,
            source_kind="approval_request",
            source_id=approval.id,
        )
        options = self._approval_options(approval)
        request_payload = dict(approval.request_payload_json or {})
        decision_type = "command_approval" if approval.request_type == "command" else "tool_approval"
        if record is None:
            record = PendingDecision(
                project_id=project.id,
                orchestration_id=orchestration.id if orchestration else None,
                decision_type=decision_type,
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
            db.add(record)
        record.project_id = project.id
        record.orchestration_id = orchestration.id if orchestration else record.orchestration_id
        record.decision_type = decision_type
        record.title = approval.title
        record.message = approval.reason_short
        record.requesting_agent_id = approval.requesting_agent_id
        record.related_task_id = approval.task_id
        record.risk_level = approval.risk_level
        record.options_json = options
        record.recommended_option = "approve_once"
        record.status = "pending" if approval.status == "pending" else "answered"
        record.answered_at = approval.resolved_at
        record.answer_json = (
            {
                "option_id": approval.status,
                "selected_text": approval.status.replace("_", " "),
                "status": approval.status,
            }
            if approval.status != "pending"
            else None
        )
        record.presentation_json = {
            "card_type": decision_type,
            "title": approval.title,
            "requesting_agent": approval.requesting_agent_id,
            "command": request_payload.get("command"),
            "tool_name": request_payload.get("tool_name"),
            "requested_access": request_payload.get("requested_access"),
            "cwd": approval.cwd,
            "scope": request_payload.get("scope") or request_payload.get("affected_paths_json") or [],
            "reason_short": approval.reason_short[:220],
            "risk_level": approval.risk_level,
            "details": redact_value(request_payload),
            "options": options,
            "fallback_markdown": approval.reason_short,
        }
        db.flush()
        return record

    def _sync_review_task_decision(
        self,
        db: Session,
        project: Project,
        task: Task,
        orchestration: OrchestrationSession | None,
    ) -> PendingDecision:
        record = self._dedupe_pending_decision_matches(
            db,
            source_kind="task_review",
            source_id=task.id,
        )
        options = [
            {"id": "approve", "label": "Approve", "description": "Mark this reviewed task complete and let Mission Control continue."},
            {"id": "request_changes", "label": "Request changes", "description": "Send this task back to backlog so Mission Control can route follow-up work."},
        ]
        message = f"Task \"{task.title}\" needs review before Mission Control can continue."
        if record is None:
            record = PendingDecision(
                project_id=project.id,
                orchestration_id=orchestration.id if orchestration else None,
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
            db.add(record)
        record.project_id = project.id
        record.orchestration_id = orchestration.id if orchestration else record.orchestration_id
        record.decision_type = "handoff_review"
        record.title = f"Review required: {task.title}"
        record.message = message
        record.requesting_agent_id = task.assigned_agent_id
        record.related_task_id = task.id
        record.risk_level = "medium"
        record.options_json = options
        record.recommended_option = "approve"
        record.status = "pending" if task.status == "needs_review" else "answered"
        if task.status == "needs_review":
            record.answered_at = None
            record.answer_json = None
        record.presentation_json = {
            "card_type": "handoff_review",
            "title": f"Review required: {task.title}",
            "subtitle": message,
            "risk_level": "medium",
            "details": [
                item
                for item in [
                    task.goal or task.scope or None,
                    f"Role: {task.agent_role}" if task.agent_role else None,
                    f"Milestone: {task.milestone}" if task.milestone else None,
                    f"Waiting reason: {task.waiting_reason}" if task.waiting_reason else None,
                ]
                if item
            ],
            "options": options,
            "recommended_option": "approve",
            "fallback_markdown": message,
        }
        db.flush()
        return record

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

    def sync_pending_decisions(
        self,
        db: Session,
        *,
        project: Project,
        orchestration: OrchestrationSession | None = None,
    ) -> list[PendingDecision]:
        if orchestration is None:
            orchestration = self._latest_project_orchestration(db, project)
        questions = list(
            db.scalars(
                select(ManagerQuestion)
                .where(ManagerQuestion.project_id == project.id)
                .order_by(ManagerQuestion.created_at.asc(), ManagerQuestion.id.asc())
            )
        )
        approvals = list(
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
        for question in questions:
            active_keys.add(("manager_question", question.id))
            self._sync_question_decision(db, project, question, orchestration)
        for approval in approvals:
            active_keys.add(("approval_request", approval.id))
            self._sync_approval_decision(db, project, approval, orchestration)
        for task in review_tasks:
            active_keys.add(("task_review", task.id))
            self._sync_review_task_decision(db, project, task, orchestration)
        burst_batches = list(
            db.scalars(
                select(SubagentBatch)
                .where(SubagentBatch.project_id == project.id, SubagentBatch.status == "proposed")
                .order_by(SubagentBatch.created_at.asc(), SubagentBatch.id.asc())
            )
        )
        for batch in burst_batches:
            active_keys.add(("subagent_batch", batch.id))
            subagent_planner_service._sync_batch_pending_decision(db, batch, approval_required=True)
        existing = list(
            db.scalars(
                select(PendingDecision)
                .where(PendingDecision.project_id == project.id)
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
            key = (str(decision.source_kind or ""), int(decision.source_id or 0))
            if key not in active_keys and decision.status == "pending":
                decision.status = "cancelled"
                decision.answered_at = utc_now()
        db.flush()
        return list(
            db.scalars(
                select(PendingDecision)
                .where(PendingDecision.project_id == project.id, PendingDecision.status == "pending")
                .order_by(PendingDecision.created_at.asc(), PendingDecision.id.asc())
            )
        )

    def get_pending_decisions(
        self,
        db: Session,
        *,
        project: Project | None = None,
        orchestration: OrchestrationSession | None = None,
    ) -> list[dict[str, Any]]:
        if orchestration is not None and project is None:
            project = db.get(Project, orchestration.project_id)
        if project is None:
            return []
        synced = self.sync_pending_decisions(db, project=project, orchestration=orchestration)
        return [self._serialize_pending_decision(item) for item in synced]

    def get_bridge_message_for_decision(self, db: Session, decision: PendingDecision) -> dict[str, Any]:
        agent_name = None
        if decision.requesting_agent_id is not None:
            agent = db.get(Agent, decision.requesting_agent_id)
            agent_name = agent.name if agent is not None else None
        return format_pending_decision_message(decision=self._serialize_pending_decision(decision), requesting_agent=agent_name)

    def _prime_dry_run_happy_path(
        self,
        db: Session,
        *,
        project: Project,
        orchestration: OrchestrationSession,
        user_request: str,
        strategy: str,
        interview_mode: str,
        create_pending_decision: bool,
    ) -> list[dict[str, Any]]:
        metadata = dict(orchestration.metadata_json or {})
        metadata.update(
            {
                "headless_happy_path": True,
                "strategy": strategy,
                "interview_mode": interview_mode,
                "simulated": True,
            }
        )
        orchestration.metadata_json = metadata
        orchestration.mode = "dry_run"
        existing_event_types = {
            str(event.event_type)
            for event in db.scalars(
                select(OrchestrationEvent)
                .where(OrchestrationEvent.orchestration_id == orchestration.id)
                .order_by(OrchestrationEvent.id.asc())
            )
        }
        if "manager_analyzed_request" not in existing_event_types:
            coordinator._record_event(
                db,
                orchestration,
                "manager_analyzed_request",
                {"message": f"Mission Control analyzed the request in dry-run mode: {user_request.strip()}"},
            )
        if "dry_run_agent_plan_created" not in existing_event_types:
            coordinator._record_event(
                db,
                orchestration,
                "dry_run_agent_plan_created",
                {
                    "message": "Mission Control prepared a deterministic dry-run agent plan.",
                    "strategy": strategy,
                    "interview_mode": interview_mode,
                },
            )
        pending = self.get_pending_decisions(db, project=project, orchestration=orchestration)
        has_command_approval = any(str(item.get("decision_type")) == "command_approval" for item in pending)
        if create_pending_decision and not has_command_approval:
            approval = service._create_approval(
                db,
                project,
                request_type="command",
                title="Approve local validation command",
                reason_short="Run a local pytest validation step so Mission Control can check the failing tests safely. No deployment or external service access is involved.",
                risk_level="low",
                cwd=project.workspace_path,
                request_payload_json={
                    "command": "python -m pytest",
                    "scope": ["tests/"],
                    "simulated": True,
                    "headless_happy_path": True,
                },
            )
            if approval.status != "pending":
                approval.status = "pending"
                approval.resolved_by = None
                approval.resolved_at = None
                db.flush()
            coordinator._record_event(
                db,
                orchestration,
                "pending_decision_created",
                {
                    "decision_type": "command_approval",
                    "message": "Mission Control queued a deterministic dry-run validation approval.",
                },
            )
            pending = self.get_pending_decisions(db, project=project, orchestration=orchestration)
        for record in list(
            db.scalars(
                select(PendingDecision)
                .where(PendingDecision.project_id == project.id, PendingDecision.status == "pending")
                .order_by(PendingDecision.created_at.asc(), PendingDecision.id.asc())
            )
        ):
            if record.decision_type == "command_approval":
                continue
            if record.source_kind == "manager_question" and record.source_id is not None:
                question = db.get(ManagerQuestion, record.source_id)
                if question is not None and question.status == "pending":
                    question.status = "cancelled"
                    question.resolved_at = utc_now()
            elif record.source_kind == "approval_request" and record.source_id is not None:
                approval = db.get(ApprovalRequest, record.source_id)
                if approval is not None and approval.status == "pending":
                    approval.status = "denied"
                    approval.resolved_by = "system"
                    approval.resolved_at = utc_now()
            record.status = "cancelled"
            record.answered_at = utc_now()
        pending = self.get_pending_decisions(db, project=project, orchestration=orchestration)
        if pending:
            coordinator._update_session_status(
                db,
                orchestration,
                status="waiting_for_user",
                manager_status="Dry-run orchestration is waiting for a user decision before it can continue.",
            )
        else:
            coordinator._update_session_status(
                db,
                orchestration,
                status="running",
                manager_status="Dry-run orchestration is ready to continue in the background.",
            )
        db.flush()
        return pending

    def _queued_live_status_summary(
        self,
        *,
        project: Project,
        orchestration: OrchestrationSession,
        pending: Sequence[dict[str, Any]] | Sequence[PendingDecision],
    ) -> dict[str, Any]:
        waiting_lines: list[str] = []
        for item in pending:
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
                message = str(item.get("message") or "").strip()
            else:
                title = str(item.title or "").strip()
                message = str(item.message or "").strip()
            if not title and not message:
                continue
            waiting_lines.append(f"{title}: {message}" if title and message else (title or message))
        return format_status_summary_message(
            message_id=f"status-summary-{project.id}-{orchestration.id}",
            project_id=project.id,
            orchestration_id=orchestration.id,
            title="Mission Control status",
            summary=redact_text((orchestration.manager_status or "Mission Control queued the first live background turn.")[:220]),
            project_name=project.name,
            manager_status=orchestration.manager_status or "Mission Control queued the first live background turn.",
            mode=f"{orchestration.mode} / {project.manager_mode}",
            swarm="not planned",
            user_action_needed="yes" if waiting_lines else "no",
            current_work=[
                "Mission Control accepted the task and queued the first live background turn.",
                "Poll status or pending decisions for the next concrete update.",
            ],
            waiting_on_you=waiting_lines[:5],
            next_expected_step=(
                "Answer the pending Mission Control decision."
                if waiting_lines
                else "Mission Control Manager will continue the live background turn and then publish a richer status update."
            ),
            risk_level="medium" if waiting_lines else None,
            created_at=utc_now(),
            orchestration_status=orchestration.status,
            current_blockers=[],
            handoff_readiness=str(project.handoff_status or "not_ready"),
            active_agent_count=0,
            model_advisories=[],
        )

    async def start_headless_task(
        self,
        db: Session,
        *,
        workspace_path: str | None,
        project_id: int | None,
        user_request: str,
        strategy: str,
        mode: str,
        interview_mode: str,
        attach_policy: str,
        source: str = "codex_plugin",
        create_pending_decision: bool = True,
    ) -> dict[str, Any]:
        attached: dict[str, Any] | None = None
        project: Project | None = None
        orchestration: OrchestrationSession | None = None
        if workspace_path and project_id is not None:
            try:
                workspace = resolve_local_path(workspace_path)
            except PathValidationError as exc:
                raise self._error(
                    "MC-WORKSPACE-PATH-MISSING-001",
                    detail=str(exc),
                    breakpoint="workspace.attach",
                    safe_details={"workspace_path": workspace_path},
                    caused_by=exc,
                ) from exc
            project = db.get(Project, project_id)
            if project is None:
                raise self._error(
                    "MC-WORKSPACE-PATH-MISSING-001",
                    detail="Mission Control could not find the requested project.",
                    breakpoint="workspace.attach",
                    project_id=project_id,
                )
            if not (
                self._path_matches_workspace(project.workspace_path, workspace)
                or self._path_matches_workspace(project.source_path, workspace)
            ):
                raise self._error(
                    "MC-WORKSPACE-PATH-MISSING-001",
                    detail="The provided project_id does not belong to the provided workspace_path.",
                    breakpoint="workspace.attach",
                    project_id=project_id,
                    safe_details={"workspace_path": workspace_path, "project_id": project_id},
                )
            active = self._latest_workspace_orchestration(db, workspace)
            if active is not None and active.project_id == project.id:
                orchestration = active
                attached = {
                    "project": service._serialize_project_card(db, project),
                    "project_id": project.id,
                    "project_name": project.name,
                    "source_type": project.source_type,
                    "workspace_path": project.workspace_path,
                    "orchestration": coordinator._serialize_session(active),
                    "attach_outcome": "reused_existing_orchestration",
                    "next_action": "get_status_summary",
                    "reused_existing_project": True,
                    "reused_existing_orchestration": True,
                    "user_action_required": False,
                    "pending_decision_id": None,
                    "message": "Mission Control reused the explicitly selected project and its active orchestration.",
                    "status_summary_markdown": None,
                }
        elif workspace_path:
            attach_mode = "existing_codebase"
            try:
                workspace = resolve_local_path(workspace_path)
            except PathValidationError as exc:
                raise self._error(
                    "MC-WORKSPACE-PATH-MISSING-001",
                    detail=str(exc),
                    breakpoint="workspace.attach",
                    safe_details={"workspace_path": workspace_path},
                    caused_by=exc,
                ) from exc
            if workspace.exists() and workspace.is_dir() and not any(workspace.iterdir()):
                attach_mode = "new_project"
            attached = self.attach_workspace(
                db,
                workspace_path=workspace_path,
                project_name=None,
                mode=attach_mode,
                read_only_first=True,
                attach_policy=attach_policy,
                source=source,
            )
            if attached.get("project_id") is not None:
                project = db.get(Project, int(attached["project_id"]))
            orchestration_payload = attached.get("orchestration") or None
            if orchestration_payload and orchestration_payload.get("id") is not None:
                orchestration = db.get(OrchestrationSession, int(orchestration_payload["id"]))
        elif project_id is not None:
            project = db.get(Project, project_id)
        if project is None:
            raise self._error(
                "MC-WORKSPACE-PATH-MISSING-001",
                detail="Mission Control could not resolve a project for this background task.",
                breakpoint="workspace.attach",
                project_id=project_id,
                safe_details={"workspace_path": workspace_path, "project_id": project_id},
            )

        if orchestration is not None and attached and attached.get("pending_decision_id") is not None:
            status_summary = await self.get_status_summary(db, project=project, orchestration=orchestration)
            attached["status_summary_markdown"] = status_summary["fallback_markdown"]
            return {
                "project": service._serialize_project_card(db, project),
                "orchestration": coordinator._serialize_session(orchestration),
                "attach": attached,
                "status_summary": status_summary,
                "pending_decisions": self.get_pending_decisions(db, project=project, orchestration=orchestration),
                "next_action": attached.get("next_action"),
                "user_action_required": True,
                "mode_used": orchestration.mode,
            }

        resolved_mode = await self._resolve_orchestration_mode(mode)
        run_initial_turn_inline = resolved_mode == "dry_run"
        project.runner_mode = "dry_run" if resolved_mode == "dry_run" else ("cli" if resolved_mode == "codex_cli" else project.runner_mode)
        if project.settings is not None:
            project.settings.runner_mode = project.runner_mode
        if not run_initial_turn_inline:
            self._promote_project_for_live_run(db, project)
        service.open_project(db, project)
        orchestration_payload = self.create_orchestration(
            db,
            project=project,
            source=source,
            user_request=user_request,
            orchestration_id=orchestration.id if orchestration is not None else None,
            mode=resolved_mode,
            metadata_json={
                "strategy": strategy,
                "interview_mode": interview_mode,
                "headless_entrypoint": "start_task",
            },
            schedule_background_turn=not run_initial_turn_inline,
        )
        orchestration = db.get(OrchestrationSession, int(orchestration_payload["id"]))
        if orchestration is None:
            raise self._error(
                "MC-ORCH-START-FAILED-001",
                detail="Mission Control could not create an orchestration session.",
                breakpoint="orchestration.create",
                project_id=project.id,
                safe_details={"workspace_path": workspace_path, "mode": resolved_mode},
            )
        if resolved_mode == "dry_run":
            pending = self._prime_dry_run_happy_path(
                db,
                project=project,
                orchestration=orchestration,
                user_request=user_request,
                strategy=strategy,
                interview_mode=interview_mode,
                create_pending_decision=create_pending_decision,
            )
            status_summary = await self.get_status_summary(db, project=project, orchestration=orchestration)
        else:
            pending = self.get_pending_decisions(db, project=project, orchestration=orchestration)
            status_summary = self._queued_live_status_summary(project=project, orchestration=orchestration, pending=pending)
        if attached is not None:
            attached["status_summary_markdown"] = status_summary["fallback_markdown"]
        return {
            "project": service._serialize_project_card(db, project),
            "orchestration": coordinator._serialize_session(orchestration),
            "attach": attached,
            "status_summary": status_summary,
            "pending_decisions": pending,
            "next_action": "answer_pending_decision" if pending else "get_status_summary",
            "user_action_required": bool(pending),
            "mode_used": resolved_mode,
        }

    async def get_status_summary(
        self,
        db: Session,
        *,
        project: Project | None = None,
        orchestration: OrchestrationSession | None = None,
    ) -> dict[str, Any]:
        if orchestration is not None and project is None:
            project = db.get(Project, orchestration.project_id)
        if project is None:
            raise self._error(
                "MC-BRIDGE-FORMAT-FAILED-001",
                detail="Project not found for status summary.",
                breakpoint="bridge.format_status",
                orchestration_id=orchestration.id if orchestration is not None else None,
            )
        settings = service._project_settings_preview(db, project)
        degraded_notices = await service._workspace_degraded_notices(project, settings)
        return self._build_status_summary(
            db,
            project=project,
            orchestration=orchestration,
            degraded_notices=degraded_notices,
            current_action=service._derive_current_action(db, project, degraded_notices, mutate=True),
        )

    def get_status_summary_preview(
        self,
        db: Session,
        *,
        project: Project | None = None,
        orchestration: OrchestrationSession | None = None,
    ) -> dict[str, Any]:
        if orchestration is not None and project is None:
            project = db.get(Project, orchestration.project_id)
        if project is None:
            raise self._error(
                "MC-BRIDGE-FORMAT-FAILED-001",
                detail="Project not found for status summary.",
                breakpoint="bridge.format_status",
                orchestration_id=orchestration.id if orchestration is not None else None,
            )
        degraded_notices = service._workspace_degraded_notices_preview(project)
        return self._build_status_summary(
            db,
            project=project,
            orchestration=orchestration,
            degraded_notices=degraded_notices,
            current_action=service._derive_current_action_preview(
                db,
                project,
                degraded_notices,
            ),
        )

    def _build_status_summary(
        self,
        db: Session,
        *,
        project: Project,
        orchestration: OrchestrationSession | None,
        degraded_notices: list[str],
        current_action: dict[str, Any],
    ) -> dict[str, Any]:
        pending = self.get_pending_decisions(db, project=project, orchestration=orchestration)
        handoff = service.get_project_handoff_summary(db, project)
        active_agents = list(
            db.scalars(
                select(Agent)
                .where(Agent.project_id == project.id, Agent.kind != "manager")
                .order_by(Agent.last_update.desc(), Agent.id.desc())
            )
        )
        current_work: list[str] = []
        if orchestration is not None:
            current_work.append(orchestration.manager_status)
        elif project.latest_activity:
            current_work.append(project.latest_activity)
        for agent in active_agents[:4]:
            if agent.status in ACTIVE_AGENT_STATUSES:
                current_work.append(f"{agent.name}: {agent.current_action or agent.status}")
        if current_action.get("type") not in {"no_action", None} and current_action.get("message"):
            current_work.append(str(current_action["message"]))
        background_runtime: dict[str, Any] = {}
        if orchestration is not None:
            background_runtime = coordinator._background_runtime_snapshot(orchestration.id, metadata=dict(orchestration.metadata_json or {}))
            if background_runtime.get("retry_scheduled"):
                current_work.append("Mission Control queued a retry after a recoverable background error.")
            elif background_runtime.get("turn_active"):
                current_work.append("Mission Control is actively running a background manager turn.")
        waiting = [f"{item['title']}: {item['message']}" if item.get("message") else item["title"] for item in pending]
        handoff_status = str(handoff.get("status") or "not_ready")
        handoff_missing_evidence = [str(item) for item in list(handoff.get("missing_evidence") or []) if str(item).strip()]
        handoff_known_limitations = [str(item) for item in list(handoff.get("known_limitations") or []) if str(item).strip()]
        effective_handoff_readiness = handoff_status if project.status == "handoff_ready" else str(project.handoff_status or "not_ready")
        handoff_ready_for_review = (
            project.status == "handoff_ready"
            and handoff_status in {"needs_review", "ready"}
            and not background_runtime.get("turn_active")
        )
        if handoff_ready_for_review:
            confidence_level = str(handoff.get("confidence_level") or "low")
            evidence_level = str(handoff.get("evidence_status") or "missing")
            manager_status = (
                "Mission Control generated the latest evidence-backed handoff and is waiting for review."
                if handoff_status == "needs_review"
                else "Mission Control completed the latest evidence-backed handoff."
            )
            current_work = [
                manager_status,
                f"Handoff confidence is {confidence_level} with {evidence_level} evidence.",
                *handoff_missing_evidence[:2],
                *handoff_known_limitations[:1],
            ]
            if handoff_status == "needs_review" and not waiting:
                waiting = ["Review the latest evidence-backed handoff and resolve the remaining required gates."]
        else:
            manager_status = orchestration.manager_status if orchestration is not None else str(current_action.get("title") or "Monitoring")
        include_handoff_evidence_blockers = handoff_ready_for_review or project.status == "handoff_ready"
        blockers = list(
            dict.fromkeys(
                [
                    *(handoff_missing_evidence if include_handoff_evidence_blockers else []),
                    *list(
                        current_action.get("type") not in {"no_action", None}
                        and current_action.get("message")
                        and [str(current_action["message"])]
                        or []
                    ),
                    *[str(item) for item in degraded_notices if str(item).strip()],
                ]
            )
        )
        model_advisories: list[str] = []
        swarm_plan = service.get_swarm_plan(db, project)
        swarm_summary = "Not planned"
        if swarm_plan:
            swarm_summary = f"{swarm_plan.get('mode', 'unknown')} / {swarm_plan.get('status', 'unknown')}"
        user_action_needed = "yes" if waiting else "no"
        return format_status_summary_message(
            message_id=f"status-summary-{project.id}-{orchestration.id if orchestration else 'project'}",
            project_id=project.id,
            orchestration_id=orchestration.id if orchestration else None,
            title="Mission Control status",
            summary=redact_text(manager_status[:220]),
            project_name=project.name,
            manager_status=manager_status,
            mode=f"{(orchestration.mode if orchestration is not None else project.runner_mode)} / {project.manager_mode}",
            swarm=swarm_summary,
            user_action_needed=user_action_needed,
            current_work=current_work[:5],
            waiting_on_you=waiting[:5],
            next_expected_step=(
                "Review the latest evidence-backed handoff."
                if handoff_ready_for_review
                else str(current_action.get("title") or "Mission Control will continue with the next safe background step.")
            ),
            risk_level="high" if blockers else ("medium" if waiting else None),
            created_at=utc_now(),
            orchestration_status=project.status if handoff_ready_for_review else (orchestration.status if orchestration is not None else project.status),
            current_blockers=blockers[:5],
            handoff_readiness=effective_handoff_readiness,
            active_agent_count=len([agent for agent in active_agents if agent.status in ACTIVE_AGENT_STATUSES]),
            model_advisories=model_advisories[:3],
        )

    async def happy_path_demo(
        self,
        db: Session,
        *,
        workspace_path: str,
        project_name: str | None,
        user_request: str,
        mode: str,
        read_only_first: bool,
        attach_policy: str,
        create_pending_decision: bool,
    ) -> dict[str, Any]:
        attached = self.attach_workspace(
            db,
            workspace_path=workspace_path,
            project_name=project_name,
            mode=mode,
            read_only_first=read_only_first,
            attach_policy=attach_policy,
            source="test",
        )
        start_payload = await self.start_headless_task(
            db,
            workspace_path=None,
            project_id=int(attached["project_id"]),
            user_request=user_request,
            strategy="balanced",
            mode="dry_run",
            interview_mode="skip",
            attach_policy=attach_policy,
            source="test",
            create_pending_decision=create_pending_decision,
        )
        orchestration_payload = start_payload.get("orchestration")
        if orchestration_payload is None:
            raise self._error(
                "MC-ORCH-START-FAILED-001",
                detail="Mission Control could not create the background-running happy path orchestration.",
                breakpoint="orchestration.create",
                safe_details={"workspace_path": workspace_path, "mode": mode},
            )
        pending = list(start_payload.get("pending_decisions") or [])
        selected = next((item for item in pending if item["decision_type"] == "command_approval"), pending[0] if pending else None)
        selected_record = db.get(PendingDecision, int(selected["id"])) if selected is not None else None
        return {
            "attach": attached,
            "orchestration": orchestration_payload,
            "initial_status_summary": start_payload.get("status_summary"),
            "pending_decision": selected,
            "decision_bridge_message": self.get_bridge_message_for_decision(db, selected_record) if selected_record is not None else None,
            "answer_result": None,
            "event_digest": None,
            "handoff_summary": None,
            "dry_run": True,
        }

    async def run_happy_path_demo(
        self,
        db: Session,
        *,
        workspace_path: str,
        project_name: str | None,
        user_request: str,
        mode: str,
        read_only_first: bool,
        attach_policy: str,
        create_pending_decision: bool,
    ) -> dict[str, Any]:
        return await self.happy_path_demo(
            db,
            workspace_path=workspace_path,
            project_name=project_name,
            user_request=user_request,
            mode=mode,
            read_only_first=read_only_first,
            attach_policy=attach_policy,
            create_pending_decision=create_pending_decision,
        )

    def _event_time_cutoff(
        self,
        db: Session,
        *,
        project: Project,
        orchestration: OrchestrationSession | None,
        window: str,
    ):
        now = utc_now()
        if window == "last_5_minutes":
            return now - timedelta(minutes=5)
        if window == "last_15_minutes":
            return now - timedelta(minutes=15)
        if window == "since_last_user_interaction":
            last_user_message = db.scalar(
                select(ManagerMessage)
                .where(ManagerMessage.project_id == project.id, ManagerMessage.role == "user")
                .order_by(ManagerMessage.created_at.desc(), ManagerMessage.id.desc())
            )
            return last_user_message.created_at if last_user_message is not None else project.created_at
        if window == "since_orchestration_start" and orchestration is not None:
            return orchestration.created_at
        return project.created_at

    def _event_digest_category(self, event_type: str) -> str:
        lowered = event_type.lower()
        if "approval" in lowered or "decision" in lowered:
            return "Approvals"
        if "conflict" in lowered:
            return "Conflicts"
        if "recovery" in lowered:
            return "Recovery"
        if "handoff" in lowered:
            return "Handoff"
        if "validation" in lowered or "test" in lowered or "build" in lowered:
            return "Validation"
        if "diagnostic" in lowered or "safe_mode" in lowered:
            return "Diagnostics"
        if "agent" in lowered:
            return "Agents"
        return "Manager"

    def _event_digest_line(self, event_type: str, payload: dict[str, Any]) -> str:
        payload = redact_value(dict(payload or {}))
        if "message" in payload and payload["message"]:
            return f"{event_type.replace('_', ' ')}: {payload['message']}"
        if "status" in payload and payload["status"]:
            return f"{event_type.replace('_', ' ')} -> {payload['status']}"
        if "reason" in payload and payload["reason"]:
            return f"{event_type.replace('_', ' ')}: {payload['reason']}"
        if "decision_type" in payload and payload["decision_type"]:
            return f"{event_type.replace('_', ' ')}: {payload['decision_type']}"
        return event_type.replace("_", " ").replace(".", " ").title()

    def _timeline_digest_line(self, event: ProjectTimelineEvent) -> str:
        summary = redact_text(str(event.summary or "").strip())
        title = redact_text(str(event.title or "").strip())
        if title and summary:
            return f"{title}: {summary}"
        return title or summary or event.event_type.replace("_", " ")

    def get_event_digest(
        self,
        db: Session,
        *,
        project: Project | None = None,
        orchestration: OrchestrationSession | None = None,
        window: str = "last_15_minutes",
    ) -> dict[str, Any]:
        if orchestration is not None and project is None:
            project = db.get(Project, orchestration.project_id)
        if project is None:
            raise self._error(
                "MC-BRIDGE-FORMAT-FAILED-001",
                detail="Project not found for event digest.",
                breakpoint="bridge.format_status",
                orchestration_id=orchestration.id if orchestration is not None else None,
            )
        cutoff = self._event_time_cutoff(db, project=project, orchestration=orchestration, window=window)
        timeline_events = list(
            db.scalars(
                select(ProjectTimelineEvent)
                .where(ProjectTimelineEvent.project_id == project.id, ProjectTimelineEvent.created_at >= cutoff)
                .order_by(ProjectTimelineEvent.created_at.asc(), ProjectTimelineEvent.id.asc())
            )
        )
        if orchestration is not None:
            events = list(
                db.scalars(
                    select(OrchestrationEvent)
                    .where(OrchestrationEvent.orchestration_id == orchestration.id, OrchestrationEvent.created_at >= cutoff)
                    .order_by(OrchestrationEvent.created_at.asc(), OrchestrationEvent.id.asc())
                )
            )
        else:
            events = list(
                db.scalars(
                    select(ProjectEvent)
                    .where(ProjectEvent.project_id == project.id, ProjectEvent.created_at >= cutoff)
                    .order_by(ProjectEvent.created_at.asc(), ProjectEvent.id.asc())
                )
            )
        groups: dict[str, list[str]] = {"Manager": [], "Agents": [], "Approvals": [], "Validation": [], "Handoff": [], "Conflicts": [], "Recovery": [], "Diagnostics": []}
        for event in timeline_events[:20]:
            category = self._event_digest_category(event.event_type)
            groups.setdefault(category, []).append(self._timeline_digest_line(event))
        for event in events[:40]:
            category = self._event_digest_category(event.event_type)
            groups.setdefault(category, []).append(self._event_digest_line(event.event_type, event.payload_json))
        item_count = len(events) + len(timeline_events)
        summary = "No significant orchestration events." if item_count == 0 else f"{item_count} event(s) summarized for {window.replace('_', ' ')}."
        return format_event_digest_message(
            message_id=f"event-digest-{project.id}-{orchestration.id if orchestration else 'project'}-{window}",
            project_id=project.id,
            orchestration_id=orchestration.id if orchestration else None,
            title="Mission Control event digest",
            summary=summary,
            grouped_items=groups,
            created_at=utc_now(),
        )

    def _latest_handoff(self, db: Session, project: Project) -> EvidenceBasedHandoff | None:
        return db.scalar(
            select(EvidenceBasedHandoff)
            .where(EvidenceBasedHandoff.project_id == project.id)
            .order_by(EvidenceBasedHandoff.created_at.desc(), EvidenceBasedHandoff.id.desc())
        )

    def get_handoff_summary(
        self,
        db: Session,
        *,
        project: Project | None = None,
        orchestration: OrchestrationSession | None = None,
    ) -> dict[str, Any]:
        if orchestration is not None and project is None:
            project = db.get(Project, orchestration.project_id)
        if project is None:
            raise self._error(
                "MC-HANDOFF-RENDER-FAILED-001",
                detail="Project not found for handoff summary.",
                breakpoint="handoff.render_chat_summary",
                orchestration_id=orchestration.id if orchestration is not None else None,
            )
        handoff_record = self._latest_handoff(db, project)
        handoff = service.get_project_handoff_summary(db, project)
        missing_evidence = [str(item) for item in list(handoff.get("missing_evidence") or []) if str(item).strip()]
        if handoff_record is None:
            return format_handoff_message(
                message_id=f"handoff-{project.id}-{orchestration.id if orchestration else 'project'}",
                project_id=project.id,
                orchestration_id=orchestration.id if orchestration else None,
                handoff_status=str(handoff["status"]),
                confidence_level=str(handoff.get("confidence_level") or "low"),
                evidence_level=str(handoff.get("evidence_status") or "missing"),
                what_changed=[],
                how_to_run=list(handoff.get("run_instructions") or []),
                validation_items=["Validation not run."],
                known_limitations=list(handoff.get("known_limitations") or []),
                next_tasks=[],
                important_files=[item for item in [handoff.get("artifacts_path"), project.docs_path] if item],
                dry_run=bool(handoff.get("dry_run")),
                created_at=utc_now(),
                missing_evidence=missing_evidence,
            )
        validation_items: list[str] = []
        if handoff_record.tests_run_json:
            for item in handoff_record.tests_run_json:
                name = str(item.get("name") or item.get("title") or item.get("command") or "validation step")
                status = str(item.get("status") or item.get("result") or "unknown").replace("_", " ")
                validation_items.append(f"{name}: {status}")
        else:
            validation_items.append("Not run.")
        what_changed = [line.strip("- ").strip() for line in handoff_record.what_was_built.splitlines() if line.strip()]
        how_to_run = [line.strip("- ").strip() for line in handoff_record.how_to_run.splitlines() if line.strip()]
        next_tasks = [str(item) for item in list(handoff_record.suggested_next_steps_json or [])]
        important_files = [item for item in [handoff.get("artifacts_path"), project.docs_path] if item]
        return format_handoff_message(
            message_id=f"handoff-{project.id}-{orchestration.id if orchestration else 'project'}",
            project_id=project.id,
            orchestration_id=orchestration.id if orchestration else None,
            handoff_status=str(handoff["status"]),
            confidence_level=str(handoff_record.confidence_level),
            evidence_level=str(handoff.get("evidence_status") or "missing"),
            what_changed=what_changed[:8],
            how_to_run=how_to_run[:8],
            validation_items=validation_items[:8],
            known_limitations=[str(item) for item in list(handoff_record.known_limitations_json or [])][:8],
            next_tasks=next_tasks[:8],
            important_files=important_files,
            dry_run=bool(handoff_record.dry_run),
            created_at=handoff_record.created_at,
            missing_evidence=missing_evidence,
        )

    async def get_diagnostic_summary(self) -> dict[str, Any]:
        health = await mission_control_plugin_health()
        checks = list(health.get("checks") or [])
        what_works = [f"{check['label']}: {check['summary']}" for check in checks if check.get("status") == "ready"][:6]
        needs_attention = [f"{check['label']}: {check['summary']}" for check in checks if check.get("status") != "ready"][:8]
        return format_diagnostic_summary_message(
            message_id="diagnostic-summary-headless",
            status=str(health.get("status") or "unknown"),
            what_works=what_works,
            needs_attention=needs_attention,
            recommended_fixes=[str(item) for item in list(health.get("recommended_next_steps") or [])][:8],
            safe_commands=[str(item) for item in list(health.get("safe_troubleshooting_commands") or [])][:8],
            notes=[str(item) for item in list(health.get("notes") or [])][:6],
            created_at=health.get("checked_at") or utc_now(),
        )

    def get_safe_mode(self, db: Session, *, project: Project) -> dict[str, Any]:
        policy = security_service.get_policy(db, project=project, create_if_missing=False)
        preferences = service.get_swarm_preferences(db, project)
        imported_safety = import_service.ensure_safety(db, project, create_if_missing=False) if project.source_type == "existing_folder" else None
        enabled = (
            policy.default_command_policy == "ask"
            and policy.deployment_policy == "deny"
            and policy.destructive_action_policy == "deny"
            and not policy.auto_approve_low_risk
            and not policy.auto_approve_medium_risk
            and not preferences["allow_dynamic_spawning"]
        )
        payload = {
            "project_id": project.id,
            "enabled": enabled,
            "require_all_command_approvals": policy.default_command_policy == "ask",
            "destructive_actions_blocked": policy.destructive_action_policy == "deny",
            "deployment_tools_blocked": policy.deployment_policy == "deny",
            "external_account_tools_require_approval": policy.external_account_policy == "ask",
            "dynamic_spawning_paused": not preferences["allow_dynamic_spawning"],
            "require_read_only_scan_for_imported_codebases": bool(imported_safety is not None),
        }
        payload["bridge_message"] = format_safe_mode_message(
            message_id=f"safe-mode-{project.id}",
            project_id=project.id,
            enabled=enabled,
            details=payload,
            created_at=utc_now(),
        )
        return payload

    def enable_safe_mode(self, db: Session, *, project: Project) -> dict[str, Any]:
        security_service.update_policy(
            db,
            {
                "default_command_policy": "ask",
                "default_tool_policy": "ask",
                "network_access_policy": "ask",
                "external_account_policy": "ask",
                "deployment_policy": "deny",
                "destructive_action_policy": "deny",
                "auto_approve_low_risk": False,
                "auto_approve_medium_risk": False,
                "high_risk_requires_user": True,
            },
            project=project,
        )
        service.update_swarm_preferences(
            db,
            project,
            type("SwarmPrefPayload", (), {
                "optimization_mode": service.get_swarm_preferences(db, project)["optimization_mode"],
                "swarm_aggressiveness": service.get_swarm_preferences(db, project)["swarm_aggressiveness"],
                "max_agents": service.get_swarm_preferences(db, project)["max_agents"],
                "require_approval_above_agent_count": service.get_swarm_preferences(db, project)["require_approval_above_agent_count"],
                "allow_dynamic_spawning": False,
                "allow_dynamic_retirement": service.get_swarm_preferences(db, project)["allow_dynamic_retirement"],
                "docs_depth": service.get_swarm_preferences(db, project)["docs_depth"],
                "testing_depth": service.get_swarm_preferences(db, project)["testing_depth"],
            })(),
        )
        if project.source_type == "existing_folder":
            safety = import_service.ensure_safety(db, project)
            project.write_permission_status = "read_only"
            safety.write_permission_status = "read_only"
            if not safety.read_only_scan_completed:
                import_service.initial_scan(db, project)
        db.flush()
        return self.get_safe_mode(db, project=project)

    async def answer_decision(
        self,
        db: Session,
        decision: PendingDecision,
        *,
        option_id: str,
        selected_text: str,
        free_text: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        allowed = {str(item.get("id")) for item in list(decision.options_json or []) if item.get("id")}
        if option_id not in allowed:
            raise MissionControlError(
                code="MC-DECISION-INVALID-OPTION-001",
                breakpoint="decision.validate_option",
                project_id=decision.project_id,
                orchestration_id=decision.orchestration_id,
                safe_details={"allowed_options": sorted(allowed), "received_option": option_id},
            )
        project = db.get(Project, decision.project_id) if decision.project_id is not None else None
        if decision.status != "pending":
            raise MissionControlError(
                code="MC-DECISION-EXPIRED-001",
                breakpoint="decision.answer",
                project_id=decision.project_id,
                orchestration_id=decision.orchestration_id,
                safe_details={"decision_status": decision.status},
            )
        if decision.source_kind == "attach_workspace":
            updated_record = coordinator.answer_pending_decision(
                db,
                decision,
                option_id=option_id,
                selected_text=selected_text,
                free_text=free_text,
            )
            decision = updated_record
            project = db.get(Project, decision.project_id) if decision.project_id is not None else project
        elif decision.source_kind == "manager_question" and decision.source_id is not None:
            if decision.orchestration_id is not None:
                updated_record = coordinator.answer_pending_decision(
                    db,
                    decision,
                    option_id=option_id,
                    selected_text=selected_text,
                    free_text=free_text,
                )
                decision = updated_record
                project = db.get(Project, decision.project_id) if decision.project_id is not None else project
            else:
                question = db.get(ManagerQuestion, decision.source_id)
                if question is None:
                    raise MissionControlError(
                        code="MC-QUESTION-NOT-FOUND-001",
                        detail="Manager question not found.",
                        breakpoint="decision.answer",
                        project_id=decision.project_id,
                        orchestration_id=decision.orchestration_id,
                    )
                resolved_question = service.answer_question(
                    db,
                    question.id,
                    option_id=option_id,
                    selected_text=selected_text,
                    project_id=project.id if project is not None else None,
                )
                decision.status = "answered"
                decision.answered_at = utc_now()
                decision.answer_json = {
                    "option_id": resolved_question.selected_option_id or option_id,
                    "selected_text": resolved_question.selected_text or selected_text,
                    "free_text": free_text,
                }
                db.flush()
        elif decision.source_kind == "approval_request" and decision.source_id is not None:
            if decision.orchestration_id is not None:
                updated_record = coordinator.answer_pending_decision(
                    db,
                    decision,
                    option_id=option_id,
                    selected_text=selected_text,
                    free_text=free_text,
                )
                decision = updated_record
                project = db.get(Project, decision.project_id) if decision.project_id is not None else project
            else:
                approval = db.get(ApprovalRequest, decision.source_id)
                if approval is None:
                    raise MissionControlError(
                        code="MC-APPROVAL-NOT-FOUND-001",
                        detail="Approval request not found.",
                        breakpoint="decision.answer",
                        project_id=decision.project_id,
                        orchestration_id=decision.orchestration_id,
                    )
                if option_id == "approve_once":
                    service.approve_once(db, approval.id, project_id=project.id if project is not None else None)
                elif option_id == "deny":
                    service.deny_approval(db, approval.id, project_id=project.id if project is not None else None)
                elif option_id in {"allow_for_project", "always_allow_if_safe"}:
                    service.allow_approval_for_project(
                        db,
                        approval.id,
                        project_id=project.id if project is not None else None,
                    )
                else:
                    raise MissionControlError(
                        code="MC-DECISION-INVALID-OPTION-001",
                        breakpoint="decision.validate_option",
                        project_id=decision.project_id,
                        orchestration_id=decision.orchestration_id,
                        safe_details={"received_option": option_id},
                    )
                decision.status = "answered"
                decision.answered_at = utc_now()
                decision.answer_json = {"option_id": option_id, "selected_text": selected_text, "free_text": free_text}
                db.flush()
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
            orchestration = db.get(OrchestrationSession, decision.orchestration_id) if decision.orchestration_id is not None else None
            if option_id == "approve":
                await service.complete_task_by_user(db, task)
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
            decision.status = "answered"
            decision.answered_at = utc_now()
            decision.answer_json = {"option_id": option_id, "selected_text": selected_text, "free_text": free_text}
            db.flush()
            if orchestration is not None:
                coordinator._record_event(
                    db,
                    orchestration,
                    "pending_decision_answered",
                    {"decision_id": decision.id, "decision_type": decision.decision_type, "option_id": option_id},
                )
                coordinator.sync_pending_decisions(db, orchestration)
                if orchestration.status != "completed":
                    coordinator._update_session_status(
                        db,
                        orchestration,
                        status="planning",
                        manager_status="Decision recorded. Mission Control is continuing the orchestration.",
                    )
                    coordinator._schedule_background_turn(orchestration.id, "decision_answered")
        elif decision.source_kind == "subagent_batch" and decision.source_id is not None:
            batch = db.get(SubagentBatch, decision.source_id)
            if batch is None:
                raise MissionControlError(
                    code="MC-SUBAGENT-RESULT-INVALID-001",
                    detail="Subagent batch not found.",
                    breakpoint="subagent_burst.ingest_result",
                    project_id=decision.project_id,
                    orchestration_id=decision.orchestration_id,
                )
            subagent_planner_service.resolve_batch_decision(db, batch, option_id=option_id, selected_text=selected_text)
            decision.status = "answered"
            decision.answered_at = utc_now()
            decision.answer_json = {"option_id": option_id, "selected_text": selected_text, "free_text": free_text}
            db.flush()
        else:
            raise MissionControlError(
                code="MC-DECISION-NOT-FOUND-001",
                detail="Unsupported pending decision source.",
                breakpoint="decision.answer",
                project_id=decision.project_id,
                orchestration_id=decision.orchestration_id,
                safe_details={"source_kind": decision.source_kind},
            )
        if project is not None:
            service.events.publish(
                db,
                project.id,
                "pending_decision_answered",
                {"decision_id": decision.id, "decision_type": decision.decision_type, "option_id": option_id},
            )
            audit_decision = self._audit_decision_for_pending_decision(decision.decision_type, option_id)
            if audit_decision is not None:
                security_service.log_audit(
                    db,
                    project=project,
                    orchestration_id=decision.orchestration_id,
                    decision_id=decision.id,
                    action_type=decision.decision_type,
                    action_summary=decision.title,
                    risk_level=decision.risk_level,
                    decision=audit_decision,
                    decided_by="user",
                    reason=selected_text or option_id,
                    metadata_json={"free_text": free_text},
                )
        orchestration = db.get(OrchestrationSession, decision.orchestration_id) if decision.orchestration_id is not None else None
        if orchestration is not None and project is not None:
            metadata = dict(orchestration.metadata_json or {})
            dry_run_happy_path = metadata.get("headless_happy_path") and decision.decision_type == "command_approval" and (
                str(orchestration.mode or "").strip().lower() == "dry_run" or bool(metadata.get("simulated"))
            )
            if dry_run_happy_path:
                coordinator._record_event(
                    db,
                    orchestration,
                    "approval_recorded",
                    {"decision_id": decision.id, "option_id": option_id},
                )
                if option_id in {"approve_once", "allow_for_project", "always_allow_if_safe"}:
                    coordinator._record_event(
                        db,
                        orchestration,
                        "dry_run_validation_simulated",
                        {
                            "command": "python -m pytest",
                            "status": "not_run",
                            "message": "Mission Control simulated the local pytest validation step in dry-run mode.",
                        },
                    )
                    service.add_handoff_evidence(
                        db,
                        project,
                        {
                            "evidence_type": "test_result",
                            "claim": "Dry-run validation simulated for python -m pytest.",
                            "summary": "Mission Control recorded a simulated local validation step without claiming that real tests executed.",
                            "command": "python -m pytest",
                            "status": "not_run",
                            "metadata_json": {"source": "headless_happy_path", "simulated": True},
                        },
                    )
                    service.generate_evidence_handoff(db, project)
                    coordinator.complete_orchestration(
                        db,
                        orchestration,
                        manager_status="Dry-run orchestration completed with a simulated handoff.",
                        event_type="dry_run_happy_path_completed",
                        payload={"result": "approved"},
                    )
                elif option_id == "deny":
                    coordinator._record_event(
                        db,
                        orchestration,
                        "command_denied",
                        {
                            "command": "python -m pytest",
                            "message": "The user denied the local validation command.",
                        },
                    )
                    service.add_handoff_evidence(
                        db,
                        project,
                        {
                            "evidence_type": "manual_note",
                            "claim": "Validation was not run because the user denied the dry-run validation command.",
                            "summary": "Mission Control completed the dry-run flow with a limitation after approval was denied.",
                            "command": "python -m pytest",
                            "status": "not_run",
                            "metadata_json": {"source": "headless_happy_path", "denied": True},
                        },
                    )
                    service.generate_evidence_handoff(db, project)
                    coordinator.complete_orchestration(
                        db,
                        orchestration,
                        manager_status="Dry-run orchestration completed with limitations because validation approval was denied.",
                        event_type="dry_run_happy_path_completed",
                        payload={"result": "denied"},
                    )
        next_summary = None
        if project is not None:
            next_summary = redact_value(await self.get_status_summary(db, project=project, orchestration=orchestration))
        return self._serialize_pending_decision(decision), next_summary

    async def resume_workspace(self, db: Session, *, workspace_path: str, attach_policy: str) -> dict[str, Any]:
        try:
            workspace = resolve_local_path(workspace_path)
        except PathValidationError as exc:
            raise self._error(
                "MC-WORKSPACE-PATH-MISSING-001",
                detail=str(exc),
                breakpoint="workspace.attach",
                safe_details={"workspace_path": workspace_path},
                caused_by=exc,
            ) from exc
        matches = self._workspace_projects(db, workspace)
        session = self._latest_workspace_orchestration(db, workspace)
        if session is not None:
            project = db.get(Project, session.project_id)
            if project is None:
                raise self._error(
                    "MC-ORCH-SESSION-NOT-FOUND-001",
                    detail="Active orchestration references a missing project.",
                    breakpoint="orchestration.resume_after_decision",
                    orchestration_id=session.id,
                )
            status_summary = await self.get_status_summary(db, project=project, orchestration=session)
            pending = self.get_pending_decisions(db, project=project, orchestration=session)
            return {
                "workspace_path": workspace.as_posix(),
                "status": "found_active" if session.status in ACTIVE_ORCHESTRATION_STATUSES else "found_recent",
                "message": "Mission Control found an orchestration for this workspace.",
                "project": service._serialize_project_card(db, project),
                "orchestration": coordinator._serialize_session(session),
                "status_summary": status_summary,
                "pending_decisions": pending,
                "user_action_required": any(item["status"] == "pending" for item in pending),
            }
        if len(matches) > 1 and attach_policy != "create_new":
            attached = coordinator.attach_workspace(
                db,
                workspace_path=workspace.as_posix(),
                project_name=None,
                mode="existing_codebase",
                read_only_first=True,
                attach_policy=attach_policy,
                source="codex_plugin",
            )
            orchestration_payload = attached.get("orchestration")
            pending: list[dict[str, Any]] = []
            status_summary = None
            orchestration = None
            if orchestration_payload and orchestration_payload.get("id") is not None:
                orchestration = db.get(OrchestrationSession, int(orchestration_payload["id"]))
            if orchestration is not None:
                pending = self.get_pending_decisions(db, project=db.get(Project, orchestration.project_id), orchestration=orchestration)
                project = db.get(Project, orchestration.project_id)
                if project is not None:
                    status_summary = await self.get_status_summary(db, project=project, orchestration=orchestration)
            return {
                "workspace_path": workspace.as_posix(),
                "status": "needs_selection",
                "message": "Mission Control found multiple matching projects for this workspace and needs you to choose one.",
                "project": attached.get("project"),
                "orchestration": orchestration_payload,
                "status_summary": status_summary,
                "pending_decisions": pending,
                "user_action_required": True,
            }
        if matches and attach_policy == "create_new":
            return {
                "workspace_path": workspace.as_posix(),
                "status": "not_found",
                "message": "Mission Control found existing project links for this workspace, so resume cannot create a new project here automatically.",
                "project": None,
                "orchestration": None,
                "status_summary": None,
                "pending_decisions": [],
                "user_action_required": True,
            }
        if matches:
            project = matches[0]
            status_summary = await self.get_status_summary(db, project=project, orchestration=None)
            pending = self.get_pending_decisions(db, project=project, orchestration=None)
            return {
                "workspace_path": workspace.as_posix(),
                "status": "found_project_only",
                "message": "Mission Control found a project for this workspace, but nothing is actively orchestrating right now.",
                "project": service._serialize_project_card(db, project),
                "orchestration": None,
                "status_summary": status_summary,
                "pending_decisions": pending,
                "user_action_required": any(item["status"] == "pending" for item in pending),
            }
        return {
            "workspace_path": workspace.as_posix(),
            "status": "not_found",
            "message": f"Mission Control could not find a known workspace for {workspace.as_posix()}. Attach policy was {attach_policy}.",
            "project": None,
            "orchestration": None,
            "status_summary": None,
            "pending_decisions": [],
            "user_action_required": False,
        }


bridge_runtime_service = BridgeRuntimeService()
