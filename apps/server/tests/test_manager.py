from __future__ import annotations

import asyncio
import json

from conftest import sample_workspace
from db import SessionLocal
from main import service as app_service
from manager import MissionControlService
from models import Agent, AgentExecutionTrace, AgentRun, Project, RecoveryPlan, Task
from project_settings import get_or_create_project_settings, resolve_manager_settings, resolve_worker_settings
from schemas import ManagerDocFile, ManagerDocUpdate, RunnerResultEnvelope, WorkerReport


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
        worker = Agent(project_id=project.id, name="Builder Agent A", role="Primary implementation", kind="worker", status="working", workspace_path=project.workspace_path, current_task_id=1, locked_paths_json=["src"])
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


def test_finalize_run_rejects_missing_runner_result_envelope() -> None:
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
        recovery_plans = db.query(RecoveryPlan).filter(RecoveryPlan.project_id == project.id).all()
        traces = db.query(AgentExecutionTrace).filter(AgentExecutionTrace.run_id == run.id).all()

        assert run.status == "error"
        assert run.failure_classification == "runner_bug"
        assert task.status == "needs_review"
        assert "envelope validation failed" in (task.waiting_reason or "").lower()
        assert worker.current_task_id is None
        assert recovery_plans
        assert traces == []
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
