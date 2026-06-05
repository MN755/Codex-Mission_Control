from __future__ import annotations

from pathlib import Path

import pytest

from main import service
from db import SessionLocal
from models import (
    Agent,
    AgentRun,
    DecisionRecord,
    EvidenceBasedHandoff,
    HandoffEvidence,
    OrchestrationSession,
    PathLock,
    Project,
    ProjectTimelineEvent,
    ReviewGate,
    Task,
    ValidationCoverageArea,
    ValidationRecipe,
)

from conftest import sample_workspace


@pytest.fixture(autouse=True)
def _fast_operator_snapshot_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(service, "_workspace_degraded_notices_preview", lambda project: [])
    monkeypatch.setattr(
        service,
        "_derive_current_action_preview",
        lambda db, project, notices: {
            "type": "blocker",
            "title": "Restore validation evidence.",
            "message": "Validation evidence is still missing.",
        },
    )
    monkeypatch.setattr(
        service,
        "get_project_health_preview",
        lambda db, project: {
            "state": "warning",
            "top_risks": ["Validation evidence is incomplete."],
            "reasons": [],
            "next_action": "Restore validation evidence.",
        },
    )
    monkeypatch.setattr(service, "get_project_handoff_summary", lambda db, project: {"status": "not_ready"})
    monkeypatch.setattr(service, "recent_diagnostic_reports", lambda project: [])
    monkeypatch.setattr(service, "get_swarm_plan", lambda db, project: None)


