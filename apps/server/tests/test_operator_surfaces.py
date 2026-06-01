from __future__ import annotations

from pathlib import Path

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
    assert "## Mission Control Operator Snapshot" in payload["snapshot_markdown"]
    assert any("browser_automation" in item or "Fix backend validation" in item for item in payload["current_focus"])


def test_instincts_preview_endpoint_derives_reusable_rules(client, bridge_headers) -> None:
    project_id = _seed_operator_project()

    response = client.get(f"/api/projects/{project_id}/instincts/preview", headers=bridge_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["instinct_count"] >= 3
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
    assert any("python -m pytest apps/server/tests/test_operator_surfaces.py -q" in item for item in payload["required_checks"])
    assert payload["evidence_gaps"]
    assert payload["release_blockers"]
    assert "## Mission Control Verification Brief" in payload["brief_markdown"]


def test_verification_brief_endpoint_surfaces_notebook_config_and_artifact_followups(client, bridge_headers, monkeypatch) -> None:
    project_id = _seed_operator_project()

    original = service.build_workspace_tooling_status

    def patched(project):
        payload = original(project)
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

    assert "saved_model_cli show --dir artifacts/exported_model --all" in payload["required_checks"]
    assert "jupyter nbconvert --to script notebooks/experiment.ipynb" in payload["recommended_checks"]
    assert any("configs/train.yaml" in item and item.startswith("python -c ") for item in payload["recommended_checks"])
    assert any(item == "Review artifact path: artifacts/exported_model/saved_model.pb" for item in payload["recommended_checks"])
    assert any("Config-driven ML path needs explicit review: configs/train.yaml" == item for item in payload["evidence_gaps"])
    assert any("Notebook-driven ML workflow still needs promotion" in item for item in payload["evidence_gaps"])
    assert any("Artifact path still needs direct inspection evidence: artifacts/exported_model/saved_model.pb" == item for item in payload["evidence_gaps"])
