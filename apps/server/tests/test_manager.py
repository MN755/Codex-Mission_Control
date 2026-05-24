from __future__ import annotations

import asyncio
import json

from conftest import sample_workspace
from manager import MissionControlService
from models import Agent, AgentRun, Project, Task
from project_settings import get_or_create_project_settings, resolve_manager_settings, resolve_worker_settings
from schemas import WorkerReport


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
