from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Agent, Project, RiskRecord, Task, utc_now


class RiskService:
    @staticmethod
    def _normalize_title(title: Any) -> str:
        normalized = " ".join(str(title).split())
        if not normalized:
            raise ValueError("Risk title cannot be blank")
        return normalized

    def _validate_related_refs(self, db: Session, project: Project, payload: dict[str, Any]) -> None:
        owner_agent_id = payload.get("owner_agent_id")
        if owner_agent_id is not None:
            agent = db.get(Agent, owner_agent_id)
            if agent is None or agent.project_id != project.id:
                raise ValueError("Risk owner agent not found in this project")

        related_task_id = payload.get("related_task_id")
        if related_task_id is not None:
            task = db.get(Task, related_task_id)
            if task is None or task.project_id != project.id:
                raise ValueError("Risk related task not found in this project")

    def list_risks(self, db: Session, project: Project) -> list[RiskRecord]:
        return list(
            db.scalars(
                select(RiskRecord)
                .where(RiskRecord.project_id == project.id)
                .order_by(RiskRecord.severity.desc(), RiskRecord.updated_at.desc(), RiskRecord.id.desc())
            )
        )

    def create_risk(self, db: Session, project: Project, payload: dict[str, Any]) -> RiskRecord:
        normalized_title = self._normalize_title(payload["title"])
        self._validate_related_refs(db, project, payload)
        matches = list(
            db.scalars(
                select(RiskRecord)
                .where(RiskRecord.project_id == project.id, RiskRecord.title == normalized_title, RiskRecord.status != "closed")
                .order_by(RiskRecord.updated_at.desc(), RiskRecord.id.desc())
            )
        )
        existing = matches[0] if matches else None
        if existing is not None:
            for duplicate in matches[1:]:
                db.delete(duplicate)
            existing.description = str(payload.get("description") or existing.description)
            existing.severity = str(payload.get("severity") or existing.severity)
            existing.likelihood = str(payload.get("likelihood") or existing.likelihood)
            existing.owner_agent_id = payload.get("owner_agent_id", existing.owner_agent_id)
            existing.mitigation = payload.get("mitigation") or existing.mitigation
            existing.status = str(payload.get("status") or existing.status)
            existing.related_task_id = payload.get("related_task_id", existing.related_task_id)
            existing.updated_at = utc_now()
            db.flush()
            return existing
        record = RiskRecord(
            project_id=project.id,
            title=normalized_title,
            description=str(payload["description"]).strip(),
            severity=str(payload.get("severity") or "medium"),
            likelihood=str(payload.get("likelihood") or "medium"),
            owner_agent_id=payload.get("owner_agent_id"),
            mitigation=(str(payload["mitigation"]).strip() if payload.get("mitigation") else None),
            status=str(payload.get("status") or "open"),
            related_task_id=payload.get("related_task_id"),
            created_by=str(payload.get("created_by") or "manager"),
        )
        db.add(record)
        db.flush()
        return record

    def update_risk(self, db: Session, project: Project, risk_id: int, payload: dict[str, Any]) -> RiskRecord:
        record = db.get(RiskRecord, risk_id)
        if record is None:
            raise ValueError("Risk not found")
        if record.project_id != project.id:
            raise ValueError("Risk not found in this project")
        self._validate_related_refs(db, project, payload)
        if "title" in payload and payload["title"] is not None:
            payload["title"] = self._normalize_title(payload["title"])
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
        return [
            {
                "title": item.title,
                "detail": f"{item.severity}/{item.likelihood} | {item.status}",
                "project_id": item.project_id,
                "status": item.status,
            }
            for item in items[:limit]
        ]

    def risk_summary(self, db: Session, *, project: Project | None = None) -> dict[str, Any]:
        items = self.list_risks(db, project) if project is not None else list(
            db.scalars(select(RiskRecord).order_by(RiskRecord.updated_at.desc(), RiskRecord.id.desc()))
        )
        by_status: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        open_count = 0
        for item in items:
            by_status[item.status] = by_status.get(item.status, 0) + 1
            by_severity[item.severity] = by_severity.get(item.severity, 0) + 1
            if item.status in {"open", "monitoring", "accepted"}:
                open_count += 1
        return {
            "project_id": project.id if project is not None else None,
            "total_count": len(items),
            "open_count": open_count,
            "status_counts": by_status,
            "severity_counts": by_severity,
            "top_risks": self.common_risks(db, limit=5) if project is None else [
                {
                    "title": item.title,
                    "detail": f"{item.severity}/{item.likelihood} | {item.status}",
                    "project_id": item.project_id,
                    "status": item.status,
                }
                for item in items[:5]
            ],
        }


risk_service = RiskService()
