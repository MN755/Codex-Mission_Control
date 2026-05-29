from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Project, SwarmAgentSpec, SwarmLaunchSimulation, SwarmPlan, Task


SPAWN_PHASE_ORDER = {
    "plan_review": 0,
    "after_architecture": 1,
    "after_path_mapping": 1,
    "build_start": 2,
    "after_first_slice": 3,
    "after_backend_stabilizes": 3,
    "after_subsystem_progress": 3,
    "validation": 4,
}


class SimulationService:
    def _build_simulation_fields(self, db: Session, project: Project, swarm_plan: SwarmPlan | None = None) -> dict[str, Any]:
        plan = swarm_plan or db.scalar(
            select(SwarmPlan).where(SwarmPlan.project_id == project.id).order_by(SwarmPlan.id.desc())
        )
        specs = (
            list(db.scalars(select(SwarmAgentSpec).where(SwarmAgentSpec.swarm_plan_id == plan.id).order_by(SwarmAgentSpec.priority.asc(), SwarmAgentSpec.id.asc())))
            if plan is not None
            else []
        )
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))

        warnings: list[str] = []
        bottlenecks: list[str] = []
        launch_order: list[dict[str, Any]] = []
        safe_count = 0
        wait_count = 0
        approval_count = 0

        if plan is None or not specs:
            return {
                "project_id": project.id,
                "swarm_plan_id": plan.id if plan is not None else None,
                "safe_to_launch_count": 0,
                "should_wait_count": 0,
                "needs_user_approval_count": 0,
                "conflict_warnings_json": ["No swarm plan exists yet."],
                "bottlenecks_json": ["Mission Control cannot simulate a swarm that does not exist."],
                "recommended_launch_order_json": [],
            }

        path_usage = Counter()
        for spec in specs:
            for path in spec.allowed_paths_json or []:
                path_usage[path] += 1

        overlapping_paths = [path for path, count in path_usage.items() if count > 1]
        if overlapping_paths:
            warnings.append(f"Path overlap detected in {', '.join(overlapping_paths[:5])}.")

        if len(overlapping_paths) >= 2:
            bottlenecks.append("Too many agents touch the same area. Revise ownership before broad launch.")

        if not any(spec.archetype in {"test", "reviewer", "release_handoff"} for spec in specs):
            bottlenecks.append("No dedicated review or validation lane exists yet.")

        if len(specs) > max(1, len(tasks) + 1):
            bottlenecks.append("More planned agents than open task lanes. Some workers will idle.")

        task_paths = {task.id: set(task.allowed_paths_json or []) for task in tasks}
        for spec in specs:
            blocked_by_dependency = "after_" in (spec.spawn_phase or "")
            overlapping = any(path_usage[path] > 1 for path in (spec.allowed_paths_json or []))
            launch_order.append(
                {
                    "name": spec.name,
                    "archetype": spec.archetype,
                    "spawn_phase": spec.spawn_phase,
                    "priority": spec.priority,
                    "status": "wait" if blocked_by_dependency or overlapping else "launch",
                }
            )
            if blocked_by_dependency or overlapping:
                wait_count += 1
            else:
                safe_count += 1
            if spec.archetype in {"security", "ops"} or any(path for path in (spec.allowed_paths_json or []) if path.lower() in {".github", "scripts", "ops"}):
                approval_count += 1

        if any(task.status in {"blocked", "waiting_on_paths"} for task in tasks):
            warnings.append("Open blocked tasks exist. Launching more workers may amplify churn instead of reducing it.")
            wait_count += 1

        if not any(task.status == "done" for task in tasks) and any("after_" in (spec.spawn_phase or "") for spec in specs):
            bottlenecks.append("Deferred phases depend on work that has not started yet.")

        launch_order.sort(key=lambda item: (SPAWN_PHASE_ORDER.get(str(item["spawn_phase"]), 99), int(item["priority"])))

        return {
            "project_id": project.id,
            "swarm_plan_id": plan.id,
            "safe_to_launch_count": safe_count,
            "should_wait_count": wait_count,
            "needs_user_approval_count": approval_count,
            "conflict_warnings_json": warnings,
            "bottlenecks_json": bottlenecks,
            "recommended_launch_order_json": launch_order,
        }

    def list_simulations(self, db: Session, project: Project) -> list[SwarmLaunchSimulation]:
        return list(
            db.scalars(
                select(SwarmLaunchSimulation)
                .where(SwarmLaunchSimulation.project_id == project.id)
                .order_by(SwarmLaunchSimulation.created_at.desc(), SwarmLaunchSimulation.id.desc())
            )
        )

    def latest_simulation(self, db: Session, project: Project) -> SwarmLaunchSimulation | None:
        return db.scalar(
            select(SwarmLaunchSimulation)
            .where(SwarmLaunchSimulation.project_id == project.id)
            .order_by(SwarmLaunchSimulation.created_at.desc(), SwarmLaunchSimulation.id.desc())
        )

    def preview_launch(self, db: Session, project: Project, swarm_plan: SwarmPlan | None = None) -> SwarmLaunchSimulation:
        return SwarmLaunchSimulation(**self._build_simulation_fields(db, project, swarm_plan))

    def simulate_launch(self, db: Session, project: Project, swarm_plan: SwarmPlan | None = None) -> SwarmLaunchSimulation:
        simulation = SwarmLaunchSimulation(**self._build_simulation_fields(db, project, swarm_plan))
        db.add(simulation)
        db.flush()
        return simulation


simulation_service = SimulationService()
