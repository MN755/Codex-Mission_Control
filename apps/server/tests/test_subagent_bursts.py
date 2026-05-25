from __future__ import annotations

import os
from pathlib import Path

from bridge_formatter import format_pending_decision_message
from conftest import sample_workspace, wait_for
from db import SessionLocal
from models import Project
from models import utc_now
from subagent_planner import BURST_TEMPLATES


def _bridge_headers() -> dict[str, str]:
    token_path = Path(os.environ["MISSION_CONTROL_RUNTIME_ROOT"]) / "daemon.token"
    wait_for(token_path.exists)
    return {"X-Mission-Control-Token": token_path.read_text(encoding="utf-8").strip()}


def _create_project(client, name: str, workspace_name: str) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"{name} idea",
            "workspace_path": sample_workspace(workspace_name),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_default_subagent_policy_is_read_only_and_no_command(client) -> None:
    response = client.get("/api/subagent-policy", headers=_bridge_headers())
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["default_mode"] == "read_only"
    assert payload["max_subagents_per_burst"] == 6
    assert payload["allow_file_edits"] is False
    assert payload["allow_commands"] is False
    assert payload["require_user_approval_above_count"] == 3


def test_burst_templates_exist() -> None:
    assert [spec.display_name for spec in BURST_TEMPLATES["codebase_intake_burst"]["subagents"]] == [
        "Repo Mapper",
        "Test Finder",
        "Docs Reader",
        "Risk Scanner",
        "Dependency Mapper",
    ]
    assert [spec.display_name for spec in BURST_TEMPLATES["review_burst"]["subagents"]] == [
        "Correctness Reviewer",
        "Security Reviewer",
        "Test Coverage Reviewer",
        "Maintainability Reviewer",
        "Docs Reviewer",
    ]
    assert [spec.display_name for spec in BURST_TEMPLATES["failure_diagnosis_burst"]["subagents"]] == [
        "Logs Analyst",
        "Recent Changes Analyst",
        "Test Failure Analyst",
        "Dependency Analyst",
        "Recovery Planner",
    ]


