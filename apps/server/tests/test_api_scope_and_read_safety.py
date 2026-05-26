from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from conftest import sample_workspace
from db import SessionLocal, init_db
from models import (
    Agent,
    AgentArchetype,
    AgentContract,
    AgentExecutionTrace,
    AgentLoadSnapshot,
    AgentRun,
    AgentStuckSignal,
    AppProfile,
    ConflictRecord,
    DecisionRecord,
    HandoffEvidence,
    ImportedCodebaseSafety,
    ManagerMessage,
    ManagerAssumption,
    ModelPolicy,
    PathReservation,
    PathLock,
    Project,
    ProjectConfidence,
    ProjectEvent,
    ProjectPlaybook,
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


def test_agent_archetypes_get_does_not_seed_rows(client) -> None:
    init_db()
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(AgentArchetype.id))) == 0
    finally:
        db.close()


def test_parallelism_safety_widget_data_stays_read_only(client, bridge_headers) -> None:
    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Parallelism Widget Read Safety",
            idea="Keep conflict previews transient.",
            workspace_path=sample_workspace("parallelism-widget-read-safety"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        agents = [
            Agent(project_id=project.id, name="Agent A", role="Builder", kind="worker", status="working", workspace_path=project.workspace_path),
            Agent(project_id=project.id, name="Agent B", role="Builder", kind="worker", status="working", workspace_path=project.workspace_path),
        ]
        db.add_all(agents)
        db.flush()
        tasks = [
            Task(project_id=project.id, title="Task A", goal="Edit the shared file.", scope="Task A scope.", status="working", priority=10, allowed_paths_json=["src/conflict.py"]),
            Task(project_id=project.id, title="Task B", goal="Edit the shared file.", scope="Task B scope.", status="working", priority=20, allowed_paths_json=["src/conflict.py"]),
        ]
        db.add_all(tasks)
        db.flush()
        db.add_all(
            [
                PathReservation(project_id=project.id, agent_id=agents[0].id, task_id=tasks[0].id, path="src/conflict.py"),
                PathReservation(project_id=project.id, agent_id=agents[1].id, task_id=tasks[1].id, path="src/conflict.py"),
            ]
        )
        db.commit()
        project_id = project.id
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
        before = {
            "conflicts": db.scalar(select(func.count(ConflictRecord.id)).where(ConflictRecord.project_id == project_id)),
            "messages": db.scalar(select(func.count(ManagerMessage.id)).where(ManagerMessage.project_id == project_id)),
            "timeline": db.scalar(select(func.count(ProjectTimelineEvent.id)).where(ProjectTimelineEvent.project_id == project_id)),
            "events": db.scalar(select(func.count(ProjectEvent.id)).where(ProjectEvent.project_id == project_id)),
        }
    finally:
        db.close()

    response = client.get(f"/api/widgets/instances/{instance_id}/data", headers=bridge_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"

    db = SessionLocal()
    try:
        after = {
            "conflicts": db.scalar(select(func.count(ConflictRecord.id)).where(ConflictRecord.project_id == project_id)),
            "messages": db.scalar(select(func.count(ManagerMessage.id)).where(ManagerMessage.project_id == project_id)),
            "timeline": db.scalar(select(func.count(ProjectTimelineEvent.id)).where(ProjectTimelineEvent.project_id == project_id)),
            "events": db.scalar(select(func.count(ProjectEvent.id)).where(ProjectEvent.project_id == project_id)),
        }
        assert after == before
    finally:
        db.close()


def test_parallelism_safety_widget_data_does_not_dismiss_conflicts_on_read(client, bridge_headers) -> None:
    init_db()
    db = SessionLocal()
    try:
        project = Project(
            name="Parallelism Widget Conflict Scope",
            idea="Keep conflict rows stable until an explicit action changes them.",
            workspace_path=sample_workspace("parallelism-widget-conflict-scope"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()
        conflict = ConflictRecord(
            project_id=project.id,
            conflict_type="path_overlap",
            title="Parallel edit pressure on src/orphan.py",
            summary="Stale conflict record.",
            involved_agent_ids_json=[1, 2],
            involved_task_ids_json=[1, 2],
            affected_paths_json=["src/orphan.py"],
            severity="high",
            status="manager_review",
            suggested_resolution_json=["serialize_tasks"],
        )
        db.add(conflict)
        db.commit()
        project_id = project.id
        conflict_id = conflict.id
    finally:
        db.close()

    added = client.post(
        f"/api/projects/{project_id}/widgets/add",
        json={"widget_type": "Parallelism Safety Meter"},
        headers=bridge_headers,
    )
    assert added.status_code == 200, added.text
    instance_id = added.json()["id"]

    response = client.get(f"/api/widgets/instances/{instance_id}/data", headers=bridge_headers)
    assert response.status_code == 200, response.text

    db = SessionLocal()
    try:
        conflict = db.get(ConflictRecord, conflict_id)
        assert conflict is not None
        assert conflict.status == "manager_review"
        assert conflict.resolved_at is None
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

    wrong_status = client.get(
        f"/api/orchestrations/{orchestration_id}/status",
        headers=bridge_headers,
        params={"project_id": project_two["id"]},
    )
    assert wrong_status.status_code == 404

    opened = client.post(f"/api/projects/{project_one['id']}/open")
    assert opened.status_code == 200, opened.text
    question = client.get(f"/api/projects/{project_one['id']}/questions/pending").json()[0]
    wrong_auto_decide = client.post(
        f"/api/questions/{question['id']}/auto-decide",
        params={"project_id": project_two["id"]},
    )
    assert wrong_auto_decide.status_code == 404

    db = SessionLocal()
    try:
        stored = db.get(Project, project_one["id"])
        assert stored is not None
    finally:
        db.close()


def test_project_routes_reject_invalid_related_resource_ids(client) -> None:
    project = _create_project(client, "Reference Validation", "reference-validation")
    project_id = project["id"]

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
        response = client.get(f"/api/widgets/instances/{instance_id}/data", headers=bridge_headers)
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