def _seed_operator_project() -> int:
    workspace_root = Path(sample_workspace("operator-surfaces"))
    workspace_root.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        project = Project(
            name="Operator Surfaces Project",
            idea="Exercise ECC-inspired operator surfaces safely.",
            workspace_path=workspace_root.as_posix(),
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
            workspace_path=project.workspace_path,
        )
        worker = Agent(
            project_id=project.id,
            name="Blocked Worker",
            role="Implementation",
            kind="worker",
            status="blocked",
            current_action="Waiting on a backend validation fix.",
            workspace_path=project.workspace_path,
        )
        db.add_all([manager, worker])
        db.flush()

        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Fix backend validation",
            goal="Restore backend validation confidence.",
            scope="Keep the scope narrow and safe.",
            agent_role="Implementation",
            milestone="MVP",
            allowed_paths_json=["apps/server/src/main.py"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest apps/server/tests/test_operator_surfaces.py -q"],
            success_criteria_json=["Validation passes"],
            estimated_complexity="small",
            dependencies_json=[],
            status="blocked",
            priority=10,
        )
        db.add(task)
        db.flush()

        db.add(
            OrchestrationSession(
                project_id=project.id,
                workspace_path=project.workspace_path,
                source="codex_plugin",
                user_request="Produce a safe operator summary.",
                status="running",
                manager_status="Waiting on validation evidence.",
                mode="existing_codebase",
                metadata_json={},
            )
        )
        db.add(
            PathLock(
                project_id=project.id,
                path_pattern="apps/server/src/main.py",
                owner_agent_id=worker.id,
                owner_task_id=task.id,
                reason="Worker owns the backend contract path.",
                status="active",
            )
        )
        db.add(
            DecisionRecord(
                project_id=project.id,
                decision_type="validation_policy",
                title="Keep backend checks explicit",
                decision="Require a named pytest slice before handoff.",
                reason="The repo needs reproducible verification, not vibes.",
                made_by="manager",
                impact_area_json=["validation", "handoff"],
                related_task_id=task.id,
                related_agent_id=worker.id,
                reversible=True,
            )
        )
        db.add(
            ProjectTimelineEvent(
                project_id=project.id,
                event_type="blocker",
                title="Backend validation blocked",
                summary="Worker is blocked until the validation lane is explicit again.",
                related_agent_id=worker.id,
                related_task_id=task.id,
                severity="warning",
            )
        )
        db.add(
            ValidationRecipe(
                project_id=project.id,
                name="Backend validation recipe",
                status="active",
                steps_json=[
                    {"title": "Run operator surface tests", "command": "python -m pytest apps/server/tests/test_operator_surfaces.py -q"},
                    {"title": "Run MCP resource tests", "command": "python -m pytest apps/mcp-server/tests/test_mcp_server.py -q"},
                ],
            )
        )
        db.add(
            ValidationCoverageArea(
                project_id=project.id,
                area="operator_surfaces",
                coverage_status="none",
                evidence_summary="No recorded verification evidence yet.",
            )
        )
        db.add(
            AgentRun(
                agent_id=worker.id,
                task_id=task.id,
                runner_type="dry_run",
                process_ref="operator-trace",
                status="blocked",
                report_json={
                    "agent": worker.name,
                    "task_id": str(task.id),
                    "status": "blocked",
                    "summary": "Browser automation target is unavailable and the validation lane is blocked.",
                    "files_changed": [],
                    "tests_run": ["python -m pytest apps/server/tests/test_operator_surfaces.py -q"],
                    "blockers": ["Browser automation target is unavailable."],
                    "risks": ["Validation evidence is incomplete."],
                    "recommended_next_task": "Restore the target and retry validation.",
                },
                result_envelope_json={
                    "status": "blocked",
                    "runner_type": "dry_run",
                    "lane": "browser_automation",
                    "summary": "Browser automation target is unavailable and the validation lane is blocked.",
                    "report": {
                        "agent": worker.name,
                        "task_id": str(task.id),
                        "status": "blocked",
                        "summary": "Browser automation target is unavailable and the validation lane is blocked.",
                        "files_changed": [],
                        "tests_run": ["python -m pytest apps/server/tests/test_operator_surfaces.py -q"],
                        "blockers": ["Browser automation target is unavailable."],
                        "risks": ["Validation evidence is incomplete."],
                        "recommended_next_task": "Restore the target and retry validation.",
                    },
                    "files_changed": [],
                    "tests_run": ["python -m pytest apps/server/tests/test_operator_surfaces.py -q"],
                    "commands_attempted": ["python -m pytest apps/server/tests/test_operator_surfaces.py -q"],
                    "evidence": [],
                    "risks": ["Validation evidence is incomplete."],
                    "blockers": ["Browser automation target is unavailable."],
                    "diagnostics": ["Target host returned unavailable."],
                    "approvals_requested": [],
                    "recovery_plan": ["Restore the browser target and retry validation."],
                    "edits": [],
                    "failure_classification": "transient",
                    "needs_approval": False,
                    "metadata_json": {},
                },
                failure_classification="transient",
            )
        )
        db.add(
            ReviewGate(
                project_id=project.id,
                gate_type="validation",
                title="Backend verification gate",
                status="pending",
                required=True,
                related_task_id=task.id,
                related_agent_id=worker.id,
                required_checks_json=["python -m pytest apps/server/tests/test_operator_surfaces.py -q"],
                evidence_ids_json=[],
                result_summary="Still waiting on explicit evidence.",
            )
        )
        db.flush()

        handoff = EvidenceBasedHandoff(
            project_id=project.id,
            title="Operator surface handoff",
            summary="Core operator surfaces exist but still need final validation evidence.",
            what_was_built="Operator snapshot, instincts preview, and verification brief.",
            how_to_run="Use the new read-only project endpoints or MCP resources.",
            how_to_use="Read the snapshot first, then instincts, then verification brief.",
            tests_run_json=[],
            known_limitations_json=["Validation evidence has not been captured yet."],
            suggested_next_steps_json=["Run the explicit pytest slices and attach the evidence."],
            evidence_ids_json=[],
            confidence_level="medium",
            dry_run=False,
        )
        db.add(handoff)
        db.flush()

        evidence = HandoffEvidence(
            project_id=project.id,
            handoff_id=handoff.id,
            evidence_type="test_plan",
            claim="The operator surfaces are ready for verification.",
            summary="A named pytest lane is defined but not yet executed.",
            source_path="apps/server/tests/test_operator_surfaces.py",
            command="python -m pytest apps/server/tests/test_operator_surfaces.py -q",
            status="pending",
            metadata_json={},
        )
        db.add(evidence)
        db.flush()
        handoff.evidence_ids_json = [evidence.id]

        db.commit()
        return project.id
    finally:
        db.close()


