from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import sample_workspace
from config import DEFAULT_CLI_MODEL
from codex_runner.base import BaseCodexRunner
from codex_runner.base import RunnerHandle
from db import SessionLocal
from main import service as app_service
from manager import MissionControlService, STALE_BLOCKED_REQUEUE_REASON
from models import Agent, AgentExecutionTrace, AgentRun, ChangeRequest, OrchestrationSession, PathReservation, Plan, Project, ProjectEvent, RecoveryPlan, SwarmAgentSpec, SwarmPlan, Task
from project_settings import DEFAULT_CODEX_WORKER_MODEL, get_or_create_project_settings, resolve_manager_settings, resolve_worker_settings
from schemas import ManagerDocFile, ManagerDocUpdate, ManagerHandoff, ManagerTaskDecomposition, ManagerTaskItem, ManagerWorkerDecision, ProjectSettingsUpdate, RunnerResultEnvelope, WorkerReport
from sqlalchemy.exc import OperationalError
from sqlalchemy import select


def test_manager_worker_decision_normalizes_zero_refs_to_none() -> None:
    decision = ManagerWorkerDecision(
        decision_type="wait",
        summary_markdown="No new safe assignment is available yet.",
        task_id=0,
        assign_to_agent_id="0",
    )

    assert decision.task_id is None
    assert decision.assign_to_agent_id is None


def test_fresh_benchmark_reset_detector_accepts_reset_count_wording() -> None:
    request = (
        "Fresh benchmark reset after Mission Control stale blocked assignment reconciliation fix. "
        "Reset accepted issue count to 0 because Mission Control code changed."
    )

    assert MissionControlService._request_implies_fresh_benchmark_reset(request) is True


def test_classify_failure_treats_usage_limit_as_transient() -> None:
    service = MissionControlService()

    assert (
        service._classify_failure(
            summary="You've hit your usage limit. Try again later.",
            blockers=[],
            risks=[],
            diagnostics=[],
            report_status="blocked",
        )
        == "transient"
    )


