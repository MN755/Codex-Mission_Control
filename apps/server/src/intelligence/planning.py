from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from capabilities import capability_service
from models import Project
from playbooks import playbook_service
from preferences import preference_service
from risk import risk_service
from simulation import simulation_service
from validation_coverage import validation_coverage_service

from .reputation import reputation_service
from .scope_creep import scope_creep_service


class PlanningIntelligenceService:
    def build_context(self, db: Session, project: Project) -> dict[str, Any]:
        playbook_state = playbook_service.project_playbook_state(db, project)
        capabilities = capability_service.capability_matrix(db)
        reputation = reputation_service.summarize(db, project)
        preferences = preference_service.get_effective_preferences(db, project)
        risks = risk_service.list_risks(db, project)
        scope_signals = scope_creep_service.list_signals(db, project)
        coverage = validation_coverage_service.list_coverage(db, project) or validation_coverage_service.recompute(db, project)
        latest_simulation = simulation_service.latest_simulation(db, project)
        return {
            "playbook": {
                "key": playbook_state.get("playbook_key"),
                "status": playbook_state.get("status"),
                "why": playbook_state.get("why"),
            },
            "capability_matrix": capabilities,
            "agent_reputation": reputation[:6],
            "preferences": [{"key": item.key, "value_json": item.value_json, "scope": item.scope, "source": item.source} for item in preferences],
            "open_risks": [
                {
                    "title": item.title,
                    "severity": item.severity,
                    "likelihood": item.likelihood,
                    "mitigation": item.mitigation,
                    "status": item.status,
                }
                for item in risks[:8]
            ],
            "scope_signals": [
                {
                    "summary": item.summary,
                    "severity": item.severity,
                    "suggested_action": item.suggested_action,
                    "status": item.status,
                }
                for item in scope_signals[:6]
            ],
            "validation_coverage": [
                {
                    "area": item.area,
                    "coverage_status": item.coverage_status,
                    "evidence_summary": item.evidence_summary,
                }
                for item in coverage
            ],
            "latest_launch_simulation": (
                {
                    "safe_to_launch_count": latest_simulation.safe_to_launch_count,
                    "should_wait_count": latest_simulation.should_wait_count,
                    "needs_user_approval_count": latest_simulation.needs_user_approval_count,
                    "conflict_warnings": latest_simulation.conflict_warnings_json,
                    "bottlenecks": latest_simulation.bottlenecks_json,
                }
                if latest_simulation is not None
                else None
            ),
        }

    def recommend_model_policy(self, db: Session, task_category: str) -> str:
        best = capability_service.top_models_for_category(db, task_category, limit=1)
        if not best:
            return "No benchmark data yet. Manager will use the default policy."
        item = best[0]
        return (
            f"Prefer {item['provider']} / {item['model']} in {item['runner_mode']} mode for {task_category} "
            f"based on recorded score {item['score']} from {item['sample_size']} sample(s)."
        )


planning_intelligence_service = PlanningIntelligenceService()
