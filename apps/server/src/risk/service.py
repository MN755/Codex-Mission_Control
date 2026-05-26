from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Agent, Project, RiskRecord, Task, utc_now


class RiskService:
    def _validate_owner_agent(self, db: Session, project: Project, owner_agent_id: int | None) -> int | None:
        if owner_agent_id is None:
            return None
        agent = db.get(Agent, owner_agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Owner agent not found")
        if agent.project_id != project.id:
            raise HTTPException(status_code=404, detail="Owner agent not found in this project")
        return agent.id

    def _validate_related_task(self, db: Session, project: Project, related_task_id: int | None) -> int | None:
        if related_task_id is None:
            return None
        task = db.get(Task, related_task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Related task not found")
        if task.project_id != project.id:
            raise HTTPException(status_code=404, detail="Related task not found in this project")
        return task.id

    def list_risks(self, db: Session, project: Project) -> list[RiskRecord]:
        return list(
            db.scalars(
                select(RiskRecord)
                .where(RiskRecord.project_id == project.id)
                .order_by(RiskRecord.severity.desc(), RiskRecord.updated_at.desc(), RiskRecord.id.desc())
            )
        )

    def create_risk(self, db: Session, project: Project, payload: dict[str, Any]) -> RiskRecord:
        owner_agent_id = self._validate_owner_agent(db, project, payload.get("owner_agent_id"))
        related_task_id = self._validate_related_task(db, project, payload.get("related_task_id"))
        normalized_title = " ".join(str(payload["title"]).split())
        existing = db.scalar(
            select(RiskRecord)
            .where(RiskRecord.project_id == project.id, RiskRecord.title == normalized_title, RiskRecord.status != "closed")
            .order_by(RiskRecord.updated_at.desc(), RiskRecord.id.desc())
        )
        if existing is not None:
            existing.description = str(payload.get("description") or existing.description)
            existing.mitigation = payload.get("mitigation") or existing.mitigation
            existing.updated_at = utc_now()
            db.flush()
            return existing
        record = RiskRecord(
            project_id=project.id,
            title=normalized_title,
            description=str(payload["description"]).strip(),
            severity=str(payload.get("severity") or "medium"),
            likelihood=str(payload.get("likelihood") or "medium"),
            owner_agent_id=owner_agent_id,
            mitigation=(str(payload["mitigation"]).strip() if payload.get("mitigation") else None),
            status=str(payload.get("status") or "open"),
            related_task_id=related_task_id,
            created_by=str(payload.get("created_by") or "manager"),
        )
        db.add(record)
        db.flush()
        return record

    def update_risk(self, db: Session, risk_id: int, payload: dict[str, Any]) -> RiskRecord:
        record = db.get(RiskRecord, risk_id)
        if record is None:
            raise ValueError("Risk not found")
        for field in [
            "title",
            "description",
            "severity",
            "likelihood",
            "owner_agent_id",
            "mitigation",
            "status",
            "related_task_id",
        ]:
            if field in payload and payload[field] is not None:
                setattr(record, field, payload[field])
        record.updated_at = utc_now()
        db.flush()
        return record

    def register_plan_risks(self, db: Session, project: Project, risks: list[str]) -> list[RiskRecord]:
        created: list[RiskRecord] = []
        for risk in risks:
            text = str(risk).strip()
            if not text:
                continue
            created.append(
                self.create_risk(
                    db,
                    project,
                    {
                        "title": text[:120],
                        "description": text,
                        "severity": "medium",
                        "likelihood": "medium",
                        "mitigation": "Track this risk in the validation and swarm plan.",
                        "created_by": "manager",
                    },
                )
            )
        return created

    def common_risks(self, db: Session, limit: int = 8) -> list[dict[str, Any]]:
        items = list(
            db.scalars(
                select(RiskRecord)
                .where(RiskRecord.status.in_(["open", "monitoring", "accepted"]))
                .order_by(RiskRecord.updated_at.desc(), RiskRecord.id.desc())
            )
        )
        rows = [
            {
                "title": item.title,
                "detail": f"{item.severity}/{item.likelihood} â€¢ {item.status}",
                "project_id": item.project_id,
                "status": item.status,
            }
            for item in items[:limit]
        ]
        return rows


risk_service = RiskService()