def test_planner_recommends_large_read_heavy_burst_and_creates_pending_decision(client) -> None:
    project = _create_project(client, "Large Repo", "large-repo")
    response = client.post(
        f"/api/projects/{project['id']}/subagent-bursts/recommend",
        headers=_bridge_headers(),
        json={
            "purpose": "Read-only codebase intake",
            "task_type": "codebase_exploration",
            "codebase_size": "large",
            "task_complexity": "large",
            "expected_parallelism": 5,
            "risk_level": "low",
            "bounded_scope": True,
            "requires_file_edits": False,
            "requires_commands": False,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["recommended"] is True
    assert payload["suggested_burst_template"] == "codebase_intake_burst"
    assert payload["number_of_subagents"] == 5
    assert payload["pending_decision_required"] is True
    assert payload["batch"]["status"] == "proposed"
    assert all(spec["sandbox_mode"] == "read-only" for spec in payload["batch"]["specs"])

    decisions = client.get(f"/api/projects/{project['id']}/pending-decisions", headers=_bridge_headers())
    assert decisions.status_code == 200, decisions.text
    assert any(item["decision_type"] == "subagent_burst_approval" for item in decisions.json())


def test_planner_rejects_simple_task(client) -> None:
    project = _create_project(client, "Small Repo", "small-repo")
    response = client.post(
        f"/api/projects/{project['id']}/subagent-bursts/recommend",
        headers=_bridge_headers(),
        json={
            "purpose": "Tiny review",
            "task_type": "review",
            "codebase_size": "small",
            "task_complexity": "small",
            "expected_parallelism": 1,
            "risk_level": "low",
            "bounded_scope": True,
            "requires_file_edits": False,
            "requires_commands": False,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["recommended"] is False
    assert payload["batch"] is None


def test_subagent_burst_bridge_message_and_use_fewer_flow(client) -> None:
    project = _create_project(client, "Burst Demo", "burst-demo")
    response = client.post(
        f"/api/projects/{project['id']}/subagent-bursts/recommend",
        headers=_bridge_headers(),
        json={
            "purpose": "Read-only codebase intake",
            "task_type": "codebase_exploration",
            "codebase_size": "large",
            "task_complexity": "large",
            "expected_parallelism": 5,
        },
    )
    batch_id = response.json()["batch"]["id"]
    decisions = client.get(f"/api/projects/{project['id']}/pending-decisions", headers=_bridge_headers()).json()
    decision = next(item for item in decisions if item["decision_type"] == "subagent_burst_approval")

    bridge_message = client.get(
        f"/api/decisions/{decision['id']}/bridge-message",
        headers=_bridge_headers(),
        params={"project_id": project["id"]},
    )
    assert bridge_message.status_code == 200, bridge_message.text
    markdown = bridge_message.json()["fallback_markdown"]
    assert "Mission Control recommends a Codex subagent burst" in markdown
    assert "Repo Mapper" in markdown
    assert "Use fewer subagents" in markdown

    answer = client.post(
        f"/api/decisions/{decision['id']}/answer",
        headers=_bridge_headers(),
        params={"project_id": project["id"]},
        json={"option_id": "use_fewer_subagents", "selected_text": "Use fewer subagents"},
    )
    assert answer.status_code == 200, answer.text

    batch = client.get(f"/api/subagents/batches/{batch_id}", headers=_bridge_headers(), params={"project_id": project["id"]}).json()
    statuses = [spec["status"] for spec in batch["specs"]]
    assert batch["status"] == "approved"
    assert statuses.count("approved") == 3
    assert statuses.count("cancelled") == 2


def test_custom_agent_generation_does_not_overwrite_existing_files(client) -> None:
    project = _create_project(client, "Agent Files", "agent-files")
    first = client.post(
        f"/api/projects/{project['id']}/subagent-agents/generate",
        headers=_bridge_headers(),
        json={"overwrite_existing": False},
    )
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["generated_count"] >= 10
    assert any(path.endswith("mc-repo-mapper.toml") for path in payload["generated_files"])

    second = client.post(
        f"/api/projects/{project['id']}/subagent-agents/generate",
        headers=_bridge_headers(),
        json={"overwrite_existing": False},
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert second_payload["generated_count"] == 0
    assert any(path.endswith("mc-repo-mapper.toml") for path in second_payload["skipped_existing_files"])


def test_custom_agent_generation_rejects_non_local_workspace_path(client) -> None:
    project = _create_project(client, "Bad Agent Root", "bad-agent-root")
    db = SessionLocal()
    try:
        record = db.get(Project, project["id"])
        assert record is not None
        record.workspace_path = "https://example.com/not-a-workspace"
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/api/projects/{project['id']}/subagent-agents/generate",
        headers=_bridge_headers(),
        json={"overwrite_existing": False},
    )
    assert response.status_code == 400, response.text
    assert "local filesystem" in response.json()["detail"].lower()


def test_result_ingestion_completes_batch(client) -> None:
    project = _create_project(client, "Results Demo", "results-demo")
    response = client.post(
        f"/api/projects/{project['id']}/subagent-bursts/recommend",
        headers=_bridge_headers(),
        json={
            "purpose": "Review package",
            "task_type": "review",
            "codebase_size": "medium",
            "task_complexity": "medium",
            "expected_parallelism": 3,
        },
    )
    assert response.status_code == 200, response.text
    batch = response.json()["batch"]
    assert batch["status"] == "approved"

    results = client.post(
        f"/api/subagents/batches/{batch['id']}/results",
        headers=_bridge_headers(),
        params={"project_id": project["id"]},
        json={
            "results": [
                {"subagent_name": spec["name"], "summary": f"{spec['display_name']} summary", "evidence": ["file.py"], "risks_found": [], "recommendations": ["keep"], "confidence": "medium"}
                for spec in batch["specs"]
            ]
        },
    )
    assert results.status_code == 200, results.text
    payload = results.json()
    assert payload["status"] == "completed"
    assert all(spec["status"] == "completed" for spec in payload["specs"])


def test_burst_policy_honors_command_and_file_edit_allowances(client) -> None:
    policy = client.put(
        "/api/subagent-policy",
        headers=_bridge_headers(),
        json={
            "enabled": True,
            "default_mode": "limited_write",
            "allow_file_edits": True,
            "allow_commands": True,
            "require_user_approval_above_count": 10,
        },
    )
    assert policy.status_code == 200, policy.text

    project = _create_project(client, "Writable Burst", "writable-burst")
    response = client.post(
        f"/api/projects/{project['id']}/subagent-bursts/recommend",
        headers=_bridge_headers(),
        json={
            "purpose": "Bounded fix burst",
            "task_type": "planning",
            "codebase_size": "large",
            "task_complexity": "medium",
            "expected_parallelism": 3,
            "risk_level": "low",
            "bounded_scope": True,
            "requires_file_edits": True,
            "requires_commands": True,
            "allowed_paths_json": ["src"],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["recommended"] is True
    assert payload["pending_decision_required"] is False
    assert all(spec["sandbox_mode"] == "workspace-write" for spec in payload["batch"]["specs"])
    assert payload["batch"]["manual_prompt_text"].startswith("Spawn short-lived Codex subagents for the following bounded tasks.")
    assert "Commands are allowed when needed for bounded validation." in payload["batch"]["manual_prompt_text"]
    assert "File edits are allowed only inside the assigned paths." in payload["batch"]["manual_prompt_text"]


def test_custom_agent_generation_reflects_current_subagent_policy(client) -> None:
    policy = client.put(
        "/api/subagent-policy",
        headers=_bridge_headers(),
        json={
            "enabled": True,
            "default_mode": "limited_write",
            "allow_file_edits": True,
            "allow_commands": True,
            "require_user_approval_above_count": 3,
        },
    )
    assert policy.status_code == 200, policy.text
    project = _create_project(client, "Agent Policy", "agent-policy")

    response = client.post(
        f"/api/projects/{project['id']}/subagent-agents/generate",
        headers=_bridge_headers(),
        json={"overwrite_existing": True, "template_names": ["mc-repo-mapper"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    generated = next(path for path in payload["generated_files"] if path.endswith("mc-repo-mapper.toml"))
    content = Path(generated).read_text(encoding="utf-8")
    assert 'sandbox_mode = "workspace-write"' in content
    assert "allow_file_edits = true" in content
    assert "allow_commands = true" in content


def test_direct_bridge_formatter_for_subagent_burst() -> None:
    message = format_pending_decision_message(
        decision={
            "id": 1,
            "project_id": 9,
            "orchestration_id": 12,
            "decision_type": "subagent_burst_approval",
            "title": "Mission Control recommends a Codex subagent burst",
            "message": "The repo has multiple independent areas that can be explored in parallel.",
            "risk_level": "low",
            "status": "pending",
            "options_json": [{"id": "approve_burst", "label": "Approve burst"}],
            "recommended_option": "approve_burst",
            "created_at": utc_now(),
            "presentation_json": {
                "purpose": "Read-only codebase intake",
                "subagent_count": 5,
                "estimated_intensity": "medium",
                "subagents": ["Repo Mapper", "Test Finder"],
            },
        }
    )
    assert message["message_type"] == "subagent_burst_recommendation"
    assert "Read-only codebase intake" in message["fallback_markdown"]
