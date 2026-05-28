from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from conftest import sample_workspace
from context_packs import context_pack_service
from db import SessionLocal, init_db
from models import (
    Agent,
    AgentArchetype,
    AgentContract,
    AgentExecutionTrace,
    AgentLoadSnapshot,
    AgentInstructionsStatus,
    AgentRun,
    AgentStuckSignal,
    AppEvent,
    AppProfile,
    CodebaseMap,
    CodebaseUnderstanding,
    ConflictRecord,
    DecisionRecord,
    HandoffQualityPreference,
    HandoffEvidence,
    ImportedCodebaseSafety,
    InterviewQuestion,
    InterviewSession,
    ManagerMessage,
    ManagerQuestion,
    ManagerAssumption,
    ModelPolicy,
    PathLock,
    PathReservation,
    OrchestrationSession,
    Project,
    ProjectConfidence,
    ProjectPlaybook,
    ProjectEvent,
    ProjectTimelineEvent,
    ProjectUnderstanding,
    RecoveryPlan,
    RepoIntelligenceSummary,
    ReviewGate,
    SandboxProfile,
    SecurityPolicy,
    SwarmBudget,
    SwarmPreferences,
    Task,
    ToolRoutingPolicy,
    ValidationCoverageArea,
    ValidationRecipe,
    WidgetDefinition,
    WidgetInstance,
    utc_now,
)


def _create_project(client, name: str, workspace_name: str) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"{name} idea",
            "workspace_path": sample_workspace(workspace_name),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_legacy_project(name: str, workspace_name: str) -> int:
    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name=name,
            idea=f"{name} idea",
            workspace_path=sample_workspace(workspace_name),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        db.add(
            Agent(
                project_id=project.id,
                name="Manager AI",
                role="Project orchestration",
                kind="manager",
                status="idle",
                workspace_path=project.workspace_path,
            )
        )
        db.commit()
        return project.id
    finally:
        db.close()


def _support_row_counts(db, project_id: int) -> dict[str, int]:
    return {
        "project_confidence": db.scalar(select(func.count(ProjectConfidence.id)).where(ProjectConfidence.project_id == project_id)),
        "review_gates": db.scalar(select(func.count(ReviewGate.id)).where(ReviewGate.project_id == project_id)),
        "model_policy": db.scalar(select(func.count(ModelPolicy.id)).where(ModelPolicy.project_id == project_id)),
        "tool_routing": db.scalar(select(func.count(ToolRoutingPolicy.id)).where(ToolRoutingPolicy.project_id == project_id)),
        "validation_recipe": db.scalar(select(func.count(ValidationRecipe.id)).where(ValidationRecipe.project_id == project_id)),
        "swarm_budget": db.scalar(select(func.count(SwarmBudget.project_id)).where(SwarmBudget.project_id == project_id)),
    }


def test_project_widget_data_route_keeps_import_and_security_widgets_read_only(client, bridge_headers) -> None:
    workspace = Path(sample_workspace("widget-import-read-only"))
    workspace.mkdir(parents=True, exist_ok=True)
    project_id = _create_legacy_project("Widget Import Read Safety", "widget-import-read-only")

    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        assert project is not None
        project.source_type = "existing_folder"
        project.source_path = workspace.as_posix()
        project.write_permission_status = "read_only"
        db.commit()
    finally:
        db.close()

    widget_types = [
        "Codebase Map",
        "Codebase Understanding",
        "Imported Codebase Safety",
        "AGENTS.md Status",
        "Security Policy",
    ]
    instance_ids: list[int] = []
    for widget_type in widget_types:
        added = client.post(
            f"/api/projects/{project_id}/widgets/add",
            json={"widget_type": widget_type},
            headers=bridge_headers,
        )
        assert added.status_code == 200, added.text
        instance_ids.append(added.json()["id"])

    for instance_id in instance_ids:
        response = client.get(
            f"/api/widgets/instances/{instance_id}/data",
            params={"project_id": project_id},
            headers=bridge_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] in {"ready", "warning", "empty"}

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(CodebaseMap.project_id)).where(CodebaseMap.project_id == project_id)) == 0
        assert db.scalar(select(func.count(CodebaseUnderstanding.project_id)).where(CodebaseUnderstanding.project_id == project_id)) == 0
        assert db.scalar(select(func.count(ImportedCodebaseSafety.project_id)).where(ImportedCodebaseSafety.project_id == project_id)) == 0
        assert db.scalar(select(func.count(AgentInstructionsStatus.project_id)).where(AgentInstructionsStatus.project_id == project_id)) == 0
        assert db.scalar(select(func.count(SecurityPolicy.id)).where(SecurityPolicy.project_id == project_id)) == 0
    finally:
        db.close()


def test_parallelism_safety_meter_data_is_read_only(client, bridge_headers) -> None:
    project = _create_project(client, "Parallelism Read Safety", "parallelism-read-safety")
    project_id = project["id"]

    db = SessionLocal()
    try:
        worker_one = Agent(
            project_id=project_id,
            name="Worker One",
            role="Implementation",
            kind="worker",
            status="running",
            workspace_path=project["workspace_path"],
        )
        worker_two = Agent(
            project_id=project_id,
            name="Worker Two",
            role="Implementation",
            kind="worker",
            status="running",
            workspace_path=project["workspace_path"],
        )
        db.add_all([worker_one, worker_two])
        db.flush()

        task_one = Task(
            project_id=project_id,
            assigned_agent_id=worker_one.id,
            title="Edit API contract",
            goal="Update backend contract safely.",
            scope="Keep the change narrow.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Contract updated"],
            estimated_complexity="small",
            dependencies_json=[],
            status="in_progress",
            priority=10,
        )
        task_two = Task(
            project_id=project_id,
            assigned_agent_id=worker_two.id,
            title="Edit API docs",
            goal="Update docs safely.",
            scope="Keep the change narrow.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Docs updated"],
            estimated_complexity="small",
            dependencies_json=[],
            status="in_progress",
            priority=20,
        )
        db.add_all([task_one, task_two])
        db.flush()

        db.add_all(
            [
                PathReservation(project_id=project_id, task_id=task_one.id, agent_id=worker_one.id, path="apps/server/src/main.py"),
                PathReservation(project_id=project_id, task_id=task_two.id, agent_id=worker_two.id, path="apps/server/src/main.py"),
                ConflictRecord(
                    project_id=project_id,
                    conflict_type="task_dependency",
                    title="Old inactive conflict",
                    summary="This should not be dismissed by a GET route.",
                    involved_agent_ids_json=[worker_one.id],
                    involved_task_ids_json=[task_one.id],
                    affected_paths_json=["docs/README.md"],
                    severity="medium",
                    status="detected",
                    suggested_resolution_json=["ask_user"],
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    added = client.post(
        f"/api/projects/{project_id}/widgets/add",
        json={"widget_type": "Parallelism Safety Meter"},
        headers=bridge_headers,
    )
    assert added.status_code == 200, added.text
    instance_id = added.json()["id"]

    db = SessionLocal()
    try:
        baseline = {
            "conflicts": db.scalar(select(func.count(ConflictRecord.id)).where(ConflictRecord.project_id == project_id)),
            "messages": db.scalar(select(func.count(ManagerMessage.id)).where(ManagerMessage.project_id == project_id)),
            "timeline": db.scalar(select(func.count(ProjectTimelineEvent.id)).where(ProjectTimelineEvent.project_id == project_id)),
            "events": db.scalar(select(func.count(ProjectEvent.id)).where(ProjectEvent.project_id == project_id)),
        }
    finally:
        db.close()

    response = client.get(
        f"/api/widgets/instances/{instance_id}/data",
        params={"project_id": project_id},
        headers=bridge_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] in {"ready", "warning"}
    assert payload["data_json"]["active_locks"] == 2
    assert payload["data_json"]["waiting_locks"] == 0

    db = SessionLocal()
    try:
        after = {
            "conflicts": db.scalar(select(func.count(ConflictRecord.id)).where(ConflictRecord.project_id == project_id)),
            "messages": db.scalar(select(func.count(ManagerMessage.id)).where(ManagerMessage.project_id == project_id)),
            "timeline": db.scalar(select(func.count(ProjectTimelineEvent.id)).where(ProjectTimelineEvent.project_id == project_id)),
            "events": db.scalar(select(func.count(ProjectEvent.id)).where(ProjectEvent.project_id == project_id)),
        }
        assert after == baseline

        stale_conflict = db.scalar(
            select(ConflictRecord)
            .where(ConflictRecord.project_id == project_id, ConflictRecord.title == "Old inactive conflict")
            .order_by(ConflictRecord.id.desc())
        )
        assert stale_conflict is not None
        assert stale_conflict.status == "detected"
    finally:
        db.close()


def test_agent_archetypes_get_does_not_seed_rows(client) -> None:
    init_db()
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AgentArchetype.id))) == 0
    finally:
        db.close()

    response = client.get("/api/agent-archetypes")
    assert response.status_code == 200, response.text
    assert response.json()

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AgentArchetype.id))) == 0
    finally:
        db.close()


