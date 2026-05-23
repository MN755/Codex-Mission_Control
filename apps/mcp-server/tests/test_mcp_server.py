from __future__ import annotations

import subprocess
from pathlib import Path

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
    "mission-control://projects/{project_id}/swarm-plan",
    "mission-control://projects/{project_id}/risk-register",
    "mission-control://projects/{project_id}/agent-contracts",
    "mission-control://projects/{project_id}/validation-summary",
    "mission-control://projects/{project_id}/decision-ledger",
    "mission-control://projects/{project_id}/path-locks",
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

    def get_orchestration_events(self, orchestration_id: int):
        self.calls.append(("get_orchestration_events", {"orchestration_id": orchestration_id}))
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

    def pause(self, orchestration_id: int):
        self.calls.append(("pause", {"orchestration_id": orchestration_id}))
        return {"id": orchestration_id, "status": "paused"}

    def resume(self, orchestration_id: int):
        self.calls.append(("resume", {"orchestration_id": orchestration_id}))
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
        {"decision_id": 9, "option_id": "approve_once", "selected_text": "Approve once"},
    )
    assert result["structuredContent"]["status"] == "answered"
    assert client.calls[0][0] == "answer_decision"


def test_new_runtime_tools_dispatch_to_client() -> None:
    client = FakeClient()
    server = MissionControlMcpServer(client=client)

    server.call_tool("mission_control_plugin_health", {})
    server.call_tool("mission_control_enable_safe_mode", {"project_id": 7})
    server.call_tool("mission_control_get_event_digest", {"project_id": 7, "window": "last_15_minutes"})
    server.call_tool("mission_control_request_snapshot", {"project_id": 7, "label": "Before edits", "description": "Checkpoint"})
    server.call_tool("mission_control_request_recovery_plan", {"project_id": 7, "trigger_summary": "Workers are stuck."})

    called = [name for name, _ in client.calls]
    assert "plugin_health_summary" in called
    assert "enable_safe_mode" in called
    assert "get_event_digest" in called
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
