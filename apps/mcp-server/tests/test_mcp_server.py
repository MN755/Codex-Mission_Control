from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mission_control_mcp_server import catalog
from mission_control_mcp_server.client import MissionControlDaemonClient, _base_url
from mission_control_mcp_server.server import MissionControlMcpServer


EXPECTED_RESOURCES = {
    "mission-control://orchestrations/{orchestration_id}/status",
    "mission-control://orchestrations/{orchestration_id}/events",
    "mission-control://projects/{project_id}/status",
    "mission-control://projects/{project_id}/agents",
    "mission-control://projects/{project_id}/pending-decisions",
    "mission-control://projects/{project_id}/handoff",
    "mission-control://projects/{project_id}/codebase-map",
    "mission-control://projects/{project_id}/diagnostics",
    "mission-control://projects/{project_id}/webwright",
    "mission-control://projects/{project_id}/swarm-plan",
    "mission-control://projects/{project_id}/risk-register",
    "mission-control://projects/{project_id}/agent-contracts",
    "mission-control://projects/{project_id}/validation-summary",
    "mission-control://projects/{project_id}/decision-ledger",
    "mission-control://projects/{project_id}/path-locks",
    "mission-control://projects/{project_id}/operator-snapshot",
    "mission-control://projects/{project_id}/instincts",
    "mission-control://projects/{project_id}/verification-brief",
}

EXPECTED_PROMPTS = {
    "attach_current_workspace",
    "use_mission_control_for_repo",
    "import_existing_codebase",
    "start_manager_led_task",
    "continue_orchestration",
    "show_pending_approvals",
    "answer_pending_approval",
    "review_latest_handoff",
    "debug_failed_orchestration",
    "use_webwright_for_browser_task",
    "pause_orchestration",
    "resume_orchestration",
    "explain_current_swarm",
    "switch_swarm_strategy",
    "enable_safe_mode",
    "generate_agents_md_proposal",
    "install_from_github",
    "autowire_providers",
}


def test_daemon_client_brackets_ipv6_loopback_urls() -> None:
    assert _base_url("::1", 8010) == "http://[::1]:8010"