def test_swarm_preferences_get_returns_defaults_without_persisting_row(client) -> None:
    project_id = _create_legacy_project("Swarm Read Safety", "swarm-read-safety")

    response = client.get(f"/api/projects/{project_id}/swarm/preferences")
    assert response.status_code == 200, response.text
    assert response.json()["optimization_mode"] == "balanced"

    db = SessionLocal()
    try:
        row_count = db.scalar(select(func.count(SwarmPreferences.project_id)).where(SwarmPreferences.project_id == project_id))
        assert row_count == 0
    finally:
        db.close()


def test_validation_coverage_get_returns_preview_without_persisting_rows(client) -> None:
    project_id = _create_legacy_project("Coverage Preview", "coverage-preview")

    response = client.get(f"/api/projects/{project_id}/validation-coverage")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    assert all(item["project_id"] == project_id for item in payload)

    db = SessionLocal()
    try:
        row_count = db.scalar(select(func.count(ValidationCoverageArea.id)).where(ValidationCoverageArea.project_id == project_id))
        assert row_count == 0
    finally:
        db.close()


def test_project_status_summary_get_is_read_only_for_support_records(client, bridge_headers) -> None:
    project_id = _create_legacy_project("Project Status Summary Read Safety", "project-status-summary-read-safety")

    db = SessionLocal()
    try:
        baseline = _support_row_counts(db, project_id)
        assert baseline == {
            "project_confidence": 0,
            "review_gates": 0,
            "model_policy": 0,
            "tool_routing": 0,
            "validation_recipe": 0,
            "swarm_budget": 0,
        }
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/status-summary", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["message_type"] in {"status_update", "blocked"}
    assert "## Mission Control Status" in payload["fallback_markdown"]

    db = SessionLocal()
    try:
        assert _support_row_counts(db, project_id) == baseline
    finally:
        db.close()


def test_orchestration_status_summary_get_is_read_only_for_support_records(client, bridge_headers) -> None:
    project_id = _create_legacy_project("Orchestration Status Summary Read Safety", "orchestration-status-summary-read-safety")

    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        assert project is not None
        session = OrchestrationSession(
            project_id=project.id,
            workspace_path=project.workspace_path,
            source="codex_plugin",
            user_request="Check status safely.",
            status="running",
            manager_status="Reviewing background work.",
            mode="existing_codebase",
            metadata_json={},
        )
        db.add(session)
        db.commit()
        orchestration_id = session.id
        baseline = _support_row_counts(db, project_id)
        assert baseline == {
            "project_confidence": 0,
            "review_gates": 0,
            "model_policy": 0,
            "tool_routing": 0,
            "validation_recipe": 0,
            "swarm_budget": 0,
        }
    finally:
        db.close()

    response = client.get(
        f"/api/orchestrations/{orchestration_id}/status-summary",
        headers=bridge_headers,
        params={"project_id": project_id},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["message_type"] in {"status_update", "blocked"}
    assert "## Mission Control Status" in payload["fallback_markdown"]

    db = SessionLocal()
    try:
        assert _support_row_counts(db, project_id) == baseline
    finally:
        db.close()


def test_widget_catalog_get_does_not_seed_or_overwrite_rows(client) -> None:
    init_db()
    db = SessionLocal()
    try:
        existing = WidgetDefinition(
            widget_type="Needs Attention",
            title="Custom Needs Attention",
            description="Keep operator override intact.",
            scope="dashboard",
            default_area="dashboard_main",
            default_size="large",
            category="ops",
            requires_project=False,
            requires_tool=None,
            coming_soon=False,
            risk_level="low",
        )
        db.add(existing)
        db.commit()
        existing_id = existing.id
    finally:
        db.close()

    response = client.get("/api/widgets/catalog")
    assert response.status_code == 200, response.text
    catalog = response.json()
    custom = next(item for item in catalog if item["widget_type"] == "Needs Attention")
    assert custom["title"] == "Custom Needs Attention"

    db = SessionLocal()
    try:
        rows = list(db.scalars(select(WidgetDefinition).order_by(WidgetDefinition.id.asc())))
        assert len(rows) == 1
        assert rows[0].id == existing_id
        assert rows[0].title == "Custom Needs Attention"
    finally:
        db.close()


def test_read_only_profile_backed_routes_do_not_create_app_profile(client) -> None:
    project = _create_legacy_project("Profile Read Safety", "profile-read-safety")

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AppProfile.id))) == 0
    finally:
        db.close()

    responses = [
        client.get("/api/tools"),
        client.get("/api/dashboard/summary"),
        client.get(f"/api/settings?project_id={project}"),
        client.get(f"/api/projects/{project}/action"),
        client.get(f"/api/projects/{project}/actions"),
        client.get(f"/api/projects/{project}/workspace"),
    ]
    for response in responses:
        assert response.status_code == 200, response.text

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AppProfile.id))) == 0
    finally:
        db.close()


def test_dashboard_support_widget_data_stays_read_only(client, bridge_headers) -> None:
    project_id = _create_legacy_project("Dashboard Widget Read Safety", "dashboard-widget-read-safety")

    db = SessionLocal()
    try:
        db.add_all(
            [
                WidgetInstance(
                    scope="dashboard",
                    project_id=None,
                    widget_type="Project Health Overview",
                    area="dashboard_main",
                    order_index=0,
                    size="large",
                    enabled=True,
                    config_json={},
                ),
                WidgetInstance(
                    scope="dashboard",
                    project_id=None,
                    widget_type="Swarm Budget Overview",
                    area="dashboard_main",
                    order_index=1,
                    size="large",
                    enabled=True,
                    config_json={},
                ),
            ]
        )
        db.commit()
        instance_ids = list(db.scalars(select(WidgetInstance.id).order_by(WidgetInstance.id.asc())))
        assert instance_ids
    finally:
        db.close()

    for instance_id in instance_ids:
        response = client.get(
            f"/api/widgets/instances/{instance_id}/data",
            headers=bridge_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] in {"ready", "warning", "empty"}

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AppProfile.id))) == 0
        assert db.scalar(select(func.count(ProjectConfidence.id)).where(ProjectConfidence.project_id == project_id)) == 0
        assert db.scalar(select(func.count(ReviewGate.id)).where(ReviewGate.project_id == project_id)) == 0
    finally:
        db.close()


