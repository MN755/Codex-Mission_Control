from __future__ import annotations

import importlib
import importlib.resources
import json
import subprocess
import sys
from pathlib import Path

MCP_SERVER_SRC = Path(__file__).resolve().parents[1] / "src"
if str(MCP_SERVER_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_SRC))

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
    "mission-control://projects/{project_id}/handoff/evidence",
    "mission-control://projects/{project_id}/handoff/evidence/preview",
    "mission-control://projects/{project_id}/codebase-map",
    "mission-control://integrations/catalog",
    "mission-control://integrations/connections",
    "mission-control://integrations/health",
    "mission-control://profile/summary",
    "mission-control://subagent-policy/summary",
    "mission-control://projects/{project_id}/integrations",
    "mission-control://projects/{project_id}/integrations/{family}",
    "mission-control://projects/{project_id}/runbook",
    "mission-control://projects/{project_id}/runbook/summary",
    "mission-control://projects/{project_id}/recovery-plans",
    "mission-control://projects/{project_id}/recovery-plans/preview",
    "mission-control://projects/{project_id}/snapshots",
    "mission-control://projects/{project_id}/snapshots/{snapshot_id}/restore-plan",
    "mission-control://projects/{project_id}/playbook",
    "mission-control://projects/{project_id}/playbook/recommendations",
    "mission-control://projects/{project_id}/workspace-tooling",
    "mission-control://projects/{project_id}/execution-policy/summary",
    "mission-control://projects/{project_id}/coordination/summary",
    "mission-control://projects/{project_id}/tensorflow/features",
    "mission-control://projects/{project_id}/tensorflow/features/{feature_id}",
    "mission-control://projects/{project_id}/pytorch/features",
    "mission-control://projects/{project_id}/pytorch/features/{feature_id}",
    "mission-control://projects/{project_id}/spatial/features",
    "mission-control://projects/{project_id}/spatial/features/{feature_id}",
    "mission-control://projects/{project_id}/diagnostics",
    "mission-control://projects/{project_id}/webwright",
    "mission-control://projects/{project_id}/nvidia-dynamo",
    "mission-control://projects/{project_id}/nvidia-nim",
    "mission-control://projects/{project_id}/nvidia-aiq",
    "mission-control://projects/{project_id}/nvidia-gpu-diagnostics",
    "mission-control://projects/{project_id}/nvidia-local-runtime",
    "mission-control://projects/{project_id}/nvidia-validation-plan",
    "mission-control://projects/{project_id}/swarm-plan",
    "mission-control://projects/{project_id}/swarm/simulations/latest",
    "mission-control://projects/{project_id}/risk-register",
    "mission-control://projects/{project_id}/agent-contracts",
    "mission-control://projects/{project_id}/validation-summary",
    "mission-control://projects/{project_id}/decision-ledger",
    "mission-control://projects/{project_id}/path-locks",
    "mission-control://projects/{project_id}/operator-snapshot",
    "mission-control://projects/{project_id}/instincts",
    "mission-control://projects/{project_id}/verification-brief",
    "mission-control://projects/{project_id}/capability-report",
    "mission-control://projects/{project_id}/capability-report/{section_key}",
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
    "review_project_capabilities",
    "ask_manager_for_plan",
    "review_project_capability_section",
    "review_integration_catalog",
    "import_host_integrations",
    "review_project_integrations",
    "review_project_integration_family",
    "review_tensorflow_feature_catalog",
    "review_tensorflow_feature_bundle",
    "review_pytorch_feature_catalog",
    "review_pytorch_feature_bundle",
    "review_spatial_feature_catalog",
    "review_spatial_feature_bundle",
}


def test_daemon_client_brackets_ipv6_loopback_urls() -> None:
    assert _base_url("::1", 8010) == "http://[::1]:8010"


def test_handoff_summary_infers_ready_from_status() -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)

    not_ready = client._summarize_handoff(
        7,
        {"status": "not_ready", "handoff": {"project_name": "Demo", "summary": "Still cooking."}},
    )
    review_ready = client._summarize_handoff(
        7,
        {"status": "needs_review", "handoff": {"project_name": "Demo", "summary": "Ready for review."}},
    )

    assert not_ready["ready"] is False
    assert review_ready["ready"] is True