def test_daemon_client_rejects_non_local_spawn(monkeypatch) -> None:
    monkeypatch.setenv("MISSION_CONTROL_BACKEND_HOST", "0.0.0.0")
    client = MissionControlDaemonClient(base_url="http://0.0.0.0:8010", timeout=0.1)

    try:
        client.ensure_daemon_running()
    except RuntimeError as exc:
        assert "localhost" in str(exc).lower()
    else:
        raise AssertionError("Expected non-local daemon binding to be rejected.")


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def attach_workspace(self, **kwargs):
        self.calls.append(("attach_workspace", kwargs))
        return {"project": {"id": 7, "name": "Demo"}, "orchestration": {"id": 14}, "attach_outcome": "reused_existing_orchestration"}

    def start_task(self, **kwargs):
        self.calls.append(("start_task", kwargs))
        return {"id": 14, "project_id": kwargs["project_id"], "status": "planning"}

    def get_status(self, **kwargs):
        self.calls.append(("get_status", kwargs))
        return {"project_name": "Demo", "orchestration_status": "running", "pending_decisions_count": 1}

    def get_status_summary(self, **kwargs):
        self.calls.append(("get_status_summary", kwargs))
        return {
            "message_type": "blocked",
            "title": "Mission Control status",
            "summary": "Waiting on approval.",
            "fallback_markdown": "## Mission Control Status\n",
            "user_action_required": True,
        }

    def get_pending_decisions(self, **kwargs):
        self.calls.append(("get_pending_decisions", kwargs))
        return [{"id": 3, "title": "Approve build", "risk_level": "medium"}]

    def answer_decision(self, **kwargs):
        self.calls.append(("answer_decision", kwargs))
        return {"id": kwargs["decision_id"], "status": "answered"}

    def get_handoff(self, **kwargs):
        self.calls.append(("get_handoff", kwargs))
        return {"ready": False, "status": "not_ready"}

    def plugin_health_summary(self):
        self.calls.append(("plugin_health_summary", {}))
        return {"status": "ready", "checks": []}

    def enable_safe_mode(self, project_id: int):
        self.calls.append(("enable_safe_mode", {"project_id": project_id}))
        return {"project_id": project_id, "enabled": True}

    def get_event_digest(self, **kwargs):
        self.calls.append(("get_event_digest", kwargs))
        return {"message_type": "event_digest", "summary": "Nothing alarming."}

    def get_handoff_summary(self, **kwargs):
        self.calls.append(("get_handoff_summary", kwargs))
        return {"message_type": "handoff_ready", "summary": "Ready for review."}

    def create_snapshot(self, project_id: int, **kwargs):
        self.calls.append(("create_snapshot", {"project_id": project_id, **kwargs}))
        return {"id": 4, "project_id": project_id, "status": "available"}

    def request_recovery_plan(self, **kwargs):
        self.calls.append(("request_recovery_plan", kwargs))
        return {"id": 8, "status": "proposed"}

    def get_orchestration_events(self, orchestration_id: int, *, project_id: int | None = None):
        self.calls.append(("get_orchestration_events", {"orchestration_id": orchestration_id, "project_id": project_id}))
        return [{"event_type": "orchestration_created"}]

    def get_codebase_map(self, project_id: int):
        self.calls.append(("get_codebase_map", {"project_id": project_id}))
        return {"project_id": project_id, "languages_json": ["Python"]}

    def get_codebase_understanding(self, project_id: int):
        self.calls.append(("get_codebase_understanding", {"project_id": project_id}))
        return {"project_id": project_id, "summary": "Small Python app."}

    def set_import_interview_choice(self, project_id: int, choice: str):
        self.calls.append(("set_import_interview_choice", {"project_id": project_id, "choice": choice}))
        return {"project_id": project_id, "choice": choice}

    def get_diagnostics(self, **kwargs):
        self.calls.append(("get_diagnostics", kwargs))
        return {"plugin_health": "healthy", "recent_reports": []}

    def get_webwright_status(self, project_id: int):
        self.calls.append(("get_webwright_status", {"project_id": project_id}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "install_status": "ready",
            "summary": "Webwright is ready.",
            "launch_command": "webwright",
            "workspace_signals": ["Playwright config detected."],
            "recommended_fix": None,
            "recommended_install_commands": ["git clone https://github.com/microsoft/Webwright"],
            "use_cases": ["Browser automation"],
            "notes": ["Optional companion runtime."],
            "version": "0.1.0",
        }

    def get_swarm_plan(self, project_id: int):
        self.calls.append(("get_swarm_plan", {"project_id": project_id}))
        return {"project_id": project_id, "mode": "balanced"}

    def update_swarm_preferences(self, project_id: int, payload: dict):
        self.calls.append(("update_swarm_preferences", {"project_id": project_id, **payload}))
        return {"project_id": project_id, **payload}

    def generate_swarm_plan(self, project_id: int, **kwargs):
        self.calls.append(("generate_swarm_plan", {"project_id": project_id, **kwargs}))
        return {"project_id": project_id, "status": "pending_approval"}

    def approve_swarm_plan(self, project_id: int, swarm_plan_id: int):
        self.calls.append(("approve_swarm_plan", {"project_id": project_id, "swarm_plan_id": swarm_plan_id}))
        return {"project_id": project_id, "id": swarm_plan_id, "status": "approved"}

    def get_project_settings(self, project_id: int):
        self.calls.append(("get_project_settings", {"project_id": project_id}))
        return {"project_id": project_id, "approval_policy": "on-request"}

    def update_project_settings(self, project_id: int, payload: dict):
        self.calls.append(("update_project_settings", {"project_id": project_id, **payload}))
        return {"project_id": project_id, **payload}

    def get_import_safety(self, project_id: int):
        self.calls.append(("get_import_safety", {"project_id": project_id}))
        return {"project_id": project_id, "read_only_scan_completed": True}

    def update_import_safety(self, project_id: int, payload: dict):
        self.calls.append(("update_import_safety", {"project_id": project_id, **payload}))
        return {"project_id": project_id, **payload}

    def get_tool_catalog(self):
        self.calls.append(("get_tool_catalog", {}))
        return [{"id": "browser", "permission_policy": "ask_every_time"}]

    def set_tool_permission(self, tool_id: str, permission_policy: str):
        self.calls.append(("set_tool_permission", {"tool_id": tool_id, "permission_policy": permission_policy}))
        return {"tool_id": tool_id, "permission_policy": permission_policy}

    def get_agents_md_status(self, project_id: int):
        self.calls.append(("get_agents_md_status", {"project_id": project_id}))
        return {"project_id": project_id, "has_agents_md": False}

    def propose_agents_md(self, project_id: int):
        self.calls.append(("propose_agents_md", {"project_id": project_id}))
        return {"project_id": project_id, "recommended_path": "AGENTS.md"}

    def request_recovery_options(self, **kwargs):
        self.calls.append(("request_recovery_options", kwargs))
        return {"status": "requested"}

    def pause(self, orchestration_id: int, *, project_id: int | None = None):
        self.calls.append(("pause", {"orchestration_id": orchestration_id, "project_id": project_id}))
        return {"id": orchestration_id, "status": "paused"}

    def resume(self, orchestration_id: int, *, project_id: int | None = None):
        self.calls.append(("resume", {"orchestration_id": orchestration_id, "project_id": project_id}))
        return {"id": orchestration_id, "status": "running"}

    def read_resource(self, uri: str):
        self.calls.append(("read_resource", {"uri": uri}))
        return {"uri": uri, "safe": True}


def test_tool_schemas_are_exposed() -> None:
    server = MissionControlMcpServer(client=FakeClient())
    names = {tool["name"] for tool in server.list_tools()}
    assert "mission_control_attach_workspace" in names
    assert "mission_control_start_task" in names
    assert "mission_control_import_existing_codebase" in names
    assert "mission_control_plugin_health" in names
    assert "mission_control_get_event_digest" in names
    assert "mission_control_request_snapshot" in names
    assert "mission_control_request_recovery_plan" in names
    assert all(tool["inputSchema"]["additionalProperties"] is False for tool in server.list_tools())


def test_attach_workspace_tool_calls_daemon_client() -> None:
    client = FakeClient()
    server = MissionControlMcpServer(client=client)
    result = server.call_tool(
        "mission_control_attach_workspace",
        {"workspace_path": "C:/demo", "project_name": "Demo", "mode": "auto", "read_only_first": True, "attach_policy": "reuse_existing"},
    )
    assert result["structuredContent"]["project"]["id"] == 7
    assert client.calls[0][0] == "attach_workspace"


def test_get_status_returns_compact_summary() -> None:
    client = FakeClient()
    server = MissionControlMcpServer(client=client)
    result = server.call_tool("mission_control_get_status", {"orchestration_id": 14})
    assert result["structuredContent"]["message_type"] == "blocked"
    assert result["structuredContent"]["user_action_required"] is True
    assert client.calls[0][0] == "get_status_summary"


def test_answer_decision_sends_answer() -> None:
    client = FakeClient()
    server = MissionControlMcpServer(client=client)
    result = server.call_tool(
        "mission_control_answer_decision",
        {"decision_id": 9, "project_id": 7, "option_id": "approve_once", "selected_text": "Approve once"},
    )
    assert result["structuredContent"]["status"] == "answered"
    assert client.calls[0][0] == "answer_decision"


def test_new_runtime_tools_dispatch_to_client() -> None:
    client = FakeClient()
    server = MissionControlMcpServer(client=client)

    server.call_tool("mission_control_plugin_health", {})
    server.call_tool("mission_control_enable_safe_mode", {"project_id": 7})
    server.call_tool("mission_control_get_event_digest", {"project_id": 7, "window": "last_15_minutes"})
    server.call_tool("mission_control_get_webwright_status", {"project_id": 7})
    server.call_tool("mission_control_request_snapshot", {"project_id": 7, "label": "Before edits", "description": "Checkpoint"})
    server.call_tool("mission_control_request_recovery_plan", {"project_id": 7, "trigger_summary": "Workers are stuck."})

    called = [name for name, _ in client.calls]
    assert "plugin_health_summary" in called
    assert "enable_safe_mode" in called
    assert "get_event_digest" in called
    assert "get_webwright_status" in called
    assert "create_snapshot" in called
    assert "request_recovery_plan" in called


def test_resources_and_prompts_are_catalog_backed() -> None:
    server = MissionControlMcpServer(client=FakeClient())
    resource_names = {resource["uriTemplate"] for resource in server.list_resource_templates()}
    prompt_names = {prompt["name"] for prompt in server.list_prompts()}
    assert server.list_resources() == []
    assert resource_names == EXPECTED_RESOURCES
    assert EXPECTED_PROMPTS.issubset(prompt_names)
    prompt = server.get_prompt("continue-orchestration")
    assert prompt["messages"][0]["role"] == "user"


def test_resources_return_safe_summary_payloads() -> None:
    client = FakeClient()
    server = MissionControlMcpServer(client=client)
    result = server.read_resource("mission-control://projects/7/status")
    assert result["contents"][0]["mimeType"] == "application/json"
    assert '"safe": true' in result["contents"][0]["text"]


def test_daemon_client_reads_new_operator_resources_without_network(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    monkeypatch.setattr(
        client,
        "get_operator_snapshot",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "project_status": "active",
            "overall_status": "needs_review",
            "orchestration_status": "running",
            "handoff_status": "needs_review",
            "current_action": "Run the named pytest lane.",
            "pending_approvals_count": 1,
            "pending_questions_count": 0,
            "active_agent_count": 2,
            "current_focus": ["Blocked Worker: Run validation."],
            "top_risks": ["Validation evidence is missing."],
            "recent_events": ["Validation blocked: worker is waiting."],
            "validation_gap_count": 1,
            "swarm_mode": "balanced",
            "recommended_next_action": "Run the named pytest lane.",
            "performance_note": "Device lag risk is low.",
            "generated_at": "2026-05-26T00:00:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_instincts_preview",
        lambda project_id: {
            "project_id": project_id,
            "instinct_count": 1,
            "instincts": [
                {
                    "key": "ship-with-evidence",
                    "title": "Ship with evidence, not vibes",
                    "trigger": "A handoff exists.",
                    "rule": "Capture proof before closing work.",
                    "confidence": "high",
                    "tags": ["handoff", "evidence"],
                    "evidence": ["Handoff status: needs_review"],
                }
            ],
            "generated_at": "2026-05-26T00:00:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_verification_brief",
        lambda project_id: {
            "project_id": project_id,
            "readiness": "blocked",
            "required_checks": ["python -m pytest apps/server/tests/test_operator_surfaces.py -q"],
            "recommended_checks": ["Review the handoff evidence."],
            "evidence_gaps": ["No validated handoff evidence has been recorded yet."],
            "release_blockers": ["Required review gate not passed: Backend verification gate [pending]"],
            "handoff_warnings": ["Handoff status is needs_review."],
            "loop_strategy": ["Run the required checks first."],
            "generated_at": "2026-05-26T00:00:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_webwright_status",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "install_status": "ready",
            "summary": "Webwright runtime and Playwright package are both detectable.",
            "launch_command": "webwright",
            "workspace_signals": ["package.json already references Playwright."],
            "recommended_fix": None,
            "recommended_install_commands": ["git clone https://github.com/microsoft/Webwright"],
            "use_cases": ["Reusable browser scripts."],
            "notes": ["Optional browser-agent companion."],
            "version": "0.1.0",
        },
    )

    snapshot = client.read_resource("mission-control://projects/7/operator-snapshot")
    instincts = client.read_resource("mission-control://projects/7/instincts")
    verification = client.read_resource("mission-control://projects/7/verification-brief")
    webwright = client.read_resource("mission-control://projects/7/webwright")

    assert snapshot["project_name"] == "Demo"
    assert snapshot["recommended_next_action"] == "Run the named pytest lane."
    assert instincts["instincts"][0]["key"] == "ship-with-evidence"
    assert verification["readiness"] == "blocked"
    assert verification["required_checks"] == ["python -m pytest apps/server/tests/test_operator_surfaces.py -q"]
    assert webwright["available"] is True
    assert webwright["launch_command"] == "webwright"


def test_daemon_client_auto_start_launches_when_health_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MISSION_CONTROL_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("MISSION_CONTROL_LAUNCHER_DIR", str(tmp_path / "launcher"))
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8123", timeout=0.2)
    attempts = {"count": 0}

    def fake_healthcheck() -> bool:
        attempts["count"] += 1
        return attempts["count"] > 1

    launches: list[list[str]] = []

    def fake_popen(args, **kwargs):
        launches.append(list(args))
        return object()

    monkeypatch.setattr(client, "_healthcheck", fake_healthcheck)
    monkeypatch.setattr(client, "_port_in_use", lambda: False)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    client.ensure_daemon_running()

    assert launches
    assert any("mission_control_daemon.py" in segment for segment in launches[0])


def test_catalog_falls_back_to_bundled_json_when_repo_root_is_missing(monkeypatch) -> None:
    catalog.load_plugin_manifest.cache_clear()
    catalog.load_resource_catalog.cache_clear()
    catalog.load_prompt_catalog.cache_clear()
    monkeypatch.setattr(catalog, "discover_repo_root", lambda: None)

    manifest = catalog.load_plugin_manifest()
    resources = catalog.resource_entries()
    prompts = catalog.prompt_entries()

    assert manifest["name"] == "mission-control"
    assert {entry["uri_template"] for entry in resources} == EXPECTED_RESOURCES
    assert EXPECTED_PROMPTS.issubset({entry["name"] for entry in prompts})


def test_bundled_catalog_files_match_repo_catalog_sources() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    bundled_root = repo_root / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "_bundled"
    assert json.loads((bundled_root / "plugin.json").read_text(encoding="utf-8")) == json.loads(
        (repo_root / "plugins" / "mission-control" / "plugin.json").read_text(encoding="utf-8")
    )
    assert json.loads((bundled_root / "resources.json").read_text(encoding="utf-8")) == json.loads(
        (repo_root / "plugins" / "mission-control" / "mcp" / "resources.json").read_text(encoding="utf-8")
    )
    assert json.loads((bundled_root / "prompts.json").read_text(encoding="utf-8")) == json.loads(
        (repo_root / "plugins" / "mission-control" / "mcp" / "prompts.json").read_text(encoding="utf-8")
    )


def test_daemon_client_uses_packaged_runtime_defaults_without_repo_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MISSION_CONTROL_REPO_ROOT", raising=False)
    monkeypatch.delenv("MISSION_CONTROL_RUNTIME_ROOT", raising=False)
    monkeypatch.delenv("MISSION_CONTROL_LAUNCHER_DIR", raising=False)
    monkeypatch.setenv("MISSION_CONTROL_APP_HOME", str(tmp_path / "app-home"))
    monkeypatch.setattr(MissionControlDaemonClient, "_discover_repo_root", lambda self: None)

    client = MissionControlDaemonClient(timeout=0.1)

    assert client.repo_root is None
    assert client.config["backendPort"] == 8010
    assert client._runtime_root == (tmp_path / "app-home" / "runtime").resolve()
    assert client._launcher_root == (tmp_path / "app-home" / "launcher").resolve()


def test_daemon_client_auto_start_uses_module_launch_when_repo_root_is_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MISSION_CONTROL_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("MISSION_CONTROL_LAUNCHER_DIR", str(tmp_path / "launcher"))
    monkeypatch.setattr(MissionControlDaemonClient, "_discover_repo_root", lambda self: None)
    monkeypatch.setattr("mission_control_mcp_server.client.find_spec", lambda name: object() if name == "mission_control_daemon" else None)
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8123", timeout=0.2)
    attempts = {"count": 0}

    def fake_healthcheck() -> bool:
        attempts["count"] += 1
        return attempts["count"] > 1

    launches: list[list[str]] = []

    def fake_popen(args, **kwargs):
        launches.append(list(args))
        return object()

    monkeypatch.setattr(client, "_healthcheck", fake_healthcheck)
    monkeypatch.setattr(client, "_port_in_use", lambda: False)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    client.ensure_daemon_running()

    assert launches
    assert launches[0][0].endswith("python") or launches[0][0].endswith("python.exe")
    assert launches[0][1:] == ["-m", "mission_control_daemon"]


def test_daemon_client_reports_missing_backend_install(monkeypatch) -> None:
    monkeypatch.setattr(MissionControlDaemonClient, "_discover_repo_root", lambda self: None)
    monkeypatch.setattr("mission_control_mcp_server.client.find_spec", lambda _name: None)
    client = MissionControlDaemonClient(timeout=0.1)

    try:
        client._server_command()
    except RuntimeError as exc:
        assert "codex-mission-control-server" in str(exc)
    else:
        raise AssertionError("Expected packaged daemon launch to require an installed backend.")