def test_playbook_catalog_get_does_not_seed_or_overwrite_rows(client) -> None:
    init_db()
    db = SessionLocal()
    try:
        existing = ProjectPlaybook(
            key="local_desktop_app",
            name="Custom Desktop Playbook",
            description="Keep custom playbook edits intact.",
            suggested_interview_categories_json=["custom"],
            suggested_swarm_mode="balanced",
            suggested_agent_archetypes_json=["backend"],
            suggested_validation_recipe_json=[{"title": "Custom"}],
            common_risks_json=["custom risk"],
            suggested_docs_json=["CUSTOM.md"],
            typical_structure_json=["custom"],
        )
        db.add(existing)
        db.commit()
        existing_id = existing.id
    finally:
        db.close()

    response = client.get("/api/playbooks")
    assert response.status_code == 200, response.text
    catalog = response.json()
    custom = next(item for item in catalog if item["key"] == "local_desktop_app")
    assert custom["name"] == "Custom Desktop Playbook"

    db = SessionLocal()
    try:
        rows = list(db.scalars(select(ProjectPlaybook).order_by(ProjectPlaybook.id.asc())))
        assert len(rows) == 1
        assert rows[0].id == existing_id
        assert rows[0].name == "Custom Desktop Playbook"
    finally:
        db.close()


def test_safe_mode_get_and_import_safety_do_not_mutate_non_imported_project(client, bridge_headers) -> None:
    project_id = _create_legacy_project("Safe Mode Read", "safe-mode-read")

    response = client.get(f"/api/projects/{project_id}/safe-mode", headers=bridge_headers)
    assert response.status_code == 200, response.text
    assert response.json()["project_id"] == project_id

    import_safety = client.get(f"/api/projects/{project_id}/import-safety")
    assert import_safety.status_code == 400

    db = SessionLocal()
    try:
        project_policy_count = db.scalar(select(func.count(SecurityPolicy.id)).where(SecurityPolicy.project_id == project_id))
        swarm_pref_count = db.scalar(select(func.count(SwarmPreferences.project_id)).where(SwarmPreferences.project_id == project_id))
        import_safety_count = db.scalar(select(func.count(ImportedCodebaseSafety.project_id)).where(ImportedCodebaseSafety.project_id == project_id))
        assert project_policy_count == 0
        assert swarm_pref_count == 0
        assert import_safety_count == 0
    finally:
        db.close()


