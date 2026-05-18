from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AgentPerformanceRecord, Project


class ReputationService:
    def list_records(self, db: Session, project: Project | None = None) -> list[AgentPerformanceRecord]:
        query = select(AgentPerformanceRecord)
        if project is not None:
            query = query.where(AgentPerformanceRecord.project_id == project.id)
        return list(db.scalars(query.order_by(AgentPerformanceRecord.created_at.desc(), AgentPerformanceRecord.id.desc())))

    def record(self, db: Session, payload: dict[str, Any]) -> AgentPerformanceRecord:
        record = AgentPerformanceRecord(
            project_id=payload.get("project_id"),
            agent_archetype=str(payload.get("agent_archetype") or "generalist"),
            agent_name=payload.get("agent_name"),
            provider=payload.get("provider"),
            model=payload.get("model"),
            runner_mode=str(payload.get("runner_mode") or "auto"),
            task_category=str(payload.get("task_category") or "general"),
            task_id=payload.get("task_id"),
            outcome=str(payload.get("outcome") or "unknown"),
            duration_seconds=payload.get("duration_seconds"),
            review_passed=payload.get("review_passed"),
            tests_passed=payload.get("tests_passed"),
            failure_summary=payload.get("failure_summary"),
        )
        db.add(record)
        db.flush()
        return record

    def summarize(self, db: Session, project: Project | None = None) -> list[dict[str, Any]]:
        records = self.list_records(db, project)
        grouped: dict[tuple[str, str | None, str | None], list[AgentPerformanceRecord]] = defaultdict(list)
        for record in records:
            grouped[(record.agent_archetype, record.provider, record.model)].append(record)

        summaries: list[dict[str, Any]] = []
        for (archetype, provider, model), items in grouped.items():
            total = len(items)
            successes = len([item for item in items if item.outcome == "success"])
            failure_modes = Counter(item.failure_summary for item in items if item.failure_summary)
            category_scores: dict[str, list[int]] = defaultdict(list)
            for item in items:
                category_scores[item.task_category].append(1 if item.outcome == "success" else 0)
            ranked = sorted(category_scores.items(), key=lambda entry: mean(entry[1]), reverse=True)
            summaries.append(
                {
                    "archetype": archetype,
                    "provider": provider,
                    "model": model,
                    "total_tasks": total,
                    "success_rate": round((successes / total) if total else 0.0, 3),
                    "common_failure_modes": [str(item) for item, _ in failure_modes.most_common(3)],
                    "recommended_for": [category for category, _ in ranked[:3]],
                    "avoid_for": [category for category, _ in ranked[-2:] if ranked and mean(category_scores[category]) < 0.5],
                    "confidence": min(100, total * 12),
                }
            )
        summaries.sort(key=lambda item: (item["success_rate"], item["confidence"], item["total_tasks"]), reverse=True)
        return summaries

    def best_categories(self, db: Session, project: Project | None = None) -> dict[str, dict[str, Any]]:
        summaries = self.summarize(db, project)
        best: dict[str, dict[str, Any]] = {}
        for summary in summaries:
            for category in summary["recommended_for"]:
                best.setdefault(category, summary)
        return best


reputation_service = ReputationService()
