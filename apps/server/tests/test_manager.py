from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import sample_workspace
from config import DEFAULT_CLI_MODEL
from codex_runner.base import BaseCodexRunner
from codex_runner.base import RunnerHandle
from codex_runner.external_adapter_runner import ExternalAdapterRunner
from db import SessionLocal
from main import service as app_service
from manager import MissionControlService, STALE_BLOCKED_REQUEUE_REASON
from models import Agent, AgentExecutionTrace, AgentRun, ChangeRequest, OrchestrationSession, PathReservation, Plan, Project, ProjectEvent, RecoveryPlan, SwarmAgentSpec, SwarmPlan, Task
from project_settings import (
    DEFAULT_CODEX_WORKER_MODEL,
    ResolvedRunSettings,
    get_or_create_project_settings,
    resolve_manager_settings,
    resolve_worker_settings,
)
from schemas import (
    ManagerDocFile,
    ManagerDocUpdate,
    ManagerHandoff,
    ManagerTaskDecomposition,
    ManagerTaskItem,
    ManagerWorkerDecision,
    ProjectSettingsUpdate,
    RunnerResultEdit,
    RunnerResultEnvelope,
    RunnerResultEvidence,
    WorkerReport,
)
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


def test_remote_execution_request_state_loads_latest_governed_dispatch_bundle(tmp_path) -> None:
    service = MissionControlService()
    workspace = tmp_path / "remote-exec-request-state"
    request_root = workspace / "artifacts" / "remote-execution-requests" / "remote-exec-1700000000001"
    request_root.mkdir(parents=True)
    (request_root / "execution-request.json").write_text(
        json.dumps(
            {
                "request_id": "remote-exec-1700000000001",
                "request_status": "ready",
                "target_id": "gpu-box",
                "selected_target_id": "gpu-box",
                "selected_target_probe_status": "ready",
                "availability_diagnostics": {
                    "summary": "Broker target `gpu-box` is ready for governed execution.",
                    "candidate_count": 1,
                    "eligible_target_count": 1,
                    "ready_candidate_count": 1,
                    "notes": [],
                    "blocking_reasons": [],
                },
                "selected_target_requirement_gaps": {},
                "selected_target_rejected_reasons": [],
                "required_runner_family": "external_adapter",
                "transport": "tailscale_ssh",
                "host": "gpu-box.tailnet.ts.net",
                "remote_workspace_root": "/srv/shadow",
                "adapter_command": "python3",
                "command_preview": "tailscale ssh gpu-box python3 /opt/mission-control/adapter.py",
                "approval_required": True,
                "approval_id": 77,
                "approval_status": "approved_once",
                "dry_run": False,
                "write_intent": True,
                "adapter_contract_status": "ready",
                "adapter_contract_count": 1,
                "selected_adapter_contract_count": 1,
                "selected_adapter_contract_ids": ["linux_cuda_contract"],
                "required_tool_adapter_families": ["python", "cuda"],
                "adapter_expected_result_formats": ["json"],
                "adapter_required_command_families": ["python", "git"],
                "selected_adapter_route_ids": ["tailscale_ssh"],
                "selected_ready_adapter_route_ids": ["tailscale_ssh"],
                "ready_route_ids": ["tailscale_ssh"],
                "selected_route_ids": ["tailscale_ssh"],
                "selected_ready_route_ids": ["tailscale_ssh"],
                "blocking_reasons": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (request_root / "approval-binding.json").write_text(
        json.dumps(
            {
                "request_id": "remote-exec-1700000000001",
                "approval_required": True,
                "approval_id": 77,
                "approval_status": "approved_once",
                "runner_ref": "remote_execution_launch:1",
                "resolved_for_execution": True,
                "launch_selected_adapter_contract_ids": ["linux_cuda_contract"],
                "launch_selected_ready_adapter_route_ids": ["tailscale_ssh"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (request_root / "result-bundle.json").write_text(
        json.dumps(
            {
                "request_id": "remote-exec-1700000000001",
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "expected_evidence_categories": ["logs", "coverage"],
                "adapter_expected_result_formats": ["json"],
                "adapter_required_command_families": ["python", "git"],
                "adapter_required_tool_families": ["python", "cuda"],
                "session_recording_required": True,
                "session_recording_enabled": True,
                "session_recording_artifact_paths": [
                    "artifacts/remote-execution-governance/session-recordings/gpu-box.cast"
                ],
                "remote_session_recording_artifact_paths": [
                    "/srv/shadow/artifacts/remote-execution-governance/session-recordings/gpu-box.cast"
                ],
                "remote_artifact_paths": ["/srv/shadow/artifacts/output.json"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (request_root / "transfer-bundle.json").write_text(
        json.dumps(
            {
                "request_id": "remote-exec-1700000000001",
                "target_id": "gpu-box",
                "request_status": "ready",
                "staged_outbound_transfer_bytes": 8,
                "staged_outbound_transfer_mb": 0.0,
                "staged_outbound_transfer_path_count": 1,
                "staged_outbound_missing_paths": [],
                "transfer_quota_status": "ready",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    project = Project(
        id=1,
        name="Remote Exec Request State",
        idea="Reload the latest governed dispatch bundle.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="cli",
        manager_mode="auto",
    )

    payload = service._remote_execution_request_state(project)

    assert payload["request_id"] == "remote-exec-1700000000001"
    assert payload["request_status"] == "ready"
    assert payload["target_id"] == "gpu-box"
    assert payload["approval_status"] == "approved_once"
    assert payload["resolved_for_execution"] is True
    assert payload["availability_diagnostics"]["candidate_count"] == 1
    assert payload["selected_target_requirement_gaps"] == {}
    assert payload["selected_target_rejected_reasons"] == []
    assert payload["execution_request_path"] == (
        "artifacts/remote-execution-requests/remote-exec-1700000000001/execution-request.json"
    )
    assert payload["result_bundle_path"] == (
        "artifacts/remote-execution-requests/remote-exec-1700000000001/result-bundle.json"
    )
    assert payload["transfer_bundle_path"] == (
        "artifacts/remote-execution-requests/remote-exec-1700000000001/transfer-bundle.json"
    )
    assert payload["remote_artifact_paths"] == ["/srv/shadow/artifacts/output.json"]
    assert payload["adapter_contract_status"] == "ready"
    assert payload["selected_adapter_contract_ids"] == ["linux_cuda_contract"]
    assert payload["required_tool_adapter_families"] == ["python", "cuda"]
    assert payload["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
    assert payload["launch_selected_adapter_contract_ids"] == ["linux_cuda_contract"]
    assert payload["adapter_result_formats"] == ["json"]
    assert payload["staged_outbound_transfer_bytes"] == 8
    assert payload["staged_outbound_transfer_path_count"] == 1
    assert payload["transfer_quota_status"] == "ready"


def test_normalize_runner_result_envelope_coerces_failed_report_status() -> None:
    service = MissionControlService()
    run = AgentRun(agent_id=1, task_id=2, runner_type="external_adapter", status="working")
    task = Task(
        project_id=1,
        title="Re-run focused validation and prepare an honest handoff",
        goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
        scope="Run the relevant checks again and prepare the handoff evidence.",
        agent_role="Validation Specialist",
        milestone="Milestone 3",
        allowed_paths_json=["tests"],
        forbidden_paths_json=[],
        validation_steps_json=["python -m pytest tests/test_bug.py -q"],
        success_criteria_json=["Validation evidence is recorded truthfully."],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=30,
    )

    envelope = service._normalize_runner_result_envelope(
        run,
        task,
        {
            "status": "failed",
            "runner_type": "external_adapter",
            "lane": "test_execution",
            "summary": "The focused validation command failed to run successfully.",
            "report": {
                "agent": "Validation Specialist",
                "task_id": "2",
                "status": "failed",
                "summary": "The focused validation command failed to run successfully.",
                "files_changed": [],
                "tests_run": ["python -m pytest tests/test_bug.py -q"],
                "blockers": ["The focused validation command failed to run successfully."],
                "risks": [],
                "recommended_next_task": "Investigate and resolve the validation failure.",
            },
            "files_changed": [],
            "tests_run": ["python -m pytest tests/test_bug.py -q"],
            "commands_attempted": ["python -m pytest tests/test_bug.py -q"],
            "evidence": [],
            "risks": [],
            "blockers": ["The focused validation command failed to run successfully."],
            "diagnostics": [],
            "approvals_requested": [],
            "recovery_plan": [],
            "edits": [],
            "failure_classification": "runner_bug",
            "needs_approval": False,
            "metadata_json": {},
        },
    )

    assert envelope.report.status == "error"
    assert envelope.status == "failed"
    assert envelope.report.tests_run == ["python -m pytest tests/test_bug.py -q"]


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
            failure_count=1,
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


def test_ingest_worker_report_marks_investigation_task_done_after_repro_evidence(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Investigation Repro Promotion",
            idea="A reproduction task that runs the failing test should advance instead of blocking the whole flow.",
            workspace_path=sample_workspace("investigation-repro-promotion"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Identify the root cause of the bug",
            goal="Determine why separability_matrix returns incorrect results for nested CompoundModels.",
            scope="astropy/modeling/separable.py, astropy/modeling/tests/test_separable.py",
            agent_role="developer",
            milestone="Identify the root cause of the bug",
            allowed_paths_json=["astropy/modeling/separable.py", "astropy/modeling/tests/test_separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Run all tests in astropy/modeling/tests/test_separable.py to confirm the bug exists."],
            success_criteria_json=["All relevant tests fail, indicating the presence of a bug."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=1,
        )
        next_task = Task(
            project_id=project.id,
            title="Generate a minimal safe patch",
            goal="Create the smallest possible code change to fix separability_matrix.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Generate the fix",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["A minimal patch is proposed."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=2,
        )
        db.add_all([worker, task, next_task])
        db.flush()
        next_task.dependencies_json = [task.id]
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        async def fake_resolve_manager_model(*args, **kwargs):
            return (
                ManagerWorkerDecision(
                    decision_type="wait",
                    summary_markdown="Wait.",
                ),
                "provider_wait",
            )

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, selected_agent, selected_task):
            started.append((selected_agent.id, selected_task.id))
            selected_agent.status = "working"
            selected_agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = selected_agent.id
            db.flush()
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary="The separability_matrix function is returning incorrect results for nested CompoundModels and needs a code fix.",
            files_changed=[],
            tests_run=["pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=["Need to understand why separability_matrix returns incorrect results for nested CompoundModels."],
            risks=[],
            recommended_next_task="Investigate the logic in astropy/modeling/separable.py and generate a minimal patch.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        db.refresh(task)
        db.refresh(next_task)

        assert task.status == "done"
        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == next_task.id
        assert started == [(worker.id, next_task.id)]
        assert next_task.status == "working"
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


def test_start_idle_agents_blocks_tasks_when_dependency_is_terminally_blocked() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Terminal Dependency Block",
            idea="Dependent validation work should stop cleanly once the implementation dependency is terminally blocked.",
            workspace_path=sample_workspace("terminal-dependency-block"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        blocked_parent = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Apply the scoped implementation fix.",
            scope="Implementation only.",
            agent_role="Backend specialist",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql/compiler.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the diff narrow."],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
        )
        terminal_follow_up = Task(
            project_id=project.id,
            title="Strategy retry: Implement the smallest safe code fix",
            goal="Retry the implementation with stricter guardrails.",
            scope="Implementation only.",
            agent_role="Backend specialist",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql/compiler.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the diff narrow."],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            waiting_reason="Manager escalated this blocked task after repeated retries.",
            priority=21,
        )
        db.add_all([blocked_parent, terminal_follow_up])
        db.flush()
        blocked_parent.waiting_reason = f"Blocked task handed off to follow-up task #{terminal_follow_up.id}."
        validation_task = Task(
            project_id=project.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Validate the implementation once the dependency completes.",
            scope="Validation only.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests/expressions", "tests/runtests.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused regression command."],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[blocked_parent.id],
            status="backlog",
            priority=30,
        )
        db.add(validation_task)
        db.commit()

        started = asyncio.run(service.start_idle_agents(db, project))

        db.refresh(validation_task)
        assert started == 0
        assert validation_task.status == "blocked"
        assert f"dependency task #{blocked_parent.id}" in (validation_task.waiting_reason or "").lower()
        assert "ended blocked" in (validation_task.waiting_reason or "").lower()
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


def test_apply_remote_execution_selection_caches_workspace_tooling(monkeypatch) -> None:
    service = MissionControlService()
    from db import init_db
    import manager as manager_module

    init_db()
    db = SessionLocal()
    try:
        workspace = Path(sample_workspace("workspace-tooling-cache"))
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "pyproject.toml").write_text("[project]\nname='workspace-tooling-cache'\n", encoding="utf-8")
        project = Project(
            name="Workspace Tooling Cache",
            idea="Avoid rescanning the same workspace tooling inventory for every worker retry.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="auto",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "ollama"
        settings.runner_mode = "auto"
        settings.model = "qwen2.5-coder:7b"
        settings.adapter_command = os.sys.executable
        settings.adapter_args_json = ["adapter.py"]
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()

        real_detect = manager_module.detect_workspace_tooling
        calls = {"count": 0}

        def fake_detect(workspace_path, *, project_name=None):
            calls["count"] += 1
            return real_detect(workspace_path, project_name=project_name)

        monkeypatch.setattr(manager_module, "detect_workspace_tooling", fake_detect)

        first = service._apply_remote_execution_selection(db, project, resolve_worker_settings(project, settings, worker))
        second = service._apply_remote_execution_selection(db, project, resolve_worker_settings(project, settings, worker))

        assert calls["count"] == 1
        assert first.remote_execution is not None
        assert second.remote_execution is not None
        assert second.remote_execution["policy"] == first.remote_execution["policy"]
    finally:
        db.close()


def test_start_agent_task_does_not_block_on_external_adapter_prompt_stdin_drain(monkeypatch) -> None:
    service = MissionControlService()
    from db import init_db

    class FakeStdin:
        def __init__(self, drain_released: asyncio.Event, stdin_closed: asyncio.Event) -> None:
            self.buffer = bytearray()
            self.closed = False
            self._drain_released = drain_released
            self._stdin_closed = stdin_closed

        def write(self, data: bytes) -> None:
            self.buffer.extend(data)

        async def drain(self) -> None:
            await self._drain_released.wait()

        def close(self) -> None:
            self.closed = True
            self._stdin_closed.set()

    class FakeProcess:
        def __init__(self, drain_released: asyncio.Event, stdin_closed: asyncio.Event) -> None:
            self.stdin = FakeStdin(drain_released, stdin_closed)
            self.stdout = None
            self.stderr = None
            self.returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            await stdin_closed.wait()
            return (
                json.dumps(
                    {
                        "status": "completed",
                        "runner_type": "external_adapter",
                        "summary": "done",
                        "report": {
                            "agent": "Service Flow Builder",
                            "task_id": "1",
                            "status": "done",
                            "summary": "done",
                            "files_changed": [],
                            "tests_run": [],
                            "blockers": [],
                            "risks": [],
                        },
                        "edits": [],
                    }
                ).encode("utf-8"),
                b"",
            )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Adapter Drain Regression",
            idea="Keep worker launch from blocking on adapter stdin backpressure.",
            workspace_path=sample_workspace("adapter-drain-regression"),
            status="building",
            runner_mode="auto",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "ollama"
        settings.runner_mode = "auto"
        settings.model = "qwen2.5-coder:7b"
        settings.adapter_command = os.sys.executable
        settings.adapter_args_json = ["adapter.py"]

        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Return a valid retry launch without stalling the manager.",
            scope="Only touch scoped workspace files.",
            agent_role="Service Flow Builder",
            milestone="Milestone 1",
            allowed_paths_json=["apps/server/src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_manager.py -q"],
            success_criteria_json=["Worker launch returns even if adapter stdin backpressure is slow."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        drain_released = asyncio.Event()
        stdin_closed = asyncio.Event()
        runner = ExternalAdapterRunner()

        async def fake_exec(*args, **kwargs):
            return FakeProcess(drain_released, stdin_closed)

        async def fake_monitor_run(run_id: int) -> None:
            return None

        monkeypatch.setattr(runner, "handshake", lambda settings=None: asyncio.sleep(0, result=True))
        monkeypatch.setattr(runner, "_build_adapter_prompt", lambda context: "retry prompt\n" * 20000)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=runner))
        monkeypatch.setattr(service, "_monitor_run", fake_monitor_run)
        monkeypatch.setattr(service, "_apply_remote_execution_selection", lambda db, project, resolved: resolved)

        async def run_test() -> None:
            launch = asyncio.create_task(service.start_agent_task(db, project, worker, task))
            run = await asyncio.wait_for(launch, timeout=1.0)
            assert run.runner_type == "external_adapter"
            assert task.status == "working"
            assert task.assigned_agent_id == worker.id
            state = runner.runs[run.process_ref]
            assert state.stdin_writer_task is not None
            drain_released.set()
            assert state.reader_task is not None
            await state.reader_task

        asyncio.run(run_test())
    finally:
        db.close()


def test_start_agent_task_creates_remote_execution_request_before_launch(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "remote_adapter"

        def __init__(self) -> None:
            self.contexts: list[object] = []

        async def start_task(self, context):
            self.contexts.append(context)
            return RunnerHandle(
                id="remote-dispatch-run-1",
                runner_type="remote_adapter",
                logs_path="C:/logs/remote-dispatch-run-1.log",
                stdout_path="C:/logs/remote-dispatch-run-1.stdout.log",
                stderr_path="C:/logs/remote-dispatch-run-1.stderr.log",
                event_log_path="C:/logs/remote-dispatch-run-1.events.jsonl",
            )

    init_db()
    db = SessionLocal()
    try:
        workspace = Path(sample_workspace("remote-dispatch-start"))
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "README.md").write_text("demo\n", encoding="utf-8")
        (workspace / "artifacts").mkdir(exist_ok=True)
        project = Project(
            name="Remote Dispatch Start",
            idea="Atomically create a brokered execution request before the remote worker launches.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="auto",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "openai_api"
        settings.runner_mode = "auto"
        settings.remote_execution_policy_json = {
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_result_formats": ["json"],
            "required_command_families": ["python"],
            "required_toolchains": ["python3.11"],
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "require_target_workspace_root": True,
            "require_session_recording": True,
            "fallback_to_local": False,
        }
        worker = Agent(
            project_id=project.id,
            name="Remote Validation Agent",
            role="Validation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Run governed remote validation",
            goal="Launch the worker only after Mission Control binds a governed remote execution request.",
            scope="Do not edit code.",
            agent_role="Validation",
            milestone="Milestone 2",
            allowed_paths_json=["artifacts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Remote execution request is recorded before the worker starts."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
        service.upsert_remote_execution_target(
            db,
            {
                "id": "gpu-box",
                "label": "GPU Box",
                "transport": "tailscale_ssh",
                "host": "gpu-box.tailnet.ts.net",
                "ssh_user": "mike",
                "os_family": "linux",
                "workspace_root": "/srv/shadow",
                "adapter_command": "python3",
                "adapter_args": ["/opt/mission-control/adapter.py"],
                "runner_families": ["external_adapter"],
                "toolchains": ["python3.11"],
                "command_families": ["python"],
                "result_formats": ["json"],
                "trust_level": "trusted",
                "session_recording_enabled": True,
                "allowed_repo_roots": ["/srv/shadow"],
                "allowed_path_prefixes": ["artifacts"],
                "artifact_roots": ["/srv/shadow/artifacts"],
                "last_probe_status": "ready",
            },
        )
        service.build_remote_execution_launch_package_plan(
            db,
            project,
            {"allowed_paths": ["artifacts"], "dry_run": True, "write_intent": False},
        )

        fake_runner = FakeRunner()

        async def fake_monitor_run(run_id: int) -> None:
            return None

        monkeypatch.setattr(service.runners, "get_runner_for_settings", lambda resolved: asyncio.sleep(0, result=fake_runner))
        monkeypatch.setattr(service, "_monitor_run", fake_monitor_run)
        monkeypatch.setattr(
            "manager.context_pack_service.build_context_pack",
            lambda db, project, agent_id, task_id, **kwargs: {"sections": []},
        )
        monkeypatch.setattr("manager.context_pack_service.render_markdown", lambda payload: "")

        run = asyncio.run(service.start_agent_task(db, project, worker, task))

        assert run.runner_type == "remote_adapter"
        assert fake_runner.contexts
        remote_execution = fake_runner.contexts[0].settings.remote_execution
        assert remote_execution["execution_request"]["request_status"] == "ready"
        assert remote_execution["execution_request"]["target_id"] == "gpu-box"
        assert remote_execution["execution_request"]["availability_diagnostics"]["candidate_count"] == 1
        assert remote_execution["execution_request"]["selected_target_requirement_gaps"] == {}
        assert remote_execution["execution_request"]["selected_adapter_contract_ids"] == ["linux_host_runtime"]
        assert remote_execution["execution_request"]["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
        execution_request_path = workspace / remote_execution["execution_request"]["execution_request_path"]
        transfer_bundle_path = workspace / remote_execution["execution_request"]["transfer_bundle_path"]
        assert execution_request_path.exists()
        assert transfer_bundle_path.exists()
        execution_request_manifest = json.loads(execution_request_path.read_text(encoding="utf-8"))
        transfer_bundle_manifest = json.loads(transfer_bundle_path.read_text(encoding="utf-8"))
        assert execution_request_manifest["adapter_contract_status"] == "ready"
        assert execution_request_manifest["selected_adapter_contract_ids"] == ["linux_host_runtime"]
        assert execution_request_manifest["selected_ready_adapter_route_ids"] == ["tailscale_ssh"]
        assert execution_request_manifest["availability_diagnostics"]["candidate_count"] == 1
        assert execution_request_manifest["selected_target_requirement_gaps"] == {}
        assert execution_request_manifest["launched_run_id"] == run.id
        assert execution_request_manifest["launched_process_ref"] == run.process_ref
        assert execution_request_manifest["runtime_manifest_path"] == (
            f"artifacts/remote-execution-governance/runtime/{run.process_ref}-launch-manifest.json"
        )
        assert transfer_bundle_manifest["launched_run_id"] == run.id
        assert transfer_bundle_manifest["launched_process_ref"] == run.process_ref
        assert transfer_bundle_manifest["runtime_manifest_path"] == (
            f"artifacts/remote-execution-governance/runtime/{run.process_ref}-launch-manifest.json"
        )
        assert transfer_bundle_manifest["staged_outbound_transfer_bytes"] == 0
        assert transfer_bundle_manifest["transfer_quota_status"] == "not_applicable"
        db.refresh(run)
        assert run.effective_settings_json["remote_execution"]["execution_request"]["request_status"] == "ready"
        assert run.effective_settings_json["remote_execution"]["execution_request"]["target_id"] == "gpu-box"
        assert run.effective_settings_json["remote_execution"]["execution_request"]["launched_run_id"] == run.id
        assert run.effective_settings_json["remote_execution"]["execution_request"]["runtime_manifest_path"] == (
            f"artifacts/remote-execution-governance/runtime/{run.process_ref}-launch-manifest.json"
        )
        assert run.effective_settings_json["remote_execution"]["execution_request"]["transfer_bundle_path"] == (
            transfer_bundle_path.relative_to(workspace).as_posix()
        )
    finally:
        db.close()


def test_start_agent_task_rejects_remote_dispatch_when_launch_package_is_missing(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        workspace = Path(sample_workspace("remote-dispatch-missing-launch-package"))
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "README.md").write_text("demo\n", encoding="utf-8")
        (workspace / "artifacts").mkdir(exist_ok=True)
        project = Project(
            name="Remote Dispatch Missing Launch Package",
            idea="Fail fast when a remote worker launch skipped the governed launch package step.",
            workspace_path=workspace.as_posix(),
            status="building",
            runner_mode="auto",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "openai_api"
        settings.runner_mode = "auto"
        settings.remote_execution_policy_json = {
            "enabled": True,
            "preferred_target_id": "gpu-box",
            "required_runner_family": "external_adapter",
            "allowed_trust_levels": ["trusted"],
            "required_result_formats": ["json"],
            "required_command_families": ["python"],
            "required_toolchains": ["python3.11"],
            "required_repo_roots": ["/srv/shadow"],
            "required_path_prefixes": ["artifacts"],
            "require_target_workspace_root": True,
            "fallback_to_local": False,
        }
        worker = Agent(
            project_id=project.id,
            name="Remote Validation Agent",
            role="Validation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Run governed remote validation",
            goal="Reject remote launch attempts that skipped the launch package.",
            scope="Do not edit code.",
            agent_role="Validation",
            milestone="Milestone 2",
            allowed_paths_json=["artifacts"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Remote launch is rejected with a clear error."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()

        monkeypatch.setattr("remote_execution.remote_transport_client_available", lambda _transport: True)
        service.upsert_remote_execution_target(
            db,
            {
                "id": "gpu-box",
                "label": "GPU Box",
                "transport": "tailscale_ssh",
                "host": "gpu-box.tailnet.ts.net",
                "ssh_user": "mike",
                "os_family": "linux",
                "workspace_root": "/srv/shadow",
                "adapter_command": "python3",
                "runner_families": ["external_adapter"],
                "toolchains": ["python3.11"],
                "command_families": ["python"],
                "result_formats": ["json"],
                "trust_level": "trusted",
                "allowed_repo_roots": ["/srv/shadow"],
                "allowed_path_prefixes": ["artifacts"],
                "last_probe_status": "ready",
            },
        )
        monkeypatch.setattr(
            "manager.context_pack_service.build_context_pack",
            lambda db, project, agent_id, task_id, **kwargs: {"sections": []},
        )
        monkeypatch.setattr("manager.context_pack_service.render_markdown", lambda payload: "")

        with pytest.raises(ValueError, match="launch package is missing"):
            asyncio.run(service.start_agent_task(db, project, worker, task))
    finally:
        db.close()


def test_prepare_remote_execution_dispatch_surfaces_broker_gap_summary(monkeypatch) -> None:
    service = MissionControlService()
    project = Project(
        id=1,
        name="Remote Dispatch Gap Summary",
        idea="Explain why the preferred remote target is blocked instead of dumping opaque reason codes.",
        workspace_path="C:/tmp/remote-dispatch-gap-summary",
        status="building",
        runner_mode="auto",
        manager_mode="auto",
    )
    task = Task(id=1, title="Run governed remote validation")
    base_settings = ResolvedRunSettings(
        provider="openai_api",
        provider_label="OpenAI API",
        runner_mode="auto",
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        model="gpt-5.4-mini",
        reasoning_effort="medium",
        provider_endpoint=None,
        adapter_command="python3",
        adapter_args=["/opt/mission-control/adapter.py"],
        effective_model_label="gpt-5.4-mini",
        effective_reasoning_label="medium",
        remote_execution=None,
    )

    def _resolved_settings(_db, _project, _resolved):
        return ResolvedRunSettings(
            **{
                **base_settings.__dict__,
                "remote_execution": {
                    "policy": {
                        "enabled": True,
                        "required_runner_family": "external_adapter",
                        "preferred_target_id": "gpu-box",
                        "fallback_to_local": False,
                    },
                    "selection": {
                        "preflight_ready": False,
                        "blocking_reasons": ["no_eligible_device_broker_targets"],
                        "availability_diagnostics": {
                            "summary": "No brokered target satisfies the current remote execution policy.",
                            "candidate_count": 1,
                            "eligible_target_count": 0,
                            "ready_candidate_count": 0,
                            "notes": [],
                            "blocking_reasons": ["no_eligible_device_broker_targets"],
                        },
                        "candidates": [
                            {
                                "target_id": "gpu-box",
                                "selected": False,
                                "status": "blocked",
                                "requirement_gaps": {
                                    "toolchains": ["cuda12"],
                                    "trust_levels": ["trusted"],
                                },
                                "rejected_reasons": [
                                    "missing_required_toolchains",
                                    "trust_level_not_allowed",
                                ],
                            }
                        ],
                    },
                    "selected_target": {},
                },
            }
        )

    monkeypatch.setattr(service, "_apply_remote_execution_selection", _resolved_settings)

    with pytest.raises(ValueError, match="No brokered target satisfies the current remote execution policy."):
        service._prepare_remote_execution_dispatch_for_task_start(None, project, task, base_settings)

    with pytest.raises(ValueError) as excinfo:
        service._prepare_remote_execution_dispatch_for_task_start(None, project, task, base_settings)

    message = str(excinfo.value)
    assert "Target `gpu-box` is missing: toolchains=cuda12; trust_levels=trusted." in message
    assert "Blocking reasons: no_eligible_device_broker_targets." in message


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


def test_service_flow_builder_role_does_not_route_to_execution_planner() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Service Flow Routing",
            idea="Keep planner lanes away from implementation retries.",
            workspace_path=sample_workspace("service-flow-routing"),
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
        backend = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            archetype="backend",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Make the required code and docs change.",
            scope="Update the implementation paths needed for the validated failure and any directly coupled docs or release notes.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["tests", "django/conf", "docs/ref"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the change scoped."],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([planner, backend, task])
        db.commit()

        assert service._agent_task_match_score(planner, task) == 0
        assert service._agent_task_match_score(backend, task) == 100
        assert service._find_next_safe_task(db, project, planner) is None
        backend_candidate = service._find_next_safe_task(db, project, backend)
        assert backend_candidate is not None and backend_candidate.id == task.id
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


def test_manager_next_step_unwraps_nested_result_payload_from_provider(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "external_adapter"
        try_parse_json_payload = staticmethod(BaseCodexRunner.try_parse_json_payload)

        async def run_manager_turn(self, context, prompt):
            return RunnerHandle(
                id="manager-next-step-nested",
                runner_type="external_adapter",
                logs_path="C:/logs/manager-next-step-nested.log",
                stdout_path=None,
                stderr_path=None,
                event_log_path=None,
            ), {
                "item": {
                    "text": json.dumps(
                        {
                            "result": json.dumps(
                                {
                                    "decision_type": "wait",
                                    "summary_markdown": "Nested provider payload was parsed successfully.",
                                }
                            )
                        }
                    )
                }
            }

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Manager Nested Result Parsing",
            idea="Unwrap nested adapter result payloads instead of falling back.",
            workspace_path=sample_workspace("manager-nested-result"),
            status="building",
            runner_mode="auto",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "ollama"
        settings.runner_mode = "auto"
        settings.manager_model = "qwen2.5-coder:7b"
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
        events = list(db.scalars(select(ProjectEvent).where(ProjectEvent.project_id == project.id).order_by(ProjectEvent.id.asc())))

        assert decision.decision_type == "wait"
        assert decision.summary_markdown == "Nested provider payload was parsed successfully."
        assert not any(event.event_type == "manager.parse_failed" for event in events)
        assert any(event.event_type == "manager.parse_repair_attempted" for event in events)
    finally:
        db.close()


def test_manager_next_step_normalizes_near_miss_worker_decision_types(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    class FakeRunner:
        runner_type = "external_adapter"
        try_parse_json_payload = staticmethod(BaseCodexRunner.try_parse_json_payload)

        async def run_manager_turn(self, context, prompt):
            return RunnerHandle(
                id="manager-next-step-near-miss",
                runner_type="external_adapter",
                logs_path="C:/logs/manager-next-step-near-miss.log",
                stdout_path=None,
                stderr_path=None,
                event_log_path=None,
            ), {
                "item": {
                    "text": json.dumps(
                        {
                            "result": json.dumps(
                                {
                                    "decision_type": "re-run focused validation",
                                    "summary_markdown": "Resume the focused validation lane.",
                                    "task_id": 123,
                                }
                            )
                        }
                    )
                }
            }

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Manager Near Miss Decision Parsing",
            idea="Normalize near-miss worker decision types instead of falling back.",
            workspace_path=sample_workspace("manager-near-miss-decision"),
            status="building",
            runner_mode="auto",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        settings = get_or_create_project_settings(db, project)
        settings.provider = "ollama"
        settings.runner_mode = "auto"
        settings.manager_model = "qwen2.5-coder:7b"
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
        events = list(db.scalars(select(ProjectEvent).where(ProjectEvent.project_id == project.id).order_by(ProjectEvent.id.asc())))

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == 123
        assert not any(event.event_type == "manager.parse_failed" for event in events)
    finally:
        db.close()


def test_normalize_manager_worker_decision_payload_maps_reassign_and_reorder_to_assign_next_task() -> None:
    normalize = MissionControlService._normalize_manager_worker_decision_payload

    for raw_value in ("reassign_task", "reorder_tasks", "reassign task", "reorder tasks"):
        payload = {"decision_type": raw_value, "task_id": 7}
        normalized = normalize(payload)
        assert normalized is not None
        assert normalized["decision_type"] == "assign_next_task"
        assert normalized["task_id"] == 7


def test_normalize_manager_worker_decision_payload_maps_implement_fix_to_request_fix() -> None:
    normalize = MissionControlService._normalize_manager_worker_decision_payload

    normalized = normalize({"decision_type": "implement_fix", "task_id": 7})

    assert normalized is not None
    assert normalized["decision_type"] == "request_fix"
    assert normalized["task_id"] == 7


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


def test_finalize_run_normalizes_external_adapter_report_identity_before_ingest(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    captured: dict[str, object] = {}
    try:
        project = Project(
            name="External Adapter Identity Repair",
            idea="Use run metadata when a local adapter hallucinates decorative identifiers.",
            workspace_path=sample_workspace("external-adapter-identity-repair"),
            status="building",
            runner_mode="auto",
            manager_mode="auto",
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
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Reproduce the failing behavior",
            goal="Confirm the current failure honestly.",
            scope="Inspect the existing repo and record evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 1",
            allowed_paths_json=["tests"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest tests/test_example.py -q"],
            success_criteria_json=["The failure is reproduced or clearly explained."],
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
            process_ref="adapter-identity-repair",
            status="done",
            report_json={
                "agent": "Service Flow Builder",
                "task_id": "999",
                "status": "done",
                "summary": "Reproduced the failing behavior and isolated tests/example.py as the broken path.",
                "files_changed": [],
                "tests_run": ["python -m pytest tests/test_example.py -q"],
                "blockers": [],
                "risks": [],
                "recommended_next_task": "Implement the smallest safe code fix.",
            },
            result_envelope_json={
                "status": "completed",
                "runner_type": "external_adapter",
                "lane": "test_execution",
                "summary": "Reproduced the failing behavior and isolated tests/example.py as the broken path.",
                "report": {
                    "agent": "Service Flow Builder",
                    "task_id": "999",
                    "status": "done",
                    "summary": "Reproduced the failing behavior and isolated tests/example.py as the broken path.",
                    "files_changed": [],
                    "tests_run": ["python -m pytest tests/test_example.py -q"],
                    "blockers": [],
                    "risks": [],
                    "recommended_next_task": "Implement the smallest safe code fix.",
                },
                "files_changed": [],
                "tests_run": ["python -m pytest tests/test_example.py -q"],
                "commands_attempted": ["python -m pytest tests/test_example.py -q"],
                "evidence": [],
                "risks": [],
                "blockers": [],
                "diagnostics": [],
                "approvals_requested": [],
                "recovery_plan": [],
                "edits": [],
                "failure_classification": None,
                "needs_approval": False,
                "metadata_json": {},
            },
        )
        db.add(run)
        db.commit()

        monkeypatch.setattr(
            service,
            "_verify_worker_report_evidence",
            lambda project, task, report, *args, **kwargs: report,
        )
        monkeypatch.setattr(
            service,
            "_verify_worker_report_validation_claims",
            lambda project, task, report, *args, **kwargs: report,
        )
        monkeypatch.setattr(service, "_convert_no_change_review_to_blocked", lambda task, report: report)

        async def fake_ingest_worker_report(db, run, report, *, envelope=None):
            captured["report"] = report
            captured["envelope"] = envelope
            return ManagerWorkerDecision(decision_type="wait", summary_markdown="normalized")

        monkeypatch.setattr(service, "ingest_worker_report", fake_ingest_worker_report)

        asyncio.run(service._finalize_run(db, project, worker, run, "done"))

        normalized_report = captured["report"]
        assert isinstance(normalized_report, WorkerReport)
        assert normalized_report.agent == worker.name
        assert normalized_report.task_id == str(task.id)
    finally:
        db.close()


def test_finalize_run_reconciles_blocked_envelope_status_before_validation_claim_replay(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    captured: dict[str, Any] = {}
    try:
        project = Project(
            name="Blocked Envelope Replay",
            idea="Treat adapter-blocked validation runs as blocked before validation replay logic runs.",
            workspace_path=sample_workspace("blocked-envelope-replay"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation command again"],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=30,
        )
        db.add_all([worker, task])
        db.flush()
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="external_adapter",
            process_ref="adapter-validation-blocked",
            status="blocked",
            report_json={
                "agent": worker.name,
                "task_id": str(task.id),
                "status": "error",
                "summary": "Focused validation command failed with exit code 1.",
                "files_changed": [],
                "tests_run": ["python tests/runtests.py expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"],
                "blockers": ["Command execution failed with exit code 1"],
                "risks": [],
                "recommended_next_task": "Inspect the failed validation output and retry.",
            },
            result_envelope_json={
                "status": "blocked",
                "runner_type": "external_adapter",
                "lane": "test_execution",
                "summary": "The required validation command failed with exit code 1.",
                "report": {
                    "agent": worker.name,
                    "task_id": str(task.id),
                    "status": "error",
                    "summary": "Focused validation command failed with exit code 1.",
                    "files_changed": [],
                    "tests_run": ["python tests/runtests.py expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"],
                    "blockers": ["Command execution failed with exit code 1"],
                    "risks": [],
                    "recommended_next_task": "Inspect the failed validation output and retry.",
                },
                "files_changed": [],
                "tests_run": ["python tests/runtests.py expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"],
                "commands_attempted": ["python tests/runtests.py expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"],
                "evidence": [],
                "risks": [],
                "blockers": ["Command execution failed with exit code 1"],
                "diagnostics": [],
                "approvals_requested": [],
                "recovery_plan": [],
                "edits": [],
                "failure_classification": "infra_blocker",
                "needs_approval": False,
                "metadata_json": {},
            },
        )
        db.add(run)
        db.commit()

        monkeypatch.setattr(
            service,
            "_verify_worker_report_evidence",
            lambda project, task, report, *args, **kwargs: report,
        )

        def fake_verify_validation_claims(project, task, report, *args, **kwargs):
            captured["status_before_validation_replay"] = report.status
            return report

        monkeypatch.setattr(
            service,
            "_verify_worker_report_validation_claims",
            fake_verify_validation_claims,
        )
        monkeypatch.setattr(service, "_convert_no_change_review_to_blocked", lambda task, report: report)

        async def fake_ingest_worker_report(db, run, report, *, envelope=None):
            captured["status_after_finalize"] = report.status
            captured["envelope_status_after_finalize"] = envelope.status if envelope is not None else None
            return ManagerWorkerDecision(decision_type="wait", summary_markdown="normalized")

        monkeypatch.setattr(service, "ingest_worker_report", fake_ingest_worker_report)

        asyncio.run(service._finalize_run(db, project, worker, run, "blocked"))

        assert captured["status_before_validation_replay"] == "blocked"
        assert captured["status_after_finalize"] == "blocked"
        assert captured["envelope_status_after_finalize"] == "blocked"
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


def test_verify_worker_report_evidence_uses_agent_workspace_snapshot(tmp_path) -> None:
    service = MissionControlService()
    project_workspace = tmp_path / "project-repo"
    agent_workspace = tmp_path / "agent-repo"
    for workspace in (project_workspace, agent_workspace):
        (workspace / "src").mkdir(parents=True)
        (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (agent_workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    project = Project(
        name="Agent Workspace Evidence",
        idea="Fix the failing tests.",
        workspace_path=project_workspace.as_posix(),
        status="building",
        runner_mode="auto",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=project_workspace.as_posix(),
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
    before = service._task_workspace_snapshot(project, task, agent_workspace_path=project_workspace.as_posix())
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

    verified = service._verify_worker_report_evidence(
        project,
        task,
        report,
        before,
        agent_workspace_path=agent_workspace.as_posix(),
    )

    assert verified.status == "done"
    assert verified.files_changed == ["src/math_utils.py"]


def test_verify_worker_report_evidence_accepts_git_dirty_workspace_when_snapshot_delta_is_empty(tmp_path) -> None:
    service = MissionControlService()
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "math_utils.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    def run_git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )

    run_git("init")
    run_git("config", "user.email", "tests@example.com")
    run_git("config", "user.name", "Mission Control Tests")
    run_git("add", "src/math_utils.py")
    run_git("commit", "-m", "initial")

    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    project = Project(
        name="Git Evidence Demo",
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

    assert verified.status == "done"
    assert verified.files_changed == ["src/math_utils.py"]


def test_verify_worker_report_evidence_accepts_envelope_edit_claims_when_report_paths_are_empty(tmp_path) -> None:
    service = MissionControlService()
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "math_utils.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    def run_git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )

    run_git("init")
    run_git("config", "user.email", "tests@example.com")
    run_git("config", "user.name", "Mission Control Tests")
    run_git("add", "src/math_utils.py")
    run_git("commit", "-m", "initial")

    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    project = Project(
        name="Envelope Edit Evidence Demo",
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
        files_changed=[],
        tests_run=[],
        blockers=[],
        risks=[],
        recommended_next_task="Re-run focused validation",
    )
    envelope = RunnerResultEnvelope(
        status="completed",
        runner_type="dry_run",
        lane="implementation",
        summary=report.summary,
        report=report,
        files_changed=[],
        tests_run=[],
        commands_attempted=[],
        evidence=[
            RunnerResultEvidence(
                kind="file_change",
                summary="Updated the math helper implementation.",
                status="passed",
                source_path=target.as_posix(),
                command=None,
                metadata_json={},
            )
        ],
        risks=[],
        blockers=[],
        diagnostics=[],
        approvals_requested=[],
        recovery_plan=[],
        edits=[RunnerResultEdit(path="src/math_utils.py", summary="Correct the add helper.")],
        failure_classification=None,
        needs_approval=False,
        metadata_json={},
    )

    verified = service._verify_worker_report_evidence(project, task, report, before, envelope=envelope)

    assert verified.status == "done"
    assert verified.files_changed == ["src/math_utils.py"]


def test_promote_verified_partial_edit_review_marks_verified_anchor_miss_as_done() -> None:
    service = MissionControlService()
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
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="2",
        status="needs_review",
        summary="Fixed the targeted implementation change and kept the diff scoped. Mission Control rejected or could not apply one or more proposed edits.",
        files_changed=["src/math_utils.py"],
        tests_run=[],
        blockers=[],
        risks=["Rejected search/replace edit because the search text was not found in src/math_utils.py"],
        recommended_next_task="Re-run focused validation",
    )

    promoted = service._promote_verified_partial_edit_review(task, report)

    assert promoted.status == "done"
    assert promoted.blockers == []
    assert any("verified that the claimed workspace changes are already present" in item.lower() for item in promoted.risks)


def test_task_workspace_snapshot_prioritizes_non_test_paths_before_large_test_trees(tmp_path) -> None:
    service = MissionControlService()
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "tests").mkdir()
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    for index in range(260):
        (workspace / "tests" / f"test_case_{index:03d}.py").write_text("def test_case():\n    assert True\n", encoding="utf-8")

    project = Project(
        name="Snapshot Ordering",
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
        allowed_paths_json=["tests", "src"],
        forbidden_paths_json=[],
        validation_steps_json=["Keep the change scoped"],
        success_criteria_json=["The implementation is corrected"],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=20,
    )

    snapshot = service._task_workspace_snapshot(project, task)

    assert "src/math_utils.py" in snapshot


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


def test_task_expects_file_changes_is_false_for_clarify_follow_up_that_mentions_fix() -> None:
    service = MissionControlService()
    task = Task(
        project_id=1,
        title="Clarify Failing Behavior",
        goal="Inspect more files or clarify the failing behavior before proceeding with a fix.",
        scope="Resolve a blocker or error before the main flow can continue.",
        agent_role="Validation, docs, and handoff",
        milestone="Milestone 3 - Validate and hand off",
        allowed_paths_json=["astropy/modeling/tests", "astropy/modeling"],
        forbidden_paths_json=[],
        validation_steps_json=["Confirm the blocker is removed", "Record what changed"],
        success_criteria_json=["The blocking issue is resolved or clearly isolated."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=31,
    )

    assert service._task_is_exploratory_follow_up(task) is True
    assert service._task_expects_file_changes(task) is False


def test_task_expects_file_changes_is_true_for_fix_follow_up_that_mentions_validation() -> None:
    service = MissionControlService()
    task = Task(
        project_id=1,
        title="Fix multiline RawSQL ordering bug in SQLCompiler",
        goal="Implement a fix that avoids removing multiline RawSQL clauses from the order by clause and rerun validation to ensure it is resolved.",
        scope="Resolve a blocker or error before the main flow can continue.",
        agent_role="Execution Planner",
        milestone="Milestone 3 - Validate and hand off",
        allowed_paths_json=["tests/expressions", "django/db/models", "django/db/models/sql"],
        forbidden_paths_json=[],
        validation_steps_json=["Confirm the blocker is removed", "Record what changed"],
        success_criteria_json=["The blocking issue is resolved or clearly isolated."],
        estimated_complexity="small",
        dependencies_json=[],
        status="backlog",
        priority=31,
    )

    assert service._task_is_exploratory_follow_up(task) is False
    assert service._task_expects_file_changes(task) is True


def test_verify_worker_report_validation_claims_blocks_failed_implementation_rerun(monkeypatch) -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("failed-implementation-rerun"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def broken():\n    return True\n", encoding="utf-8")
    project = Project(
        id=1,
        name="Validation Claim Replay",
        idea="Do not trust a worker claim that tests passed when Mission Control can rerun the command and see that it still fails.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="dry_run",
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
        validation_steps_json=["python -m pytest tests/test_math_utils.py -q"],
        success_criteria_json=["The implementation is corrected"],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=20,
    )
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="2",
        status="done",
        summary="Fixed confirmed failing behavior with minimal changes.",
        files_changed=["src/math_utils.py"],
        tests_run=["python -m pytest tests/test_math_utils.py -q"],
        blockers=[],
        risks=[],
        recommended_next_task="Install the missing dependency and retry the task.",
    )

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=2, stdout="assert 1 == 2", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    verified = service._verify_worker_report_validation_claims(project, task, report)

    assert verified.status == "blocked"
    assert "reran the claimed validation command and it still failed" in verified.summary.lower()
    assert "exit code 2" in verified.blockers[0]
    assert verified.recommended_next_task == (
        "Inspect the failed validation output, repair the implementation, and rerun the focused validation command."
    )


def test_verify_worker_report_validation_claims_prepends_workspace_to_pythonpath(monkeypatch) -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("validation-claim-replay-pythonpath"))
    workspace.mkdir(parents=True, exist_ok=True)
    stale_path = workspace.parent / "stale-pythonpath"
    stale_path.mkdir(parents=True, exist_ok=True)
    project = Project(
        id=1,
        name="Validation Replay Environment",
        idea="Validation replay should prioritize the active workspace over stale inherited PYTHONPATH entries.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="dry_run",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=workspace.as_posix(),
    )
    task = Task(
        project_id=1,
        title="Re-run focused validation and prepare an honest handoff",
        goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
        scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
        agent_role="Validation Specialist",
        milestone="Milestone 3 - Validate and hand off",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["python -m pytest tests/test_math_utils.py -q"],
        success_criteria_json=["Validation evidence is recorded truthfully."],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=30,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="3",
        status="blocked",
        summary="The focused validation command appears blocked by a missing local dependency.",
        files_changed=[],
        tests_run=["python -m pytest tests/test_math_utils.py -q"],
        blockers=["Missing dependency: rg"],
        risks=[],
        recommended_next_task="Install ripgrep and retry the task.",
    )
    observed: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        observed["cwd"] = kwargs.get("cwd")
        observed["env"] = dict(kwargs.get("env") or {})
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setenv("PYTHONPATH", stale_path.as_posix())
    monkeypatch.setattr(subprocess, "run", fake_run)

    verified = service._verify_worker_report_validation_claims(project, task, report)

    assert verified.status == "done"
    assert Path(str(observed["cwd"])).resolve() == workspace.resolve()
    env = observed["env"]
    assert isinstance(env, dict)
    pythonpath_entries = [Path(entry).resolve() for entry in str(env.get("PYTHONPATH") or "").split(os.pathsep) if entry]
    assert pythonpath_entries[0] == workspace.resolve()
    assert stale_path.resolve() in pythonpath_entries[1:]


def test_verify_worker_report_validation_claims_blocks_unvalidated_implementation_fix() -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("unvalidated-implementation-fix"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def fixed():\n    return True\n", encoding="utf-8")
    project = Project(
        id=1,
        name="Implementation Validation Required",
        idea="Implementation fixes should not be accepted without any runnable validation command evidence.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="dry_run",
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
        validation_steps_json=["python -m pytest tests/test_math_utils.py -q"],
        success_criteria_json=["The implementation is corrected"],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=20,
    )
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

    verified = service._verify_worker_report_validation_claims(project, task, report)

    assert verified.status == "blocked"
    assert "required validation evidence" in verified.summary.lower()
    assert "required at least one explicit validation command" in verified.blockers[0].lower()


def test_verify_worker_report_validation_claims_allows_deferred_validation_when_follow_up_lane_exists() -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("deferred-validation-implementation-fix"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def fixed():\n    return True\n", encoding="utf-8")
    project = Project(
        id=1,
        name="Deferred Validation Allowed",
        idea="An implementation lane can hand validation to the downstream validator when the patch is already verified in the workspace.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="dry_run",
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
        validation_steps_json=["python -m pytest tests/test_math_utils.py -q"],
        success_criteria_json=["The implementation is corrected"],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=20,
    )
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

    verified = service._verify_worker_report_validation_claims(
        project,
        task,
        report,
        allow_deferred_validation=True,
    )

    assert verified.status == "done"
    assert verified.blockers == []


def test_verify_worker_report_validation_claims_blocks_failed_validation_handoff_rerun(monkeypatch) -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("failed-validation-handoff-rerun"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def fixed():\n    return True\n", encoding="utf-8")
    project = Project(
        id=1,
        name="Validation Handoff Replay",
        idea="Do not trust a validation lane that claims the focused rerun passed when Mission Control can replay it and see the failure.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="dry_run",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=workspace.as_posix(),
    )
    task = Task(
        project_id=1,
        title="Re-run focused validation and prepare an honest handoff",
        goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
        scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
        agent_role="Validation Specialist",
        milestone="Milestone 3 - Validate and hand off",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["python -m pytest tests/test_math_utils.py -q"],
        success_criteria_json=["Validation evidence is recorded truthfully."],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=30,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="3",
        status="done",
        summary="Focused validation passed and the handoff notes are ready.",
        files_changed=[],
        tests_run=["python -m pytest tests/test_math_utils.py -q"],
        blockers=[],
        risks=[],
        recommended_next_task="Install ripgrep and retry the task.",
    )

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="sqlite3.OperationalError: near \")\": syntax error")

    monkeypatch.setattr(subprocess, "run", fake_run)

    verified = service._verify_worker_report_validation_claims(project, task, report)

    assert verified.status == "blocked"
    assert "reran the claimed validation command and it still failed" in verified.summary.lower()
    assert "exit code 1" in verified.blockers[0]
    assert "sqlite3.OperationalError" in verified.blockers[0]
    assert verified.recommended_next_task == (
        "Inspect the failed validation output, repair the implementation, and rerun the focused validation command."
    )


def test_verify_worker_report_validation_claims_upgrades_blocked_validation_handoff_when_rerun_passes(monkeypatch) -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("successful-validation-handoff-rerun"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def fixed():\n    return True\n", encoding="utf-8")
    project = Project(
        id=1,
        name="Validation Handoff Success Replay",
        idea="A blocked validation lane should be upgraded to done when Mission Control reruns the claimed command and it succeeds.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="dry_run",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=workspace.as_posix(),
    )
    task = Task(
        project_id=1,
        title="Re-run focused validation and prepare an honest handoff",
        goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
        scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
        agent_role="Validation Specialist",
        milestone="Milestone 3 - Validate and hand off",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["python -m pytest tests/test_math_utils.py -q"],
        success_criteria_json=["Validation evidence is recorded truthfully."],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=30,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="3",
        status="blocked",
        summary="The focused validation command appears blocked by a missing local dependency.",
        files_changed=[],
        tests_run=["python -m pytest tests/test_math_utils.py -q"],
        blockers=["Missing dependency: rg"],
        risks=[],
        recommended_next_task="Install ripgrep and retry the task.",
    )

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    verified = service._verify_worker_report_validation_claims(project, task, report)

    assert verified.status == "done"
    assert "reran the claimed validation command and it passed" in verified.summary.lower()
    assert verified.blockers == []
    assert verified.recommended_next_task == "Prepare the final operator handoff."


def test_verify_worker_report_validation_claims_validation_handoff_prefers_task_command_over_worker_claim(
    monkeypatch,
) -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("validation-handoff-prefers-task-command"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def fixed():\n    return True\n", encoding="utf-8")
    project = Project(
        id=1,
        name="Validation Handoff Command Preference",
        idea="Validation replay should use the manager-defined command instead of a worker-invented detour.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="dry_run",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=workspace.as_posix(),
    )
    task = Task(
        project_id=1,
        title="Re-run focused validation and prepare an honest handoff",
        goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
        scope="Run the relevant checks again and prepare the handoff evidence.",
        agent_role="Validation Specialist",
        milestone="Milestone 3 - Validate and hand off",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["Re-run the focused validation command: python -m pytest tests/test_math_utils.py -q"],
        success_criteria_json=["Validation evidence is recorded truthfully."],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=30,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="3",
        status="done",
        summary="Focused validation passed and the handoff notes are ready.",
        files_changed=[],
        tests_run=["python manage.py test wrong.path"],
        blockers=[],
        risks=[],
        recommended_next_task="Prepare the final operator handoff.",
    )
    rerun_calls: list[str] = []

    def fake_run(command, **kwargs):
        rerun_calls.append(str(command))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    verified = service._verify_worker_report_validation_claims(project, task, report)

    assert verified.status == "done"
    assert rerun_calls == ["python -m pytest tests/test_math_utils.py -q"]


def test_verify_worker_report_validation_claims_validation_handoff_uses_project_workspace_for_replay(
    monkeypatch,
) -> None:
    service = MissionControlService()
    project_workspace = Path(sample_workspace("validation-handoff-project-workspace"))
    agent_workspace = project_workspace / "agent-shadow"
    (project_workspace / "src").mkdir(parents=True, exist_ok=True)
    (project_workspace / "src" / "math_utils.py").write_text("def fixed():\n    return True\n", encoding="utf-8")
    agent_workspace.mkdir(parents=True, exist_ok=True)
    (agent_workspace / "placeholder.txt").write_text("stale worktree\n", encoding="utf-8")
    project = Project(
        id=1,
        name="Validation Handoff Workspace Root",
        idea="Validation replay should run against the canonical project workspace.",
        workspace_path=project_workspace.as_posix(),
        status="building",
        runner_mode="dry_run",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=project_workspace.as_posix(),
    )
    task = Task(
        project_id=1,
        title="Re-run focused validation and prepare an honest handoff",
        goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
        scope="Run the relevant checks again and prepare the handoff evidence.",
        agent_role="Validation Specialist",
        milestone="Milestone 3 - Validate and hand off",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["python -m pytest tests/test_math_utils.py -q"],
        success_criteria_json=["Validation evidence is recorded truthfully."],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=30,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="3",
        status="done",
        summary="Focused validation passed and the handoff notes are ready.",
        files_changed=[],
        tests_run=["python -m pytest tests/test_math_utils.py -q"],
        blockers=[],
        risks=[],
        recommended_next_task="Prepare the final operator handoff.",
    )
    rerun_cwds: list[str] = []

    def fake_run(command, **kwargs):
        rerun_cwds.append(str(kwargs.get("cwd") or ""))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    verified = service._verify_worker_report_validation_claims(
        project,
        task,
        report,
        agent_workspace_path=agent_workspace.as_posix(),
    )

    assert verified.status == "done"
    assert [Path(cwd).resolve() for cwd in rerun_cwds] == [project_workspace.resolve()]


def test_verify_worker_report_validation_claims_replays_commands_attempted_for_blocked_validation_handoff(monkeypatch) -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("blocked-validation-handoff-commands-attempted"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def fixed():\n    return True\n", encoding="utf-8")
    project = Project(
        id=1,
        name="Validation Handoff Commands Attempted Replay",
        idea="A blocked validation lane should still be upgraded when the worker omitted tests_run but recorded the attempted validation command.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="dry_run",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=workspace.as_posix(),
    )
    task = Task(
        project_id=1,
        title="Re-run focused validation and prepare an honest handoff",
        goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
        scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
        agent_role="Validation Specialist",
        milestone="Milestone 3 - Validate and hand off",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["python -m pytest tests/test_math_utils.py -q"],
        success_criteria_json=["Validation evidence is recorded truthfully."],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=30,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="3",
        status="blocked",
        summary="Missing dependencies",
        files_changed=[],
        tests_run=[],
        blockers=["Missing dependencies"],
        risks=[],
        recommended_next_task="Install the missing dependency and retry the task.",
    )

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    verified = service._verify_worker_report_validation_claims(
        project,
        task,
        report,
        commands_attempted=["python -m pytest tests/test_math_utils.py -q"],
    )

    assert verified.status == "done"
    assert verified.tests_run == ["python -m pytest tests/test_math_utils.py -q"]
    assert "reran the claimed validation command and it passed" in verified.summary.lower()
    assert verified.blockers == []


def test_verify_worker_report_validation_claims_replays_task_validation_steps_for_blocked_validation_handoff(monkeypatch) -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("blocked-validation-handoff-task-validation-steps"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "math_utils.py").write_text("def fixed():\n    return True\n", encoding="utf-8")
    project = Project(
        id=1,
        name="Validation Handoff Task Step Replay",
        idea="A blocked validation lane should still rerun its declared validation step even when the worker forgot to echo the command.",
        workspace_path=workspace.as_posix(),
        status="building",
        runner_mode="dry_run",
        manager_mode="auto",
        source_type="existing_folder",
        source_path=workspace.as_posix(),
    )
    task = Task(
        project_id=1,
        title="Re-run focused validation and prepare an honest handoff",
        goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
        scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
        agent_role="Validation Specialist",
        milestone="Milestone 3 - Validate and hand off",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["Re-run the focused validation command: python -m pytest tests/test_math_utils.py -q"],
        success_criteria_json=["Validation evidence is recorded truthfully."],
        estimated_complexity="small",
        dependencies_json=[],
        status="working",
        priority=30,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="3",
        status="blocked",
        summary="The focused validation command appears blocked by a missing local dependency.",
        files_changed=[],
        tests_run=[],
        blockers=["Missing dependency: rg"],
        risks=[],
        recommended_next_task="Install ripgrep and retry the task.",
    )

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    verified = service._verify_worker_report_validation_claims(project, task, report)

    assert verified.status == "done"
    assert verified.tests_run == ["python -m pytest tests/test_math_utils.py -q"]
    assert "reran the claimed validation command and it passed" in verified.summary.lower()
    assert verified.blockers == []


def test_deterministic_worker_decision_creates_focused_retry_for_no_change_fix_blocker() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Focused No Change Retry",
            idea="Analysis-only blocked fix tasks should become explicit reproduce-and-edit retries.",
            workspace_path=sample_workspace("focused-no-change-retry"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Develop a patch",
            goal="Create the smallest safe code fix.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The failing tests pass."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=10,
            failure_count=0,
        )
        db.add_all([worker, task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "Unable to reproduce the reported bug in the separability_matrix function for nested models. "
                "Mission Control rejected this as a no-change review gate because the task requires verified changed files."
            ),
            files_changed=[],
            tests_run=[],
            blockers=[
                "No verified workspace file changes were produced for a task that requires a concrete fix.",
                "Cannot reproduce the behavior without additional context.",
            ],
            risks=["Mission Control could not verify any workspace file changes for this run."],
            recommended_next_task="Use the provided issue evidence and implement the smallest safe patch.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == worker.id
        assert decision.follow_up_title == "Focused retry: Develop a patch"
        assert decision.follow_up_allowed_paths == ["astropy/modeling/separable.py"]
        assert "Do not return an analysis-only report" in decision.follow_up_goal
        assert "python -m pytest astropy/modeling/tests/test_separable.py -q" in decision.follow_up_goal
        assert "do not claim the symbol only exists in a test file" in decision.follow_up_goal.lower()
    finally:
        db.close()


def test_deterministic_worker_decision_keeps_focused_retry_when_zero_edit_blocker_suggests_exact_file_path() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Focused Retry With Exact File Hint",
            idea="Zero-edit implementation blockers should still route a focused retry even when the blocker text includes a narrower repo path.",
            workspace_path=sample_workspace("focused-retry-exact-file-hint"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="django/db/models/sql/compiler.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql", "tests/expressions"],
            forbidden_paths_json=[],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=1,
        )
        db.add_all([worker, task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "Fixed the targeted implementation change and kept the diff scoped. "
                "Mission Control rejected or could not apply one or more proposed edits."
            ),
            files_changed=[],
            tests_run=[],
            blockers=[
                "No verified workspace file changes were produced for a task that requires a concrete fix.",
            ],
            risks=[
                "Rejected search/replace edit because the search text was not found in django/db/models/sql/compiler.py",
            ],
            recommended_next_task="Re-read django/db/models/sql/compiler.py and retry the focused implementation fix.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == worker.id
        assert decision.follow_up_title == "Focused retry: Implement the smallest safe code fix"
        assert decision.follow_up_allowed_paths == ["django/db/models/sql", "tests/expressions"]
        assert "search/replace anchor did not match the current workspace" in decision.follow_up_goal
        assert "copy the current workspace text exactly" in decision.follow_up_goal
        assert "do not ask for more evidence" in decision.follow_up_goal.lower()
    finally:
        db.close()


def test_deterministic_worker_decision_creates_strategy_retry_after_repeated_no_change_fix_blocker() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Strategy Retry",
            idea="Repeated blocked implementation turns should get a stricter surgical retry instead of endless requeue.",
            workspace_path=sample_workspace("strategy-retry"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="django/db/models/sql/compiler.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql", "tests/expressions"],
            forbidden_paths_json=[],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=3,
        )
        db.add_all([worker, task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "The proposed fix does not address the root cause of the issue. "
                "It only removes newline characters from SQL."
            ),
            files_changed=[],
            tests_run=[],
            blockers=["The fix only removes newline characters from SQL, which does not address the repeated ordering-clause behavior."],
            risks=[],
            recommended_next_task="Re-evaluate the proposed fix and consider an alternative approach.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == worker.id
        assert decision.follow_up_title == "Strategy retry: Implement the smallest safe code fix"
        assert decision.follow_up_allowed_paths == ["django/db/models/sql", "tests/expressions"]
        assert "search/replace style patch" in decision.follow_up_goal
        assert "Do not reject a narrow working fix" in decision.follow_up_goal
    finally:
        db.close()


def test_deterministic_worker_decision_escalates_after_strategy_retry_is_blocked_again() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Strategy Retry Exhausted",
            idea="A strategy retry that blocks again should stop looping and escalate.",
            workspace_path=sample_workspace("strategy-retry-exhausted"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Strategy retry: Implement the smallest safe code fix",
            goal="Rework the fix as a surgical patch.",
            scope="django/db/models/sql/compiler.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql"],
            forbidden_paths_json=[],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=4,
        )
        db.add_all([worker, task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary="The narrowed retry still could not produce a safe concrete edit.",
            files_changed=[],
            tests_run=[],
            blockers=["The narrowed retry still could not produce a safe concrete edit."],
            risks=[],
            recommended_next_task="Review the blocked task.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, task, report)

        assert decision.decision_type == "escalate_to_user"
        assert "exhausted repeated surgical retries" in decision.summary_markdown
    finally:
        db.close()


def test_deterministic_worker_decision_escalates_after_retry_family_limit_is_reached() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Retry Family Exhausted",
            idea="A looping focused/strategy retry family should stop spawning fresh tasks once the bounded family limit is reached.",
            workspace_path=sample_workspace("retry-family-exhausted"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        family_tasks = [
            Task(
                project_id=project.id,
                title="Implement the smallest safe code fix",
                goal="Base implementation lane.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The failing tests pass."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=20,
                failure_count=1,
            ),
            Task(
                project_id=project.id,
                title="Focused retry: Implement the smallest safe code fix",
                goal="Retry the base implementation lane.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The failing tests pass."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=21,
                failure_count=2,
            ),
            Task(
                project_id=project.id,
                title="Strategy retry: Implement the smallest safe code fix",
                goal="Retry with a surgical patch.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The failing tests pass."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=22,
                failure_count=1,
            ),
            Task(
                project_id=project.id,
                title="Focused retry: Implement the smallest safe code fix",
                goal="Another focused retry in the managed retry family.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The failing tests pass."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=23,
                failure_count=2,
            ),
        ]
        current_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Focused retry: Implement the smallest safe code fix",
            goal="Retry the same implementation lane with latest failure evidence.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The failing tests pass."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=24,
                failure_count=1,
            )
        db.add(project)
        db.add(worker)
        db.add_all([*family_tasks, current_task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(current_task.id),
            status="blocked",
            summary="The focused retry still produced no safe concrete edit.",
            files_changed=[],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=["The focused retry still produced no safe concrete edit."],
            risks=[],
            recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, current_task, report)

        assert decision.decision_type == "escalate_to_user"
        assert "bounded retry family" in decision.summary_markdown
    finally:
        db.close()


def test_request_fix_does_not_reuse_source_task_for_strategy_retry() -> None:
    service = MissionControlService()
    task = Task(
        project_id=1,
        title="Implement the smallest safe code fix",
        goal="Produce a minimal implementation patch.",
        scope="django/db/models/sql/compiler.py",
        agent_role="developer",
        milestone="Milestone 2",
        allowed_paths_json=["django/db/models/sql"],
        forbidden_paths_json=[],
        validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=2,
    )
    decision = ManagerWorkerDecision(
        decision_type="request_fix",
        summary_markdown="Escalate to a stricter surgical retry.",
        assign_to_agent_id=7,
        follow_up_title="Strategy retry: Implement the smallest safe code fix",
        follow_up_goal="Rework the fix as a narrower search/replace patch.",
        follow_up_allowed_paths=["django/db/models/sql", "tests/expressions"],
    )

    assert service._request_fix_reuses_source_task(task, decision) is False


def test_request_fix_reuses_active_strategy_retry_source_task() -> None:
    service = MissionControlService()
    task = Task(
        project_id=1,
        title="Strategy retry: Implement the smallest safe code fix",
        goal="Rework the fix as a narrower search/replace patch.",
        scope="django/db/models/sql/compiler.py",
        agent_role="developer",
        milestone="Milestone 2",
        allowed_paths_json=["django/db/models/sql/compiler.py"],
        forbidden_paths_json=[],
        validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=2,
    )
    decision = ManagerWorkerDecision(
        decision_type="request_fix",
        summary_markdown="Retry the same narrowed lane with the latest failure output.",
        assign_to_agent_id=7,
        follow_up_title="Implement the smallest safe code fix",
        follow_up_goal="Retry the narrowed fix with the latest validation evidence.",
        follow_up_allowed_paths=["django/db/models/sql/compiler.py"],
    )

    assert service._request_fix_reuses_source_task(task, decision) is True


def test_request_fix_does_not_reuse_strategy_retry_for_explicit_focused_retry_child() -> None:
    service = MissionControlService()
    task = Task(
        project_id=1,
        title="Strategy retry: Implement the smallest safe code fix",
        goal="Rework the fix as a narrower search/replace patch.",
        scope="astropy/modeling/separable.py",
        agent_role="developer",
        milestone="Milestone 2",
        allowed_paths_json=["astropy/modeling/separable.py"],
        forbidden_paths_json=[],
        validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=1,
    )
    decision = ManagerWorkerDecision(
        decision_type="request_fix",
        summary_markdown="Route a focused reproduce-and-edit retry.",
        assign_to_agent_id=7,
        follow_up_title="Focused retry: Strategy retry: Implement the smallest safe code fix",
        follow_up_goal="Produce one concrete minimal fix inside astropy/modeling/separable.py.",
        follow_up_allowed_paths=["astropy/modeling/separable.py"],
    )

    assert service._request_fix_reuses_source_task(task, decision) is False


def test_compose_follow_up_title_flattens_existing_retry_prefixes() -> None:
    service = MissionControlService()

    assert service._compose_follow_up_title(
        "Focused retry",
        "Strategy retry: Focused retry: Implement the smallest safe code fix",
    ) == "Focused retry: Implement the smallest safe code fix"
    assert service._compose_follow_up_title(
        "Strategy retry",
        "Focused retry: Implement the smallest safe code fix",
    ) == "Strategy retry: Implement the smallest safe code fix"


def test_find_reusable_request_fix_task_skips_strategy_retry_reuse() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Strategy Retry Reuse Guard",
            idea="A strategy retry should not collapse back into an older blocked implementation task.",
            workspace_path=sample_workspace("strategy-retry-reuse-guard"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        source_task = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Produce a minimal implementation patch.",
            scope="django/db/models/sql/compiler.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql"],
            forbidden_paths_json=[],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=2,
        )
        db.add(source_task)
        db.flush()
        decision = ManagerWorkerDecision(
            decision_type="request_fix",
            summary_markdown="Escalate to a stricter surgical retry.",
            assign_to_agent_id=7,
            follow_up_title="Strategy retry: Implement the smallest safe code fix",
            follow_up_goal="Rework the fix as a narrower search/replace patch.",
            follow_up_allowed_paths=["django/db/models/sql", "tests/expressions"],
        )

        reusable = service._find_reusable_request_fix_task(db, project, source_task, decision)

        assert reusable is None
    finally:
        db.close()


def test_find_reusable_request_fix_task_does_not_collapse_strategy_retry_back_to_broad_parent() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Strategy Retry Parent Collapse Guard",
            idea="An active narrow strategy retry should not hand control back to the older broad implementation task.",
            workspace_path=sample_workspace("strategy-retry-parent-collapse-guard"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        broad_parent = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Produce a minimal implementation patch.",
            scope="django/db/models/sql/compiler.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql", "django/db/models/fields"],
            forbidden_paths_json=[],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=3,
        )
        strategy_retry = Task(
            project_id=project.id,
            title="Strategy retry: Implement the smallest safe code fix",
            goal="Rework the fix as a narrower search/replace patch.",
            scope="django/db/models/sql/compiler.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql/compiler.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=21,
            failure_count=1,
        )
        db.add_all([broad_parent, strategy_retry])
        db.flush()
        decision = ManagerWorkerDecision(
            decision_type="request_fix",
            summary_markdown="Retry the narrowed implementation lane with the latest failure output.",
            assign_to_agent_id=7,
            follow_up_title="Implement the smallest safe code fix",
            follow_up_goal="Retry the narrowed fix with the latest validation evidence.",
            follow_up_allowed_paths=["django/db/models/sql/compiler.py"],
        )

        reusable = service._find_reusable_request_fix_task(db, project, strategy_retry, decision)

        assert reusable is None
    finally:
        db.close()


def test_strategy_retry_preserves_source_validation_context_for_fix_lanes() -> None:
    service = MissionControlService()
    task = Task(
        project_id=1,
        title="Implement the smallest safe code fix",
        goal="Produce a minimal implementation patch.",
        scope="django/db/models/sql/compiler.py",
        agent_role="developer",
        milestone="Milestone 2",
        allowed_paths_json=["django/db/models/sql"],
        forbidden_paths_json=[],
        validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=2,
    )
    decision = ManagerWorkerDecision(
        decision_type="request_fix",
        summary_markdown="Escalate to a stricter surgical retry.",
        assign_to_agent_id=7,
        follow_up_title="Strategy retry: Implement the smallest safe code fix",
        follow_up_goal="Rework the fix as a narrower search/replace patch.",
        follow_up_allowed_paths=["django/db/models/sql"],
    )

    assert service._follow_up_preserves_source_task_context(task, decision) is True


def test_retry_goal_builders_trim_noisy_hints_and_blockers() -> None:
    service = MissionControlService()
    task = Task(
        project_id=1,
        title="Implement the smallest safe code fix",
        goal="Produce a minimal implementation patch.",
        scope="django/db/models/sql/compiler.py",
        agent_role="developer",
        milestone="Milestone 2",
        allowed_paths_json=["django/db/models/sql"],
        forbidden_paths_json=[],
        validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=2,
    )
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="2",
        status="blocked",
        summary="Mission Control reran the focused validation command and it still failed.",
        files_changed=[],
        tests_run=[],
        blockers=[
            "Mission Control reran `python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql` and it failed with exit code 1. "
            + ("very noisy output " * 40)
        ],
        risks=[],
        recommended_next_task="Clarify the failing behavior or inspect more files.",
    )

    goal = service._build_surgical_fix_retry_goal(task, report)

    assert "search/replace style patch" in goal
    assert "Clarify the failing behavior or inspect more files." not in goal
    assert "[trimmed]" in goal


def test_no_change_fix_retry_goal_uses_existing_evidence_and_blocks_more_context_loops() -> None:
    service = MissionControlService()
    task = Task(
        project_id=1,
        title="Implement the smallest safe code fix",
        goal="Produce a minimal implementation patch.",
        scope="django/db/models/sql/compiler.py",
        agent_role="developer",
        milestone="Milestone 2",
        allowed_paths_json=["django/db/models/sql/compiler.py"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"
        ],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=1,
    )
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="2",
        status="blocked",
        summary="I could not determine a safe edit from the available workspace evidence.",
        files_changed=[],
        tests_run=[],
        blockers=["No verified workspace file changes were produced for a task that requires a concrete fix."],
        risks=[
            "Need clearer evidence before editing.",
            "Rejected search/replace edit because the search text was not found in django/db/models/sql/compiler.py",
        ],
        recommended_next_task="Clarify the failing behavior or inspect more files.",
    )

    goal = service._build_no_change_fix_retry_goal(task, report)

    assert "inspect this implementation path first: django/db/models/sql/compiler.py" in goal.lower()
    assert "do not ask for more evidence" in goal.lower()
    assert "do not respond with another 'need clearer evidence' blocker" in goal.lower()
    assert "copy the current workspace text exactly" in goal.lower()


def test_validation_fix_retry_goal_carries_failure_excerpt_and_blocks_dependency_excuses() -> None:
    service = MissionControlService()
    task = Task(
        project_id=1,
        title="Implement the smallest safe code fix",
        goal="Produce a minimal implementation patch.",
        scope="django/db/models/sql/compiler.py",
        agent_role="developer",
        milestone="Milestone 2",
        allowed_paths_json=["django/db/models/sql/compiler.py"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"
        ],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=1,
    )
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="2",
        status="blocked",
        summary="Mission Control reran the claimed validation command and it still failed.",
        files_changed=["django/db/models/sql/compiler.py"],
        tests_run=[
            "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"
        ],
        blockers=[
            "Mission Control reran `python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql` and it failed with exit code 1. django.db.utils.OperationalError: near ')': syntax error"
        ],
        risks=[],
        recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
    )

    goal = service._build_validation_fix_retry_goal(task, report)

    assert "use this exact failure evidence as your debug anchor" in goal.lower()
    assert "django.db.utils.operationalerror" in goal.lower()
    assert "do not ask for more evidence or claim missing dependencies" in goal.lower()


def test_build_validation_fix_retry_goal_carries_retry_anti_pattern_guidance() -> None:
    service = MissionControlService()
    task = Task(
        title="Implement the smallest safe code fix",
        goal=(
            "Retry feedback said the previous patch only changed the final boolean coercion for `is_separable` "
            "after it was already computed."
        ),
        scope="Update only astropy/modeling/separable.py.",
        allowed_paths_json=["astropy/modeling/separable.py"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "Use the focused validation command as the implementation anchor: python -m pytest astropy/modeling/tests/test_separable.py -q"
        ],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=1,
    )
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="2",
        status="blocked",
        summary="Mission Control reran the claimed validation command and it still failed.",
        files_changed=["astropy/modeling/separable.py"],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=[
            "The previous patch only changed the final boolean coercion for `is_separable` after it was already computed."
        ],
        risks=[],
        recommended_next_task="Inspect the upstream calculation or earlier helper that produces that value instead of trying another equivalent output-normalization tweak.",
    )

    goal = service._build_validation_fix_retry_goal(task, report)

    assert "do not make another final-threshold or output-normalization tweak on the same computed variable" in goal.lower()
    assert "move upstream to the calculation or helper that produces it" in goal.lower()


def test_build_validation_fix_retry_goal_flags_rejected_boolean_normalization_direction() -> None:
    service = MissionControlService()
    task = Task(
        title="Focused retry: Implement the smallest safe code fix",
        goal="Repair the validated implementation failure.",
        scope="Update only astropy/modeling/separable.py.",
        allowed_paths_json=["astropy/modeling/separable.py"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "Use the focused validation command as the implementation anchor: python -m pytest astropy/modeling/tests/test_separable.py -q"
        ],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=1,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="8",
        status="blocked",
        summary="Mission Control reran the claimed validation command and it still failed.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=[
            "The current implementation of _separable and separability_matrix uses np.where to normalize the separable_matrix, which is incorrect. The normalization should not be applied to the entire matrix but rather to each element."
        ],
        risks=[
            "Rejected downstream boolean-normalization-only edit for astropy/modeling/separable.py; same-file helper anchors are present in task context and this edit does not patch them."
        ],
        recommended_next_task="Inspect and patch the _separable function to correctly compute separability without applying normalization to the entire matrix.",
    )

    goal = service._build_validation_fix_retry_goal(task, report)

    assert "do not make another final-threshold or output-normalization tweak on the same computed variable" in goal.lower()
    assert "move upstream to the calculation or helper that produces it" in goal.lower()
    assert "_separable function" in goal


def test_build_validation_fix_retry_goal_preserves_prior_retry_hint() -> None:
    service = MissionControlService()
    task = Task(
        title="Focused retry: Implement the smallest safe code fix",
        goal="Repair the validated implementation failure.",
        scope="Update only astropy/modeling/separable.py.",
        allowed_paths_json=["astropy/modeling/separable.py"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "Use the focused validation command as the implementation anchor: python -m pytest astropy/modeling/tests/test_separable.py -q"
        ],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=2,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="5",
        status="blocked",
        summary="Mission Control reran the claimed validation command and it still failed.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["The issue is not in the separability_matrix function but rather in the way nested CompoundModels are handled."],
        risks=[],
        recommended_next_task="Update the _separable function to handle nested models correctly.",
    )

    goal = service._build_validation_fix_retry_goal(task, report)

    assert "prior retry hint:" in goal.lower()
    assert "_separable function" in goal


def test_build_validation_fix_retry_goal_treats_exact_anchor_line_as_approximate_locator() -> None:
    service = MissionControlService()
    task = Task(
        title="Focused retry: Implement the smallest safe code fix",
        goal="Repair the validated implementation failure.",
        scope="Update only astropy/modeling/separable.py.",
        allowed_paths_json=["astropy/modeling/separable.py"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "Use the focused validation command as the implementation anchor: python -m pytest astropy/modeling/tests/test_separable.py -q"
        ],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=2,
    )
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="4",
        status="blocked",
        summary="The current implementation still fails the focused validation command.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=[
            "The file 'astropy/modeling/separable.py' does not contain the exact live implementation anchor at line 66: def separability_matrix(transform): as specified in the task instructions."
        ],
        risks=[],
        recommended_next_task="Patch the live separability_matrix implementation once the current locator is confirmed.",
    )

    goal = service._build_validation_fix_retry_goal(task, report)

    assert "approximate search locators" in goal
    assert "different line" in goal


def test_build_validation_fix_retry_goal_names_same_file_helper_focus_symbol() -> None:
    service = MissionControlService()
    task = Task(
        title="Focused retry: Implement the smallest safe code fix",
        goal="Repair the validated implementation failure.",
        scope="Update only astropy/modeling/separable.py.",
        allowed_paths_json=["astropy/modeling/separable.py"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "Use the focused validation command as the implementation anchor: python -m pytest astropy/modeling/tests/test_separable.py -q"
        ],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=2,
    )
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="4",
        status="blocked",
        summary="The separability_matrix function does not correctly handle nested CompoundModels.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["The focused validation command still fails for nested CompoundModels."],
        risks=[],
        recommended_next_task="Inspect and patch the _separable helper function to correctly handle nested CompoundModels.",
    )

    goal = service._build_validation_fix_retry_goal(task, report)

    assert "Patch this same-file helper first" in goal
    assert "`_separable`" in goal


def test_build_validation_fix_retry_goal_discourages_rechecking_existing_issue_symbol() -> None:
    service = MissionControlService()
    task = Task(
        title="Focused retry: Implement the smallest safe code fix",
        goal="Repair the validated implementation failure.",
        scope="Update only astropy/modeling/separable.py.",
        allowed_paths_json=["astropy/modeling/separable.py"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "Use the focused validation command as the implementation anchor: python -m pytest astropy/modeling/tests/test_separable.py -q"
        ],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=2,
    )
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="4",
        status="blocked",
        summary="The separability_matrix function already exists in the allowed file and matches the live workspace snippet.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["The separability_matrix function already exists in the allowed file and matches the live workspace snippet."],
        risks=[],
        recommended_next_task="Inspect and patch the _separable helper function to correctly handle nested CompoundModels.",
    )

    goal = service._build_validation_fix_retry_goal(task, report)

    assert "Do not spend another turn proving the issue-named function exists" in goal
    assert "`_separable`" in goal
    assert "Patch this same-file helper first if it exists in the live scoped file: `separability_matrix`." not in goal


def test_retry_focus_guidance_uses_live_symbol_wording_for_non_helper_symbol() -> None:
    service = MissionControlService()

    guidance = service._retry_focus_guidance("separability_matrix")

    assert guidance is not None
    assert "Start from this live symbol first" in guidance
    assert "`separability_matrix`" in guidance
    assert "same-file helper callees" in guidance


def test_retry_focus_guidance_keeps_helper_wording_for_internal_helper_symbol() -> None:
    service = MissionControlService()

    guidance = service._retry_focus_guidance("_separable")

    assert guidance == "Patch this same-file helper first if it exists in the live scoped file: `_separable`."


def test_build_validation_fix_retry_goal_ignores_generic_rerun_hint_when_report_has_specific_helper() -> None:
    service = MissionControlService()
    task = Task(
        title="Focused retry: Implement the smallest safe code fix",
        goal="Repair the validated implementation failure.",
        scope="Update only astropy/modeling/separable.py.",
        allowed_paths_json=["astropy/modeling/separable.py"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "Use the focused validation command as the implementation anchor: python -m pytest astropy/modeling/tests/test_separable.py -q"
        ],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=2,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="5",
        status="blocked",
        summary="No verified workspace file changes were produced for a task that requires a concrete fix.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["Inspect and patch the _compute_n_outputs helper before changing the downstream wrapper again."],
        risks=[],
        recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
    )

    goal = service._build_validation_fix_retry_goal(task, report)

    assert "prior retry hint:" in goal.lower()
    assert "_compute_n_outputs helper" in goal
    assert "inspect the failed validation output, repair the implementation" not in goal.lower()


def test_retry_hint_from_report_filters_generic_rerun_hint() -> None:
    service = MissionControlService()
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="5",
        status="blocked",
        summary="The previous patch did not resolve the nested model handling bug.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):"],
        risks=[],
        recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
    )

    hint = service._retry_hint_from_report(report)

    assert hint == "astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):"


def test_retry_hint_from_report_filters_stale_exact_live_anchor_blocker() -> None:
    service = MissionControlService()
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="4",
        status="blocked",
        summary="The current implementation still fails the focused validation command.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=[
            "The file 'astropy/modeling/separable.py' does not contain the exact live implementation anchor at line 66: def separability_matrix(transform): as specified in the task instructions.",
            "astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):",
        ],
        risks=[],
        recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
    )

    hint = service._retry_hint_from_report(report)

    assert hint == "astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):"


def test_retry_hint_from_report_filters_missing_symbol_excuse() -> None:
    service = MissionControlService()
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="6",
        status="blocked",
        summary="The live code does not contain the expected symbol or function that needs to be patched.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["The provided live code does not contain the expected symbol or function that needs to be patched."],
        risks=[],
        recommended_next_task="Inspect the implementation paths first: astropy/modeling/separable.py",
    )

    hint = service._retry_hint_from_report(report)

    assert hint == "Inspect the implementation paths first: astropy/modeling/separable.py"


def test_retry_focus_symbol_prefers_same_file_helper_over_existing_issue_symbol() -> None:
    service = MissionControlService()
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="4",
        status="blocked",
        summary="The separability_matrix function already exists in the allowed file and matches the live workspace snippet.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["The separability_matrix function already exists in the allowed file and matches the live workspace snippet."],
        risks=[],
        recommended_next_task="Inspect and patch the _separable helper function to correctly handle nested CompoundModels.",
    )

    symbol = service._retry_focus_symbol(report)

    assert symbol == "_separable"


def test_retry_focus_symbol_ignores_exact_function_signatures_noise() -> None:
    service = MissionControlService()
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="4",
        status="blocked",
        summary="The provided code snippet does not contain the exact function signatures or logic that match the live workspace.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["Inspect the live workspace and provide an exact search/replace patch based on the actual function signatures and logic."],
        risks=[],
        recommended_next_task="Inspect and patch the _separable helper function to correctly handle nested CompoundModels.",
    )

    symbol = service._retry_focus_symbol(report)

    assert symbol == "_separable"


def test_retry_focus_symbol_ignores_same_file_helper_prose_noise() -> None:
    service = MissionControlService()
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="4",
        status="blocked",
        summary="The focused validation still fails and the same-file helper should be inspected before retrying.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["Patch this same-file helper first if it exists in the live scoped file."],
        risks=[],
        recommended_next_task="Inspect and patch the `_separable` helper function to correctly handle nested CompoundModels.",
    )

    symbol = service._retry_focus_symbol(report)

    assert symbol == "_separable"


def test_retry_focus_symbol_prefers_backticked_helper_with_arguments() -> None:
    service = MissionControlService()
    report = WorkerReport(
        agent="Service Flow Builder",
        task_id="4",
        status="blocked",
        summary="The current implementation of `separability_matrix` does not handle nested CompoundModels correctly.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["The previous patch applied to `separability_matrix` did not address the issue with nested CompoundModels."],
        risks=[],
        recommended_next_task="Investigate and fix the logic in `_compute_n_outputs(left, right)` or `_arith_oper(left, right)` to correctly handle nested CompoundModels.",
    )

    symbol = service._retry_focus_symbol(report)

    assert symbol == "_compute_n_outputs"


def test_build_validation_strategy_retry_goal_discourages_missing_symbol_claim() -> None:
    service = MissionControlService()
    task = Task(
        title="Focused retry: Implement the smallest safe code fix",
        goal="Repair the validated implementation failure.",
        scope="Update only astropy/modeling/separable.py.",
        allowed_paths_json=["astropy/modeling/separable.py"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "Use the focused validation command as the implementation anchor: python -m pytest astropy/modeling/tests/test_separable.py -q"
        ],
        success_criteria_json=["The focused validation command passes."],
        estimated_complexity="small",
        dependencies_json=[],
        status="blocked",
        priority=20,
        failure_count=2,
    )
    report = WorkerReport(
        agent="Validation Specialist",
        task_id="7",
        status="blocked",
        summary="The provided live code does not contain the expected symbol or function that needs to be patched.",
        files_changed=[],
        tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        blockers=["astropy/modeling/separable.py does not contain the expected symbol or function that needs to be patched."],
        risks=[],
        recommended_next_task="Retarget the fix into a different upstream computation or sibling helper that still drives the wrong behavior.",
    )

    goal = service._build_validation_strategy_retry_goal(task, report)

    assert "do not spend another turn claiming the scoped live file lacks the expected symbol" in goal.lower()
    assert "treat task path:line:symbol anchors as approximate locators" in goal.lower()


def test_preferred_validation_agent_id_prefers_test_lane_worker() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Preferred Validation Agent",
            idea="Unblock follow-ups should prefer a real validation lane.",
            workspace_path=sample_workspace("preferred-validation-agent"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        planner = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            archetype="planner",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Test specialist",
            archetype="test",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
        )
        db.add_all([planner, validator])
        db.flush()

        assert service._preferred_validation_agent_id(db, project, fallback_agent_id=planner.id) == validator.id
    finally:
        db.close()


def test_deterministic_worker_decision_retries_focused_retry_task_in_place() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Focused Retry In Place",
            idea="A focused retry task should get one in-place retry before spawning more follow-up shape.",
            workspace_path=sample_workspace("focused-retry-in-place"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Focused retry: Develop a patch",
            goal="Produce a concrete fix inside the scoped paths.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The failing tests pass."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=10,
            failure_count=1,
        )
        db.add_all([worker, task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary="The separability_matrix function still appears incorrect for nested CompoundModels.",
            files_changed=[],
            tests_run=[],
            blockers=["Incorrect implementation of separability_matrix for nested CompoundModels."],
            risks=[],
            recommended_next_task="Clarify the failing behavior or inspect more files.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == worker.id
        assert decision.follow_up_title is None
        assert decision.follow_up_goal is None
    finally:
        db.close()


def test_deterministic_worker_decision_reopens_implementation_after_blocked_validation() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Blocked Validation Repair Loop",
            idea="Blocked validation with real test evidence should reopen the implementation dependency instead of deadlocking.",
            workspace_path=sample_workspace("blocked-validation-repair-loop"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=builder.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["astropy/modeling/tests", "astropy/modeling"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=30,
            failure_count=1,
        )
        db.add_all([builder, validator, implementation_task, validation_task])
        db.flush()
        validation_task.dependencies_json = [implementation_task.id]
        db.flush()

        report = WorkerReport(
            agent=validator.name,
            task_id=str(validation_task.id),
            status="blocked",
            summary="Focused validation stayed blocked after re-running the test command.",
            files_changed=[],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=["Validation failed after the last implementation attempt."],
            risks=[],
            recommended_next_task="Reopen the implementation task and repair the broken path.",
        )

        decision = service._deterministic_worker_decision(db, project, validator, validation_task, report)

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == implementation_task.id
        assert decision.assign_to_agent_id == builder.id
        assert implementation_task.status == "backlog"
        assert implementation_task.waiting_reason is None
        assert validation_task.status == "backlog"
        assert validation_task.assigned_agent_id is None
        assert validation_task.waiting_reason == "Waiting for task dependencies to finish."
    finally:
        db.close()


def test_deterministic_worker_decision_keeps_environment_only_validation_blocker_on_validation_lane() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Dependency Style Validation Repair Loop",
            idea="A blocked validation lane should reopen implementation even when the worker only reports missing environment or dependencies.",
            workspace_path=sample_workspace("dependency-style-validation-repair-loop"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=builder.id,
            title="Generate a minimal safe patch to fix the issue",
            goal="Create a small, self-contained patch that fixes the bug in separability_matrix.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Apply the patch and run all tests to ensure no new issues are introduced."],
            success_criteria_json=["A minimal safe patch is generated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Run validation tests to ensure the fix works",
            goal="Validate that the patch correctly fixes the bug in separability_matrix for nested CompoundModels.",
            scope="astropy/modeling/tests/test_separable.py",
            agent_role="developer",
            milestone="Milestone 3",
            allowed_paths_json=["astropy/modeling/tests/test_separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Run all tests, including those that previously failed due to the bug."],
            success_criteria_json=["All relevant tests pass with the patch applied."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=30,
            failure_count=1,
        )
        db.add_all([builder, validator, implementation_task, validation_task])
        db.flush()
        validation_task.dependencies_json = [implementation_task.id]
        db.flush()

        report = WorkerReport(
            agent=validator.name,
            task_id=str(validation_task.id),
            status="blocked",
            summary="Failed to run validation tests due to missing environment or dependencies.",
            files_changed=[],
            tests_run=[],
            blockers=["Missing environment or dependencies"],
            risks=[],
            recommended_next_task="Ensure the required environment and dependencies are installed.",
        )

        decision = service._deterministic_worker_decision(db, project, validator, validation_task, report)

        assert decision.decision_type == "request_fix"
        assert decision.task_id is None
        assert decision.assign_to_agent_id == validator.id
        assert implementation_task.status == "done"
        assert validation_task.status == "blocked"
    finally:
        db.close()


def test_deterministic_worker_decision_keeps_failed_to_run_validation_blocker_on_validation_lane() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Failed Validation Command Stays On Validation Lane",
            idea="A blocked validation command without concrete failure evidence should not reopen implementation on the first retry.",
            workspace_path=sample_workspace("failed-validation-command-stays-on-validation-lane"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=builder.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="django/db/models/sql/compiler.py",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql", "tests/expressions", "tests"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the change scoped to the validated failure."],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests/expressions", "tests", "django/db/models"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "Re-run the focused validation command: python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=30,
            failure_count=1,
        )
        db.add_all([builder, validator, implementation_task, validation_task])
        db.flush()
        validation_task.dependencies_json = [implementation_task.id]
        db.flush()

        report = WorkerReport(
            agent=validator.name,
            task_id=str(validation_task.id),
            status="blocked",
            summary="The test command failed to run and did not produce any evidence.",
            files_changed=[],
            tests_run=[
                "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            blockers=["The test command failed to run and did not produce any evidence."],
            risks=[],
            recommended_next_task="Re-run the validation command after ensuring all dependencies are correctly set up.",
        )

        decision = service._deterministic_worker_decision(db, project, validator, validation_task, report)

        assert decision.decision_type == "request_fix"
        assert decision.task_id is None
        assert decision.assign_to_agent_id == validator.id
        assert implementation_task.status == "done"
        assert validation_task.status == "blocked"
    finally:
        db.close()


def test_deterministic_worker_decision_reopens_implementation_after_repeated_dependency_style_validation_blocker() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Repeated Dependency Style Validation Repair Loop",
            idea="A validation lane that keeps failing on dependency-style blockers should still reopen implementation instead of idling on the validator forever.",
            workspace_path=sample_workspace("repeated-dependency-style-validation-repair-loop"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=builder.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="django/db/models/sql/compiler.py",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql", "tests/expressions", "tests"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the change scoped to the validated failure."],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests/expressions", "tests", "django/db/models"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "Re-run the focused validation command: python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=30,
            failure_count=5,
        )
        db.add_all([builder, validator, implementation_task, validation_task])
        db.flush()
        validation_task.dependencies_json = [implementation_task.id]
        db.flush()

        report = WorkerReport(
            agent=validator.name,
            task_id=str(validation_task.id),
            status="blocked",
            summary="The required validation command cannot be executed because the environment is missing dependencies.",
            files_changed=[],
            tests_run=[
                "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            blockers=["Mission Control reran the claimed validation command and it still failed."],
            risks=[],
            recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
        )

        decision = service._deterministic_worker_decision(db, project, validator, validation_task, report)

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == implementation_task.id
        assert implementation_task.status == "backlog"
        assert implementation_task.waiting_reason is None
        assert validation_task.status == "backlog"
        assert validation_task.assigned_agent_id is None
        assert validation_task.waiting_reason == "Waiting for task dependencies to finish."
    finally:
        db.close()


def test_deterministic_worker_decision_requests_focused_retry_after_failed_validation_rerun() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Implementation Validation Retry",
            idea="A claimed fix that still fails rerun validation should trigger a focused repair retry instead of a deadlock.",
            workspace_path=sample_workspace("implementation-validation-retry"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=1,
        )
        db.add_all([worker, task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "Corrected the separability_matrix function to ensure proper handling of nested CompoundModels. "
                "Mission Control reran the claimed validation command and it still failed."
            ),
            files_changed=["astropy/modeling/separable.py"],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=["Mission Control reran `python -m pytest astropy/modeling/tests/test_separable.py -q` and it failed with exit code 2."],
            risks=[],
            recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == worker.id
        assert decision.follow_up_title == "Focused retry: Implement the smallest safe code fix"
        assert decision.follow_up_goal is not None
        assert "failed validation evidence" in decision.follow_up_goal.lower()
    finally:
        db.close()


def test_deterministic_worker_decision_routes_validation_strategy_retry_after_discarded_edit_rerun() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Implementation Validation Strategy Retry",
            idea="A focused retry that reran validation but lost accepted edits should still route through the validation-failure strategy lane.",
            workspace_path=sample_workspace("implementation-validation-strategy-retry"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Focused validation",
            kind="worker",
            status="idle",
            workspace_path=project.workspace_path,
            archetype="test",
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=builder.id,
            title="Focused retry: Implement the smallest safe code fix",
            goal="Repair the validated implementation failure with one concrete scoped edit.",
            scope="Update only the implementation path needed for the focused failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=2,
        )
        db.add_all([builder, validator, task])
        db.flush()

        report = WorkerReport(
            agent=builder.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "The focused validation command still fails. Mission Control discarded unvetted direct workspace edits because the adapter did not provide accepted edits[]. "
                "Mission Control reran the claimed validation command and it still failed."
            ),
            files_changed=[],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=[
                "The function 'separability_matrix' already exists in astropy/modeling/separable.py, but the focused validation command still fails."
            ],
            risks=[
                "Mission Control discarded unvetted direct workspace edits because the adapter did not provide accepted edits[]."
            ],
            recommended_next_task="Inspect the failed test cases to understand why the existing implementation is failing and make targeted changes.",
        )

        decision = service._deterministic_worker_decision(db, project, builder, task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == builder.id
        assert decision.follow_up_title == "Strategy retry: Implement the smallest safe code fix"
        assert decision.follow_up_goal is not None
        assert "different fix direction" in decision.follow_up_goal.lower()
        assert "internal review-guided re-localization pass" in decision.follow_up_goal.lower()
    finally:
        db.close()


def test_deterministic_worker_decision_stops_validation_retry_family_loop_after_limit() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Validation Retry Family Exhausted",
            idea="A validation-driven focused/strategy retry loop should stop once the bounded retry family limit is reached.",
            workspace_path=sample_workspace("validation-retry-family-exhausted"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Focused validation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="test",
        )
        current_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Focused retry: Implement the smallest safe code fix",
            goal="Retry the implementation with the latest validation evidence.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=23,
            failure_count=2,
        )
        earlier_tasks = [
            Task(
                project_id=project.id,
                title="Focused retry: Implement the smallest safe code fix",
                goal="Earlier focused retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=20,
                failure_count=2,
            ),
            Task(
                project_id=project.id,
                title="Strategy retry: Implement the smallest safe code fix",
                goal="Earlier strategy retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=21,
                failure_count=1,
            ),
            Task(
                project_id=project.id,
                title="Focused retry: Implement the smallest safe code fix",
                goal="Another focused retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=22,
                failure_count=2,
            ),
        ]
        db.add(worker)
        db.flush()
        db.add_all(earlier_tasks + [current_task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(current_task.id),
            status="blocked",
            summary=(
                "The current implementation still fails the focused validation command. "
                "Mission Control discarded unvetted direct workspace edits because the adapter did not provide accepted edits[]. "
                "Mission Control reran the claimed validation command and it still failed."
            ),
            files_changed=[],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=["The focused validation command still fails for nested CompoundModels."],
            risks=["Mission Control discarded unvetted direct workspace edits because the adapter did not provide accepted edits[]."],
            recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, current_task, report)

        assert decision.decision_type == "escalate_to_user"
        assert "bounded retry family" in decision.summary_markdown
    finally:
        db.close()


def test_deterministic_worker_decision_does_not_count_source_task_toward_retry_family_limit() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Validation Retry Family Source Task Guard",
            idea="The original implementation task should not consume retry-family budget for focused/strategy retries.",
            workspace_path=sample_workspace("validation-retry-family-source-task-guard"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Focused validation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="test",
        )
        source_task = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=1,
        )
        earlier_tasks = [
            Task(
                project_id=project.id,
                title="Focused retry: Implement the smallest safe code fix",
                goal="Earlier focused retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=21,
                failure_count=2,
            ),
            Task(
                project_id=project.id,
                title="Strategy retry: Implement the smallest safe code fix",
                goal="Earlier strategy retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=22,
                failure_count=1,
            ),
        ]
        current_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Focused retry: Implement the smallest safe code fix",
            goal="Retry the implementation with the latest validation evidence.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=23,
            failure_count=1,
        )
        db.add_all([builder, validator, source_task, *earlier_tasks, current_task])
        db.flush()

        report = WorkerReport(
            agent=validator.name,
            task_id=str(current_task.id),
            status="blocked",
            summary=(
                "The focused validation command still fails. Mission Control discarded unvetted direct workspace edits because the adapter did not provide accepted edits[]. "
                "Mission Control reran the claimed validation command and it still failed."
            ),
            files_changed=[],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=[
                "The function 'separability_matrix' already exists in astropy/modeling/separable.py, but the focused validation command still fails."
            ],
            risks=[
                "Mission Control discarded unvetted direct workspace edits because the adapter did not provide accepted edits[]."
            ],
            recommended_next_task="Inspect the failed test cases to understand why the existing implementation is failing and make targeted changes.",
        )

        decision = service._deterministic_worker_decision(db, project, validator, current_task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == builder.id
        assert decision.follow_up_title is None
        assert decision.follow_up_goal is None
    finally:
        db.close()


def test_deterministic_worker_decision_grants_anchor_recovery_turn_for_strategy_retry_with_rejected_edits() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Strategy Retry Anchor Recovery",
            idea="A strategy retry that returns a concrete rejected edit proposal should earn one more focused retry instead of immediate escalation.",
            workspace_path=sample_workspace("strategy-retry-anchor-recovery"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Focused validation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="test",
        )
        retry_history = [
            Task(
                project_id=project.id,
                title="Focused retry: Implement the smallest safe code fix",
                goal="Earlier focused retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=21,
                failure_count=2,
            ),
            Task(
                project_id=project.id,
                title="Strategy retry: Implement the smallest safe code fix",
                goal="Earlier strategy retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=22,
                failure_count=1,
            ),
            Task(
                project_id=project.id,
                title="Focused retry: Implement the smallest safe code fix",
                goal="Another focused retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=23,
                failure_count=2,
            ),
        ]
        current_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Strategy retry: Implement the smallest safe code fix",
            goal="Review the repeated failed validation evidence and propose a different fix direction.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=24,
            failure_count=1,
        )
        db.add_all([validator, *retry_history, current_task])
        db.flush()

        report = WorkerReport(
            agent=validator.name,
            task_id=str(current_task.id),
            status="blocked",
            summary=(
                "The separability_matrix function is not computing the separability correctly for nested CompoundModels. "
                "A fix direction has been identified and is ready for review. Mission Control rejected or could not apply one or more proposed edits."
            ),
            files_changed=[],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=[],
            risks=[
                "Rejected downstream boolean-normalization-only edit for astropy/modeling/separable.py; same-file helper anchors are present in task context and this edit does not patch them."
            ],
            recommended_next_task="Run the updated validation command and review the results.",
        )

        decision = service._deterministic_worker_decision(db, project, validator, current_task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == validator.id
        assert decision.follow_up_title == "Focused retry: Implement the smallest safe code fix"
        assert decision.follow_up_goal is not None
    finally:
        db.close()


def test_deterministic_worker_decision_grants_validation_repair_turn_for_strategy_retry_after_failed_rerun() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Strategy Retry Validation Repair Turn",
            idea="A first strategy retry that produced a concrete patch but still fails rerun validation should earn one bounded focused repair turn.",
            workspace_path=sample_workspace("strategy-retry-validation-repair-turn"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        retry_history = [
            Task(
                project_id=project.id,
                title="Focused retry: Implement the smallest safe code fix",
                goal="Earlier focused retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=21,
                failure_count=2,
            ),
            Task(
                project_id=project.id,
                title="Strategy retry: Implement the smallest safe code fix",
                goal="Earlier strategy retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=22,
                failure_count=1,
            ),
            Task(
                project_id=project.id,
                title="Focused retry: Implement the smallest safe code fix",
                goal="Another focused retry.",
                scope="astropy/modeling/separable.py",
                agent_role="developer",
                milestone="Milestone 2",
                allowed_paths_json=["astropy/modeling/separable.py"],
                forbidden_paths_json=[],
                validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                success_criteria_json=["The focused validation command passes."],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                priority=23,
                failure_count=2,
            ),
        ]
        current_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Strategy retry: Implement the smallest safe code fix",
            goal="Try a different concrete fix direction in the scoped file.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=24,
            failure_count=1,
        )
        db.add_all([worker, *retry_history, current_task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(current_task.id),
            status="blocked",
            summary=(
                "Fixed the issue in separability_matrix for nested CompoundModels by modifying the logic in _separable. "
                "Mission Control reran the claimed validation command and it still failed."
            ),
            files_changed=["astropy/modeling/separable.py"],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=[
                "Mission Control reran `python -m pytest astropy/modeling/tests/test_separable.py -q` and it failed with exit code 2."
            ],
            risks=[],
            recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, current_task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == worker.id
        assert decision.follow_up_title == "Focused retry: Implement the smallest safe code fix"
        assert decision.follow_up_goal is not None
        assert "use this exact failure evidence as your debug anchor" in decision.follow_up_goal.lower()
    finally:
        db.close()


def test_deterministic_worker_decision_requests_focused_retry_after_missing_validation_evidence() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Implementation Validation Evidence Retry",
            idea="A claimed fix without runnable validation evidence should trigger a focused retry instead of escalating to the user.",
            workspace_path=sample_workspace("implementation-validation-evidence-retry"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql"],
            forbidden_paths_json=[],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=1,
        )
        db.add_all([worker, task])
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "Fixed the targeted implementation change and kept the diff scoped. "
                "Mission Control required validation evidence for the claimed code fix and did not receive any runnable command."
            ),
            files_changed=["django/db/models/sql/compiler.py"],
            tests_run=[],
            blockers=["Mission Control required at least one explicit validation command for this implementation step."],
            risks=[],
            recommended_next_task="Re-run focused validation.",
        )

        decision = service._deterministic_worker_decision(db, project, worker, task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == worker.id
        assert decision.follow_up_title == "Focused retry: Implement the smallest safe code fix"
        assert decision.follow_up_goal is not None
    finally:
        db.close()


def test_sanitize_benchmark_edit_follow_up_paths_keeps_implementation_retry_out_of_test_paths() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        workspace = Path(sample_workspace("benchmark-implementation-retry-path-guard"))
        (workspace / "django/db/models/sql").mkdir(parents=True, exist_ok=True)
        (workspace / "tests/expressions").mkdir(parents=True, exist_ok=True)
        project = Project(
            name="Benchmark Implementation Retry Guard",
            idea="Prepared benchmark implementation retries should not regain test-file write scope.",
            workspace_path=workspace.as_posix(),
            source_type="existing_folder",
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nFix the multiline RawSQL ordering regression.\n"
                "Workspace clues:\n"
                "- Files to inspect first: tests/expressions/tests.py\n"
                "- Likely related implementation files: django/db/models/sql/compiler.py\n"
                "Focused reproduction commands:\n"
                "- python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=workspace.as_posix(),
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql"],
            forbidden_paths_json=["tests/expressions"],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=1,
        )
        db.add_all([request, worker, task])
        db.flush()

        sanitized = service._sanitize_benchmark_edit_follow_up_paths(
            db,
            project,
            task,
            ["django/db/models/sql", "tests/expressions", "tests/expressions/tests.py"],
        )

        assert sanitized == ["django/db/models/sql"]
    finally:
        db.close()


def test_sanitize_benchmark_edit_follow_up_paths_narrows_to_exact_impl_file_hint() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-implementation-retry-exact-file"))
    (workspace / "django/db/models/sql").mkdir(parents=True, exist_ok=True)
    (workspace / "tests/expressions").mkdir(parents=True, exist_ok=True)
    (workspace / "django/db/models/sql/compiler.py").write_text("class SQLCompiler:\n    pass\n", encoding="utf-8")
    (workspace / "tests/expressions/tests.py").write_text("def test_order_by_multiline_sql():\n    assert True\n", encoding="utf-8")

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Implementation Retry Exact File",
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
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nFix the multiline RawSQL ordering regression.\n"
                "Workspace clues:\n"
                "- Files to inspect first: tests/expressions/tests.py\n"
                "- Likely related implementation files: django/db/models/sql/compiler.py\n"
                "Focused reproduction commands:\n"
                "- python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=workspace.as_posix(),
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql"],
            forbidden_paths_json=["tests/expressions"],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
            failure_count=1,
        )
        db.add_all([request, worker, task])
        db.flush()

        sanitized = service._sanitize_benchmark_edit_follow_up_paths(
            db,
            project,
            task,
            ["django/db/models/sql"],
        )

        assert sanitized == ["django/db/models/sql/compiler.py"]
    finally:
        db.close()


def test_deterministic_worker_decision_retries_validation_rerun_task_after_noop_blocker() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Validation Rerun Retry",
            idea="A validation lane that did not actually rerun the focused command should get one in-place retry instead of idling forever.",
            workspace_path=sample_workspace("validation-rerun-retry"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Re-run focused validation with the updated settings",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again and capture the result.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests", "django/conf", "docs/ref"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "Re-run the focused validation command: python tests/runtests.py --settings=test_sqlite test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions",
                "Record pass/fail results and remaining limitations",
            ],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=30,
            failure_count=1,
        )
        db.add_all([validator, task])
        db.flush()

        report = WorkerReport(
            agent=validator.name,
            task_id=str(task.id),
            status="blocked",
            summary="No changes were made to the specified files, so the focused validation was not rerun.",
            files_changed=[],
            tests_run=[],
            blockers=["No changes were made to the specified files."],
            risks=[],
            recommended_next_task="Re-run focused validation with the updated settings context.",
        )

        decision = service._deterministic_worker_decision(db, project, validator, task, report)

        assert decision.decision_type == "request_fix"
        assert decision.assign_to_agent_id == validator.id
        assert decision.follow_up_title is None
        assert decision.follow_up_goal is None
    finally:
        db.close()


def test_apply_worker_decision_preserves_validation_context_for_validation_follow_up() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Validation Follow Up Context",
            idea="Validation follow-up tasks should keep the focused validation command instead of degrading to generic placeholder steps.",
            workspace_path=sample_workspace("validation-follow-up-context"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        source_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests", "django/conf", "docs/ref"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "Re-run the focused validation command: python tests/runtests.py --settings=test_sqlite test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions",
                "Record pass/fail results and remaining limitations",
            ],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=30,
        )
        db.add_all([validator, source_task])
        db.flush()

        decision = ManagerWorkerDecision(
            decision_type="request_fix",
            summary_markdown="Create a validation follow-up.",
            assign_to_agent_id=validator.id,
            follow_up_title="Re-run focused validation with the updated settings",
            follow_up_goal="Retry the focused validation with the updated settings context.",
        )

        asyncio.run(service._apply_worker_decision(db, project, validator, source_task, decision))
        db.flush()

        follow_up = db.scalar(
            select(Task).where(
                Task.project_id == project.id,
                Task.title == "Re-run focused validation with the updated settings",
            )
        )

        assert follow_up is not None
        assert follow_up.validation_steps_json == source_task.validation_steps_json
        assert follow_up.success_criteria_json == source_task.success_criteria_json
        assert follow_up.scope == source_task.scope
    finally:
        db.close()


def test_apply_worker_decision_reuses_same_implementation_task_for_focused_retry(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Same Task Focused Retry",
            idea="Implementation retries should stay on the same task when the follow-up title targets the same delivery lane.",
            workspace_path=sample_workspace("same-task-focused-retry"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        source_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the validated failing behavior with the least invasive change.",
            scope="Implementation only.",
            agent_role="Backend specialist",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models", "tests/expressions"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the diff narrow."],
            success_criteria_json=["The fix is complete."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
        )
        db.add_all([worker, source_task])
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append(selected_task.id)
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.flush()
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        decision = ManagerWorkerDecision(
            decision_type="request_fix",
            summary_markdown="Retry the same implementation lane with tighter guidance.",
            assign_to_agent_id=worker.id,
            follow_up_title="Focused retry: Implement the smallest safe code fix",
            follow_up_goal="Retry the same implementation task with a targeted search/replace patch.",
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, source_task, decision))

        duplicate = db.scalar(
            select(Task).where(
                Task.project_id == project.id,
                Task.id != source_task.id,
            )
        )

        assert started == [source_task.id]
        assert duplicate is None
        assert source_task.goal == "Retry the same implementation task with a targeted search/replace patch."
        assert source_task.status == "working"
    finally:
        db.close()


def test_apply_worker_decision_keeps_strategy_retry_on_same_task_instead_of_broad_parent(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Strategy Retry Same Task",
            idea="A narrowed strategy retry should stay on the same task instead of widening back to the parent implementation lane.",
            workspace_path=sample_workspace("strategy-retry-same-task"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        broad_parent = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the validated failing behavior with the least invasive change.",
            scope="Implementation only.",
            agent_role="Backend specialist",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql", "django/db/models/fields"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the diff narrow."],
            success_criteria_json=["The fix is complete."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
        )
        strategy_retry = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Strategy retry: Implement the smallest safe code fix",
            goal="Rework the fix as a narrower search/replace patch.",
            scope="Implementation only.",
            agent_role="Backend specialist",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql/compiler.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the diff narrow."],
            success_criteria_json=["The fix is complete."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=21,
        )
        db.add_all([worker, broad_parent, strategy_retry])
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append(selected_task.id)
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.flush()
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        decision = ManagerWorkerDecision(
            decision_type="request_fix",
            summary_markdown="Retry the narrowed implementation lane with the latest failure output.",
            assign_to_agent_id=worker.id,
            follow_up_title="Implement the smallest safe code fix",
            follow_up_goal="Retry the narrowed fix with the latest validation evidence.",
            follow_up_allowed_paths=["django/db/models/sql/compiler.py"],
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, strategy_retry, decision))

        assert started == [strategy_retry.id]
        assert strategy_retry.goal == "Retry the narrowed fix with the latest validation evidence."
        assert strategy_retry.status == "working"
        assert broad_parent.status == "blocked"
    finally:
        db.close()


def test_apply_worker_decision_escalation_keeps_blocked_task_terminal(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Escalation Stays Terminal",
            idea="Escalated blocked tasks should not get requeued as stale work on the next scheduler pass.",
            workspace_path=sample_workspace("escalation-stays-terminal"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
            current_task_id=None,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=None,
            title="Strategy retry: Implement the smallest safe code fix",
            goal="Retry the implementation with the latest failure evidence.",
            scope="Implementation only.",
            agent_role="Backend specialist",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql/compiler.py"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the diff narrow."],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=21,
        )
        db.add_all([worker, task])
        db.flush()
        worker.current_task_id = task.id
        task.assigned_agent_id = worker.id
        db.commit()

        async def forbidden_start_agent_task(db, project, agent, selected_task):
            raise AssertionError("Escalated blocked tasks should not be relaunched immediately.")

        monkeypatch.setattr(service, "start_agent_task", forbidden_start_agent_task)

        decision = ManagerWorkerDecision(
            decision_type="escalate_to_user",
            summary_markdown="Task exhausted repeated surgical retries and needs review.",
            escalation_message="Concrete blocker from the latest retry.",
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, task, decision))
        started = asyncio.run(service.start_idle_agents(db, project))

        db.refresh(task)
        stale_requeues = list(
            db.scalars(
                select(ProjectEvent).where(
                    ProjectEvent.project_id == project.id,
                    ProjectEvent.event_type == "task.stale_blocked_assignment_requeued",
                )
            )
        )

        assert started == 0
        assert task.status == "blocked"
        assert task.assigned_agent_id is None
        assert task.waiting_reason == "Concrete blocker from the latest retry."
        assert stale_requeues == []
    finally:
        db.close()


def test_apply_worker_decision_reuses_existing_implementation_task_instead_of_creating_duplicate_follow_up(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Reuse Existing Implementation Lane",
            idea="A review or exploratory lane should hand off to the canonical implementation task instead of creating a duplicate implementation follow-up.",
            workspace_path=sample_workspace("reuse-existing-implementation-lane"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        planner = Agent(
            project_id=project.id,
            name="Execution Planner",
            role="Planner specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        review_task = Task(
            project_id=project.id,
            assigned_agent_id=planner.id,
            title="Review Test Case",
            goal="Resolve the reproduction blocker before the main implementation can continue.",
            scope="Focused review only.",
            agent_role="Planner specialist",
            milestone="Milestone 1",
            allowed_paths_json=["tests/expressions", "tests", "django/db/models"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed."],
            success_criteria_json=["The blocker is clearly resolved."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=11,
        )
        implementation_task = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Implementation only.",
            agent_role="Backend specialist",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models", "django/db/models/sql", "tests/expressions", "tests"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the diff narrow."],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([planner, builder, review_task, implementation_task])
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append(selected_task.id)
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.flush()
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        decision = ManagerWorkerDecision(
            decision_type="request_fix",
            summary_markdown="Hand the blocked review lane off to the canonical implementation task.",
            assign_to_agent_id=builder.id,
            follow_up_title="Implement the smallest safe code fix",
            follow_up_goal="Apply the suggested fix and ensure it resolves the issue without introducing new bugs.",
        )

        asyncio.run(service._apply_worker_decision(db, project, builder, review_task, decision))

        duplicates = list(
            db.scalars(
                select(Task).where(
                    Task.project_id == project.id,
                    Task.title == "Implement the smallest safe code fix",
                )
            )
        )

        assert started == [implementation_task.id]
        assert len(duplicates) == 1
        assert review_task.status == "superseded"
        assert str(implementation_task.id) in (review_task.waiting_reason or "")
        assert implementation_task.status == "working"
    finally:
        db.close()


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


def test_ingest_worker_report_promotes_exploratory_evidence_needs_review_to_done() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Exploratory Evidence Promotion",
            idea="Concrete repro evidence should complete the exploratory task instead of trapping it in a review loop.",
            workspace_path=sample_workspace("exploratory-evidence-promotion"),
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
            name="Service Flow Builder",
            role="Backend specialist",
            archetype="backend",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Clarify Failing Behavior",
            goal="Gather enough evidence to isolate the broken path.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="backend_specialist",
            milestone="Milestone 1 - Reproduce the problem",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused repro."],
            success_criteria_json=["The blocker is clarified."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-exploratory-evidence", status="working")
        db.add(run)
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="needs_review",
            summary="Failed to reproduce the expected test failure. The current implementation in src/math_utils.py returns a - b instead of a + b, and tests/test_math_utils.py expected 5 but got -1.",
            files_changed=[],
            tests_run=["pytest tests/test_math_utils.py"],
            blockers=["Failed to reproduce the expected test failure."],
            risks=["Need clearer evidence before editing."],
            recommended_next_task="Clarify the failing behavior or inspect more files.",
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

        assert task.status == "done"
        assert run.status == "done"
        assert (run.report_json or {}).get("status") == "done"
    finally:
        db.close()


def test_ingest_worker_report_promotes_validation_non_repro_blocked_to_done() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Validation Non Repro Promotion",
            idea="A validation lane that no longer reproduces the old failure should resolve as done.",
            workspace_path=sample_workspace("validation-non-repro-promotion"),
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
            name="Validation Specialist",
            role="Validation Specialist",
            archetype="test",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions.",
            scope="Validation and handoff only.",
            agent_role="Validation Specialist",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation command."],
            success_criteria_json=["Validation is recorded honestly."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-validation-non-repro", status="working")
        db.add(run)
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary="Failed to reproduce the expected test failure.",
            files_changed=[],
            tests_run=["pytest tests/test_math_utils.py"],
            blockers=["Failed to reproduce the expected test failure."],
            risks=[],
            recommended_next_task="Clarify failing behavior.",
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

        assert task.status == "done"
        assert run.status == "done"
        assert (run.report_json or {}).get("status") == "done"
    finally:
        db.close()


def test_ingest_worker_report_promotes_milestone_one_validation_retry_with_failed_repro_evidence() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Milestone One Validation Retry Promotion",
            idea="A milestone-one validation retry that captures the real failing repro should resolve as done instead of looping forever on a bogus environment blocker.",
            workspace_path=sample_workspace("milestone-one-validation-retry-promotion"),
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
            name="Validation Specialist",
            role="Validation Specialist",
            archetype="test",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Install missing dependencies and retry validation",
            goal="Ensure all necessary dependencies are installed before attempting to run the test suite again.",
            scope="Inspect the existing repo, run focused validation, and capture the failure without widening scope.",
            agent_role="Validation Specialist",
            milestone="Milestone 1 - Reproduce the problem",
            allowed_paths_json=["tests/expressions", "tests", "django/db/models"],
            forbidden_paths_json=[],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"],
            success_criteria_json=["The current failure is reproduced or clearly explained."],
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
            process_ref="dry-m1-validation-retry",
            status="working",
        )
        db.add(run)
        db.flush()

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "Reproduced the failure in tests/expressions/tests.py and isolated "
                "django/db/models/sql/compiler.py as the broken path. "
                "Mission Control reran the claimed validation command and it still failed."
            ),
            files_changed=[],
            tests_run=[
                "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            blockers=[
                "Mission Control reran `python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations` and it failed with exit code 1. django.db.utils.OperationalError: near \")\": syntax error"
            ],
            risks=[],
            recommended_next_task="Implement the smallest safe code fix against django/db/models/sql/compiler.py.",
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

        assert task.status == "done"
        assert run.status == "done"
        assert (run.report_json or {}).get("status") == "done"
    finally:
        db.close()


def test_complete_task_by_user_recursively_resolves_follow_up_waiting_reasons(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="User Completion Follow Up Resolution",
            idea="Completing a follow-up task by user should collapse its blocked parent chain instead of leaving stale waiting markers behind.",
            workspace_path=sample_workspace("user-completion-follow-up-resolution"),
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
            status="working",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()
        parent_task = Task(
            project_id=project.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Validation and handoff only.",
            agent_role="handoff_writer",
            milestone="Milestone 3",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation command."],
            success_criteria_json=["Validation is recorded honestly."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        blocked_follow_up = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Clarify Failing Behavior",
            goal="Collect additional evidence to proceed safely.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="handoff_writer",
            milestone="Milestone 3",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed."],
            success_criteria_json=["The blocker is resolved or isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=11,
        )
        leaf_follow_up = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Collect Additional Evidence",
            goal="Gather more context before retrying the validation lane.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="handoff_writer",
            milestone="Milestone 3",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Record what changed."],
            success_criteria_json=["The blocker is resolved or isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            priority=12,
        )
        db.add_all([parent_task, blocked_follow_up, leaf_follow_up])
        db.flush()
        parent_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{blocked_follow_up.id}."
        blocked_follow_up.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{leaf_follow_up.id}."
        worker.current_task_id = leaf_follow_up.id
        run = AgentRun(
            agent_id=worker.id,
            task_id=leaf_follow_up.id,
            runner_type="dry_run",
            process_ref="dry-user-complete-follow-up",
            status="working",
        )
        db.add(run)
        db.flush()

        scheduled_reasons: list[str] = []

        async def fake_finalize_handoff(db, project):
            return None

        monkeypatch.setattr(service, "_maybe_finalize_handoff", fake_finalize_handoff)
        monkeypatch.setattr(
            service,
            "_schedule_orchestration_follow_up",
            lambda db, project, reason: scheduled_reasons.append(reason),
        )

        asyncio.run(service.complete_task_by_user(db, leaf_follow_up))

        assert leaf_follow_up.status == "done"
        assert blocked_follow_up.status == "done"
        assert blocked_follow_up.waiting_reason is None
        assert parent_task.status == "done"
        assert parent_task.waiting_reason is None
        assert worker.status == "waiting"
        assert worker.current_task_id is None
        assert run.status == "stopped"
        assert scheduled_reasons == ["task_completed_by_user"]
    finally:
        db.close()


def test_complete_task_by_user_revives_blocked_implementation_parent_after_follow_up_completion(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Blocked Implementation Parent Revival",
            idea="Completing an exploratory follow-up should return the blocked implementation task to backlog instead of falsely marking it done.",
            workspace_path=sample_workspace("blocked-implementation-parent-revival"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            archetype="backend",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Implementation only.",
            agent_role="backend_specialist",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["src"],
            forbidden_paths_json=["docs", "mission-control"],
            validation_steps_json=["Keep the change narrow."],
            success_criteria_json=["The implementation is correct."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
        )
        inspect_follow_up = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Inspect More Files for Failing Behavior",
            goal="Inspect more files before retrying the code fix.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="handoff_writer",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["src"],
            forbidden_paths_json=["docs", "mission-control"],
            validation_steps_json=["Record what changed."],
            success_criteria_json=["The blocker is resolved or isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="needs_review",
            priority=21,
        )
        validation_task = Task(
            project_id=project.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions.",
            scope="Validation only.",
            agent_role="handoff_writer",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation command."],
            success_criteria_json=["Validation is recorded honestly."],
            estimated_complexity="small",
            dependencies_json=[implementation_task.id],
            status="backlog",
            priority=30,
            waiting_reason="Waiting for task dependencies to finish.",
        )
        db.add_all([implementation_task, inspect_follow_up, validation_task])
        db.flush()
        implementation_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{inspect_follow_up.id}."
        worker.current_task_id = inspect_follow_up.id
        run = AgentRun(
            agent_id=worker.id,
            task_id=inspect_follow_up.id,
            runner_type="dry_run",
            process_ref="dry-implementation-parent-revival",
            status="working",
        )
        db.add(run)
        db.flush()

        scheduled_reasons: list[str] = []

        async def fake_finalize_handoff(db, project):
            return None

        monkeypatch.setattr(service, "_maybe_finalize_handoff", fake_finalize_handoff)
        monkeypatch.setattr(
            service,
            "_schedule_orchestration_follow_up",
            lambda db, project, reason: scheduled_reasons.append(reason),
        )

        asyncio.run(service.complete_task_by_user(db, inspect_follow_up))

        assert inspect_follow_up.status == "done"
        assert implementation_task.status == "working"
        assert implementation_task.assigned_agent_id == worker.id
        assert implementation_task.waiting_reason is None
        assert validation_task.status == "backlog"
        assert validation_task.waiting_reason == "Waiting for task dependencies to finish."
        assert worker.status in {"starting", "working"}
        assert worker.current_task_id == implementation_task.id
        assert run.status == "stopped"
        assert scheduled_reasons == ["task_completed_by_user"]
    finally:
        db.close()


def test_resolve_follow_up_blocked_tasks_requeues_focused_retry_parent_after_clarify_follow_up() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Focused Retry Parent Recovery",
            idea="A clarify-style follow-up must not mark a focused implementation retry done when no code edit happened.",
            workspace_path=sample_workspace("focused-retry-parent-recovery"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        focused_retry_task = Task(
            project_id=project.id,
            title="Focused retry: Implement the smallest safe code fix",
            goal=(
                "Produce a concrete fix for implement the smallest safe code fix inside the existing scoped paths. "
                "Inspect the scoped implementation and related tests before concluding the task is blocked."
            ),
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Validation, docs, and handoff",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["astropy/modeling"],
            forbidden_paths_json=["docs"],
            validation_steps_json=["Confirm the blocker is removed", "Record what changed"],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=21,
        )
        clarify_follow_up = Task(
            project_id=project.id,
            title="Clarify the failing behavior or inspect more files",
            goal="Identify the root cause of the issue before attempting any fixes.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Primary implementation",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["astropy/modeling"],
            forbidden_paths_json=["docs"],
            validation_steps_json=["Confirm the blocker is removed", "Record what changed"],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=22,
        )
        db.add_all([focused_retry_task, clarify_follow_up])
        db.flush()
        focused_retry_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{clarify_follow_up.id}."
        db.flush()

        service._resolve_follow_up_blocked_tasks(db, project, clarify_follow_up)

        assert focused_retry_task.status == "backlog"
        assert focused_retry_task.waiting_reason is None
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


def test_apply_worker_decision_revives_blocked_parent_after_replacement_follow_up(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Replacement Follow Up Recovery",
            idea="A completed replacement follow-up should revive the blocked parent instead of leaving a stale follow-up chain open.",
            workspace_path=sample_workspace("replacement-follow-up-recovery"),
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
        blocked_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the validated failing behavior with the least invasive change.",
            scope="Implementation only.",
            agent_role="Planner specialist",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the diff narrow."],
            success_criteria_json=["The code fix is complete."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
        )
        stale_follow_up = Task(
            project_id=project.id,
            title="Clarify failing behavior",
            goal="Reproduce the failure again before retrying the fix.",
            scope="Focused repro only.",
            agent_role="Planner specialist",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Record the blocker honestly."],
            success_criteria_json=["The blocker is clarified."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=21,
        )
        replacement_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Fix for failing add function",
            goal="Implement the safe replacement fix for the failing add function.",
            scope="Implementation only.",
            agent_role="Planner specialist",
            milestone="Milestone 2",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed."],
            success_criteria_json=["The replacement fix is complete."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=22,
        )
        db.add_all([worker, blocked_task, stale_follow_up, replacement_task])
        db.flush()
        blocked_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{stale_follow_up.id}."
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append(selected_task.id)
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.flush()
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        decision = ManagerWorkerDecision(
            decision_type="assign_next_task",
            summary_markdown="Route the revived fix task back to the worker.",
            task_id=blocked_task.id,
            assign_to_agent_id=worker.id,
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, replacement_task, decision))

        assert started == [blocked_task.id]
        assert blocked_task.status == "working"
        assert blocked_task.waiting_reason is None
        assert stale_follow_up.status == "superseded"
        assert str(replacement_task.id) in (stale_follow_up.waiting_reason or "")
    finally:
        db.close()


def test_apply_worker_decision_retries_same_blocked_task_when_manager_reassigns_it(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Blocked Task Retry Revival",
            idea="A manager-selected same-task retry should revive a blocked task instead of letting it fall into stale backlog reconciliation.",
            workspace_path=sample_workspace("blocked-task-retry-revival"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Focused Fix Runner",
            role="Backend specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        blocked_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Clarify Failing Behavior or Inspect More Files",
            goal="Inspect the focused failing path again and convert the evidence into the next safe edit.",
            scope="Focused repo inspection and safe retry only.",
            agent_role="Backend specialist",
            milestone="Milestone 1",
            allowed_paths_json=["src", "tests"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the next attempt narrow."],
            success_criteria_json=["The retry launches cleanly."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=10,
        )
        db.add_all([worker, blocked_task])
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append(selected_task.id)
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.flush()
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        decision = ManagerWorkerDecision(
            decision_type="assign_next_task",
            summary_markdown="Retry the focused clarify-or-inspect task immediately.",
            task_id=blocked_task.id,
            assign_to_agent_id=worker.id,
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, blocked_task, decision))

        assert started == [blocked_task.id]
        assert blocked_task.status == "working"
        assert blocked_task.waiting_reason is None
        assert blocked_task.assigned_agent_id == worker.id
    finally:
        db.close()


def test_apply_worker_decision_revives_blocked_parent_after_cross_milestone_clarify_completion(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Cross Milestone Clarify Revival",
            idea="A completed clarify lane should be allowed to revive the blocked implementation lane when the manager explicitly routes work back there.",
            workspace_path=sample_workspace("cross-milestone-clarify-revival"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        blocked_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Implementation only.",
            agent_role="Backend specialist",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["src"],
            forbidden_paths_json=["docs", "mission-control"],
            validation_steps_json=["Keep the change narrow."],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=20,
        )
        stale_follow_up = Task(
            project_id=project.id,
            title="Clarify Failing Behavior",
            goal="Reproduce and isolate the smallest broken path to determine a safe code fix.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Primary implementation",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["src"],
            forbidden_paths_json=["docs", "mission-control"],
            validation_steps_json=["Record what changed."],
            success_criteria_json=["The blocker is clarified."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=21,
        )
        clarify_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Clarify the failing behavior or inspect more files",
            goal="Implement the smallest safe code fix after clarifying the failing behavior and isolating the smallest broken path.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Validation, docs, and handoff",
            milestone="Milestone 1 - Reproduce the problem",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed."],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=11,
        )
        db.add_all([worker, blocked_task, stale_follow_up, clarify_task])
        db.flush()
        blocked_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{stale_follow_up.id}."
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, selected_task):
            started.append(selected_task.id)
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.flush()
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        decision = ManagerWorkerDecision(
            decision_type="assign_next_task",
            summary_markdown="The clarify lane produced enough evidence, so route implementation back to the worker.",
            task_id=blocked_task.id,
            assign_to_agent_id=worker.id,
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, clarify_task, decision))

        assert started == [blocked_task.id]
        assert blocked_task.status == "working"
        assert blocked_task.waiting_reason is None
        assert stale_follow_up.status == "superseded"
        assert str(clarify_task.id) in (stale_follow_up.waiting_reason or "")
    finally:
        db.close()


def test_start_idle_agents_supersedes_stale_duplicate_follow_up_after_replacement_completion(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Duplicate Follow Up Recovery",
            idea="A completed replacement follow-up should supersede the stale duplicate follow-up before it relaunches.",
            workspace_path=sample_workspace("duplicate-follow-up-recovery"),
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
        db.add(worker)
        db.flush()
        parent_task = Task(
            project_id=project.id,
            title="Reproduce the failing behavior and isolate the smallest broken path",
            goal="Confirm the current failure locally and identify the narrowest code path that needs a fix.",
            scope="Inspect the existing repo, run focused validation, and capture the failure without widening scope.",
            agent_role="Planner specialist",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused repro."],
            success_criteria_json=["The failure is reproduced cleanly."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
            waiting_reason=f"{service._FOLLOW_UP_BLOCKER_PREFIX}2.",
        )
        stale_follow_up = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Clarify Failing Behavior",
            goal="Gather more evidence to identify the smallest broken path and make a safe edit.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Planner specialist",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Record the blocker honestly."],
            success_criteria_json=["The blocker is clarified."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=11,
        )
        replacement_follow_up = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Clarify Failing Behavior",
            goal="Identify and document the failing behavior in more detail to inform the next steps.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Planner specialist",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Record the clarified evidence."],
            success_criteria_json=["The blocker is clarified."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=12,
        )
        next_task = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Implementation only.",
            agent_role="Planner specialist",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the diff narrow."],
            success_criteria_json=["The code fix is complete."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        db.add_all([parent_task, stale_follow_up, replacement_follow_up, next_task])
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, task):
            started.append(task.id)
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 0
        assert started == []
        assert stale_follow_up.status == "superseded"
        assert stale_follow_up.assigned_agent_id is None
        assert str(replacement_follow_up.id) in (stale_follow_up.waiting_reason or "")
        assert parent_task.status == "done"
        assert parent_task.waiting_reason is None
    finally:
        db.close()


def test_start_idle_agents_supersedes_stale_exploratory_follow_up_after_fix_and_validation_complete(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Exploratory Follow Up Recovery",
            idea="A stale clarify-or-inspect lane should not stay open after the fix and validation lanes are already done.",
            workspace_path=sample_workspace("exploratory-follow-up-recovery"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()
        parent_task = Task(
            project_id=project.id,
            title="Reproduce the failing behavior and isolate the smallest broken path",
            goal="Confirm the current failure locally and identify the narrowest code path that needs a fix.",
            scope="Inspect the existing repo, run focused validation, and capture the failure without widening scope.",
            agent_role="Validation Specialist",
            milestone="Milestone 1 - Reproduce the problem",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the narrowest relevant test command"],
            success_criteria_json=["The failure is reproduced cleanly."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
            waiting_reason="placeholder",
        )
        stale_follow_up = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Clarify Failing Behavior or Inspect More Files",
            goal="Gather more evidence to identify the smallest broken path and make a safe edit.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Validation, docs, and handoff",
            milestone="Milestone 1 - Reproduce the problem",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed", "Record what changed"],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=11,
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure and avoid opportunistic refactors.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["src"],
            forbidden_paths_json=["docs", "mission-control"],
            validation_steps_json=["Keep the change scoped to the validated failure"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[1],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
            agent_role="Service Flow Builder",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation command again"],
            success_criteria_json=["The fix stays green under focused validation."],
            estimated_complexity="small",
            dependencies_json=[2],
            status="done",
            priority=30,
        )
        db.add_all([parent_task, stale_follow_up, implementation_task, validation_task])
        db.flush()
        parent_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{stale_follow_up.id}."
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, task):
            started.append(task.id)
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 0
        assert started == []
        assert stale_follow_up.status == "superseded"
        assert stale_follow_up.assigned_agent_id is None
        assert "accepted downstream completed task" in (stale_follow_up.waiting_reason or "")
        assert parent_task.status == "done"
        assert parent_task.waiting_reason is None
    finally:
        db.close()


def test_start_idle_agents_supersedes_generic_blocker_follow_up_after_fix_progress(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Generic Blocker Follow Up Recovery",
            idea="A stale generic blocker follow-up should not keep the board open after downstream implementation and validation progress land.",
            workspace_path=sample_workspace("generic-blocker-follow-up-recovery"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()
        parent_task = Task(
            project_id=project.id,
            title="Reproduce the failing behavior and isolate the smallest broken path",
            goal="Confirm the current failure locally and identify the narrowest code path that needs a fix.",
            scope="Inspect the existing repo, run focused validation, and capture the failure without widening scope.",
            agent_role="Validation Specialist",
            milestone="Milestone 1",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the narrowest relevant test command"],
            success_criteria_json=["The failure is reproduced cleanly."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
            waiting_reason=f"{service._FOLLOW_UP_BLOCKER_PREFIX}4.",
        )
        stale_follow_up = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Install the missing dependencies and re-run the validation command.",
            goal="Ensure all dependencies are installed and then attempt the focused validation again.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Validation Specialist",
            milestone="Milestone 1",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed", "Record what changed"],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=11,
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure and avoid opportunistic refactors.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["src"],
            forbidden_paths_json=["docs", "mission-control"],
            validation_steps_json=["Keep the change scoped to the validated failure"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[1],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
            agent_role="Service Flow Builder",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation command again"],
            success_criteria_json=["The fix stays green under focused validation."],
            estimated_complexity="small",
            dependencies_json=[2],
            status="done",
            priority=30,
        )
        db.add_all([parent_task, stale_follow_up, implementation_task, validation_task])
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, task):
            started.append(task.id)
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))

        assert started_count == 0
        assert started == []
        assert stale_follow_up.status == "superseded"
        assert stale_follow_up.assigned_agent_id is None
        assert "accepted downstream completed task" in (stale_follow_up.waiting_reason or "")
        assert parent_task.status == "done"
        assert parent_task.waiting_reason is None
    finally:
        db.close()


def test_start_idle_agents_supersedes_completed_parent_follow_up_after_downstream_progress(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Completed Parent Follow Up After Downstream Progress",
            idea="A stale follow-up from an already completed reproduction lane should be superseded once downstream implementation progress is already done.",
            workspace_path=sample_workspace("completed-parent-follow-up-after-downstream-progress"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Test specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()
        parent_task = Task(
            project_id=project.id,
            title="Reproduce the failing behavior and isolate the smallest broken path",
            goal="Confirm the current failure locally and identify the narrowest code path that needs a fix.",
            scope="Inspect the existing repo, run focused validation, and capture the failure without widening scope.",
            agent_role="Validation Specialist",
            milestone="Milestone 1",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the narrowest relevant test command"],
            success_criteria_json=["The failure is reproduced cleanly."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
            waiting_reason=f"{service._FOLLOW_UP_BLOCKER_PREFIX}4.",
        )
        stale_follow_up = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Install Dependencies and Re-run Validation",
            goal="Re-run the focused validation command after dependencies are fixed.",
            scope="Inspect the existing repo, run focused validation, and capture the failure without widening scope.",
            agent_role="Validation Specialist",
            milestone="Milestone 1",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the narrowest relevant test command"],
            success_criteria_json=["The failure is reproduced cleanly."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=11,
        )
        implementation_task = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure and avoid opportunistic refactors.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the change scoped to the validated failure"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests", "src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation command again"],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=30,
            waiting_reason="Waiting for task dependencies to finish.",
        )
        db.add_all([parent_task, stale_follow_up, implementation_task, validation_task])
        db.flush()
        parent_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{stale_follow_up.id}."
        implementation_task.dependencies_json = [parent_task.id]
        validation_task.dependencies_json = [implementation_task.id]
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, task):
            started.append(task.id)
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))
        db.refresh(parent_task)
        db.refresh(stale_follow_up)
        db.refresh(validation_task)

        assert started_count == 1
        assert started == [validation_task.id]
        assert stale_follow_up.status == "superseded"
        assert stale_follow_up.assigned_agent_id is None
        assert "accepted downstream completed task" in (stale_follow_up.waiting_reason or "")
        assert parent_task.waiting_reason is None
        assert validation_task.waiting_reason is None
    finally:
        db.close()


def test_set_waiting_on_paths_preserves_follow_up_marker_for_blocked_parent() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Follow Up Path Wait Preservation",
            idea="Path-conflict bookkeeping should not erase the follow-up linkage for the blocked parent task.",
            workspace_path=sample_workspace("follow-up-path-wait-preservation"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            locked_paths_json=["astropy/modeling/tests", "astropy/modeling"],
        )
        follow_up_task = Task(
            project_id=project.id,
            title="Install Missing Dependencies",
            goal="Ensure dependencies are installed before re-running the focused validation command.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Validation, docs, and handoff",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["astropy/modeling/tests", "astropy/modeling"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed"],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=31,
        )
        parent_task = Task(
            project_id=project.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["astropy/modeling/tests", "astropy/modeling"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation command again"],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[2],
            status="blocked",
            priority=30,
        )
        db.add_all([worker, follow_up_task, parent_task])
        db.flush()
        parent_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}."

        service._set_waiting_on_paths(db, project, parent_task, [worker])

        assert parent_task.status == "waiting_on_paths"
        assert parent_task.waiting_reason == (
            f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}. "
            "Paths still blocked by Service Flow Builder owns astropy/modeling/tests, astropy/modeling"
        )

        worker.locked_paths_json = []
        service._set_waiting_on_paths(db, project, parent_task, [worker])

        assert parent_task.status == "blocked"
        assert parent_task.waiting_reason == f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}."
    finally:
        db.close()


def test_start_idle_agents_requeues_validation_lane_after_blocker_follow_up_completion(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Validation Lane Recovery",
            idea="A completed blocker-removal follow-up should reopen the real validation lane instead of superseding it.",
            workspace_path=sample_workspace("validation-lane-recovery"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Test specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        implementation_task = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["astropy/modeling"],
            forbidden_paths_json=["docs"],
            validation_steps_json=["Keep the change scoped to the validated failure"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["astropy/modeling/tests", "astropy/modeling"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation command again"],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="waiting_on_paths",
            priority=30,
        )
        follow_up_task = Task(
            project_id=project.id,
            title="Install Missing Dependencies",
            goal="Ensure all required dependencies are installed in the local environment before re-running the focused validation command.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Validation, docs, and handoff",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["astropy/modeling/tests", "astropy/modeling"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed", "Record what changed"],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=31,
        )
        db.add_all([worker, implementation_task, validation_task, follow_up_task])
        db.flush()
        validation_task.dependencies_json = [implementation_task.id]
        validation_task.waiting_reason = (
            f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}. "
            "Paths still blocked by Service Flow Builder owns astropy/modeling/tests, astropy/modeling"
        )
        db.flush()

        started: list[int] = []

        async def fake_start_agent_task(db, project, agent, task):
            started.append(task.id)
            return None

        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)

        started_count = asyncio.run(service.start_idle_agents(db, project))
        db.refresh(validation_task)
        db.refresh(follow_up_task)

        assert started_count == 1
        assert started == [validation_task.id]
        assert "Superseded after Mission Control accepted downstream completed task" not in (
            validation_task.waiting_reason or ""
        )
        assert follow_up_task.status == "done"
    finally:
        db.close()


def test_apply_worker_decision_mark_done_supersedes_stale_follow_up_child(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Completed Parent Follow Up Cleanup",
            idea="If a completed validation task still points at an exploratory child follow-up, Mission Control should supersede that stale child immediately.",
            workspace_path=sample_workspace("completed-parent-follow-up-cleanup"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Test specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()
        follow_up_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Clarify Failing Behavior or Inspect More Files",
            goal="Inspect more evidence before continuing.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Validation, docs, and handoff",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed"],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=31,
        )
        parent_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions.",
            scope="Validation only.",
            agent_role="Validation Specialist",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Run the focused validation command again"],
            success_criteria_json=["The fix stays green under focused validation."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=30,
            waiting_reason=f"{service._FOLLOW_UP_BLOCKER_PREFIX}1.",
        )
        db.add_all([follow_up_task, parent_task])
        db.flush()
        parent_task.waiting_reason = f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}."

        decision = ManagerWorkerDecision(
            decision_type="mark_done",
            summary_markdown="Validation completed cleanly.",
            task_id=parent_task.id,
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, parent_task, decision))

        assert parent_task.status == "done"
        assert parent_task.waiting_reason is None
        assert follow_up_task.status == "superseded"
        assert follow_up_task.assigned_agent_id is None
        assert str(parent_task.id) in (follow_up_task.waiting_reason or "")
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


def test_ingest_worker_report_prefers_deterministic_next_assignment_after_done_report(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Done Report Next Assignment",
            idea="A finished reproduction task should advance to the next dependency instead of spawning a stale follow-up.",
            workspace_path=sample_workspace("done-report-next-assignment"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Investigate Bug in separability_matrix",
            goal="Reproduce the failure and isolate the root cause.",
            scope="astropy/modeling/separable.py, astropy/modeling/tests/test_separable.py",
            agent_role="developer",
            milestone="Milestone 1",
            allowed_paths_json=["astropy/modeling/separable.py", "astropy/modeling/tests/test_separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The bug is reproduced."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        next_task = Task(
            project_id=project.id,
            title="Propose a Minimal Safe Patch",
            goal="Generate the smallest safe patch.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["A small safe patch is proposed."],
            estimated_complexity="small",
            dependencies_json=[1],
            status="backlog",
            priority=20,
        )
        db.add_all([worker, task, next_task])
        db.flush()
        worker.current_task_id = task.id
        next_task.dependencies_json = [task.id]
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        async def fake_resolve_manager_model(*args, **kwargs):
            return (
                ManagerWorkerDecision(
                    decision_type="request_fix",
                    summary_markdown="Spawn a stale clarification task.",
                    task_id=task.id,
                    assign_to_agent_id=worker.id,
                    follow_up_title="Clarify Failing Behavior",
                    follow_up_goal="Collect more evidence.",
                ),
                "provider_request_fix",
            )

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, selected_agent, selected_task):
            started.append((selected_agent.id, selected_task.id))
            selected_agent.status = "working"
            selected_agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = selected_agent.id
            db.flush()
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="done",
            summary="Reproduced the failure and isolated astropy/modeling/separable.py as the broken path.",
            files_changed=[],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=[],
            risks=[],
            recommended_next_task="Implement the smallest safe code fix.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        db.refresh(task)
        db.refresh(next_task)

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == next_task.id
        assert started == [(worker.id, next_task.id)]
        assert task.status == "done"
        assert next_task.status == "working"
        assert next_task.assigned_agent_id == worker.id
    finally:
        db.close()


def test_ingest_worker_report_ignores_provider_worker_decision_for_wrong_task(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Wrong Task Worker Decision Guard",
            idea="A provider worker-decision payload must not mutate a different task than the one that just reported.",
            workspace_path=sample_workspace("wrong-task-worker-decision-guard"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        reproduce_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Reproduce the failing behavior and isolate the smallest broken path",
            goal="Confirm the current failure locally and identify the narrowest code path that needs a fix.",
            scope="Inspect the existing repo and capture the failure without widening scope.",
            agent_role="Validation Specialist",
            milestone="Milestone 1 - Reproduce the problem",
            allowed_paths_json=["astropy/modeling/tests", "astropy/modeling"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The failure is reproduced cleanly."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        implementation_task = Task(
            project_id=project.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2 - Fix the code",
            allowed_paths_json=["astropy/modeling"],
            forbidden_paths_json=["docs"],
            validation_steps_json=["Keep the change scoped to the validated failure"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        db.add_all([worker, reproduce_task, implementation_task])
        db.flush()
        worker.current_task_id = reproduce_task.id
        implementation_task.dependencies_json = [reproduce_task.id]
        run = AgentRun(agent_id=worker.id, task_id=reproduce_task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        async def fake_resolve_manager_model(*args, **kwargs):
            return (
                ManagerWorkerDecision(
                    decision_type="request_fix",
                    summary_markdown="Route a fix on the previous task.",
                    task_id=reproduce_task.id,
                    assign_to_agent_id=worker.id,
                    follow_up_title="Implement a Safe Code Fix for Nested CompoundModels",
                    follow_up_goal="Identify the root cause and implement a safe fix.",
                ),
                "provider_request_fix",
            )

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, selected_agent, selected_task):
            started.append((selected_agent.id, selected_task.id))
            selected_agent.status = "working"
            selected_agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = selected_agent.id
            db.flush()
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(reproduce_task.id),
            status="done",
            summary="Reproduced the failure and isolated astropy/modeling/separable.py as the broken path.",
            files_changed=[],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=[],
            risks=[],
            recommended_next_task="Implement the smallest safe code fix.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        db.refresh(reproduce_task)
        db.refresh(implementation_task)

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == implementation_task.id
        assert started == [(worker.id, implementation_task.id)]
        assert reproduce_task.status == "done"
        assert implementation_task.status == "working"
        assert implementation_task.assigned_agent_id == worker.id
    finally:
        db.close()


def test_ingest_worker_report_ignores_provider_request_fix_that_breaks_strategy_retry_lane(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Strategy Retry Lane Guard",
            idea="Provider follow-up decisions must not assign implementation retries to a non-worker or spawn a generic retry lane.",
            workspace_path=sample_workspace("strategy-retry-lane-guard"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
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
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Strategy retry: Implement the smallest safe code fix",
            goal="Rework the fix as a surgical patch.",
            scope="django/db/models/sql/compiler.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql"],
            forbidden_paths_json=[],
            validation_steps_json=["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"],
            success_criteria_json=["The focused validation command passes."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=20,
            failure_count=4,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        worker.current_task_id = task.id
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        async def fake_resolve_manager_model(*args, **kwargs):
            return (
                ManagerWorkerDecision(
                    decision_type="request_fix",
                    summary_markdown="The worker's attempt at fixing the issue was rejected or could not be applied, likely due to a full-file rewrite that is too broad.",
                    task_id=task.id,
                    assign_to_agent_id=manager_agent.id,
                    follow_up_title="Implement smallest safe code fix",
                    follow_up_goal="Revisit and refine the proposed fix to address the rejection and ensure it meets quality standards.",
                    escalation_message="The initial fix attempt was rejected or could not be applied. Please review and provide a revised implementation.",
                ),
                "provider_request_fix",
            )

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary="The targeted retry still could not produce a safe concrete edit.",
            files_changed=[],
            tests_run=[],
            blockers=["The targeted retry still could not produce a safe concrete edit."],
            risks=[],
            recommended_next_task="Review the blocked task.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))

        assert decision.decision_type == "escalate_to_user"
        assert "exhausted repeated surgical retries" in decision.summary_markdown
        assert db.scalar(
            select(Task).where(
                Task.project_id == project.id,
                Task.title == "Implement smallest safe code fix",
            )
        ) is None
    finally:
        db.close()


def test_deterministic_worker_decision_routes_completed_implementation_to_validation_worker() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Cross Worker Validation Handoff",
            idea="A completed implementation task should hand off to the queued validation worker instead of reopening implementation.",
            workspace_path=sample_workspace("cross-worker-validation-handoff"),
            status="building",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
            archetype="test",
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=builder.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql/compiler.py"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again and capture the result.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests", "django/db/models/sql/compiler.py"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "Re-run the focused validation command: python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations",
                "Record pass/fail results and remaining limitations",
            ],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=30,
        )
        db.add_all([builder, validator, implementation_task, validation_task])
        db.flush()
        validation_task.dependencies_json = [implementation_task.id]
        db.flush()

        report = WorkerReport(
            agent=builder.name,
            task_id=str(implementation_task.id),
            status="done",
            summary="Implemented the smallest safe code fix for the order by clause removal issue.",
            files_changed=["django/db/models/sql/compiler.py"],
            tests_run=[],
            blockers=[],
            risks=[],
            recommended_next_task="Re-run focused validation.",
        )

        decision = service._deterministic_worker_decision(db, project, builder, implementation_task, report)

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == validation_task.id
        assert decision.assign_to_agent_id == validator.id
    finally:
        db.close()


def test_ingest_worker_report_overrides_provider_request_fix_with_validation_handoff_after_done_implementation(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Done Implementation Validation Handoff",
            idea="A completed implementation report should hand off to validation even if the provider asks to reopen implementation.",
            workspace_path=sample_workspace("done-implementation-validation-handoff"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
            archetype="test",
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=builder.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql/compiler.py"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again and capture the result.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests", "django/db/models/sql/compiler.py"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "Re-run the focused validation command: python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations",
                "Record pass/fail results and remaining limitations",
            ],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=30,
        )
        db.add_all([builder, validator, implementation_task, validation_task])
        db.flush()
        validation_task.dependencies_json = [implementation_task.id]
        db.flush()
        builder.current_task_id = implementation_task.id
        run = AgentRun(agent_id=builder.id, task_id=implementation_task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        async def fake_resolve_manager_model(*args, **kwargs):
            return (
                ManagerWorkerDecision(
                    decision_type="request_fix",
                    summary_markdown="Reopen implementation and try a more robust change.",
                    task_id=implementation_task.id,
                    assign_to_agent_id=builder.id,
                    follow_up_title="Focused retry: Implement the smallest safe code fix",
                    follow_up_goal="Retry the implementation lane with a different fix.",
                ),
                "provider_request_fix",
            )

        async def fake_start_agent_task(db, project, agent, selected_task):
            agent.status = "working"
            agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = agent.id
            db.flush()
            return AgentRun(agent_id=agent.id, task_id=selected_task.id, runner_type="dry_run", process_ref="follow-up", status="working")

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=builder.name,
            task_id=str(implementation_task.id),
            status="done",
            summary="Implemented the smallest safe code fix for the order by clause removal issue.",
            files_changed=["django/db/models/sql/compiler.py"],
            tests_run=[],
            blockers=[],
            risks=[],
            recommended_next_task="Re-run focused validation.",
        )
        envelope = service._build_runner_result_envelope_from_report(run, implementation_task, report)

        decision = asyncio.run(service.ingest_worker_report(db, run, report, envelope=envelope))
        db.refresh(implementation_task)
        db.refresh(validation_task)
        db.refresh(validator)

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == validation_task.id
        assert decision.assign_to_agent_id == validator.id
        assert implementation_task.status == "done"
        assert validation_task.status == "working"
        assert validation_task.assigned_agent_id == validator.id
        assert validator.current_task_id == validation_task.id
    finally:
        db.close()


def test_ingest_worker_report_starts_strategy_retry_follow_up_after_repeated_zero_edit_blocker(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Strategy Retry Immediate Launch",
            idea="A repeated blocked implementation run should create and immediately start the strategy retry follow-up.",
            workspace_path=sample_workspace("strategy-retry-immediate-launch"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Backend specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="django/db/models/sql/compiler.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql/compiler.py"],
            forbidden_paths_json=["tests"],
            validation_steps_json=[
                "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=20,
            failure_count=1,
        )
        db.add_all([worker, task])
        db.flush()
        worker.current_task_id = task.id
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        started: list[int] = []

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("Provider decision should be skipped for repeated zero-edit blockers.")

        async def fake_start_agent_task(db, project, selected_agent, selected_task):
            started.append(selected_task.id)
            selected_agent.status = "working"
            selected_agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = selected_agent.id
            db.flush()
            return AgentRun(agent_id=selected_agent.id, task_id=selected_task.id, runner_type="dry_run", process_ref="follow-up", status="working")

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fail_if_called)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "Mission Control executed the required validation command locally and it failed. "
                "Mission Control reran the claimed validation command and it still failed."
            ),
            files_changed=[],
            tests_run=[
                "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            blockers=[
                "Required validation command failed with exit code 1: python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            risks=[
                "Mission Control could not verify any workspace file changes for this claimed implementation step.",
                "Mission Control rejected this as a no-change review gate because the task requires verified changed files.",
            ],
            recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
        )
        envelope = service._build_runner_result_envelope_from_report(run, task, report)

        decision = asyncio.run(service.ingest_worker_report(db, run, report, envelope=envelope))
        db.refresh(task)
        db.refresh(worker)

        follow_up = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.title == "Strategy retry: Implement the smallest safe code fix")
            .order_by(Task.id.desc())
        )

        assert decision.decision_type == "request_fix"
        assert follow_up is not None
        assert started == [follow_up.id]
        assert follow_up.status == "working"
        assert follow_up.assigned_agent_id == worker.id
        assert worker.current_task_id == follow_up.id
        assert task.waiting_reason == f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up.id}."
    finally:
        db.close()


def test_ingest_worker_report_creates_distinct_focused_retry_child_from_strategy_retry(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Strategy Retry Focused Child Guard",
            idea="A blocked strategy retry should spawn a distinct focused retry child instead of reusing the same task.",
            workspace_path=sample_workspace("strategy-retry-focused-child-guard"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Strategy retry: Implement the smallest safe code fix",
            goal="Rework the fix as a surgical patch.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The failing tests pass."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=20,
            failure_count=0,
        )
        db.add_all([worker, task])
        db.flush()
        worker.current_task_id = task.id
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        started: list[int] = []

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("Provider decision should be skipped for strategy-retry zero-edit blockers.")

        async def fake_start_agent_task(db, project, selected_agent, selected_task):
            started.append(selected_task.id)
            selected_agent.status = "working"
            selected_agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = selected_agent.id
            db.flush()
            return AgentRun(agent_id=selected_agent.id, task_id=selected_task.id, runner_type="dry_run", process_ref="follow-up", status="working")

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fail_if_called)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "Mission Control executed the required validation command locally and it failed. "
                "Mission Control reran the claimed validation command and it still failed."
            ),
            files_changed=[],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=[
                "Required validation command failed with exit code 1: python -m pytest astropy/modeling/tests/test_separable.py -q"
            ],
            risks=[
                "Mission Control could not verify any workspace file changes for this claimed implementation step.",
                "Mission Control rejected this as a no-change review gate because the task requires verified changed files.",
            ],
            recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
        )
        envelope = service._build_runner_result_envelope_from_report(run, task, report)

        decision = asyncio.run(service.ingest_worker_report(db, run, report, envelope=envelope))
        db.refresh(task)
        db.refresh(worker)

        follow_up = db.scalar(
            select(Task)
            .where(
                Task.project_id == project.id,
                Task.title == "Focused retry: Implement the smallest safe code fix",
            )
            .order_by(Task.id.desc())
        )

        assert decision.decision_type == "request_fix"
        assert follow_up is not None
        assert follow_up.id != task.id
        assert started == [follow_up.id]
        assert follow_up.status == "working"
        assert follow_up.assigned_agent_id == worker.id
        assert worker.current_task_id == follow_up.id
        assert task.status == "blocked"
        assert task.waiting_reason == f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up.id}."
    finally:
        db.close()


def test_ingest_worker_report_bypasses_provider_for_no_change_fix_blocker(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="No Change Fix Guardrail",
            idea="Skip the extra manager-model turn when a fix task comes back blocked with zero verified edits.",
            workspace_path=sample_workspace("no-change-fix-guardrail"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Develop a patch",
            goal="Create the smallest safe code fix.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The failing tests pass."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("Provider decision should be skipped for no-change fix blockers.")

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fail_if_called)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "Unable to reproduce the reported bug in the separability_matrix function for nested models. "
                "Mission Control rejected this as a no-change review gate because the task requires verified changed files."
            ),
            files_changed=[],
            tests_run=[],
            blockers=[
                "No verified workspace file changes were produced for a task that requires a concrete fix.",
                "Cannot reproduce the behavior without additional context.",
            ],
            risks=["Mission Control could not verify any workspace file changes for this run."],
            recommended_next_task="Use the provided issue evidence and implement the smallest safe patch.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        db.flush()

        follow_up_task = db.scalar(
            select(Task).where(
                Task.project_id == project.id,
                Task.title == "Focused retry: Develop a patch",
            )
        )
        assert decision.decision_type == "request_fix"
        assert follow_up_task is not None
        assert follow_up_task.allowed_paths_json == ["astropy/modeling/separable.py"]
        assert follow_up_task.scope == "astropy/modeling/separable.py"
        assert follow_up_task.agent_role == "developer"
        assert follow_up_task.validation_steps_json == ["python -m pytest astropy/modeling/tests/test_separable.py -q"]
        assert follow_up_task.success_criteria_json == ["The failing tests pass."]
        assert "Do not return an analysis-only report" in follow_up_task.goal
        assert "do not claim the symbol only exists in a test file" in follow_up_task.goal.lower()
        assert task.waiting_reason == f"{service._FOLLOW_UP_BLOCKER_PREFIX}{follow_up_task.id}."
    finally:
        db.close()


def test_ingest_worker_report_retries_focused_retry_task_without_provider(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Focused Retry Guardrail",
            idea="A blocked focused retry task should be retried in place without another provider decision turn.",
            workspace_path=sample_workspace("focused-retry-guardrail"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Focused retry: Develop a patch",
            goal="Produce a concrete fix inside the scoped paths.",
            scope="astropy/modeling/separable.py",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The failing tests pass."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([worker, task])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("Provider decision should be skipped for focused retry zero-edit blockers.")

        async def fake_start_agent_task(db, project, selected_agent, selected_task):
            selected_agent.status = "working"
            selected_agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = selected_agent.id
            db.flush()
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fail_if_called)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary="The separability_matrix function still appears incorrect for nested CompoundModels.",
            files_changed=[],
            tests_run=[],
            blockers=["Incorrect implementation of separability_matrix for nested CompoundModels."],
            risks=[],
            recommended_next_task="Clarify the failing behavior or inspect more files.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        db.refresh(task)
        db.refresh(worker)

        assert decision.decision_type == "request_fix"
        assert task.status == "working"
        assert task.assigned_agent_id == worker.id
        assert worker.current_task_id == task.id
    finally:
        db.close()


def test_ingest_worker_report_bypasses_provider_for_blocked_validation_repair_loop(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Blocked Validation Guardrail",
            idea="A blocked validation lane with test evidence should reopen implementation without another provider decision turn.",
            workspace_path=sample_workspace("blocked-validation-guardrail"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="test",
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=builder.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling/separable.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["astropy/modeling/tests", "astropy/modeling"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=30,
        )
        db.add_all([builder, validator, implementation_task, validation_task])
        db.flush()
        validation_task.dependencies_json = [implementation_task.id]
        run = AgentRun(agent_id=validator.id, task_id=validation_task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("Provider decision should be skipped for blocked validation repair loops.")

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, selected_agent, selected_task):
            started.append((selected_agent.id, selected_task.id))
            selected_agent.status = "working"
            selected_agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = selected_agent.id
            db.flush()
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fail_if_called)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=validator.name,
            task_id=str(validation_task.id),
            status="blocked",
            summary="Focused validation stayed blocked after re-running the test command.",
            files_changed=[],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=["Validation failed after the last implementation attempt."],
            risks=[],
            recommended_next_task="Reopen the implementation task and repair the broken path.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        db.refresh(builder)
        db.refresh(validator)
        db.refresh(implementation_task)
        db.refresh(validation_task)

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == implementation_task.id
        assert started == [(builder.id, implementation_task.id)]
        assert implementation_task.status == "working"
        assert implementation_task.assigned_agent_id == builder.id
        assert validation_task.status == "backlog"
        assert validation_task.assigned_agent_id is None
        assert validation_task.waiting_reason == "Waiting for task dependencies to finish."
    finally:
        db.close()


def test_ingest_worker_report_bypasses_provider_for_concrete_validation_rerun_despite_stale_dependency_claim(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Concrete Validation Rerun Guardrail",
            idea="A stale dependency claim must not suppress the deterministic repair loop once Mission Control recorded concrete rerun failure evidence.",
            workspace_path=sample_workspace("concrete-validation-rerun-guardrail"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="test",
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=builder.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql/compiler.py"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests/expressions", "tests", "django/db/models"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=30,
        )
        db.add_all([builder, validator, implementation_task, validation_task])
        db.flush()
        validation_task.dependencies_json = [implementation_task.id]
        run = AgentRun(
            agent_id=validator.id,
            task_id=validation_task.id,
            runner_type="dry_run",
            process_ref="dry-concrete-validation-rerun",
            status="working",
        )
        db.add(run)
        db.commit()

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("Provider decision should be skipped once concrete rerun failure evidence exists.")

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, selected_agent, selected_task):
            started.append((selected_agent.id, selected_task.id))
            selected_agent.status = "working"
            selected_agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = selected_agent.id
            db.flush()
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fail_if_called)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)

        report = WorkerReport(
            agent=validator.name,
            task_id=str(validation_task.id),
            status="blocked",
            summary=(
                "The required validation command failed because of missing dependencies. "
                "Mission Control reran the claimed validation command and it still failed."
            ),
            files_changed=[],
            tests_run=[
                "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            blockers=[
                (
                    "Mission Control reran `python tests/runtests.py --settings=test_sqlite "
                    "expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql "
                    "expressions.tests.BasicExpressionsTests.test_order_of_operations` and it failed with exit code 1. "
                    "ERROR: test_order_by_multiline_sql Traceback django.db.utils.OperationalError: near \")\": syntax error"
                ),
                "Missing dependencies",
            ],
            risks=[],
            recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        db.refresh(builder)
        db.refresh(validator)
        db.refresh(implementation_task)
        db.refresh(validation_task)

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == implementation_task.id
        assert started == [(builder.id, implementation_task.id)]
        assert implementation_task.status == "working"
        assert implementation_task.assigned_agent_id == builder.id
        assert validation_task.status == "backlog"
        assert validation_task.assigned_agent_id is None
        assert validation_task.waiting_reason == "Waiting for task dependencies to finish."
    finally:
        db.close()


def test_ingest_worker_report_replays_task_validation_step_and_reopens_implementation(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        workspace = Path(sample_workspace("validation-step-replay-repair-loop"))
        workspace.mkdir(parents=True, exist_ok=True)
        project = Project(
            name="Validation Step Replay Repair Loop",
            idea="A validation lane that forgot to report its command should still replay the task validation step and reopen implementation on concrete failed evidence.",
            workspace_path=str(workspace),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        builder = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        validator = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="test",
        )
        implementation_task = Task(
            project_id=project.id,
            assigned_agent_id=builder.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["django/db/models/sql", "tests/expressions", "tests"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the change scoped to the validated failure."],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        validation_task = Task(
            project_id=project.id,
            assigned_agent_id=validator.id,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            scope="Run the relevant checks again and prepare the handoff evidence.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests/expressions", "tests", "django/db/models"],
            forbidden_paths_json=[],
            validation_steps_json=[
                "Re-run the focused validation command: python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
            ],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=30,
        )
        db.add_all([builder, validator, implementation_task, validation_task])
        db.flush()
        validation_task.dependencies_json = [implementation_task.id]
        run = AgentRun(agent_id=validator.id, task_id=validation_task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("Provider decision should be skipped when validation-step replay yields concrete failed evidence.")

        started: list[tuple[int, int]] = []

        async def fake_start_agent_task(db, project, selected_agent, selected_task):
            started.append((selected_agent.id, selected_task.id))
            selected_agent.status = "working"
            selected_agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = selected_agent.id
            db.flush()
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        def fake_run(*args, **kwargs):
            return SimpleNamespace(returncode=1, stdout="", stderr="AssertionError: still failing")

        monkeypatch.setattr(service, "_resolve_manager_model", fail_if_called)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)
        monkeypatch.setattr(subprocess, "run", fake_run)

        report = WorkerReport(
            agent=validator.name,
            task_id=str(validation_task.id),
            status="blocked",
            summary="The required validation command cannot be executed because the environment is missing dependencies.",
            files_changed=[],
            tests_run=[],
            blockers=["Missing Django settings"],
            risks=[],
            recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        db.refresh(builder)
        db.refresh(validator)
        db.refresh(implementation_task)
        db.refresh(validation_task)
        db.refresh(run)

        assert decision.decision_type == "assign_next_task"
        assert decision.task_id == implementation_task.id
        assert started == [(builder.id, implementation_task.id)]
        assert implementation_task.status == "working"
        assert implementation_task.assigned_agent_id == builder.id
        assert validation_task.status == "backlog"
        assert validation_task.assigned_agent_id is None
        assert validation_task.waiting_reason == "Waiting for task dependencies to finish."
        assert "reran the claimed validation command and it still failed" in (run.report_json or {}).get("summary", "").lower()
        assert (run.report_json or {}).get("tests_run") == [
            "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations"
        ]
    finally:
        db.close()


def test_ingest_worker_report_bypasses_provider_for_failed_validation_rerun_retry(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Implementation Validation Retry Guardrail",
            idea="A claimed implementation fix that still fails rerun validation should trigger a focused retry without another provider turn.",
            workspace_path=sample_workspace("implementation-validation-retry-guardrail"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Service Flow Builder",
            role="Primary implementation",
            kind="worker",
            status="working",
            workspace_path=project.workspace_path,
            archetype="backend",
        )
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Implement the smallest safe code fix",
            goal="Correct the confirmed failing behavior with the least invasive code change.",
            scope="Update only the implementation paths needed for the validated failure.",
            agent_role="developer",
            milestone="Milestone 2",
            allowed_paths_json=["astropy/modeling"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            success_criteria_json=["The implementation matches the expected behavior."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=20,
        )
        db.add_all([worker, task])
        db.flush()
        run = AgentRun(agent_id=worker.id, task_id=task.id, runner_type="dry_run", process_ref="dry-run", status="working")
        db.add(run)
        db.commit()

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("Provider decision should be skipped for failed validation rerun retries.")

        async def fake_start_agent_task(db, project, selected_agent, selected_task):
            selected_agent.status = "working"
            selected_agent.current_task_id = selected_task.id
            selected_task.status = "working"
            selected_task.assigned_agent_id = selected_agent.id
            db.flush()
            return None

        async def fake_start_idle_agents(db, project):
            return 0

        monkeypatch.setattr(service, "_resolve_manager_model", fail_if_called)
        monkeypatch.setattr(service, "start_agent_task", fake_start_agent_task)
        monkeypatch.setattr(service, "start_idle_agents", fake_start_idle_agents)
        monkeypatch.setattr(
            service,
            "_verify_worker_report_evidence",
            lambda project, task, report, before_snapshot, **kwargs: report,
        )
        monkeypatch.setattr(
            service,
            "_verify_worker_report_validation_claims",
            lambda project, task, report, **kwargs: report,
        )
        monkeypatch.setattr(service, "_convert_no_change_review_to_blocked", lambda task, report: report)

        report = WorkerReport(
            agent=worker.name,
            task_id=str(task.id),
            status="blocked",
            summary=(
                "Corrected the separability_matrix function to ensure proper handling of nested CompoundModels. "
                "Mission Control reran the claimed validation command and it still failed."
            ),
            files_changed=["astropy/modeling/separable.py"],
            tests_run=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            blockers=["Mission Control reran `python -m pytest astropy/modeling/tests/test_separable.py -q` and it failed with exit code 2."],
            risks=[],
            recommended_next_task="Inspect the failed validation output, repair the implementation, and rerun the focused validation command.",
        )

        decision = asyncio.run(service.ingest_worker_report(db, run, report))
        db.refresh(worker)
        db.refresh(task)

        focused_retry = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.title == "Focused retry: Implement the smallest safe code fix")
            .order_by(Task.id.desc())
        )

        assert decision.decision_type == "request_fix"
        if focused_retry is not None:
            assert focused_retry.status == "working"
            assert focused_retry.assigned_agent_id == worker.id
            assert worker.current_task_id == focused_retry.id
        else:
            assert task.status == "working"
            assert task.assigned_agent_id == worker.id
            assert worker.current_task_id == task.id
    finally:
        db.close()


def test_agent_task_match_score_treats_operator_role_as_implementation_lane() -> None:
    service = MissionControlService()

    agent = Agent(
        project_id=1,
        name="Service Flow Builder",
        role="Backend specialist",
        kind="worker",
        status="idle",
        workspace_path=sample_workspace("operator-role-match"),
        archetype="backend",
    )
    task = Task(
        project_id=1,
        title="Analyze the existing separability_matrix implementation",
        goal="Understand the implementation.",
        scope="astropy/modeling/separable.py",
        agent_role="Operator",
        milestone="Milestone 1",
        allowed_paths_json=["astropy/modeling/separable.py"],
        forbidden_paths_json=[],
        validation_steps_json=[],
        success_criteria_json=["done"],
        estimated_complexity="small",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    assert service._agent_task_match_score(agent, task) > 0


def test_upsert_tasks_from_decomposition_prunes_forbidden_globs_that_cover_allowed_paths() -> None:
    from db import init_db

    service = MissionControlService()
    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Prune Conflicting Forbidden Paths",
            idea="Do not generate self-contradictory task path ownership.",
            workspace_path=sample_workspace("prune-conflicting-forbidden-paths"),
            status="building",
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()

        decomposition = ManagerTaskDecomposition(
            summary_markdown="Create a single implementation task.",
            milestones=["Milestone 1"],
            tasks=[
                ManagerTaskItem(
                    title="Update separability_matrix implementation",
                    goal="Modify astropy/modeling/separable.py safely.",
                    scope="Update only the implementation file.",
                    agent_role="Developer",
                    milestone="Milestone 1",
                    priority=10,
                    allowed_paths=["astropy/modeling/separable.py"],
                    forbidden_paths=["astropy/*", "docs/**"],
                    validation_steps=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                    success_criteria=["The implementation path remains editable."],
                    estimated_complexity="small",
                    dependencies=[],
                    status="backlog",
                )
            ],
        )

        tasks = service._upsert_tasks_from_decomposition(db, project, decomposition)
        db.flush()

        assert len(tasks) == 1
        assert tasks[0].allowed_paths_json == ["astropy/modeling/separable.py"]
        assert tasks[0].forbidden_paths_json == ["docs/**"]
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
        worker.current_task_id = task.id
        worker.locked_paths_json = ["src"]
        db.add(PathReservation(project_id=project.id, task_id=task.id, agent_id=worker.id, path="src"))
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
        assert worker.locked_paths_json == []
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


def test_apply_worker_decision_ignores_stale_request_fix_after_completed_handoff_task() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Ignore Stale Post Handoff Follow Up",
            idea="Do not create a new exploratory follow-up after the source task is already done and the project is handoff ready.",
            workspace_path=sample_workspace("ignore-stale-post-handoff-follow-up"),
            status="handoff_ready",
            runner_mode="dry_run",
            manager_mode="deterministic",
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            archetype="test",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        completed_task = Task(
            project_id=project.id,
            title="Clarify Failing Behavior",
            goal="Collect more information before attempting any edits.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Validation Specialist",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Record what changed."],
            success_criteria_json=["The blocker is resolved or isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=31,
        )
        db.add_all([worker, completed_task])
        db.flush()

        decision = ManagerWorkerDecision(
            decision_type="request_fix",
            summary_markdown="Spawn another clarify lane.",
            task_id=completed_task.id,
            assign_to_agent_id=worker.id,
            follow_up_title="Examine Additional Evidence",
            follow_up_goal="Collect more evidence before editing.",
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, completed_task, decision))

        spawned_follow_ups = list(
            db.scalars(
                select(Task).where(
                    Task.project_id == project.id,
                    Task.id != completed_task.id,
                )
            )
        )

        assert spawned_follow_ups == []
        assert completed_task.status == "done"
        assert worker.status == "waiting"
        assert "ignored a stale follow-up decision" in (worker.current_action or "").lower()
    finally:
        db.close()


def test_apply_worker_decision_supersedes_late_exploratory_task_after_handoff_ready() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Supersede Late Exploratory Task",
            idea="Do not let a late clarify lane keep the board open after handoff readiness.",
            workspace_path=sample_workspace("supersede-late-exploratory-task"),
            status="handoff_ready",
            runner_mode="dry_run",
            manager_mode="deterministic",
            final_report_json={"summary_markdown": "Ready for review."},
        )
        db.add(project)
        db.flush()
        worker = Agent(
            project_id=project.id,
            name="Validation Specialist",
            role="Validation Specialist",
            archetype="test",
            kind="worker",
            status="waiting",
            workspace_path=project.workspace_path,
        )
        exploratory_task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Clarify Failing Behavior or Inspect More Files",
            goal="Gather more evidence before attempting further edits.",
            scope="Resolve a blocker or error before the main flow can continue.",
            agent_role="Validation, docs, and handoff",
            milestone="Milestone 3 - Validate and hand off",
            allowed_paths_json=["tests", "src", "docs", "mission-control"],
            forbidden_paths_json=[],
            validation_steps_json=["Confirm the blocker is removed."],
            success_criteria_json=["The blocking issue is resolved or clearly isolated."],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=31,
        )
        db.add_all([worker, exploratory_task])
        db.flush()

        decision = ManagerWorkerDecision(
            decision_type="mark_blocked",
            summary_markdown="Still blocked.",
            task_id=exploratory_task.id,
        )

        asyncio.run(service._apply_worker_decision(db, project, worker, exploratory_task, decision))

        assert exploratory_task.status == "superseded"
        assert exploratory_task.assigned_agent_id is None
        assert "handoff-ready" in (exploratory_task.waiting_reason or "").lower()
        assert worker.status == "waiting"
        assert "handoff-ready" in (worker.current_action or "").lower()
    finally:
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
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "screenshots").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "coverage").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "traces").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "logs").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "inputs").mkdir(parents=True, exist_ok=True)
        (workspace / "README.md").write_text("remote exec demo\n", encoding="utf-8")
        (workspace / "artifacts" / "inputs" / "suite.json").write_text("{\"suite\":true}\n", encoding="utf-8")
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
        request_root = workspace / "artifacts" / "remote-execution-requests" / "remote-exec-1700000000002"
        request_root.mkdir(parents=True, exist_ok=True)
        execution_request_path = request_root / "execution-request.json"
        approval_binding_path = request_root / "approval-binding.json"
        result_bundle_path = request_root / "result-bundle.json"
        transfer_bundle_path = request_root / "transfer-bundle.json"
        execution_request_path.write_text(
            json.dumps(
                {
                    "request_id": "remote-exec-1700000000002",
                    "request_status": "ready",
                    "target_id": "browser-box",
                    "selected_target_id": "browser-box",
                    "selected_target_probe_status": "ready",
                    "required_runner_family": "external_adapter",
                    "transport": "tailscale_ssh",
                    "host": "browser-box.tailnet.ts.net",
                    "remote_workspace_root": "/srv/browser-work",
                    "runner_command": "python3",
                    "runner_args": ["/opt/mission-control/adapter.py"],
                    "adapter_command": "python3",
                    "adapter_args": ["/opt/mission-control/adapter.py"],
                    "dry_run": False,
                    "write_intent": False,
                    "approval_required": False,
                    "approval_id": None,
                    "approval_status": None,
                    "availability_diagnostics": {
                        "summary": "Browser box is ready for governed execution.",
                        "has_blockers": False,
                    },
                    "selected_target_requirement_gaps": {"toolchains": ["cuda12"]},
                    "selected_target_rejected_reasons": ["plain_ssh_missing_policy_match"],
                    "execution_request_path": "artifacts/remote-execution-requests/remote-exec-1700000000002/execution-request.json",
                    "approval_binding_path": "artifacts/remote-execution-requests/remote-exec-1700000000002/approval-binding.json",
                    "result_bundle_path": "artifacts/remote-execution-requests/remote-exec-1700000000002/result-bundle.json",
                    "transfer_bundle_path": "artifacts/remote-execution-requests/remote-exec-1700000000002/transfer-bundle.json",
                    "blocking_reasons": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        approval_binding_path.write_text(
            json.dumps(
                {
                    "request_id": "remote-exec-1700000000002",
                    "approval_required": False,
                    "approval_id": None,
                    "approval_status": None,
                    "runner_ref": None,
                    "resolved_for_execution": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        result_bundle_path.write_text(
            json.dumps(
                {
                    "request_id": "remote-exec-1700000000002",
                    "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                    "expected_evidence_categories": ["logs", "coverage", "screenshots", "traces"],
                    "session_recording_required": True,
                    "session_recording_enabled": True,
                    "session_recording_artifact_paths": [
                        "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
                    ],
                    "remote_session_recording_artifact_paths": [
                        "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
                    ],
                    "remote_artifact_paths": ["/srv/browser-work/artifacts/inputs/suite.json"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        staged_bytes = (workspace / "artifacts" / "inputs" / "suite.json").stat().st_size
        transfer_bundle_path.write_text(
            json.dumps(
                {
                    "request_id": "remote-exec-1700000000002",
                    "target_id": "browser-box",
                    "request_status": "ready",
                    "target_file_transfer_quota_bytes": 4 * 1024 * 1024,
                    "staged_outbound_artifacts": [
                        {
                            "local_path": "artifacts/inputs/suite.json",
                            "remote_path": "/srv/browser-work/artifacts/inputs/suite.json",
                            "bytes": staged_bytes,
                            "status": "staged",
                        }
                    ],
                    "staged_outbound_transfer_bytes": staged_bytes,
                    "staged_outbound_transfer_mb": 0.0,
                    "staged_outbound_transfer_path_count": 1,
                    "staged_outbound_missing_paths": [],
                    "declared_result_collection": [
                        {
                            "local_path": "artifacts/remote-execution-governance/session-recordings/browser-box.cast",
                            "remote_path": "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast",
                            "collection_stage": "remote_session_recording",
                        },
                        {
                            "local_path": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                            "remote_path": None,
                            "collection_stage": "normalized_summary",
                        },
                    ],
                    "declared_result_collection_count": 2,
                    "transfer_quota_status": "ready",
                    "preflight_ready": True,
                    "blocking_reasons": [],
                    "status": "dispatched",
                    "notes": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
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
                        "session_recording_artifact_paths": [
                            "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
                        ],
                        "remote_session_recording_artifact_paths": [
                            "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
                        ],
                    },
                    "execution_request": {
                        "request_id": "remote-exec-1700000000002",
                        "request_status": "ready",
                        "target_id": "browser-box",
                        "selected_target_probe_status": "ready",
                        "availability_diagnostics": {
                            "summary": "Browser box is ready for governed execution.",
                            "has_blockers": False,
                        },
                        "selected_target_requirement_gaps": {"toolchains": ["cuda12"]},
                        "selected_target_rejected_reasons": ["plain_ssh_missing_policy_match"],
                        "execution_request_path": execution_request_path.relative_to(workspace).as_posix(),
                        "approval_binding_path": approval_binding_path.relative_to(workspace).as_posix(),
                        "result_bundle_path": result_bundle_path.relative_to(workspace).as_posix(),
                        "transfer_bundle_path": transfer_bundle_path.relative_to(workspace).as_posix(),
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
        events = db.query(ProjectEvent).filter(ProjectEvent.project_id == project.id).all()

        assert payload["summary_count"] == 1
        assert payload["passed_count"] == 1
        assert payload["failed_count"] == 0
        assert payload["expected_evidence_categories"] == ["logs", "coverage", "screenshots", "traces"]
        assert payload["observed_evidence_categories"] == ["logs", "screenshots", "traces", "coverage"]
        assert payload["latest_run_id"] == run.id
        assert payload["latest_report_status"] == "done"
        assert payload["latest_selected_target_probe_status"] == "ready"
        assert payload["latest_availability_diagnostics"]["summary"] == (
            "Browser box is ready for governed execution."
        )
        assert payload["latest_selected_target_requirement_gaps"] == {"toolchains": ["cuda12"]}
        assert payload["latest_selected_target_rejected_reasons"] == ["plain_ssh_missing_policy_match"]
        assert payload["summaries"][0]["selected_target_id"] == "browser-box"
        assert payload["summaries"][0]["selected_target_probe_status"] == "ready"
        assert payload["summaries"][0]["availability_diagnostics"]["summary"] == (
            "Browser box is ready for governed execution."
        )
        assert payload["summaries"][0]["selected_target_requirement_gaps"] == {"toolchains": ["cuda12"]}
        assert payload["summaries"][0]["selected_target_rejected_reasons"] == [
            "plain_ssh_missing_policy_match"
        ]
        assert payload["summaries"][0]["observed_evidence_categories"] == ["logs", "screenshots", "traces", "coverage"]
        transfer_payload = json.loads(transfer_bundle_path.read_text(encoding="utf-8"))
        assert transfer_payload["broker_result_collection_status"] == "blocked"
        assert transfer_payload["required_result_artifact_count"] == 2
        assert transfer_payload["collected_result_artifact_count"] == 1
        assert transfer_payload["missing_result_artifact_paths"] == [
            "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
        ]
        assert transfer_payload["required_missing_result_artifact_paths"] == [
            "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
        ]
        assert transfer_payload["optional_missing_result_artifact_paths"] == []
        assert transfer_payload["collected_result_artifacts"][1]["local_path"] == (
            "artifacts/remote-execution-governance/normalized-execution-summary.json"
        )
        assert transfer_payload["collected_result_artifacts"][1]["status"] == "collected"
        assert transfer_payload["collected_result_transfer_bytes"] == artifact_path.stat().st_size
        assert transfer_payload["actual_total_known_transfer_bytes"] == staged_bytes + artifact_path.stat().st_size
        assert transfer_payload["final_transfer_status"] == "blocked"
        assert transfer_payload["status"] == "blocked"
        assert transfer_payload["report_status"] == "done"
        assert "required_result_artifact_missing_after_remote_execution" in transfer_payload["blocking_reasons"]
        collection_event = next(
            event for event in events if event.event_type == "remote_execution.result_collection_completed"
        )
        assert collection_event.payload_json["broker_result_collection_status"] == "blocked"
        reconcile_event = next(
            event for event in events if event.event_type == "remote_execution.transfer_reconciled"
        )
        assert reconcile_event.payload_json["request_id"] == "remote-exec-1700000000002"
        assert reconcile_event.payload_json["final_transfer_status"] == "blocked"
        assert reconcile_event.payload_json["collected_result_artifact_count"] == 1
        assert reconcile_event.payload_json["missing_result_artifact_paths"] == [
            "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
        ]
        assert reconcile_event.payload_json["collected_result_transfer_bytes"] == artifact_path.stat().st_size
    finally:
        db.close()


def test_ingest_worker_report_collects_remote_result_artifacts_into_governed_paths(monkeypatch) -> None:
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
        workspace = Path(sample_workspace("remote-exec-governed-result-collection"))
        (workspace / "artifacts" / "inbox").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "logs").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "coverage").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "traces").mkdir(parents=True, exist_ok=True)
        (workspace / "README.md").write_text("remote exec collection demo\n", encoding="utf-8")
        (workspace / "artifacts" / "inbox" / "browser-box.cast").write_text("cast-payload\n", encoding="utf-8")
        (workspace / "artifacts" / "inbox" / "boot.png").write_text("png-payload\n", encoding="utf-8")
        project = Project(
            name="Remote Exec Governed Result Collection",
            idea="Broker-owned result collection should move remote artifacts into governed destinations.",
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
            title="Collect governed browser evidence remotely",
            goal="Adopt remote worker outputs into governed paths.",
            scope="Do not edit code.",
            agent_role="Browser validation",
            milestone="Milestone 2",
            allowed_paths_json=["artifacts"],
            forbidden_paths_json=[],
            validation_steps_json=["playwright test"],
            success_criteria_json=["Governed result artifacts are collected and audited."],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=10,
        )
        db.add_all([manager_agent, worker, task])
        db.flush()
        request_root = workspace / "artifacts" / "remote-execution-requests" / "remote-exec-1700000000003"
        request_root.mkdir(parents=True, exist_ok=True)
        execution_request_path = request_root / "execution-request.json"
        approval_binding_path = request_root / "approval-binding.json"
        result_bundle_path = request_root / "result-bundle.json"
        transfer_bundle_path = request_root / "transfer-bundle.json"
        execution_request_path.write_text(
            json.dumps(
                {
                    "request_id": "remote-exec-1700000000003",
                    "request_status": "ready",
                    "target_id": "browser-box",
                    "selected_target_id": "browser-box",
                    "selected_target_probe_status": "ready",
                    "required_runner_family": "external_adapter",
                    "transport": "tailscale_ssh",
                    "host": "browser-box.tailnet.ts.net",
                    "remote_workspace_root": "/srv/browser-work",
                    "dry_run": False,
                    "write_intent": False,
                    "approval_required": False,
                    "blocking_reasons": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        approval_binding_path.write_text(
            json.dumps(
                {
                    "request_id": "remote-exec-1700000000003",
                    "approval_required": False,
                    "resolved_for_execution": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        result_bundle_path.write_text(
            json.dumps(
                {
                    "request_id": "remote-exec-1700000000003",
                    "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                    "expected_evidence_categories": ["logs", "screenshots", "traces"],
                    "session_recording_required": True,
                    "session_recording_enabled": True,
                    "session_recording_artifact_paths": [
                        "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
                    ],
                    "remote_session_recording_artifact_paths": [
                        "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
                    ],
                    "remote_artifact_paths": ["/srv/browser-work/artifacts/screenshots/boot.png"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        transfer_bundle_path.write_text(
            json.dumps(
                {
                    "request_id": "remote-exec-1700000000003",
                    "target_id": "browser-box",
                    "request_status": "ready",
                    "declared_result_collection": [
                        {
                            "local_path": "artifacts/screenshots/boot.png",
                            "remote_path": "/srv/browser-work/artifacts/screenshots/boot.png",
                            "collection_stage": "remote_workspace_artifact",
                            "source_kind": "workspace_artifact",
                            "required": False,
                            "collection_mode": "pull_remote_artifact",
                        },
                        {
                            "local_path": "artifacts/remote-execution-governance/session-recordings/browser-box.cast",
                            "remote_path": "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast",
                            "collection_stage": "remote_session_recording",
                            "source_kind": "session_recording",
                            "required": True,
                            "collection_mode": "pull_remote_artifact",
                        },
                        {
                            "local_path": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                            "remote_path": None,
                            "collection_stage": "normalized_summary",
                            "source_kind": "normalized_summary",
                            "required": True,
                            "collection_mode": "local_generated_artifact",
                        },
                    ],
                    "declared_result_collection_count": 3,
                    "staged_outbound_transfer_bytes": 0,
                    "blocking_reasons": [],
                    "notes": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="external_adapter",
            process_ref="remote-browser-run-collect",
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
                    },
                    "selected_target": {
                        "id": "browser-box",
                        "transport": "tailscale_ssh",
                        "os_family": "linux",
                    },
                    "broker_contract": {
                        "require_session_recording": True,
                        "session_recording_enabled": True,
                    },
                    "result_contract": {
                        "expected_evidence_categories": ["logs", "screenshots", "traces"],
                        "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                        "session_recording_artifact_paths": [
                            "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
                        ],
                        "remote_session_recording_artifact_paths": [
                            "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
                        ],
                    },
                    "execution_request": {
                        "request_id": "remote-exec-1700000000003",
                        "request_status": "ready",
                        "target_id": "browser-box",
                        "execution_request_path": execution_request_path.relative_to(workspace).as_posix(),
                        "approval_binding_path": approval_binding_path.relative_to(workspace).as_posix(),
                        "result_bundle_path": result_bundle_path.relative_to(workspace).as_posix(),
                        "transfer_bundle_path": transfer_bundle_path.relative_to(workspace).as_posix(),
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
            files_changed=[],
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
            files_changed=[],
            tests_run=list(report.tests_run),
            commands_attempted=["playwright test"],
            evidence=[
                {
                    "kind": "artifact",
                    "summary": "Captured screenshot artifact.",
                    "status": "present",
                    "source_path": "artifacts/inbox/boot.png",
                    "metadata_json": {
                        "remote_path": "/srv/browser-work/artifacts/screenshots/boot.png",
                        "collection_stage": "remote_workspace_artifact",
                        "source_kind": "workspace_artifact",
                    },
                },
                {
                    "kind": "artifact",
                    "summary": "Captured session recording artifact.",
                    "status": "present",
                    "source_path": "artifacts/inbox/browser-box.cast",
                    "metadata_json": {
                        "remote_path": "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast",
                        "collection_stage": "remote_session_recording",
                        "source_kind": "session_recording",
                    },
                },
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

        screenshot_target = workspace / "artifacts" / "screenshots" / "boot.png"
        recording_target = workspace / "artifacts" / "remote-execution-governance" / "session-recordings" / "browser-box.cast"
        summary_target = workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json"
        assert screenshot_target.exists()
        assert recording_target.exists()
        assert summary_target.exists()
        assert screenshot_target.read_text(encoding="utf-8") == "png-payload\n"
        assert recording_target.read_text(encoding="utf-8") == "cast-payload\n"

        transfer_payload = json.loads(transfer_bundle_path.read_text(encoding="utf-8"))
        events = db.query(ProjectEvent).filter(ProjectEvent.project_id == project.id).all()

        assert transfer_payload["broker_result_collection_status"] == "completed"
        assert transfer_payload["collection_action_count"] == 3
        assert transfer_payload["required_result_artifact_count"] == 2
        assert {item["status"] for item in transfer_payload["collection_actions"]} == {
            "copied",
            "already_present",
        }
        assert transfer_payload["broker_collected_result_artifact_paths"] == [
            "artifacts/screenshots/boot.png",
            "artifacts/remote-execution-governance/session-recordings/browser-box.cast",
            "artifacts/remote-execution-governance/normalized-execution-summary.json",
        ]
        assert transfer_payload["broker_missing_result_artifact_paths"] == []
        assert transfer_payload["final_transfer_status"] == "completed"
        assert transfer_payload["collected_result_artifact_count"] == 3
        assert transfer_payload["missing_result_artifact_paths"] == []
        assert transfer_payload["required_missing_result_artifact_paths"] == []
        assert transfer_payload["optional_missing_result_artifact_paths"] == []

        collection_event = next(
            event for event in events if event.event_type == "remote_execution.result_collection_completed"
        )
        assert collection_event.payload_json["broker_result_collection_status"] == "completed"
        assert collection_event.payload_json["collection_action_count"] == 3
        reconcile_event = next(
            event for event in events if event.event_type == "remote_execution.transfer_reconciled"
        )
        assert reconcile_event.payload_json["final_transfer_status"] == "completed"
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
        assert not any(event.event_type == "remote_execution.transfer_reconciled" for event in events)
    finally:
        db.close()


def test_ingest_worker_report_emits_result_collection_failed_event(monkeypatch) -> None:
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
        "_collect_remote_execution_result_artifacts",
        lambda project, run, envelope: (_ for _ in ()).throw(OSError("copy failed during governed collection")),
    )

    init_db()
    db = SessionLocal()
    try:
        workspace = Path(sample_workspace("remote-exec-result-collection-failure"))
        workspace.mkdir(parents=True, exist_ok=True)
        project = Project(
            name="Remote Exec Result Collection Failure",
            idea="Do not lose accepted worker results when governed artifact collection fails.",
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
            goal="Persist the accepted report even if result collection storage complains.",
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
            process_ref="gpu-remote-run-collection-failure",
            status="working",
            effective_settings_json={
                "remote_execution": {
                    "policy": {"enabled": True},
                    "execution_request": {
                        "request_id": "remote-exec-failed-collection",
                        "transfer_bundle_path": "artifacts/remote-execution-requests/remote-exec-failed-collection/transfer-bundle.json",
                    },
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
        assert any(event.event_type == "remote_execution.result_collection_failed" for event in events)
        assert not any(event.event_type == "remote_execution.result_collection_completed" for event in events)
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
                    "latest_selected_target_probe_status": "blocked",
                    "latest_availability_diagnostics": {
                        "summary": "Browser box is visible but missing required toolchains.",
                        "has_blockers": True,
                    },
                    "latest_selected_target_requirement_gaps": {"toolchains": ["playwright"]},
                    "latest_selected_target_rejected_reasons": ["plain_ssh_missing_policy_match"],
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
                "ready_route_ids": ["tailscale_ssh"],
                "selected_ready_route_ids": ["tailscale_ssh"],
                "partial_route_ids": [],
                "notes": [],
            },
        )
        monkeypatch.setattr(
            service,
            "build_platform_runner_summary",
            lambda db, project: {
                "ready_lane_count": 1,
                "ready_lane_ids": ["browser"],
                "ready_route_count": 1,
                "ready_route_ids": ["tailscale_ssh"],
                "selected_ready_lane_ids": ["browser"],
                "selected_ready_route_ids": ["tailscale_ssh"],
                "partial_route_ids": [],
                "lanes": [
                    {
                        "lane_id": "browser",
                        "status": "ready",
                        "selected_target_ids": ["browser-box"],
                        "route_ids": ["tailscale_ssh"],
                        "ready_route_ids": ["tailscale_ssh"],
                        "selected_route_ids": ["tailscale_ssh"],
                        "selected_ready_route_ids": ["tailscale_ssh"],
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
        assert summary["selected_target_probe_status"] == "ready"
        assert summary["availability_diagnostics"]["summary"] == (
            "Browser box is visible but missing required toolchains."
        )
        assert summary["selected_target_requirement_gaps"] == {"toolchains": ["playwright"]}
        assert summary["selected_target_rejected_reasons"] == ["plain_ssh_missing_policy_match"]
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
                "selected_target_probe_status": "blocked",
                "availability_diagnostics": {
                    "summary": "GPU Linux is visible but CUDA capability is still missing.",
                    "has_blockers": True,
                },
                "selected_target_requirement_gaps": {"toolchains": ["cuda12"]},
                "selected_target_rejected_reasons": ["plain_ssh_missing_policy_match"],
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
    assert rollup["selected_target_probe_status_counts"] == {"blocked": 1}
    assert rollup["availability_diagnostic_summaries"] == [
        "GPU Linux is visible but CUDA capability is still missing."
    ]
    assert rollup["availability_diagnostic_blocker_count"] == 1
    assert rollup["selected_target_requirement_gap_count"] == 1
    assert rollup["selected_target_requirement_gap_targets"] == ["gpu-linux"]
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


def test_build_artifact_registry_plan_reads_transfer_bundle_result_collection_rollup() -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("artifact-registry-transfer-bundle-rollup"))
    runtime_root = workspace / "artifacts" / "remote-execution-governance" / "runtime"
    request_root = workspace / "artifacts" / "remote-execution-requests" / "remote-exec-1700000009999"
    runtime_root.mkdir(parents=True, exist_ok=True)
    request_root.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# remote runtime transfer bundle\n", encoding="utf-8")
    (workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json").write_text(
        json.dumps({"run_count": 1}, indent=2),
        encoding="utf-8",
    )
    (workspace / "artifacts" / "screenshots").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "screenshots" / "boot.png").write_text("png\n", encoding="utf-8")
    (runtime_root / "remote-adapter-transfer-rollup-launch-manifest.json").write_text(
        json.dumps(
            {
                "run_id": "remote-adapter-transfer-rollup",
                "target_id": "gpu-linux",
                "transport": "tailscale_ssh",
                "host": "gpu-linux.tailnet.ts.net",
                "remote_artifact_paths": ["/srv/gpu-work/artifacts/screenshots/boot.png"],
                "session_recording_required": True,
                "session_recording_enabled": True,
                "transfer_bundle_path": "artifacts/remote-execution-requests/remote-exec-1700000009999/transfer-bundle.json",
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "command_preview": "tailscale ssh gpu-linux.tailnet.ts.net python -m pytest",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (request_root / "transfer-bundle.json").write_text(
        json.dumps(
            {
                "request_id": "remote-exec-1700000009999",
                "final_transfer_status": "partial",
                "declared_result_collection": [
                    {
                        "local_path": "artifacts/screenshots/boot.png",
                        "remote_path": "/srv/gpu-work/artifacts/screenshots/boot.png",
                        "collection_stage": "remote_workspace_artifact",
                        "source_kind": "workspace_artifact",
                    },
                    {
                        "local_path": "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast",
                        "remote_path": "/srv/gpu-work/artifacts/remote-execution-governance/session-recordings/gpu-linux.cast",
                        "collection_stage": "remote_session_recording",
                        "source_kind": "session_recording",
                    },
                ],
                "collected_result_artifacts": [
                    {
                        "local_path": "artifacts/screenshots/boot.png",
                        "remote_path": "/srv/gpu-work/artifacts/screenshots/boot.png",
                        "collection_stage": "remote_workspace_artifact",
                        "status": "collected",
                    },
                    {
                        "local_path": "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast",
                        "remote_path": "/srv/gpu-work/artifacts/remote-execution-governance/session-recordings/gpu-linux.cast",
                        "collection_stage": "remote_session_recording",
                        "status": "missing",
                    },
                ],
                "collected_result_artifact_count": 1,
                "missing_result_artifact_paths": [
                    "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    project = Project(
        id=105,
        name="Artifact Registry Transfer Bundle Rollup",
        workspace_path=workspace.as_posix(),
        source_path=workspace.as_posix(),
    )

    plan = service.build_artifact_registry_plan(project)

    assert plan["plan_status"] == "partial"
    rollup = json.loads((workspace / "artifacts" / "artifact-registry" / "remote-runtime-rollup.json").read_text(encoding="utf-8"))
    assert rollup["declared_result_collection_count"] == 2
    assert rollup["result_collection_artifact_present_count"] == 1
    assert rollup["result_collection_artifact_gap_count"] == 1
    assert rollup["produced_result_artifact_paths"] == ["artifacts/screenshots/boot.png"]
    assert rollup["missing_result_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/gpu-linux.cast"
    ]
    assert rollup["result_collection_transfer_statuses"] == {"partial": 1}


def test_build_artifact_transport_summary_rolls_up_result_collection_delivery_from_runtime_manifests(monkeypatch) -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("artifact-transport-summary-result-collection"))
    runtime_root = workspace / "artifacts" / "remote-execution-governance" / "runtime"
    request_root = workspace / "artifacts" / "remote-execution-requests" / "remote-exec-transport-summary"
    runtime_root.mkdir(parents=True, exist_ok=True)
    request_root.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# artifact transport summary\n", encoding="utf-8")
    (workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json").write_text(
        json.dumps({"run_count": 1}, indent=2),
        encoding="utf-8",
    )
    recording_path = workspace / "artifacts" / "remote-execution-governance" / "session-recordings" / "linux-sync.cast"
    recording_path.parent.mkdir(parents=True, exist_ok=True)
    recording_path.write_text("cast\n", encoding="utf-8")
    (request_root / "transfer-bundle.json").write_text(
        json.dumps(
            {
                "request_id": "remote-exec-transport-summary",
                "final_transfer_status": "partial",
                "declared_result_collection": [
                    {
                        "local_path": "artifacts/screenshots/home.png",
                        "collection_stage": "remote_workspace_artifact",
                    },
                    {
                        "local_path": "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
                        "collection_stage": "remote_session_recording",
                    },
                    {
                        "local_path": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                        "collection_stage": "normalized_summary",
                    },
                ],
                "collected_result_artifacts": [
                    {
                        "local_path": "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
                        "collection_stage": "remote_session_recording",
                        "status": "collected",
                    },
                    {
                        "local_path": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                        "collection_stage": "normalized_summary",
                        "status": "collected",
                    },
                    {
                        "local_path": "artifacts/screenshots/home.png",
                        "collection_stage": "remote_workspace_artifact",
                        "status": "missing",
                    },
                ],
                "missing_result_artifact_paths": ["artifacts/screenshots/home.png"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (runtime_root / "linux-sync.json").write_text(
        json.dumps(
            {
                "run_id": "run-linux-sync",
                "target_id": "linux-sync",
                "transport": "ssh",
                "host": "linux-sync.local",
                "session_recording_required": True,
                "session_recording_enabled": True,
                "session_recording_artifact_paths": [
                    "artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
                ],
                "remote_session_recording_artifact_paths": [
                    "/srv/shadow/artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
                ],
                "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "transfer_bundle_path": "artifacts/remote-execution-requests/remote-exec-transport-summary/transfer-bundle.json",
                "remote_artifact_paths": ["/srv/shadow/artifacts/screenshots/home.png"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    project = Project(
        id=106,
        name="Artifact Transport Result Collection Summary",
        workspace_path=workspace.as_posix(),
        source_path=workspace.as_posix(),
    )

    monkeypatch.setattr(
        service,
        "preview_project_remote_execution",
        lambda db, candidate: {
            "policy_enabled": True,
            "policy": {"enabled": True},
            "selected_target_id": "linux-sync",
            "selected_target_probe_status": "ready",
            "preflight_ready": True,
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["linux-sync"],
            "blocking_reasons": [],
            "artifact_contract": {
                "sync_enabled": True,
                "blocking_reasons": [],
                "notes": [],
                "selected_artifact_root": "/srv/shadow/artifacts",
                "remote_workspace_root": "/srv/shadow",
            },
            "connector_contract": {
                "blocking_reasons": [],
                "notes": [],
                "available_families": ["source_control"],
            },
        },
    )
    monkeypatch.setattr(
        service,
        "build_project_artifact_registry",
        lambda candidate: {
            "artifact_count": 3,
            "artifact_paths": [
                "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
                "artifacts/screenshots/home.png",
            ],
            "artifact_kind_summaries": [],
            "inspection_commands": [],
        },
    )
    monkeypatch.setattr(
        service,
        "get_connector_registry",
        lambda db: {
            "provider_counts": {"source_control": 1},
            "status_counts": {"connected": 1},
        },
    )
    monkeypatch.setattr(
        service,
        "build_platform_runner_summary",
        lambda db, candidate: {
            "ready_lane_ids": ["linux"],
            "selected_ready_lane_ids": ["linux"],
            "target_backed_ready_lane_ids": ["linux"],
            "partial_lane_ids": [],
            "ready_route_ids": ["tailscale_ssh"],
            "selected_ready_route_ids": ["tailscale_ssh"],
            "partial_route_ids": [],
            "blocking_reasons": [],
        },
    )

    summary = service.build_artifact_transport_summary(None, project)

    assert summary["recommended_transport_mode"] == "blocked"
    assert summary["result_collection_status"] == "partial"
    assert summary["result_collection_required"] is True
    assert summary["result_collection_runtime_manifest_count"] == 1
    assert summary["declared_result_collection_count"] == 3
    assert summary["produced_result_artifact_count"] == 2
    assert summary["missing_result_artifact_count"] == 1
    assert summary["produced_result_artifact_paths"] == [
        "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
        "artifacts/remote-execution-governance/normalized-execution-summary.json",
    ]
    assert summary["missing_result_artifact_paths"] == ["artifacts/screenshots/home.png"]
    assert summary["result_collection_transfer_statuses"] == {"partial": 1}
    assert "result_artifact_missing_after_remote_execution" in summary["blocking_reasons"]


def test_build_artifact_transport_plan_persists_result_collection_delivery_contract(monkeypatch) -> None:
    service = MissionControlService()
    workspace = Path(sample_workspace("artifact-transport-plan-result-collection"))
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# artifact transport plan\n", encoding="utf-8")
    project = Project(
        id=107,
        name="Artifact Transport Result Collection Plan",
        workspace_path=workspace.as_posix(),
        source_path=workspace.as_posix(),
    )

    monkeypatch.setattr(
        service,
        "build_artifact_transport_summary",
        lambda db, candidate: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": workspace.as_posix(),
            "summary": "Artifact transport summary is ready for result collection review.",
            "selected_target_id": "linux-sync",
            "selected_target_probe_status": "ready",
            "ready_candidate_count": 1,
            "ready_candidate_ids": ["linux-sync"],
            "preflight_ready": True,
            "sync_enabled": True,
            "recommended_transport_mode": "workspace_relative_sync",
            "blocking_reasons": [],
            "session_recording_status": "ready",
            "session_recording_required": True,
            "session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
            ],
            "produced_session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
            ],
            "missing_session_recording_artifact_paths": [],
            "remote_session_recording_artifact_paths": [
                "/srv/shadow/artifacts/remote-execution-governance/session-recordings/linux-sync.cast"
            ],
            "session_recording_runtime_manifest_count": 1,
            "result_collection_status": "ready",
            "result_collection_required": True,
            "result_collection_runtime_manifest_count": 1,
            "declared_result_collection_count": 3,
            "declared_result_artifact_paths": [
                "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
                "artifacts/screenshots/home.png",
            ],
            "produced_result_artifact_count": 3,
            "produced_result_artifact_paths": [
                "artifacts/remote-execution-governance/normalized-execution-summary.json",
                "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
                "artifacts/screenshots/home.png",
            ],
            "missing_result_artifact_count": 0,
            "missing_result_artifact_paths": [],
            "result_collection_transfer_statuses": {"completed": 1},
            "ready_route_count": 1,
            "selected_ready_route_count": 1,
            "partial_route_count": 0,
            "ready_route_ids": ["tailscale_ssh"],
            "selected_ready_route_ids": ["tailscale_ssh"],
            "partial_route_ids": [],
            "ready_platform_lanes": ["linux"],
            "selected_ready_platform_lanes": ["linux"],
            "target_backed_ready_platform_lanes": ["linux"],
            "partial_platform_lanes": [],
            "notes": [],
            "artifact_registry": {
                "artifact_count": 3,
                "artifact_paths": [
                    "artifacts/remote-execution-governance/normalized-execution-summary.json",
                    "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
                    "artifacts/screenshots/home.png",
                ],
                "artifact_kind_summaries": [],
                "inspection_commands": [],
            },
            "connector_registry": {"provider_counts": {"source_control": 1}, "status_counts": {"connected": 1}},
            "artifact_contract": {
                "required": True,
                "sync_enabled": True,
                "preflight_ready": True,
                "blocking_reasons": [],
                "notes": [],
                "local_artifact_paths": [
                    "artifacts/remote-execution-governance/normalized-execution-summary.json",
                    "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
                    "artifacts/screenshots/home.png",
                ],
                "local_artifact_path_count": 3,
                "artifact_kind_summaries": [],
                "artifact_inspection_commands": [],
                "target_artifact_roots": ["/srv/shadow/artifacts"],
                "selected_artifact_root": "/srv/shadow/artifacts",
                "remote_workspace_root": "/srv/shadow",
                "remote_workspace_artifact_paths": ["/srv/shadow/artifacts/screenshots/home.png"],
            },
            "connector_contract": {
                "missing_required_families": [],
                "available_families": ["source_control"],
                "available_connector_count": 1,
                "preflight_ready": True,
                "blocking_reasons": [],
                "notes": [],
                "required_connector_families": ["source_control"],
                "target_connector_families": ["source_control"],
            },
        },
    )
    monkeypatch.setattr(
        service,
        "build_platform_runner_summary",
        lambda db, candidate: {
            "lanes": [
                {
                    "lane_id": "linux",
                    "status": "ready",
                    "selected_target_ids": ["linux-sync"],
                    "route_ids": ["tailscale_ssh"],
                    "ready_route_ids": ["tailscale_ssh"],
                    "selected_route_ids": ["tailscale_ssh"],
                    "selected_ready_route_ids": ["tailscale_ssh"],
                    "recommended_commands": ["python -m pytest"],
                }
            ]
        },
    )

    plan = service.build_artifact_transport_plan(None, project)

    assert plan["plan_status"] == "ready"
    assert plan["result_collection_status"] == "ready"
    assert plan["declared_result_collection_count"] == 3
    assert plan["produced_result_artifact_count"] == 3
    assert plan["missing_result_artifact_count"] == 0
    assert plan["result_collection_transfer_statuses"] == {"completed": 1}
    delivery_manifest = json.loads(
        (workspace / "artifacts" / "artifact-transport" / "session-recording-delivery.json").read_text(encoding="utf-8")
    )
    assert delivery_manifest["result_collection_status"] == "ready"
    assert delivery_manifest["declared_result_collection_count"] == 3
    assert delivery_manifest["produced_result_artifact_paths"] == [
        "artifacts/remote-execution-governance/normalized-execution-summary.json",
        "artifacts/remote-execution-governance/session-recordings/linux-sync.cast",
        "artifacts/screenshots/home.png",
    ]
    approval_manifest = json.loads(
        (workspace / "artifacts" / "artifact-transport" / "approval-checkpoints.json").read_text(encoding="utf-8")
    )
    checkpoint_by_id = {item["checkpoint_id"]: item for item in approval_manifest["checkpoints"]}
    assert checkpoint_by_id["result_collection_delivery_review"]["status"] == "ready"


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


def test_deterministic_task_decomposition_uses_workspace_file_hints_from_change_request() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-path-hints"))
    (workspace / "astropy/modeling/tests").mkdir(parents=True, exist_ok=True)
    (workspace / "astropy/modeling/tests/test_separable.py").write_text("def test_example():\n    assert True\n", encoding="utf-8")
    (workspace / "astropy/modeling/separable.py").write_text("def separable():\n    return True\n", encoding="utf-8")
    (workspace / "docs").mkdir(parents=True, exist_ok=True)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Path Hints",
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
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nFix the separability regression.\n"
                "Workspace clues:\n"
                "- Files to inspect first: astropy/modeling/tests/test_separable.py\n"
                "- Likely related implementation files: astropy/modeling/separable.py\n"
                "Validation commands:\n"
                "- python -m pytest astropy/modeling/tests/test_separable.py -q\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        db.add(request)
        db.commit()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        assert decomposition.tasks[0].allowed_paths == ["astropy/modeling/tests", "astropy/modeling"]
        assert decomposition.tasks[1].allowed_paths == ["astropy/modeling/separable.py"]
        assert "docs" in decomposition.tasks[1].forbidden_paths
        assert "astropy/modeling/tests" in decomposition.tasks[1].forbidden_paths
        assert decomposition.tasks[2].allowed_paths == ["astropy/modeling/tests", "astropy/modeling"]
        assert all("src" not in task.allowed_paths for task in decomposition.tasks)
    finally:
        db.close()


def test_deterministic_task_decomposition_keeps_doc_paths_for_doc_coupled_benchmark_bugfix() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-doc-coupled-bugfix"))
    (workspace / "django/conf").mkdir(parents=True, exist_ok=True)
    (workspace / "tests/test_utils").mkdir(parents=True, exist_ok=True)
    (workspace / "docs/ref").mkdir(parents=True, exist_ok=True)
    (workspace / "docs/releases").mkdir(parents=True, exist_ok=True)
    (workspace / "django/conf/global_settings.py").write_text(
        "FILE_UPLOAD_PERMISSIONS = None\n",
        encoding="utf-8",
    )
    (workspace / "tests/test_utils/tests.py").write_text(
        "def test_override_file_upload_permissions():\n    assert True\n",
        encoding="utf-8",
    )
    (workspace / "docs/ref/settings.txt").write_text(
        "FILE_UPLOAD_PERMISSIONS documentation\n",
        encoding="utf-8",
    )
    (workspace / "docs/releases/3.0.txt").write_text(
        "Release notes\n",
        encoding="utf-8",
    )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Doc Coupled Bugfix",
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
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nSet default FILE_UPLOAD_PERMISSION to 0o644.\n"
                "Workspace clues:\n"
                "- Files to inspect first: tests/test_utils/tests.py\n"
                "- Likely related implementation files: django/conf/global_settings.py, docs/ref/settings.txt, docs/releases/3.0.txt\n"
                "Hints:\n"
                "Add a breaking change note and adjust the references in the settings docs and deployment checklist.\n"
                "Validation commands:\n"
                "- python tests/runtests.py --settings=test_sqlite test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        db.add(request)
        db.commit()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        assert decomposition.tasks[0].allowed_paths == ["tests/test_utils", "django/conf"]
        assert decomposition.tasks[1].allowed_paths == ["django/conf", "docs/ref", "docs/releases"]
        assert "tests/test_utils" in decomposition.tasks[1].forbidden_paths
        assert "tests/test_utils/tests.py" in decomposition.tasks[1].forbidden_paths
        assert decomposition.tasks[2].allowed_paths == ["tests/test_utils", "django/conf", "docs/ref"]
    finally:
        db.close()


def test_deterministic_task_decomposition_keeps_release_notes_when_more_than_two_doc_hints_exist() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-multi-doc-bugfix"))
    (workspace / "django/conf").mkdir(parents=True, exist_ok=True)
    (workspace / "tests/test_utils").mkdir(parents=True, exist_ok=True)
    (workspace / "docs/ref").mkdir(parents=True, exist_ok=True)
    (workspace / "docs/ref/contrib").mkdir(parents=True, exist_ok=True)
    (workspace / "docs/releases").mkdir(parents=True, exist_ok=True)
    (workspace / "django/conf/global_settings.py").write_text("FILE_UPLOAD_PERMISSIONS = None\n", encoding="utf-8")
    (workspace / "tests/test_utils/tests.py").write_text(
        "def test_override_file_upload_permissions():\n    assert True\n",
        encoding="utf-8",
    )
    (workspace / "docs/ref/settings.txt").write_text("FILE_UPLOAD_PERMISSIONS documentation\n", encoding="utf-8")
    (workspace / "docs/ref/contrib/staticfiles.txt").write_text("Staticfiles deployment checklist\n", encoding="utf-8")
    (workspace / "docs/releases/3.0.txt").write_text("Release notes\n", encoding="utf-8")

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Multi Doc Bugfix",
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
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nSet default FILE_UPLOAD_PERMISSION to 0o644.\n"
                "Workspace clues:\n"
                "- Files to inspect first: tests/test_utils/tests.py\n"
                "- Likely related implementation files: django/conf/global_settings.py, docs/ref/settings.txt, docs/ref/contrib/staticfiles.txt, docs/releases/3.0.txt\n"
                "Hints:\n"
                "Add a breaking change note and adjust the references in the settings docs and deployment checklist.\n"
                "Validation commands:\n"
                "- python tests/runtests.py --settings=test_sqlite test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        db.add(request)
        db.commit()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        assert decomposition.tasks[1].allowed_paths == [
            "django/conf",
            "docs/ref",
            "docs/ref/contrib",
            "docs/releases",
        ]
    finally:
        db.close()


def test_deterministic_task_decomposition_carries_focused_validation_command_into_benchmark_tasks() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-focused-validation-command"))
    (workspace / "django/conf").mkdir(parents=True, exist_ok=True)
    (workspace / "tests/test_utils").mkdir(parents=True, exist_ok=True)
    (workspace / "django/conf/global_settings.py").write_text("FILE_UPLOAD_PERMISSIONS = None\n", encoding="utf-8")
    (workspace / "tests/test_utils/tests.py").write_text(
        "def test_override_file_upload_permissions():\n    assert True\n",
        encoding="utf-8",
    )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Focused Validation",
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
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nSet default FILE_UPLOAD_PERMISSION to 0o644.\n"
                "Workspace clues:\n"
                "- Files to inspect first: tests/test_utils/tests.py\n"
                "- Likely related implementation files: django/conf/global_settings.py\n"
                "\nFocused reproduction commands:\n"
                "- python tests/runtests.py --settings=test_sqlite test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        db.add(request)
        db.commit()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        assert decomposition.tasks[0].validation_steps[0].startswith(
            "Run the focused validation command: python tests/runtests.py --settings=test_sqlite"
        )
        assert decomposition.tasks[2].validation_steps[0].startswith(
            "Re-run the focused validation command: python tests/runtests.py --settings=test_sqlite"
        )
    finally:
        db.close()


def test_deterministic_task_decomposition_ignores_bug_campaign_tokens_for_benchmark_bugfix() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-bugfix-overrides-campaign"))
    (workspace / "django/db/models").mkdir(parents=True, exist_ok=True)
    (workspace / "tests/expressions").mkdir(parents=True, exist_ok=True)
    (workspace / "django/db/models/expressions.py").write_text("class Expression:\n    pass\n", encoding="utf-8")
    (workspace / "tests/expressions/tests.py").write_text("def test_order_by_multiline_sql():\n    assert True\n", encoding="utf-8")

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Bugfix Overrides Campaign",
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
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nContinue fixing the expression ordering problem without widening scope.\n"
                "Workspace clues:\n"
                "- Files to inspect first: tests/expressions/tests.py\n"
                "- Likely related implementation files: django/db/models/expressions.py\n"
                "Focused reproduction commands:\n"
                "- python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        db.add(request)
        db.commit()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        assert decomposition.tasks[0].title == "Reproduce the failing behavior and isolate the smallest broken path"
        assert decomposition.tasks[1].title == "Implement the smallest safe code fix"
        assert decomposition.tasks[2].title == "Re-run focused validation and prepare an honest handoff"
        assert not any(task.title.endswith("Defect Batch") for task in decomposition.tasks)
        assert decomposition.tasks[1].allowed_paths == ["django/db/models"]
    finally:
        db.close()


def test_deterministic_task_decomposition_uses_top_ranked_exact_benchmark_implementation_hint() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-exact-file-hints"))
    (workspace / "django/db/models/sql").mkdir(parents=True, exist_ok=True)
    (workspace / "django/db/models/fields").mkdir(parents=True, exist_ok=True)
    (workspace / "tests/expressions").mkdir(parents=True, exist_ok=True)
    (workspace / "django/db/models/sql/compiler.py").write_text("class SQLCompiler:\n    pass\n", encoding="utf-8")
    (workspace / "django/db/models/fields/related_descriptors.py").write_text("class Related:\n    pass\n", encoding="utf-8")
    (workspace / "django/db/models/expressions.py").write_text("class Expression:\n    pass\n", encoding="utf-8")
    (workspace / "django/db/models/fields/files.py").write_text("class FieldFile:\n    pass\n", encoding="utf-8")
    (workspace / "tests/expressions/tests.py").write_text("def test_order_by_multiline_sql():\n    assert True\n", encoding="utf-8")

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Exact File Hints",
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
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nFix multiline RawSQL ordering.\n"
                "Workspace clues:\n"
                "- Files to inspect first: tests/expressions/tests.py\n"
                "- Likely related implementation files: django/db/models/sql/compiler.py, django/db/models/fields/related_descriptors.py, django/db/models/expressions.py, django/db/models/fields/files.py\n"
                "Implementation anchors:\n"
                "- django/db/models/sql/compiler.py:1: class SQLCompiler:\n"
                "- django/db/models/fields/related_descriptors.py:1: class Related:\n"
                "Focused reproduction commands:\n"
                "- python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        db.add(request)
        db.commit()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        assert decomposition.tasks[1].allowed_paths == ["django/db/models/sql/compiler.py"]
        assert "django/db/models/sql/compiler.py" in decomposition.tasks[1].scope
        assert "Implementation locator (line numbers approximate): django/db/models/sql/compiler.py:1: class SQLCompiler:" in decomposition.tasks[1].scope
        assert "django/db/models/fields/related_descriptors.py" not in decomposition.tasks[1].scope
        assert "tests/expressions/tests.py" not in decomposition.tasks[1].scope
    finally:
        db.close()


def test_deterministic_task_decomposition_prefers_issue_named_benchmark_symbol_anchor() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-issue-symbol-anchor"))
    (workspace / "astropy/modeling").mkdir(parents=True, exist_ok=True)
    (workspace / "astropy/modeling/separable.py").write_text(
        "def is_separable(transform):\n    pass\n\n\ndef separability_matrix(transform):\n    pass\n",
        encoding="utf-8",
    )
    (workspace / "astropy/modeling/tests").mkdir(parents=True, exist_ok=True)
    (workspace / "astropy/modeling/tests/test_separable.py").write_text(
        "def test_regression():\n    assert True\n",
        encoding="utf-8",
    )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Issue Symbol Anchor",
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
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nModeling's `separability_matrix` does not compute separability correctly.\n"
                "Workspace clues:\n"
                "- Files to inspect first: astropy/modeling/separable.py, astropy/modeling/tests/test_separable.py\n"
                "- Likely related implementation files: astropy/modeling/separable.py\n"
                "Implementation anchors:\n"
                "- astropy/modeling/separable.py:1: def is_separable(transform):\n"
                "- astropy/modeling/separable.py:4: def separability_matrix(transform):\n"
                "Focused reproduction commands:\n"
                "- python -m pytest astropy/modeling/tests/test_separable.py -q\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        db.add(request)
        db.commit()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        assert decomposition.tasks[1].allowed_paths == ["astropy/modeling/separable.py"]
        assert "Implementation locator (line numbers approximate): astropy/modeling/separable.py:4: def separability_matrix(transform):" in decomposition.tasks[1].scope
        assert "Same-file helper locators (line numbers approximate):" in decomposition.tasks[1].scope
        assert "astropy/modeling/separable.py:1: def is_separable(transform):" in decomposition.tasks[1].scope
    finally:
        db.close()


def test_extract_request_validation_commands_handles_single_line_change_request_text() -> None:
    service = MissionControlService()
    request_text = (
        "Run this as a prepared local SWE-bench-style coding task. "
        "Focused reproduction commands: - python tests/runtests.py --settings=test_sqlite "
        "test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions "
        "Broader validation commands after a fix: - python tests/runtests.py --settings=test_sqlite "
        "test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions test_utils.tests.OtherTests.test_ok "
        "FAIL_TO_PASS targets: - test_override_file_upload_permissions (test_utils.tests.OverrideSettingsTests)"
    )

    commands = service._extract_request_validation_commands(request_text)

    assert commands[0] == (
        "python tests/runtests.py --settings=test_sqlite "
        "test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions"
    )


def test_deterministic_task_decomposition_uses_focused_validation_command_after_change_request_normalization() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-change-request-normalization"))
    (workspace / "django/conf").mkdir(parents=True, exist_ok=True)
    (workspace / "tests/test_utils").mkdir(parents=True, exist_ok=True)
    (workspace / "django/conf/global_settings.py").write_text("FILE_UPLOAD_PERMISSIONS = None\n", encoding="utf-8")
    (workspace / "tests/test_utils/tests.py").write_text(
        "def test_override_file_upload_permissions():\n    assert True\n",
        encoding="utf-8",
    )

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Normalized Change Request",
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
        request_text = (
            "Run this as a prepared local SWE-bench-style coding task.\n"
            "Issue:\nSet default FILE_UPLOAD_PERMISSION to 0o644.\n"
            "Workspace clues:\n"
            "- Files to inspect first: tests/test_utils/tests.py\n"
            "- Likely related implementation files: django/conf/global_settings.py\n"
            "\nFocused reproduction commands:\n"
            "- python tests/runtests.py --settings=test_sqlite test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions\n"
        )
        service.create_change_request(db, project, request_text)
        db.commit()
        request = db.query(ChangeRequest).filter(ChangeRequest.project_id == project.id).one()

        decomposition = service._deterministic_task_decomposition(
            db,
            project,
            plan=None,
            requested_change_requests=[request],
        )

        assert decomposition.tasks[0].validation_steps[0].startswith(
            "Run the focused validation command: python tests/runtests.py --settings=test_sqlite"
        )
    finally:
        db.close()


def test_generate_tasks_replaces_weak_provider_decomposition_for_benchmark_bugfix(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-bugfix-task-floor"))
    (workspace / "astropy/modeling/tests").mkdir(parents=True, exist_ok=True)
    (workspace / "astropy/modeling/tests/test_separable.py").write_text("def test_example():\n    assert True\n", encoding="utf-8")
    (workspace / "astropy/modeling/separable.py").write_text("def separable():\n    return True\n", encoding="utf-8")
    (workspace / "docs").mkdir(parents=True, exist_ok=True)

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerTaskDecomposition(
                summary_markdown="Weak provider decomposition.",
                milestones=["Milestone 1", "Milestone 2", "Milestone 3"],
                tasks=[
                    ManagerTaskItem(
                        title="Identify the bug in separability_matrix",
                        goal="Understand why the function behaves incorrectly.",
                        scope="astropy/modeling/separable.py",
                        agent_role="Developer",
                        milestone="Milestone 1",
                        allowed_paths=["astropy/modeling/separable.py"],
                        forbidden_paths=[],
                        validation_steps=[],
                        success_criteria=["The bug is identified."],
                        estimated_complexity="small",
                        priority=1,
                    ),
                    ManagerTaskItem(
                        title="Fix the separability_matrix function",
                        goal="Implement a fix.",
                        scope="astropy/modeling/separable.py",
                        agent_role="Developer",
                        milestone="Milestone 2",
                        allowed_paths=["astropy/modeling/separable.py"],
                        forbidden_paths=[],
                        validation_steps=["Run the unit tests."],
                        success_criteria=["The bug is fixed."],
                        estimated_complexity="small",
                        priority=2,
                        dependencies=[1],
                    ),
                    ManagerTaskItem(
                        title="Validate the fix with additional unit tests",
                        goal="Add coverage and re-run tests.",
                        scope="astropy/modeling/tests/test_separable.py",
                        agent_role="Developer",
                        milestone="Milestone 3",
                        allowed_paths=["astropy/modeling/tests/test_separable.py"],
                        forbidden_paths=[],
                        validation_steps=["Run the unit tests."],
                        success_criteria=["Tests pass."],
                        estimated_complexity="small",
                        priority=3,
                        dependencies=[2],
                    ),
                ],
            ),
            "manager_ai",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Bugfix Task Floor",
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
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nFix the separability regression.\n"
                "Workspace clues:\n"
                "- Files to inspect first: astropy/modeling/tests/test_separable.py\n"
                "- Likely related implementation files: astropy/modeling/separable.py\n"
                "Validation commands:\n"
                "- python -m pytest astropy/modeling/tests/test_separable.py -q\n"
                "FAIL_TO_PASS targets:\n"
                "- astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]\n"
                "PASS_TO_PASS targets:\n"
                "- astropy/modeling/tests/test_separable.py::test_coord_matrix\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        db.add(request)
        db.commit()

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        assert manager_mode_used == "deterministic_guardrail"
        assert tasks[0].title == "Reproduce the failing behavior and isolate the smallest broken path"
        assert tasks[0].agent_role == "Validation Specialist"
        assert tasks[0].allowed_paths_json == ["astropy/modeling/tests", "astropy/modeling"]
        assert tasks[0].validation_steps_json[0].startswith(
            "Run the focused validation command: python -m pytest astropy/modeling/tests/test_separable.py -q"
        )
        assert tasks[1].allowed_paths_json == ["astropy/modeling/separable.py"]
        assert tasks[1].validation_steps_json[0].startswith(
            "Use the focused validation command as the implementation anchor: python -m pytest astropy/modeling/tests/test_separable.py -q"
        )
        assert "astropy/modeling/separable.py" in tasks[1].scope
        assert "astropy/modeling/tests/test_separable.py" not in tasks[1].scope
    finally:
        db.close()


def test_generate_tasks_uses_deterministic_floor_even_when_provider_decomposition_looks_strong(monkeypatch) -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-bugfix-task-floor-pass"))
    (workspace / "astropy/modeling/tests").mkdir(parents=True, exist_ok=True)
    (workspace / "astropy/modeling/tests/test_separable.py").write_text("def test_example():\n    assert True\n", encoding="utf-8")
    (workspace / "astropy/modeling/separable.py").write_text("def separable():\n    return True\n", encoding="utf-8")
    (workspace / "docs").mkdir(parents=True, exist_ok=True)

    async def fake_resolve_manager_model(*args, **kwargs):
        return (
            ManagerTaskDecomposition(
                summary_markdown="Strong provider decomposition.",
                milestones=["Milestone 1", "Milestone 2", "Milestone 3"],
                tasks=[
                    ManagerTaskItem(
                        title="Reproduce the failing behavior for separability_matrix",
                        goal="Run the focused pytest command, confirm the failure, and isolate the narrowest broken path.",
                        scope="Use the provided tests before proposing any code edit.",
                        agent_role="Validation Specialist",
                        milestone="Milestone 1",
                        allowed_paths=["astropy/modeling/tests", "astropy/modeling"],
                        forbidden_paths=[],
                        validation_steps=["Run python -m pytest astropy/modeling/tests/test_separable.py -q", "Record the observed failure."],
                        success_criteria=["The current failure is reproduced.", "The broken path is narrowed down."],
                        estimated_complexity="small",
                        priority=1,
                    ),
                    ManagerTaskItem(
                        title="Implement the smallest safe fix for separability_matrix",
                        goal="Update the implementation with the least invasive change that resolves the reproduced failure.",
                        scope="Stay inside the hinted implementation path.",
                        agent_role="Service Flow Builder",
                        milestone="Milestone 2",
                        allowed_paths=["astropy/modeling"],
                        forbidden_paths=["docs"],
                        validation_steps=["Keep the diff tightly scoped."],
                        success_criteria=["The implementation is corrected."],
                        estimated_complexity="small",
                        priority=2,
                        dependencies=[1],
                    ),
                    ManagerTaskItem(
                        title="Validate the fix and prepare an honest handoff",
                        goal="Re-run pytest, record pass/fail honestly, and capture any remaining limitations.",
                        scope="Use the focused validation command and leave evidence-backed handoff notes.",
                        agent_role="Validation Specialist",
                        milestone="Milestone 3",
                        allowed_paths=["astropy/modeling/tests", "astropy/modeling"],
                        forbidden_paths=[],
                        validation_steps=["Run python -m pytest astropy/modeling/tests/test_separable.py -q", "Record pass/fail and limitations."],
                        success_criteria=["Validation evidence is recorded."],
                        estimated_complexity="small",
                        priority=3,
                        dependencies=[2],
                    ),
                ],
            ),
            "manager_ai",
        )

    monkeypatch.setattr(service, "_resolve_manager_model", fake_resolve_manager_model)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Bugfix Task Floor Pass",
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
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nFix the separability regression.\n"
                "Workspace clues:\n"
                "- Files to inspect first: astropy/modeling/tests/test_separable.py\n"
                "- Likely related implementation files: astropy/modeling/separable.py\n"
                "Validation commands:\n"
                "- python -m pytest astropy/modeling/tests/test_separable.py -q\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="new",
        )
        db.add(request)
        db.commit()

        tasks, manager_mode_used = asyncio.run(service.generate_tasks(db, project))

        assert manager_mode_used == "deterministic_guardrail"
        assert tasks[0].title == "Reproduce the failing behavior and isolate the smallest broken path"
        assert tasks[0].allowed_paths_json == ["astropy/modeling/tests", "astropy/modeling"]
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
    assert not service._request_implies_bug_campaign(
        "Run this as a prepared local SWE-bench-style coding task. Issue: this model should be more separable."
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


def test_initialize_build_roster_does_not_open_defect_campaign_for_single_benchmark_bugfix() -> None:
    service = MissionControlService()
    from db import SessionLocal, init_db

    workspace = Path(sample_workspace("benchmark-roster-no-defect-campaign"))
    (workspace / "django/db/models").mkdir(parents=True, exist_ok=True)
    (workspace / "tests/expressions").mkdir(parents=True, exist_ok=True)
    (workspace / "docs").mkdir(parents=True, exist_ok=True)

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Benchmark Roster No Defect Campaign",
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
        request = ChangeRequest(
            project_id=project.id,
            request_text=(
                "Run this as a prepared local SWE-bench-style coding task.\n"
                "Issue:\nContinue fixing the expression ordering problem without widening scope.\n"
                "Workspace clues:\n"
                "- Files to inspect first: tests/expressions/tests.py\n"
                "- Likely related implementation files: django/db/models/expressions.py\n"
                "Focused reproduction commands:\n"
                "- python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql\n"
            ),
            classification="bugfix",
            impact_estimate="medium",
            status="triaged",
        )
        db.add(request)
        db.commit()

        workers = service.initialize_build_roster(db, project)
        plan = service._current_swarm_plan_record(db, project.id)

        assert plan is not None
        assert plan.mode != "defect_campaign"
        assert all(not worker.name.endswith("Subsystem Builder") for worker in workers)
    finally:
        db.close()