def test_path_locks_get_is_read_only(client, bridge_headers) -> None:
    project = _create_project(client, "Path Lock Read Safety", "path-lock-read-safety")
    project_id = project["id"]

    db = SessionLocal()
    try:
        worker = Agent(
            project_id=project_id,
            name="Worker",
            role="Implementation",
            kind="worker",
            status="running",
            workspace_path=project["workspace_path"],
        )
        db.add(worker)
        db.flush()
        task = Task(
            project_id=project_id,
            assigned_agent_id=worker.id,
            title="Blocked task",
            goal="Wait for a path to clear.",
            scope="Keep the change narrow.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["src/**"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Path becomes available"],
            estimated_complexity="small",
            dependencies_json=[],
            status="waiting_on_paths",
            priority=10,
            waiting_reason="Waiting on path ownership.",
        )
        db.add(task)
        db.commit()
        assert db.scalar(select(func.count(PathLock.id)).where(PathLock.project_id == project_id)) == 0
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/path-locks", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    assert payload[0]["path_pattern"] == "src/**"

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(PathLock.id)).where(PathLock.project_id == project_id)) == 0
    finally:
        db.close()


def test_agent_contracts_get_is_read_only(client, bridge_headers) -> None:
    project = _create_project(client, "Agent Contract Read Safety", "agent-contract-read-safety")
    project_id = project["id"]

    db = SessionLocal()
    try:
        db.add(
            Agent(
                project_id=project_id,
                name="Builder",
                role="Implementation",
                kind="worker",
                status="working",
                workspace_path=project["workspace_path"],
                current_action="Implement the next small change.",
            )
        )
        db.commit()
        assert db.scalar(select(func.count(AgentContract.id)).where(AgentContract.project_id == project_id)) == 0
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/agent-contracts", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    assert payload[0]["agent_name"] == "Builder"

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AgentContract.id)).where(AgentContract.project_id == project_id)) == 0
    finally:
        db.close()


def test_decision_ledger_get_is_read_only(client, bridge_headers) -> None:
    project = _create_project(client, "Decision Ledger Read Safety", "decision-ledger-read-safety")
    project_id = project["id"]

    db = SessionLocal()
    try:
        db.add(
            ManagerQuestion(
                project_id=project_id,
                question="Should Mission Control preserve the current API shape?",
                options_json=[{"id": "preserve", "label": "Preserve it"}],
                impact="medium",
                status="answered",
                selected_option_id="preserve",
                selected_text="Preserve it",
                manager_recommendation="Preserve it",
            )
        )
        db.commit()
        assert db.scalar(select(func.count(DecisionRecord.id)).where(DecisionRecord.project_id == project_id)) == 0
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/decision-ledger", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    assert payload[0]["decision_type"] == "manager_question"
    assert payload[0]["decision"] == "Preserve it"

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(DecisionRecord.id)).where(DecisionRecord.project_id == project_id)) == 0
    finally:
        db.close()


def test_manager_read_endpoints_do_not_auto_decide_due_questions(client, bridge_headers) -> None:
    project = _create_project(client, "Question Read Safety", "question-read-safety")
    project_id = project["id"]

    db = SessionLocal()
    try:
        question = ManagerQuestion(
            project_id=project_id,
            question="Ship it?",
            options_json=[{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
            impact="medium",
            status="pending",
            auto_decide_at=utc_now() - timedelta(minutes=1),
            manager_recommendation="yes",
        )
        db.add(question)
        db.commit()
        question_id = question.id
    finally:
        db.close()

    def assert_question_still_pending() -> None:
        db = SessionLocal()
        try:
            stored = db.get(ManagerQuestion, question_id)
            assert stored is not None
            assert stored.status == "pending"
            assert stored.selected_option_id is None
            assert stored.resolved_at is None
        finally:
            db.close()

    pending = client.get(f"/api/projects/{project_id}/questions/pending", headers=bridge_headers)
    assert pending.status_code == 200, pending.text
    assert pending.json()[0]["id"] == question_id
    assert_question_still_pending()

    queue = client.get(f"/api/projects/{project_id}/manager/queue", headers=bridge_headers)
    assert queue.status_code == 200, queue.text
    assert_question_still_pending()

    action = client.get(f"/api/projects/{project_id}/action", headers=bridge_headers)
    assert action.status_code == 200, action.text
    assert action.json()["question_id"] == question_id
    assert_question_still_pending()

    actions = client.get(f"/api/projects/{project_id}/actions", headers=bridge_headers)
    assert actions.status_code == 200, actions.text
    assert actions.json()[0]["question_id"] == question_id
    assert_question_still_pending()

    workspace = client.get(f"/api/projects/{project_id}/workspace", headers=bridge_headers)
    assert workspace.status_code == 200, workspace.text
    assert_question_still_pending()


def test_pending_questions_read_does_not_create_interview_question_mirror(client, bridge_headers) -> None:
    project_id = _create_legacy_project("Interview Mirror Read Safety", "interview-mirror-read-safety")

    db = SessionLocal()
    try:
        session = InterviewSession(
            project_id=project_id,
            question_count=1,
            question_budget=5,
            questions_asked=0,
            current_index=0,
            status="in_progress",
            manager_mode="auto",
        )
        db.add(session)
        db.flush()
        db.add(
            InterviewQuestion(
                session_id=session.id,
                project_id=project_id,
                index=0,
                question="What stack?",
                category="architecture",
                impact="medium",
                options_json=[{"id": "react", "label": "React"}, {"id": "vue", "label": "Vue"}],
                status="pending",
                question_source="fallback_generated",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/questions/pending", headers=bridge_headers)
    assert response.status_code == 200, response.text
    assert response.json() == []

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ManagerQuestion.id)).where(ManagerQuestion.project_id == project_id)) == 0
    finally:
        db.close()


def test_swarm_preferences_get_is_read_only(client, bridge_headers) -> None:
    project_id = _create_legacy_project("Swarm Preferences Read Safety", "swarm-preferences-read-safety")

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(SwarmPreferences.project_id)).where(SwarmPreferences.project_id == project_id)) == 0
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/swarm/preferences", headers=bridge_headers)
    assert response.status_code == 200, response.text
    assert response.json()["project_id"] == project_id

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(SwarmPreferences.project_id)).where(SwarmPreferences.project_id == project_id)) == 0
    finally:
        db.close()


def test_validation_coverage_get_is_read_only(client, bridge_headers) -> None:
    project_id = _create_legacy_project("Validation Coverage Read Safety", "validation-coverage-read-safety")

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ValidationCoverageArea.id)).where(ValidationCoverageArea.project_id == project_id)) == 0
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/validation-coverage", headers=bridge_headers)
    assert response.status_code == 200, response.text
    assert response.json()

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ValidationCoverageArea.id)).where(ValidationCoverageArea.project_id == project_id)) == 0
    finally:
        db.close()


def test_agent_archetype_catalog_get_is_read_only_and_preserves_edits(client, bridge_headers) -> None:
    empty_catalog = client.get("/api/agent-archetypes", headers=bridge_headers)
    assert empty_catalog.status_code == 200, empty_catalog.text

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AgentArchetype.id))) == 0
        custom = AgentArchetype(
            name="frontend",
            purpose="CUSTOM PURPOSE",
            default_guidelines="Custom guidelines",
            default_tools_json=["edit"],
            default_permissions_json={"writes": "workspace"},
            spawn_triggers_json=["custom"],
            retirement_triggers_json=["done"],
            risk_profile="medium",
        )
        db.add(custom)
        db.commit()
        custom_id = custom.id
    finally:
        db.close()


def test_project_widget_summary_stays_read_only_for_support_records(client, bridge_headers) -> None:
    project = _create_project(client, "Widget Summary Read Safety", "widget-summary-read-safety")
    project_id = project["id"]

    widget_types = [
        "Confidence Tracker",
        "Merge / Review Gates",
        "Model Assignment Policy",
        "Tool Routing Policy",
        "Sandbox Profiles",
    ]
    for widget_type in widget_types:
        added = client.post(
            f"/api/projects/{project_id}/widgets/add",
            json={"widget_type": widget_type},
            headers=bridge_headers,
        )
        assert added.status_code == 200, added.text

    db = SessionLocal()
    try:
        baseline = {
            "confidence": db.scalar(select(func.count(ProjectConfidence.id)).where(ProjectConfidence.project_id == project_id)),
            "review_gates": db.scalar(select(func.count(ReviewGate.id)).where(ReviewGate.project_id == project_id)),
            "model_policy": db.scalar(select(func.count(ModelPolicy.id)).where(ModelPolicy.project_id == project_id)),
            "tool_routing": db.scalar(select(func.count(ToolRoutingPolicy.id)).where(ToolRoutingPolicy.project_id == project_id)),
            "sandbox_profiles": db.scalar(select(func.count(SandboxProfile.id)).where(SandboxProfile.project_id.is_(None))),
        }
        assert baseline == {
            "confidence": 0,
            "review_gates": 0,
            "model_policy": 0,
            "tool_routing": 0,
            "sandbox_profiles": 0,
        }
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/widgets/summary", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope"] == "project"
    assert len(payload["instances"]) == len(widget_types)
    returned_types = {item["widget_type"] for item in payload["data"]}
    assert set(widget_types).issubset(returned_types)

    db = SessionLocal()
    try:
        after = {
            "confidence": db.scalar(select(func.count(ProjectConfidence.id)).where(ProjectConfidence.project_id == project_id)),
            "review_gates": db.scalar(select(func.count(ReviewGate.id)).where(ReviewGate.project_id == project_id)),
            "model_policy": db.scalar(select(func.count(ModelPolicy.id)).where(ModelPolicy.project_id == project_id)),
            "tool_routing": db.scalar(select(func.count(ToolRoutingPolicy.id)).where(ToolRoutingPolicy.project_id == project_id)),
            "sandbox_profiles": db.scalar(select(func.count(SandboxProfile.id)).where(SandboxProfile.project_id.is_(None))),
        }
        assert after == baseline
    finally:
        db.close()


def test_global_id_routes_require_matching_project_scope(client, bridge_headers) -> None:
    project_one = _create_project(client, "Scope One", "scope-one-read")
    project_two = _create_project(client, "Scope Two", "scope-two-read")

    workspace = Path(project_one["workspace_path"])
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# Existing codebase\n", encoding="utf-8")

    pack = client.post(
        f"/api/projects/{project_one['id']}/context-packs/build",
        json={"title": "Scoped Pack", "goal": "Summarize the repo for workers."},
    )
    assert pack.status_code == 200, pack.text
    pack_id = pack.json()["id"]

    wrong_pack = client.get(f"/api/context-packs/{pack_id}", params={"project_id": project_two["id"]})
    assert wrong_pack.status_code == 404

    orchestration = client.post(
        "/api/orchestrations",
        headers=bridge_headers,
        json={"project_id": project_one["id"], "user_request": "Run Mission Control here.", "source": "test"},
    )
    assert orchestration.status_code == 200, orchestration.text
    orchestration_id = orchestration.json()["id"]

    wrong_orchestration = client.get(
        f"/api/orchestrations/{orchestration_id}",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_orchestration.status_code == 404

    wrong_status = client.get(
        f"/api/orchestrations/{orchestration_id}/status",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_status.status_code == 404

    wrong_pause = client.post(
        f"/api/orchestrations/{orchestration_id}/pause",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_pause.status_code == 404

    opened = client.post(f"/api/projects/{project_one['id']}/open")
    assert opened.status_code == 200, opened.text
    question = client.get(f"/api/projects/{project_one['id']}/questions/pending").json()[0]
    wrong_auto_decide = client.post(
        f"/api/questions/{question['id']}/auto-decide",
        params={"project_id": project_two["id"]},
    )
    assert wrong_auto_decide.status_code == 404

    paused = client.post(
        f"/api/orchestrations/{orchestration_id}/pause",
        headers=bridge_headers,
        params={"project_id": project_one["id"]},
    )
    assert paused.status_code == 200, paused.text

    wrong_resume = client.post(
        f"/api/orchestrations/{orchestration_id}/resume",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_resume.status_code == 404

    db = SessionLocal()
    try:
        stored = db.get(Project, project_one["id"])
        assert stored is not None
    finally:
        db.close()


def test_agent_and_task_global_id_routes_require_matching_project_scope(client, bridge_headers) -> None:
    project_one = _create_project(client, "Action Scope One", "action-scope-one")
    project_two = _create_project(client, "Action Scope Two", "action-scope-two")

    log_path = Path(project_one["workspace_path"]) / "worker.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("worker output\n", encoding="utf-8")

    db = SessionLocal()
    try:
        scoped_agent = Agent(
            project_id=project_one["id"],
            name="Scoped Worker",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project_one["workspace_path"],
        )
        db.add(scoped_agent)
        db.flush()

        scoped_task = Task(
            project_id=project_one["id"],
            assigned_agent_id=scoped_agent.id,
            title="Scoped task",
            goal="Keep task ownership scoped.",
            scope="Do not leak across projects.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["README.md"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Scope preserved"],
            estimated_complexity="small",
            dependencies_json=[],
            status="todo",
            priority=10,
        )
        db.add(scoped_task)
        db.flush()
        db.add(
            AgentRun(
                agent_id=scoped_agent.id,
                task_id=scoped_task.id,
                runner_type="dry_run",
                process_ref="scoped-log-run",
                status="done",
                logs_path=log_path.as_posix(),
            )
        )
        db.commit()
        agent_id = scoped_agent.id
        task_id = scoped_task.id
    finally:
        db.close()

    wrong_agent_start = client.post(
        f"/api/agents/{agent_id}/start",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_agent_start.status_code == 404

    wrong_agent_stop = client.post(
        f"/api/agents/{agent_id}/stop",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_agent_stop.status_code == 404

    wrong_agent_pause = client.post(
        f"/api/agents/{agent_id}/pause",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_agent_pause.status_code == 404

    wrong_agent_logs = client.get(
        f"/api/agents/{agent_id}/logs",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_agent_logs.status_code == 404

    wrong_task_start = client.post(
        f"/api/tasks/{task_id}/start",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_task_start.status_code == 404

    wrong_task_complete = client.post(
        f"/api/tasks/{task_id}/complete",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_task_complete.status_code == 404


def test_project_routes_reject_invalid_related_resource_ids(client) -> None:
    project = _create_project(client, "Reference Validation", "reference-validation")
    foreign_project = _create_project(client, "Foreign Reference Validation", "reference-validation-foreign")
    project_id = project["id"]

    db = SessionLocal()
    try:
        foreign_agent = Agent(
            project_id=foreign_project["id"],
            name="Foreign Context Agent",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=foreign_project["workspace_path"],
        )
        db.add(foreign_agent)
        db.flush()
        foreign_task = Task(
            project_id=foreign_project["id"],
            assigned_agent_id=foreign_agent.id,
            title="Foreign context task",
            goal="Stay scoped to the foreign project.",
            scope="Foreign scope only.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Stay foreign"],
            estimated_complexity="small",
            dependencies_json=[],
            status="todo",
            priority=30,
        )
        db.add(foreign_task)
        db.commit()
        foreign_agent_id = foreign_agent.id
        foreign_task_id = foreign_task.id
    finally:
        db.close()

    invalid_context_agent = client.post(
        f"/api/projects/{project_id}/context-packs/build",
        json={"title": "Bad agent", "goal": "Validate refs", "agent_id": 999999},
    )
    assert invalid_context_agent.status_code == 404

    invalid_context_task = client.post(
        f"/api/projects/{project_id}/context-packs/build",
        json={"title": "Bad task", "goal": "Validate refs", "task_id": 999999},
    )
    assert invalid_context_task.status_code == 404

    foreign_context_agent = client.post(
        f"/api/projects/{project_id}/context-packs/build",
        json={"title": "Foreign agent", "goal": "Validate refs", "agent_id": foreign_agent_id},
    )
    assert foreign_context_agent.status_code == 404

    foreign_context_task = client.post(
        f"/api/projects/{project_id}/context-packs/build",
        json={"title": "Foreign task", "goal": "Validate refs", "task_id": foreign_task_id},
    )
    assert foreign_context_task.status_code == 404

    invalid_risk_owner = client.post(
        f"/api/projects/{project_id}/risks",
        json={
            "title": "Risk owner missing",
            "description": "Owner should exist.",
            "severity": "medium",
            "likelihood": "medium",
            "owner_agent_id": 999999,
        },
    )
    assert invalid_risk_owner.status_code == 404

    invalid_risk_task = client.post(
        f"/api/projects/{project_id}/risks",
        json={
            "title": "Risk task missing",
            "description": "Task should exist.",
            "severity": "medium",
            "likelihood": "medium",
            "related_task_id": 999999,
        },
    )
    assert invalid_risk_task.status_code == 404

    invalid_scope_task = client.post(
        f"/api/projects/{project_id}/scope-creep/analyze",
        json={"summary": "This clearly drifts scope.", "related_task_id": 999999},
    )
    assert invalid_scope_task.status_code == 404

    invalid_scope_message = client.post(
        f"/api/projects/{project_id}/scope-creep/analyze",
        json={"summary": "This also drifts scope.", "related_message_id": 999999},
    )
    assert invalid_scope_message.status_code == 404

    invalid_snapshot_task = client.post(
        f"/api/projects/{project_id}/snapshots",
        json={
            "label": "Bad task snapshot",
            "description": "Should reject missing task.",
            "created_before_task_id": 999999,
        },
    )
    assert invalid_snapshot_task.status_code == 404

    invalid_snapshot_agent = client.post(
        f"/api/projects/{project_id}/snapshots",
        json={
            "label": "Bad agent snapshot",
            "description": "Should reject missing agent.",
            "created_before_agent_id": 999999,
        },
    )
    assert invalid_snapshot_agent.status_code == 404

    invalid_recovery_task = client.post(
        f"/api/projects/{project_id}/recovery-plans",
        json={
            "trigger_type": "task_blocked",
            "trigger_summary": "Recovery needs a real task.",
            "related_task_id": 999999,
            "suggested_actions_json": ["ask_user"],
        },
    )
    assert invalid_recovery_task.status_code == 404

    invalid_recovery_agent = client.post(
        f"/api/projects/{project_id}/recovery-plans",
        json={
            "trigger_type": "agent_stuck",
            "trigger_summary": "Recovery needs a real agent.",
            "related_agent_id": 999999,
            "suggested_actions_json": ["ask_user"],
        },
    )
    assert invalid_recovery_agent.status_code == 404


def test_context_pack_service_rejects_invalid_or_cross_project_refs(client) -> None:
    project = _create_project(client, "Context Pack Service Scope", "context-pack-service-scope")
    foreign_project = _create_project(client, "Context Pack Service Foreign", "context-pack-service-foreign")

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project["id"])
        assert scoped_project is not None

        foreign_agent = Agent(
            project_id=foreign_project["id"],
            name="Foreign Service Agent",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=foreign_project["workspace_path"],
        )
        db.add(foreign_agent)
        db.flush()
        foreign_task = Task(
            project_id=foreign_project["id"],
            assigned_agent_id=foreign_agent.id,
            title="Foreign service task",
            goal="Reject cross-project task refs.",
            scope="Foreign project only.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Rejected correctly"],
            estimated_complexity="small",
            dependencies_json=[],
            status="todo",
            priority=40,
        )
        db.add(foreign_task)
        db.commit()

        with pytest.raises(ValueError, match="Agent not found"):
            context_pack_service.build_context_pack(db, scoped_project, agent_id=999999)
        with pytest.raises(ValueError, match="Agent not found in this project"):
            context_pack_service.build_context_pack(db, scoped_project, agent_id=foreign_agent.id)
        with pytest.raises(ValueError, match="Task not found"):
            context_pack_service.build_context_pack(db, scoped_project, task_id=999999)
        with pytest.raises(ValueError, match="Task not found in this project"):
            context_pack_service.build_context_pack(db, scoped_project, task_id=foreign_task.id)
    finally:
        db.close()


def test_run_report_requires_matching_project_scope(client, bridge_headers) -> None:
    project_one = _create_project(client, "Run Scope One", "run-scope-one")
    project_two = _create_project(client, "Run Scope Two", "run-scope-two")

    db = SessionLocal()
    try:
        worker = Agent(
            project_id=project_one["id"],
            name="Scoped Run Worker",
            role="Implementation",
            kind="worker",
            status="working",
            workspace_path=project_one["workspace_path"],
        )
        db.add(worker)
        db.flush()
        task = Task(
            project_id=project_one["id"],
            assigned_agent_id=worker.id,
            title="Scoped run task",
            goal="Keep run reports project-scoped.",
            scope="Protect foreign runs.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["README.md"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Run stays scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="working",
            priority=25,
        )
        db.add(task)
        db.flush()
        run = AgentRun(
            agent_id=worker.id,
            task_id=task.id,
            runner_type="dry_run",
            process_ref="scoped-run-report",
            status="running",
        )
        db.add(run)
        db.commit()
        run_id = run.id
        task_id = task.id
        agent_id = worker.id
    finally:
        db.close()

    response = client.post(
        f"/api/runs/{run_id}/report",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
        json={
            "agent": "Attacker",
            "task_id": "999",
            "status": "done",
            "summary": "attacker completed foreign work",
            "files_changed": ["secret.txt"],
            "tests_run": ["pytest"],
            "blockers": [],
            "risks": ["foreign"],
            "recommended_next_task": "none",
        },
    )
    assert response.status_code == 404

    db = SessionLocal()
    try:
        persisted_run = db.get(AgentRun, run_id)
        persisted_task = db.get(Task, task_id)
        persisted_agent = db.get(Agent, agent_id)
        assert persisted_run is not None
        assert persisted_task is not None
        assert persisted_agent is not None
        assert persisted_run.status == "running"
        assert persisted_run.finished_at is None
        assert persisted_run.report_json in (None, {})
        assert persisted_task.status == "working"
        assert persisted_agent.status == "working"
    finally:
        db.close()


def test_handoff_evidence_get_is_read_only_and_preview_derives_without_persisting(client, bridge_headers) -> None:
    init_db()
    db = SessionLocal()
    try:
        workspace_path = sample_workspace("handoff-evidence-preview")
        project = Project(
            name="Handoff Evidence Preview",
            idea="Verify read safety for handoff evidence",
            workspace_path=workspace_path,
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        db.add(Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=workspace_path))
        worker = Agent(
            project_id=project.id,
            name="Builder Agent",
            role="Implementation",
            kind="worker",
            status="done",
            workspace_path=workspace_path,
        )
        db.add(worker)
        db.flush()
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Ship the core flow",
            goal="Implement the workflow",
            scope="Keep the test scope small.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Workflow works"],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=10,
        )
        db.add(task)
        db.flush()
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=task.id,
                runner_type="dry_run",
                process_ref="dry-test",
                status="done",
                report_json={
                    "summary": "Implemented the first useful slice.",
                    "tests_run": ["pytest -q"],
                    "files_changed": ["src/app.py"],
                },
            )
        )
        db.commit()
        project_id = project.id
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/handoff/evidence", headers=bridge_headers)
    assert response.status_code == 200, response.text
    assert response.json() == []

    preview = client.get(f"/api/projects/{project_id}/handoff/evidence/preview", headers=bridge_headers)
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["project_id"] == project_id
    assert payload["stored_count"] == 0
    assert payload["derived_candidate_count"] == 3
    assert payload["persisted"] == []
    assert {item["evidence_type"] for item in payload["derived_candidates"]} == {"file_change", "test_result", "report"}

    db = SessionLocal()
    try:
        handoff_evidence_count = db.scalar(select(func.count(HandoffEvidence.id)).where(HandoffEvidence.project_id == project_id))
        assert handoff_evidence_count == 0
    finally:
        db.close()


def test_recovery_plans_get_is_read_only_and_preview_stays_non_persistent(client, bridge_headers) -> None:
    init_db()
    db = SessionLocal()
    try:
        workspace_path = sample_workspace("recovery-plan-preview")
        project = Project(
            name="Recovery Preview",
            idea="Verify read safety for recovery plans",
            workspace_path=workspace_path,
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        db.add(Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=workspace_path))
        worker = Agent(
            project_id=project.id,
            name="Verifier Agent",
            role="Validation",
            kind="worker",
            status="blocked",
            workspace_path=workspace_path,
            current_action="Waiting for a fix path.",
        )
        db.add(worker)
        db.flush()
        db.add(
            Task(
                project_id=project.id,
                assigned_agent_id=worker.id,
                title="Unblock verifier",
                goal="Recover from the blocked worker state",
                scope="Recovery-only test scope.",
                agent_role="Validation",
                milestone="MVP",
                allowed_paths_json=["tests"],
                forbidden_paths_json=[],
                validation_steps_json=["pytest -q"],
                success_criteria_json=["Verifier unblocked"],
                estimated_complexity="small",
                dependencies_json=[],
                status="blocked",
                waiting_reason="Verifier is blocked on a missing fix.",
                priority=10,
            )
        )
        db.commit()
        project_id = project.id
    finally:
        db.close()


def test_project_widget_summary_stays_read_only_for_support_widgets(client, bridge_headers) -> None:
    init_db()
    db = SessionLocal()
    try:
        workspace_path = sample_workspace("widget-summary-read-only")
        workspace = Path(workspace_path)
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "README.md").write_text("# Widget Summary Read Safety\n", encoding="utf-8")

        project = Project(
            name="Widget Summary Read Safety",
            idea="Keep summary reads non-persistent.",
            workspace_path=workspace_path,
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()

        manager = Agent(
            project_id=project.id,
            name="Manager AI",
            role="Project orchestration",
            kind="manager",
            status="idle",
            workspace_path=workspace_path,
        )
        blocked_worker = Agent(
            project_id=project.id,
            name="Blocked Worker",
            role="Implementation",
            kind="worker",
            status="blocked",
            current_action="Waiting on a conflict decision.",
            last_report_summary="Blocked on path ownership.",
            workspace_path=workspace_path,
        )
        finished_worker = Agent(
            project_id=project.id,
            name="Finished Worker",
            role="Implementation",
            kind="worker",
            status="done",
            workspace_path=workspace_path,
        )
        db.add_all([manager, blocked_worker, finished_worker])
        db.flush()

        blocked_task = Task(
            project_id=project.id,
            assigned_agent_id=blocked_worker.id,
            title="Blocked backend task",
            goal="Fix the blocked backend path.",
            scope="Keep the scope small.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Blocker resolved"],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=10,
        )
        finished_task = Task(
            project_id=project.id,
            assigned_agent_id=finished_worker.id,
            title="Completed docs task",
            goal="Finish the docs slice.",
            scope="Keep the scope small.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["README.md"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Docs updated"],
            estimated_complexity="small",
            dependencies_json=[],
            status="done",
            priority=20,
        )
        db.add_all([blocked_task, finished_task])
        db.flush()

        db.add(
            AgentRun(
                agent_id=finished_worker.id,
                task_id=finished_task.id,
                runner_type="dry_run",
                process_ref="summary-read-test",
                status="done",
                report_json={
                    "summary": "Updated the docs successfully.",
                    "tests_run": ["pytest -q"],
                    "files_changed": ["README.md"],
                },
            )
        )
        db.add(
            ProjectUnderstanding(
                project_id=project.id,
                summary="The project still needs stronger test coverage.",
                assumptions_json=["Need test coverage"],
                unknowns_json={"validation": ["Need a clearer smoke test path."]},
            )
        )
        db.commit()
        project_id = project.id
    finally:
        db.close()


def test_project_widget_summary_conflict_resolver_is_read_only(client, bridge_headers) -> None:
    project = _create_project(client, "Conflict Summary Read Safety", "conflict-summary-read-safety")
    project_id = project["id"]

    db = SessionLocal()
    try:
        worker_one = Agent(
            project_id=project_id,
            name="Worker One",
            role="Implementation",
            kind="worker",
            status="running",
            workspace_path=project["workspace_path"],
        )
        worker_two = Agent(
            project_id=project_id,
            name="Worker Two",
            role="Implementation",
            kind="worker",
            status="running",
            workspace_path=project["workspace_path"],
        )
        db.add_all([worker_one, worker_two])
        db.flush()

        task_one = Task(
            project_id=project_id,
            assigned_agent_id=worker_one.id,
            title="Edit API contract",
            goal="Update backend contract safely.",
            scope="Keep the change narrow.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Contract updated"],
            estimated_complexity="small",
            dependencies_json=[],
            status="in_progress",
            priority=10,
        )
        task_two = Task(
            project_id=project_id,
            assigned_agent_id=worker_two.id,
            title="Edit API docs",
            goal="Update docs safely.",
            scope="Keep the change narrow.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["pytest -q"],
            success_criteria_json=["Docs updated"],
            estimated_complexity="small",
            dependencies_json=[],
            status="in_progress",
            priority=20,
        )
        db.add_all([task_one, task_two])
        db.flush()

        db.add_all(
            [
                PathReservation(project_id=project_id, task_id=task_one.id, agent_id=worker_one.id, path="apps/server/src/main.py"),
                PathReservation(project_id=project_id, task_id=task_two.id, agent_id=worker_two.id, path="apps/server/src/main.py"),
                ConflictRecord(
                    project_id=project_id,
                    conflict_type="task_dependency",
                    title="Old inactive conflict",
                    summary="This should not be dismissed by a GET route.",
                    involved_agent_ids_json=[worker_one.id],
                    involved_task_ids_json=[task_one.id],
                    affected_paths_json=["docs/README.md"],
                    severity="medium",
                    status="detected",
                    suggested_resolution_json=["ask_user"],
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    added = client.post(
        f"/api/projects/{project_id}/widgets/add",
        json={"widget_type": "Conflict Resolver"},
        headers=bridge_headers,
    )
    assert added.status_code == 200, added.text

    db = SessionLocal()
    try:
        baseline = {
            "conflicts": db.scalar(select(func.count(ConflictRecord.id)).where(ConflictRecord.project_id == project_id)),
            "messages": db.scalar(select(func.count(ManagerMessage.id)).where(ManagerMessage.project_id == project_id)),
            "timeline": db.scalar(select(func.count(ProjectTimelineEvent.id)).where(ProjectTimelineEvent.project_id == project_id)),
            "events": db.scalar(select(func.count(ProjectEvent.id)).where(ProjectEvent.project_id == project_id)),
            "app_events": db.scalar(select(func.count(AppEvent.id))),
        }
        assert baseline["conflicts"] == 1
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/widgets/summary", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    conflict_widget = next(item for item in payload["data"] if item["widget_type"] == "Conflict Resolver")
    assert conflict_widget["status"] == "warning"
    titles = [item["title"] for item in conflict_widget["data_json"]["items"]]
    assert "Old inactive conflict" in titles
    assert any(title.startswith("Parallel edit pressure on apps/server/src/main.py") for title in titles)

    db = SessionLocal()
    try:
        after = {
            "conflicts": db.scalar(select(func.count(ConflictRecord.id)).where(ConflictRecord.project_id == project_id)),
            "messages": db.scalar(select(func.count(ManagerMessage.id)).where(ManagerMessage.project_id == project_id)),
            "timeline": db.scalar(select(func.count(ProjectTimelineEvent.id)).where(ProjectTimelineEvent.project_id == project_id)),
            "events": db.scalar(select(func.count(ProjectEvent.id)).where(ProjectEvent.project_id == project_id)),
            "app_events": db.scalar(select(func.count(AppEvent.id))),
        }
        assert after == baseline

        stale_conflict = db.scalar(
            select(ConflictRecord)
            .where(ConflictRecord.project_id == project_id, ConflictRecord.title == "Old inactive conflict")
            .order_by(ConflictRecord.id.desc())
        )
        assert stale_conflict is not None
        assert stale_conflict.status == "detected"
        assert stale_conflict.resolved_at is None
    finally:
        db.close()

    added = client.post(
        f"/api/projects/{project_id}/widgets/add",
        json={"widget_type": "What Changed Timeline"},
        headers=bridge_headers,
    )
    assert added.status_code == 200, added.text

    db = SessionLocal()
    try:
        baseline = {
            "assumptions": db.scalar(select(func.count(ManagerAssumption.id)).where(ManagerAssumption.project_id == project_id)),
            "traces": db.scalar(select(func.count(AgentExecutionTrace.id)).where(AgentExecutionTrace.project_id == project_id)),
            "load": db.scalar(select(func.count(AgentLoadSnapshot.id)).where(AgentLoadSnapshot.project_id == project_id)),
            "stuck": db.scalar(select(func.count(AgentStuckSignal.id)).where(AgentStuckSignal.project_id == project_id)),
            "recovery": db.scalar(select(func.count(RecoveryPlan.id)).where(RecoveryPlan.project_id == project_id)),
            "repo": db.scalar(select(func.count(RepoIntelligenceSummary.project_id)).where(RepoIntelligenceSummary.project_id == project_id)),
        }
        assert baseline == {
            "assumptions": 0,
            "traces": 0,
            "load": 0,
            "stuck": 0,
            "recovery": 0,
            "repo": 0,
        }
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/widgets/summary", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope"] == "project"
    assert any(item["widget_type"] == "What Changed Timeline" for item in payload["instances"])
    timeline_entry = next(item for item in payload["data"] if item["widget_type"] == "What Changed Timeline")
    assert timeline_entry["status"] in {"ready", "empty"}

    db = SessionLocal()
    try:
        after = {
            "assumptions": db.scalar(select(func.count(ManagerAssumption.id)).where(ManagerAssumption.project_id == project_id)),
            "traces": db.scalar(select(func.count(AgentExecutionTrace.id)).where(AgentExecutionTrace.project_id == project_id)),
            "load": db.scalar(select(func.count(AgentLoadSnapshot.id)).where(AgentLoadSnapshot.project_id == project_id)),
            "stuck": db.scalar(select(func.count(AgentStuckSignal.id)).where(AgentStuckSignal.project_id == project_id)),
            "recovery": db.scalar(select(func.count(RecoveryPlan.id)).where(RecoveryPlan.project_id == project_id)),
            "repo": db.scalar(select(func.count(RepoIntelligenceSummary.project_id)).where(RepoIntelligenceSummary.project_id == project_id)),
        }
        assert after == baseline
    finally:
        db.close()


def test_project_widget_data_route_stays_read_only_for_preview_widgets(client, bridge_headers) -> None:
    workspace_root = Path(sample_workspace("widget-read-only-preview"))
    (workspace_root / "src").mkdir(parents=True, exist_ok=True)
    (workspace_root / "tests").mkdir(parents=True, exist_ok=True)
    (workspace_root / "package.json").write_text(
        '{"dependencies":{"react":"^19.0.0","vite":"^6.0.0"},"scripts":{"build":"vite build","test":"vitest run"}}',
        encoding="utf-8",
    )
    (workspace_root / "package-lock.json").write_text("{}", encoding="utf-8")
    (workspace_root / "src" / "main.tsx").write_text("export const main = true;\n", encoding="utf-8")
    (workspace_root / "README.md").write_text("# Widget Preview\n", encoding="utf-8")

    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Widget Preview Project",
            idea="Exercise read-only project widgets",
            workspace_path=workspace_root.as_posix(),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        db.add(
            ProjectUnderstanding(
                project_id=project.id,
                summary="Manager assumptions exist only in understanding, not as rows.",
                known_facts_json={},
                unknowns_json={},
                assumptions_json=["Need Python 3.10"],
                constraints_json=[],
                confidence_by_category_json={},
            )
        )
        db.add(Agent(project_id=project.id, name="Manager AI", role="Project orchestration", kind="manager", status="idle", workspace_path=project.workspace_path))
        worker = Agent(
            project_id=project.id,
            name="Preview Worker",
            role="Implementation",
            kind="worker",
            status="blocked",
            workspace_path=project.workspace_path,
            current_action="Waiting for a missing fix.",
            failure_count=3,
        )
        db.add(worker)
        db.flush()
        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Fix the preview lane",
            goal="Unblock the worker",
            scope="Read-only preview test scope.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["vitest run"],
            success_criteria_json=["Worker unblocked"],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            waiting_reason="Needs a real fix.",
            priority=10,
        )
        db.add(task)
        db.flush()
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=task.id,
                runner_type="dry_run",
                process_ref="preview-run",
                status="done",
                report_json={
                    "summary": "Recorded a blocked implementation pass.",
                    "tests_run": ["vitest run"],
                    "files_changed": ["src/main.tsx"],
                },
            )
        )
        db.commit()
        project_id = project.id
    finally:
        db.close()

    widget_types = [
        "Manager Assumptions",
        "Agent Black Box",
        "Agent Load Balancer",
        "Failure Recovery",
        "Agent Stuck Detection",
        "Repo Intelligence",
        "Confidence Tracker",
        "Merge / Review Gates",
        "Model Assignment Policy",
        "Tool Routing Policy",
        "Sandbox Profiles",
        "Validation Recipe",
        "Swarm Budget",
        "Agent Contracts",
        "Path Ownership Map",
        "Decision Ledger",
    ]
    instance_ids: list[int] = []
    for widget_type in widget_types:
        added = client.post(
            f"/api/projects/{project_id}/widgets/add",
            json={"widget_type": widget_type},
            headers=bridge_headers,
        )
        assert added.status_code == 200, added.text
        instance_ids.append(added.json()["id"])

    for instance_id in instance_ids:
        response = client.get(
            f"/api/widgets/instances/{instance_id}/data",
            params={"project_id": project_id},
            headers=bridge_headers,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] in {"ready", "warning", "empty"}

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ManagerAssumption.id)).where(ManagerAssumption.project_id == project_id)) == 0
        assert db.scalar(select(func.count(AgentExecutionTrace.id)).where(AgentExecutionTrace.project_id == project_id)) == 0
        assert db.scalar(select(func.count(AgentLoadSnapshot.id)).where(AgentLoadSnapshot.project_id == project_id)) == 0
        assert db.scalar(select(func.count(AgentStuckSignal.id)).where(AgentStuckSignal.project_id == project_id)) == 0
        assert db.scalar(select(func.count(RecoveryPlan.id)).where(RecoveryPlan.project_id == project_id)) == 0
        assert db.scalar(select(func.count(RepoIntelligenceSummary.project_id)).where(RepoIntelligenceSummary.project_id == project_id)) == 0
        assert db.scalar(select(func.count(ProjectConfidence.id)).where(ProjectConfidence.project_id == project_id)) == 0
        assert db.scalar(select(func.count(ReviewGate.id)).where(ReviewGate.project_id == project_id)) == 0
        assert db.scalar(select(func.count(ModelPolicy.id)).where(ModelPolicy.project_id == project_id)) == 0
        assert db.scalar(select(func.count(ToolRoutingPolicy.id)).where(ToolRoutingPolicy.project_id == project_id)) == 0
        assert db.scalar(select(func.count(SandboxProfile.id)).where(SandboxProfile.project_id.is_(None))) == 0
        assert db.scalar(select(func.count(ValidationRecipe.id)).where(ValidationRecipe.project_id == project_id)) == 0
        assert db.scalar(select(func.count(SwarmBudget.project_id)).where(SwarmBudget.project_id == project_id)) == 0
        assert db.scalar(select(func.count(SwarmPreferences.id)).where(SwarmPreferences.project_id == project_id)) == 0
        assert db.scalar(select(func.count(AgentContract.id)).where(AgentContract.project_id == project_id)) == 0
        assert db.scalar(select(func.count(PathLock.id)).where(PathLock.project_id == project_id)) == 0
        assert db.scalar(select(func.count(DecisionRecord.id)).where(DecisionRecord.project_id == project_id)) == 0
        assert db.scalar(select(func.count(AgentArchetype.id))) == 0
        assert db.scalar(select(func.count(AppProfile.id))) == 0
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/recovery-plans", headers=bridge_headers)
    assert response.status_code == 200, response.text
    assert response.json() == []

    preview = client.get(f"/api/projects/{project_id}/recovery-plans/preview", headers=bridge_headers)
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["project_id"] == project_id
    assert payload["stored_count"] == 0
    assert payload["blocked_task_count"] == 1
    assert payload["stuck_signal_count"] == 1
    assert payload["persisted"] == []
    assert payload["derived_candidate_count"] >= 2
    assert {item["trigger_type"] for item in payload["derived_candidates"]} >= {"blocker", "blocked_task", "stuck_agents"}

    db = SessionLocal()
    try:
        recovery_plan_count = db.scalar(select(func.count(RecoveryPlan.id)).where(RecoveryPlan.project_id == project_id))
        stuck_signal_count = db.scalar(select(func.count(AgentStuckSignal.id)).where(AgentStuckSignal.project_id == project_id))
        assumption_count = db.scalar(select(func.count(ManagerAssumption.id)).where(ManagerAssumption.project_id == project_id))
        repo_summary_count = db.scalar(select(func.count(RepoIntelligenceSummary.project_id)).where(RepoIntelligenceSummary.project_id == project_id))
        trace_count = db.scalar(select(func.count(AgentExecutionTrace.id)).where(AgentExecutionTrace.project_id == project_id))
        load_snapshot_count = db.scalar(select(func.count(AgentLoadSnapshot.id)).where(AgentLoadSnapshot.project_id == project_id))
        assert recovery_plan_count == 0
        assert stuck_signal_count == 0
        assert assumption_count == 0
        assert repo_summary_count == 0
        assert trace_count == 0
        assert load_snapshot_count == 0
    finally:
        db.close()


def test_project_widget_summary_keeps_validation_and_handoff_support_read_only(client, bridge_headers) -> None:
    project = _create_project(client, "Widget Summary Support Read Safety", "widget-summary-support-read-safety")
    project_id = project["id"]

    for widget_type in ["Validation Recipe", "Handoff Quality"]:
        added = client.post(
            f"/api/projects/{project_id}/widgets/add",
            json={"widget_type": widget_type},
            headers=bridge_headers,
        )
        assert added.status_code == 200, added.text

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ValidationRecipe.id)).where(ValidationRecipe.project_id == project_id)) == 0
        assert db.scalar(
            select(func.count(HandoffQualityPreference.project_id)).where(HandoffQualityPreference.project_id == project_id)
        ) == 0
    finally:
        db.close()

    response = client.get(f"/api/projects/{project_id}/widgets/summary", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert {item["widget_type"] for item in payload["data"]} >= {"Validation Recipe", "Handoff Quality"}

    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ValidationRecipe.id)).where(ValidationRecipe.project_id == project_id)) == 0
        assert db.scalar(
            select(func.count(HandoffQualityPreference.project_id)).where(HandoffQualityPreference.project_id == project_id)
        ) == 0
    finally:
        db.close()
