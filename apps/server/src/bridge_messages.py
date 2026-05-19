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
from imported_codebase import import_service
from manager import service
from models import (
    Agent,
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
from security.path_validation import PathValidationError, resolve_local_path
from security.redaction import redact_text, redact_value
from security.service import security_service
from subagent_planner import subagent_planner_service


ACTIVE_AGENT_STATUSES = {"starting", "working", "waiting", "needs_review", "blocked"}


class BridgeRuntimeService:
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

    def _workspace_projects(self, db: Session, workspace: Path) -> list[Project]:
        workspace_text = workspace.as_posix()
        return list(
            db.scalars(
                select(Project)
                .where(or_(Project.workspace_path == workspace_text, Project.source_path == workspace_text))
                .order_by(Project.updated_at.desc(), Project.id.desc())
            )
        )

    def _latest_workspace_orchestration(self, db: Session, workspace: Path) -> OrchestrationSession | None:
        workspace_text = workspace.as_posix()
        return db.scalar(
            select(OrchestrationSession)
            .where(OrchestrationSession.workspace_path == workspace_text)
            .order_by(
                OrchestrationSession.status.in_(list(ACTIVE_ORCHESTRATION_STATUSES)).desc(),
                OrchestrationSession.updated_at.desc(),
                OrchestrationSession.id.desc(),
            )
        )

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
    ) -> dict[str, Any]:
        session = coordinator.start_orchestration(
            db,
            project=project,
            source=source,
            user_request=user_request,
            orchestration_id=orchestration_id,
        )
        return coordinator._serialize_session(session)

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

    def _sync_question_decision(
        self,
        db: Session,
        project: Project,
        question: ManagerQuestion,
        orchestration: OrchestrationSession | None,
    ) -> PendingDecision:
        record = db.scalar(
            select(PendingDecision)
            .where(PendingDecision.source_kind == "manager_question", PendingDecision.source_id == question.id)
            .order_by(PendingDecision.id.desc())
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
        record = db.scalar(
            select(PendingDecision)
            .where(PendingDecision.source_kind == "approval_request", PendingDecision.source_id == approval.id)
            .order_by(PendingDecision.id.desc())
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
        active_keys: set[tuple[str, int]] = set()
        for question in questions:
            active_keys.add(("manager_question", question.id))
            self._sync_question_decision(db, project, question, orchestration)
        for approval in approvals:
            active_keys.add(("approval_request", approval.id))
            self._sync_approval_decision(db, project, approval, orchestration)
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
            raise ValueError("Project not found for status summary.")
        pending = self.get_pending_decisions(db, project=project, orchestration=orchestration)
        current_action = await service.get_project_action(db, project)
        health = service.get_project_health(db, project)
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
        waiting = [f"{item['title']}: {item['message']}" if item.get("message") else item["title"] for item in pending]
        blockers = list(dict.fromkeys([*list(current_action.get("message") and [str(current_action["message"])] or []), *list(health.get("reasons") or [])]))
        swarm_plan = service.get_swarm_plan(db, project)
        swarm_summary = "Not planned"
        if swarm_plan:
            swarm_summary = f"{swarm_plan.get('mode', 'unknown')} / {swarm_plan.get('status', 'unknown')}"
        manager_status = orchestration.manager_status if orchestration is not None else str(current_action.get("title") or "Monitoring")
        user_action_needed = "yes" if waiting else "no"
        return format_status_summary_message(
            message_id=f"status-summary-{project.id}-{orchestration.id if orchestration else 'project'}",
            project_id=project.id,
            orchestration_id=orchestration.id if orchestration else None,
            title="Mission Control status",
            summary=redact_text(manager_status[:220]),
            project_name=project.name,
            manager_status=manager_status,
            mode=f"{project.runner_mode} / {project.manager_mode}",
            swarm=swarm_summary,
            user_action_needed=user_action_needed,
            current_work=current_work[:5],
            waiting_on_you=waiting[:5],
            next_expected_step=str(current_action.get("title") or "Mission Control will continue with the next safe background step."),
            risk_level="high" if blockers else ("medium" if waiting else None),
            created_at=utc_now(),
            orchestration_status=orchestration.status if orchestration is not None else project.status,
            current_blockers=blockers[:5],
            handoff_readiness=str(handoff.get("status") or "not_ready"),
            active_agent_count=len([agent for agent in active_agents if agent.status in ACTIVE_AGENT_STATUSES]),
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
    ) -> dict[str, Any]:
        attached = self.attach_workspace(
            db,
            workspace_path=workspace_path,
            project_name=project_name,
            mode=mode,
            read_only_first=read_only_first,
            attach_policy=attach_policy,
            source="codex_plugin",
        )
        project = db.get(Project, int(attached["project_id"]))
        if project is None:
            raise ValueError("Project not found after workspace attach.")
        project.runner_mode = "dry_run"
        if project.settings is not None:
            project.settings.runner_mode = "dry_run"
        service.open_project(db, project)
        orchestration_payload = self.start_orchestration(
            db,
            project=project,
            source="test",
            user_request=user_request,
            orchestration_id=attached.get("orchestration", {}).get("id") if attached.get("orchestration") else None,
        )
        orchestration = db.get(OrchestrationSession, int(orchestration_payload["id"]))
        if orchestration is None:
            raise ValueError("Orchestration session was not created.")

        pending: list[dict[str, Any]] = []
        for _ in range(20):
            await asyncio.sleep(0.05)
            db.expire_all()
            orchestration = db.get(OrchestrationSession, int(orchestration_payload["id"]))
            if orchestration is None:
                raise ValueError("Orchestration session disappeared during demo setup.")
            pending = self.get_pending_decisions(db, project=project, orchestration=orchestration)
            if pending:
                break

        if not pending:
            service._create_approval(
                db,
                project,
                request_type="command",
                title="Approve simulated dry-run test command",
                reason_short="Run a simulated local test command so Mission Control can continue the headless bridge flow safely.",
                risk_level="medium",
                cwd=project.workspace_path,
                request_payload_json={
                    "command": "python -m pytest",
                    "scope": ["tests/"],
                    "simulated": True,
                },
            )
            db.flush()
            pending = self.get_pending_decisions(db, project=project, orchestration=orchestration)

        if not pending:
            raise ValueError("Mission Control could not create a pending decision for the headless happy path demo.")

        initial_status_summary = await self.get_status_summary(db, project=project, orchestration=orchestration)
        selected = next((item for item in pending if item["decision_type"] == "command_approval"), pending[0])

        for decision in pending:
            if decision["id"] == selected["id"]:
                continue
            option = self._preferred_option(decision)
            if option is None:
                continue
            decision_record = db.get(PendingDecision, int(decision["id"]))
            if decision_record is None or decision_record.status != "pending":
                continue
            await self.answer_decision(
                db,
                decision_record,
                option_id=str(option["id"]),
                selected_text=str(option.get("label") or option["id"]),
            )
            db.flush()

        selected_record = db.get(PendingDecision, int(selected["id"]))
        if selected_record is None:
            raise ValueError("Pending decision not found for the headless happy path demo.")
        decision_bridge_message = self.get_bridge_message_for_decision(db, selected_record)
        selected_option = self._preferred_option(selected)
        if selected_option is None:
            raise ValueError("Pending decision has no selectable options.")
        answered_decision, next_status_summary = await self.answer_decision(
            db,
            selected_record,
            option_id=str(selected_option["id"]),
            selected_text=str(selected_option.get("label") or selected_option["id"]),
        )

        service.add_handoff_evidence(
            db,
            project,
            {
                "evidence_type": "manual_note",
                "claim": "Headless happy path demo was executed in dry-run mode.",
                "summary": "Mission Control completed a simulated attach, decision relay, digest, and handoff pass without claiming real execution.",
                "command": "dry-run demo",
                "status": "not_run",
                "metadata_json": {"source": "headless_happy_path_demo"},
            },
        )
        service.generate_evidence_handoff(db, project)
        event_digest = self.get_event_digest(db, project=project, orchestration=orchestration, window="since_orchestration_start")
        handoff_summary = self.get_handoff_summary(db, project=project, orchestration=orchestration)

        return {
            "attach": attached,
            "orchestration": orchestration_payload,
            "initial_status_summary": initial_status_summary,
            "pending_decision": selected,
            "decision_bridge_message": decision_bridge_message,
            "answer_result": {
                "decision": answered_decision,
                "next_status_summary": next_status_summary,
            },
            "event_digest": event_digest,
            "handoff_summary": handoff_summary,
            "dry_run": True,
        }

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
            raise ValueError("Project not found for event digest.")
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
            raise ValueError("Project not found for handoff summary.")
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
                status = str(item.get("status") or item.get("result") or "unknown")
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
        policy = security_service.get_policy(db, project=project)
        preferences = service.get_swarm_preferences(db, project)
        imported_safety = import_service.ensure_safety(db, project) if project.source_type == "existing_folder" else None
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
            raise ValueError("Selected option is not allowed for this decision.")
        project = db.get(Project, decision.project_id) if decision.project_id is not None else None
        if decision.status != "pending":
            raise ValueError("Pending decision is no longer actionable.")
        if decision.source_kind == "manager_question" and decision.source_id is not None:
            question = db.get(ManagerQuestion, decision.source_id)
            if question is None:
                raise ValueError("Manager question not found.")
            service.answer_question(db, question.id, option_id=option_id, selected_text=selected_text, project_id=question.project_id)
        elif decision.source_kind == "approval_request" and decision.source_id is not None:
            approval = db.get(ApprovalRequest, decision.source_id)
            if approval is None:
                raise ValueError("Approval request not found.")
            if option_id == "approve_once":
                service.approve_once(db, approval.id, project_id=approval.project_id)
            elif option_id == "deny":
                service.deny_approval(db, approval.id, project_id=approval.project_id)
            elif option_id in {"always_allow_for_project", "always_allow_if_safe"}:
                service.allow_approval_for_project(db, approval.id, project_id=approval.project_id)
            else:
                raise ValueError("Unsupported approval resolution option.")
        elif decision.source_kind == "attach_workspace":
            updated = coordinator.answer_pending_decision(db, decision, option_id=option_id, selected_text=selected_text, free_text=free_text)
            next_summary = None
            if updated.orchestration_id is not None:
                orchestration = db.get(OrchestrationSession, updated.orchestration_id)
                project = db.get(Project, updated.project_id) if updated.project_id is not None else None
                if orchestration is not None and project is not None:
                    next_summary = redact_value(await self.get_status_summary(db, project=project, orchestration=orchestration))
            return self._serialize_pending_decision(updated), next_summary
        elif decision.source_kind == "subagent_batch" and decision.source_id is not None:
            batch = db.get(SubagentBatch, decision.source_id)
            if batch is None:
                raise ValueError("Subagent batch not found.")
            subagent_planner_service.resolve_batch_decision(db, batch, option_id=option_id, selected_text=selected_text)
        else:
            raise ValueError("Unsupported pending decision source.")

        decision.status = "answered"
        decision.answered_at = utc_now()
        decision.answer_json = {"option_id": option_id, "selected_text": selected_text, "free_text": free_text}
        db.flush()
        if project is not None:
            service.events.publish(
                db,
                project.id,
                "pending_decision_answered",
                {"decision_id": decision.id, "decision_type": decision.decision_type, "option_id": option_id},
            )
            security_service.log_audit(
                db,
                project=project,
                orchestration_id=decision.orchestration_id,
                decision_id=decision.id,
                action_type=decision.decision_type,
                action_summary=decision.title,
                risk_level=decision.risk_level,
                decision=option_id,
                decided_by="user",
                reason=selected_text or option_id,
                metadata_json={"free_text": free_text},
            )
        next_summary = None
        if project is not None:
            orchestration = db.get(OrchestrationSession, decision.orchestration_id) if decision.orchestration_id is not None else None
            next_summary = redact_value(await self.get_status_summary(db, project=project, orchestration=orchestration))
        return self._serialize_pending_decision(decision), next_summary

    async def resume_workspace(self, db: Session, *, workspace_path: str, attach_policy: str) -> dict[str, Any]:
        try:
            workspace = resolve_local_path(workspace_path)
        except PathValidationError as exc:
            raise ValueError(str(exc)) from exc
        matches = self._workspace_projects(db, workspace)
        session = self._latest_workspace_orchestration(db, workspace)
        if session is not None:
            project = db.get(Project, session.project_id)
            if project is None:
                raise ValueError("Active orchestration references a missing project.")
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