def test_project_diagnostics_requests_project_scoped_report_history(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    requested_paths: list[str] = []

    monkeypatch.setattr(client, "plugin_health", lambda: {"status": "healthy", "checks": []})
    monkeypatch.setattr(
        client,
        "_request",
        lambda method, path, **kwargs: requested_paths.append(path) or [],
    )
    monkeypatch.setattr(client, "get_status", lambda **kwargs: {"manager_status": "idle", "orchestration_status": "idle"})

    payload = client.get_diagnostics(project_id=7)

    assert payload["recent_reports"] == []
    assert "/api/diagnostics/reports?project_id=7" in requested_paths


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

    def get_integrations_catalog(self):
        self.calls.append(("get_integrations_catalog", {}))
        return [{"family": "source_control", "name": "GitHub / GitLab / Bitbucket", "status": "connected"}]

    def get_integration_connections(self):
        self.calls.append(("get_integration_connections", {}))
        return [{"family": "source_control", "status": "connected", "host_imported": True}]

    def get_integration_health(self):
        self.calls.append(("get_integration_health", {}))
        return {"family_count": 30, "connection_count": 1, "status_counts": {"connected": 1}}

    def import_host_integrations(self):
        self.calls.append(("import_host_integrations", {}))
        return {"status": "completed", "connections": [{"family": "source_control"}]}

    def get_project_integrations(self, project_id: int):
        self.calls.append(("get_project_integrations", {"project_id": project_id}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "workspace_path": "C:/demo",
            "summary": "1 ready family.",
            "families": [{"family": "source_control", "status": "ready", "available_actions": []}],
        }

    def get_project_integration_family(self, project_id: int, family: str):
        self.calls.append(("get_project_integration_family", {"project_id": project_id, "family": family}))
        return {
            "family": family,
            "name": "GitHub / GitLab / Bitbucket",
            "summary": "Repo host lane.",
            "category": "delivery",
            "project_name": "Demo",
            "workspace_path": "C:/demo",
            "status": "ready",
            "connection_source": "codex_host",
            "host_imported": True,
            "providers": ["github"],
            "required_permissions": ["ask_every_time"],
            "health": {"cli_detected": ["gh"]},
            "artifacts": [],
            "safe_commands": ["gh repo view --json name,defaultBranchRef"],
            "blockers": [],
            "recommended_fixes": [],
            "available_actions": [],
            "notes": [],
        }

    def preview_project_integration_action(self, project_id: int, family: str, action_id: str, *, params: dict[str, object] | None = None):
        self.calls.append(("preview_project_integration_action", {"project_id": project_id, "family": family, "action_id": action_id, "params": params or {}}))
        return {
            "family": family,
            "action_id": action_id,
            "title": "Create issue",
            "summary": "Create a work item.",
            "project_name": "Demo",
            "workspace_path": "C:/demo",
            "command": 'gh issue create --title "Demo" --body "Body"',
            "risk_level": "medium",
            "permission_policy": "ask_every_time",
            "preview_supported": True,
            "mutates_remote_state": True,
            "requires_confirmation": True,
            "missing_params": [],
            "notes": [],
        }

    def execute_project_integration_action(self, project_id: int, family: str, action_id: str, *, params: dict[str, object] | None = None, confirmed: bool = False):
        self.calls.append(("execute_project_integration_action", {"project_id": project_id, "family": family, "action_id": action_id, "params": params or {}, "confirmed": confirmed}))
        return {
            "family": family,
            "action_id": action_id,
            "title": "Create issue",
            "summary": "Create a work item.",
            "project_name": "Demo",
            "workspace_path": "C:/demo",
            "command": 'gh issue create --title "Demo" --body "Body"',
            "risk_level": "medium",
            "permission_policy": "ask_every_time",
            "preview_supported": True,
            "mutates_remote_state": True,
            "requires_confirmation": True,
            "missing_params": [],
            "notes": [],
            "status": "approval_required" if not confirmed else "completed",
            "stdout": "",
            "stderr": "",
            "returncode": None if not confirmed else 0,
            "approval_required": not confirmed,
            "updated_registry": {},
        }

    def get_tensorflow_feature_catalog(self, project_id: int):
        self.calls.append(("get_tensorflow_feature_catalog", {"project_id": project_id}))
        return [
            {
                "feature_id": "keras_scaffold",
                "title": "Keras scaffold",
                "summary": "Starter lane for structured TensorFlow product code.",
                "variants": ["classification", "time_series"],
                "keywords": ["keras", "tensorflow", "training"],
            }
        ]

    def get_tensorflow_feature_bundle(self, project_id: int, feature_id: str, *, variant: str | None = None):
        self.calls.append(("get_tensorflow_feature_bundle", {"project_id": project_id, "feature_id": feature_id, "variant": variant}))
        return {
            "feature_id": feature_id,
            "variant": variant or "classification",
            "summary": "Starter lane for structured TensorFlow product code.",
            "files": {"tensorflow_starters/model.py": "class Model", "tensorflow_starters/train.py": "artifacts/final.keras"},
            "validation_steps": ["python -m pytest"],
            "dependencies": ["tensorflow", "keras"],
            "evidence_targets": ["training logs", "saved model"],
        }

    def get_pytorch_feature_catalog(self, project_id: int):
        self.calls.append(("get_pytorch_feature_catalog", {"project_id": project_id}))
        return [
            {
                "feature_id": "project_scaffold",
                "title": "PyTorch scaffold",
                "summary": "Starter lane for structured PyTorch training code.",
                "variants": ["classification", "nlp"],
                "keywords": ["pytorch", "training", "export"],
            }
        ]

    def get_pytorch_feature_bundle(self, project_id: int, feature_id: str, *, variant: str | None = None):
        self.calls.append(("get_pytorch_feature_bundle", {"project_id": project_id, "feature_id": feature_id, "variant": variant}))
        return {
            "feature_id": feature_id,
            "variant": variant or "classification",
            "summary": "Starter lane for structured PyTorch training code.",
            "files": {"pytorch_starters/model.py": "class Model", "pytorch_starters/train.py": "artifacts/checkpoint.pt"},
            "validation_steps": ["python -m pytest"],
            "dependencies": ["torch", "torchvision"],
            "evidence_targets": ["checkpoint", "eval metrics"],
        }

    def get_spatial_feature_catalog(self, project_id: int):
        self.calls.append(("get_spatial_feature_catalog", {"project_id": project_id}))
        return [
            {
                "id": "asset_pipeline",
                "title": "Spatial asset pipeline",
                "summary": "Starter lane for ingest, conversion, validation, and publishing.",
                "category": "pipeline",
                "variants": ["default"],
                "keywords": ["spatial", "assets", "pipeline"],
            },
            {
                "id": "visual_regression_3d",
                "title": "3D visual regression",
                "summary": "Render diff and evidence capture workflow.",
                "category": "validation",
                "variants": ["default"],
                "keywords": ["render", "diff", "validation"],
            },
        ]

    def get_spatial_feature_bundle(self, project_id: int, feature_id: str, *, variant: str | None = None):
        self.calls.append(("get_spatial_feature_bundle", {"project_id": project_id, "feature_id": feature_id, "variant": variant}))
        return {
            "feature_id": feature_id,
            "variant": variant or "default",
            "title": "Spatial asset pipeline",
            "summary": "Starter lane for ingest, conversion, validation, and publishing.",
            "dependencies": ["blender", "usd-core"],
            "starter_files": ["pipelines/asset_pipeline.py", "configs/asset_pipeline.yaml"],
            "validation_steps": [{"title": "Render probe", "command": "python scripts/render_probe.py"}],
            "evidence_targets": ["Rendered preview", "conversion logs"],
            "notes": ["Block if Blender is missing."],
        }

    def get_capability_report(self, project_id: int):
        self.calls.append(("get_capability_report", {"project_id": project_id}))
        return {
            "project_id": project_id,
            "project_name": "Demo",
            "section_count": 2,
            "sections": [
                {"key": "issue_to_execution_profiles", "title": "Issue-to-execution profiles", "status": "ready", "summary": "Profiles exist."},
                {"key": "release_readiness_mode", "title": "Release readiness mode", "status": "needs_review", "summary": "One blocker remains."},
            ],
            "report_markdown": "## Mission Control Capability Report\n",
        }

    def get_capability_section(self, project_id: int, section_key: str):
        self.calls.append(("get_capability_section", {"project_id": project_id, "section_key": section_key}))
        return {
            "key": section_key,
            "title": "Semantic code impact mapping",
            "status": "ready",
            "summary": "Parser-backed dependency mapping is active.",
            "details": ["src/worker.py -> tests/test_worker.py"],
            "commands": ["python -m pytest apps/server/tests/test_capability_report.py -q"],
            "artifacts": [],
            "metadata_json": {"semantic_backend": "python-ast-graph"},
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
    assert "mission_control_get_capability_report" in names
    assert "mission_control_get_workspace_tooling" in names
    assert "mission_control_get_tensorflow_feature_catalog" in names
    assert "mission_control_get_tensorflow_feature_bundle" in names
    assert "mission_control_get_pytorch_feature_catalog" in names
    assert "mission_control_get_pytorch_feature_bundle" in names
    assert "mission_control_get_spatial_feature_catalog" in names
    assert "mission_control_get_spatial_feature_bundle" in names
    assert "mission_control_get_capability_section" in names
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
    server.call_tool("mission_control_get_capability_report", {"project_id": 7})
    server.call_tool("mission_control_get_workspace_tooling", {"project_id": 7})
    server.call_tool("mission_control_get_tensorflow_feature_catalog", {"project_id": 7})
    server.call_tool("mission_control_get_tensorflow_feature_bundle", {"project_id": 7, "feature_id": "keras_scaffold"})
    server.call_tool("mission_control_get_pytorch_feature_catalog", {"project_id": 7})
    server.call_tool("mission_control_get_pytorch_feature_bundle", {"project_id": 7, "feature_id": "project_scaffold"})
    server.call_tool("mission_control_get_spatial_feature_catalog", {"project_id": 7})
    server.call_tool("mission_control_get_spatial_feature_bundle", {"project_id": 7, "feature_id": "asset_pipeline"})
    server.call_tool("mission_control_get_capability_section", {"project_id": 7, "section_key": "semantic_code_impact_mapping"})
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
    assert "get_capability_report" in called
    assert "get_workspace_tooling" in called
    assert "get_tensorflow_feature_catalog" in called
    assert "get_tensorflow_feature_bundle" in called
    assert "get_pytorch_feature_catalog" in called
    assert "get_pytorch_feature_bundle" in called
    assert "get_spatial_feature_catalog" in called
    assert "get_spatial_feature_bundle" in called
    assert "get_capability_section" in called
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
        "get_capability_report",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "section_count": 2,
            "sections": [
                {"key": "issue_to_execution_profiles", "title": "Issue-to-execution profiles", "status": "ready", "summary": "Profiles exist."},
                {"key": "release_readiness_mode", "title": "Release readiness mode", "status": "needs_review", "summary": "One blocker remains."},
            ],
            "report_markdown": "## Mission Control Capability Report\n",
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
        "get_profile_summary",
        lambda: {
            "id": 1,
            "exists": True,
            "display_name": "Mike",
            "selected_provider": "codex",
            "first_run_completed": True,
            "onboarding_completed": True,
            "startup_behavior": "dashboard",
            "default_runner_mode": "auto",
            "sandbox_mode": "workspace-write",
            "approval_policy": "on-request",
            "connected_account_count": 2,
            "dashboard_widget_count": 4,
            "enabled_notification_count": 3,
            "has_provider_endpoint": False,
            "has_adapter": True,
            "updated_at": "2026-06-03T12:40:00Z",
            "last_opened_at": "2026-06-03T12:45:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_subagent_policy_summary",
        lambda: {
            "enabled": True,
            "default_mode": "limited_write",
            "sandbox_mode": "workspace-write",
            "max_subagents_per_burst": 4,
            "max_runtime_seconds": 1800,
            "allow_file_edits": True,
            "allow_commands": True,
            "require_user_approval_above_count": 2,
            "allowed_task_types_json": ["review", "planning", "failure_diagnosis"],
            "default_spawn_method": "codex_chat_bridge",
            "writes_allowed": True,
            "read_only_default": False,
            "command_capable": True,
        },
    )
    monkeypatch.setattr(
        client,
        "get_handoff_evidence",
        lambda project_id: [
            {
                "id": 41,
                "project_id": project_id,
                "evidence_type": "test_result",
                "claim": "pytest suite passed",
                "summary": "Named pytest slice completed cleanly.",
                "source_path": "apps/server/tests/test_api_smoke.py",
                "command": "python -m pytest apps/server/tests/test_api_smoke.py -q",
                "status": "passed",
                "created_at": "2026-06-03T13:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_handoff_evidence_preview",
        lambda project_id: {
            "project_id": project_id,
            "persisted": [],
            "derived_candidates": [
                {"evidence_type": "test_result", "claim": "pytest slice", "summary": "Derived from agent report.", "status": "pending"}
            ],
            "stored_count": 0,
            "derived_candidate_count": 1,
            "generated_at": "2026-06-03T13:05:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_runbook",
        lambda project_id: {
            "id": 12,
            "project_id": project_id,
            "content_markdown": "# Runbook\n\n## Run\n- python -m pytest\n",
            "generated_from_handoff_id": 3,
            "generated_at": "2026-06-03T12:00:00Z",
            "updated_at": "2026-06-03T12:30:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_runbook_summary",
        lambda project_id: {
            "project_id": project_id,
            "exists": True,
            "section_count": 2,
            "sections": ["Run", "Validate"],
            "run_command_count": 1,
            "run_commands": ["python -m pytest"],
            "content_preview": "Run and validate the project.",
            "generated_from_handoff_id": 3,
            "generated_at": "2026-06-03T12:00:00Z",
            "updated_at": "2026-06-03T12:30:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_recovery_plans",
        lambda project_id: [
            {
                "id": 55,
                "project_id": project_id,
                "trigger_type": "blocked_task",
                "trigger_summary": "Validation gate is blocked.",
                "status": "proposed",
                "selected_action": "rerun_validation",
                "suggested_actions_json": ["rerun_validation", "request_help"],
                "created_at": "2026-06-03T13:10:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_recovery_plans_preview",
        lambda project_id: {
            "project_id": project_id,
            "current_action": "Investigate blocked validation lane.",
            "blocked_task_count": 1,
            "stuck_signal_count": 1,
            "persisted_statuses": ["proposed"],
            "persisted_status_counts": {"proposed": 1},
            "persisted_status_group_count": 1,
            "persisted": [],
            "derived_trigger_types": ["blocked_task"],
            "derived_trigger_type_counts": {"blocked_task": 1},
            "derived_trigger_type_group_count": 1,
            "suggested_action_count": 2,
            "suggested_action_values": ["rerun_validation", "request_help"],
            "suggested_action_counts": {"rerun_validation": 1, "request_help": 1},
            "suggested_action_group_count": 2,
            "derived_candidates": [
                {"trigger_type": "blocked_task", "trigger_summary": "Validation gate is blocked.", "suggested_actions_json": ["rerun_validation", "request_help"]}
            ],
            "stored_count": 0,
            "derived_candidate_count": 1,
            "generated_at": "2026-06-03T13:15:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "list_snapshots",
        lambda project_id: [
            {
                "id": 61,
                "project_id": project_id,
                "snapshot_type": "git_commit",
                "label": "Before risky migration",
                "description": "Checkpoint before changing task routing.",
                "status": "available",
                "git_ref": "abc1234",
                "created_at": "2026-06-03T13:20:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_snapshot_restore_plan",
        lambda project_id, snapshot_id: {
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "status": "available",
            "restore_type": "git_commit",
            "git_ref": "abc1234",
            "warnings": ["Working tree was dirty when this snapshot was recorded."],
            "steps": [
                "Inspect diff against snapshot: git diff abc1234..HEAD",
                "Only after approval, consider checking out or branching from abc1234.",
            ],
        },
    )
    monkeypatch.setattr(
        client,
        "get_playbook",
        lambda project_id: {
            "project_id": project_id,
            "playbook_key": "existing_repo_fix",
            "status": "active",
            "why": "The repo already has structure and failing tests.",
            "playbook": {
                "id": 9,
                "key": "existing_repo_fix",
                "name": "Existing Repo Fix",
                "description": "Repair an existing codebase with targeted validation.",
                "suggested_interview_categories_json": ["product goal", "testing/validation"],
                "suggested_swarm_mode": "balanced",
                "suggested_agent_archetypes_json": ["code-reviewer", "test-engineer"],
                "suggested_validation_recipe_json": [{"type": "pytest", "command": "python -m pytest"}],
                "common_risks_json": ["regression drift"],
                "suggested_docs_json": ["runbook"],
                "typical_structure_json": ["apps/server", "tests"],
                "created_at": "2026-06-03T11:00:00Z",
                "updated_at": "2026-06-03T11:30:00Z",
            },
        },
    )
    monkeypatch.setattr(
        client,
        "get_playbook_recommendations",
        lambda project_id: [
            {
                "playbook_key": "existing_repo_fix",
                "score": 95,
                "why": "Matches a repo with existing tests and repair work.",
                "is_current": True,
                "status": "active",
                "playbook": {
                    "id": 9,
                    "key": "existing_repo_fix",
                    "name": "Existing Repo Fix",
                    "description": "Repair an existing codebase with targeted validation.",
                    "suggested_interview_categories_json": ["product goal", "testing/validation"],
                    "suggested_swarm_mode": "balanced",
                    "suggested_agent_archetypes_json": ["code-reviewer", "test-engineer"],
                    "suggested_validation_recipe_json": [{"type": "pytest", "command": "python -m pytest"}],
                    "common_risks_json": ["regression drift"],
                    "suggested_docs_json": ["runbook"],
                    "typical_structure_json": ["apps/server", "tests"],
                    "created_at": "2026-06-03T11:00:00Z",
                    "updated_at": "2026-06-03T11:30:00Z",
                },
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_agent_contracts",
        lambda project_id: [
            {
                "id": 21,
                "project_id": project_id,
                "agent_id": "reviewer-1",
                "agent_name": "Reviewer",
                "archetype": "review",
                "mission": "Review the backend hardening patch.",
                "allowed_paths_json": ["apps/server/src", "apps/server/tests"],
                "forbidden_paths_json": ["apps/dashboard"],
                "allowed_tools_json": ["rg", "pytest"],
                "expected_output": "Risk-focused review notes.",
                "validation_required_json": ["python -m pytest apps/server/tests/test_api_smoke.py -q"],
                "stop_conditions_json": ["Stop if branch protection blocks push."],
                "escalation_conditions_json": ["Escalate if write scope must widen."],
                "completion_report_schema_json": {"sections": ["findings", "validation"]},
                "status": "active",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_decision_ledger",
        lambda project_id: [
            {
                "id": 9,
                "project_id": project_id,
                "decision_type": "approval",
                "title": "Keep direct pushes temporary",
                "decision": "Continue direct pushes until branch protection is fixed.",
                "reason": "Required build check is still bypassed on main.",
                "made_by": "operator",
                "impact_area_json": ["release", "governance"],
                "related_task_id": "release-hardening",
                "related_agent_id": "manager",
                "reversible": True,
                "superseded_by": None,
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_execution_policy_summary",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "provider": "codex",
            "runner_mode": "auto",
            "sandbox_mode": "workspace-write",
            "approval_policy": "on-request",
            "model_policy_name": "default",
            "manager_model": "gpt-5-codex",
            "worker_model_count": 2,
            "tool_routing_count": 1,
            "approval_required_tool_count": 1,
            "approval_required_tools": ["git push"],
            "blocked_tool_count": 1,
            "blocked_tools": ["rm -rf"],
            "sandbox_profile_count": 1,
            "default_sandbox_profile": "workspace-write",
            "current_sandbox_profile": "workspace-write",
            "validation_step_count": 2,
            "validation_command_count": 1,
            "validation_commands": ["python -m pytest"],
            "validation_status": "ready",
        },
    )
    monkeypatch.setattr(
        client,
        "get_coordination_summary",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "current_action_type": "manager_question",
            "contract_count": 3,
            "active_contract_count": 2,
            "waiting_lock_count": 1,
            "active_lock_count": 1,
            "unresolved_conflict_count": 0,
            "decision_count": 4,
            "decision_types": ["scope_change", "approval"],
            "low_confidence_count": 1,
            "low_confidence_categories": ["validation"],
            "failed_gate_count": 0,
            "pending_gate_count": 1,
            "review_gate_count": 2,
        },
    )
    monkeypatch.setattr(
        client,
        "get_latest_swarm_simulation",
        lambda project_id: {
            "simulation_id": 17,
            "project_id": project_id,
            "swarm_plan_id": 5,
            "safe_to_launch_count": 2,
            "should_wait_count": 1,
            "needs_user_approval_count": 1,
            "conflict_warnings_json": ["tests/ and apps/server overlap"],
            "bottlenecks_json": ["validation gate pending"],
            "recommended_launch_order_json": [{"agent_name": "reviewer", "order": 1}],
            "created_at": "2026-06-03T12:55:00Z",
            "persisted": False,
            "stale": False,
        },
    )
    monkeypatch.setattr(
        client,
        "get_tensorflow_feature_catalog",
        lambda project_id: [
            {
                "feature_id": "keras_scaffold",
                "title": "Keras scaffold",
                "summary": "Starter lane for structured TensorFlow product code.",
                "variants": ["classification", "time_series"],
                "keywords": ["keras", "tensorflow", "training"],
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_tensorflow_feature_bundle",
        lambda project_id, feature_id, variant=None: {
            "feature_id": feature_id,
            "variant": variant or "classification",
            "summary": "Starter lane for structured TensorFlow product code.",
            "files": {"tensorflow_starters/model.py": "class Model", "tensorflow_starters/train.py": "artifacts/final.keras"},
            "validation_steps": ["python -m pytest"],
            "dependencies": ["tensorflow", "keras"],
            "evidence_targets": ["training logs", "saved model"],
        },
    )
    monkeypatch.setattr(
        client,
        "get_pytorch_feature_catalog",
        lambda project_id: [
            {
                "feature_id": "project_scaffold",
                "title": "PyTorch scaffold",
                "summary": "Starter lane for structured PyTorch training code.",
                "variants": ["classification", "nlp"],
                "keywords": ["pytorch", "training", "export"],
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_pytorch_feature_bundle",
        lambda project_id, feature_id, variant=None: {
            "feature_id": feature_id,
            "variant": variant or "classification",
            "summary": "Starter lane for structured PyTorch training code.",
            "files": {"pytorch_starters/model.py": "class Model", "pytorch_starters/train.py": "artifacts/checkpoint.pt"},
            "validation_steps": ["python -m pytest"],
            "dependencies": ["torch", "torchvision"],
            "evidence_targets": ["checkpoint", "eval metrics"],
        },
    )
    monkeypatch.setattr(
        client,
        "get_spatial_feature_catalog",
        lambda project_id: [
            {
                "id": "asset_pipeline",
                "title": "Spatial asset pipeline",
                "summary": "Starter lane for ingest, conversion, validation, and publishing.",
                "category": "pipeline",
                "variants": ["default"],
                "keywords": ["spatial", "assets", "pipeline"],
            },
            {
                "id": "visual_regression_3d",
                "title": "3D visual regression",
                "summary": "Render diff and evidence capture workflow.",
                "category": "validation",
                "variants": ["default"],
                "keywords": ["render", "diff", "validation"],
            },
        ],
    )
    monkeypatch.setattr(
        client,
        "get_spatial_feature_bundle",
        lambda project_id, feature_id, variant=None: {
            "feature_id": feature_id,
            "variant": variant or "default",
            "title": "Spatial asset pipeline",
            "summary": "Starter lane for ingest, conversion, validation, and publishing.",
            "dependencies": ["blender", "usd-core"],
            "starter_files": ["pipelines/asset_pipeline.py", "configs/asset_pipeline.yaml"],
            "validation_steps": [{"title": "Render probe", "command": "python scripts/render_probe.py"}],
            "evidence_targets": ["Rendered preview", "conversion logs"],
            "notes": ["Block if Blender is missing."],
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
    monkeypatch.setattr(
        client,
        "get_capability_section",
        lambda project_id, section_key: {
            "key": section_key,
            "title": "Semantic code impact mapping",
            "status": "ready",
            "summary": "Parser-backed dependency mapping is active.",
            "details": ["src/worker.py -> tests/test_worker.py"],
            "commands": ["tree-sitter parse src/worker.py"],
            "artifacts": [],
            "metadata_json": {"semantic_backend": "python-ast-graph"},
        },
    )

    profile_summary = client.read_resource("mission-control://profile/summary")
    subagent_policy_summary = client.read_resource("mission-control://subagent-policy/summary")
    snapshot = client.read_resource("mission-control://projects/7/operator-snapshot")
    instincts = client.read_resource("mission-control://projects/7/instincts")
    verification = client.read_resource("mission-control://projects/7/verification-brief")
    capability_report = client.read_resource("mission-control://projects/7/capability-report")
    capability_section = client.read_resource("mission-control://projects/7/capability-report/semantic_code_impact_mapping")
    handoff_evidence = client.read_resource("mission-control://projects/7/handoff/evidence")
    handoff_evidence_preview = client.read_resource("mission-control://projects/7/handoff/evidence/preview")
    tooling = client.read_resource("mission-control://projects/7/workspace-tooling")
    runbook = client.read_resource("mission-control://projects/7/runbook")
    runbook_summary = client.read_resource("mission-control://projects/7/runbook/summary")
    recovery_plans = client.read_resource("mission-control://projects/7/recovery-plans")
    recovery_plans_preview = client.read_resource("mission-control://projects/7/recovery-plans/preview")
    snapshots = client.read_resource("mission-control://projects/7/snapshots")
    restore_plan = client.read_resource("mission-control://projects/7/snapshots/61/restore-plan")
    playbook = client.read_resource("mission-control://projects/7/playbook")
    playbook_recommendations = client.read_resource("mission-control://projects/7/playbook/recommendations")
    agent_contracts = client.read_resource("mission-control://projects/7/agent-contracts")
    decision_ledger = client.read_resource("mission-control://projects/7/decision-ledger")
    execution_policy = client.read_resource("mission-control://projects/7/execution-policy/summary")
    coordination = client.read_resource("mission-control://projects/7/coordination/summary")
    tensorflow_catalog = client.read_resource("mission-control://projects/7/tensorflow/features")
    tensorflow_bundle = client.read_resource("mission-control://projects/7/tensorflow/features/keras_scaffold")
    pytorch_catalog = client.read_resource("mission-control://projects/7/pytorch/features")
    pytorch_bundle = client.read_resource("mission-control://projects/7/pytorch/features/project_scaffold")
    spatial_catalog = client.read_resource("mission-control://projects/7/spatial/features")
    spatial_bundle = client.read_resource("mission-control://projects/7/spatial/features/asset_pipeline")
    webwright = client.read_resource("mission-control://projects/7/webwright")
    dynamo = client.read_resource("mission-control://projects/7/nvidia-dynamo")
    nim = client.read_resource("mission-control://projects/7/nvidia-nim")
    aiq = client.read_resource("mission-control://projects/7/nvidia-aiq")
    gpu = client.read_resource("mission-control://projects/7/nvidia-gpu-diagnostics")
    local_runtime = client.read_resource("mission-control://projects/7/nvidia-local-runtime")
    validation_plan = client.read_resource("mission-control://projects/7/nvidia-validation-plan")
    latest_simulation = client.read_resource("mission-control://projects/7/swarm/simulations/latest")

    assert profile_summary["display_name"] == "Mike"
    assert subagent_policy_summary["default_mode"] == "limited_write"
    assert snapshot["project_name"] == "Demo"
    assert snapshot["recommended_next_action"] == "Run the named pytest lane."
    assert instincts["instincts"][0]["key"] == "ship-with-evidence"
    assert verification["readiness"] == "blocked"
    assert verification["required_checks"] == ["python -m pytest apps/server/tests/test_operator_surfaces.py -q"]
    assert capability_report["section_count"] == 2
    assert capability_report["sections"][0]["key"] == "issue_to_execution_profiles"
    assert capability_section["section_key"] == "semantic_code_impact_mapping"
    assert capability_section["metadata_json"]["semantic_backend"] == "python-ast-graph"
    assert handoff_evidence["evidence_count"] == 1
    assert handoff_evidence["evidence_items"][0]["evidence_type"] == "test_result"
    assert handoff_evidence_preview["derived_candidate_count"] == 1
    assert tooling["validation_commands"] == ["uv run pytest", "ruff check ."]
    assert runbook["exists"] is True
    assert runbook["generated_from_handoff_id"] == 3
    assert runbook_summary["section_count"] == 2
    assert runbook_summary["run_commands"] == ["python -m pytest"]
    assert recovery_plans["recovery_plan_count"] == 1
    assert recovery_plans["plans"][0]["selected_action"] == "rerun_validation"
    assert recovery_plans_preview["suggested_action_count"] == 2
    assert snapshots["snapshot_count"] == 1
    assert snapshots["snapshots"][0]["label"] == "Before risky migration"
    assert restore_plan["snapshot_id"] == 61
    assert restore_plan["git_ref"] == "abc1234"
    assert playbook["playbook_key"] == "existing_repo_fix"
    assert playbook["playbook"]["name"] == "Existing Repo Fix"
    assert playbook_recommendations["project_id"] == 7
    assert playbook_recommendations["recommendations"][0]["score"] == 95
    assert agent_contracts["contract_count"] == 1
    assert agent_contracts["contracts"][0]["agent_name"] == "Reviewer"
    assert agent_contracts["contracts"][0]["allowed_paths"] == ["apps/server/src", "apps/server/tests"]
    assert decision_ledger["decision_count"] == 1
    assert decision_ledger["recent_decisions"][0]["title"] == "Keep direct pushes temporary"
    assert decision_ledger["recent_decisions"][0]["made_by"] == "operator"
    assert execution_policy["model_policy_name"] == "default"
    assert execution_policy["approval_required_tools"] == ["git push"]
    assert coordination["decision_count"] == 4
    assert coordination["low_confidence_categories"] == ["validation"]
    assert tensorflow_catalog["feature_count"] == 1
    assert tensorflow_bundle["feature_id"] == "keras_scaffold"
    assert pytorch_catalog["feature_count"] == 1
    assert pytorch_bundle["feature_id"] == "project_scaffold"
    assert spatial_catalog["feature_count"] == 2
    assert spatial_bundle["feature_id"] == "asset_pipeline"
    assert spatial_bundle["starter_files"] == ["pipelines/asset_pipeline.py", "configs/asset_pipeline.yaml"]
    assert webwright["available"] is True
    assert webwright["launch_command"] == "webwright"
    assert dynamo["reachable"] is True
    assert nim["reachable"] is True
    assert aiq["install_status"] == "ready"
    assert gpu["status"] == "ready"
    assert local_runtime["repo_mode"] == "cuda_cpp"
    assert validation_plan["status"] == "needs_review"
    assert latest_simulation["simulation_id"] == 17
    assert latest_simulation["persisted"] is False


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


def test_mcp_server_surfaces_integration_tools_and_resources() -> None:
    client = FakeClient()
    server = MissionControlMcpServer(client=client)

    tools = {item["name"] for item in server._build_tool_specs()}
    assert "mission_control_get_integrations_catalog" in tools
    assert "mission_control_get_integration_health" in tools
    assert "mission_control_get_project_integrations" in tools
    assert "mission_control_preview_integration_action" in tools
    assert "mission_control_execute_integration_action" in tools

    resource_catalog = server._call_get_integrations_catalog({})
    connections = server._call_get_integration_connections({})
    health = server._call_get_integration_health({})
    project_family = server._call_get_project_integration_family({"project_id": 7, "family": "source_control"})

    assert resource_catalog[0]["family"] == "source_control"
    assert connections[0]["family"] == "source_control"
    assert health["family_count"] == 30
    assert project_family["family"] == "source_control"

    preview = server._call_preview_integration_action({"project_id": 7, "family": "source_control", "action_id": "create", "params": {"title": "Demo", "body": "Body"}})
    execute = server._call_execute_integration_action({"project_id": 7, "family": "source_control", "action_id": "create", "params": {"title": "Demo", "body": "Body"}, "confirmed": False})

    assert preview["action_id"] == "create"
    assert execute["status"] == "approval_required"


def test_daemon_client_constructs_without_repo_checkout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MISSION_CONTROL_REPO_ROOT", raising=False)
    monkeypatch.delenv("MISSION_CONTROL_RUNTIME_ROOT", raising=False)
    monkeypatch.delenv("MISSION_CONTROL_LAUNCHER_DIR", raising=False)
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


def test_daemon_client_runbook_resource_returns_stable_missing_payload(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    monkeypatch.setattr(client, "get_runbook", lambda project_id: None)

    payload = client.read_resource("mission-control://projects/7/runbook")

    assert payload == {
        "project_id": 7,
        "exists": False,
        "content_markdown": None,
        "generated_from_handoff_id": None,
        "generated_at": None,
        "updated_at": None,
    }


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
        ".codex-plugin/plugin.json",
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
    skills_dir = package_files / "skills"
    assert skills_dir.is_dir(), "Missing bundled skills directory"
    for skill_name in manifest.get("skills") or []:
        assert (skills_dir / skill_name / "SKILL.md").is_file(), f"Missing bundled skill: {skill_name}"


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
