from __future__ import annotations

import os
from pathlib import Path

from conftest import sample_workspace, wait_for
from db import SessionLocal
from manager import service
from models import Project, ProjectEvent


def _bridge_headers() -> dict[str, str]:
    token_path = Path(os.environ["MISSION_CONTROL_RUNTIME_ROOT"]) / "daemon.token"
    wait_for(token_path.exists)
    return {"X-Mission-Control-Token": token_path.read_text(encoding="utf-8").strip()}


def _prepare_repo_workspace(name: str) -> Path:
    workspace = Path(sample_workspace(name))
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# Repo under Mission Control\n", encoding="utf-8")
    tests_dir = workspace / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_sample.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    return workspace


def _set_project_to_dry_run(client, project_id: int) -> None:
    settings = client.get("/api/settings", params={"project_id": project_id})
    assert settings.status_code == 200, settings.text
    payload = settings.json()
    payload["runner_mode"] = "dry_run"
    response = client.put("/api/settings", params={"project_id": project_id}, json=payload)
    assert response.status_code == 200, response.text


def test_headless_happy_path_acceptance(client) -> None:
    workspace = _prepare_repo_workspace("headless-happy-path")
    attach = client.post(
        "/api/orchestrations/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Headless Happy Path",
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert attach.status_code == 200, attach.text
    attach_payload = attach.json()
    project_id = attach_payload["project"]["id"]
    assert attach_payload["attach_outcome"] == "imported_existing_codebase"

    _set_project_to_dry_run(client, project_id)

    opened = client.post(f"/api/projects/{project_id}/open")
    assert opened.status_code == 200, opened.text

    orchestration = client.post(
        "/api/orchestrations",
        headers=_bridge_headers(),
        json={
            "project_id": project_id,
            "user_request": "Use Mission Control for this repo and fix the failing tests.",
            "source": "codex_plugin",
        },
    )
    assert orchestration.status_code == 200, orchestration.text
    orchestration_id = orchestration.json()["id"]

    wait_for(
        lambda: bool(
            client.get(
                f"/api/orchestrations/{orchestration_id}/pending-decisions",
                headers=_bridge_headers(),
                params={"project_id": project_id},
            ).json()
        )
    )

    status_summary = client.get(
        f"/api/projects/{project_id}/orchestrations/{orchestration_id}/status-summary",
        headers=_bridge_headers(),
    )
    assert status_summary.status_code == 200, status_summary.text
    status_payload = status_summary.json()
    assert status_payload["message_type"] in {"blocked", "status_update"}
    assert status_payload["user_action_required"] is True
    assert "## Mission Control Status" in status_payload["fallback_markdown"]
    assert "### Current work" in status_payload["fallback_markdown"]
    assert "### Waiting on you" in status_payload["fallback_markdown"]
    assert "### Next expected step" in status_payload["fallback_markdown"]

    decisions_response = client.get(
        f"/api/orchestrations/{orchestration_id}/pending-decisions",
        headers=_bridge_headers(),
        params={"project_id": project_id},
    )
    assert decisions_response.status_code == 200, decisions_response.text
    decisions = decisions_response.json()
    approval = next((item for item in decisions if item["decision_type"] == "command_approval"), None)
    if approval is None:
        db = SessionLocal()
        try:
            project = db.get(Project, project_id)
            assert project is not None
            service._create_approval(
                db,
                project,
                request_type="command",
                title="Approve simulated dry-run test command",
                reason_short="Run a simulated local test command so Mission Control can continue the headless bridge flow safely.",
                risk_level="medium",
                cwd=project.workspace_path,
                request_payload_json={"command": "python -m pytest", "scope": ["tests/"], "simulated": True},
            )
            db.commit()
        finally:
            db.close()
        decisions = client.get(
            f"/api/orchestrations/{orchestration_id}/pending-decisions",
            headers=_bridge_headers(),
            params={"project_id": project_id},
        ).json()
        approval = next(item for item in decisions if item["decision_type"] == "command_approval")

    for decision in decisions:
        if decision["id"] == approval["id"] or not decision.get("options"):
            continue
        option = decision["options"][0]
        response = client.post(
            f"/api/decisions/{decision['id']}/answer",
            headers=_bridge_headers(),
            params={"project_id": project_id},
            json={"option_id": option["id"], "selected_text": option["label"]},
        )
        assert response.status_code == 200, response.text

    approval_message = client.get(
        f"/api/decisions/{approval['id']}/bridge-message",
        headers=_bridge_headers(),
        params={"project_id": project_id},
    )
    assert approval_message.status_code == 200, approval_message.text
    approval_payload = approval_message.json()
    assert approval_payload["message_type"] == "approval_request"
    assert "##" in approval_payload["fallback_markdown"]
    assert "**Command:**" in approval_payload["fallback_markdown"]
    assert "### Choose one" in approval_payload["fallback_markdown"]

    answered = client.post(
        f"/api/decisions/{approval['id']}/answer",
        headers=_bridge_headers(),
        params={"project_id": project_id},
        json={"option_id": "approve_once", "selected_text": "Approve once"},
    )
    assert answered.status_code == 200, answered.text
    answered_payload = answered.json()
    assert answered_payload["decision"]["status"] == "answered"
    assert answered_payload["next_status_summary"] is not None
    assert answered_payload["next_status_summary"]["user_action_required"] is False

    db = SessionLocal()
    try:
        db.add(
            ProjectEvent(
                project_id=project_id,
                event_type="validation_log",
                payload_json={
                    "message": "Validation saw Authorization: Bearer super-secret-token and OPENAI_API_KEY=sk-proj-secret-value",
                    "raw_log": "never show this raw log",
                },
            )
        )
        db.commit()
    finally:
        db.close()

    digest = client.get(
        f"/api/projects/{project_id}/orchestrations/{orchestration_id}/event-digest",
        headers=_bridge_headers(),
        params={"window": "since_orchestration_start"},
    )
    assert digest.status_code == 200, digest.text
    digest_payload = digest.json()
    assert digest_payload["message_type"] == "event_digest"
    assert "## Mission Control event digest" in digest_payload["fallback_markdown"]
    assert "super-secret-token" not in digest_payload["fallback_markdown"]
    assert "sk-proj-secret-value" not in digest_payload["fallback_markdown"]
    assert "raw_log" not in digest_payload["fallback_markdown"]

    evidence = client.post(
        f"/api/projects/{project_id}/handoff/evidence",
        headers=_bridge_headers(),
        json={
            "evidence_type": "test_result",
            "claim": "OPENAI_API_KEY=sk-proj-secret-value pytest run",
            "summary": "Authorization: Bearer super-secret-token should be redacted in chat output.",
            "command": "python -m pytest",
            "status": "not_run",
            "metadata_json": {"note": "Dry-run evidence seed"},
        },
    )
    assert evidence.status_code == 200, evidence.text

    handoff_generate = client.post(
        f"/api/projects/{project_id}/handoff/generate",
        headers=_bridge_headers(),
    )
    assert handoff_generate.status_code == 200, handoff_generate.text
    assert handoff_generate.json()["dry_run"] is True

    handoff_summary = client.get(
        f"/api/projects/{project_id}/orchestrations/{orchestration_id}/handoff-summary",
        headers=_bridge_headers(),
    )
    assert handoff_summary.status_code == 200, handoff_summary.text
    handoff_payload = handoff_summary.json()
    assert handoff_payload["message_type"] == "handoff_ready"
    assert "## Mission Control handoff" in handoff_payload["fallback_markdown"]
    assert "### Validation / evidence" in handoff_payload["fallback_markdown"]
    assert "dry-run" in handoff_payload["fallback_markdown"].lower()
    assert "sk-proj-secret-value" not in handoff_payload["fallback_markdown"]
    assert "super-secret-token" not in handoff_payload["fallback_markdown"]


def test_headless_attach_workspace_alias_returns_bridge_fields(client) -> None:
    workspace = _prepare_repo_workspace("headless-attach-alias")
    response = client.post(
        "/api/headless/attach-workspace",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Headless Alias",
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == payload["project"]["id"]
    assert payload["project_name"] == payload["project"]["name"]
    assert payload["source_type"] == "existing_folder"
    assert payload["next_action"] == "start_orchestration"


def test_headless_happy_path_demo_endpoint(client) -> None:
    workspace = _prepare_repo_workspace("headless-happy-path-demo")
    response = client.post(
        "/api/headless/happy-path-demo",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_name": "Happy Path Demo",
            "mode": "existing_codebase",
            "read_only_first": True,
            "attach_policy": "reuse_existing",
            "user_request": "Use Mission Control for this repo and fix the failing tests.",
            "create_pending_decision": True,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["attach"]["project_id"] == payload["attach"]["project"]["id"]
    assert payload["orchestration"]["source"] == "test"
    assert payload["orchestration"]["mode"] == "dry_run"
    assert payload["initial_status_summary"]["message_type"] in {"blocked", "status_update"}
    assert payload["pending_decision"]["status"] == "pending"
    assert payload["decision_bridge_message"]["message_type"] in {"approval_request", "manager_question"}
    assert payload["answer_result"] is None
    assert payload["event_digest"] is None
    assert payload["handoff_summary"] is None


def test_full_headless_happy_path_approve_flow(client) -> None:
    workspace = _prepare_repo_workspace("headless-approve-flow")
    start = client.post(
        "/api/headless/start-task",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "user_request": "Use Mission Control for this repo and fix the failing tests.",
            "strategy": "balanced",
            "mode": "dry_run",
            "interview_mode": "skip",
        },
    )
    assert start.status_code == 200, start.text
    payload = start.json()
    orchestration_id = payload["orchestration"]["id"]
    approval = next(item for item in payload["pending_decisions"] if item["decision_type"] == "command_approval")
    answered = client.post(
        f"/api/decisions/{approval['id']}/answer",
        headers=_bridge_headers(),
        params={"project_id": payload["project"]["id"]},
        json={"option_id": "approve_once", "selected_text": "Approve once"},
    )
    assert answered.status_code == 200, answered.text
    answer_payload = answered.json()
    assert answer_payload["decision"]["status"] == "answered"
    assert answer_payload["next_status_summary"]["user_action_required"] is False

    digest = client.get(
        f"/api/projects/{payload['project']['id']}/orchestrations/{orchestration_id}/event-digest",
        headers=_bridge_headers(),
        params={"window": "since_orchestration_start"},
    )
    assert digest.status_code == 200, digest.text
    assert "dry run validation simulated" in digest.json()["fallback_markdown"].lower()

    handoff = client.get(f"/api/projects/{payload['project']['id']}/orchestrations/{orchestration_id}/handoff-summary", headers=_bridge_headers())
    assert handoff.status_code == 200, handoff.text
    handoff_payload = handoff.json()
    assert "dry-run" in handoff_payload["fallback_markdown"].lower()
    assert "not run" in handoff_payload["fallback_markdown"].lower()


def test_start_headless_task_honors_project_id_when_workspace_is_also_provided(client) -> None:
    workspace = _prepare_repo_workspace("headless-project-id-match")
    first = client.post(
        "/api/projects",
        json={
            "name": "Project Id Match",
            "idea": "Honor the explicit project id",
            "workspace_path": workspace.as_posix(),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    )
    assert first.status_code == 200, first.text
    project = first.json()

    second = client.post(
        "/api/projects",
        json={
            "name": "Project Id Match Duplicate",
            "idea": "Same workspace, different project",
            "workspace_path": workspace.as_posix(),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    )
    assert second.status_code == 200, second.text

    start = client.post(
        "/api/headless/start-task",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "project_id": project["id"],
            "user_request": "Use Mission Control for this repo and fix the failing tests.",
            "strategy": "balanced",
            "mode": "dry_run",
            "interview_mode": "skip",
            "attach_policy": "reuse_existing",
        },
    )
    assert start.status_code == 200, start.text
    assert start.json()["project"]["id"] == project["id"]


def test_full_headless_happy_path_deny_flow(client) -> None:
    workspace = _prepare_repo_workspace("headless-deny-flow")
    start = client.post(
        "/api/headless/start-task",
        headers=_bridge_headers(),
        json={
            "workspace_path": workspace.as_posix(),
            "user_request": "Use Mission Control for this repo and fix the failing tests.",
            "strategy": "safe_mode",
            "mode": "dry_run",
            "interview_mode": "skip",
        },
    )
    assert start.status_code == 200, start.text
    payload = start.json()
    orchestration_id = payload["orchestration"]["id"]
    approval = next(item for item in payload["pending_decisions"] if item["decision_type"] == "command_approval")
    answered = client.post(
        f"/api/decisions/{approval['id']}/answer",
        headers=_bridge_headers(),
        params={"project_id": payload["project"]["id"]},
        json={"option_id": "deny", "selected_text": "Deny"},
    )
    assert answered.status_code == 200, answered.text
    answer_payload = answered.json()
    assert answer_payload["decision"]["status"] == "answered"
    assert answer_payload["next_status_summary"]["user_action_required"] is False

    handoff = client.get(f"/api/projects/{payload['project']['id']}/orchestrations/{orchestration_id}/handoff-summary", headers=_bridge_headers())
    assert handoff.status_code == 200, handoff.text
    handoff_markdown = handoff.json()["fallback_markdown"].lower()
    assert "dry-run" in handoff_markdown
    assert "not run" in handoff_markdown
    assert "denied" in handoff_markdown or "limitations" in handoff_markdown
