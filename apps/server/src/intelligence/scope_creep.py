from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ChangeRequest, Project, ScopeChangeSignal, utc_now


class ScopeCreepService:
    def recent_signals(self, db: Session, limit: int = 10) -> list[ScopeChangeSignal]:
        return list(
            db.scalars(
                select(ScopeChangeSignal)
                .order_by(ScopeChangeSignal.created_at.desc(), ScopeChangeSignal.id.desc())
            )
        )[:limit]

    def list_signals(self, db: Session, project: Project) -> list[ScopeChangeSignal]:
        return list(
            db.scalars(
                select(ScopeChangeSignal)
                .where(ScopeChangeSignal.project_id == project.id)
                .order_by(ScopeChangeSignal.created_at.desc(), ScopeChangeSignal.id.desc())
            )
        )

    def _severity_and_action(self, project: Project, summary: str) -> tuple[str, str]:
        text = summary.lower()
        if any(token in text for token in ("rewrite", "architecture", "multi-tenant", "payments", "deployment", "app server", "new auth")):
            return "high", "ask_user"
        if any(token in text for token in ("integration", "dashboard", "reporting", "new feature", "export", "settings")):
            return "medium", "create_future_milestone"
        project_scope = re.findall(r"[a-zA-Z]{4,}", project.idea.lower())
        matched = sum(1 for token in project_scope[:10] if token in text)
        if matched == 0:
            return "medium", "defer"
        return "low", "include_now"

    def analyze(self, db: Session, project: Project, payload: dict[str, Any]) -> list[ScopeChangeSignal]:
        created: list[ScopeChangeSignal] = []
        summaries: list[tuple[str, str, int | None, int | None]] = []
        explicit_summary = str(payload.get("summary") or "").strip()
        if explicit_summary:
            summaries.append(
                (
                    str(payload.get("source") or "manager"),
                    explicit_summary,
                    payload.get("related_task_id"),
                    payload.get("related_message_id"),
                )
            )
        else:
            change_requests = list(
                db.scalars(
                    select(ChangeRequest)
                    .where(ChangeRequest.project_id == project.id, ChangeRequest.status.in_(["new", "triaged", "approved"]))
                    .order_by(ChangeRequest.created_at.desc(), ChangeRequest.id.desc())
                )
            )[:5]
            summaries.extend(("change_request", item.request_text, None, None) for item in change_requests)

        for source, summary, related_task_id, related_message_id in summaries:
            severity, suggested_action = self._severity_and_action(project, summary)
            existing = db.scalar(
                select(ScopeChangeSignal)
                .where(
                    ScopeChangeSignal.project_id == project.id,
                    ScopeChangeSignal.summary == summary,
                    ScopeChangeSignal.status == "open",
                )
                .order_by(ScopeChangeSignal.id.desc())
            )
            if existing is not None:
                created.append(existing)
                continue
            signal = ScopeChangeSignal(
                project_id=project.id,
                source=source,
                summary=summary,
                severity=severity,
                related_task_id=related_task_id,
                related_message_id=related_message_id,
                suggested_action=suggested_action,
                status="open",
            )
            db.add(signal)
            db.flush()
            created.append(signal)
        return created

    def resolve(self, db: Session, signal_id: int, status: str, *, project_id: int | None = None) -> ScopeChangeSignal:
        signal = db.get(ScopeChangeSignal, signal_id)
        if signal is None:
            raise ValueError("Scope creep signal not found")
        if project_id is not None and signal.project_id != project_id:
            raise ValueError("Scope creep signal not found in this project")
        signal.status = status
        signal.resolved_at = utc_now()
        db.flush()
        return signal


scope_creep_service = ScopeCreepService()