def test_deterministic_worker_decision_waits_on_transient_blocker() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Transient Blocker Backoff",
            idea="Do not spawn unblock-task chains for provider quota failures.",
            workspace_path=sample_workspace("transient-blocker-backoff"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Apps Server Subsystem Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Apps Server Defect Batch",
            goal="Repair apps/server issues.",
            scope="Server-only lane.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary="You've hit your usage limit. Visit settings/usage to purchase more credits or try again later.",
            files_changed=[],
            tests_run=[],
            blockers=["You've hit your usage limit. Visit settings/usage to purchase more credits or try again later."],
            risks=[],
            recommended_next_task="Retry after the provider/runtime blocker is resolved.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, task, report)

        assert decision.decision_type == "wait"
        assert "external provider/runtime blocker" in decision.summary_markdown
    finally:
        db.close()


def test_swarm_sync_reactivates_retired_target_agent() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("swarm-sync-reactivates-retired-target"))
    (workspace / "apps" / "dashboard" / "public").mkdir(parents=True, exist_ok=True)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Reactivated Target Agent",
            idea="A fresh plan should not leave target lanes retired.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        plan = SwarmPlan(
            project_id=project.id,
            mode="defect_campaign",
            goal="Run the dashboard public defect lane.",
            recommended_agent_count=1,
            max_agent_count=1,
            coordination_risk="low",
            path_conflict_risk="low",
            expected_bottlenecks_json=[],
            validation_strategy_json=[],
            strategy_summary="One target lane.",
            approved_by_user=True,
            status="approved",
        )
        db.add(plan)
        db.flush()
        stale_task = Task(
            project_id=project.id,
            title="Old Dashboard Public Lane",
            goal="Old retired-lane work.",
            scope="Legacy target lane.",
            agent_role="Feature specialist",
            milestone="Old plan",
            allowed_paths_json=["apps/dashboard/public"],
            forbidden_paths_json=[],
            validation_steps_json=["npm run build"],
            success_criteria_json=["Old lane completed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add(stale_task)
        db.flush()
        spec = SwarmAgentSpec(
            swarm_plan_id=plan.id,
            project_id=project.id,
            archetype="feature",
            name="Apps Dashboard Public Subsystem Builder",
            mission="Own apps/dashboard/public defects.",
            model_policy="Use the default worker model.",
            toolset_json=["feature_work"],
            allowed_paths_json=["apps/dashboard/public"],
            forbidden_paths_json=[],
            spawn_phase="build_start",
            retire_when="The lane is complete.",
            priority=10,
            iteration_budget=2,
            status="planned",
        )
        retired_agent = Agent(
            project_id=project.id,
            name="Apps Dashboard Public Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="retired",
            workspace_path=project.workspace_path,
            current_task_id=stale_task.id,
            current_action="Retired by an older plan.",
            session_ref="old-session",
            active_usage_json={"input_tokens": 42},
            active_model="gpt-5.3-codex-spark",
            active_runner_type="codex_cli",
            locked_paths_json=["apps/dashboard/public"],
            failure_count=3,
        )
        db.add_all([spec, retired_agent])
        db.commit()

        spawned, retired = service._sync_agents_to_swarm_plan(db, project, plan)

        db.refresh(retired_agent)
        db.refresh(spec)
        assert spawned == 1
        assert retired == 0
        assert spec.status == "spawned"
        assert retired_agent.status == "idle"
        assert retired_agent.current_task_id is None
        assert retired_agent.current_action is None
        assert retired_agent.session_ref is None
        assert retired_agent.active_usage_json is None
        assert retired_agent.active_model is None
        assert retired_agent.active_runner_type is None
        assert retired_agent.locked_paths_json == []
        assert retired_agent.failure_count == 0
        assert retired_agent.swarm_plan_id == plan.id
    finally:
        db.close()


def test_deterministic_worker_decision_skips_retired_worker_for_follow_up_assignment() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Retired Follow Up Guard",
            idea="Do not assign unblock work to retired workers.",
            workspace_path=sample_workspace("retired-follow-up-guard"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        retired_worker = Agent(
            project_id=project.id,
            name="Retired Worker",
            role="Validation",
            kind="worker",
            status="retired",
            workspace_path=project.workspace_path,
        )
        active_worker = Agent(
            project_id=project.id,
            name="Active Worker",
            role="Validation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task_owner = Agent(
            project_id=project.id,
            name="Task Owner",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Apps Dashboard Defect Batch",
            goal="Repair dashboard issues.",
            scope="Dashboard-only lane.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/dashboard"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=10,
            failure_count=0,
        )
        db.add_all([retired_worker, active_worker, task_owner, task])
        db.flush()

        report = WorkerReport(
            agent=task_owner.name,
            task_id=str(task.id),
            status="blocked",
            summary="Need a focused unblock task for a reproducible local issue.",
            files_changed=[],
            tests_run=[],
            blockers=["Dashboard reproduction points at apps/dashboard/widget.tsx."],
            risks=[],
            recommended_next_task="Inspect apps/dashboard/widget.tsx and remove the blocker.",
        )

        decision = service._deterministic_worker_decision(db, project, task_owner, task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == active_worker.id
    finally:
        db.close()


def test_manager_doc_generation_uses_deterministic_for_dry_run(client) -> None:
    response = client.post(
        "/api/projects",
        json={
            "name": "Docs Demo",
            "idea": "Build a local project manager",
            "workspace_path": sample_workspace("docs-demo"),
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    project_id = response.json()["id"]
    docs = client.post(f"/api/projects/{project_id}/docs/generate").json()
    assert docs["manager_mode_used"] == "deterministic"


def test_manager_doc_generation_rejects_paths_outside_docs_root(client, monkeypatch) -> None:
    response = client.post(
        "/api/projects",
        json={
            "name": "Docs Escape Demo",
            "idea": "Build a local project manager",
            "workspace_path": sample_workspace("docs-escape-demo"),
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    project_id = response.json()["id"]

    async def fake_resolve(*args, **kwargs):
        return ManagerDocUpdate(summary_markdown="x", files=[ManagerDocFile(filename="../escape.txt", content="owned")]), "deterministic"

    monkeypatch.setattr(app_service, "_resolve_manager_model", fake_resolve)
    docs = client.post(f"/api/projects/{project_id}/docs/generate")
    assert docs.status_code == 400
    assert "stay inside the selected root" in docs.json()["detail"].lower()


def test_manager_doc_generation_creates_nested_parent_directories(client, monkeypatch) -> None:
    workspace_path = sample_workspace("docs-nested-demo")
    response = client.post(
        "/api/projects",
        json={
            "name": "Docs Nested Demo",
            "idea": "Build a local project manager",
            "workspace_path": workspace_path,
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    project = response.json()

    async def fake_resolve(*args, **kwargs):
        return ManagerDocUpdate(summary_markdown="x", files=[ManagerDocFile(filename="nested/readme.md", content="hi")]), "deterministic"

    monkeypatch.setattr(app_service, "_resolve_manager_model", fake_resolve)
    docs = client.post(f"/api/projects/{project['id']}/docs/generate")
    assert docs.status_code == 200
    assert "nested/readme.md" in docs.json()["files"]


def test_path_reservations_acquire_and_release() -> None:
    service = MissionControlService()

    class DummyDb:
        pass

    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Demo", idea="Idea", workspace_path="C:/demo", status="building", runner_mode="dry_run", manager_mode="auto")
        db.add(project)
        db.flush()
        agent = Agent(project_id=project.id, name="Worker", role="Primary implementation", kind="worker", status="idle", workspace_path="C:/demo")
        task = Task(
            project_id=project.id,
            title="Task",
            goal="Goal",
            scope="Scope",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["check"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([agent, task])
        db.flush()
        service._reserve_task_paths(db, project, agent, task)
        assert len(service.list_reservations(db, project.id)) == 1
        service._release_reservations(db, project.id, task_id=task.id, agent_id=agent.id)
        assert len(service.list_reservations(db, project.id)) == 0
    finally:
        db.close()


def test_worker_report_ingestion_routes_next_task() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Demo",
            idea="Idea",
            workspace_path=sample_workspace("unit-demo"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="working", workspace_path=project.workspace_path, locked_paths_json=["src"])
        task_one = Task(
            id=1,
            project_id=project.id,
            assigned_agent_id=None,
            title="Vertical slice",
            goal="Build",
            scope="Scope",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["run"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        task_two = Task(
            project_id=project.id,
            title="Validation",
            goal="Validate",
            scope="Scope",
            agent_role="Primary implementation",
            milestone="Milestone 2",
            allowed_paths_json=["tests"],
            forbidden_paths_json=[],
            validation_steps_json=["test"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([manager_agent, worker, task_one, task_two])
        db.flush()
        worker.current_task_id = task_one.id
        run = AgentRun(agent_id=worker.id, task_id=task_one.id, runner_type="dry_run", process_ref="dry-test", status="working")
        db.add(run)
        db.flush()
        report = WorkerReport(
            agent=worker.name,
            task_id=str(task_one.id),
            status="done",
            summary="Completed",
            files_changed=["src/app.ts"],
            tests_run=["npm run build"],
            blockers=[],
            risks=[],
            recommended_next_task="Validation",
        )
        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        assert task_one.status == "done"
        assert decision.decision_type in {"assign_next_task", "wait"}
    finally:
        db.close()


def test_start_idle_agents_keeps_dependency_blocked_unowned_task_unassigned() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    worker_id = None
    task_id = None
    run_id = None
    try:
        project = Project(
            name="Dependency Wait Demo",
            idea="Do not fake assignment state.",
            workspace_path=sample_workspace("dependency-wait-demo"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        dependency = Task(
            project_id=project.id,
            title="Finish dependency",
            goal="Complete the prerequisite task.",
            scope="Narrow dependency work.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src/dependency.ts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Dependency done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        blocked = Task(
            project_id=project.id,
            title="Blocked follow-up",
            goal="Wait until dependency finishes.",
            scope="Should not claim ownership yet.",
            agent_role="Primary implementation",
            milestone="Milestone 2",
            allowed_paths_json=["src/follow-up.ts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Follow-up ready"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([worker, dependency, blocked])
        db.flush()
        blocked.dependencies_json = [dependency.id]
        db.flush()

        asyncio.run(service.start_idle_agents(db, project))

        assert blocked.status == "backlog"
        assert blocked.assigned_agent_id is None
        assert blocked.waiting_reason == "Waiting for task dependencies to finish."
    finally:
        db.close()


def test_start_idle_agents_requeues_task_assigned_to_retired_worker() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Retired Assignment Requeue",
            idea="Do not let retired workers own runnable tasks.",
            workspace_path=sample_workspace("retired-assignment-requeue"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        retired_worker = Agent(
            project_id=project.id,
            name="Scripts Subsystem Builder",
            role="Scripts",
            kind="worker",
            status="retired",
            workspace_path=project.workspace_path,
            current_task_id=None,
        )
        task = Task(
            project_id=project.id,
            title="Scripts Defect Batch",
            goal="Find and fix script defects.",
            scope="Scripts only.",
            agent_role="Scripts Subsystem Builder",
            milestone="Milestone 1",
            allowed_paths_json=["scripts"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest"],
            success_criteria_json=["Scripts defects are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="assigned",
            priority=20,
        )
        db.add_all([retired_worker, task])
        db.flush()
        task.assigned_agent_id = retired_worker.id
        db.commit()

        started = asyncio.run(service.start_idle_agents(db, project))

        db.refresh(task)
        assert started == 0
        assert task.status == "backlog"
        assert task.assigned_agent_id is None
        assert "retired, missing, or busy worker" in (task.waiting_reason or "")
    finally:
        db.close()


def test_start_idle_agents_requeues_agentless_assigned_task_and_launches_waiting_worker(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Agentless Assigned Requeue",
            idea="Do not strand assigned tasks that have no owning worker.",
            workspace_path=sample_workspace("agentless-assigned-requeue"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Mission Control Core Subsystem Builder",
            role="Scheduler specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Enforce Live Worker Policy And Resume Eligible Runs",
            goal="Repair scheduler policy issues.",
            scope="Mission Control scheduler.",
            agent_role="Scheduler specialist",
            milestone="Milestone 1",
            allowed_paths_json=["mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest"],
            success_criteria_json=["Agentless assigned tasks are runnable."],
            estimated_complexity="small",
            dependencies_json=[],
            status="assigned",
            assigned_agent_id=None,
            priority=10,
        )
        db.add_all([worker, task])
        db.commit()

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            selected_task.waiting_reason = None
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        db.refresh(task)
        db.refresh(worker)
        assert started_count == 1
        assert started == [(worker.id, task.id)]
        assert task.status == "working"
        assert task.assigned_agent_id == worker.id
        assert worker.status == "working"
        assert worker.current_task_id == task.id
    finally:
        db.close()


def test_start_idle_agents_requeues_task_assigned_to_busy_worker() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Busy Assignment Requeue",
            idea="Do not let an already-running worker hold another startable task.",
            workspace_path=sample_workspace("busy-assignment-requeue"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        busy_worker = Agent(
            project_id=project.id,
            name="Apps Mcp Server Src Subsystem Builder",
            role="MCP specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        active_task = Task(
            project_id=project.id,
            title="Apps Mcp Server Tests Defect Batch",
            goal="Current live work.",
            scope="MCP tests.",
            agent_role="MCP specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/mcp-server/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest"],
            success_criteria_json=["MCP tests are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        stale_task = Task(
            project_id=project.id,
            title="Scripts Defect Batch",
            goal="This should not be assigned to the busy worker.",
            scope="Scripts only.",
            agent_role="Scripts specialist",
            milestone="Milestone 1",
            allowed_paths_json=["scripts"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest"],
            success_criteria_json=["Scripts defects are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([busy_worker, active_task, stale_task])
        db.flush()
        busy_worker.current_task_id = active_task.id
        active_task.assigned_agent_id = busy_worker.id
        stale_task.assigned_agent_id = busy_worker.id
        db.add(AgentRun(agent_id=busy_worker.id, task_id=active_task.id, runner_type="cli", process_ref="active-run", status="working"))
        db.commit()

        started = asyncio.run(service.start_idle_agents(db, project))

        db.refresh(stale_task)
        assert started == 0
        assert stale_task.status == "backlog"
        assert stale_task.assigned_agent_id is None
        assert "retired, missing, or busy worker" in (stale_task.waiting_reason or "")
    finally:
        db.close()


def test_feature_worker_can_take_unmatched_defect_batch(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Defect Fallback Assignment",
            idea="Keep defect campaign workers saturated on independent lanes.",
            workspace_path=sample_workspace("defect-fallback-assignment"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Apps Desktop Tests Subsystem Builder",
            role="Feature specialist",
            archetype="feature",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Scripts Defect Batch",
            goal="Fix independent scripts defects.",
            scope="Scripts only.",
            agent_role="Scripts Subsystem Builder",
            milestone="Milestone 1",
            allowed_paths_json=["scripts"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest"],
            success_criteria_json=["Scripts defects are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.commit()

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.flush()
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        db.refresh(task)
        assert started_count == 1
        assert started == [(worker.id, task.id)]
        assert task.status == "working"
        assert task.assigned_agent_id == worker.id
    finally:
        db.close()


def test_validator_worker_can_backfill_unmatched_defect_batch(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Validator Defect Backfill",
            idea="Keep benchmark workers saturated when only validation capacity is idle.",
            workspace_path=sample_workspace("validator-defect-backfill"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Defect Ledger Validator",
            role="Validation specialist",
            archetype="test",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Github Workflows Defect Batch",
            goal="Fix independent workflow defects.",
            scope="GitHub workflow files only.",
            agent_role="Github Workflows Subsystem Builder",
            milestone="Milestone 1",
            allowed_paths_json=[".github/workflows"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest"],
            success_criteria_json=["Workflow defects are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.commit()

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.flush()
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        db.refresh(task)
        assert started_count == 1
        assert started == [(worker.id, task.id)]
        assert task.status == "working"
        assert task.assigned_agent_id == worker.id
    finally:
        db.close()


def test_start_idle_agents_requeues_stale_blocked_task_assignment() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Stale Blocked Assignment",
            idea="Do not strand blocked tasks with stale ownership.",
            workspace_path=sample_workspace("stale-blocked-assignment"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Apps Desktop Tests Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        active_task = Task(
            project_id=project.id,
            title="Scripts Defect Batch",
            goal="Current work owned by the worker.",
            scope="Scripts only.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["scripts"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest"],
            success_criteria_json=["Scripts defects are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        stale_blocked = Task(
            project_id=project.id,
            title="Apps Dashboard Public Defect Batch",
            goal="This task should not stay stranded.",
            scope="Dashboard public assets.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/dashboard/public"],
            forbidden_paths_json=[],
            validation_steps_json=["npm run build"],
            success_criteria_json=["Dashboard public defects are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=15,
        )
        reset_stale_blocked = Task(
            project_id=project.id,
            title="Apps Desktop Tests Defect Batch",
            goal="This reset-cleared review task should not stay blocked.",
            scope="Desktop tests.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/desktop/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest"],
            success_criteria_json=["Desktop test defects are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            waiting_reason="Fresh benchmark reset requested; stale review gate cleared for rerun.",
            priority=16,
        )
        persisted_marker_blocked = Task(
            project_id=project.id,
            title="Github Workflows Defect Batch",
            goal="This already-marked stale task should not poison status.",
            scope="GitHub workflow fixes.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=[".github/workflows"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest"],
            success_criteria_json=["Workflow defects are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            waiting_reason=STALE_BLOCKED_REQUEUE_REASON,
            priority=17,
        )
        db.add_all([worker, active_task, stale_blocked, reset_stale_blocked, persisted_marker_blocked])
        db.flush()
        worker.current_task_id = active_task.id
        active_task.assigned_agent_id = worker.id
        stale_blocked.assigned_agent_id = worker.id
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=active_task.id,
                runner_type="cli",
                process_ref="active-worker-run",
                status="working",
            )
        )
        db.commit()

        started = asyncio.run(service.start_idle_agents(db, project))

        db.refresh(stale_blocked)
        assert started == 0
        assert stale_blocked.status == "backlog"
        assert stale_blocked.assigned_agent_id is None
        assert "no recorded blocker" in (stale_blocked.waiting_reason or "")
        db.refresh(reset_stale_blocked)
        assert reset_stale_blocked.status == "backlog"
        assert reset_stale_blocked.assigned_agent_id is None
        assert "no recorded blocker" in (reset_stale_blocked.waiting_reason or "")
        db.refresh(persisted_marker_blocked)
        assert persisted_marker_blocked.status == "backlog"
        assert persisted_marker_blocked.assigned_agent_id is None
        assert persisted_marker_blocked.waiting_reason == STALE_BLOCKED_REQUEUE_REASON
    finally:
        db.close()


def test_start_idle_agents_releases_orphaned_agent_path_locks(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Orphaned Agent Path Locks",
            idea="Do not let a waiting worker with no task block runnable work.",
            workspace_path=sample_workspace("orphaned-agent-path-locks"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        ghost_owner = Agent(
            project_id=project.id,
            name="Apps Mcp Server Tests Subsystem Builder",
            role="Ledger validator",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
            current_task_id=None,
            current_action=None,
            session_ref="stale-session",
            active_usage_json={"input_tokens": 321},
            active_model="gpt-5.4-mini",
            active_runner_type="codex_cli",
            locked_paths_json=["tests", "docs", "mission-control"],
        )
        task = Task(
            project_id=project.id,
            title="Produce a real cross-batch ledger or report update with evidence",
            goal="Create the benchmark ledger once overlapping paths are free.",
            scope="tests, docs, and mission-control.",
            agent_role="Ledger validator",
            milestone="Milestone 1",
            allowed_paths_json=["tests", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["The ledger task starts instead of staying path-blocked."],
            estimated_complexity="small",
            dependencies_json=[],
            status="waiting_on_paths",
            waiting_reason="Apps Mcp Server Tests Subsystem Builder owns tests, docs, mission-control",
            priority=10,
        )
        db.add_all([ghost_owner, task])
        db.flush()
        for path in ["tests", "docs", "mission-control"]:
            db.add(PathReservation(project_id=project.id, task_id=task.id, agent_id=ghost_owner.id, path=path))
        db.commit()

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            selected_task.waiting_reason = None
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        db.refresh(ghost_owner)
        db.refresh(task)
        active_reservations = db.scalars(
            select(PathReservation).where(PathReservation.project_id == project.id, PathReservation.released_at.is_(None))
        ).all()
        assert started_count == 1
        assert started == [(ghost_owner.id, task.id)]
        assert active_reservations == []
        assert ghost_owner.session_ref is None
        assert ghost_owner.active_usage_json is None
        assert ghost_owner.active_model is None
        assert ghost_owner.active_runner_type is None
        assert task.status == "working"
        assert task.assigned_agent_id == ghost_owner.id
        assert task.waiting_reason is None
    finally:
        db.close()


def test_start_idle_agents_requeues_orphaned_working_task_without_live_run(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Orphaned Working Task",
            idea="Do not let ghost working tasks freeze the swarm.",
            workspace_path=sample_workspace("orphaned-working-task"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=None,
            title="Resume The Lost Worker Slice",
            goal="Recover a task whose live run vanished.",
            scope="Requeue the task safely and restart it.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src/ghost.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Task restarts instead of stalling in working forever."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()
        worker.current_task_id = task.id
        db.flush()

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            selected_task.waiting_reason = None
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 1
        assert started == [(worker.id, task.id)]
        assert task.status == "working"
        assert task.assigned_agent_id == worker.id
        assert task.waiting_reason is None
        assert worker.status == "working"
        assert worker.current_task_id == task.id
    finally:
        db.close()


def test_finalize_run_retries_after_transient_sqlite_lock(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Retry Finalize Run",
            idea="Transient SQLite lock during run finalization should retry instead of killing the daemon.",
            workspace_path=sample_workspace("retry-finalize-run"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Finalize report",
            goal="Persist a completed worker report.",
            scope="One task.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src/retry.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Run finalization survives one SQLite lock."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()
        worker.current_task_id = task.id
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="dry_run",
            process_ref="dry-finalize-retry",
            status="done",
            report_json={
                "agent": worker.name,
                "task_id": str(task.id),
                "status": "done",
                "summary": "Completed after retry.",
                "files_changed": [],
                "tests_run": [],
                "blockers": [],
                "risks": [],
                "recommended_next_task": "",
            },
        )
        db.add(run)
        db.commit()

        calls = {"count": 0}

        async def fake_ingest_worker_report(db, run, report, *, envelope=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OperationalError("UPDATE agents", {}, Exception("database is locked"))
            run.finished_at = run.finished_at or project.updated_at or project.created_at
            return ManagerWorkerDecision(decision_type="wait", summary_markdown="Retried successfully.")

        monkeypatch.setattr(service, "ingest_worker_report", fake_ingest_worker_report)

        asyncio.run(service._finalize_run_with_retry(run.id, status="done"))

        assert calls["count"] == 2
    finally:
        db.close()


def test_ingest_worker_report_defers_follow_up_after_sqlite_lock(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Deferred Follow Up",
            idea="Persist worker completion even if follow-up routing hits a transient SQLite lock.",
            workspace_path=sample_workspace("deferred-follow-up"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(
            project_id=project.id,
            name="Manager AI",
            role="Project orchestration",
            kind="manager",
            status="idle",
            workspace_path=project.workspace_path,
        )
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Persist worker outcome",
            goal="Record a finished task safely.",
            scope="One task.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src/persist.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Worker outcome stays persisted."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        worker.current_task_id = task.id
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-follow-up-lock", status="working")
        db.add(run)
        db.commit()

        async def fake_resolve_manager_model(*args, **kwargs):
            return ManagerWorkerDecision(decision_type="wait", summary_markdown="Route later."), "deterministic"

        async def fake_apply_worker_decision(*args, **kwargs):
            raise OperationalError("UPDATE tasks", {}, Exception("database is locked"))

        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "_apply_worker_decision", fake_apply_worker_decision)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="done",
            summary="Completed before the coordination lock hit.",
            files_changed=["apps/server/src/persist.py"],
            tests_run=["python -m pytest apps/server/tests/test_manager.py -q"],
            blockers=[],
            risks=[],
            recommended_next_task="",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))

        db.expire_all()
        persisted_run = db.get(AgentRun, run.id)
        persisted_task = db.get(Task, task.id)
        persisted_agent = db.get(Agent, worker.id)

        assert decision.decision_type == "wait"
        assert "deferred follow-up routing" in decision.summary_markdown.lower()
        assert persisted_run is not None
        assert persisted_run.finished_at is not None
        assert persisted_task is not None
        assert persisted_task.status == "done"
        assert persisted_agent is not None
        assert persisted_agent.status == "waiting"
    finally:
        db.close()


def test_start_idle_agents_skips_agent_claimed_by_parallel_turn(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Parallel Launch Race",
            idea="Do not fail the whole turn when another background loop already claimed a worker.",
            workspace_path=sample_workspace("parallel-launch-race"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        first_worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        second_worker = Agent(
            project_id=project.id,
            name="UI Workflow Builder",
            role="Planner specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Resume repair batch",
            goal="Restart a runnable repair slice.",
            scope="One safe work item.",
            agent_role="Planner specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src/retry.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Task restarts safely."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([first_worker, second_worker, task])
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            if agent.id == first_worker.id:
                raise ValueError("Agent already has an active unfinished run.")
            started.append(agent.id)
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 1
        assert started == [second_worker.id]
        assert task.status == "working"
        assert task.assigned_agent_id == second_worker.id
    finally:
        db.close()


def test_start_idle_agents_skips_task_that_changed_state_mid_launch(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Parallel Task State Race",
            idea="Do not fail the whole turn when another background loop already changed a queued task state.",
            workspace_path=sample_workspace("parallel-task-state-race"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        first_worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        second_worker = Agent(
            project_id=project.id,
            name="UI Workflow Builder",
            role="Planner specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        stale_task = Task(
            project_id=project.id,
            title="Stale launch candidate",
            goal="This candidate is claimed by another turn before launch finishes.",
            scope="One stale work item.",
            agent_role="Planner specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src/stale.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Stale launch candidates do not fail the whole turn."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        healthy_task = Task(
            project_id=project.id,
            title="Healthy launch candidate",
            goal="Another worker should still launch successfully.",
            scope="One healthy work item.",
            agent_role="Planner specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src/healthy.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["The remaining safe candidate still starts."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=11,
        )
        db.add_all([first_worker, second_worker, stale_task, healthy_task])
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            if selected_task.id == stale_task.id:
                selected_task.status = "blocked"
                raise ValueError("Task is not in a startable state.")
            started.append(agent.id)
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.add(
                AgentRun(
                    agent_id=agent.id,
                    task_id=selected_task.id,
                    runner_type="dry_run",
                    process_ref=f"run-{agent.id}",
                    status="working",
                )
            )
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 1
        assert started == [second_worker.id]
        assert stale_task.status in {"backlog", "blocked"}
        assert stale_task.assigned_agent_id is None
        assert first_worker.status == "waiting"
        assert first_worker.current_task_id is None
        assert healthy_task.status == "working"
        assert healthy_task.assigned_agent_id == second_worker.id
    finally:
        db.close()


def test_start_idle_agents_pauses_new_launches_during_provider_quota_backoff(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Provider Quota Backoff",
            idea="Do not keep launching workers into the same provider quota wall.",
            workspace_path=sample_workspace("provider-quota-backoff"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        first_worker = Agent(
            project_id=project.id,
            name="Apps Dashboard Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        second_worker = Agent(
            project_id=project.id,
            name="Apps Server Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        dashboard_task = Task(
            project_id=project.id,
            title="Apps Dashboard Defect Batch",
            goal="Keep the dashboard lane moving.",
            scope="Dashboard-only lane.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/dashboard"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        server_task = Task(
            project_id=project.id,
            title="Apps Server Defect Batch",
            goal="Keep the server lane moving.",
            scope="Server-only lane.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([first_worker, second_worker, dashboard_task, server_task])
        db.flush()
        for worker, task_id in ((first_worker, dashboard_task.id), (second_worker, server_task.id)):
            db.add(
                AgentRun(
                    agent_id=worker.id,
                    task_id=task_id,
                    runner_type="codex_cli",
                    process_ref=f"quota-{worker.id}",
                    status="blocked",
                    finished_at=project.created_at,
                    report_json={
                        "agent": worker.name,
                        "task_id": str(task_id),
                        "status": "blocked",
                        "summary": "You've hit your usage limit. Visit settings/usage to purchase more credits or try again later.",
                        "files_changed": [],
                        "tests_run": [],
                        "blockers": ["You've hit your usage limit. Visit settings/usage to purchase more credits or try again later."],
                        "risks": [],
                        "recommended_next_task": "Retry after the provider/runtime blocker is resolved.",
                    },
                )
            )
        db.commit()

        async def fail_if_started(*args, **kwargs):
            raise AssertionError("start_agent_task should not be called while provider backoff is active")

        monkeypatch.setattr(service, "start_agent_task", fail_if_started)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 0
        assert first_worker.status == "waiting"
        assert "Provider quota backoff is active until" in (first_worker.current_action or "")
        assert second_worker.status == "waiting"
        assert "Provider quota backoff is active until" in (second_worker.current_action or "")
    finally:
        db.close()


def test_start_idle_agents_pauses_after_single_provider_quota_signal(monkeypatch) -> None:
    service = MissionControlService()
    from db import init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Single Provider Quota Signal",
            idea="One explicit usage-limit signal should be enough to stop new launches.",
            workspace_path=sample_workspace("single-provider-quota-signal"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Apps Server Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Apps Server Defect Batch",
            goal="Keep the server lane moving.",
            scope="Server-only lane.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([worker, task])
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.quota_backoff_cooldown_minutes = 90
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=task.id,
                runner_type="codex_cli",
                process_ref="quota-single",
                status="blocked",
                finished_at=project.created_at,
                report_json={
                    "agent": worker.name,
                    "task_id": str(task.id),
                    "status": "blocked",
                    "summary": "You've hit your usage limit. Try again later.",
                    "files_changed": [],
                    "tests_run": [],
                    "blockers": ["You've hit your usage limit. Try again later."],
                    "risks": [],
                    "recommended_next_task": "Retry later.",
                },
            )
        )
        db.commit()

        async def fail_if_started(*args, **kwargs):
            raise AssertionError("start_agent_task should not run after a single quota signal")

        monkeypatch.setattr(service, "start_agent_task", fail_if_started)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 0
        assert worker.status == "waiting"
        assert "Provider quota backoff is active until" in (worker.current_action or "")
    finally:
        db.close()


def test_start_idle_agents_pauses_when_token_budget_is_exhausted(monkeypatch) -> None:
    service = MissionControlService()
    from db import init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Token Budget Trip",
            idea="Do not keep launching workers after the budget is blown.",
            workspace_path=sample_workspace("token-budget-trip"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.hard_total_token_budget = 50
        worker = Agent(
            project_id=project.id,
            name="Apps Server Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Apps Server Defect Batch",
            goal="Keep the server lane moving.",
            scope="Server-only lane.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([worker, task])
        db.flush()
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=task.id,
                runner_type="codex_cli",
                process_ref="token-budget-run",
                status="done",
                finished_at=project.created_at,
                usage_json={"input_tokens": 40, "output_tokens": 20, "total_tokens": 60, "peak_context_tokens": 25},
            )
        )
        db.commit()

        async def fail_if_started(*args, **kwargs):
            raise AssertionError("start_agent_task should not run after the token budget trips")

        monkeypatch.setattr(service, "start_agent_task", fail_if_started)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 0
        assert worker.status == "waiting"
        assert "Token budget exhausted" in (worker.current_action or "")
        budget = service._sync_swarm_budget(db, project)
        assert budget.launch_guard_status == "blocked_token_budget"
        assert budget.observed_total_tokens == 60
    finally:
        db.close()


def test_start_idle_agents_counts_active_worker_usage_against_launch_guard(monkeypatch) -> None:
    service = MissionControlService()
    from db import init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Active Worker Usage Budget",
            idea="Do not spawn another worker when a live run already burned through the token budget.",
            workspace_path=sample_workspace("active-worker-usage-budget"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.hard_total_token_budget = 100
        first_worker = Agent(
            project_id=project.id,
            name="Apps Server Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            active_usage_json={
                "input_tokens": 90,
                "output_tokens": 20,
                "total_tokens": 110,
                "peak_context_tokens": 64,
            },
        )
        second_worker = Agent(
            project_id=project.id,
            name="Apps Dashboard Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        active_task = Task(
            project_id=project.id,
            title="Apps Server Defect Batch",
            goal="Keep the server lane moving.",
            scope="Server-only lane.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        queued_task = Task(
            project_id=project.id,
            title="Apps Dashboard Defect Batch",
            goal="Keep the dashboard lane moving.",
            scope="Dashboard-only lane.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/dashboard"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([first_worker, second_worker, active_task, queued_task])
        db.flush()
        first_worker.current_task_id = active_task.id
        active_task.assigned_agent_id = first_worker.id
        db.add(
            AgentRun(
                agent_id=first_worker.id,
                task_id=active_task.id,
                runner_type="codex_cli",
                process_ref="active-budget-run",
                status="running",
            )
        )
        db.commit()

        async def fail_if_started(*args, **kwargs):
            raise AssertionError("start_agent_task should not run while live worker usage already exhausted the token budget")

        monkeypatch.setattr(service, "start_agent_task", fail_if_started)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 0
        assert second_worker.status == "waiting"
        assert "Token budget exhausted" in (second_worker.current_action or "")
        budget = service._sync_swarm_budget(db, project)
        assert budget.launch_guard_status == "blocked_token_budget"
        assert budget.observed_total_tokens == 110
        assert budget.observed_peak_context_tokens == 64
    finally:
        db.close()


def test_start_idle_agents_pauses_when_launch_budget_is_exhausted(monkeypatch) -> None:
    service = MissionControlService()
    from db import init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Launch Budget Trip",
            idea="Do not create thread confetti after the launch cap is reached.",
            workspace_path=sample_workspace("launch-budget-trip"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.hard_total_worker_launch_budget = 1
        worker = Agent(
            project_id=project.id,
            name="Apps Server Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Apps Server Defect Batch",
            goal="Keep the server lane moving.",
            scope="Server-only lane.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([worker, task])
        db.flush()
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=task.id,
                runner_type="codex_cli",
                process_ref="launch-budget-run",
                status="done",
                finished_at=project.created_at,
            )
        )
        db.commit()

        async def fail_if_started(*args, **kwargs):
            raise AssertionError("start_agent_task should not run after the launch budget trips")

        monkeypatch.setattr(service, "start_agent_task", fail_if_started)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 0
        assert worker.status == "waiting"
        assert "Worker launch budget exhausted" in (worker.current_action or "")
        budget = service._sync_swarm_budget(db, project)
        assert budget.launch_guard_status == "blocked_launch_budget"
        assert budget.launches_started == 1
    finally:
        db.close()


def test_derive_current_action_preview_reports_provider_quota_backoff() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Provider Backoff Status Preview",
            idea="Surface provider quota backoff as degraded status instead of pretending the swarm is simply idle.",
            workspace_path=sample_workspace("provider-backoff-status-preview"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        first_worker = Agent(
            project_id=project.id,
            name="Apps Dashboard Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        second_worker = Agent(
            project_id=project.id,
            name="Apps Server Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        db.add_all([first_worker, second_worker])
        db.flush()
        first_task = Task(
            project_id=project.id,
            title="Apps Dashboard Defect Batch",
            goal="Keep the dashboard lane moving.",
            scope="Dashboard-only lane.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/dashboard"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        second_task = Task(
            project_id=project.id,
            title="Apps Server Defect Batch",
            goal="Keep the server lane moving.",
            scope="Server-only lane.",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([first_task, second_task])
        db.flush()
        for worker, task_id in ((first_worker, first_task.id), (second_worker, second_task.id)):
            db.add(
                AgentRun(
                    agent_id=worker.id,
                    task_id=task_id,
                    runner_type="codex_cli",
                    process_ref=f"quota-preview-{worker.id}",
                    status="blocked",
                    finished_at=project.created_at,
                    report_json={
                        "agent": worker.name,
                        "task_id": str(task_id),
                        "status": "blocked",
                        "summary": "You've hit your usage limit. Visit settings/usage to purchase more credits or try again later.",
                        "files_changed": [],
                        "tests_run": [],
                        "blockers": ["You've hit your usage limit. Visit settings/usage to purchase more credits or try again later."],
                        "risks": [],
                        "recommended_next_task": "Retry after the provider/runtime blocker is resolved.",
                    },
                )
            )
        db.commit()

        preview = service._derive_current_action_preview(db, project, [])

        assert preview["type"] == "degraded"
        assert "provider usage limit" in preview["message"].lower()
        assert preview["expires_at"] is not None
    finally:
        db.close()


def test_derive_current_action_ignores_non_actionable_lane_blockers_while_workers_run() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Active Swarm Lane Blockers",
            idea="Do not label an active swarm blocked because one lane is waiting on path ownership.",
            workspace_path=sample_workspace("active-swarm-lane-blockers"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Apps Dashboard Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            active_model="gpt-5.4-mini",
            current_action="Working on an independent defect batch.",
        )
        active_task = Task(
            project_id=project.id,
            title="Apps Dashboard Src Defect Batch",
            goal="Keep active work moving.",
            scope="apps/dashboard/src",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/dashboard/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["One distinct defect fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=20,
        )
        stale_marker_blocker = Task(
            project_id=project.id,
            title="Github Workflows Defect Batch",
            goal="A stale persisted requeue marker should not block an active swarm.",
            scope=".github/workflows",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=[".github/workflows"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Workflow defects are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            waiting_reason=STALE_BLOCKED_REQUEUE_REASON,
            priority=4,
        )
        stale_blocker = Task(
            project_id=project.id,
            title="Apps Desktop Tests Defect Batch",
            goal="Old blocked lane has a follow-up.",
            scope="apps/desktop/tests",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/desktop/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Follow-up handles this lane."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=5,
        )
        follow_up = Task(
            project_id=project.id,
            title="Unblock: Apps Desktop Tests Defect Batch",
            goal="Wait for path ownership to clear.",
            scope="apps/desktop/src",
            agent_role="Feature specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/desktop/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Path conflict clears."],
            estimated_complexity="small",
            dependencies_json=[],
            status="waiting_on_paths",
            waiting_reason="Apps Dashboard Subsystem Builder owns apps/desktop/src",
            priority=6,
        )
        db.add_all([worker, active_task, stale_marker_blocker, stale_blocker, follow_up])
        db.flush()
        worker.current_task_id = active_task.id
        active_task.assigned_agent_id = worker.id
        stale_blocker.waiting_reason = f"Blocked task handed off to follow-up task #{follow_up.id}."
        db.add(AgentRun(agent_id=worker.id, task_id=active_task.id, runner_type="codex_cli", process_ref="active-lane", status="working"))
        db.commit()

        action = service._derive_current_action(db, project, [], mutate=False)
        preview = service._derive_current_action_preview(db, project, [])

        assert action["type"] == "no_action"
        assert "1 agents are working" in action["title"]
        assert preview["type"] == "no_action"
        assert "1 agents are working" in preview["title"]
    finally:
        db.close()


def test_start_idle_agents_launches_multiple_candidates_concurrently(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Parallel Worker Launches",
            idea="Launch independent worker lanes in parallel instead of serially waiting on each startup.",
            workspace_path=sample_workspace("parallel-worker-launches"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        first_worker = Agent(
            project_id=project.id,
            name="Apps Dashboard Subsystem Builder",
            role="Feature specialist",
            archetype="feature",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        second_worker = Agent(
            project_id=project.id,
            name="Apps Desktop Subsystem Builder",
            role="Feature specialist",
            archetype="feature",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        dashboard_task = Task(
            project_id=project.id,
            title="Apps Dashboard Defect Batch",
            goal="Keep the dashboard defect lane hot.",
            scope="Dashboard-only fixes.",
            agent_role="Apps Dashboard Subsystem Builder",
            milestone="Milestone 1",
            allowed_paths_json=["apps/dashboard"],
            forbidden_paths_json=["apps/desktop"],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Launch immediately."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        desktop_task = Task(
            project_id=project.id,
            title="Apps Desktop Defect Batch",
            goal="Keep the desktop defect lane hot.",
            scope="Desktop-only fixes.",
            agent_role="Apps Desktop Subsystem Builder",
            milestone="Milestone 1",
            allowed_paths_json=["apps/desktop"],
            forbidden_paths_json=["apps/dashboard"],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Launch immediately."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([first_worker, second_worker, dashboard_task, desktop_task])
        db.flush()

        started: list[tuple[int, int]] = []
        both_started = asyncio.Event()

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            if len(started) >= 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.2)
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            return object()

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(asyncio.wait_for(service.start_idle_agents(db, project), timeout=0.5))

        assert started_count == 2
        assert sorted(started) == sorted(
            [
                (first_worker.id, dashboard_task.id),
                (second_worker.id, desktop_task.id),
            ]
        )
    finally:
        db.close()


def test_start_idle_agents_spawns_newly_activated_deferred_specs(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Deferred Swarm Activation",
            idea="Spawn newly unblocked deferred workers during the same live turn.",
            workspace_path=sample_workspace("deferred-swarm-activation"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        prefs = service._ensure_swarm_preferences(db, project)
        prefs.max_agents = 4

        plan = SwarmPlan(
            project_id=project.id,
            mode="balanced",
            goal="Keep the swarm scaling as earlier batches complete.",
            recommended_agent_count=2,
            max_agent_count=4,
            coordination_risk="medium",
            path_conflict_risk="medium",
            expected_bottlenecks_json=[],
            validation_strategy_json=["Run focused validation."],
            strategy_summary="Promote deferred specialists as upstream work lands.",
            approved_by_user=True,
            status="active",
        )
        db.add(plan)
        db.flush()

        initial_spec = SwarmAgentSpec(
            swarm_plan_id=plan.id,
            project_id=project.id,
            archetype="planner",
            name="Execution Planner",
            mission="Own the first batch.",
            model_policy="Prefer the default worker model.",
            toolset_json=["task_planning"],
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            spawn_phase="build_start",
            retire_when="done",
            priority=10,
            iteration_budget=1,
            status="spawned",
        )
        deferred_spec = SwarmAgentSpec(
            swarm_plan_id=plan.id,
            project_id=project.id,
            archetype="backend",
            name="Service Flow Builder",
            mission="Pick up the next backend slice as soon as the planner clears the first wave.",
            model_policy="Prefer the default worker model.",
            toolset_json=["api_editing"],
            allowed_paths_json=["apps/server/tests"],
            forbidden_paths_json=["apps/server/src"],
            spawn_phase="after_architecture",
            retire_when="done",
            priority=20,
            iteration_budget=1,
            status="deferred",
        )
        db.add_all([initial_spec, deferred_spec])
        db.flush()

        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            archetype="planner",
            kind="worker",
            status="blocked",
            workspace_path=project.workspace_path,
            swarm_plan_id=plan.id,
        )
        completed_task = Task(
            project_id=project.id,
            title="Completed architecture slice",
            goal="Trigger deferred activation.",
            scope="Already finished.",
            agent_role="execution_planner",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=[],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=5,
        )
        next_task = Task(
            project_id=project.id,
            title="Resume backend repair wave",
            goal="Give the deferred backend specialist real work immediately after activation.",
            scope="Backend-only follow-up.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["apps/server/tests"],
            forbidden_paths_json=["apps/server/src"],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["The newly spawned worker starts in the same turn."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, completed_task, next_task])
        db.flush()

        started: list[tuple[str, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.name, selected_task.id))
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        spawned_worker = db.scalar(
            select(Agent).where(Agent.project_id == project.id, Agent.name == "Service Flow Builder")
        )
        db.refresh(deferred_spec)

        assert started_count == 1
        assert started == [("Service Flow Builder", next_task.id)]
        assert spawned_worker is not None
        assert deferred_spec.status == "spawned"
        assert next_task.status == "working"
        assert next_task.assigned_agent_id == spawned_worker.id
    finally:
        db.close()


def test_get_project_action_uses_preview_degraded_notices_without_live_probe(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Preview Action Status",
            idea="Status polls must not trigger live runner probes.",
            workspace_path=sample_workspace("preview-action-status"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()

        async def fail_live_probe(project, settings):
            raise AssertionError("get_project_action should not probe live runner availability")

        monkeypatch.setattr(service, "_workspace_degraded_notices", fail_live_probe)

        action = asyncio.run(service.get_project_action(db, project, mutate=False))

        assert action["type"] == "no_action"
    finally:
        db.close()


def test_start_agent_task_uses_real_codex_cli_runner_for_live_worker(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "codex_cli"

        async def start_task(self, context):
            return RunnerHandle(
                id="cli-run-1",
                runner_type="codex_cli",
                logs_path="C:/logs/cli-run-1.log",
                stdout_path="C:/logs/cli-run-1.stdout.log",
                stderr_path="C:/logs/cli-run-1.stderr.log",
                event_log_path="C:/logs/cli-run-1.events.jsonl",
            )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Live Codex Worker",
            idea="Use the real Codex CLI worker path.",
            workspace_path=sample_workspace("live-codex-worker"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"

        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Implement live task",
            goal="Use the live Codex runner.",
            scope="Scoped worker task.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Task started with Codex CLI"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        async def fake_monitor_run(run_id: int) -> None:
            return None

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))
        monkeypatch.setattr(service, "_monitor_run", fake_monitor_run)

        run = asyncio.run(service.start_agent_task(db, project, worker, task))

        assert run.runner_type == "codex_cli"
        assert worker.active_runner_type == "codex_cli"
        assert task.status == "working"
        assert task.assigned_agent_id == worker.id
        assert run.process_ref == "cli-run-1"
    finally:
        db.close()


def test_start_agent_task_releases_transaction_before_runner_start(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "codex_cli"

        async def start_task(self, context):
            assert db.in_transaction() is False
            return RunnerHandle(
                id="cli-run-release-1",
                runner_type="codex_cli",
                logs_path="C:/logs/cli-run-release-1.log",
                stdout_path="C:/logs/cli-run-release-1.stdout.log",
                stderr_path="C:/logs/cli-run-release-1.stderr.log",
                event_log_path="C:/logs/cli-run-release-1.events.jsonl",
            )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Worker Transaction Release",
            idea="Release the DB transaction before runner startup.",
            workspace_path=sample_workspace("worker-transaction-release"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"

        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Release transaction before start",
            goal="Start the runner without pinning SQLite.",
            scope="Worker task startup.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Runner starts after the DB transaction is released."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        async def fake_monitor_run(run_id: int) -> None:
            return None

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))
        monkeypatch.setattr(service, "_monitor_run", fake_monitor_run)

        run = asyncio.run(service.start_agent_task(db, project, worker, task))

        assert run.runner_type == "codex_cli"
        assert task.status == "working"
    finally:
        db.close()


def test_start_agent_task_moves_render_and_snapshot_off_thread(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "codex_cli"

        async def start_task(self, context):
            return RunnerHandle(
                id="cli-run-threaded-1",
                runner_type="codex_cli",
                logs_path="C:/logs/cli-run-threaded-1.log",
                stdout_path="C:/logs/cli-run-threaded-1.stdout.log",
                stderr_path="C:/logs/cli-run-threaded-1.stderr.log",
                event_log_path="C:/logs/cli-run-threaded-1.events.jsonl",
            )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Worker Off Thread Startup",
            idea="Build prompts and snapshots away from the event loop.",
            workspace_path=sample_workspace("worker-off-thread-startup"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"

        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Off-thread worker startup",
            goal="Keep blocking startup work off the async loop.",
            scope="Worker task startup.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Prompt rendering and file snapshotting stay off-thread."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        async def fake_monitor_run(run_id: int) -> None:
            return None

        calls: list[str] = []

        async def fake_to_thread(func, *args, **kwargs):
            calls.append(func.__name__)
            if func.__name__ == "render_markdown":
                return "# Context pack"
            if func.__name__ == "_task_workspace_snapshot":
                assert db.scalar(select(AgentRun.id).where(AgentRun.agent_id == worker.id).limit(1)) is None
                assert worker.current_task_id is None
                assert task.status == "backlog"
                return {"apps/server/src/main.py": "abc123"}
            raise AssertionError(f"Unexpected to_thread function: {func.__name__}")

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))
        monkeypatch.setattr(service, "_monitor_run", fake_monitor_run)
        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

        run = asyncio.run(service.start_agent_task(db, project, worker, task))

        assert run.runner_type == "codex_cli"
        assert calls == ["render_markdown", "_task_workspace_snapshot"]
        assert service.run_input_snapshots[run.id] == {"apps/server/src/main.py": "abc123"}
    finally:
        db.close()


def test_start_agent_task_builds_ephemeral_context_pack(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "codex_cli"

        async def start_task(self, context):
            return RunnerHandle(
                id="cli-run-ephemeral-pack-1",
                runner_type="codex_cli",
                logs_path="C:/logs/cli-run-ephemeral-pack-1.log",
                stdout_path="C:/logs/cli-run-ephemeral-pack-1.stdout.log",
                stderr_path="C:/logs/cli-run-ephemeral-pack-1.stderr.log",
                event_log_path="C:/logs/cli-run-ephemeral-pack-1.events.jsonl",
            )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Worker Ephemeral Context Pack",
            idea="Launch workers without writing context-pack rows during startup.",
            workspace_path=sample_workspace("worker-ephemeral-context-pack"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"

        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Ephemeral context pack startup",
            goal="Skip persisted context-pack writes during worker launch.",
            scope="Worker task startup.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Worker startup uses a non-persisted context pack."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        captured: dict[str, object] = {}

        def fake_build_context_pack(db_session, project_record, *, agent_id=None, task_id=None, persist=True, **kwargs):
            captured["agent_id"] = agent_id
            captured["task_id"] = task_id
            captured["persist"] = persist
            return {"sections": []}

        async def fake_monitor_run(run_id: int) -> None:
            return None

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))
        monkeypatch.setattr("manager.context_pack_service.build_context_pack", fake_build_context_pack)
        monkeypatch.setattr("manager.context_pack_service.render_markdown", lambda payload: "")
        monkeypatch.setattr(service, "_monitor_run", fake_monitor_run)

        asyncio.run(service.start_agent_task(db, project, worker, task))

        assert captured == {"agent_id": worker.id, "task_id": task.id, "persist": False}
    finally:
        db.close()


def test_start_agent_task_uses_compact_context_for_benchmark_swarm(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    captured: dict[str, object] = {}

    class FakeRunner:
        runner_type = "codex_cli"

        async def start_task(self, context):
            captured["context_pack_markdown"] = context.context_pack_markdown
            captured["plan_markdown"] = context.plan_markdown
            return RunnerHandle(
                id="cli-run-benchmark-compact-1",
                runner_type="codex_cli",
                logs_path="C:/logs/cli-run-benchmark-compact-1.log",
                stdout_path="C:/logs/cli-run-benchmark-compact-1.stdout.log",
                stderr_path="C:/logs/cli-run-benchmark-compact-1.stderr.log",
                event_log_path="C:/logs/cli-run-benchmark-compact-1.events.jsonl",
            )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Compact Context",
            idea="Benchmark workers should launch with compact context instead of the heavy context-pack path.",
            workspace_path=sample_workspace("benchmark-compact-context"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"

        worker = Agent(
            project_id=project.id,
            name="Apps Server Subsystem Builder",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Apps Server Defect Batch",
            goal="Keep the benchmark lane hot.",
            scope="Server-only defect lane.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Worker starts with compact benchmark context."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        async def fake_monitor_run(run_id: int) -> None:
            return None

        def fail_build_context_pack(*args, **kwargs):
            raise AssertionError("build_context_pack should be skipped for benchmark swarm workers")

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))
        monkeypatch.setattr(service, "_benchmark_defect_campaign_active", lambda db_session, project_record: True)
        monkeypatch.setattr("manager.context_pack_service.build_context_pack", fail_build_context_pack)
        monkeypatch.setattr(service, "_monitor_run", fake_monitor_run)

        asyncio.run(service.start_agent_task(db, project, worker, task))

        assert isinstance(captured["context_pack_markdown"], str)
        assert "# Worker Context" in str(captured["context_pack_markdown"])
        assert captured["plan_markdown"] is None
    finally:
        db.close()


def test_start_idle_agents_matches_snake_case_role_to_existing_worker(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "codex_cli"

        async def start_task(self, context):
            return RunnerHandle(
                id="cli-run-role-match-1",
                runner_type="codex_cli",
                logs_path="C:/logs/cli-run-role-match-1.log",
                stdout_path="C:/logs/cli-run-role-match-1.stdout.log",
                stderr_path="C:/logs/cli-run-role-match-1.stderr.log",
                event_log_path="C:/logs/cli-run-role-match-1.events.jsonl",
            )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Snake Case Role Matching",
            idea="Do not strand live backlog tasks because role labels use different separators.",
            workspace_path=sample_workspace("snake-case-role-matching"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"

        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            kind="worker",
            archetype="planner",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Run Headless Intake And Build Defect Ledger",
            goal="Kick off the first live planning batch.",
            scope="Headless/backend discovery only.",
            agent_role="execution_planner",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/**", "docs/**", "mission-control/**"],
            forbidden_paths_json=["apps/dashboard/**"],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["The planner worker can accept the snake_case task role."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        async def fake_monitor_run(run_id: int) -> None:
            return None

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))
        monkeypatch.setattr(service, "_monitor_run", fake_monitor_run)

        started = asyncio.run(service.start_idle_agents(db, project))

        assert started == 1
        assert worker.current_task_id == task.id
        assert task.status == "working"
        assert task.assigned_agent_id == worker.id
    finally:
        db.close()


def test_specialized_workers_prefer_own_subsystem_lanes() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Specialized Worker Matching",
            idea="Do not let generic planner/docs workers steal the specialized subsystem lanes.",
            workspace_path=sample_workspace("specialized-worker-matching"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        planner = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            kind="worker",
            archetype="planner",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        frontend = Agent(
            project_id=project.id,
            name="UI Workflow Builder",
            role="Frontend specialist",
            kind="worker",
            archetype="frontend",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        docs = Agent(
            project_id=project.id,
            name="Handoff Writer",
            role="Docs specialist",
            kind="worker",
            archetype="docs",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        tester = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Test specialist",
            kind="worker",
            archetype="test",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        dashboard_task = Task(
            project_id=project.id,
            title="Apps Dashboard Defect Batch",
            goal="Fix the dashboard batch in the right lane.",
            scope="Frontend lane only.",
            agent_role="Apps Dashboard Subsystem Builder",
            milestone="Benchmark reset",
            allowed_paths_json=["apps/dashboard"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["The frontend worker claims the dashboard lane."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        validation_task = Task(
            project_id=project.id,
            title="Cross-batch validation and defect ledger update",
            goal="Validate the active implementation batches.",
            scope="Validation lane only.",
            agent_role="Validation Specialist",
            milestone="Benchmark reset",
            allowed_paths_json=["tests", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["The validation specialist claims the validation lane."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([planner, frontend, docs, tester, dashboard_task, validation_task])
        db.commit()

        planner_candidate = service._find_next_safe_task(db, project, planner)
        frontend_candidate = service._find_next_safe_task(db, project, frontend)
        docs_candidate = service._find_next_safe_task(db, project, docs)
        tester_candidate = service._find_next_safe_task(db, project, tester)

        assert planner_candidate is None
        assert frontend_candidate is not None and frontend_candidate.id == dashboard_task.id
        assert docs_candidate is None
        assert tester_candidate is not None and tester_candidate.id == validation_task.id
    finally:
        db.close()


def test_manager_next_step_applies_assignment_before_starting_idle_agents(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Manager Next Step Assignment",
            idea="Do not lose manager task assignments.",
            workspace_path=sample_workspace("manager-next-step-assignment"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Expand Runtime Path Inventory",
            goal="Expose runtime path details safely.",
            scope="Backend-only contract update.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Task is assigned and started."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        async def fake_greenfield_intake_decision(db, project):
            return None

        async def fake_resolve_manager_model(*args, **kwargs):
            return (
                ManagerWorkerDecision(
                    decision_type="assign_next_task",
                    summary_markdown=f"Route **{task.title}** to {worker.name}.",
                    task_id=task.id,
                    assign_to_agent_id=worker.id,
                ),
                "deterministic",
            )

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            agent.status = "working"
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_greenfield_intake_decision", fake_greenfield_intake_decision)
        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        decision = asyncio.run(service.manager_next_step(db, project))

        assert decision.decision_type == "assign_next_task"
        assert task.assigned_agent_id == worker.id
        assert task.status == "working"
        assert started == [(worker.id, task.id)]
    finally:
        db.close()


def test_manager_next_step_skips_provider_when_safe_assignment_is_already_known(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Manager Next Step Fast Path",
            idea="Do not stall obvious backlog routing on an unnecessary manager model turn.",
            workspace_path=sample_workspace("manager-next-step-fast-path"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Launch the next safe backlog slice",
            goal="Keep the swarm moving without waiting on unnecessary manager deliberation.",
            scope="Bounded backend task.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["The task is assigned immediately."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        async def fake_greenfield_intake_decision(db, project):
            return None

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("manager model should not run when a deterministic assignment is already safe")

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            agent.status = "working"
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_greenfield_intake_decision", fake_greenfield_intake_decision)
        monkeypatch.setattr(service, "_resolve_manager_model", fail_if_called)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        decision = asyncio.run(service.manager_next_step(db, project))

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == task.id
        assert decision.assign_to_agent_id == worker.id
        assert task.assigned_agent_id == worker.id
        assert task.status == "working"
        assert started == [(worker.id, task.id)]
    finally:
        db.close()


def test_manager_next_step_falls_back_when_model_omits_assignment_refs(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Manager Next Step Fallback",
            idea="Use the deterministic fallback assignment when the model omits task refs.",
            workspace_path=sample_workspace("manager-next-step-fallback"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Clear Script Bytecode Residue",
            goal="Remove remaining scripts __pycache__ residue and validate the cleanup.",
            scope="Shadow repo script cleanup and validation only.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["scripts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Task is assigned and started."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        async def fake_greenfield_intake_decision(db, project):
            return None

        async def fake_resolve_manager_model(*args, **kwargs):
            return (
                ManagerWorkerDecision(
                    decision_type="assign_next_task",
                    summary_markdown="Open the next narrow cleanup batch.",
                ),
                "provider_missing_refs",
            )

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            agent.status = "working"
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_greenfield_intake_decision", fake_greenfield_intake_decision)
        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        decision = asyncio.run(service.manager_next_step(db, project))

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == task.id
        assert decision.assign_to_agent_id == worker.id
        assert task.assigned_agent_id == worker.id
        assert task.status == "working"
        assert started == [(worker.id, task.id)]
    finally:
        db.close()


def test_manager_next_step_recovers_blocked_follow_up_when_provider_omits_refs(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Blocked Follow-Up Recovery",
            idea="Recover the follow-up task from a persisted blocked worker report.",
            workspace_path=sample_workspace("blocked-follow-up-recovery"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()
        blocked_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement Next Headless Or Backend Fix Batch",
            goal="Apply the next evidence-backed backend batch.",
            scope="Backend-only batch.",
            agent_role="Primary implementation",
            milestone="Milestone 2",
            allowed_paths_json=["apps/server/src/**", "apps/mcp-server/src/**", "scripts/**"],
            forbidden_paths_json=["apps/server/tests/**", "docs/**"],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Apply the next safe fix batch."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=8,
        )
        db.add(blocked_task)
        db.flush()
        run = AgentRun(
            agent_id=worker.id,
            task_id=blocked_task.id,
            runner_type="codex_cli",
            process_ref="blocked-follow-up-recovery",
            status="blocked",
            report_json={
                "agent": worker.name,
                "task_id": str(blocked_task.id),
                "status": "blocked",
                "summary": "D-32 and D-33 are in apps/server/tests/test_integrations.py, so this source-only task cannot fix them honestly.",
                "files_changed": [],
                "tests_run": [],
                "blockers": [
                    "The mapped defects D-32 and D-33 are owned by apps/server/tests/test_integrations.py.",
                    "apps/server/tests/** is explicitly forbidden for this task.",
                ],
                "risks": [],
                "recommended_next_task": "Implement D-32 and D-33 in apps/server/tests/test_integrations.py and apps/server/tests/**.",
            },
        )
        db.add(run)
        db.flush()

        async def fake_greenfield_intake_decision(db, project):
            return None

        async def fake_resolve_manager_model(*args, **kwargs):
            return (
                ManagerWorkerDecision(
                    decision_type="assign_next_task",
                    summary_markdown="Open the correctly scoped follow-up task.",
                ),
                "provider_missing_refs",
            )

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            agent.status = "working"
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_greenfield_intake_decision", fake_greenfield_intake_decision)
        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        decision = asyncio.run(service.manager_next_step(db, project))

        follow_up = db.scalar(select(Task).where(Task.project_id == project.id, Task.title == f"Unblock: {blocked_task.title}"))

        assert decision.decision_type == "request_fix"
        assert follow_up is not None
        assert follow_up.allowed_paths_json == ["apps/server/tests/test_integrations.py", "apps/server/tests/**"]
        assert follow_up.forbidden_paths_json == ["docs/**"]
        assert follow_up.assigned_agent_id == worker.id
        assert blocked_task.waiting_reason == f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up.id}."
        assert follow_up.status == "working"
        assert started == [(worker.id, follow_up.id)]
    finally:
        db.close()


def test_manager_message_releases_transaction_before_provider_turn(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "codex_cli"

        async def run_manager_turn(self, context, prompt):
            assert db.in_transaction() is False
            return RunnerHandle(
                id="manager-message-turn-1",
                runner_type="codex_cli",
                logs_path="C:/logs/manager-message-turn-1.log",
                stdout_path=None,
                stderr_path=None,
                event_log_path=None,
            ), {"item": {"text": "Manager provider reply."}}

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Manager Message Transaction Release",
            idea="Release the DB transaction before a live manager turn.",
            workspace_path=sample_workspace("manager-message-transaction-release"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"
        manager_agent = Agent(
            project_id=project.id,
            name="Manager",
            role="Manager",
            kind="manager",
            status="idle",
            workspace_path=project.workspace_path,
        )
        db.add(manager_agent)
        db.flush()

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))

        payload = asyncio.run(service.manager_message(db, project, "Continue with the next safe step."))

        assert payload["reply"] == "Manager provider reply."
    finally:
        db.close()


def test_manager_message_builds_provider_prompt_off_thread(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "codex_cli"

        async def run_manager_turn(self, context, prompt):
            assert prompt == "threaded-manager-message-prompt"
            return RunnerHandle(
                id="manager-message-threaded-1",
                runner_type="codex_cli",
                logs_path="C:/logs/manager-message-threaded-1.log",
                stdout_path=None,
                stderr_path=None,
                event_log_path=None,
            ), {"item": {"text": "Manager provider reply."}}

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Manager Message Prompt Threading",
            idea="Build live provider prompts off the event loop.",
            workspace_path=sample_workspace("manager-message-prompt-threading"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"
        manager_agent = Agent(
            project_id=project.id,
            name="Manager",
            role="Manager",
            kind="manager",
            status="idle",
            workspace_path=project.workspace_path,
        )
        db.add(manager_agent)
        db.flush()

        calls: list[str] = []

        async def fake_to_thread(func, *args, **kwargs):
            calls.append(func.__name__)
            return "threaded-manager-message-prompt"

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))
        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

        payload = asyncio.run(service.manager_message(db, project, "Continue with the next safe step."))

        assert payload["reply"] == "Manager provider reply."
        assert calls == ["manager_message_prompt"]
    finally:
        db.close()


def test_manager_next_step_releases_transaction_before_provider_turn(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "codex_cli"

        async def run_manager_turn(self, context, prompt):
            assert db.in_transaction() is False
            return RunnerHandle(
                id="manager-next-step-turn-1",
                runner_type="codex_cli",
                logs_path="C:/logs/manager-next-step-turn-1.log",
                stdout_path=None,
                stderr_path=None,
                event_log_path=None,
            ), {"item": {"text": json.dumps({"decision_type": "wait", "summary_markdown": "No safe backlog task is ready."})}}

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Manager Next Step Transaction Release",
            idea="Release the DB transaction before manager task routing.",
            workspace_path=sample_workspace("manager-next-step-transaction-release"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"
        manager_agent = Agent(
            project_id=project.id,
            name="Manager",
            role="Manager",
            kind="manager",
            status="idle",
            workspace_path=project.workspace_path,
        )
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        db.add_all([manager_agent, worker])
        db.flush()

        async def fake_greenfield_intake_decision(db, project):
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))
        monkeypatch.setattr(service, "_greenfield_intake_decision", fake_greenfield_intake_decision)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        decision = asyncio.run(service.manager_next_step(db, project))

        assert decision.decision_type == "wait"
    finally:
        db.close()


def test_manager_next_step_builds_provider_prompt_off_thread(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "codex_cli"

        async def run_manager_turn(self, context, prompt):
            assert prompt == "threaded-manager-action-prompt"
            return RunnerHandle(
                id="manager-next-step-threaded-1",
                runner_type="codex_cli",
                logs_path="C:/logs/manager-next-step-threaded-1.log",
                stdout_path=None,
                stderr_path=None,
                event_log_path=None,
            ), {"item": {"text": json.dumps({"decision_type": "wait", "summary_markdown": "No safe backlog task is ready."})}}

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Manager Next Step Prompt Threading",
            idea="Build manager action prompts off the event loop.",
            workspace_path=sample_workspace("manager-next-step-prompt-threading"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"
        manager_agent = Agent(
            project_id=project.id,
            name="Manager",
            role="Manager",
            kind="manager",
            status="idle",
            workspace_path=project.workspace_path,
        )
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        db.add_all([manager_agent, worker])
        db.flush()

        async def fake_greenfield_intake_decision(db, project):
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        calls: list[str] = []

        async def fake_to_thread(func, *args, **kwargs):
            calls.append(func.__name__)
            return "threaded-manager-action-prompt"

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))
        monkeypatch.setattr(service, "_greenfield_intake_decision", fake_greenfield_intake_decision)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)
        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

        decision = asyncio.run(service.manager_next_step(db, project))

        assert decision.decision_type == "wait"
        assert calls == ["manager_action_prompt"]
    finally:
        db.close()


def test_manager_next_step_clears_stale_codex_session_and_retries(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    stale_summary = "Error: thread/resume: thread/resume failed: no rollout found for thread id stale-thread (code -32600)"
    observed_sessions: list[str | None] = []

    class FakeRunner:
        runner_type = "codex_cli"

        async def run_manager_turn(self, context, prompt):
            observed_sessions.append(context.agent.session_ref)
            if len(observed_sessions) == 1:
                return RunnerHandle(
                    id="manager-next-step-stale-1",
                    runner_type="codex_cli",
                    logs_path="C:/logs/manager-next-step-stale-1.log",
                    stdout_path=None,
                    stderr_path=None,
                    event_log_path=None,
                ), {"item": {"text": json.dumps({"status": "failed", "runner_type": "codex_cli", "summary": stale_summary, "report": {"agent": "Manager", "task_id": "unknown", "status": "error", "summary": stale_summary}})}}
            return RunnerHandle(
                id="manager-next-step-stale-2",
                runner_type="codex_cli",
                logs_path="C:/logs/manager-next-step-stale-2.log",
                stdout_path=None,
                stderr_path=None,
                event_log_path=None,
                session_ref="fresh-thread",
            ), {"item": {"text": json.dumps({"decision_type": "wait", "summary_markdown": "No safe backlog task is ready."})}}

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Manager Stale Session Retry",
            idea="Reset dead Codex resume threads automatically.",
            workspace_path=sample_workspace("manager-stale-session-retry"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.runner_mode = "cli"
        manager_agent = Agent(
            project_id=project.id,
            name="Manager",
            role="Manager",
            kind="manager",
            status="idle",
            workspace_path=project.workspace_path,
            session_ref="stale-thread",
        )
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        db.add_all([manager_agent, worker])
        db.flush()

        async def fake_greenfield_intake_decision(db, project):
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=FakeRunner()))
        monkeypatch.setattr(service, "_greenfield_intake_decision", fake_greenfield_intake_decision)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        decision = asyncio.run(service.manager_next_step(db, project))

        assert decision.decision_type == "wait"
        assert observed_sessions == ["stale-thread", None]
    finally:
        db.close()


def test_sqlite_busy_timeout_scope_restores_original_timeout() -> None:
    service = MissionControlService()
    from db import SQLITE_DEFAULT_BUSY_TIMEOUT_MS, SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        before = db.connection().exec_driver_sql("PRAGMA busy_timeout").scalar()
        with service._sqlite_busy_timeout_scope(db, milliseconds=750):
            during = db.connection().exec_driver_sql("PRAGMA busy_timeout").scalar()
            assert int(during) == 750
        after = db.connection().exec_driver_sql("PRAGMA busy_timeout").scalar()

        assert int(before) == SQLITE_DEFAULT_BUSY_TIMEOUT_MS
        assert int(after) == int(before)
    finally:
        db.close()


def test_sqlite_engine_enables_wal_and_foreign_keys() -> None:
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        journal_mode = db.connection().exec_driver_sql("PRAGMA journal_mode").scalar()
        foreign_keys = db.connection().exec_driver_sql("PRAGMA foreign_keys").scalar()

        assert str(journal_mode).lower() == "wal"
        assert int(foreign_keys) == 1
    finally:
        db.close()


def test_manager_startup_reconciles_orphaned_worker_runs_for_safe_retry() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Restart Recovery Demo",
            idea="Recover stranded worker runs after a daemon restart.",
            workspace_path=sample_workspace("restart-recovery-demo"),
            status="building",
            runner_mode="cli",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            current_action="Enrich Diagnostic Bundle Metadata",
        )
        task = Task(
            id=1,
            project_id=project.id,
            assigned_agent_id=None,
            title="Recover me",
            goal="Prove restart reconciliation.",
            scope="Worker task recovery.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Run is safely requeued after restart"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()
        worker.current_task_id = task.id
        task.assigned_agent_id = worker.id
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="codex_cli",
            process_ref="orphaned-run",
            status="working",
            logs_path="C:/missing/orphaned-run.log",
        )
        db.add(run)
        db.commit()
        worker_id = worker.id
        task_id = task.id
        run_id = run.id
    finally:
        db.close()

    asyncio.run(service.on_startup())

    db = SessionLocal()
    try:
        refreshed_worker = db.get(Agent, worker_id)
        refreshed_task = db.get(Task, task_id)
        refreshed_run = db.get(AgentRun, run_id)

        assert refreshed_run.finished_at is not None
        assert refreshed_run.status == "stopped"
        assert refreshed_worker.status == "waiting"
        assert refreshed_worker.current_task_id is None
        assert "daemon restarted" in (refreshed_worker.current_action or "").lower()
        assert refreshed_task.status == "backlog"
        assert refreshed_task.assigned_agent_id is None
        assert "safe retry" in (refreshed_task.waiting_reason or "").lower()
    finally:
        db.close()


def test_on_startup_clears_stale_locked_paths_without_active_reservations() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Clear Stale Agent Locks",
            idea="Do not leave phantom locked_paths on workers when there are no active path reservations.",
            workspace_path=sample_workspace("clear-stale-agent-locks"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Handoff Writer",
            role="Docs specialist",
            kind="worker",
            archetype="docs",
            status="waiting",
            workspace_path=project.workspace_path,
            locked_paths_json=["tests", "docs", "mission-control"],
            current_action="Stale lock state.",
        )
        db.add(worker)
        db.commit()
        worker_id = worker.id
    finally:
        db.close()

    asyncio.run(service.on_startup())

    db = SessionLocal()
    try:
        refreshed_worker = db.get(Agent, worker_id)
        assert refreshed_worker is not None
        assert refreshed_worker.locked_paths_json == []
    finally:
        db.close()


def test_manual_start_route_rejects_manager_and_active_worker_without_side_effects(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Manual Start Guard",
            "idea": "Do not start the wrong thing.",
            "workspace_path": sample_workspace("manual-start-guard"),
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()

    db = SessionLocal()
    try:
        manager_agent = db.query(Agent).filter(Agent.project_id == project["id"], Agent.kind == "manager").one()
        worker = Agent(
            project_id=project["id"],
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project["workspace_path"],
        )
        task_one = Task(
            project_id=project["id"],
            title="Task One",
            goal="Keep the first run active.",
            scope="Narrow scope.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Remain scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        task_two = Task(
            project_id=project["id"],
            title="Task Two",
            goal="Would be the illegal second run.",
            scope="Narrow scope.",
            agent_role="Primary implementation",
            milestone="Milestone 2",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Remain scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([worker, task_one, task_two])
        db.flush()
        worker.current_task_id = task_one.id
        task_one.assigned_agent_id = worker.id
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=task_one.id,
                runner_type="dry_run",
                process_ref="existing-run",
                status="working",
            )
        )
        db.commit()

        manager_response = client.post(f"/api/agents/{manager_agent.id}/start", params={"project_id": project["id"]})
        assert manager_response.status_code == 200
        assert manager_response.json()["ok"] is False
        assert "Only worker agents" in manager_response.json()["message"]

        worker_response = client.post(f"/api/agents/{worker.id}/start", params={"project_id": project["id"]})
        assert worker_response.status_code == 200
        assert worker_response.json()["ok"] is False
        assert "active unfinished run" in worker_response.json()["message"]

        runs = db.query(AgentRun).filter(AgentRun.agent_id == worker.id, AgentRun.finished_at.is_(None)).all()
        assert len(runs) == 1
        assert runs[0].task_id == task_one.id
        db.refresh(task_two)
        assert task_two.status == "backlog"
    finally:
        db.close()


def test_start_project_agents_route_reports_paused_project(client) -> None:
    project = client.post(
        "/api/projects",
        json={
            "name": "Paused Project Start",
            "idea": "Do not claim success on paused projects.",
            "workspace_path": sample_workspace("paused-project-start"),
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()

    paused = client.post(f"/api/projects/{project['id']}/pause")
    assert paused.status_code == 200

    response = client.post(f"/api/projects/{project['id']}/agents/start")
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "Project is paused" in response.json()["message"]


def test_ingest_worker_report_rejects_mismatched_agent_and_task_identifiers() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Mismatch Report",
            idea="Do not trust decorative ids.",
            workspace_path=sample_workspace("mismatch-report"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="working", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Vertical slice",
            goal="Build",
            scope="Scope",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["run"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-test", status="working")
        db.add(run)
        db.flush()

        bad_agent_report = WorkerReport(
            agent="Not the real agent",
            task_id=str(task.id),
            status="done",
            summary="Completed",
            files_changed=[],
            tests_run=[],
            blockers=[],
            risks=[],
            recommended_next_task="None",
        )
        try:
            asyncio.run(service.ingest_worker_report(db, run, bad_agent_report))
            assert False, "Expected mismatched agent name rejection"
        except ValueError as exc:
            assert "run agent" in str(exc)

        bad_task_report = WorkerReport(
            agent=worker.name,
            task_id="999",
            status="done",
            summary="Completed",
            files_changed=[],
            tests_run=[],
            blockers=[],
            risks=[],
            recommended_next_task="None",
        )
        try:
            asyncio.run(service.ingest_worker_report(db, run, bad_task_report))
            assert False, "Expected mismatched task id rejection"
        except ValueError as exc:
            assert "run task" in str(exc)
    finally:
        db.close()


def test_stop_agent_reconciles_all_unfinished_runs() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Stop All Runs",
            idea="One stop should clean up all active runs.",
            workspace_path=sample_workspace("stop-all-runs"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task_one = Task(
            project_id=project.id,
            assigned_agent_id=None,
            title="Task One",
            goal="Stop the first run.",
            scope="Narrow scope.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Remain scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        task_two = Task(
            project_id=project.id,
            assigned_agent_id=None,
            title="Task Two",
            goal="Stop the second run.",
            scope="Narrow scope.",
            agent_role="Primary implementation",
            milestone="Milestone 2",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Remain scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=20,
        )
        db.add_all([worker, task_one, task_two])
        db.flush()
        worker.current_task_id = task_two.id
        task_one.assigned_agent_id = worker.id
        task_two.assigned_agent_id = worker.id
        run_one = AgentRun(agent_id=worker.id, task_id=task_one.id, runner_type="dry_run", process_ref="run-one", status="working")
        run_two = AgentRun(agent_id=worker.id, task_id=task_two.id, runner_type="dry_run", process_ref="run-two", status="working")
        db.add_all([run_one, run_two])
        db.commit()

        asyncio.run(service.stop_agent(db, worker))

        db.refresh(run_one)
        db.refresh(run_two)
        db.refresh(task_one)
        db.refresh(task_two)
        db.refresh(worker)
        assert run_one.finished_at is not None
        assert run_two.finished_at is not None
        assert run_one.status == "stopped"
        assert run_two.status == "stopped"
        assert task_one.assigned_agent_id is None
        assert task_two.assigned_agent_id is None
        assert task_one.status == "assigned"
        assert task_two.status == "assigned"
        assert worker.status == "stopped"
        assert worker.current_task_id is None
    finally:
        db.close()


def test_pause_project_stops_active_worker_execution() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Pause Project Runtime",
            idea="Pause should stop live execution.",
            workspace_path=sample_workspace("pause-project-runtime"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=None,
            title="Task One",
            goal="Stop the active run.",
            scope="Narrow scope.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Remain scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()
        worker.current_task_id = task.id
        task.assigned_agent_id = worker.id
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="pause-run", status="working")
        db.add(run)
        db.commit()

        paused = service.pause_project(db, project)

        db.refresh(run)
        db.refresh(task)
        db.refresh(worker)
        assert paused.status == "paused"
        assert run.finished_at is not None
        assert run.status == "stopped"
        assert worker.status == "stopped"
        assert worker.current_task_id is None
        assert task.assigned_agent_id is None
        assert task.status == "assigned"
    finally:
        db.close()


def test_project_settings_resolution_prefers_role_overrides() -> None:
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Settings Demo", idea="Idea", workspace_path="C:/demo", status="draft", runner_mode="auto", manager_mode="auto")
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "claude_code"
        settings.manager_model = "gpt-5.5"
        settings.manager_reasoning_effort = "high"
        settings.default_worker_model = "gpt-5.4"
        settings.default_worker_reasoning_effort = "low"
        settings.per_role_model_overrides_json = {"Primary implementation": "gpt-5.5-mini"}
        settings.per_role_reasoning_overrides_json = {"Primary implementation": "minimal"}

        manager_settings = resolve_manager_settings(project, settings)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="idle", workspace_path="C:/demo")
        worker_settings = resolve_worker_settings(project, settings, worker)

        assert manager_settings.model == "gpt-5.5"
        assert manager_settings.reasoning_effort == "high"
        assert manager_settings.provider == "claude_code"
        assert worker_settings.model == "gpt-5.5-mini"
        assert worker_settings.reasoning_effort == "minimal"
    finally:
        db.close()


def test_worker_settings_normalizes_legacy_external_adapter_to_custom() -> None:
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Adapter Demo", idea="Idea", workspace_path="C:/demo", status="draft", runner_mode="cli", manager_mode="auto")
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "external_adapter"
        settings.adapter_command = "python"
        settings.adapter_args_json = ["adapter.py", "--json"]
        worker = Agent(project_id=project.id, name="Adapter Worker", role="Primary implementation", kind="worker", status="idle", workspace_path="C:/demo")

        worker_settings = resolve_worker_settings(project, settings, worker)

        assert worker_settings.provider == "custom"
        assert worker_settings.adapter_command == "python"
        assert worker_settings.adapter_args == ["adapter.py", "--json"]
    finally:
        db.close()


def test_codex_project_settings_resolution_injects_supported_default_models() -> None:
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Codex Defaults", idea="Idea", workspace_path="C:/demo", status="draft", runner_mode="cli", manager_mode="auto")
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.manager_model = None
        settings.default_worker_model = None
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="idle", workspace_path="C:/demo")

        manager_settings = resolve_manager_settings(project, settings)
        worker_settings = resolve_worker_settings(project, settings, worker)

        assert manager_settings.model == DEFAULT_CLI_MODEL
        assert manager_settings.effective_model_label == DEFAULT_CLI_MODEL
        assert worker_settings.model == DEFAULT_CODEX_WORKER_MODEL
        assert worker_settings.effective_model_label == DEFAULT_CODEX_WORKER_MODEL
    finally:
        db.close()


def test_codex_project_settings_resolution_clamps_worker_and_manager_model_labels() -> None:
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Codex Clamp", idea="Idea", workspace_path="C:/demo", status="draft", runner_mode="cli", manager_mode="auto")
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.manager_model = "GPT 5.4 medium"
        settings.default_worker_model = "gpt-5.5-mini"
        settings.per_role_model_overrides_json = {"Primary implementation": "gpt-5.5-mini"}
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="idle", workspace_path="C:/demo")

        manager_settings = resolve_manager_settings(project, settings)
        worker_settings = resolve_worker_settings(project, settings, worker)

        assert manager_settings.model == DEFAULT_CLI_MODEL
        assert worker_settings.model == DEFAULT_CODEX_WORKER_MODEL
    finally:
        db.close()


def test_update_settings_clamps_codex_models_on_write() -> None:
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        service = MissionControlService()
        project = Project(name="Codex Write Clamp", idea="Idea", workspace_path="C:/demo", status="draft", runner_mode="cli", manager_mode="auto")
        db.add(project)
        db.flush()

        updated = service.update_settings(
            db,
            project,
            ProjectSettingsUpdate(
                provider="codex",
                manager_model="gpt-5.5",
                default_worker_model="gpt-5.4-mini",
                per_role_model_overrides_json={"Primary implementation": "gpt-5.5-mini"},
            ),
        )

        assert updated.manager_model == DEFAULT_CLI_MODEL
        assert updated.default_worker_model == DEFAULT_CODEX_WORKER_MODEL
        assert updated.per_role_model_overrides_json == {"Primary implementation": DEFAULT_CODEX_WORKER_MODEL}
    finally:
        db.close()


def test_codex_manager_model_resolution_allows_gpt54mini() -> None:
    from db import init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Codex Manager Mini", idea="Idea", workspace_path="C:/demo", status="draft", runner_mode="cli", manager_mode="auto")
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "codex"
        settings.manager_model = "gpt-5.4-mini"

        resolved = resolve_manager_settings(project, settings)

        assert resolved.model == "gpt-5.4-mini"
        assert resolved.effective_model_label == "gpt-5.4-mini"
    finally:
        db.close()


def test_update_settings_persists_launch_guard_configuration() -> None:
    from db import init_db

    init_db()
    db = SessionLocal()
    try:
        service = MissionControlService()
        project = Project(name="Launch Guard Config", idea="Idea", workspace_path="C:/demo", status="draft", runner_mode="cli", manager_mode="auto")
        db.add(project)
        db.flush()

        updated = service.update_settings(
            db,
            project,
            ProjectSettingsUpdate(
                launch_guard_enabled=True,
                hard_total_token_budget=1234,
                hard_total_worker_launch_budget=7,
                hard_peak_context_budget=222,
                quota_backoff_cooldown_minutes=90,
            ),
        )

        assert updated.launch_guard_enabled is True
        assert updated.hard_total_token_budget == 1234
        assert updated.hard_total_worker_launch_budget == 7
        assert updated.hard_peak_context_budget == 222
        assert updated.quota_backoff_cooldown_minutes == 90
    finally:
        db.close()


def test_format_provider_manager_reply_normalizes_nested_request_payload() -> None:
    formatted = MissionControlService()._format_provider_manager_reply(
        json.dumps(
            {
                "projectName": "Round 1 Greenfield",
                "request": {
                    "description": "Turn the project idea into a usable first slice.",
                    "status": "received",
                    "nextSteps": [
                        "Clarify the first usable outcome.",
                        "Confirm the preferred runtime.",
                    ],
                },
            }
        )
    )

    assert "## Mission Control Manager: Round 1 Greenfield" in formatted
    assert "**Status:** received" in formatted
    assert "Turn the project idea into a usable first slice." in formatted
    assert "- Clarify the first usable outcome." in formatted


def test_format_provider_manager_reply_strips_echo_payload_and_chatty_preamble() -> None:
    formatted = MissionControlService()._sanitize_provider_markdown(
        "\n".join(
            [
                "## Mission Control Manager: Demo",
                "",
                "{'from': 'Operator', 'content': 'We want a local-first CLI notes app.'}",
                "",
                "Understood, Operator. We want a local-first CLI notes app.",
                "We want a local-first CLI notes app.",
            ]
        )
    )

    assert "{'from': 'Operator'" not in formatted
    assert "Understood, Operator" not in formatted
    assert formatted.count("We want a local-first CLI notes app.") == 1


def test_verify_worker_report_evidence_downgrades_unverified_fix_claim(tmp_path) -> None:
    service = MissionControlService()
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "math_utils.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    project = Project(
        name="Evidence Demo",
        idea="Fix the failing tests.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="auto",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=workspace.as_posix(),
    )
    task = Task(
        project_id=1,
        title="Implement the smallest safe code fix",
        goal="Correct the broken math behavior.",
        scope="Update the implementation only.",
        agent_role="Service Flow Builder",
        milestone="Milestone 2 - Fix the code",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["Keep the change scoped"],
        success_criteria_json=["The implementation is corrected"],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=20,
    )
    before = service._task_workspace_snapshot(project, task)
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="2",
        status="done",
        summary="Fixed confirmed failing behavior with minimal changes.",
        files_changed=["src/math_utils.py"],
        tests_run=[],
        blockers=[],
        risks=[],
        recommended_next_task="Re-run focused validation",
    )

    verified = service._verify_worker_report_evidence(project, task, report, before)

    assert verified.status == "needs_review"
    assert verified.files_changed == []
    assert "could not verify any workspace file changes" in verified.summary.lower()


def test_no_change_review_on_fix_task_is_blocked_not_user_review() -> None:
    service = MissionControlService()
    task = Task(
        project_id=1,
        title="Fix desktop launcher behavior",
        goal="Fix the confirmed desktop launcher defect.",
        scope="Update apps/desktop/src implementation.",
        agent_role="Primary implementation",
        milestone="Milestone 1",
        allowed_paths_json=["apps/desktop/src"],
        forbidden_paths_json=[],
        validation_steps_json=["pytest -q"],
        success_criteria_json=["The implementation is corrected."],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=10,
    )
    report = WorkerReport(
        agent="Desktop Builder",
        task_id="1",
        status="needs_review",
        summary="Validated current behavior but produced no workspace changes.",
        files_changed=[],
        tests_run=["python -m pytest apps/desktop/tests/test_app.py"],
        blockers=[],
        risks=["Mission Control could not verify any workspace file changes for this run."],
        recommended_next_task="Try a more focused implementation pass.",
    )

    converted = service._convert_no_change_review_to_blocked(task, report)

    assert converted.status == "blocked"
    assert converted.files_changed == []
    assert "no-change review gate" in converted.summary
    assert "No verified workspace file changes" in converted.blockers[0]


def test_duplicate_worker_report_is_rejected() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Duplicate Report", idea="Idea", workspace_path=sample_workspace("duplicate-report"), status="building", runner_mode="dry_run", manager_mode="deterministic")
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="waiting", workspace_path=project.workspace_path)
        db.add_all([manager_agent, worker])
        db.flush()
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Vertical slice",
            goal="Build",
            scope="Scope",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["run"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add(task)
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-test", status="done", finished_at=project.created_at, report_json={"status": "done"})
        db.add(run)
        db.flush()
        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="done",
            summary="Completed",
            files_changed=[],
            tests_run=[],
            blockers=[],
            risks=[],
            recommended_next_task="None",
        )

        try:
            asyncio.run(service.ingest_worker_report(db, run, report))
            assert False, "Expected duplicate worker report rejection"
        except ValueError as exc:
            assert "already recorded" in str(exc).lower()
    finally:
        db.close()


def test_ingest_worker_report_schedules_orchestration_follow_up(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db
    from orchestration import coordinator

    scheduled: list[tuple[int, str]] = []

    async def fake_start_idle_agents(db, project):
        return None

    monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)
    monkeypatch.setattr(coordinator, "_schedule_background_turn", lambda orchestration_id, reason: scheduled.append((orchestration_id, reason)))

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Worker Follow Up",
            idea="Wake the orchestration after a worker finishes.",
            workspace_path=sample_workspace("worker-follow-up"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=project.workspace_path,
            source="test",
            user_request="Continue.",
            status="running",
            manager_status="Mission Control is continuing in the background.",
            mode="dry_run / deterministic",
            metadata_json={},
        )
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="working", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Finish bounded change",
            goal="Complete the implementation.",
            scope="Stay in scope.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([session, manager_agent, worker, task])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-test", status="working")
        db.add(run)
        db.flush()
        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="done",
            summary="Completed the scoped change.",
            files_changed=["src/app.py"],
            tests_run=["pytest -q"],
            blockers=[],
            risks=[],
            recommended_next_task="Wrap handoff.",
        )

        asyncio.run(service.ingest_worker_report(db, run, report))

        db.flush()
        db.refresh(session)
        assert session.status == "planning"
        assert "recorded worker progress" in session.manager_status.lower()
        assert scheduled == [(session.id, "worker_report_recorded")]
    finally:
        db.close()


def test_apply_worker_decision_marks_original_gating_task_done_from_follow_up() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Gate Resolution",
            idea="Do not leave the original gating task in needs_review after its validation follow-up passes.",
            workspace_path=sample_workspace("gate-resolution"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            archetype="planner",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()
        gating_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Repair Mission Control Runtime And Daemon Health Blockers",
            goal="Fix the runtime blocker.",
            scope="Runtime reliability only.",
            agent_role="runtime_reliability_engineer",
            milestone="Milestone 2",
            allowed_paths_json=["apps/server/src/*orchestrat*.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused runtime validation."],
            success_criteria_json=["Runtime blocker is cleared."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            priority=10,
        )
        follow_up_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Complete Runtime Blocker Validation For Retry Scheduling Fix",
            goal="Validate the gating runtime fix.",
            scope="Targeted validation only.",
            agent_role="execution_planner",
            milestone="Milestone 2",
            allowed_paths_json=["apps/server/tests/test_runtime_reliability.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Re-run the focused runtime tests."],
            success_criteria_json=["The blocker is validated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=11,
        )
        db.add_all([worker, gating_task, follow_up_task])
        db.flush()

        decision = ManagerWorkerDecision(
            decision_type="mark_done",
            summary_markdown="The gating task can be accepted as done.",
            task_id=gating_task.id,
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, follow_up_task, decision))

        assert gating_task.status == "done"
        assert follow_up_task.status == "done"
    finally:
        db.close()


def test_apply_worker_decision_marks_blocked_parent_done_when_follow_up_unblock_task_completes() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Blocked Parent Resolution",
            idea="Do not leave the original blocked task gating orchestration after its unblock follow-up is done.",
            workspace_path=sample_workspace("blocked-parent-resolution"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            archetype="planner",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        blocked_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Finish App-Server Residue Cleanup",
            goal="Remove the runtime residue.",
            scope="Cleanup only.",
            agent_role="execution_planner",
            milestone="Milestone 3",
            allowed_paths_json=["apps/server/.runtime-test/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the residue is gone."],
            success_criteria_json=["Residue cleanup completes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=10,
        )
        db.add_all([worker, blocked_task])
        db.flush()

        decision = ManagerWorkerDecision(
            decision_type="request_fix",
            summary_markdown="Create a follow-up unblock task.",
            assign_to_agent_id=worker.id,
            follow_up_title="Expand Scope And Finish App-Server Residue Cleanup",
            follow_up_goal="Gain write scope and finish the cleanup.",
        )
        asyncio.run(service._apply_worker_decision(db, project, worker, blocked_task, decision))
        db.flush()

        follow_up_task = db.scalar(
            select(Task).where(
                Task.project_id == project.id,
                Task.title == "Expand Scope And Finish App-Server Residue Cleanup",
            )
        )
        assert follow_up_task is not None
        assert blocked_task.waiting_reason == f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}."

        done_decision = ManagerWorkerDecision(
            decision_type="mark_done",
            summary_markdown="The unblock follow-up completed successfully.",
        )
        asyncio.run(service._apply_worker_decision(db, project, worker, follow_up_task, done_decision))

        assert follow_up_task.status == "done"
        assert blocked_task.status == "done"
        assert blocked_task.waiting_reason is None
    finally:
        db.close()


def test_apply_worker_decision_recursively_resolves_chained_follow_up_waiting_reasons() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Chained Follow Up Resolution",
            idea="Do not strand a blocked grandparent when a follow-up spawns another follow-up.",
            workspace_path=sample_workspace("chained-follow-up-resolution"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            archetype="planner",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        blocked_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Backend batch",
            goal="Finish the blocked backend batch.",
            scope="Backend only.",
            agent_role="execution_planner",
            milestone="Milestone 3",
            allowed_paths_json=["apps/server/src/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the batch is unblocked."],
            success_criteria_json=["The blocked batch can advance."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=10,
        )
        db.add_all([worker, blocked_task])
        db.flush()

        first_follow_up = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Unblock backend batch",
            goal="Perform the first unblock step.",
            scope="Repair step one.",
            agent_role="execution_planner",
            milestone="Milestone 3",
            allowed_paths_json=["apps/server/tests/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the first unblock step is complete."],
            success_criteria_json=["The first follow-up completes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=11,
            waiting_reason=f"{service._FOLLOW_UP_BLOCKER_PREFIX}999.",
        )
        second_follow_up = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Continue unblock backend batch",
            goal="Perform the second unblock step.",
            scope="Repair step two.",
            agent_role="execution_planner",
            milestone="Milestone 3",
            allowed_paths_json=["apps/server/tests/test_integrations.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the second unblock step is complete."],
            success_criteria_json=["The second follow-up completes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=12,
        )
        db.add_all([first_follow_up, second_follow_up])
        db.flush()

        blocked_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{first_follow_up.id}."
        first_follow_up.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{second_follow_up.id}."
        db.flush()

        done_decision = ManagerWorkerDecision(
            decision_type="mark_done",
            summary_markdown="The chained unblock follow-up completed successfully.",
        )
        asyncio.run(service._apply_worker_decision(db, project, worker, second_follow_up, done_decision))

        assert second_follow_up.status == "done"
        assert first_follow_up.status == "done"
        assert first_follow_up.waiting_reason is None
        assert blocked_task.status == "done"
        assert blocked_task.waiting_reason is None
    finally:
        db.close()


def test_ingest_worker_report_marks_follow_up_parent_done_from_needs_review() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db
    from orchestration import coordinator

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Follow Up Report Resolution",
            idea="Do not leave the original gating task in needs_review after the follow-up run reports done.",
            workspace_path=sample_workspace("follow-up-report-resolution"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(
            project_id=project.id,
            name="Manager AI",
            role="Project orchestration",
            kind="manager",
            status="idle",
            workspace_path=project.workspace_path,
        )
        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            archetype="planner",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        gating_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Reconcile Batch Evidence",
            goal="Accept the batch only after the follow-up validation lands.",
            scope="Handoff and validation only.",
            agent_role="handoff_writer",
            milestone="Milestone 3",
            allowed_paths_json=["mission-control/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the follow-up evidence is present."],
            success_criteria_json=["The batch can be accepted as done."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            waiting_reason=f"{service._FOLLOW_UP_BLOCKER_PREFIX}999.",
            priority=10,
        )
        follow_up_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Validate Batch Evidence",
            goal="Run the final follow-up validation.",
            scope="Focused validation only.",
            agent_role="handoff_writer",
            milestone="Milestone 3",
            allowed_paths_json=["mission-control/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation."],
            success_criteria_json=["The batch evidence is verified."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=11,
        )
        db.add_all([manager_agent, worker, gating_task, follow_up_task])
        db.flush()
        gating_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}."
        run = AgentRun(agent_id=worker.id, task_id=follow_up_task.id, runner_type="dry_run", process_ref="dry-follow-up", status="working")
        db.add(run)
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(follow_up_task.id),
            status="done",
            summary="Validation follow-up completed successfully.",
            files_changed=["mission-control/ledger.md"],
            tests_run=["pytest -q"],
            blockers=[],
            risks=[],
            recommended_next_task="Advance the baseline.",
        )

        async def fake_start_idle_agents(db, project):
            return 0

        original_schedule_follow_up = service._schedule_orchestration_follow_up
        original_start_idle_agents = service.start_idle_agents
        original_resolve_manager_model = service._resolve_manager_model
        try:
            service.start_idle_agents = fake_start_idle_agents  # type: ignore[method-assign]
            service._schedule_orchestration_follow_up = lambda db, project, reason: None  # type: ignore[method-assign]
            service._resolve_manager_model = lambda *args, **kwargs: asyncio.sleep(0, result=(ManagerWorkerDecision(decision_type="wait", summary_markdown="Wait."), "deterministic"))  # type: ignore[method-assign]
            asyncio.run(service.ingest_worker_report(db, run, report))
        finally:
            service._schedule_orchestration_follow_up = original_schedule_follow_up  # type: ignore[method-assign]
            service.start_idle_agents = original_start_idle_agents  # type: ignore[method-assign]
            service._resolve_manager_model = original_resolve_manager_model  # type: ignore[method-assign]

        assert follow_up_task.status == "done"
        assert gating_task.status == "done"
        assert gating_task.waiting_reason is None
    finally:
        db.close()


def test_start_idle_agents_reconciles_stale_done_follow_up_before_launching_next_task(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Recover Stale Follow Up State",
            idea="Do not leave restart-recovered follow-up markers blocking the next runnable task.",
            workspace_path=sample_workspace("recover-stale-follow-up-state"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Handoff Writer",
            role="Docs specialist",
            archetype="docs",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        gating_task = Task(
            project_id=project.id,
            title="Implement next repair batch",
            goal="Finish the implementation batch before validation starts.",
            scope="Implementation only.",
            agent_role="backend_runtime_engineer",
            milestone="Milestone 2",
            allowed_paths_json=["apps/server/src/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the implementation batch is complete."],
            success_criteria_json=["Implementation is done."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            waiting_reason=f"{service._FOLLOW_UP_BLOCKER_PREFIX}999.",
            priority=10,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Validate repaired batch",
            goal="Run the focused validation once the implementation is really done.",
            scope="Validation and reconciliation only.",
            agent_role="handoff_writer",
            milestone="Milestone 3",
            allowed_paths_json=["mission-control/**", "docs/**", "README.md"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation slice."],
            success_criteria_json=["Validation starts as soon as the dependency is clear."],
            estimated_complexity="small",
            dependencies_json=[],
            status="assigned",
            waiting_reason="Waiting for task dependencies to finish.",
            priority=8,
        )
        follow_up_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Verify the implementation batch",
            goal="Confirm the implementation batch before validation resumes.",
            scope="Focused verification only.",
            agent_role="handoff_writer",
            milestone="Milestone 2",
            allowed_paths_json=["mission-control/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed."],
            success_criteria_json=["The follow-up verification is complete."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=9,
        )
        db.add_all([worker, gating_task, validation_task, follow_up_task])
        db.flush()
        gating_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}."
        validation_task.dependencies_json = [gating_task.id]
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, task):
            started.append(task.id)
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 1
        assert started == [validation_task.id]
        assert gating_task.status == "done"
        assert gating_task.waiting_reason is None
    finally:
        db.close()


def test_start_idle_agents_collapses_stale_follow_up_review_chain_when_worker_signals_next_task(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Follow Up Review Chain Recovery",
            idea="Do not strand a validation task behind a stale follow-up review chain once the worker explicitly says to start it.",
            workspace_path=sample_workspace("follow-up-review-chain-recovery"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            archetype="planner",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()
        gating_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement next repair batch",
            goal="Finish the implementation batch before validation starts.",
            scope="Implementation only.",
            agent_role="execution_planner",
            milestone="Milestone 2",
            allowed_paths_json=["apps/server/src/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the implementation batch is complete."],
            success_criteria_json=["Implementation is done."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            waiting_reason=f"{service._FOLLOW_UP_BLOCKER_PREFIX}2.",
            priority=10,
        )
        follow_up_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Re-run the warning-strict repro",
            goal="Verify the implementation batch before validation resumes.",
            scope="Focused verification only.",
            agent_role="execution_planner",
            milestone="Milestone 2",
            allowed_paths_json=["apps/server/tests/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed."],
            success_criteria_json=["The follow-up verification is complete."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            waiting_reason=f"{service._FOLLOW_UP_BLOCKER_PREFIX}3.",
            priority=9,
        )
        evidence_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Resubmit verifiable fix evidence",
            goal="Provide the final evidence needed for the validation lane.",
            scope="Evidence only.",
            agent_role="execution_planner",
            milestone="Milestone 2",
            allowed_paths_json=["apps/server/tests/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Record what changed."],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            priority=8,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Validate repaired batch",
            goal="Run the focused validation once the implementation is really done.",
            scope="Validation and reconciliation only.",
            agent_role="execution_planner",
            milestone="Milestone 3",
            allowed_paths_json=["apps/server/src/**", "apps/server/tests/**", "mission-control/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation slice."],
            success_criteria_json=["Validation starts as soon as the dependency is clear."],
            estimated_complexity="small",
            dependencies_json=[],
            status="assigned",
            waiting_reason="Waiting for task dependencies to finish.",
            priority=7,
        )
        db.add_all([gating_task, follow_up_task, evidence_task, validation_task])
        db.flush()
        gating_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}."
        follow_up_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{evidence_task.id}."
        validation_task.dependencies_json = [gating_task.id]
        worker.current_action = (
            f"The next safe move is to start task {validation_task.id}. "
            f"Task {evidence_task.id} provided the missing evidence, so the implementation lane is actionable enough "
            "to move into validation-and-count reconciliation."
        )
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, task):
            started.append(task.id)
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 1
        assert started == [validation_task.id]
        assert gating_task.status == "done"
        assert follow_up_task.status == "done"
        assert evidence_task.status == "done"
        assert gating_task.waiting_reason is None
        assert follow_up_task.waiting_reason is None
        assert validation_task.waiting_reason is None
    finally:
        db.close()


def test_start_idle_agents_collapses_review_chain_for_intended_next_step_wording(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Follow Up Review Intended Next Step",
            idea="Do not strand validation when the worker says the dependent task is the intended next step using softer wording.",
            workspace_path=sample_workspace("follow-up-review-intended-next-step"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            archetype="planner",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()
        gating_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Repair D-36",
            goal="Finish the implementation batch before validation starts.",
            scope="Implementation only.",
            agent_role="execution_planner",
            milestone="Milestone 2",
            allowed_paths_json=["apps/server/src/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the implementation batch is complete."],
            success_criteria_json=["Implementation is done."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            waiting_reason=f"{service._FOLLOW_UP_BLOCKER_PREFIX}2.",
            priority=10,
        )
        evidence_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Resubmit verifiable file evidence",
            goal="Provide the repo-visible proof needed for validation to resume.",
            scope="Evidence only.",
            agent_role="execution_planner",
            milestone="Milestone 2",
            allowed_paths_json=["docs/**", "README.md"],
            forbidden_paths_json=[],
            validation_steps_json=["Record the file-visible proof."],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            priority=9,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Validate D-36 and reconcile count",
            goal="Run the focused validation once the implementation is really done.",
            scope="Validation and reconciliation only.",
            agent_role="execution_planner",
            milestone="Milestone 3",
            allowed_paths_json=["apps/server/src/**", "apps/server/tests/**", "docs/**", "README.md"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation slice."],
            success_criteria_json=["Validation starts as soon as the dependency is clear."],
            estimated_complexity="small",
            dependencies_json=[],
            status="assigned",
            waiting_reason="Waiting for task dependencies to finish.",
            priority=8,
        )
        db.add_all([gating_task, evidence_task, validation_task])
        db.flush()
        gating_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{evidence_task.id}."
        validation_task.dependencies_json = [gating_task.id]
        worker.current_action = (
            f"Task {validation_task.id} has supplied the missing repo-visible evidence and the backlog now shows "
            f"Task {validation_task.id} as the intended next step. The safest move is to resume the planned "
            "validation/count-reconciliation lane so the defect status can be updated before any new handoff refresh."
        )
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, task):
            started.append(task.id)
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 1
        assert started == [validation_task.id]
        assert gating_task.status == "done"
        assert evidence_task.status == "done"
        assert validation_task.waiting_reason is None
    finally:
        db.close()


def test_start_agent_task_stops_duplicate_runner_when_agent_gets_claimed_during_launch(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Duplicate Launch Guard",
            idea="Stop the extra runner if another turn claims the agent before the DB run record is written.",
            workspace_path=sample_workspace("duplicate-launch-guard"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Resume duplicate-prone slice",
            goal="Exercise the launch race cleanup path.",
            scope="One planner-safe task.",
            agent_role="Planner specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src/retry.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Duplicate runner is terminated before the method exits."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        class FakeRunner:
            def __init__(self) -> None:
                self.stopped: list[str] = []

            async def start_task(self, context):
                return RunnerHandle(
                    id="cli-race-cleanup",
                    runner_type="codex_cli",
                    logs_path="logs",
                    stdout_path="stdout",
                    stderr_path="stderr",
                    event_log_path="events",
                )

            async def stop_run(self, run_id: str) -> None:
                self.stopped.append(run_id)

        fake_runner = FakeRunner()

        async def fake_get_runner_for_settings(settings):
            return fake_runner

        monkeypatch.setattr(service.runners, "get_runner_for_settings", fake_get_runner_for_settings)
        monkeypatch.setattr(
            "manager.context_pack_service.build_context_pack",
            lambda db, project, agent_id, task_id, **kwargs: {"sections": []},
        )
        monkeypatch.setattr("manager.context_pack_service.render_markdown", lambda payload: "")

        checks = {"count": 0}
        original_has_unfinished = service._agent_has_unfinished_run

        def fake_has_unfinished_run(db, agent_id):
            if agent_id != worker.id:
                return original_has_unfinished(db, agent_id)
            checks["count"] += 1
            return checks["count"] >= 2

        monkeypatch.setattr(service, "_agent_has_unfinished_run", fake_has_unfinished_run)

        with pytest.raises(ValueError, match="active unfinished run"):
            asyncio.run(service.start_agent_task(db, project, worker, task))

        assert fake_runner.stopped == ["cli-race-cleanup"]
    finally:
        db.close()


def test_start_agent_task_stops_duplicate_runner_when_task_gets_claimed_during_launch(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Duplicate Task Launch Guard",
            idea="Stop the extra runner if another turn claims the task before the DB run record is written.",
            workspace_path=sample_workspace("duplicate-task-launch-guard"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Resume duplicate-task slice",
            goal="Exercise the task claim race cleanup path.",
            scope="One planner-safe task.",
            agent_role="Planner specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src/retry.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Duplicate task runner is terminated before the method exits."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        class FakeRunner:
            def __init__(self) -> None:
                self.stopped: list[str] = []

            async def start_task(self, context):
                return RunnerHandle(
                    id="cli-task-race-cleanup",
                    runner_type="codex_cli",
                    logs_path="logs",
                    stdout_path="stdout",
                    stderr_path="stderr",
                    event_log_path="events",
                )

            async def stop_run(self, run_id: str) -> None:
                self.stopped.append(run_id)

        fake_runner = FakeRunner()

        async def fake_get_runner_for_settings(settings):
            return fake_runner

        monkeypatch.setattr(service.runners, "get_runner_for_settings", fake_get_runner_for_settings)
        monkeypatch.setattr(
            "manager.context_pack_service.build_context_pack",
            lambda db, project, agent_id, task_id, **kwargs: {"sections": []},
        )
        monkeypatch.setattr("manager.context_pack_service.render_markdown", lambda payload: "")

        checks = {"count": 0}
        original_has_task_run = service._task_has_unfinished_run

        def fake_task_has_unfinished_run(db, task_id, *, exclude_agent_id=None):
            if task_id != task.id:
                return original_has_task_run(db, task_id, exclude_agent_id=exclude_agent_id)
            checks["count"] += 1
            return checks["count"] >= 2

        monkeypatch.setattr(service, "_task_has_unfinished_run", fake_task_has_unfinished_run)

        with pytest.raises(ValueError, match="Task already has an active unfinished run"):
            asyncio.run(service.start_agent_task(db, project, worker, task))

        assert fake_runner.stopped == ["cli-task-race-cleanup"]
    finally:
        db.close()


def test_apply_worker_decision_skips_non_startable_assignment(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Stale Assignment Guard",
            idea="Do not reopen finished tasks because of a stale manager decision.",
            workspace_path=sample_workspace("stale-assignment-guard"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Already finished task",
            goal="Stay done.",
            scope="No rerun should happen.",
            agent_role="Planner specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Task remains done."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append(selected_task.id)
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        decision = ManagerWorkerDecision(
            decision_type="assign_next_task",
            summary_markdown="Retry the finished task anyway.",
            task_id=task.id,
            assign_to_agent_id=worker.id,
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, None, decision))

        assert started == []
        assert task.status == "done"
        assert task.assigned_agent_id is None
    finally:
        db.close()


def test_apply_worker_decision_skips_busy_assignment_target(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Busy Assignment Guard",
            idea="Manager decisions must not assign startable work to a busy worker.",
            workspace_path=sample_workspace("busy-assignment-guard"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        reporting_worker = Agent(
            project_id=project.id,
            name="Defect Ledger Validator",
            role="Validation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        busy_worker = Agent(
            project_id=project.id,
            name="Apps Mcp Server Src Subsystem Builder",
            role="MCP specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        active_task = Task(
            project_id=project.id,
            title="Apps Mcp Server Tests Defect Batch",
            goal="Current work.",
            scope="MCP tests.",
            agent_role="MCP specialist",
            milestone="Milestone 1",
            allowed_paths_json=["apps/mcp-server/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        next_task = Task(
            project_id=project.id,
            title="Scripts Defect Batch",
            goal="Start scripts work only on an eligible worker.",
            scope="Scripts only.",
            agent_role="Validation",
            milestone="Milestone 1",
            allowed_paths_json=["scripts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([reporting_worker, busy_worker, active_task, next_task])
        db.flush()
        busy_worker.current_task_id = active_task.id
        active_task.assigned_agent_id = busy_worker.id
        db.add(AgentRun(agent_id=busy_worker.id, task_id=active_task.id, runner_type="cli", process_ref="busy-run", status="working"))
        db.commit()

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append((agent.id, selected_task.id))
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.flush()
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        decision = ManagerWorkerDecision(
            decision_type="assign_next_task",
            summary_markdown="Assign scripts to the MCP worker.",
            task_id=next_task.id,
            assign_to_agent_id=busy_worker.id,
        )

        asyncio.run(service._apply_worker_decision(db, project, reporting_worker, None, decision))

        db.refresh(next_task)
        assert started == [(reporting_worker.id, next_task.id)]
        assert next_task.assigned_agent_id == reporting_worker.id
        assert next_task.status == "working"
    finally:
        db.close()


def test_apply_worker_decision_defers_immediate_launch_agent_claim_race(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Immediate Launch Claim Race",
            idea="A concurrent refill should not fail the manager turn.",
            workspace_path=sample_workspace("immediate-launch-claim-race"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Defect Ledger Validator",
            role="Validation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Scripts Defect Batch",
            goal="Stay queued if an immediate launch loses the race.",
            scope="Scripts only.",
            agent_role="Validation",
            milestone="Milestone 1",
            allowed_paths_json=["scripts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Race is deferred, not fatal."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([worker, task])
        db.flush()

        async def fake_start_agent_task(db, project, agent, selected_task):
            raise ValueError("Agent already has an active unfinished run.")

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        decision = ManagerWorkerDecision(
            decision_type="assign_next_task",
            summary_markdown="Assign scripts immediately.",
            task_id=task.id,
            assign_to_agent_id=worker.id,
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, None, decision))

        db.refresh(worker)
        db.refresh(task)
        assert worker.status == "waiting"
        assert worker.current_task_id is None
        assert task.status == "backlog"
        assert task.assigned_agent_id is None
        assert "concurrent worker-claim race" in (task.waiting_reason or "")
    finally:
        db.close()


def test_apply_worker_decision_follow_up_can_override_allowed_paths() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Follow Up Scope Override", idea="Allow unblock tasks to change write scope.", workspace_path=sample_workspace("follow-up-scope-override"), status="building", runner_mode="dry_run", manager_mode="deterministic")
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Builder Agent A",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        blocked_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Source-only batch",
            goal="Fix the next backend issue.",
            scope="Backend only.",
            agent_role="execution_planner",
            milestone="Milestone 3",
            allowed_paths_json=["apps/server/src/**"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the fix works."],
            success_criteria_json=["The issue is fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=10,
        )
        db.add_all([worker, blocked_task])
        db.flush()

        decision = ManagerWorkerDecision(
            decision_type="request_fix",
            summary_markdown="Create a re-scoped follow-up task.",
            assign_to_agent_id=worker.id,
            follow_up_title="Repair test-surface batch",
            follow_up_goal="Fix the mapped test-surface defects.",
            follow_up_allowed_paths=["apps/server/tests/test_integrations.py"],
        )
        asyncio.run(service._apply_worker_decision(db, project, worker, blocked_task, decision))
        db.flush()

        follow_up_task = db.scalar(
            select(Task).where(
                Task.project_id == project.id,
                Task.title == "Repair test-surface batch",
            )
        )
        assert follow_up_task is not None
        assert follow_up_task.allowed_paths_json == ["apps/server/tests/test_integrations.py"]
        assert follow_up_task.forbidden_paths_json == []
        assert blocked_task.waiting_reason == f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}."
    finally:
        db.close()


def test_ingest_worker_report_uses_rescoped_follow_up_for_scope_conflict(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Scope Conflict Follow Up", idea="Create a re-scoped unblock task when the mapped defect is outside the current allowed paths.", workspace_path=sample_workspace("scope-conflict-follow-up"), status="building", runner_mode="dry_run", manager_mode="auto")
        db.add(project)
        db.flush()
        worker = Agent(project_id=project.id, name="Execution Planner", role="Primary implementation", kind="worker", status="working", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement Next Headless Or Backend Fix Batch",
            goal="Fix the mapped backend batch.",
            scope="Backend source only.",
            agent_role="execution_planner",
            milestone="Milestone 4",
            allowed_paths_json=["apps/server/src/**", "apps/mcp-server/src/**", "scripts/**"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["The mapped defects are fixed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-test", status="working")
        db.add(run)
        db.flush()

        async def fake_resolve_manager_model(*args, **kwargs):
            return (
                ManagerWorkerDecision(
                    decision_type="mark_blocked",
                    summary_markdown="Block the task.",
                ),
                "provider_mark_blocked",
            )

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary="The next mapped defects live in apps/server/tests/test_integrations.py, outside the current allowed write scope.",
            files_changed=[],
            tests_run=[],
            blockers=[
                "The mapped defects D-32 and D-33 are owned by apps/server/tests/test_integrations.py.",
                "apps/server/tests/** is explicitly forbidden for this task, while the allowed write scope is limited to apps/server/src/**, apps/mcp-server/src/**, and scripts/**.",
            ],
            risks=["Editing source paths anyway would widen scope."],
            recommended_next_task="Re-scope the task to permit apps/server/tests/test_integrations.py.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        db.flush()

        follow_up_task = db.scalar(
            select(Task).where(
                Task.project_id == project.id,
                Task.title == f"Unblock: {task.title}",
            )
        )
        assert decision.decision_type == "request_fix"
        assert follow_up_task is not None
        assert follow_up_task.allowed_paths_json == ["apps/server/tests/test_integrations.py", "apps/server/tests/**"]
        assert follow_up_task.forbidden_paths_json == []
        assert task.waiting_reason == f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}."
    finally:
        db.close()


def test_finalize_run_recovers_missing_runner_result_envelope_from_plain_report() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Strict Envelope", idea="Reject legacy worker payloads.", workspace_path=sample_workspace("strict-envelope"), status="building", runner_mode="dry_run", manager_mode="deterministic")
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="working", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Validate legacy report ingestion",
            goal="Confirm the manager can ingest a plain worker report.",
            scope="Do not edit code.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="dry_run",
            process_ref="dry-test",
            status="working",
            report_json={
                "agent": worker.name,
                "task_id": str(task.id),
                "status": "done",
                "summary": "Legacy report without an envelope.",
                "files_changed": [],
                "tests_run": [],
                "blockers": [],
                "risks": [],
                "recommended_next_task": "",
            },
        )
        db.add(run)
        db.commit()

        asyncio.run(service._finalize_run(db, project, worker, run, "done"))

        db.refresh(run)
        db.refresh(task)
        db.refresh(worker)
        traces = db.query(AgentExecutionTrace).filter(AgentExecutionTrace.run_id == run.id).all()

        assert run.status == "done"
        assert run.failure_classification is None
        assert task.status == "done"
        assert task.waiting_reason is None
        assert worker.current_task_id is None
        assert isinstance(run.result_envelope_json, dict)
        assert run.result_envelope_json.get("report", {}).get("summary") == "Legacy report without an envelope."
        assert traces
    finally:
        db.close()


def test_finalize_run_falls_back_to_valid_report_when_stored_envelope_is_malformed() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Malformed Envelope Fallback",
            idea="Do not reject a valid worker report just because the stored envelope lost its report object.",
            workspace_path=sample_workspace("malformed-envelope-fallback"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="working", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Validate malformed envelope fallback",
            goal="Confirm the manager prefers a valid worker report over a junk envelope.",
            scope="Do not edit code.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="dry_run",
            process_ref="dry-test",
            status="working",
            result_envelope_json={"status": "completed", "runner_type": "dry_run", "summary": "Missing report object."},
            report_json={
                "agent": worker.name,
                "task_id": str(task.id),
                "status": "done",
                "summary": "Valid report survives the malformed envelope.",
                "files_changed": ["apps/server/tests/test_manager.py"],
                "tests_run": ["pytest -q"],
                "blockers": [],
                "risks": [],
                "recommended_next_task": "",
            },
        )
        db.add(run)
        db.commit()

        asyncio.run(service._finalize_run(db, project, worker, run, "done"))

        db.refresh(run)
        db.refresh(task)
        db.refresh(worker)

        assert run.status == "done"
        assert run.failure_classification is None
        assert task.status == "done"
        assert worker.current_task_id is None
        assert isinstance(run.result_envelope_json, dict)
        assert run.result_envelope_json.get("report", {}).get("summary") == "Valid report survives the malformed envelope."
        assert run.report_json.get("summary") == "Valid report survives the malformed envelope."
    finally:
        db.close()


def test_finalize_run_rejects_missing_runner_result_envelope_without_recoverable_report() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        scheduled_reasons: list[str] = []
        original_schedule_follow_up = service._schedule_orchestration_follow_up
        service._schedule_orchestration_follow_up = lambda db, project, reason: scheduled_reasons.append(reason)  # type: ignore[method-assign]
        project = Project(name="Strict Envelope", idea="Reject invalid legacy worker payloads.", workspace_path=sample_workspace("strict-envelope-invalid"), status="building", runner_mode="dry_run", manager_mode="deterministic")
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="working", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Vertical slice",
            goal="Build the thing.",
            scope="Stay narrow.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="dry_run",
            process_ref="dry-test",
            status="working",
            report_json={"summary": "Missing required worker report fields."},
        )
        db.add(run)
        db.commit()

        asyncio.run(service._finalize_run(db, project, worker, run, "done"))

        db.refresh(run)
        db.refresh(task)
        db.refresh(worker)
        recovery_plans = db.query(RecoveryPlan).filter(RecoveryPlan.project_id == project.id).all()
        traces = db.query(AgentExecutionTrace).filter(AgentExecutionTrace.run_id == run.id).all()

        assert run.status == "error"
        assert run.failure_classification == "runner_bug"
        assert task.status == "backlog"
        assert "queued a clean retry" in (task.waiting_reason or "").lower()
        assert task.assigned_agent_id is None
        assert worker.current_task_id is None
        assert recovery_plans
        assert scheduled_reasons == ["worker_report_rejected"]
        assert traces == []
    finally:
        service._schedule_orchestration_follow_up = original_schedule_follow_up  # type: ignore[method-assign]
        db.close()


def test_monitor_run_rejects_worker_when_monitor_loop_raises(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        async def read_events(self, run_id: str) -> list[dict[str, object]]:
            raise RuntimeError("event persistence exploded")

        async def get_status(self, run_id: str) -> str:
            return "starting"

    init_db()
    db = SessionLocal()
    try:
        scheduled_reasons: list[str] = []
        original_schedule_follow_up = service._schedule_orchestration_follow_up
        service._schedule_orchestration_follow_up = lambda db, project, reason: scheduled_reasons.append(reason)  # type: ignore[method-assign]
        project = Project(
            name="Monitor Failure Recovery",
            idea="Reject zombie worker runs when the monitor loop crashes.",
            workspace_path=sample_workspace("monitor-failure-recovery"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="starting", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Recover from monitor crash",
            goal="Do not leave the worker stuck forever.",
            scope="Worker monitor bookkeeping.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["The failed monitor path resets the task for retry."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        worker.current_task_id = task.id
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="codex_cli",
            process_ref="cli-monitor-fail",
            status="starting",
        )
        db.add(run)
        db.commit()
        service.run_input_snapshots[run.id] = {"apps/server/src/main.py": "abc123"}

        async def fake_get_runner(runner_type: str):
            return FakeRunner()

        async def fast_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(service.runners, "get_runner", fake_get_runner)
        monkeypatch.setattr("manager.asyncio.sleep", fast_sleep)

        asyncio.run(service._monitor_run(run.id))

        db.refresh(run)
        db.refresh(task)
        db.refresh(worker)
        recovery_plans = db.query(RecoveryPlan).filter(RecoveryPlan.project_id == project.id).all()

        assert run.status == "error"
        assert run.finished_at is not None
        assert run.failure_classification == "runner_bug"
        assert "run monitor failed" in (run.report_json or {}).get("summary", "").lower()
        assert task.status == "backlog"
        assert "queued a clean retry" in (task.waiting_reason or "").lower()
        assert task.assigned_agent_id is None
        assert worker.status == "waiting"
        assert worker.current_task_id is None
        assert recovery_plans
        assert scheduled_reasons == ["worker_report_rejected"]
        assert run.id not in service.run_input_snapshots
    finally:
        service._schedule_orchestration_follow_up = original_schedule_follow_up  # type: ignore[method-assign]
        db.close()


def test_monitor_run_preserves_resolved_remote_execution_when_runner_emits_thin_effective_settings(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunState:
        exit_code = 0
        session_ref = "browser-box"

    class FakeRunner:
        def __init__(self, worker_name: str, task_id: int) -> None:
            self.runs = {"remote-monitor": FakeRunState()}
            self._events = [
                {
                    "type": "turn.started",
                    "effective_settings": {
                        "provider": "codex",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": json.dumps(
                            {
                                "status": "completed",
                                "runner_type": "remote_adapter",
                                "lane": "test_execution",
                                "summary": "Remote browser validation completed.",
                                "report": {
                                    "agent": worker_name,
                                    "task_id": str(task_id),
                                    "status": "done",
                                    "summary": "Remote browser validation completed.",
                                    "files_changed": ["artifacts/screenshots/boot.png"],
                                    "tests_run": ["playwright test"],
                                    "blockers": [],
                                    "risks": [],
                                    "recommended_next_task": "",
                                },
                                "commands_attempted": ["playwright test"],
                                "evidence": [],
                                "diagnostics": [],
                                "approvals_requested": [],
                                "recovery_plan": [],
                                "edits": [],
                                "failure_classification": None,
                                "needs_approval": False,
                                "metadata_json": {},
                            }
                        ),
                    },
                },
                {"type": "turn.completed"},
            ]

        async def read_events(self, run_id: str) -> list[dict[str, object]]:
            events = list(self._events)
            self._events = []
            return events

        async def get_status(self, run_id: str) -> str:
            return "done"

        @staticmethod
        def try_parse_result_envelope(text: str):
            return BaseCodexRunner.try_parse_result_envelope(text)

        @staticmethod
        def try_parse_report(text: str):
            return BaseCodexRunner.try_parse_report(text)

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerWorkerDecision(
                decision_type="wait",
                summary_markdown="Remote validation is recorded; wait for next dispatch.",
            ),
            "deterministic",
        )

    async def fake_start_idle_agents(*args, **kwargs):
        return 0

    original_sleep = asyncio.sleep

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Monitor Preserves Remote Execution",
            idea="Do not lose remote execution contracts when runner events only emit thin effective settings.",
            workspace_path=sample_workspace("monitor-preserves-remote-execution"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        Path(project.workspace_path).mkdir(parents=True, exist_ok=True)
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Browser Validation Agent", role="Browser validation", kind="worker", status="starting", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Run remote browser validation",
            goal="Collect remote browser evidence without losing contract metadata.",
            scope="Do not edit code.",
            agent_role="Browser validation",
            milestone="Milestone 2",
            allowed_paths_json=["artifacts"],
            forbidden_paths_json=[],
            validation_steps_json=["playwright test"],
            success_criteria_json=["Run recorded with remote execution metadata intact."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        worker.current_task_id = task.id
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="remote_adapter",
            process_ref="remote-monitor",
            status="starting",
            effective_settings_json={
                "provider": "codex",
                "model": "gpt-5.4-mini",
                "reasoning_effort": "medium",
                "remote_execution": {
                    "policy": {"enabled": True, "required_runner_family": "external_adapter"},
                    "selected_target": {"id": "browser-box", "transport": "tailscale_ssh", "host": "browser-box.tailnet.ts.net"},
                    "result_contract": {
                        "expected_evidence_categories": ["logs", "screenshots", "traces"],
                        "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                    },
                },
            },
        )
        db.add(run)
        db.commit()

        monkeypatch.setattr(service.runners, "get_runner", lambda runner_type: original_sleep(0, result=FakeRunner(worker.name, task.id)))
        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)
        monkeypatch.setattr("manager.asyncio.sleep", lambda _seconds: original_sleep(0))

        asyncio.run(service._monitor_run(run.id))

        db.refresh(run)
        assert isinstance(run.effective_settings_json, dict)
        assert run.effective_settings_json["remote_execution"]["selected_target"]["id"] == "browser-box"
        assert run.effective_settings_json["remote_execution"]["result_contract"]["normalized_summary_artifact"] == (
            "artifacts/remote-execution-governance/normalized-execution-summary.json"
        )
        assert run.status == "done"
    finally:
        db.close()


def test_ingest_worker_report_persists_envelope_and_span_tree() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(name="Span Tree", idea="Persist typed runner traces.", workspace_path=sample_workspace("span-tree"), status="building", runner_mode="dry_run", manager_mode="deterministic")
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Validation Agent", role="Validation", kind="worker", status="working", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Run focused validation",
            goal="Execute targeted pytest validation.",
            scope="Do not edit code.",
            agent_role="Validation",
            milestone="Milestone 2",
            allowed_paths_json=["apps/server/tests"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["The failure is isolated"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-test", status="working")
        db.add(run)
        db.flush()
        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary="Cluster GPU memory is saturated; validation cannot start.",
            files_changed=[],
            tests_run=["python -m pytest apps/server/tests/test_manager.py -q"],
            blockers=["GPU memory is saturated."],
            risks=["This looks like an infrastructure blocker."],
            recommended_next_task="Wait for cluster capacity.",
        )
        envelope = RunnerResultEnvelope(
            status="blocked",
            runner_type="dry_run",
            lane="test_execution",
            summary=report.summary,
            report=report,
            files_changed=[],
            tests_run=list(report.tests_run),
            commands_attempted=list(report.tests_run),
            evidence=[],
            risks=list(report.risks),
            blockers=list(report.blockers),
            diagnostics=["dcgm memory saturation"],
            approvals_requested=[],
            recovery_plan=["Retry once cluster pressure drops."],
            edits=[],
            failure_classification="infra_blocker",
            needs_approval=False,
            metadata_json={},
        )

        asyncio.run(service.ingest_worker_report(db, run, report, envelope=envelope))

        db.refresh(run)
        traces = db.query(AgentExecutionTrace).filter(AgentExecutionTrace.run_id == run.id).order_by(AgentExecutionTrace.id.asc()).all()
        assert run.result_envelope_json is not None
        assert run.failure_classification == "infra_blocker"
        assert len(traces) == 3
        assert {trace.span_kind for trace in traces} == {"run", "test_execution", "validation"}
        assert all(trace.trace_id == f"run-{run.id}" for trace in traces)
        assert any(trace.failure_classification == "infra_blocker" for trace in traces)
    finally:
        db.close()


def test_ingest_worker_report_persists_remote_execution_normalized_summary_artifact(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerWorkerDecision(
                decision_type="wait",
                summary_markdown="Record the run and wait.",
            ),
            "deterministic",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)

    init_db()
    db = SessionLocal()
    try:
        workspace = Path(sample_workspace("remote-exec-normalized-summary"))
        (workspace / "artifacts" / "screenshots").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "coverage").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "traces").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "logs").mkdir(parents=True, exist_ok=True)
        (workspace / "README.md").write_text("remote exec demo\n", encoding="utf-8")
        project = Project(
            name="Remote Exec Normalized Summary",
            idea="Persist real brokered-run evidence into the remote execution rollup.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(
            project_id=project.id,
            name="Manager AI",
            role="Project orchestration",
            kind="manager",
            status="idle",
            workspace_path=project.workspace_path,
        )
        worker = Agent(
            project_id=project.id,
            name="Browser Validation Agent",
            role="Browser validation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Run browser validation remotely",
            goal="Collect governed browser evidence from a brokered host.",
            scope="Do not edit code.",
            agent_role="Browser validation",
            milestone="Milestone 2",
            allowed_paths_json=["artifacts"],
            forbidden_paths_json=[],
            validation_steps_json=["playwright test"],
            success_criteria_json=["Evidence is captured in governed artifact lanes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        get_or_create_project_settings(db, project).remote_execution_policy_json = {
            "enabled": True,
            "preferred_target_id": "browser-box",
            "required_result_formats": ["json"],
            "required_command_families": ["browser"],
            "required_toolchains": ["playwright"],
        }
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="external_adapter",
            process_ref="remote-browser-run",
            status="working",
            logs_path="artifacts/logs/run.log",
            stdout_path="artifacts/logs/stdout.log",
            stderr_path="artifacts/logs/stderr.log",
            event_log_path="artifacts/logs/events.jsonl",
            effective_settings_json={
                "provider": "codex",
                "model": "test-model",
                "remote_execution": {
                    "policy": {
                        "enabled": True,
                        "required_result_formats": ["json"],
                        "required_command_families": ["browser"],
                        "required_toolchains": ["playwright"],
                    },
                    "selected_target": {
                        "id": "browser-box",
                        "transport": "tailscale_ssh",
                        "os_family": "linux",
                    },
                    "broker_contract": {
                        "target_result_formats": ["json"],
                        "target_command_families": ["browser"],
                        "target_toolchains": ["playwright"],
                    },
                    "result_contract": {
                        "expected_evidence_categories": ["logs", "coverage", "screenshots", "traces"],
                        "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                    },
                },
            },
        )
        db.add(run)
        db.flush()
        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="done",
            summary="Browser validation completed on the brokered host.",
            files_changed=[
                "artifacts/screenshots/boot.png",
                "artifacts/coverage/lcov.info",
            ],
            tests_run=["playwright test"],
            blockers=[],
            risks=[],
            recommended_next_task="Review the governed evidence bundle.",
        )
        envelope = RunnerResultEnvelope(
            status="completed",
            runner_type="external_adapter",
            lane="test_execution",
            summary=report.summary,
            report=report,
            files_changed=list(report.files_changed),
            tests_run=list(report.tests_run),
            commands_attempted=["playwright test"],
            evidence=[
                {
                    "kind": "artifact",
                    "summary": "Captured Playwright trace bundle.",
                    "status": "present",
                    "source_path": "artifacts/traces/playwright-trace.zip",
                }
            ],
            risks=[],
            blockers=[],
            diagnostics=["artifacts/logs/run.log"],
            approvals_requested=[],
            recovery_plan=[],
            edits=[],
            failure_classification=None,
            needs_approval=False,
            metadata_json={},
        )

        asyncio.run(service.ingest_worker_report(db, run, report, envelope=envelope))

        artifact_path = workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json"
        assert artifact_path.exists()
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))

        assert payload["summary_count"] == 1
        assert payload["passed_count"] == 1
        assert payload["failed_count"] == 0
        assert payload["expected_evidence_categories"] == ["logs", "coverage", "screenshots", "traces"]
        assert payload["observed_evidence_categories"] == ["logs", "screenshots", "traces", "coverage"]
        assert payload["latest_run_id"] == run.id
        assert payload["latest_report_status"] == "done"
        assert payload["summaries"][0]["selected_target_id"] == "browser-box"
        assert payload["summaries"][0]["observed_evidence_categories"] == ["logs", "screenshots", "traces", "coverage"]
    finally:
        db.close()


def test_ingest_worker_report_keeps_result_when_remote_execution_rollup_write_fails(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerWorkerDecision(
                decision_type="wait",
                summary_markdown="Record the run and wait.",
            ),
            "deterministic",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
    monkeypatch.setattr(
        service,
        "_persist_remote_execution_normalized_results_summary",
        lambda project, run, envelope: (_ for _ in ()).throw(OSError("disk full during rollup write")),
    )

    init_db()
    db = SessionLocal()
    try:
        workspace = Path(sample_workspace("remote-exec-rollup-write-failure"))
        workspace.mkdir(parents=True, exist_ok=True)
        project = Project(
            name="Remote Exec Rollup Write Failure",
            idea="Do not lose accepted worker results when the remote rollup artifact cannot be written.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(
            project_id=project.id,
            name="Manager AI",
            role="Project orchestration",
            kind="manager",
            status="idle",
            workspace_path=project.workspace_path,
        )
        worker = Agent(
            project_id=project.id,
            name="GPU Validation Agent",
            role="Validation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Validate brokered GPU run",
            goal="Persist the accepted report even if artifact storage complains.",
            scope="Do not edit code.",
            agent_role="Validation",
            milestone="Milestone 2",
            allowed_paths_json=["artifacts"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest"],
            success_criteria_json=["The worker report is still recorded."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="external_adapter",
            process_ref="gpu-remote-run",
            status="working",
            effective_settings_json={
                "remote_execution": {
                    "policy": {"enabled": True},
                    "result_contract": {
                        "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                    },
                }
            },
        )
        db.add(run)
        db.flush()
        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="done",
            summary="Accepted the brokered GPU validation result.",
            files_changed=[],
            tests_run=["python -m pytest"],
            blockers=[],
            risks=[],
            recommended_next_task="Continue with review.",
        )
        envelope = RunnerResultEnvelope(
            status="completed",
            runner_type="external_adapter",
            lane="test_execution",
            summary=report.summary,
            report=report,
            files_changed=[],
            tests_run=list(report.tests_run),
            commands_attempted=list(report.tests_run),
            evidence=[],
            risks=[],
            blockers=[],
            diagnostics=[],
            approvals_requested=[],
            recovery_plan=[],
            edits=[],
            failure_classification=None,
            needs_approval=False,
            metadata_json={},
        )

        asyncio.run(service.ingest_worker_report(db, run, report, envelope=envelope))

        db.refresh(run)
        db.refresh(task)
        events = db.query(ProjectEvent).filter(ProjectEvent.project_id == project.id).all()

        assert run.report_json is not None
        assert run.finished_at is not None
        assert task.status == "done"
        assert any(event.event_type == "remote_execution.rollup_persist_failed" for event in events)
    finally:
        db.close()


def test_finalize_run_recovers_result_envelope_from_event_log(tmp_path) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Recover Event Log Envelope",
            idea="Do not reject a completed worker when the structured envelope only survived in the event log.",
            workspace_path=sample_workspace("recover-event-log-envelope"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Windows Worker", role="Windows specialist", kind="worker", status="working", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Remove Windows cache artifact",
            goal="Delete the committed Windows cache file.",
            scope="Stay inside Microsoft/Windows.",
            agent_role="Windows specialist",
            milestone="Milestone 1",
            allowed_paths_json=["Microsoft/Windows"],
            forbidden_paths_json=[],
            validation_steps_json=["Test-Path Microsoft/Windows/PowerShell/ModuleAnalysisCache"],
            success_criteria_json=["The cache file is gone."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        worker.current_task_id = task.id
        event_log_path = tmp_path / "worker.events.jsonl"
        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="done",
            summary="Removed the Windows cache artifact.",
            files_changed=["Microsoft/Windows/PowerShell/ModuleAnalysisCache"],
            tests_run=["Test-Path Microsoft/Windows/PowerShell/ModuleAnalysisCache"],
            blockers=[],
            risks=[],
            recommended_next_task="",
        )
        envelope = RunnerResultEnvelope(
            status="completed",
            runner_type="codex_cli",
            lane="implementation",
            summary=report.summary,
            report=report,
            files_changed=list(report.files_changed),
            tests_run=list(report.tests_run),
            commands_attempted=list(report.tests_run),
            evidence=[],
            risks=[],
            blockers=[],
            diagnostics=[],
            approvals_requested=[],
            recovery_plan=[],
            edits=[],
            failure_classification=None,
            needs_approval=False,
            metadata_json={},
        )
        event_log_path.write_text(
            "\n".join(
                [
                    json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                    json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": envelope.model_dump_json()}}),
                    json.dumps({"type": "turn.completed"}),
                ]
            ),
            encoding="utf-8",
        )
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="codex_cli",
            process_ref="cli-event-log-recovery",
            status="working",
            event_log_path=str(event_log_path),
        )
        db.add(run)
        db.commit()

        asyncio.run(service._finalize_run(db, project, worker, run, "done"))

        db.refresh(run)
        db.refresh(task)
        db.refresh(worker)

        assert run.status == "done"
        assert run.failure_classification is None
        assert isinstance(run.result_envelope_json, dict)
        assert run.result_envelope_json.get("report", {}).get("summary") == "Removed the Windows cache artifact."
        assert task.status == "done"
        assert worker.current_task_id is None
    finally:
        db.close()


def test_remote_execution_governance_summary_reads_persisted_normalized_results_rollup(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        workspace = Path(sample_workspace("remote-exec-governance-rollup"))
        (workspace / "artifacts" / "remote-execution-governance").mkdir(parents=True, exist_ok=True)
        project = Project(
            name="Remote Exec Governance Rollup",
            idea="Governance should use persisted remote run evidence when it exists.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.commit()
        rollup_path = workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json"
        rollup_path.write_text(
            json.dumps(
                {
                    "project_id": project.id,
                    "project_name": project.name,
                    "summary_count": 1,
                    "passed_count": 1,
                    "failed_count": 0,
                    "missing_count": 0,
                    "parse_error_count": 0,
                    "warning_count": 0,
                    "publish_ready": True,
                    "blocking_statuses": ["failed", "missing", "parse_error"],
                    "expected_evidence_categories": ["logs", "coverage"],
                    "observed_evidence_categories": ["logs", "coverage", "screenshots", "traces"],
                    "latest_run_id": 5,
                    "latest_report_status": "done",
                    "latest_failure_classification": None,
                    "summaries": [
                        {
                            "run_id": 5,
                            "status": "passed",
                            "observed_evidence_categories": ["logs", "coverage", "screenshots", "traces"],
                        }
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(
            service,
            "preview_project_remote_execution",
            lambda db, project: {
                "policy": {
                    "enabled": True,
                    "required_repo_roots": ["/srv/work"],
                    "required_path_prefixes": ["src", "artifacts"],
                    "required_result_formats": ["json"],
                    "required_command_families": ["browser"],
                    "required_toolchains": ["playwright"],
                    "allowed_trust_levels": ["trusted"],
                },
                "artifact_contract": {
                    "preflight_ready": True,
                    "blocking_reasons": [],
                },
                "connector_contract": {
                    "preflight_ready": True,
                    "missing_required_families": [],
                },
                "broker_contract": {
                    "target_repo_roots": ["/srv/work"],
                    "target_path_prefixes": ["src", "artifacts"],
                    "target_result_formats": ["json"],
                    "target_command_families": ["browser"],
                    "target_toolchains": ["playwright"],
                    "target_command_runtime_seconds": 900,
                    "target_file_transfer_quota_mb": 512,
                    "session_recording_enabled": True,
                    "preflight_ready": True,
                    "blocking_reasons": [],
                },
                "result_contract": {
                    "expected_evidence_categories": ["logs", "coverage"],
                    "observed_evidence_categories": [],
                    "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                },
                "selected_target": {
                    "id": "browser-box",
                    "transport": "tailscale_ssh",
                    "os_family": "linux",
                },
                "selected_target_id": "browser-box",
                "selected_target_probe_status": "ready",
                "required_runner_family": "external_adapter",
                "preflight_ready": True,
                "blocking_reasons": [],
                "eligible_target_count": 1,
                "ready_candidate_count": 1,
                "ready_candidate_ids": ["browser-box"],
            },
        )
        monkeypatch.setattr(service, "build_device_broker_summary", lambda db, project: {"ready_target_count": 1, "blocking_reasons": []})
        monkeypatch.setattr(
            service,
            "build_artifact_transport_summary",
            lambda db, project: {
                "recommended_transport_mode": "brokered_sync",
                "blocking_reasons": [],
                "notes": [],
            },
        )
        monkeypatch.setattr(
            service,
            "build_platform_runner_summary",
            lambda db, project: {
                "ready_lane_count": 1,
                "ready_lane_ids": ["browser"],
                "selected_ready_lane_ids": ["browser"],
                "lanes": [
                    {
                        "lane_id": "browser",
                        "status": "ready",
                        "selected_target_ids": ["browser-box"],
                    }
                ],
            },
        )

        summary = service.build_remote_execution_governance_summary(db, project)

        assert summary["governance_status"] == "ready"
        assert summary["normalized_results_summary_path"] == "artifacts/remote-execution-governance/normalized-execution-summary.json"
        assert summary["normalized_summary_count"] == 1
        assert summary["normalized_passed_count"] == 1
        assert summary["normalized_failed_count"] == 0
        assert summary["normalized_publish_ready"] is True
        assert summary["observed_evidence_categories"] == ["logs", "coverage", "screenshots", "traces"]
    finally:
        db.close()


def test_build_project_artifact_registry_promotes_remote_runtime_manifest_signals() -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("artifact-registry-remote-runtime"))
    runtime_root = workspace / "artifacts" / "remote-execution-governance" / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# remote runtime\n", encoding="utf-8")
    (workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json").write_text(
        json.dumps({"run_count": 1}, indent=2),
        encoding="utf-8",
    )
    (runtime_root / "remote-adapter-abc-launch-manifest.json").write_text(
        json.dumps(
            {
                "run_id": "remote-adapter-abc",
                "target_id": "browser-box",
                "transport": "tailscale_ssh",
                "remote_artifact_paths": [
                    "/srv/browser-work/artifacts/screenshots/boot.png",
                    "/srv/browser-work/artifacts/logs/run.log",
                ],
                "session_recording_required": True,
                "session_recording_enabled": True,
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "command_preview": "tailscale ssh browser-box tailnet command",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    project = Project(
        id=101,
        name="Artifact Registry Runtime Overlay",
        workspace_path=workspace.as_posix(),
        source_path=workspace.as_posix(),
    )

    summary = service.build_project_artifact_registry(project)

    assert "artifacts/remote-execution-governance/runtime/remote-adapter-abc-launch-manifest.json" in summary["artifact_paths"]
    assert summary["artifact_kind_counts"]["remote_execution_runtime_manifest"] == 1
    assert "artifacts/remote-execution-governance/runtime/remote-adapter-abc-launch-manifest.json" in summary["config_review_paths"]
    assert "artifacts/remote-execution-governance/normalized-execution-summary.json" in summary["validation_evidence_targets"]
    assert "/srv/browser-work/artifacts/screenshots/boot.png" in summary["validation_evidence_targets"]
    assert "tailscale ssh browser-box tailnet command" in summary["execution_entrypoints"]
    assert any("session-recording artifact" in step for step in summary["recommended_next_steps"])


def test_build_artifact_registry_plan_writes_remote_runtime_rollup_and_flags_recording_gaps() -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("artifact-registry-remote-runtime-plan"))
    runtime_root = workspace / "artifacts" / "remote-execution-governance" / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# remote runtime plan\n", encoding="utf-8")
    (workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json").write_text(
        json.dumps({"run_count": 1}, indent=2),
        encoding="utf-8",
    )
    (runtime_root / "remote-adapter-plan-launch-manifest.json").write_text(
        json.dumps(
            {
                "run_id": "remote-adapter-plan",
                "target_id": "gpu-linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "remote_artifact_paths": ["/srv/gpu-work/artifacts/screenshots/boot.png"],
                "session_recording_required": True,
                "session_recording_enabled": True,
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "command_preview": "tailscale ssh gpu-linux.tailnet.ts.net python -m pytest",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    project = Project(
        id=102,
        name="Artifact Registry Runtime Plan",
        workspace_path=workspace.as_posix(),
        source_path=workspace.as_posix(),
    )

    plan = service.build_artifact_registry_plan(project)

    assert plan["remote_runtime_rollup_path"] == "artifacts/artifact-registry/remote-runtime-rollup.json"
    assert plan["plan_status"] == "partial"
    assert "remote_session_recording_artifact_gap" in plan["blocking_reasons"]
    rollup = json.loads((workspace / "artifacts" / "artifact-registry" / "remote-runtime-rollup.json").read_text(encoding="utf-8"))
    assert rollup["runtime_manifest_count"] == 1
    assert rollup["session_recording_artifact_gap_count"] == 1
    assert rollup["runtime_manifest_paths"] == [
        "artifacts/remote-execution-governance/runtime/remote-adapter-plan-launch-manifest.json"
    ]
    assert rollup["target_ids"] == ["gpu-linux"]
    assert rollup["execution_entrypoints"] == ["tailscale ssh gpu-linux.tailnet.ts.net python -m pytest"]
    assert rollup["normalized_summary_artifacts"] == ["artifacts/remote-execution-governance/normalized-execution-summary.json"]


def test_build_artifact_registry_plan_clears_recording_gap_when_runtime_manifest_declares_recording_paths() -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("artifact-registry-remote-runtime-plan-ready"))
    runtime_root = workspace / "artifacts" / "remote-execution-governance" / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# remote runtime plan ready\n", encoding="utf-8")
    (workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json").write_text(
        json.dumps({"run_count": 1}, indent=2),
        encoding="utf-8",
    )
    recording_root = workspace / "artifacts" / "remote-execution-governance" / "session-recordings"
    recording_root.mkdir(parents=True, exist_ok=True)
    (recording_root / "gpu-linux.cast").write_text("cast\n", encoding="utf-8")
    (runtime_root / "remote-adapter-plan-ready-launch-manifest.json").write_text(
        json.dumps(
            {
                "run_id": "remote-adapter-plan-ready",
                "target_id": "gpu-linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "remote_artifact_paths": ["/srv/gpu-work/artifacts/screenshots/boot.png"],
                "session_recording_required": True,
                "session_recording_enabled": True,
                "session_recording_artifact_paths": [
                    "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
                ],
                "remote_session_recording_artifact_paths": [
                    "/srv/gpu-work/artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
                ],
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "command_preview": "tailscale ssh gpu-linux.tailnet.ts.net python -m pytest",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    project = Project(
        id=103,
        name="Artifact Registry Runtime Plan Ready",
        workspace_path=workspace.as_posix(),
        source_path=workspace.as_posix(),
    )

    plan = service.build_artifact_registry_plan(project)

    assert plan["plan_status"] == "ready"
    assert "remote_session_recording_artifact_gap" not in plan["blocking_reasons"]
    rollup = json.loads((workspace / "artifacts" / "artifact-registry" / "remote-runtime-rollup.json").read_text(encoding="utf-8"))
    assert rollup["session_recording_artifact_gap_count"] == 0
    assert rollup["session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]
    assert rollup["produced_session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]
    assert rollup["missing_session_recording_artifact_paths"] == []
    assert rollup["remote_session_recording_artifact_paths"] == [
        "/srv/gpu-work/artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]


def test_build_artifact_registry_plan_keeps_recording_gap_when_manifest_declares_but_does_not_produce_recording() -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("artifact-registry-remote-runtime-plan-declared-only"))
    runtime_root = workspace / "artifacts" / "remote-execution-governance" / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# remote runtime declared only\n", encoding="utf-8")
    (workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json").write_text(
        json.dumps({"run_count": 1}, indent=2),
        encoding="utf-8",
    )
    (runtime_root / "remote-adapter-plan-declared-only-launch-manifest.json").write_text(
        json.dumps(
            {
                "run_id": "remote-adapter-plan-declared-only",
                "target_id": "gpu-linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "remote_artifact_paths": ["/srv/gpu-work/artifacts/screenshots/boot.png"],
                "session_recording_required": True,
                "session_recording_enabled": True,
                "session_recording_artifact_paths": [
                    "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
                ],
                "remote_session_recording_artifact_paths": [
                    "/srv/gpu-work/artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
                ],
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "command_preview": "tailscale ssh gpu-linux.tailnet.ts.net python -m pytest",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    project = Project(
        id=104,
        name="Artifact Registry Runtime Plan Declared Only",
        workspace_path=workspace.as_posix(),
        source_path=workspace.as_posix(),
    )

    plan = service.build_artifact_registry_plan(project)

    assert plan["plan_status"] == "partial"
    assert "remote_session_recording_artifact_gap" in plan["blocking_reasons"]
    rollup = json.loads((workspace / "artifacts" / "artifact-registry" / "remote-runtime-rollup.json").read_text(encoding="utf-8"))
    assert rollup["session_recording_declared_count"] == 1
    assert rollup["session_recording_artifact_present_count"] == 0
    assert rollup["session_recording_artifact_gap_count"] == 1
    assert rollup["produced_session_recording_artifact_paths"] == []
    assert rollup["missing_session_recording_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]


def test_get_project_handoff_summary_falls_back_to_persisted_final_report() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Persisted Final Report",
            idea="Do not hide a saved handoff behind a missing evidence row.",
            workspace_path=sample_workspace("persisted-final-report"),
            status="handoff_ready",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json={
                "summary_markdown": "Ready for review.",
                "how_to_run": ["python -m pytest tests/test_manager.py -q"],
                "tests_builds_run": ["passed: python -m pytest tests/test_manager.py -q"],
                "known_limitations": ["One follow-up remains."],
                "confidence_level": "high",
                "dry_run": False,
            },
        )
        db.add(project)
        db.flush()

        handoff = service.get_project_handoff_summary(db, project)

        assert handoff["status"] == "ready"
        assert handoff["tests_count"] == 1
        assert handoff["run_instruction_count"] == 1
        assert handoff["evidence_backed"] is True
    finally:
        db.close()


def test_maybe_finalize_handoff_creates_evidence_backed_record(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db
    from models import EvidenceBasedHandoff

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerHandoff(
                summary_markdown="Evidence-backed handoff ready.",
                what_was_built=["Completed the bounded backend updates."],
                how_to_run=["python -m pytest tests/test_manager.py -q"],
                how_to_use=["Review the saved handoff and run the focused validation command."],
                tests_builds_run=["python -m pytest tests/test_manager.py -q"],
                known_limitations=[],
                remaining_risks=[],
                suggested_next_improvements=[],
            ),
            "deterministic",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Finalize Evidence Handoff",
            idea="Generate a persisted evidence-backed handoff on finalization.",
            workspace_path=sample_workspace("finalize-evidence-handoff"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        manager_agent = Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path)
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="waiting", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Finish implementation",
            goal="Complete the scoped work.",
            scope="Stay narrow.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest tests/test_manager.py -q"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="dry_run",
            process_ref="dry-test",
            status="done",
            finished_at=project.created_at,
            report_json={
                "agent": worker.name,
                "task_id": str(task.id),
                "status": "done",
                "summary": "Completed the scoped work.",
                "files_changed": ["src/app.py"],
                "tests_run": ["python -m pytest tests/test_manager.py -q"],
                "blockers": [],
                "risks": [],
                "recommended_next_task": "Prepare the handoff.",
            },
            effective_settings_json={"provider": "codex", "model": "test-model"},
            exit_code=0,
        )
        db.add(run)
        db.flush()

        asyncio.run(service._maybe_finalize_handoff(db, project))

        db.flush()
        db.refresh(project)
        handoff_rows = db.query(EvidenceBasedHandoff).filter(EvidenceBasedHandoff.project_id == project.id).all()

        assert project.status == "handoff_ready"
        assert project.handoff_status in {"ready", "needs_review"}
        assert project.final_report_json is not None
        assert handoff_rows
    finally:
        db.close()


def test_derived_handoff_evidence_preview_skips_blank_run_history() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Handoff Noise Filter",
            idea="Do not treat blank stopped runs as evidence.",
            workspace_path=sample_workspace("handoff-noise-filter"),
            status="building",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="waiting", workspace_path=project.workspace_path)
        task = Task(
            project_id=project.id,
            title="Finish the scoped change",
            goal="Generate one real handoff signal.",
            scope="Backend only.",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest tests/test_manager.py -q"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()
        blank_run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="codex_cli",
            process_ref="blank-run",
            status="stopped",
            report_json={},
        )
        meaningful_run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="codex_cli",
            process_ref="meaningful-run",
            status="done",
            exit_code=0,
            report_json={
                "summary": "Implemented the scoped fix.",
                "files_changed": ["apps/server/src/manager.py"],
                "tests_run": ["python -m pytest tests/test_manager.py -q"],
                "blockers": [],
                "risks": [],
            },
        )
        db.add_all([blank_run, meaningful_run])
        db.flush()

        preview = service._derive_handoff_evidence_preview(db, project)

        assert preview
        assert {item["derived_from_run_id"] for item in preview} == {meaningful_run.id}
        assert all("blank-run" not in str(item.get("source_path") or "") for item in preview)
    finally:
        db.close()


def test_generate_tasks_uses_follow_up_change_request_for_handoff_ready_existing_repo(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    captured: dict[str, object] = {}

    async def fake_resolve_manager_model(*args, **kwargs):
        captured["requested_change_requests"] = kwargs["payload"]["requested_change_requests"]
        return (
            ManagerTaskDecomposition(
                summary_markdown="Reopen the imported repo for the new follow-up scope.",
                milestones=["Follow-up batch"],
                tasks=[
                    ManagerTaskItem(
                        title="Implement the follow-up scope",
                        goal="Ship the new requested change safely.",
                        scope="Touch only the reopened follow-up paths.",
                        agent_role="Primary implementation",
                        milestone="Follow-up batch",
                        allowed_paths=["apps/server/src"],
                        forbidden_paths=["apps/dashboard"],
                        validation_steps=["python -m pytest apps/server/tests/test_manager.py -q"],
                        success_criteria=["The reopened scope is represented by a fresh backlog task."],
                        estimated_complexity="small",
                        priority=15,
                    )
                ]
            ),
            "deterministic",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Follow Up Existing Repo",
            idea="Reopen a completed imported repo from a fresh change request.",
            workspace_path=sample_workspace("follow-up-existing-repo"),
            source_type="existing_folder",
            status="handoff_ready",
            handoff_status="ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json={"summary_markdown": "Old handoff"},
        )
        db.add(project)
        db.flush()
        plan = Plan(
            project_id=project.id,
            version=1,
            content_markdown="Initial imported-repo plan.",
            status="approved",
            summary_json={"milestones": ["Initial scope"]},
        )
        completed_task = Task(
            project_id=project.id,
            title="Old completed task",
            goal="Finish the original imported-repo scope.",
            scope="Legacy completed scope.",
            agent_role="Primary implementation",
            milestone="Initial batch",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Original scope shipped."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add_all([plan, completed_task])
        db.flush()
        completed_task.updated_at = project.created_at
        request = ChangeRequest(
            project_id=project.id,
            request_text="Add a fresh follow-up feature to the imported repo.",
            classification="feature",
            impact_estimate="medium",
            status="pending",
        )
        db.add(request)
        db.commit()

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        db.refresh(project)
        db.refresh(request)
        assert manager_mode_used == "deterministic"
        assert len(tasks) == 1
        assert tasks[0].title == "Implement the follow-up scope"
        assert tasks[0].status == "backlog"
        assert project.status == "building"
        assert project.handoff_status == "not_ready"
        assert project.final_report_json is None
        assert captured["requested_change_requests"] == [
            {
                "id": request.id,
                "request_text": request.request_text,
                "classification": request.classification,
                "impact_estimate": request.impact_estimate,
                "status": request.status,
            }
        ]
    finally:
        db.close()


def test_generate_tasks_keeps_standing_change_request_for_active_existing_repo_campaign(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    captured: dict[str, object] = {}

    async def fake_resolve_manager_model(*args, **kwargs):
        captured["requested_change_requests"] = kwargs["payload"]["requested_change_requests"]
        return (
            ManagerTaskDecomposition(
                summary_markdown="Reopen the imported repo from the standing campaign request.",
                milestones=["Next bounded batch"],
                tasks=[
                    ManagerTaskItem(
                        title="Open next bounded repo-analysis batch",
                        goal="Continue the standing imported-repo repair campaign.",
                        scope="Only the next evidence-backed slice.",
                        agent_role="execution_planner",
                        milestone="Next bounded batch",
                        allowed_paths=["apps/server/src", "docs"],
                        forbidden_paths=["apps/dashboard"],
                        validation_steps=["python -m pytest apps/server/tests/test_manager.py -q"],
                        success_criteria=["A fresh backlog task exists for the still-active campaign."],
                        estimated_complexity="small",
                        priority=15,
                    )
                ],
            ),
            "deterministic",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Standing Existing Repo Campaign",
            idea="Keep fixing the imported repo until the standing campaign is actually done.",
            workspace_path=sample_workspace("standing-existing-repo-campaign"),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        plan = Plan(
            project_id=project.id,
            version=1,
            content_markdown="Original imported-repo campaign plan.",
            status="approved",
            summary_json={"milestones": ["Campaign"]},
        )
        completed_task = Task(
            project_id=project.id,
            title="Previously completed bounded fix batch",
            goal="Finish the earlier bounded repair slice.",
            scope="Legacy completed scope.",
            agent_role="Primary implementation",
            milestone="Earlier batch",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Earlier batch shipped."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        request = ChangeRequest(
            project_id=project.id,
            request_text="Find and fix more real bugs in the imported repo until the campaign is actually complete.",
            classification="bugfix",
            impact_estimate="large",
            status="triaged",
        )
        db.add_all([plan, completed_task, request])
        db.flush()
        completed_task.updated_at = project.created_at + timedelta(minutes=10)
        request.updated_at = project.created_at
        db.flush()

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        assert manager_mode_used == "deterministic"
        assert len(tasks) == 1
        assert tasks[0].title == "Open next bounded repo-analysis batch"
        assert tasks[0].status == "backlog"
        assert captured["requested_change_requests"] == [
            {
                "id": request.id,
                "request_text": request.request_text,
                "classification": request.classification,
                "impact_estimate": request.impact_estimate,
                "status": request.status,
            }
        ]
    finally:
        db.close()


def test_generate_tasks_reopens_completed_title_for_standing_existing_repo_campaign(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerTaskDecomposition(
                summary_markdown="Reopen the same bounded title as a fresh runnable batch.",
                milestones=["Next bounded batch"],
                tasks=[
                    ManagerTaskItem(
                        title="Open next bounded repo-analysis batch",
                        goal="Continue the standing imported-repo repair campaign.",
                        scope="Only the next evidence-backed slice.",
                        agent_role="execution_planner",
                        milestone="Next bounded batch",
                        allowed_paths=["apps/server/src", "docs"],
                        forbidden_paths=["apps/dashboard"],
                        validation_steps=["python -m pytest apps/server/tests/test_manager.py -q"],
                        success_criteria=["The previously completed title is reopened as runnable backlog."],
                        estimated_complexity="small",
                        priority=15,
                    )
                ],
            ),
            "deterministic",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Reopen Completed Title Campaign",
            idea="Do not fake a reopened batch by leaving the matching title done.",
            workspace_path=sample_workspace("reopen-completed-title-campaign"),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        plan = Plan(
            project_id=project.id,
            version=1,
            content_markdown="Original imported-repo campaign plan.",
            status="approved",
            summary_json={"milestones": ["Campaign"]},
        )
        stale_worker = Agent(
            id=123,
            project_id=project.id,
            name="Legacy Execution Planner",
            role="execution_planner",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        completed_task = Task(
            project_id=project.id,
            title="Open next bounded repo-analysis batch",
            goal="Finish the earlier bounded repair slice.",
            scope="Legacy completed scope.",
            agent_role="execution_planner",
            milestone="Earlier batch",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Earlier batch shipped."],
            estimated_complexity="small",
            dependencies_json=[999],
            status="done",
            priority=10,
            assigned_agent_id=123,
            waiting_reason="stale",
            failure_count=2,
        )
        request = ChangeRequest(
            project_id=project.id,
            request_text="Keep the repo-analysis and bug-fix campaign going until the user says stop.",
            classification="bugfix",
            impact_estimate="large",
            status="triaged",
        )
        db.add_all([plan, stale_worker, completed_task, request])
        db.flush()

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        assert manager_mode_used == "deterministic"
        assert len(tasks) == 1
        reopened = tasks[0]
        assert reopened.id == completed_task.id
        assert reopened.status == "backlog"
        assert reopened.goal == "Continue the standing imported-repo repair campaign."
        assert reopened.scope == "Only the next evidence-backed slice."
        assert reopened.assigned_agent_id is None
        assert reopened.waiting_reason is None
        assert reopened.failure_count == 0
        assert reopened.dependencies_json == []
    finally:
        db.close()


def test_generate_tasks_replenishes_existing_repo_campaign_before_total_idle(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    captured: dict[str, object] = {}

    async def fake_resolve_manager_model(*args, **kwargs):
        captured["requested_change_requests"] = kwargs["payload"]["requested_change_requests"]
        captured["current_productive_open_task_count"] = kwargs["payload"]["current_productive_open_task_count"]
        captured["target_parallel_task_count"] = kwargs["payload"]["target_parallel_task_count"]
        return (
            ManagerTaskDecomposition(
                summary_markdown="Replenish the campaign backlog before the swarm collapses into one lonely lane.",
                milestones=["Next bounded batch"],
                tasks=[
                    ManagerTaskItem(
                        title="Open next bounded repo-analysis batch",
                        goal="Continue the standing imported-repo repair campaign.",
                        scope="Only the next evidence-backed slice.",
                        agent_role="execution_planner",
                        milestone="Next bounded batch",
                        allowed_paths=["apps/server/src", "docs"],
                        forbidden_paths=["apps/dashboard"],
                        validation_steps=["python -m pytest apps/server/tests/test_manager.py -q"],
                        success_criteria=["The completed batch title is reopened while other work is still in flight."],
                        estimated_complexity="small",
                        priority=15,
                    )
                ],
            ),
            "deterministic",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
    monkeypatch.setattr("manager.recommended_swarm_max_agents", lambda: 5)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Underfilled Existing Repo Campaign",
            idea="Keep the imported repo repair campaign moving instead of waiting for total silence.",
            workspace_path=sample_workspace("underfilled-existing-repo-campaign"),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        prefs = service._ensure_swarm_preferences(db, project)
        prefs.max_agents = 5
        prefs.swarm_aggressiveness = "medium"
        plan = Plan(
            project_id=project.id,
            version=1,
            content_markdown="Original imported-repo campaign plan.",
            status="approved",
            summary_json={"milestones": ["Campaign"]},
        )
        completed_task = Task(
            project_id=project.id,
            title="Open next bounded repo-analysis batch",
            goal="Finish the earlier bounded repair slice.",
            scope="Legacy completed scope.",
            agent_role="execution_planner",
            milestone="Earlier batch",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Earlier batch shipped."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        in_flight_task = Task(
            project_id=project.id,
            title="Current bounded fix batch",
            goal="Keep one active lane moving.",
            scope="A single active batch should not suppress the rest of the swarm.",
            agent_role="Service Flow Builder",
            milestone="Current batch",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Current lane still runs."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=5,
        )
        blocked_by_dependency = Task(
            project_id=project.id,
            title="Future batch waiting on a dependency",
            goal="Do not count dependency-blocked work as real parallel capacity.",
            scope="This exists only to prove the productive-open-task counter is not fake.",
            agent_role="Validation Specialist",
            milestone="Later batch",
            allowed_paths_json=["tests"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Dependency gating is respected."],
            estimated_complexity="small",
            dependencies_json=[999999],
            status="backlog",
            priority=20,
        )
        request = ChangeRequest(
            project_id=project.id,
            request_text="Continue the imported-repo bug-fix campaign with more bounded parallel batches instead of waiting for the last lane to finish.",
            classification="bugfix",
            impact_estimate="large",
            status="triaged",
        )
        db.add_all([plan, completed_task, in_flight_task, blocked_by_dependency, request])
        db.flush()
        in_flight_task.updated_at = project.created_at + timedelta(minutes=5)
        request.updated_at = project.created_at + timedelta(minutes=10)
        db.commit()

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        assert manager_mode_used == "deterministic"
        reopened = next(task for task in tasks if task.title == "Open next bounded repo-analysis batch")
        assert reopened.id == completed_task.id
        assert reopened.status == "backlog"
        assert reopened.waiting_reason is None
        assert reopened.failure_count == 0
        assert captured["current_productive_open_task_count"] == 1
        assert captured["target_parallel_task_count"] == 5
        assert captured["requested_change_requests"] == [
            {
                "id": request.id,
                "request_text": request.request_text,
                "classification": request.classification,
                "impact_estimate": request.impact_estimate,
                "status": request.status,
            }
        ]
    finally:
        db.close()


def test_generate_tasks_fresh_benchmark_reset_supersedes_stale_open_lanes(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerTaskDecomposition(
                summary_markdown="Reset the stale benchmark backlog and reopen fresh product-code lanes.",
                milestones=["Fresh benchmark reset"],
                tasks=[
                    ManagerTaskItem(
                        title="Fresh product-code benchmark lane",
                        goal="Start a fresh bounded benchmark lane on real product code.",
                        scope="Only the newly regenerated product-code lane.",
                        agent_role="Service Flow Builder",
                        milestone="Fresh benchmark reset",
                        allowed_paths=["apps/server/src"],
                        forbidden_paths=["docs", ".github"],
                        validation_steps=["python -m pytest apps/server/tests/test_manager.py -q"],
                        success_criteria=["The fresh benchmark request owns the new runnable lane."],
                        estimated_complexity="small",
                        priority=10,
                    )
                ],
            ),
            "deterministic",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Fresh Benchmark Reset Campaign",
            idea="Do not let stale backlog lanes survive a fresh benchmark reset.",
            workspace_path=sample_workspace("fresh-benchmark-reset-campaign"),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        plan = Plan(
            project_id=project.id,
            version=1,
            content_markdown="Original repo campaign plan.",
            status="approved",
            summary_json={"milestones": ["Campaign"]},
        )
        stale_backlog = Task(
            project_id=project.id,
            title="Github Defect Batch",
            goal="Legacy hidden-config lane.",
            scope="Old stale lane.",
            agent_role="Execution Planner",
            milestone="Legacy batch",
            allowed_paths_json=[".github"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Legacy lane stays open."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=30,
        )
        stale_waiting = Task(
            project_id=project.id,
            title="Claude Defect Batch",
            goal="Another stale lane that should be retired.",
            scope="Old stale lane.",
            agent_role="Execution Planner",
            milestone="Legacy batch",
            allowed_paths_json=[".claude"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Legacy lane stays open."],
            estimated_complexity="small",
            dependencies_json=[],
            status="waiting_on_paths",
            waiting_reason="Legacy overlap.",
            priority=31,
        )
        active_lane = Task(
            project_id=project.id,
            title="Active validation lane",
            goal="Old-version live work must not survive a fresh benchmark reset.",
            scope="Stale live work should be cancelled at a benchmark version boundary.",
            agent_role="Validation Specialist",
            milestone="Current batch",
            allowed_paths_json=["tests"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["The active lane remains working."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=5,
        )
        stale_done = Task(
            project_id=project.id,
            title="Old Completed Benchmark Lane",
            goal="Previously completed work from an older Mission Control version.",
            scope="Old stale completed lane.",
            agent_role="Execution Planner",
            milestone="Legacy batch",
            allowed_paths_json=["old"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Old lane stays countable."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=32,
        )
        request = ChangeRequest(
            project_id=project.id,
            request_text="Fresh benchmark reset after Mission Control runtime update. Start from zero, ignore prior counts, and regenerate real product-code lanes.",
            classification="bugfix",
            impact_estimate="large",
            status="new",
        )
        db.add_all([plan, stale_backlog, stale_waiting, active_lane, stale_done, request])
        db.flush()
        stale_worker = Agent(
            project_id=project.id,
            name="Stale Spark Worker",
            role="Validation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            current_task_id=active_lane.id,
            current_action=active_lane.title,
            session_ref="old-session",
            active_usage_json={"input_tokens": 123456},
            active_model="gpt-5.3-codex-spark",
            active_runner_type="codex_cli",
            locked_paths_json=["tests"],
        )
        db.add(stale_worker)
        db.flush()
        active_lane.assigned_agent_id = stale_worker.id
        db.commit()

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        db.refresh(stale_backlog)
        db.refresh(stale_waiting)
        db.refresh(active_lane)
        db.refresh(stale_done)
        db.refresh(stale_worker)
        assert manager_mode_used == "deterministic"
        assert [task.title for task in tasks] == ["Fresh product-code benchmark lane"]
        assert stale_backlog.status == "superseded"
        assert stale_backlog.assigned_agent_id is None
        assert stale_backlog.waiting_reason == "Superseded by a fresh benchmark reset request."
        assert stale_waiting.status == "superseded"
        assert stale_waiting.waiting_reason == "Superseded by a fresh benchmark reset request."
        assert active_lane.status == "superseded"
        assert active_lane.assigned_agent_id is None
        assert active_lane.waiting_reason == "Superseded by a fresh benchmark reset request."
        assert stale_done.status == "superseded"
        assert stale_done.waiting_reason == "Superseded by a fresh benchmark reset request."
        assert stale_worker.status == "waiting"
        assert stale_worker.current_task_id is None
        assert stale_worker.session_ref is None
        assert stale_worker.active_usage_json is None
        assert stale_worker.active_model is None
        assert stale_worker.active_runner_type is None
        assert stale_worker.locked_paths_json == []
    finally:
        db.close()


def test_generate_tasks_fresh_benchmark_reset_reopens_retained_review_lane(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerTaskDecomposition(
                summary_markdown="Reopen the retained benchmark lane from review back to backlog.",
                milestones=["Fresh benchmark reset"],
                tasks=[
                    ManagerTaskItem(
                        title="Apps Mcp Server Defect Batch",
                        goal="Restart the retained subsystem lane from a clean benchmark reset state.",
                        scope="Only the retained apps/mcp-server lane.",
                        agent_role="Apps Mcp Server Subsystem Builder",
                        milestone="Fresh benchmark reset",
                        allowed_paths=["apps/mcp-server"],
                        forbidden_paths=["docs", ".github"],
                        validation_steps=["python -m pytest apps/server/tests/test_manager.py -q"],
                        success_criteria=["The retained review lane is reopened as backlog with no stale assignment or review debt."],
                        estimated_complexity="small",
                        priority=10,
                    )
                ],
            ),
            "deterministic",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Fresh Benchmark Reset Retained Review Lane",
            idea="Do not carry retained review debt into a fresh benchmark reset.",
            workspace_path=sample_workspace("fresh-benchmark-retained-review-lane"),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Apps Mcp Server Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
            current_task_id=None,
        )
        review_lane = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Apps Mcp Server Defect Batch",
            goal="Old retained lane that should be reopened.",
            scope="Old retained review lane.",
            agent_role="Apps Mcp Server Subsystem Builder",
            milestone="Previous batch",
            allowed_paths_json=["apps/mcp-server"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Legacy retained lane stays stuck in review."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            waiting_reason="Runner completion envelope validation failed.",
            failure_count=2,
            priority=20,
        )
        request = ChangeRequest(
            project_id=project.id,
            request_text="Fresh benchmark reset after Mission Control runtime update. Start from zero, ignore prior counts, and regenerate real product-code lanes.",
            classification="bugfix",
            impact_estimate="large",
            status="new",
        )
        db.add_all([worker, review_lane, request])
        db.commit()

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        db.refresh(worker)
        db.refresh(review_lane)
        assert manager_mode_used == "deterministic"
        assert [task.title for task in tasks] == ["Apps Mcp Server Defect Batch"]
        assert review_lane.status == "backlog"
        assert review_lane.assigned_agent_id is None
        assert review_lane.waiting_reason is None
        assert review_lane.failure_count == 0
        assert worker.current_task_id is None
    finally:
        db.close()


def test_generate_tasks_fresh_benchmark_reset_is_consumed_after_first_pass(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerTaskDecomposition(
                summary_markdown="Keep the current benchmark lane alive without replaying the reset.",
                milestones=["Fresh benchmark reset"],
                tasks=[
                    ManagerTaskItem(
                        title="Fresh product-code benchmark lane",
                        goal="Run the fresh benchmark lane once and preserve its progress.",
                        scope="Single retained benchmark lane.",
                        agent_role="Apps Server Subsystem Builder",
                        milestone="Fresh benchmark reset",
                        allowed_paths=["apps/server"],
                        forbidden_paths=["docs"],
                        validation_steps=["python -m pytest apps/server/tests/test_manager.py -q"],
                        success_criteria=["The same reset request does not keep re-zeroing active work."],
                        estimated_complexity="small",
                        priority=10,
                    )
                ],
            ),
            "deterministic",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Fresh Benchmark Reset Is Consumed",
            idea="Do not replay the same benchmark reset on every manager turn.",
            workspace_path=sample_workspace("fresh-benchmark-reset-consumed-once"),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        active_lane = Task(
            project_id=project.id,
            title="Fresh product-code benchmark lane",
            goal="Currently running fresh benchmark lane.",
            scope="Live lane should survive follow-up manager turns.",
            agent_role="Apps Server Subsystem Builder",
            milestone="Fresh benchmark reset",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=["docs"],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["The active lane stays working after the reset is consumed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        request = ChangeRequest(
            project_id=project.id,
            request_text="Fresh benchmark reset after Mission Control runtime update. Start from zero, ignore prior counts, and regenerate real product-code lanes.",
            classification="bugfix",
            impact_estimate="large",
            status="new",
        )
        db.add_all([active_lane, request])
        db.commit()

        first_tasks, first_manager_mode_used = asyncio.run(service.generate_tasks(db, project))
        db.refresh(active_lane)
        db.refresh(request)

        assert active_lane.status == "backlog"
        assert active_lane.waiting_reason is None

        active_lane.status = "working"
        active_lane.waiting_reason = None
        db.commit()

        second_tasks, second_manager_mode_used = asyncio.run(service.generate_tasks(db, project))
        db.refresh(active_lane)
        db.refresh(request)

        assert first_manager_mode_used == "deterministic"
        assert second_manager_mode_used == "deterministic"
        assert [task.title for task in first_tasks] == ["Fresh product-code benchmark lane"]
        assert [task.title for task in second_tasks] == ["Fresh product-code benchmark lane"]
        assert request.status == "accepted"
        assert active_lane.failure_count == 0
        assert active_lane.assigned_agent_id is None
        assert active_lane.waiting_reason is None
        assert active_lane.status == "working"
    finally:
        db.close()


def test_generate_tasks_fresh_benchmark_reset_clears_worker_debt_and_supersedes_unblock_chain(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerTaskDecomposition(
                summary_markdown="Restart the product-code benchmark lanes from clean state.",
                milestones=["Fresh benchmark reset"],
                tasks=[
                    ManagerTaskItem(
                        title="Apps Server Defect Batch",
                        goal="Restart the apps/server lane from zero.",
                        scope="Server-only benchmark lane.",
                        agent_role="Apps Server Subsystem Builder",
                        milestone="Fresh benchmark reset",
                        allowed_paths=["apps/server"],
                        forbidden_paths=["docs"],
                        validation_steps=["python -m pytest apps/server/tests/test_manager.py -q"],
                        success_criteria=["The retained apps/server lane is reopened cleanly."],
                        estimated_complexity="small",
                        priority=10,
                    )
                ],
            ),
            "deterministic",
        )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Fresh Benchmark Reset Clears Worker Debt",
            idea="A real reset should not keep stale worker failure debt or unblock-chain garbage.",
            workspace_path=sample_workspace("fresh-benchmark-reset-clears-worker-debt"),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Apps Server Subsystem Builder",
            role="Feature specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            current_task_id=None,
            failure_count=7,
            current_action="Old failing run",
            last_report_summary="usage limit",
        )
        retained_lane = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Apps Server Defect Batch",
            goal="Old retained lane.",
            scope="Old lane.",
            agent_role="Apps Server Subsystem Builder",
            milestone="Previous batch",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Old retained lane."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            waiting_reason="Old blocker",
            failure_count=3,
            priority=10,
        )
        unblock_lane = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Unblock: Apps Server Defect Batch",
            goal="Old unblock chain that should die on reset.",
            scope="Old unblock lane.",
            agent_role="Apps Server Subsystem Builder",
            milestone="Previous batch",
            allowed_paths_json=["apps/server"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Old unblock lane."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            waiting_reason="Old unblocker",
            failure_count=2,
            priority=11,
        )
        db.add_all([worker, retained_lane, unblock_lane])
        db.flush()
        worker.current_task_id = retained_lane.id
        run = AgentRun(
            agent_id=worker.id,
            task_id=retained_lane.id,
            runner_type="codex_cli",
            process_ref="stale-run",
            status="working",
        )
        request = ChangeRequest(
            project_id=project.id,
            request_text="Fresh benchmark reset after Mission Control runtime update. Start from zero, ignore prior counts, and regenerate real product-code lanes.",
            classification="bugfix",
            impact_estimate="large",
            status="new",
        )
        db.add_all([run, request])
        db.commit()

        stopped_agents: list[int] = []

        async def fake_stop_agent(db, agent):
            stopped_agents.append(agent.id)
            service._reconcile_stopped_agent_state(db, agent, service._unfinished_runs_for_agent(db, agent.id))

        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "stop_agent", fake_stop_agent)

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        db.refresh(worker)
        db.refresh(retained_lane)
        db.refresh(unblock_lane)
        db.refresh(run)
        assert manager_mode_used == "deterministic"
        assert stopped_agents == [worker.id]
        assert [task.title for task in tasks] == ["Apps Server Defect Batch"]
        assert worker.failure_count == 0
        assert worker.current_task_id is None
        assert worker.current_action is None
        assert worker.last_report_summary is None
        assert worker.status == "waiting"
        assert retained_lane.status == "backlog"
        assert retained_lane.assigned_agent_id is None
        assert retained_lane.waiting_reason is None
        assert retained_lane.failure_count == 0
        assert unblock_lane.status == "superseded"
        assert unblock_lane.waiting_reason == "Superseded by a fresh benchmark reset request."
        assert unblock_lane.failure_count == 0
        assert run.status == "stopped"
        assert run.finished_at is not None
    finally:
        db.close()


def test_deterministic_existing_repo_bug_campaign_creates_parallel_batches(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("deterministic-bug-campaign"))
    for directory in ("apps", "docs", "scripts", "tests", "plugins", "workspace"):
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    async def fake_resolve_manager_model(*args, fallback_factory=None, **kwargs):
        assert fallback_factory is not None
        return fallback_factory(), "deterministic"

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
    monkeypatch.setattr("manager.recommended_swarm_max_agents", lambda: 5)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Deterministic Bug Campaign",
            idea="Imported existing codebase.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        prefs = service._ensure_swarm_preferences(db, project)
        prefs.max_agents = 5
        prefs.swarm_aggressiveness = "maximum"
        request = ChangeRequest(
            project_id=project.id,
            request_text="Using live codex_cli only, find and fix 100 distinct bugs in parallel batches and keep the campaign moving faster.",
            classification="bugfix",
            impact_estimate="large",
            status="triaged",
        )
        db.add(request)
        db.commit()

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        assert manager_mode_used == "deterministic"
        assert len(tasks) >= 3
        batch_tasks = [task for task in tasks if task.title.endswith("Defect Batch")]
        assert len(batch_tasks) >= 2
        assert all(task.status == "backlog" for task in batch_tasks)
        assert all(not task.dependencies_json for task in batch_tasks)
        assert len({tuple(task.allowed_paths_json) for task in batch_tasks}) == len(batch_tasks)
        assert any(task.title == "Cross-batch validation and defect ledger update" for task in tasks)
    finally:
        db.close()


def test_deterministic_bug_campaign_prefers_parallel_batches_over_existing_swarm_titles(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("bug-campaign-overrides-existing-swarm"))
    for directory in ("apps", "docs", "scripts", "tests", "plugins", "workspace"):
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("manager.recommended_swarm_max_agents", lambda: 5)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Bug Campaign With Existing Swarm",
            idea="Imported existing codebase.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        prefs = service._ensure_swarm_preferences(db, project)
        prefs.max_agents = 5
        swarm_plan = SwarmPlan(
            project_id=project.id,
            mode="balanced",
            goal="Old conservative swarm plan.",
            recommended_agent_count=4,
            max_agent_count=5,
            coordination_risk="medium",
            path_conflict_risk="medium",
            expected_bottlenecks_json=[],
            validation_strategy_json=[],
            strategy_summary="Old plan",
            approved_by_user=True,
            status="approved",
        )
        db.add(swarm_plan)
        db.flush()
        db.add_all(
            [
                SwarmAgentSpec(
                    swarm_plan_id=swarm_plan.id,
                    project_id=project.id,
                    archetype="planner",
                    name="Execution Planner",
                    mission="Old planner lane",
                    model_policy="Prefer the default worker model.",
                    toolset_json=["task_planning"],
                    allowed_paths_json=["docs"],
                    forbidden_paths_json=["apps"],
                    spawn_phase="plan_review",
                    retire_when="done",
                    priority=10,
                    iteration_budget=1,
                    status="spawned",
                ),
                SwarmAgentSpec(
                    swarm_plan_id=swarm_plan.id,
                    project_id=project.id,
                    archetype="backend",
                    name="Service Flow Builder",
                    mission="Old backend lane",
                    model_policy="Prefer the default worker model.",
                    toolset_json=["api_editing"],
                    allowed_paths_json=["apps"],
                    forbidden_paths_json=["docs"],
                    spawn_phase="build_start",
                    retire_when="done",
                    priority=20,
                    iteration_budget=1,
                    status="spawned",
                ),
            ]
        )
        request = ChangeRequest(
            project_id=project.id,
            request_text="Continue the 100-fix campaign with faster parallel defect batches across the imported repo.",
            classification="bugfix",
            impact_estimate="large",
            status="triaged",
            related_tasks_json=[],
        )
        db.add(request)
        db.commit()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        titles = [item.title for item in decomposition.tasks]
        assert any(title.endswith("Defect Batch") for title in titles)
        assert "Execution Planner" not in titles
        assert "Service Flow Builder" not in titles
        assert "Cross-batch validation and defect ledger update" in titles
    finally:
        db.close()


def test_deterministic_bug_campaign_uses_subdirectories_to_fill_more_parallel_lanes(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("bug-campaign-subdirectory-lanes"))
    for directory in (
        "apps/server",
        "apps/dashboard",
        "apps/mcp-server",
        "apps/desktop",
        ".claude/commands",
        ".codex/skills",
        ".codex-relay/inbox",
        "docs/guides",
        "scripts/tools",
        "tests/integration",
    ):
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("manager.recommended_swarm_max_agents", lambda: 6)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Bug Campaign Subdirectory Lanes",
            idea="Imported existing codebase.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        prefs = service._ensure_swarm_preferences(db, project)
        prefs.max_agents = 6
        prefs.swarm_aggressiveness = "maximum"
        request = ChangeRequest(
            project_id=project.id,
            request_text="Using live codex_cli only, find and fix 100 distinct bugs in parallel batches and keep the campaign moving faster.",
            classification="bugfix",
            impact_estimate="large",
            status="triaged",
        )
        db.add(request)
        db.commit()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        batch_paths = [tuple(task.allowed_paths) for task in decomposition.tasks if task.title.endswith("Defect Batch")]
        assert len(batch_paths) >= 5
        assert ("apps",) not in batch_paths
        assert ("docs",) not in batch_paths
        assert ("scripts",) not in batch_paths
        assert ("tests",) not in batch_paths
        assert ("apps/server",) in batch_paths
        assert ("apps/dashboard",) in batch_paths
        assert ("apps/mcp-server",) in batch_paths
        assert ("apps/desktop",) in batch_paths
        assert all(not path[0].startswith(".claude") for path in batch_paths)
        assert all(not path[0].startswith(".codex") for path in batch_paths)
    finally:
        db.close()


def test_deterministic_bug_campaign_prefers_leaf_lanes_over_large_subsystems(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("bug-campaign-leaf-lanes"))
    for directory in (
        "apps/server/src",
        "apps/server/tests",
        "apps/dashboard/src",
        "apps/dashboard/public",
        "apps/dashboard/node_modules/pkg",
        "apps/mcp-server/src",
        "apps/mcp-server/tests",
        ".github/workflows",
        ".github/ISSUE_TEMPLATE",
        "docs/guides",
        "scripts/tools",
    ):
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("manager.recommended_swarm_max_agents", lambda: 8)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Bug Campaign Leaf Lanes",
            idea="Imported existing codebase.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        prefs = service._ensure_swarm_preferences(db, project)
        prefs.max_agents = 8
        prefs.swarm_aggressiveness = "maximum"
        request = ChangeRequest(
            project_id=project.id,
            request_text="Find, deduplicate, fix, validate, and report 50 distinct bugs in parallel within 45 minutes.",
            classification="bugfix",
            impact_estimate="large",
            status="triaged",
        )
        db.add(request)
        db.commit()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        batch_paths = [tuple(task.allowed_paths) for task in decomposition.tasks if task.title.endswith("Defect Batch")]
        assert ("apps/server",) not in batch_paths
        assert ("apps/dashboard",) not in batch_paths
        assert ("apps/mcp-server",) not in batch_paths
        assert ("apps/dashboard/node_modules",) not in batch_paths
        assert ("apps/server/src",) in batch_paths
        assert ("apps/server/tests",) in batch_paths
        assert ("apps/dashboard/src",) in batch_paths
        assert ("apps/mcp-server/src",) in batch_paths
        assert (".github/workflows",) in batch_paths
        assert all("node_modules" not in path[0] for path in batch_paths)
    finally:
        db.close()


def test_fresh_bug_benchmark_reset_overrides_broad_manager_lanes(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("fresh-bug-benchmark-overrides-broad-manager-lanes"))
    for directory in (
        "apps/server/src",
        "apps/server/tests",
        "apps/dashboard/src",
        "apps/mcp-server/src",
        "apps/mcp-server/tests",
        ".github/workflows",
    ):
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerTaskDecomposition(
                summary_markdown="Broad lanes that would collapse parallelism.",
                milestones=["Fresh benchmark reset"],
                tasks=[
                    ManagerTaskItem(
                        title="Apps Server Defect Batch",
                        goal="Find defects under the whole server subtree.",
                        scope="Too broad for the benchmark swarm.",
                        agent_role="Apps Server Subsystem Builder",
                        milestone="Fresh benchmark reset",
                        allowed_paths=["apps/server"],
                        forbidden_paths=["apps/dashboard", "apps/mcp-server"],
                        validation_steps=["python -m pytest apps/server/tests -q"],
                        success_criteria=["Server defects are fixed."],
                        estimated_complexity="large",
                        priority=10,
                    )
                ],
            ),
            "manager_ai",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
    monkeypatch.setattr("manager.recommended_swarm_max_agents", lambda: 7)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Fresh Bug Benchmark Override",
            idea="Imported existing codebase.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="auto",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Fresh benchmark reset after Mission Control code changes. Reset to 0 and use parallel workers to "
                "diagnose, deduplicate, fix, validate, and report 50 distinct issues within 45 minutes."
            ),
            classification="bugfix",
            impact_estimate="large",
            status="new",
        )
        db.add(request)
        db.commit()

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        batch_paths = [tuple(task.allowed_paths_json) for task in tasks if task.title.endswith("Defect Batch")]
        assert manager_mode_used == "deterministic"
        assert ("apps/server",) not in batch_paths
        assert ("apps/server/src",) in batch_paths
        assert ("apps/server/tests",) in batch_paths
        assert ("apps/mcp-server/src",) in batch_paths
    finally:
        db.close()


def test_bug_campaign_detection_matches_benchmark_wording() -> None:
    service = MissionControlService()

    assert service._request_implies_bug_campaign(
        "Use parallel codex_cli workers to find, deduplicate, fix, validate, and report 50 distinct issues within 45 minutes."
    )
    assert not service._request_implies_bug_campaign(
        "Implement one small feature and write a short handoff."
    )


def test_initialize_build_roster_uses_defect_campaign_swarm_for_parallel_bug_benchmark(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("bug-campaign-swarm"))
    for directory in (
        "apps/server",
        "apps/dashboard",
        "apps/mcp-server",
        "apps/desktop",
        "docs/guides",
        "scripts/tools",
        "tests/integration",
    ):
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("manager.recommended_swarm_max_agents", lambda: 6)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Bug Campaign Swarm",
            idea="Imported existing codebase.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        prefs = service._ensure_swarm_preferences(db, project)
        prefs.max_agents = 6
        prefs.swarm_aggressiveness = "maximum"
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Benchmark Mission Control on this connected shadow repo. Use parallel codex_cli workers to "
                "diagnose, deduplicate by root cause, fix, validate, review, and report 50 distinct issues within 45 minutes."
            ),
            classification="bugfix",
            impact_estimate="large",
            status="triaged",
        )
        db.add(request)
        db.commit()

        workers = service.initialize_build_roster(db, project)
        plan = service._current_swarm_plan_record(db, project.id)

        assert plan is not None
        assert plan.mode == "defect_campaign"
        assert plan.recommended_agent_count == 6
        assert len(workers) == 6
        assert sum(1 for worker in workers if worker.name.endswith("Subsystem Builder")) == 5
        assert any(worker.name == "Defect Ledger Validator" for worker in workers)
    finally:
        db.close()


def test_initialize_build_roster_allows_benchmark_headroom_above_device_recommendation(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("bug-benchmark-headroom"))
    for directory in (
        "apps/server",
        "apps/dashboard",
        "apps/mcp-server",
        "apps/desktop",
        ".github/workflows",
        ".github/ISSUE_TEMPLATE",
        "Microsoft/Windows",
        "tests/integration",
    ):
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("manager.detect_performance_profile", lambda: {"lag_risk": "medium", "recommended_swarm_max_agents": 5})
    monkeypatch.setattr("manager.recommended_swarm_max_agents", lambda: 5)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Headroom",
            idea="Imported existing codebase.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        prefs = service._ensure_swarm_preferences(db, project)
        prefs.max_agents = 8
        prefs.swarm_aggressiveness = "maximum"
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Fresh benchmark reset. Start from zero and use parallel codex_cli workers to diagnose, deduplicate, "
                "fix, validate, review, and report 50 distinct issues within 45 minutes."
            ),
            classification="bugfix",
            impact_estimate="large",
            status="triaged",
        )
        db.add(request)
        db.commit()

        workers = service.initialize_build_roster(db, project)
        plan = service._current_swarm_plan_record(db, project.id)

        assert plan is not None
        assert plan.mode == "defect_campaign"
        assert plan.recommended_agent_count == 8
        assert len(workers) == 8
        assert sum(1 for worker in workers if worker.name.endswith("Subsystem Builder")) == 7
        assert any(worker.name == "Defect Ledger Validator" for worker in workers)
    finally:
        db.close()


def test_initialize_build_roster_replaces_stale_balanced_plan_for_fresh_bug_benchmark(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("bug-campaign-roster-reset"))
    for directory in ("apps/server", "apps/dashboard", "apps/mcp-server", "docs/guides", "tests/integration"):
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("manager.recommended_swarm_max_agents", lambda: 6)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Bug Campaign Roster Reset",
            idea="Imported existing codebase.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            handoff_status="not_ready",
            runner_mode="cli",
            manager_mode="deterministic",
            final_report_json=None,
        )
        db.add(project)
        db.flush()
        prefs = service._ensure_swarm_preferences(db, project)
        prefs.max_agents = 6
        prefs.swarm_aggressiveness = "maximum"
        stale_plan = SwarmPlan(
            project_id=project.id,
            mode="balanced",
            goal="Old conservative swarm plan.",
            recommended_agent_count=4,
            max_agent_count=6,
            coordination_risk="medium",
            path_conflict_risk="medium",
            expected_bottlenecks_json=[],
            validation_strategy_json=[],
            strategy_summary="Old plan",
            approved_by_user=True,
            status="approved",
        )
        db.add(stale_plan)
        db.flush()
        stale_worker = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
            swarm_plan_id=stale_plan.id,
            active_model="gpt-5.3-codex-spark",
            active_runner_type="codex_cli",
            active_usage_json={"input_tokens": 9999},
            session_ref="old-worker-session",
            locked_paths_json=["apps/server"],
        )
        db.add(stale_worker)
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Fresh benchmark reset. Use parallel codex_cli workers to diagnose, deduplicate, fix, validate, and report 50 distinct issues within 45 minutes."
            ),
            classification="bugfix",
            impact_estimate="large",
            status="triaged",
        )
        db.add(request)
        db.commit()

        workers = service.initialize_build_roster(db, project)
        plan = service._current_swarm_plan_record(db, project.id)
        active_workers = [worker for worker in workers if worker.status not in {"done", "retired"}]

        assert plan is not None
        assert plan.mode == "defect_campaign"
        assert plan.id != stale_plan.id
        assert len(active_workers) == 6
        assert any(worker.name == "Defect Ledger Validator" for worker in active_workers)
        db.refresh(stale_worker)
        assert stale_worker.status == "retired"
        assert stale_worker.active_model is None
        assert stale_worker.active_runner_type is None
        assert stale_worker.active_usage_json is None
        assert stale_worker.session_ref is None
        assert stale_worker.locked_paths_json == []
    finally:
        db.close()
