from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import CapabilityBenchmark, utc_now


CAPABILITY_CATEGORIES = [
    "code_editing",
    "bug_fixing",
    "test_generation",
    "docs_writing",
    "json_schema_following",
    "long_context_planning",
    "shell_command_reasoning",
    "speed",
    "reliability",
]


class CapabilityService:
    def list_benchmarks(self, db: Session) -> list[CapabilityBenchmark]:
        return list(
            db.scalars(
                select(CapabilityBenchmark).order_by(
                    CapabilityBenchmark.provider.asc(),
                    CapabilityBenchmark.model.asc(),
                    CapabilityBenchmark.runner_mode.asc(),
                    CapabilityBenchmark.category.asc(),
                )
            )
        )

    def record_benchmark(self, db: Session, payload: dict[str, Any]) -> CapabilityBenchmark:
        record = CapabilityBenchmark(
            provider=str(payload["provider"]).strip(),
            model=str(payload["model"]).strip(),
            runner_mode=str(payload.get("runner_mode") or "auto").strip() or "auto",
            category=str(payload["category"]).strip(),
            score=max(0, min(100, int(payload["score"]))),
            sample_size=max(0, int(payload.get("sample_size") or 0)),
            notes=(str(payload["notes"]).strip() if payload.get("notes") else None),
            last_run_at=payload.get("last_run_at") or utc_now(),
        )
        db.add(record)
        db.flush()
        return record

    def capability_matrix(self, db: Session) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str], list[CapabilityBenchmark]] = defaultdict(list)
        for record in self.list_benchmarks(db):
            grouped[(record.provider, record.model, record.runner_mode)].append(record)

        rows: list[dict[str, Any]] = []
        for provider, model, runner_mode in sorted(grouped.keys()):
            records = grouped[(provider, model, runner_mode)]
            scores = {category: None for category in CAPABILITY_CATEGORIES}
            notes: list[str] = []
            sample_size = 0
            for record in records:
                scores[record.category] = record.score
                sample_size += record.sample_size
                if record.notes and record.notes not in notes:
                    notes.append(record.notes)
            rows.append(
                {
                    "provider": provider,
                    "model": model,
                    "runner_mode": runner_mode,
                    "scores": scores,
                    "sample_size": sample_size,
                    "notes": notes[:3],
                    "recommendation_note": (
                        "No benchmark data yet. Manager will use default policy."
                        if not any(value is not None for value in scores.values())
                        else "Use recorded benchmark data as a hint, not a lie detector."
                    ),
                }
            )
        return rows

    def top_models_for_category(self, db: Session, category: str, limit: int = 3) -> list[dict[str, Any]]:
        records = [
            record
            for record in self.list_benchmarks(db)
            if record.category == category and record.sample_size > 0
        ]
        records.sort(key=lambda item: (item.score, item.sample_size, item.updated_at), reverse=True)
        return [
            {
                "provider": item.provider,
                "model": item.model,
                "runner_mode": item.runner_mode,
                "score": item.score,
                "sample_size": item.sample_size,
            }
            for item in records[:limit]
        ]

    def benchmark_summary(self, db: Session) -> dict[str, Any]:
        matrix = self.capability_matrix(db)
        top_categories = {
            category: self.top_models_for_category(db, category, limit=1)[0]
            for category in CAPABILITY_CATEGORIES
            if self.top_models_for_category(db, category, limit=1)
        }
        return {
            "has_data": bool(matrix),
            "total_records": len(self.list_benchmarks(db)),
            "matrix": matrix,
            "top_categories": top_categories,
        }


capability_service = CapabilityService()