def test_operator_snapshot_endpoint_returns_compact_project_state(client, bridge_headers) -> None:
    project_id = _seed_operator_project()

    response = client.get(f"/api/projects/{project_id}/operator-snapshot", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["project_name"] == "Operator Surfaces Project"
    assert payload["active_agent_count"] >= 1
    assert payload["pending_approvals_count"] >= 0
    assert payload["trace_spans"]
    assert payload["evidence_items"]
    expected_trace_outcome_counts = {}
    expected_trace_span_kind_counts = {}
    expected_trace_failure_classification_counts = {}
    for trace in payload["trace_spans"]:
        expected_trace_outcome_counts[trace["outcome"]] = expected_trace_outcome_counts.get(trace["outcome"], 0) + 1
        expected_trace_span_kind_counts[trace["span_kind"]] = expected_trace_span_kind_counts.get(trace["span_kind"], 0) + 1
        if trace["failure_classification"]:
            expected_trace_failure_classification_counts[trace["failure_classification"]] = (
                expected_trace_failure_classification_counts.get(trace["failure_classification"], 0) + 1
            )
    expected_evidence_status_counts = {}
    for entry in payload["evidence_items"]:
        expected_evidence_status_counts[entry["status"]] = expected_evidence_status_counts.get(entry["status"], 0) + 1
    assert payload["trace_span_count"] == len(payload["trace_spans"])
    assert payload["trace_outcome_counts"] == expected_trace_outcome_counts
    assert payload["trace_outcome_group_count"] == len(expected_trace_outcome_counts)
    assert payload["trace_span_kind_counts"] == expected_trace_span_kind_counts
    assert payload["trace_span_kind_group_count"] == len(expected_trace_span_kind_counts)
    assert payload["trace_failure_classifications"] == sorted(expected_trace_failure_classification_counts)
    assert payload["trace_failure_classification_counts"] == expected_trace_failure_classification_counts
    assert payload["trace_failure_classification_group_count"] == len(expected_trace_failure_classification_counts)
    assert payload["evidence_item_count"] == len(payload["evidence_items"])
    assert payload["evidence_status_counts"] == expected_evidence_status_counts
    assert payload["evidence_status_group_count"] == len(expected_evidence_status_counts)
    assert payload["current_focus_count"] == len(payload["current_focus"])
    assert payload["top_risk_count"] == len(payload["top_risks"])
    assert payload["recent_event_count"] == len(payload["recent_events"])
    assert "## Mission Control Operator Snapshot" in payload["snapshot_markdown"]
    assert any("browser_automation" in item or "Fix backend validation" in item for item in payload["current_focus"])
    assert payload["trace_outcome_counts"].get("blocked", 0) >= 1
    assert payload["trace_failure_classification_counts"].get("transient", 0) >= 1
    assert payload["evidence_status_counts"].get("pending", 0) >= 1


def test_instincts_preview_endpoint_derives_reusable_rules(client, bridge_headers) -> None:
    project_id = _seed_operator_project()

    response = client.get(f"/api/projects/{project_id}/instincts/preview", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["instinct_count"] >= 3
    assert payload["instinct_count"] == len(payload["instincts"])
    assert payload["instinct_keys"] == [item["key"] for item in payload["instincts"]]
    expected_confidence_counts = {}
    expected_tag_counts = {}
    expected_evidence_item_count = 0
    expected_evidenceful_instinct_count = 0
    for item in payload["instincts"]:
        expected_confidence_counts[item["confidence"]] = expected_confidence_counts.get(item["confidence"], 0) + 1
        if item["evidence"]:
            expected_evidenceful_instinct_count += 1
        expected_evidence_item_count += len(item["evidence"])
        for tag in set(item["tags"]):
            expected_tag_counts[tag] = expected_tag_counts.get(tag, 0) + 1
    assert payload["confidence_levels"] == sorted(expected_confidence_counts)
    assert payload["confidence_counts"] == expected_confidence_counts
    assert payload["confidence_group_count"] == len(expected_confidence_counts)
    assert payload["tags"] == sorted(expected_tag_counts)
    assert payload["tag_counts"] == expected_tag_counts
    assert payload["tag_group_count"] == len(expected_tag_counts)
    assert payload["evidence_item_count"] == expected_evidence_item_count
    assert payload["evidenceful_instinct_count"] == expected_evidenceful_instinct_count
    keys = {item["key"] for item in payload["instincts"]}
    assert "path-lock-before-parallel-edit" in keys
    assert "ship-with-evidence" in keys
    assert "turn-gaps-into-checks" in keys


def test_verification_brief_endpoint_exposes_checks_and_blockers(client, bridge_headers) -> None:
    project_id = _seed_operator_project()

    response = client.get(f"/api/projects/{project_id}/verification-brief", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["readiness"] == "blocked"
    assert payload["required_check_count"] == len(payload["required_checks"])
    assert payload["recommended_check_count"] == len(payload["recommended_checks"])
    assert payload["evidence_gap_count"] == len(payload["evidence_gaps"])
    assert payload["release_blocker_count"] == len(payload["release_blockers"])
    assert payload["handoff_warning_count"] == len(payload["handoff_warnings"])
    assert payload["loop_strategy_count"] == len(payload["loop_strategy"])
    assert any("python -m pytest apps/server/tests/test_operator_surfaces.py -q" in item for item in payload["required_checks"])
    assert payload["evidence_gaps"]
    assert payload["release_blockers"]
    assert "## Mission Control Verification Brief" in payload["brief_markdown"]


def test_verification_brief_endpoint_surfaces_notebook_config_and_artifact_followups(client, bridge_headers, monkeypatch) -> None:
    project_id = _seed_operator_project()

    original = service.build_workspace_tooling_status

    def patched(project):
        payload = original(project)
        payload["important_paths"] = ["train.py", "configs/train.yaml"]
        payload["execution_entrypoints"] = ["python train.py", "python export.py"]
        payload["runtime_blockers"] = ["Python is not available on PATH for the repo-owned TensorFlow commands this workspace expects to run."]
        payload["validation_evidence_targets"] = ["Capture TensorBoard evidence instead of motivational speeches."]
        payload["notebook_paths"] = ["notebooks/experiment.ipynb"]
        payload["notebook_commands"] = ["jupyter nbconvert --to script notebooks/experiment.ipynb"]
        payload["artifact_paths"] = ["artifacts/exported_model/saved_model.pb"]
        payload["artifact_inspection_commands"] = ["saved_model_cli show --dir artifacts/exported_model --all"]
        payload["config_review_paths"] = ["configs/train.yaml"]
        payload["config_review_commands"] = ['python -c "from pathlib import Path; p = Path(\\"configs/train.yaml\\"); print(p.read_text(encoding=\'utf-8\', errors=\'ignore\'))"']
        return payload

    monkeypatch.setattr(service, "build_workspace_tooling_status", patched)

    response = client.get(f"/api/projects/{project_id}/verification-brief", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["required_check_count"] == len(payload["required_checks"])
    assert payload["recommended_check_count"] == len(payload["recommended_checks"])
    assert payload["evidence_gap_count"] == len(payload["evidence_gaps"])
    assert payload["release_blocker_count"] == len(payload["release_blockers"])
    assert payload["handoff_warning_count"] == len(payload["handoff_warnings"])
    assert payload["loop_strategy_count"] == len(payload["loop_strategy"])
    assert "python train.py" in payload["required_checks"]
    assert any(item == "Focus path: train.py" for item in payload["recommended_checks"])
    assert "saved_model_cli show --dir artifacts/exported_model --all" in payload["required_checks"]
    assert "jupyter nbconvert --to script notebooks/experiment.ipynb" in payload["recommended_checks"]
    assert any("configs/train.yaml" in item and item.startswith("python -c ") for item in payload["recommended_checks"])
    assert any(item == "Review artifact path: artifacts/exported_model/saved_model.pb" for item in payload["recommended_checks"])
    assert any("Runtime blocker: Python is not available on PATH" in item for item in payload["evidence_gaps"])
    assert any("Evidence target still needs proof: Capture TensorBoard evidence instead of motivational speeches." == item for item in payload["evidence_gaps"])
    assert any("Config-driven ML path needs explicit review: configs/train.yaml" == item for item in payload["evidence_gaps"])
    assert any("Notebook-driven ML workflow still needs promotion" in item for item in payload["evidence_gaps"])
    assert any("Artifact path still needs direct inspection evidence: artifacts/exported_model/saved_model.pb" == item for item in payload["evidence_gaps"])
