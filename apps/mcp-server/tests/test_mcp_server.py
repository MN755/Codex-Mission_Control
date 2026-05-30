from __future__ import annotations

import importlib
import importlib.resources
import json
import subprocess
import sys
from pathlib import Path

from mission_control_mcp_server import catalog
from mission_control_mcp_server.client import MissionControlDaemonClient, _base_url
from mission_control_mcp_server.server import MissionControlMcpServer


EXPECTED_RESOURCES = {
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events",
    "mission-control://projects/{project_id}/status",
    "mission-control://projects/{project_id}/agents",
    "mission-control://projects/{project_id}/pending-decisions",
    "mission-control://projects/{project_id}/handoff",
    "mission-control://projects/{project_id}/codebase-map",
    "mission-control://projects/{project_id}/workspace-tooling",
    "mission-control://projects/{project_id}/diagnostics",
    "mission-control://projects/{project_id}/webwright",
    "mission-control://projects/{project_id}/nvidia-dynamo",
    "mission-control://projects/{project_id}/nvidia-nim",
    "mission-control://projects/{project_id}/nvidia-aiq",
    "mission-control://projects/{project_id}/nvidia-gpu-diagnostics",
    "mission-control://projects/{project_id}/nvidia-local-runtime",
    "mission-control://projects/{project_id}/nvidia-validation-plan",
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

    def get_workspace_tooling(self, project_id: int):
        self.calls.append(("get_workspace_tooling", {"project_id": project_id}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "workspace_path": "C:/demo",
            "available": True,
            "summary": "Detected 3 installed helper CLIs. validation evidence lane available.",
            "repo_profile": {"python_repo": True, "node_repo": False, "lockfiles": ["uv.lock"]},
            "packs": [{"id": "validation_evidence_pack", "status": "ready"}],
            "intake_commands": ["rg --files"],
            "validation_commands": ["uv run pytest", "ruff check ."],
            "security_commands": ["gitleaks dir . --redact"],
            "recommended_next_steps": ["Install OSV-Scanner for dependency auditing."],
            "tools": [{"id": "uv", "label": "uv", "installed": True, "configured": True, "status": "ready"}],
        }

    def search_codebase(self, project_id: int, **kwargs):
        self.calls.append(("search_codebase", {"project_id": project_id, **kwargs}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "workspace_path": "C:/demo",
            "pattern": kwargs["pattern"],
            "glob": kwargs.get("glob"),
            "match_count": 1,
            "truncated": False,
            "search_backend": "ripgrep",
            "command": "rg --line-number TODO .",
            "matches": [{"path": "src/main.py", "line_number": 3, "line_text": "TODO wire validation lane"}],
            "notes": ["Search used ripgrep."],
        }

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

    def get_nvidia_dynamo_status(self, project_id: int):
        self.calls.append(("get_nvidia_dynamo_status", {"project_id": project_id}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "provider": "nvidia_dynamo",
            "label": "NVIDIA Dynamo",
            "available": True,
            "reachable": True,
            "endpoint": "http://localhost:8000",
            "endpoint_configured": True,
            "api_key_configured": False,
            "auth_required": False,
            "authenticated": True,
            "available_models": ["Qwen/Qwen3-0.6B"],
            "summary": "NVIDIA Dynamo frontend is reachable.",
            "notes": ["Optional GPU-backed provider lane."],
        }

    def get_nvidia_nim_status(self, project_id: int):
        self.calls.append(("get_nvidia_nim_status", {"project_id": project_id}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "provider": "nvidia_nim",
            "label": "NVIDIA NIM",
            "available": True,
            "reachable": True,
            "endpoint": "https://integrate.api.nvidia.com",
            "endpoint_configured": True,
            "api_key_configured": True,
            "auth_required": True,
            "authenticated": True,
            "available_models": ["meta/llama-3.1-8b-instruct"],
            "runtime_ready": True,
            "runtime_status": "ready",
            "runtime_summary": "NVIDIA NIM and adapter runtime are ready.",
            "runtime_blockers": [],
            "summary": "NVIDIA NIM endpoint is reachable.",
            "notes": ["Optional GPU-backed provider lane."],
        }

    def get_nvidia_aiq_status(self, project_id: int):
        self.calls.append(("get_nvidia_aiq_status", {"project_id": project_id}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "install_status": "ready",
            "summary": "NVIDIA AI-Q endpoint is reachable.",
            "endpoint": "http://localhost:8000",
            "endpoint_configured": True,
            "api_key_configured": False,
            "auth_required": False,
            "dask_available": True,
            "agent_types": ["deep_researcher"],
            "data_sources": ["pubmed"],
            "recommended_fix": None,
            "notes": ["Async research lane is ready."],
        }

    def run_nvidia_aiq_research(self, project_id: int, **kwargs):
        self.calls.append(("run_nvidia_aiq_research", {"project_id": project_id, **kwargs}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "endpoint": "http://localhost:8000",
            "agent_type": kwargs.get("agent_type", "deep_researcher"),
            "job_id": "job-123",
            "status": "SUCCESS",
            "timed_out": False,
            "poll_count": 2,
            "summary": "AI-Q research completed.",
            "report": "Use a retrieval-backed plan.",
            "source_summary": {"found": 3, "cited": 2},
            "tool_count": 1,
            "tools": [{"name": "web-search", "status": "ok", "workflow": "research"}],
            "status_payload": {"status": "SUCCESS"},
        }

    def get_nvidia_gpu_diagnostics(self, project_id: int):
        self.calls.append(("get_nvidia_gpu_diagnostics", {"project_id": project_id}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "status": "ready",
            "summary": "GPU telemetry looks healthy.",
            "prometheus_url": "http://prometheus:9090",
            "metrics": {"average_gpu_util_percent": 42.0},
            "alerts": [],
            "recommended_fixes": [],
        }

    def get_nvidia_local_runtime_status(self, project_id: int):
        self.calls.append(("get_nvidia_local_runtime_status", {"project_id": project_id}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "status": "partial",
            "summary": "CUDA repo signals are present, but the local runtime still lacks profiler coverage.",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_cpp",
            "detected_tools": ["nvidia_smi", "nvcc"],
            "missing_required_tools": [],
            "missing_optional_tools": ["nsys", "ncu"],
            "gpu_names": ["NVIDIA RTX PRO 4500"],
            "driver_version": "555.42",
            "cuda_release": "13.3",
            "nsight_systems_available": False,
            "nsight_compute_available": False,
            "recommended_fixes": ["Install Nsight if you want profile evidence."],
            "validation_hints": ["cmake --build build --parallel"],
            "notes": ["Local runtime surface only."],
        }

    def get_nvidia_validation_plan(self, project_id: int):
        self.calls.append(("get_nvidia_validation_plan", {"project_id": project_id}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "status": "needs_review",
            "summary": "Validation path is usable but still missing profiler coverage.",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_cpp",
            "local_runtime_status": "partial",
            "gpu_diagnostics_status": "ready",
            "steps": [
                {
                    "title": "Verify local GPU visibility",
                    "command": "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader",
                    "type": "smoke",
                    "source": "local_runtime",
                    "status": "pending",
                }
            ],
            "blockers": [],
            "recommended_fixes": ["Install Nsight if you want profile evidence."],
            "evidence_targets": ["Capture build and benchmark results."],
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
    assert "mission_control_get_workspace_tooling" in names
    assert "mission_control_search_codebase" in names
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
    result = server.call_tool("mission_control_get_status", {"project_id": 7, "orchestration_id": 14})
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


def test_core_orchestration_tools_require_project_scope() -> None:
    server = MissionControlMcpServer(client=FakeClient())

    for tool_name in [
        "mission_control_get_status",
        "mission_control_get_pending_decisions",
        "mission_control_pause",
        "mission_control_resume",
        "mission_control_get_handoff",
        "mission_control_get_diagnostics",
        "mission_control_request_recovery_options",
    ]:
        try:
            server.call_tool(tool_name, {"orchestration_id": 14})
        except RuntimeError as exc:
            assert "project_id" in str(exc)
        else:
            raise AssertionError(f"Expected {tool_name} to require project scope.")


def test_new_runtime_tools_dispatch_to_client() -> None:
    client = FakeClient()
    server = MissionControlMcpServer(client=client)

    server.call_tool("mission_control_plugin_health", {})
    server.call_tool("mission_control_enable_safe_mode", {"project_id": 7})
    server.call_tool("mission_control_get_event_digest", {"project_id": 7, "window": "last_15_minutes"})
    server.call_tool("mission_control_get_workspace_tooling", {"project_id": 7})
    server.call_tool("mission_control_search_codebase", {"project_id": 7, "pattern": "TODO", "max_matches": 5})
    server.call_tool("mission_control_get_webwright_status", {"project_id": 7})
    server.call_tool("mission_control_get_nvidia_dynamo_status", {"project_id": 7})
    server.call_tool("mission_control_get_nvidia_nim_status", {"project_id": 7})
    server.call_tool("mission_control_get_nvidia_aiq_status", {"project_id": 7})
    server.call_tool("mission_control_run_nvidia_aiq_research", {"project_id": 7, "query": "Best CUDA testing loop?"})
    server.call_tool("mission_control_get_nvidia_gpu_diagnostics", {"project_id": 7})
    server.call_tool("mission_control_get_nvidia_local_runtime_status", {"project_id": 7})
    server.call_tool("mission_control_get_nvidia_validation_plan", {"project_id": 7})
    server.call_tool("mission_control_request_snapshot", {"project_id": 7, "label": "Before edits", "description": "Checkpoint"})
    server.call_tool("mission_control_request_recovery_plan", {"project_id": 7, "trigger_summary": "Workers are stuck."})

    called = [name for name, _ in client.calls]
    assert "plugin_health_summary" in called
    assert "enable_safe_mode" in called
    assert "get_event_digest" in called
    assert "get_workspace_tooling" in called
    assert "search_codebase" in called
    assert "get_webwright_status" in called
    assert "get_nvidia_dynamo_status" in called
    assert "get_nvidia_nim_status" in called
    assert "get_nvidia_aiq_status" in called
    assert "run_nvidia_aiq_research" in called
    assert "get_nvidia_gpu_diagnostics" in called
    assert "get_nvidia_local_runtime_status" in called
    assert "get_nvidia_validation_plan" in called
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
        "get_workspace_tooling",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "workspace_path": "C:/demo",
            "available": True,
            "summary": "Detected 3 installed helper CLIs. validation evidence lane available.",
            "repo_profile": {"python_repo": True, "lockfiles": ["uv.lock"]},
            "packs": [{"id": "validation_evidence_pack", "status": "ready"}],
            "intake_commands": ["rg --files"],
            "validation_commands": ["uv run pytest", "ruff check ."],
            "security_commands": ["gitleaks dir . --redact"],
            "recommended_next_steps": ["Install OSV-Scanner for dependency auditing."],
            "tools": [{"id": "uv", "label": "uv", "installed": True, "configured": True, "status": "ready"}],
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
    monkeypatch.setattr(
        client,
        "get_nvidia_dynamo_status",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "reachable": True,
            "endpoint": "http://localhost:8000",
            "endpoint_configured": True,
            "api_key_configured": False,
            "auth_required": False,
            "authenticated": True,
            "available_models": ["Qwen/Qwen3-0.6B"],
            "summary": "NVIDIA Dynamo frontend is reachable.",
            "notes": ["Optional GPU-backed provider lane."],
        },
    )
    monkeypatch.setattr(
        client,
        "get_nvidia_nim_status",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "reachable": True,
            "endpoint": "https://integrate.api.nvidia.com",
            "endpoint_configured": True,
            "api_key_configured": True,
            "auth_required": True,
            "authenticated": True,
            "available_models": ["meta/llama-3.1-8b-instruct"],
            "summary": "NVIDIA NIM is reachable.",
            "notes": ["Optional GPU-backed provider lane."],
        },
    )
    monkeypatch.setattr(
        client,
        "get_nvidia_aiq_status",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "install_status": "ready",
            "summary": "NVIDIA AI-Q endpoint is reachable.",
            "endpoint": "http://localhost:8000",
            "endpoint_configured": True,
            "api_key_configured": False,
            "auth_required": False,
            "dask_available": True,
            "agent_types": ["deep_researcher"],
            "data_sources": ["pubmed"],
            "recommended_fix": None,
            "notes": ["Async research lane is ready."],
        },
    )
    monkeypatch.setattr(
        client,
        "get_nvidia_gpu_diagnostics",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "status": "ready",
            "summary": "GPU telemetry looks healthy.",
            "prometheus_url": "http://prometheus:9090",
            "metrics": {"average_gpu_util_percent": 42.0},
            "alerts": [],
            "recommended_fixes": [],
        },
    )
    monkeypatch.setattr(
        client,
        "get_nvidia_local_runtime_status",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "status": "partial",
            "summary": "CUDA repo signals are present, but profiler tooling is still missing.",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_cpp",
            "detected_tools": ["nvidia_smi", "nvcc"],
            "missing_required_tools": [],
            "missing_optional_tools": ["nsys", "ncu"],
            "gpu_names": ["NVIDIA RTX PRO 4500"],
            "driver_version": "555.42",
            "cuda_release": "13.3",
            "recommended_fixes": ["Install Nsight if you want profile evidence."],
            "validation_hints": ["cmake --build build --parallel"],
            "notes": ["Local runtime surface only."],
        },
    )
    monkeypatch.setattr(
        client,
        "get_nvidia_validation_plan",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "available": True,
            "status": "needs_review",
            "summary": "Validation path is usable but still missing profiler coverage.",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_cpp",
            "local_runtime_status": "partial",
            "gpu_diagnostics_status": "ready",
            "steps": [{"title": "Verify local GPU visibility", "command": "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader", "type": "smoke", "source": "local_runtime", "status": "pending"}],
            "blockers": [],
            "recommended_fixes": ["Install Nsight if you want profile evidence."],
            "evidence_targets": ["Capture build and benchmark results."],
        },
    )

    snapshot = client.read_resource("mission-control://projects/7/operator-snapshot")
    instincts = client.read_resource("mission-control://projects/7/instincts")
    verification = client.read_resource("mission-control://projects/7/verification-brief")
    tooling = client.read_resource("mission-control://projects/7/workspace-tooling")
    webwright = client.read_resource("mission-control://projects/7/webwright")
    dynamo = client.read_resource("mission-control://projects/7/nvidia-dynamo")
    nim = client.read_resource("mission-control://projects/7/nvidia-nim")
    aiq = client.read_resource("mission-control://projects/7/nvidia-aiq")
    gpu = client.read_resource("mission-control://projects/7/nvidia-gpu-diagnostics")
    local_runtime = client.read_resource("mission-control://projects/7/nvidia-local-runtime")
    validation_plan = client.read_resource("mission-control://projects/7/nvidia-validation-plan")

    assert snapshot["project_name"] == "Demo"
    assert snapshot["recommended_next_action"] == "Run the named pytest lane."
    assert instincts["instincts"][0]["key"] == "ship-with-evidence"
    assert verification["readiness"] == "blocked"
    assert verification["required_checks"] == ["python -m pytest apps/server/tests/test_operator_surfaces.py -q"]
    assert tooling["validation_commands"] == ["uv run pytest", "ruff check ."]
    assert webwright["available"] is True
    assert webwright["launch_command"] == "webwright"
    assert dynamo["reachable"] is True
    assert nim["reachable"] is True
    assert aiq["install_status"] == "ready"
    assert gpu["status"] == "ready"
    assert local_runtime["repo_mode"] == "cuda_cpp"
    assert validation_plan["status"] == "needs_review"


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


def test_daemon_client_constructs_without_repo_checkout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MISSION_CONTROL_REPO_ROOT", raising=False)
    monkeypatch.setenv("MISSION_CONTROL_APP_HOME", str(tmp_path / "app-home"))
    monkeypatch.setattr(MissionControlDaemonClient, "_discover_repo_root", lambda self: None)

    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)

    assert client.repo_root is None
    assert client._runtime_root == (tmp_path / "app-home" / "runtime").resolve()
    assert client._launcher_root == (tmp_path / "app-home" / ".runtime" / "launcher").resolve()


def test_daemon_client_project_scoped_orchestration_resources_are_supported(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    monkeypatch.setattr(
        client,
        "get_status",
        lambda **kwargs: {"orchestration_id": kwargs["orchestration_id"], "project_id": kwargs["project_id"], "project_name": "Demo"},
    )
    monkeypatch.setattr(
        client,
        "get_orchestration_events",
        lambda orchestration_id, *, project_id=None: [{"event_type": "running", "orchestration_id": orchestration_id, "project_id": project_id}],
    )

    status = client.read_resource("mission-control://projects/7/orchestrations/14/status")
    events = client.read_resource("mission-control://projects/7/orchestrations/14/events")

    assert status["project_id"] == 7
    assert events["event_count"] == 1


def test_daemon_client_bare_orchestration_resource_reads_raise_guidance() -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)

    try:
        client.read_resource("mission-control://orchestrations/14/status")
    except RuntimeError as exc:
        assert "project-scoped URI" in str(exc)
    else:
        raise AssertionError("Expected bare orchestration status resource to be rejected.")

    try:
        client.read_resource("mission-control://orchestrations/14/events")
    except RuntimeError as exc:
        assert "project-scoped URI" in str(exc)
    else:
        raise AssertionError("Expected bare orchestration events resource to be rejected.")


def test_daemon_client_project_status_read_passes_project_scope(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    seen: dict[str, int] = {}
    monkeypatch.setattr(client, "get_project", lambda project_id: {"id": project_id, "name": "Demo", "status": "active"})
    monkeypatch.setattr(client, "_maybe_orchestration_id", lambda **kwargs: 14)

    def fake_get_status(**kwargs):
        seen["project_id"] = kwargs["project_id"]
        seen["orchestration_id"] = kwargs["orchestration_id"]
        return {"project_id": kwargs["project_id"], "orchestration_id": kwargs["orchestration_id"]}

    monkeypatch.setattr(client, "get_status", fake_get_status)

    client.read_resource("mission-control://projects/7/status")

    assert seen == {"project_id": 7, "orchestration_id": 14}


def test_daemon_client_bridge_auth_protected_reads_include_token(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    calls: list[tuple[str, str, bool]] = []

    def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, bool(kwargs.get("requires_token", True))))
        return {}

    monkeypatch.setattr(client, "_request", fake_request)

    client.daemon_status()
    client.get_project_handoff(7)
    client.get_codebase_map(7)
    client.get_codebase_understanding(7)

    assert calls == [
        ("GET", "/api/daemon/status", True),
        ("GET", "/api/projects/7/handoff", True),
        ("GET", "/api/projects/7/codebase-map", True),
        ("GET", "/api/projects/7/codebase-understanding", True),
    ]


def test_catalog_uses_bundled_assets_when_repo_is_unavailable(monkeypatch) -> None:
    catalog.load_plugin_manifest.cache_clear()
    catalog.load_resource_catalog.cache_clear()
    catalog.load_prompt_catalog.cache_clear()
    monkeypatch.setattr(catalog, "discover_repo_root", lambda: (_ for _ in ()).throw(RuntimeError("no repo")))

    resources = catalog.resource_entries()
    prompts = catalog.prompt_entries()
    manifest = catalog.load_plugin_manifest()

    assert any(entry["uri_template"] == "mission-control://projects/{project_id}/diagnostics" for entry in resources)
    assert any(entry["name"] == "continue_orchestration" for entry in prompts)
    assert manifest["name"] == "mission-control"


def test_bundled_plugin_manifest_references_existing_assets() -> None:
    package_files = importlib.resources.files("mission_control_mcp_server._bundled")
    manifest = json.loads((package_files / "plugin.json").read_text(encoding="utf-8"))
    expected_files = [
        manifest["mcp"]["example_config"].removeprefix("./"),
        manifest["mcp"]["resources_catalog"].removeprefix("./"),
        manifest["mcp"]["prompts_catalog"].removeprefix("./"),
        manifest["claude_code"]["manifest"].removeprefix("./"),
        manifest["assets"]["icon"].removeprefix("./"),
    ]
    expected_dirs = [
        manifest["mcp"]["chat_templates_dir"].removeprefix("./"),
        manifest["claude_code"]["commands"].removeprefix("./").rstrip("/"),
        manifest["claude_code"]["agents"].removeprefix("./").rstrip("/"),
    ]

    for relative_path in expected_files:
        assert (package_files / relative_path).is_file(), f"Missing bundled file: {relative_path}"
    for relative_path in expected_dirs:
        assert (package_files / relative_path).is_dir(), f"Missing bundled directory: {relative_path}"


def test_daemon_client_launches_installed_module_when_repo_script_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MISSION_CONTROL_REPO_ROOT", raising=False)
    monkeypatch.setenv("MISSION_CONTROL_APP_HOME", str(tmp_path / "app-home"))
    monkeypatch.setattr(MissionControlDaemonClient, "_discover_repo_root", lambda self: None)
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8124", timeout=0.2)
    attempts = {"count": 0}

    def fake_healthcheck() -> bool:
        attempts["count"] += 1
        return attempts["count"] > 1

    launches: list[list[str]] = []

    def fake_popen(args, **kwargs):
        launches.append(list(args))
        return object()

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, package=None):
        if name == "mission_control_daemon":
            return object()
        return original_find_spec(name, package)

    monkeypatch.setattr(client, "_healthcheck", fake_healthcheck)
    monkeypatch.setattr(client, "_port_in_use", lambda: False)
    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    client.ensure_daemon_running()

    assert launches
    assert launches[0][:3] == [sys.executable, "-m", "mission_control_daemon"]
