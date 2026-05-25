from __future__ import annotations

import asyncio
from pathlib import Path

from errors import ERROR_REGISTRY, MissionControlError, format_codex_chat_error, format_problem_details, is_valid_error_code, iter_error_definitions
from plugin_health import mission_control_plugin_health
from bridge_formatter import format_mission_control_error_message
from conftest import sample_workspace, wait_for


REQUIRED_CODES = {
    "MC-BOOT-RUNTIME-PATH-001",
    "MC-DAEMON-PORT-IN-USE-001",
    "MC-MCP-TOOL-NOT-FOUND-001",
    "MC-RUNNER-NONE-AVAILABLE-001",
    "MC-CODEX-CLI-MISSING-001",
    "MC-OLLAMA-SERVER-OFFLINE-001",
    "MC-WORKSPACE-PATH-MISSING-001",
    "MC-ORCH-SESSION-NOT-FOUND-001",
    "MC-DECISION-INVALID-OPTION-001",
    "MC-BRIDGE-REDACTION-FAILED-001",
    "MC-HANDOFF-EVIDENCE-MISSING-001",
    "MC-VALIDATION-NOT-RUN-001",
    "MC-SECURITY-POLICY-BLOCKED-001",
    "MC-UNKNOWN-UNEXPECTED-001",
}


def _bridge_headers() -> dict[str, str]:
    token_path = Path(__import__("os").environ["MISSION_CONTROL_RUNTIME_ROOT"]) / "daemon.token"
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


def test_error_registry_contains_required_codes_and_unique_entries() -> None:
    assert REQUIRED_CODES.issubset(ERROR_REGISTRY.keys())
    codes = [definition.code for definition in iter_error_definitions()]
    assert len(codes) == len(set(codes))
    for definition in iter_error_definitions():
        assert is_valid_error_code(definition.code)
        assert definition.family
        assert definition.title
        assert definition.severity
        assert definition.default_breakpoint
        assert definition.recommended_fix


def test_problem_details_and_chat_formatter_include_required_fields_and_redact() -> None:
    error = MissionControlError(
        code="MC-BRIDGE-REDACTION-FAILED-001",
        breakpoint="bridge.redact_output",
        safe_details={"token": "ghp_abcdefghijklmnopqrstuvwxyz", "runner": "codex_cli"},
    )
    payload = format_problem_details(error, instance="/api/test")
    assert payload["type"]
    assert payload["title"]
    assert payload["status"] == 500
    assert payload["detail"]
    assert payload["instance"] == "/api/test"
    assert payload["code"] == "MC-BRIDGE-REDACTION-FAILED-001"
    assert payload["safe_details"]["token"] != "ghp_abcdefghijklmnopqrstuvwxyz"
    markdown = format_codex_chat_error(error)
    assert "MC-BRIDGE-REDACTION-FAILED-001" in markdown
    assert "**Severity:** error" in markdown
    assert "### Recommended fix" in markdown
    bridge_message = format_mission_control_error_message(message_id="err-1", error=error, created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    assert bridge_message["message_type"] == "failed"
    assert bridge_message["machine_payload_json"]["code"] == "MC-BRIDGE-REDACTION-FAILED-001"


def test_plugin_health_maps_runner_errors_to_codes(monkeypatch) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": False,
            "cli_version": None,
            "login_status": "Unavailable",
            "auth_mode": None,
            "authenticated": False,
            "auth_status_detectable": True,
            "mcp_servers": [],
            "local_skills": [],
        },
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "web"})
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr("plugin_health._probe_url", lambda url, timeout=2.0: (False, "URLError"))
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)

    payload = asyncio.run(mission_control_plugin_health())
    by_key = {item["key"]: item for item in payload["checks"]}
    assert by_key["mission_control_daemon_reachable"]["code"] == "MC-DAEMON-NOT-RUNNING-001"
    assert by_key["mcp_server_reachable"]["code"] == "MC-MCP-BRIDGE-MISSING-001"
    assert by_key["codex_cli_detected"]["code"] == "MC-CODEX-CLI-MISSING-001"


def test_unknown_exception_maps_to_unknown_problem_details() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        error = MissionControlError(code="MC-UNKNOWN-UNEXPECTED-001", detail="boom", breakpoint="diagnostics.run", caused_by=exc)
    payload = error.to_problem_details(instance="/api/test")
    assert payload["code"] == "MC-UNKNOWN-UNEXPECTED-001"
    assert payload["severity"] == "error"


def test_pending_decision_invalid_option_returns_problem_details(client) -> None:
    project = _create_project(client, "Invalid Decision Problem", "invalid-decision-problem")
    db_module = __import__("db")
    models_module = __import__("models")
    db = db_module.SessionLocal()
    try:
        record = db.get(models_module.Project, project["id"])
        assert record is not None
        question = models_module.ManagerQuestion(
            project_id=record.id,
            question="Which path should Mission Control take?",
            options_json=[{"id": "safe", "label": "Safe path"}],
            impact="medium",
            status="pending",
        )
        db.add(question)
        db.commit()
    finally:
        db.close()

    decisions = client.get(f"/api/projects/{project['id']}/pending-decisions", headers=_bridge_headers()).json()
    decision_id = decisions[0]["id"]
    response = client.post(
        f"/api/decisions/{decision_id}/answer",
        headers=_bridge_headers(),
        params={"project_id": project["id"]},
        json={"option_id": "reckless", "selected_text": "Reckless path"},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "MC-DECISION-INVALID-OPTION-001"
    assert payload["breakpoint"] == "decision.validate_option"
    assert payload["user_action_required"] is True
