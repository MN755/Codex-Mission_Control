from __future__ import annotations

import pytest

from conftest import sample_workspace
from db import SessionLocal, init_db
from intelligence.reputation import reputation_service
from manager import service
from models import Agent, ChangeRequest, EvidenceBasedHandoff, HandoffEvidence, Project, ProjectSnapshot, ProjectTimelineEvent, RecoveryPlan, ReviewGate, Task
from risk.service import risk_service


def _seed_project_pair() -> tuple[int, int, int, int, int, int]:
    init_db()
    db = SessionLocal()
    try:
        project_one = Project(
            name="Reference Validation One",
            idea="Keep manager references scoped.",
            workspace_path=sample_workspace("reference-validation-one"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        project_two = Project(
            name="Reference Validation Two",
            idea="Provide foreign refs for validation.",
            workspace_path=sample_workspace("reference-validation-two"),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add_all([project_one, project_two])
        db.flush()

        agent_one = Agent(
            project_id=project_one.id,
            name="Worker One",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project_one.workspace_path,
        )
        agent_two = Agent(
            project_id=project_two.id,
            name="Worker Two",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project_two.workspace_path,
        )
        db.add_all([agent_one, agent_two])
        db.flush()

        task_one = Task(
            project_id=project_one.id,
            assigned_agent_id=agent_one.id,
            title="Scoped task",
            goal="Stay inside the project boundary.",
            scope="Narrow validation task.",
            agent_role="Implementation",
            milestone="Validation",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Stay scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        task_two = Task(
            project_id=project_two.id,
            assigned_agent_id=agent_two.id,
            title="Foreign task",
            goal="Provide an invalid foreign reference.",
            scope="Cross-project validation fixture.",
            agent_role="Implementation",
            milestone="Validation",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Stay scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add_all([task_one, task_two])
        db.commit()
        return project_one.id, project_two.id, agent_one.id, agent_two.id, task_one.id, task_two.id
    finally:
        db.close()


def test_record_manager_message_rejects_foreign_agent_and_missing_task() -> None:
    project_one_id, _, _, foreign_agent_id, _, _ = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None
        with pytest.raises(ValueError, match="related agent"):
            service._record_manager_message(
                db,
                scoped_project,
                role="manager",
                message_type="blocker_report",
                content_markdown="Nope.",
                related_agent_id=foreign_agent_id,
            )
        with pytest.raises(ValueError, match="related task"):
            service._record_manager_message(
                db,
                scoped_project,
                role="manager",
                message_type="blocker_report",
                content_markdown="Still nope.",
                related_task_id=999_999,
            )
    finally:
        db.close()


def test_create_question_rejects_foreign_agent_and_missing_task() -> None:
    project_one_id, _, _, foreign_agent_id, _, _ = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None
        with pytest.raises(ValueError, match="related agent"):
            service._create_question(
                db,
                scoped_project,
                question="Should this accept nonsense?",
                options_json=[{"id": "yes", "label": "Yes"}],
                impact="medium",
                related_agent_id=foreign_agent_id,
            )
        with pytest.raises(ValueError, match="related task"):
            service._create_question(
                db,
                scoped_project,
                question="Should this accept fake tasks?",
                options_json=[{"id": "yes", "label": "Yes"}],
                impact="medium",
                related_task_id=999_999,
            )
    finally:
        db.close()


def test_create_risk_rejects_foreign_and_missing_related_refs() -> None:
    project_one_id, _, _, foreign_agent_id, _, foreign_task_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None

        with pytest.raises(ValueError, match="Risk owner agent"):
            risk_service.create_risk(
                db,
                scoped_project,
                {
                    "title": "Foreign owner",
                    "description": "Reject cross-project owner refs.",
                    "owner_agent_id": foreign_agent_id,
                },
            )
        with pytest.raises(ValueError, match="Risk related task"):
            risk_service.create_risk(
                db,
                scoped_project,
                {
                    "title": "Foreign task",
                    "description": "Reject cross-project task refs.",
                    "related_task_id": foreign_task_id,
                },
            )
        with pytest.raises(ValueError, match="Risk owner agent"):
            risk_service.create_risk(
                db,
                scoped_project,
                {
                    "title": "Missing owner",
                    "description": "Reject fake owner refs.",
                    "owner_agent_id": 999_999,
                },
            )
        with pytest.raises(ValueError, match="Risk related task"):
            risk_service.create_risk(
                db,
                scoped_project,
                {
                    "title": "Missing task",
                    "description": "Reject fake task refs.",
                    "related_task_id": 999_999,
                },
            )
    finally:
        db.close()


def test_create_approval_rejects_foreign_agent_and_missing_task() -> None:
    project_one_id, _, _, foreign_agent_id, _, _ = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None
        with pytest.raises(ValueError, match="requesting agent"):
            service._create_approval(
                db,
                scoped_project,
                request_type="command",
                title="Bad agent ref",
                reason_short="Reject cross-project agents.",
                risk_level="medium",
                cwd=scoped_project.workspace_path,
                request_payload_json={"command": "echo nope"},
                requesting_agent_id=foreign_agent_id,
            )
        with pytest.raises(ValueError, match="related task"):
            service._create_approval(
                db,
                scoped_project,
                request_type="command",
                title="Bad task ref",
                reason_short="Reject fake tasks.",
                risk_level="medium",
                cwd=scoped_project.workspace_path,
                request_payload_json={"command": "echo nope"},
                task_id=999_999,
            )
    finally:
        db.close()


def test_record_decision_rejects_foreign_agent_and_missing_task() -> None:
    project_one_id, _, _, foreign_agent_id, _, _ = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None
        with pytest.raises(ValueError, match="related agent"):
            service._record_decision(
                db,
                scoped_project,
                decision_type="manager",
                title="Bad agent ref",
                decision="Do not trust foreign references.",
                reason="Cross-project refs are garbage.",
                made_by="manager",
                related_agent_id=foreign_agent_id,
            )
        with pytest.raises(ValueError, match="related task"):
            service._record_decision(
                db,
                scoped_project,
                decision_type="manager",
                title="Bad task ref",
                decision="Do not trust fake tasks.",
                reason="Missing refs should fail loudly.",
                made_by="manager",
                related_task_id=999_999,
            )
    finally:
        db.close()


def test_review_gate_create_rejects_foreign_refs_and_missing_evidence() -> None:
    project_one_id, project_two_id, _, foreign_agent_id, _, foreign_task_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        foreign_project = db.get(Project, project_two_id)
        assert scoped_project is not None
        assert foreign_project is not None
        foreign_evidence = HandoffEvidence(
            project_id=foreign_project.id,
            evidence_type="test_result",
            claim="Foreign evidence",
            summary="Should not be accepted across projects.",
            status="verified",
        )
        db.add(foreign_evidence)
        db.flush()

        base_payload = {
            "gate_type": "code_review",
            "title": "Scoped gate",
            "status": "pending",
            "required": True,
            "required_checks_json": ["pytest -q"],
            "evidence_ids_json": [],
        }

        with pytest.raises(ValueError, match="Review gate related task"):
            service.create_review_gate(db, scoped_project, {**base_payload, "related_task_id": foreign_task_id})
        with pytest.raises(ValueError, match="Review gate related agent"):
            service.create_review_gate(db, scoped_project, {**base_payload, "related_agent_id": foreign_agent_id})
        with pytest.raises(ValueError, match="Review gate evidence"):
            service.create_review_gate(db, scoped_project, {**base_payload, "evidence_ids_json": [foreign_evidence.id, 999_999]})
    finally:
        db.close()


def test_review_gate_update_rejects_foreign_refs_and_missing_evidence() -> None:
    project_one_id, project_two_id, agent_one_id, foreign_agent_id, task_one_id, foreign_task_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        foreign_project = db.get(Project, project_two_id)
        assert scoped_project is not None
        assert foreign_project is not None
        scoped_evidence = HandoffEvidence(
            project_id=scoped_project.id,
            evidence_type="report",
            claim="Scoped evidence",
            summary="Valid evidence for the project.",
            status="verified",
        )
        foreign_evidence = HandoffEvidence(
            project_id=foreign_project.id,
            evidence_type="report",
            claim="Foreign evidence",
            summary="Should stay out of this review gate.",
            status="verified",
        )
        gate = ReviewGate(
            project_id=scoped_project.id,
            gate_type="code_review",
            title="Existing gate",
            status="pending",
            required=True,
            related_task_id=task_one_id,
            related_agent_id=agent_one_id,
            evidence_ids_json=[],
        )
        db.add_all([scoped_evidence, foreign_evidence, gate])
        db.flush()

        with pytest.raises(ValueError, match="Review gate related task"):
            service.update_review_gate(db, gate.id, {"related_task_id": foreign_task_id})
        with pytest.raises(ValueError, match="Review gate related agent"):
            service.update_review_gate(db, gate.id, {"related_agent_id": foreign_agent_id})
        with pytest.raises(ValueError, match="Review gate evidence"):
            service.update_review_gate(db, gate.id, {"evidence_ids_json": [scoped_evidence.id, foreign_evidence.id, 999_999]})
    finally:
        db.close()


def test_create_recovery_plan_rejects_foreign_and_missing_related_refs_before_persisting() -> None:
    project_one_id, _, _, foreign_agent_id, _, foreign_task_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None

        with pytest.raises(ValueError, match="Recovery plan related agent"):
            service.create_recovery_plan(
                db,
                scoped_project,
                {
                    "trigger_type": "agent_stuck",
                    "trigger_summary": "Foreign agent should be rejected.",
                    "related_agent_id": foreign_agent_id,
                    "suggested_actions_json": ["ask_user"],
                },
            )
        with pytest.raises(ValueError, match="Recovery plan related task"):
            service.create_recovery_plan(
                db,
                scoped_project,
                {
                    "trigger_type": "task_blocked",
                    "trigger_summary": "Foreign task should be rejected.",
                    "related_task_id": foreign_task_id,
                    "suggested_actions_json": ["ask_user"],
                },
            )
        with pytest.raises(ValueError, match="Recovery plan related agent"):
            service.create_recovery_plan(
                db,
                scoped_project,
                {
                    "trigger_type": "agent_stuck",
                    "trigger_summary": "Missing agent should be rejected.",
                    "related_agent_id": 999_999,
                    "suggested_actions_json": ["ask_user"],
                },
            )
        with pytest.raises(ValueError, match="Recovery plan related task"):
            service.create_recovery_plan(
                db,
                scoped_project,
                {
                    "trigger_type": "task_blocked",
                    "trigger_summary": "Missing task should be rejected.",
                    "related_task_id": 999_999,
                    "suggested_actions_json": ["ask_user"],
                },
            )
        assert db.query(RecoveryPlan).filter(RecoveryPlan.project_id == scoped_project.id).count() == 0
    finally:
        db.close()


def test_create_project_snapshot_rejects_foreign_and_missing_related_refs() -> None:
    project_one_id, _, _, foreign_agent_id, _, foreign_task_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None

        with pytest.raises(ValueError, match="Snapshot task"):
            service.create_project_snapshot(
                db,
                scoped_project,
                label="Foreign task snapshot",
                description="Should reject foreign tasks.",
                created_before_task_id=foreign_task_id,
            )
        with pytest.raises(ValueError, match="Snapshot agent"):
            service.create_project_snapshot(
                db,
                scoped_project,
                label="Foreign agent snapshot",
                description="Should reject foreign agents.",
                created_before_agent_id=foreign_agent_id,
            )
        with pytest.raises(ValueError, match="Snapshot task"):
            service.create_project_snapshot(
                db,
                scoped_project,
                label="Missing task snapshot",
                description="Should reject missing tasks.",
                created_before_task_id=999_999,
            )
        with pytest.raises(ValueError, match="Snapshot agent"):
            service.create_project_snapshot(
                db,
                scoped_project,
                label="Missing agent snapshot",
                description="Should reject missing agents.",
                created_before_agent_id=999_999,
            )
        assert db.query(ProjectSnapshot).filter(ProjectSnapshot.project_id == scoped_project.id).count() == 0
    finally:
        db.close()


def test_create_timeline_event_rejects_foreign_and_missing_related_refs() -> None:
    project_one_id, project_two_id, agent_one_id, foreign_agent_id, task_one_id, foreign_task_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        foreign_project = db.get(Project, project_two_id)
        assert scoped_project is not None
        assert foreign_project is not None
        scoped_handoff = EvidenceBasedHandoff(
            project_id=scoped_project.id,
            title="Scoped handoff",
            summary="Valid handoff",
            what_was_built="- feature",
            how_to_run="- run",
            how_to_use="- use",
            tests_run_json=[],
            known_limitations_json=[],
            suggested_next_steps_json=[],
            evidence_ids_json=[],
            confidence_level="medium",
            dry_run=True,
        )
        foreign_handoff = EvidenceBasedHandoff(
            project_id=foreign_project.id,
            title="Foreign handoff",
            summary="Invalid handoff",
            what_was_built="- foreign",
            how_to_run="- run",
            how_to_use="- use",
            tests_run_json=[],
            known_limitations_json=[],
            suggested_next_steps_json=[],
            evidence_ids_json=[],
            confidence_level="medium",
            dry_run=True,
        )
        db.add_all([scoped_handoff, foreign_handoff])
        db.flush()

        valid = service.create_timeline_event(
            db,
            scoped_project,
            {
                "event_type": "status_update",
                "title": "Valid event",
                "summary": "This one is scoped correctly.",
                "related_agent_id": agent_one_id,
                "related_task_id": task_one_id,
                "related_handoff_id": scoped_handoff.id,
            },
        )
        assert valid.project_id == scoped_project.id

        with pytest.raises(ValueError, match="Timeline event related agent"):
            service.create_timeline_event(
                db,
                scoped_project,
                {"event_type": "status_update", "title": "Bad agent", "summary": "Nope", "related_agent_id": foreign_agent_id},
            )
        with pytest.raises(ValueError, match="Timeline event related task"):
            service.create_timeline_event(
                db,
                scoped_project,
                {"event_type": "status_update", "title": "Bad task", "summary": "Nope", "related_task_id": foreign_task_id},
            )
        with pytest.raises(ValueError, match="Timeline event related handoff"):
            service.create_timeline_event(
                db,
                scoped_project,
                {"event_type": "status_update", "title": "Bad handoff", "summary": "Nope", "related_handoff_id": foreign_handoff.id},
            )
        with pytest.raises(ValueError, match="Timeline event related agent"):
            service.create_timeline_event(
                db,
                scoped_project,
                {"event_type": "status_update", "title": "Missing agent", "summary": "Nope", "related_agent_id": 999_999},
            )
        with pytest.raises(ValueError, match="Timeline event related task"):
            service.create_timeline_event(
                db,
                scoped_project,
                {"event_type": "status_update", "title": "Missing task", "summary": "Nope", "related_task_id": 999_999},
            )
        with pytest.raises(ValueError, match="Timeline event related handoff"):
            service.create_timeline_event(
                db,
                scoped_project,
                {"event_type": "status_update", "title": "Missing handoff", "summary": "Nope", "related_handoff_id": 999_999},
            )
        assert db.query(ProjectTimelineEvent).filter(ProjectTimelineEvent.project_id == scoped_project.id).count() == 1
    finally:
        db.close()


def test_select_recovery_action_rejects_unrecognized_or_unproposed_values() -> None:
    project_one_id, _, agent_one_id, _, task_one_id, _ = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        assert scoped_project is not None
        plan = RecoveryPlan(
            project_id=scoped_project.id,
            trigger_type="blocked_task",
            trigger_summary="Blocked task needs intervention.",
            related_agent_id=agent_one_id,
            related_task_id=task_one_id,
            suggested_actions_json=["pause_project", "Ask user / ask Manager"],
            status="proposed",
        )
        db.add(plan)
        db.flush()

        accepted = service.select_recovery_action(db, plan.id, "Ask user / ask Manager")
        assert accepted.selected_action == "ask_user"
        assert accepted.status == "accepted"

        plan_two = RecoveryPlan(
            project_id=scoped_project.id,
            trigger_type="blocked_task",
            trigger_summary="Second plan for failure cases.",
            related_agent_id=agent_one_id,
            related_task_id=task_one_id,
            suggested_actions_json=["pause_project"],
            status="proposed",
        )
        db.add(plan_two)
        db.flush()

        with pytest.raises(ValueError, match="not recognized"):
            service.select_recovery_action(db, plan_two.id, "launch_the_nukes")
        with pytest.raises(ValueError, match="not proposed"):
            service.select_recovery_action(db, plan_two.id, "ask_user")
    finally:
        db.close()


def test_update_change_request_rejects_foreign_and_missing_related_refs() -> None:
    project_one_id, project_two_id, _, _, task_one_id, foreign_task_id = _seed_project_pair()

    db = SessionLocal()
    try:
        scoped_project = db.get(Project, project_one_id)
        foreign_project = db.get(Project, project_two_id)
        assert scoped_project is not None
        assert foreign_project is not None
        scoped_handoff = EvidenceBasedHandoff(
            project_id=scoped_project.id,
            title="Scoped handoff",
            summary="Valid handoff",
            what_was_built="- feature",
            how_to_run="- run",
            how_to_use="- use",
            tests_run_json=[],
            known_limitations_json=[],
            suggested_next_steps_json=[],
            evidence_ids_json=[],
            confidence_level="medium",
            dry_run=True,
        )
        foreign_handoff = EvidenceBasedHandoff(
            project_id=foreign_project.id,
            title="Foreign handoff",
            summary="Invalid handoff",
            what_was_built="- foreign",
            how_to_run="- run",
            how_to_use="- use",
            tests_run_json=[],
            known_limitations_json=[],
            suggested_next_steps_json=[],
            evidence_ids_json=[],
            confidence_level="medium",
            dry_run=True,
        )
        request = ChangeRequest(
            project_id=scoped_project.id,
            request_text="Tighten the workflow.",
            classification="needs_triage",
            impact_estimate="unknown",
            status="new",
            related_tasks_json=[],
            related_handoff_id=None,
        )
        db.add_all([scoped_handoff, foreign_handoff, request])
        db.flush()

        updated = service.update_change_request(
            db,
            request.id,
            {"related_tasks_json": [task_one_id], "related_handoff_id": scoped_handoff.id, "status": "triaged"},
        )
        assert updated.related_tasks_json == [task_one_id]
        assert updated.related_handoff_id == scoped_handoff.id

        with pytest.raises(ValueError, match="Change request related task"):
            service.update_change_request(db, request.id, {"related_tasks_json": [foreign_task_id]})
        with pytest.raises(ValueError, match="Change request related handoff"):
            service.update_change_request(db, request.id, {"related_handoff_id": foreign_handoff.id})
        with pytest.raises(ValueError, match="Change request related task"):
            service.update_change_request(db, request.id, {"related_tasks_json": [999_999]})
        with pytest.raises(ValueError, match="Change request related handoff"):
            service.update_change_request(db, request.id, {"related_handoff_id": 999_999})
    finally:
        db.close()


def test_record_agent_performance_rejects_nonexistent_or_mismatched_refs() -> None:
    project_one_id, _, _, _, task_one_id, foreign_task_id = _seed_project_pair()

    db = SessionLocal()
    try:
        recorded = reputation_service.record(
            db,
            {
                "project_id": project_one_id,
                "agent_archetype": "generalist",
                "task_category": "validation",
                "task_id": task_one_id,
                "outcome": "success",
            },
        )
        assert recorded.project_id == project_one_id
        assert recorded.task_id == task_one_id

        with pytest.raises(ValueError, match="Project not found"):
            reputation_service.record(
                db,
                {
                    "project_id": 999_999,
                    "agent_archetype": "generalist",
                    "task_category": "validation",
                },
            )
        with pytest.raises(ValueError, match="Task not found$"):
            reputation_service.record(
                db,
                {
                    "project_id": project_one_id,
                    "agent_archetype": "generalist",
                    "task_category": "validation",
                    "task_id": 999_999,
                },
            )
        with pytest.raises(ValueError, match="require a project_id"):
            reputation_service.record(
                db,
                {
                    "agent_archetype": "generalist",
                    "task_category": "validation",
                    "task_id": task_one_id,
                },
            )
        with pytest.raises(ValueError, match="Task not found in this project"):
            reputation_service.record(
                db,
                {
                    "project_id": project_one_id,
                    "agent_archetype": "generalist",
                    "task_category": "validation",
                    "task_id": foreign_task_id,
                },
            )
    finally:
        db.close()
