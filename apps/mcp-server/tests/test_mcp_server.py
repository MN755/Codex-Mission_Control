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
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/handoff",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/pending-decisions",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status-summary",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/event-digest",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/handoff-summary",
    "mission-control://projects/{project_id}/orchestrations/active",
    "mission-control://projects/{project_id}/status",
    "mission-control://projects/{project_id}/agents",
    "mission-control://projects/{project_id}/agents/{agent_id}/logs",
    "mission-control://projects/{project_id}/pending-decisions",
    "mission-control://projects/{project_id}/questions/pending",
    "mission-control://projects/{project_id}/approvals/pending",
    "mission-control://projects/{project_id}/event-digest",
    "mission-control://projects/{project_id}/handoff-summary",
    "mission-control://projects/{project_id}/handoff",
    "mission-control://projects/{project_id}/handoff/evidence",
    "mission-control://projects/{project_id}/handoff/evidence/preview",
    "mission-control://projects/{project_id}/codebase-map",
    "mission-control://projects/{project_id}/codebase-understanding",
    "mission-control://projects/{project_id}/import-safety",
    "mission-control://integrations/catalog",
    "mission-control://integrations/connections",
    "mission-control://integrations/health",
    "mission-control://agent-archetypes",
    "mission-control://agents/reputation",
    "mission-control://capabilities/benchmarks",
    "mission-control://capabilities/matrix",
    "mission-control://context-packs/{context_pack_id}",
    "mission-control://playbooks",
    "mission-control://playbooks/{playbook_key}",
    "mission-control://security/policy",
    "mission-control://daemon/status",
    "mission-control://runners/status",
    "mission-control://plugin/health",
    "mission-control://headless/config",
    "mission-control://system/status",
    "mission-control://system/auth-state",
    "mission-control://system/auth-jobs/{job_id}",
    "mission-control://system/codex-status",
    "mission-control://startup/status",
    "mission-control://dashboard/summary",
    "mission-control://widgets/catalog",
    "mission-control://widgets/catalog/{scope}",
    "mission-control://widgets/instances",
    "mission-control://widgets/instances/{instance_id}/data",
    "mission-control://tools",
    "mission-control://skills",
    "mission-control://handoffs",
    "mission-control://health",
    "mission-control://diagnostics/reports",
    "mission-control://diagnostics/identity",
    "mission-control://headless/health",
    "mission-control://headless/diagnostic-summary",
    "mission-control://projects",
    "mission-control://profile",
    "mission-control://profile/summary",
    "mission-control://preferences",
    "mission-control://preferences/summary",
    "mission-control://subagent-policy",
    "mission-control://subagent-policy/summary",
    "mission-control://projects/{project_id}/integrations",
    "mission-control://projects/{project_id}/integrations/{family}",
    "mission-control://projects/{project_id}/integrations/{family}/actions",
    "mission-control://projects/{project_id}/integrations/{family}/actions/{action_id}/preview",
    "mission-control://projects/{project_id}/settings",
    "mission-control://projects/{project_id}/details",
    "mission-control://projects/{project_id}/understanding",
    "mission-control://projects/{project_id}/interview",
    "mission-control://projects/{project_id}/plan",
    "mission-control://projects/{project_id}/runbook",
    "mission-control://projects/{project_id}/runbook/summary",
    "mission-control://projects/{project_id}/safe-mode",
    "mission-control://projects/{project_id}/recovery-plans",
    "mission-control://projects/{project_id}/recovery-plans/preview",
    "mission-control://projects/{project_id}/snapshots",
    "mission-control://projects/{project_id}/snapshots/{snapshot_id}/restore-plan",
    "mission-control://projects/{project_id}/playbook",
    "mission-control://projects/{project_id}/playbook/recommendations",
    "mission-control://projects/{project_id}/context-packs",
    "mission-control://projects/{project_id}/agents/reputation",
    "mission-control://projects/{project_id}/preferences",
    "mission-control://projects/{project_id}/preferences/summary",
    "mission-control://projects/{project_id}/preferences/effective",
    "mission-control://projects/{project_id}/subagent-batches",
    "mission-control://projects/{project_id}/subagent-batches/{batch_id}",
    "mission-control://projects/{project_id}/widgets/summary",
    "mission-control://projects/{project_id}/widgets/instances",
    "mission-control://projects/{project_id}/workspace",
    "mission-control://projects/{project_id}/workspace-tooling",
    "mission-control://projects/{project_id}/security/policy",
    "mission-control://projects/{project_id}/security/audit-log",
    "mission-control://projects/{project_id}/decisions/{decision_id}/bridge-message",
    "mission-control://projects/{project_id}/action",
    "mission-control://projects/{project_id}/actions",
    "mission-control://projects/{project_id}/manager/messages",
    "mission-control://projects/{project_id}/manager/queue",
    "mission-control://projects/{project_id}/tasks",
    "mission-control://projects/{project_id}/reservations",
    "mission-control://projects/{project_id}/events",
    "mission-control://projects/{project_id}/status-summary",
    "mission-control://projects/{project_id}/execution-policy/summary",
    "mission-control://projects/{project_id}/coordination/summary",
    "mission-control://projects/{project_id}/tensorflow/features",
    "mission-control://projects/{project_id}/tensorflow/features/{feature_id}",
    "mission-control://projects/{project_id}/pytorch/features",
    "mission-control://projects/{project_id}/pytorch/features/{feature_id}",
    "mission-control://projects/{project_id}/spatial/features",
    "mission-control://projects/{project_id}/spatial/features/{feature_id}",
    "mission-control://projects/{project_id}/diagnostics",
    "mission-control://projects/{project_id}/diagnostics/latest-report",
    "mission-control://projects/{project_id}/webwright",
    "mission-control://projects/{project_id}/nvidia-dynamo",
    "mission-control://projects/{project_id}/nvidia-nim",
    "mission-control://projects/{project_id}/nvidia-aiq",
    "mission-control://projects/{project_id}/nvidia-gpu-diagnostics",
    "mission-control://projects/{project_id}/nvidia-local-runtime",
    "mission-control://projects/{project_id}/nvidia-validation-plan",
    "mission-control://projects/{project_id}/swarm/preferences",
    "mission-control://projects/{project_id}/swarm-plan",
    "mission-control://projects/{project_id}/swarm/events",
    "mission-control://projects/{project_id}/swarm/simulations",
    "mission-control://projects/{project_id}/swarm/simulations/latest",
    "mission-control://risks/common",
    "mission-control://risks/summary",
    "mission-control://security/audit-log",
    "mission-control://projects/{project_id}/scope-creep",
    "mission-control://projects/{project_id}/risk-register",
    "mission-control://projects/{project_id}/risks/summary",
    "mission-control://projects/{project_id}/agent-contracts",
    "mission-control://projects/{project_id}/validation-summary",
    "mission-control://projects/{project_id}/validation-coverage",
    "mission-control://projects/{project_id}/validation-coverage/summary",
    "mission-control://projects/{project_id}/decision-ledger",
    "mission-control://projects/{project_id}/path-locks",
    "mission-control://projects/{project_id}/agents-md/status",
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
    requested_calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(client, "plugin_health", lambda: {"status": "healthy", "checks": []})
    monkeypatch.setattr(
        client,
        "_request",
        lambda method, path, **kwargs: requested_calls.append((path, kwargs)) or [],
    )
    monkeypatch.setattr(client, "get_status", lambda **kwargs: {"manager_status": "idle", "orchestration_status": "idle"})

    payload = client.get_diagnostics(project_id=7)

    assert payload["recent_reports"] == []
    assert ("/api/diagnostics/reports", {"params": {"project_id": 7}}) in requested_calls


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
        return [{
            "family": "source_control",
            "name": "GitHub / GitLab / Bitbucket",
            "summary": "Source control and review workflow lane.",
            "category": "delivery",
            "providers": ["github"],
            "host_support": ["codex"],
            "available_action_ids": ["create_issue"],
            "status": "connected",
            "connection_source": "codex_host",
            "host_imported": True,
        }]

    def get_integration_connections(self):
        self.calls.append(("get_integration_connections", {}))
        return [{
            "family": "source_control",
            "status": "connected",
            "providers": ["github"],
            "connection_source": "codex_host",
            "host_imported": True,
            "approval_policy": "ask_every_time",
            "notes": ["Imported from host CLI session."],
        }]

    def get_integration_health(self):
        self.calls.append(("get_integration_health", {}))
        return {
            "version": 2,
            "family_count": 30,
            "connection_count": 1,
            "authoritative_connection_count": 1,
            "host_imported_count": 1,
            "status_counts": {"connected": 1},
            "recent_action_failures": [],
            "host_import_roots": {"codex": ["C:/demo"]},
        }

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
            "family_count": 1,
            "status_counts": {"ready": 1},
            "connection_status_counts": {"connected": 1},
            "families": [{
                "family": "source_control",
                "name": "GitHub / GitLab / Bitbucket",
                "status": "ready",
                "connection_status": "connected",
                "resolved_provider": "github",
                "connection_source": "codex_host",
                "host_imported": True,
                "available_actions": [{"action_id": "create_issue"}],
                "blockers": [],
            }],
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
            "action_count": 1,
            "available_actions": [{
                "action_id": "create_issue",
                "title": "Create issue",
                "summary": "Create a work item.",
                "status": "available",
                "risk_level": "medium",
                "permission_policy": "ask_every_time",
                "provider": "github",
                "preview_supported": True,
                "requires_confirmation": True,
                "ready_to_execute": False,
                "missing_params": ["title"],
            }],
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
        "get_project_workspace",
        lambda project_id: {
            "project_id": project_id,
            "workspace_path": "C:/demo",
            "exists": True,
            "is_git_repo": True,
            "git_branch": "main",
            "git_status": "dirty",
            "top_level_entries": ["apps", "plugins", "docs"],
            "updated_at": "2026-06-03T12:39:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "list_projects",
        lambda: [
            {
                "id": 7,
                "name": "Demo",
                "slug": "demo",
                "idea": "Harden the MCP bridge.",
                "workspace_path": "C:/demo",
                "status": "active",
                "display_status": "needs_review",
                "runner_mode": "auto",
                "manager_mode": "codex",
                "pinned": True,
                "handoff_status": "needs_review",
                "latest_milestone": "Bridge parity",
                "latest_activity": "Validation is blocked on evidence capture.",
                "last_opened_at": "2026-06-03T12:45:00Z",
                "updated_at": "2026-06-03T12:46:00Z",
                "archived_at": None,
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_project",
        lambda project_id: {
            "id": project_id,
            "name": "Demo",
            "slug": "demo",
            "idea": "Harden the MCP bridge.",
            "workspace_path": "C:/demo",
            "status": "active",
            "display_status": "needs_review",
            "runner_mode": "auto",
            "manager_mode": "codex",
            "source_type": "existing_folder",
            "source_path": "C:/demo",
            "import_mode": "linked",
            "scan_status": "completed",
            "write_permission_status": "write_allowed",
            "pinned": True,
            "archived_at": None,
            "handoff_status": "needs_review",
            "latest_milestone": "Bridge parity",
            "latest_activity": "Validation is blocked on evidence capture.",
            "docs_path": "docs",
            "created_at": "2026-06-03T11:30:00Z",
            "updated_at": "2026-06-03T12:46:00Z",
            "last_opened_at": "2026-06-03T12:45:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_project_action",
        lambda project_id: {
            "project_id": project_id,
            "action_id": "run_validation",
            "title": "Run validation",
            "summary": "Execute the named pytest lane and record evidence.",
            "status": "pending",
            "priority": "high",
            "owner": "manager",
        },
    )
    monkeypatch.setattr(
        client,
        "list_project_actions",
        lambda project_id: [
            {
                "project_id": project_id,
                "action_id": "run_validation",
                "title": "Run validation",
                "summary": "Execute the named pytest lane and record evidence.",
                "status": "pending",
                "priority": "high",
                "owner": "manager",
            },
            {
                "project_id": project_id,
                "action_id": "update_catalog",
                "title": "Update MCP catalog",
                "summary": "Keep runtime and metadata aligned.",
                "status": "queued",
                "priority": "medium",
                "owner": "bridge",
            },
        ],
    )
    monkeypatch.setattr(
        client,
        "get_manager_messages",
        lambda project_id: [
            {
                "id": 91,
                "project_id": project_id,
                "role": "manager",
                "message": "Validation is blocked on evidence capture.",
                "created_at": "2026-06-03T12:40:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_decision_bridge_message",
        lambda decision_id, project_id: {
            "message_type": "pending_decision",
            "summary": "Need approval for a direct push to main.",
            "severity": "warning",
            "bullets": [f"Decision {decision_id}", f"Project {project_id}"],
        },
    )
    monkeypatch.setattr(
        client,
        "get_manager_queue",
        lambda project_id: {
            "project_id": project_id,
            "pending_question_count": 1,
            "pending_approval_count": 1,
            "pending_action_count": 2,
            "stale_message_count": 0,
            "next_priority": "high",
            "updated_at": "2026-06-03T12:41:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_project_tasks",
        lambda project_id: [
            {
                "id": 101,
                "project_id": project_id,
                "title": "Stabilize MCP runtime reads",
                "status": "in_progress",
                "priority": 1,
                "owner": "bridge",
            },
            {
                "id": 102,
                "project_id": project_id,
                "title": "Validate catalog parity",
                "status": "pending",
                "priority": 2,
                "owner": "reviewer",
            },
        ],
    )
    monkeypatch.setattr(
        client,
        "get_project_events",
        lambda project_id: [
            {
                "id": 111,
                "project_id": project_id,
                "event_type": "task_updated",
                "summary": "Validation task moved to in_progress.",
                "created_at": "2026-06-03T12:42:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "list_handoffs",
        lambda: [
            {
                "project_id": 7,
                "project_name": "Demo",
                "status": "needs_review",
                "summary": "Ready for review once evidence is attached.",
                "updated_at": "2026-06-03T12:43:00Z",
            }
        ],
    )
    monkeypatch.setattr(client, "get_health", lambda: {"status": "ok"})
    monkeypatch.setattr(
        client,
        "get_diagnostics_identity",
        lambda: {
            "service": "mission-control-daemon",
            "version": "0.3.0",
            "install_root": "C:/demo/install",
            "runtime_root": "C:/demo/runtime",
            "workspace_root": "C:/demo",
        },
    )
    monkeypatch.setattr(
        client,
        "get_headless_health",
        lambda: {
            "status": "ready",
            "checks": [{"key": "daemon", "status": "ok"}],
            "recommended_next_steps": [],
            "safe_troubleshooting_commands": ["python -m pytest"],
            "checked_at": "2026-06-03T12:44:30Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_headless_diagnostic_summary",
        lambda: {
            "message_type": "diagnostic_summary",
            "summary": "Headless runtime is healthy.",
            "severity": "info",
            "bullets": ["Daemon reachable", "Plugin health checks are green"],
        },
    )
    monkeypatch.setattr(
        client,
        "get_auth_job",
        lambda job_id: {
            "job_id": job_id,
            "status": "running",
            "auth_mode": "device",
            "provider": "openai",
            "message": "Waiting for device approval.",
            "created_at": "2026-06-03T12:40:00Z",
            "updated_at": "2026-06-03T12:45:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "list_diagnostic_reports",
        lambda project_id=None: [
            {
                "project_id": project_id or 7,
                "report_id": 121,
                "status": "warning",
                "summary": "One runtime catalog mismatch was corrected.",
                "created_at": "2026-06-03T12:44:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_tool_catalog",
        lambda: [
            {
                "name": "mission_control_attach_workspace",
                "description": "Attach the current workspace to Mission Control.",
                "category": "bootstrap",
                "requires_project": False,
                "requires_tool": None,
                "coming_soon": False,
                "risk_level": "low",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_project_settings",
        lambda project_id: {
            "project_id": project_id,
            "plan_autostart": True,
            "auto_apply_safe_fixes": False,
            "preferred_runner_mode": "auto",
            "workspace_write_allowed": True,
            "external_network_allowed": True,
            "dangerous_commands_require_approval": True,
            "preferred_diff_style": "unified",
            "preferred_test_command": "python -m pytest",
            "preferred_lint_command": "ruff check .",
            "preferred_build_command": "python -m build",
            "context_window_hint": 32000,
            "updated_at": "2026-06-03T12:35:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_integrations_catalog",
        lambda: [
            {
                "family": "source_control",
                "name": "GitHub / GitLab / Bitbucket",
                "summary": "Source control and review workflow lane.",
                "category": "delivery",
                "providers": ["github"],
                "host_support": ["codex"],
                "available_action_ids": ["create_issue"],
                "status": "connected",
                "connection_source": "codex_host",
                "host_imported": True,
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_integration_connections",
        lambda: [
            {
                "family": "source_control",
                "status": "connected",
                "providers": ["github"],
                "connection_source": "codex_host",
                "host_imported": True,
                "approval_policy": "ask_every_time",
                "notes": ["Imported from host CLI session."],
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_integration_health",
        lambda: {
            "version": 2,
            "family_count": 30,
            "connection_count": 1,
            "authoritative_connection_count": 1,
            "host_imported_count": 1,
            "status_counts": {"connected": 1},
            "recent_action_failures": [],
            "host_import_roots": {"codex": ["C:/demo"]},
        },
    )
    monkeypatch.setattr(
        client,
        "get_project_integrations",
        lambda project_id: {
            "project_id": project_id,
            "project_name": "Demo",
            "workspace_path": "C:/demo",
            "summary": "1 ready family.",
            "family_count": 1,
            "status_counts": {"ready": 1},
            "connection_status_counts": {"connected": 1},
            "families": [
                {
                    "family": "source_control",
                    "name": "GitHub / GitLab / Bitbucket",
                    "status": "ready",
                    "connection_status": "connected",
                    "resolved_provider": "github",
                    "connection_source": "codex_host",
                    "host_imported": True,
                    "available_actions": [{"action_id": "create_issue"}],
                    "blockers": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        client,
        "get_project_integration_family",
        lambda project_id, family: {
            "family": family,
            "name": "GitHub / GitLab / Bitbucket",
            "summary": "Repo host lane.",
            "category": "delivery",
            "project_name": "Demo",
            "workspace_path": "C:/demo",
            "status": "ready",
            "connection_status": "connected",
            "connection_source": "codex_host",
            "host_imported": True,
            "providers": ["github"],
            "resolved_provider": "github",
            "provider_candidates": ["github"],
            "required_permissions": ["ask_every_time"],
            "health": {"cli_detected": ["gh"]},
            "artifacts": [],
            "safe_commands": ["gh repo view --json name,defaultBranchRef"],
            "blockers": [],
            "recommended_fixes": [],
            "action_count": 1,
            "available_actions": [
                {
                    "action_id": "create_issue",
                    "title": "Create issue",
                    "summary": "Create a work item.",
                    "status": "available",
                    "risk_level": "medium",
                    "permission_policy": "ask_every_time",
                    "provider": "github",
                    "preview_supported": True,
                    "requires_confirmation": True,
                    "ready_to_execute": False,
                    "missing_params": ["title"],
                }
            ],
            "notes": [],
        },
    )
    monkeypatch.setattr(
        client,
        "preview_project_integration_action",
        lambda project_id, family, action_id, params=None: {
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
        },
    )
    monkeypatch.setattr(
        client,
        "get_agent_logs",
        lambda project_id, agent_id: {
            "agent_id": agent_id,
            "logs_path": f"C:/demo/runtime/{agent_id}.log",
            "content": "starting agent\nrunning validation lane\nwaiting for approval",
        },
    )
    monkeypatch.setattr(
        client,
        "get_orchestration",
        lambda orchestration_id, project_id=None: {
            "id": orchestration_id,
            "project_id": project_id or 7,
            "workspace_path": "C:/demo",
            "source": "codex_plugin",
            "user_request": "Finish the MCP parity work.",
            "status": "running",
            "manager_status": "awaiting_validation",
            "mode": "delegate",
            "created_at": "2026-06-03T12:00:00Z",
            "updated_at": "2026-06-03T12:46:00Z",
            "completed_at": None,
            "metadata_json": {"phase": "validation"},
        },
    )
    monkeypatch.setattr(
        client,
        "get_status_summary",
        lambda **kwargs: {
            "message_type": "status_summary",
            "summary": "Validation is the next gate.",
            "severity": "warning",
            "bullets": ["One approval is pending", "Validation evidence still missing"],
            "project_id": kwargs.get("project_id"),
            "orchestration_id": kwargs.get("orchestration_id"),
        },
    )
    monkeypatch.setattr(
        client,
        "get_codebase_understanding",
        lambda project_id: {
            "project_id": project_id,
            "summary": "Mission Control is a headless-first orchestration bridge with a Python backend and bundled MCP surfaces.",
            "architecture_notes": ["Codex chat bridges into the daemon.", "Plugin catalogs must stay in sync with runtime reads."],
            "unknowns": ["Live branch protection is weaker than expected."],
            "recommended_interview_mode": "targeted",
            "updated_at": "2026-06-03T12:36:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_import_safety",
        lambda project_id: {
            "project_id": project_id,
            "workspace_path": "C:/demo",
            "status": "ready",
            "requires_interview": False,
            "requires_confirmation": False,
            "warnings": ["Large repo; prefer targeted summaries."],
            "blockers": [],
            "safe_to_import": True,
            "updated_at": "2026-06-03T12:37:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_swarm_preferences",
        lambda project_id: {
            "project_id": project_id,
            "optimization_mode": "balanced",
            "swarm_aggressiveness": "measured",
            "max_agents": 4,
            "allow_dynamic_spawning": True,
            "allow_parallel_validation": True,
            "updated_at": "2026-06-03T12:38:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_swarm_events",
        lambda project_id: [
            {
                "id": 501,
                "project_id": project_id,
                "swarm_plan_id": 17,
                "event_type": "agent_spawned",
                "message": "Spawned reviewer lane after validation gate.",
                "agent_id": 22,
                "created_at": "2026-06-03T12:46:00Z",
                "metadata_json": {"lane": "review"},
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "list_swarm_simulations",
        lambda project_id: [
            {
                "id": 17,
                "project_id": project_id,
                "mode": "balanced",
                "recommended_agent_count": 3,
                "approval_required": False,
                "created_at": "2026-06-03T12:47:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_project_subagent_batches",
        lambda project_id: [
            {
                "id": 51,
                "project_id": project_id,
                "status": "completed",
                "task_type": "review",
                "spawn_method": "codex_chat_bridge",
                "requested_count": 2,
                "approved_count": 2,
                "completed_count": 2,
                "failure_count": 0,
                "created_at": "2026-06-03T12:46:00Z",
                "updated_at": "2026-06-03T12:47:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_subagent_batch",
        lambda project_id, batch_id: {
            "id": batch_id,
            "project_id": project_id,
            "status": "completed",
            "task_type": "review",
            "spawn_method": "codex_chat_bridge",
            "requested_count": 2,
            "approved_count": 2,
            "completed_count": 2,
            "failure_count": 0,
            "approvals_required": False,
            "summary_markdown": "## Batch summary\nTwo review agents completed successfully.",
            "results": [{"agent_name": "Reviewer A", "status": "completed"}],
            "created_at": "2026-06-03T12:46:00Z",
            "updated_at": "2026-06-03T12:47:30Z",
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
        "get_profile",
        lambda: {
            "id": 1,
            "display_name": "Mike",
            "preferred_provider_choice": "codex",
            "preferred_start_mode": "new_project",
            "selected_provider": "codex",
            "auth_mode": "device_code",
            "first_run_completed": True,
            "onboarding_completed": True,
            "default_runner_mode": "auto",
            "manager_model": "gpt-5-codex",
            "default_worker_model": "gpt-5-codex-mini",
            "sandbox_mode": "workspace-write",
            "approval_policy": "on-request",
            "theme": "system",
            "startup_behavior": "dashboard",
            "connected_accounts_json": {"github": {"connected": True}},
            "dashboard_widgets_json": ["recent_projects", "queue"],
            "tool_permission_overrides_json": {"git push": "ask"},
            "provider_endpoint": None,
            "adapter_command": "codex",
            "adapter_args_json": ["mcp", "serve"],
            "recent_startup_error_json": None,
            "created_at": "2026-06-03T11:20:00Z",
            "updated_at": "2026-06-03T12:40:00Z",
            "last_opened_at": "2026-06-03T12:45:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "active_project_orchestration",
        lambda project_id: {
            "id": 14,
            "project_id": project_id,
            "workspace_path": "C:/demo",
            "source": "codex_plugin",
            "user_request": "Finish the MCP parity work.",
            "status": "running",
            "manager_status": "awaiting_validation",
            "mode": "delegate",
            "created_at": "2026-06-03T12:00:00Z",
            "updated_at": "2026-06-03T12:46:00Z",
            "completed_at": None,
            "metadata_json": {"phase": "validation"},
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
        "get_agent_archetypes",
        lambda: [
            {
                "id": 1,
                "name": "reviewer",
                "description": "Finds regressions and validation gaps.",
                "default_temperature": 0.1,
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_agent_reputation",
        lambda project_id=None: [
            {
                "archetype": "reviewer" if project_id is None else "implementer",
                "provider": "codex",
                "model": "gpt-5.5",
                "total_tasks": 12 if project_id is None else 5,
                "success_rate": 0.92 if project_id is None else 0.8,
                "common_failure_modes": ["metadata drift"],
                "recommended_for": ["catalog alignment"],
                "avoid_for": [],
                "confidence": 84 if project_id is None else 61,
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_capability_benchmarks",
        lambda: [
            {
                "capability_key": "bridge_runtime_reads",
                "score": 95,
                "status": "ready",
                "summary": "Runtime read coverage is strong.",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_capability_matrix",
        lambda: [
            {
                "capability_key": "mcp_runtime",
                "support_level": "full",
                "notes": "Client, manifests, and bundled catalogs agree.",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_global_preference_summary",
        lambda: {
            "scope": "global",
            "project_id": None,
            "items": [
                {
                    "id": 11,
                    "key": "review_depth",
                    "value_json": "standard",
                    "source": "user",
                    "scope": "global",
                    "project_id": None,
                    "editable": True,
                    "inherited": False,
                    "created_at": "2026-06-03T12:20:00Z",
                    "updated_at": "2026-06-03T12:21:00Z",
                }
            ],
            "item_count": 1,
            "editable_count": 1,
            "inherited_count": 0,
            "project_override_count": 0,
        },
    )
    monkeypatch.setattr(
        client,
        "get_preferences",
        lambda: [
            {
                "id": 11,
                "key": "review_depth",
                "value_json": "standard",
                "source": "user",
                "scope": "global",
                "project_id": None,
                "editable": True,
                "created_at": "2026-06-03T12:20:00Z",
                "updated_at": "2026-06-03T12:21:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_subagent_policy",
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
            "updated_at": "2026-06-03T12:22:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "list_playbooks",
        lambda: [
            {
                "id": 1,
                "key": "ai_local_tool",
                "name": "AI Local Tool",
                "description": "Headless local tool workflow.",
                "suggested_interview_categories_json": ["product goal"],
                "suggested_swarm_mode": "balanced",
                "suggested_agent_archetypes_json": ["manager", "reviewer"],
                "suggested_validation_recipe_json": [{"type": "pytest", "command": "python -m pytest"}],
                "common_risks_json": ["policy drift"],
                "suggested_docs_json": ["runbook"],
                "typical_structure_json": ["apps/server", "plugins"],
                "created_at": "2026-06-03T11:00:00Z",
                "updated_at": "2026-06-03T11:30:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_playbook_catalog_entry",
        lambda playbook_key: {
            "id": 1,
            "key": playbook_key,
            "name": "AI Local Tool",
            "description": "Headless local tool workflow.",
            "suggested_interview_categories_json": ["product goal"],
            "suggested_swarm_mode": "balanced",
            "suggested_agent_archetypes_json": ["manager", "reviewer"],
            "suggested_validation_recipe_json": [{"type": "pytest", "command": "python -m pytest"}],
            "common_risks_json": ["policy drift"],
            "suggested_docs_json": ["runbook"],
            "typical_structure_json": ["apps/server", "plugins"],
            "created_at": "2026-06-03T11:00:00Z",
            "updated_at": "2026-06-03T11:30:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_context_packs",
        lambda project_id: [
            {
                "id": 31,
                "project_id": project_id,
                "title": "Bridge Runtime Pack",
                "status": "ready",
                "summary": "Captures runtime routes, manifests, and guard tests.",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_context_pack",
        lambda context_pack_id, project_id=None: {
            "id": context_pack_id,
            "project_id": project_id or 7,
            "title": "Bridge Runtime Pack",
            "status": "ready",
            "summary": "Captures runtime routes, manifests, and guard tests.",
            "artifacts": ["client.py", "plugin.json", "resources.json"],
        },
    )
    monkeypatch.setattr(
        client,
        "get_pending_decisions",
        lambda **kwargs: [
            {
                "id": 31,
                "project_id": kwargs.get("project_id", 7),
                "orchestration_id": kwargs.get("orchestration_id", 14),
                "category": "approval",
                "question_text": "Approve direct push to main?",
                "severity": "medium",
                "options": [{"id": "approve", "label": "Approve"}],
                "status": "pending",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_handoff",
        lambda **kwargs: {
            "status": "needs_review",
            "ready": True,
            "handoff": {
                "project_name": "Demo",
                "status": "needs_review",
                "summary": "Validation evidence still needs operator review.",
                "run_instructions": ["python -m pytest"],
                "tests_count": 1,
                "confidence_level": "medium",
                "evidence_status": "partial",
                "missing_evidence": ["release check"],
                "known_limitations": ["build check bypassed"],
                "dry_run": False,
            },
        },
    )
    monkeypatch.setattr(
        client,
        "get_pending_questions",
        lambda project_id: [
            {
                "id": 71,
                "project_id": project_id,
                "category": "scope",
                "question": "Should the bridge expose snapshot restore plans?",
                "impact": "Changes operator-facing recovery guidance.",
                "status": "pending",
                "options": [{"id": "yes", "label": "Yes"}, {"id": "later", "label": "Later"}],
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_pending_approvals",
        lambda project_id: [
            {
                "id": 81,
                "project_id": project_id,
                "kind": "command",
                "summary": "Approve a guarded git push.",
                "risk_level": "medium",
                "status": "pending",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_event_digest",
        lambda **kwargs: {
            "message_type": "event_digest",
            "title": "Mission Control event digest",
            "summary": "One recent blocker needs attention.",
            "fallback_markdown": "## Mission Control Event Digest\n",
            "user_action_required": False,
            "project_id": kwargs.get("project_id"),
            "orchestration_id": kwargs.get("orchestration_id"),
        },
    )
    monkeypatch.setattr(
        client,
        "get_handoff_summary",
        lambda **kwargs: {
            "message_type": "handoff_ready",
            "title": "Mission Control handoff summary",
            "summary": "Ready for review with one known limitation.",
            "fallback_markdown": "## Mission Control Handoff Summary\n",
            "user_action_required": False,
            "project_id": kwargs.get("project_id"),
            "orchestration_id": kwargs.get("orchestration_id"),
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
        "get_project_preference_summary",
        lambda project_id: {
            "scope": "project",
            "project_id": project_id,
            "items": [
                {
                    "id": 12,
                    "key": "review_depth",
                    "value_json": "strict",
                    "source": "manager_observed",
                    "scope": "project",
                    "project_id": project_id,
                    "editable": True,
                    "inherited": False,
                    "created_at": "2026-06-03T12:22:00Z",
                    "updated_at": "2026-06-03T12:23:00Z",
                },
                {
                    "id": 13,
                    "key": "docs_depth",
                    "value_json": "publishable",
                    "source": "setup",
                    "scope": "global",
                    "project_id": None,
                    "editable": False,
                    "inherited": True,
                    "created_at": "2026-06-03T12:24:00Z",
                    "updated_at": "2026-06-03T12:25:00Z",
                },
            ],
            "item_count": 2,
            "editable_count": 1,
            "inherited_count": 1,
            "project_override_count": 1,
        },
    )
    monkeypatch.setattr(
        client,
        "get_project_preferences",
        lambda project_id: [
            {
                "id": 21,
                "key": "validation_depth",
                "value_json": "release_grade",
                "source": "user",
                "scope": "project",
                "project_id": project_id,
                "editable": True,
                "created_at": "2026-06-03T12:23:00Z",
                "updated_at": "2026-06-03T12:24:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_effective_preferences",
        lambda project_id: [
            {
                "id": 12,
                "key": "review_depth",
                "value_json": "strict",
                "source": "manager_observed",
                "scope": "project",
                "project_id": project_id,
                "editable": True,
                "inherited": False,
                "created_at": "2026-06-03T12:22:00Z",
                "updated_at": "2026-06-03T12:23:00Z",
            },
            {
                "id": 13,
                "key": "docs_depth",
                "value_json": "publishable",
                "source": "setup",
                "scope": "global",
                "project_id": None,
                "editable": False,
                "inherited": True,
                "created_at": "2026-06-03T12:24:00Z",
                "updated_at": "2026-06-03T12:25:00Z",
            },
        ],
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
        "get_safe_mode",
        lambda project_id: {
            "project_id": project_id,
            "enabled": True,
            "require_all_command_approvals": True,
            "restrict_to_workspace": True,
            "bridge_message": {
                "message_type": "safe_mode",
                "title": "Mission Control safe mode",
                "summary": "Safe mode enabled.",
                "fallback_markdown": "## Safe Mode\n",
                "user_action_required": False,
            },
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
        "get_agents_md_status",
        lambda project_id: {
            "project_id": project_id,
            "has_agents_md": True,
            "status": "ready",
            "path": ".agents/AGENTS.md",
            "last_generated_at": "2026-06-03T13:25:00Z",
            "summary": "Repo-scoped agent instructions are present.",
        },
    )
    monkeypatch.setattr(
        client,
        "get_security_policy",
        lambda project_id=None: {
            "id": 44 if project_id is None else 45,
            "project_id": project_id,
            "approval_mode": "on-request",
            "allow_network": True,
            "allow_file_edits": True,
            "allow_background_processes": False,
            "updated_at": "2026-06-03T12:46:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_security_audit_log",
        lambda project_id=None: [
            {
                "id": 701,
                "project_id": project_id,
                "orchestration_id": 14 if project_id is not None else None,
                "decision_id": 31,
                "action_type": "git_push",
                "action_summary": "Push validated MCP catalog updates to main.",
                "risk_level": "medium",
                "decision": "approved_once",
                "decided_by": "user",
                "reason": "Validated targeted MCP tests passed.",
                "created_at": "2026-06-03T12:49:00Z",
                "metadata_json": {"branch": "main"},
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
        "get_validation_coverage_summary",
        lambda project_id: {
            "project_id": project_id,
            "items": [
                {
                    "project_id": project_id,
                    "area": "api",
                    "coverage_status": "passed",
                    "evidence_summary": "Named pytest API slice passed.",
                },
                {
                    "project_id": project_id,
                    "area": "recovery",
                    "coverage_status": "failed",
                    "evidence_summary": "Recovery workflow is still missing a validated probe.",
                },
            ],
            "gaps": ["recovery"],
            "gap_count": 1,
        },
    )
    monkeypatch.setattr(
        client,
        "get_validation_coverage",
        lambda project_id: [
            {
                "area": "api",
                "coverage_status": "passed",
                "evidence_summary": "Route smoke tests exist.",
                "coverage_percent": 100,
                "last_verified_at": "2026-06-03T12:25:00Z",
            },
            {
                "area": "recovery",
                "coverage_status": "failed",
                "evidence_summary": "No recovery evidence yet.",
                "coverage_percent": 0,
                "last_verified_at": "2026-06-03T12:26:00Z",
            },
        ],
    )
    monkeypatch.setattr(
        client,
        "get_risk_summary",
        lambda project_id=None: {
            "project_id": project_id,
            "total_count": 2 if project_id is not None else 5,
            "open_count": 1 if project_id is not None else 3,
            "status_counts": {"open": 1 if project_id is not None else 3, "mitigated": 1 if project_id is not None else 2},
            "severity_counts": {"medium": 1, "high": 1 if project_id is not None else 2},
            "top_risks": [
                {
                    "title": "Validation drift",
                    "severity": "high",
                    "likelihood": "medium",
                    "status": "open",
                    "project_id": project_id,
                }
            ],
        },
    )
    monkeypatch.setattr(
        client,
        "get_common_risks",
        lambda: [
            {
                "title": "Metadata drift",
                "severity": "high",
                "detail": "Runtime behavior and catalogs disagree unless parity tests stay enforced.",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_scope_creep",
        lambda project_id: [
            {
                "id": 91,
                "project_id": project_id,
                "source": "manager",
                "summary": "Add branch-protection auditing before release.",
                "severity": "medium",
                "related_task_id": None,
                "related_message_id": None,
                "suggested_action": "defer",
                "status": "open",
                "created_at": "2026-06-03T12:48:00Z",
                "resolved_at": None,
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_system_status",
        lambda project_id=None: {
            "selected_provider": "codex",
            "selected_provider_label": "Codex",
            "cli_detected": True,
            "cli_path": "C:/Tools/codex.exe",
            "cli_path_exists": True,
            "cli_execution_available": True,
            "cli_version": "1.0.0",
            "login_status": "authenticated",
            "auth_mode": "device_auth",
            "authenticated": True,
            "runtime_ready": True,
            "runtime_summary": "Runtime is ready.",
            "app_server_supported": True,
            "app_server_handshake_status": "connected",
            "app_server_transport": "http",
            "effective_runner_mode": "auto",
            "dry_run_available": True,
            "runtime_directory": "C:/Runtime",
            "diagnostics_directory": "C:/Runtime/diagnostics",
            "repo_root": "C:/Repo",
            "launcher_root": "C:/Launcher",
            "plugin_source_root": "C:/Repo/plugins/mission-control",
            "backend_host": "127.0.0.1",
            "backend_port": 8010,
            "backend_base_url": "http://127.0.0.1:8010",
            "configured_backend_port": 8010,
            "backend_binding_source": "config",
            "frontend_port": 4173,
            "active_runs": [],
            "current_settings_summary": None,
            "selected_manager_model": "gpt-5-codex",
            "selected_default_worker_model": "gpt-5-codex",
            "available_models": ["gpt-5-codex"],
            "model_advisories": [],
            "provider_statuses": [],
            "mcp_servers": [],
            "configured_mcp_servers": [],
            "mcp_state": {"healthy": True},
            "configured_plugins": ["mission-control"],
            "local_skills": ["mission-control"],
            "current_auth_job": None,
            "notes": ["Runtime ready."],
            "startup_summary": None,
            "app_state_summary": None,
        },
    )
    monkeypatch.setattr(
        client,
        "daemon_status",
        lambda: {
            "status": "running",
            "pid": 4242,
            "host": "127.0.0.1",
            "port": 8010,
            "healthy": True,
        },
    )
    monkeypatch.setattr(
        client,
        "get_runners_status",
        lambda: {
            "runner_count": 2,
            "available_runners": ["dry_run", "codex_cli"],
            "default_runner": "dry_run",
            "active_runner": "codex_cli",
            "requires_approval": False,
        },
    )
    monkeypatch.setattr(
        client,
        "plugin_health_summary",
        lambda: {
            "status": "ready",
            "checks": [{"key": "plugin_manifest", "status": "ready", "summary": "Manifest is valid."}],
        },
    )
    monkeypatch.setattr(
        client,
        "get_headless_config",
        lambda: {
            "enabled": True,
            "backend_host": "127.0.0.1",
            "backend_port": 8010,
            "bridge_token_configured": True,
            "default_mode": "existing_codebase",
            "approvals_required": True,
        },
    )
    monkeypatch.setattr(
        client,
        "get_auth_state",
        lambda: {
            "authenticated": True,
            "auth_mode": "device_auth",
            "login_status": "authenticated",
            "cli_detected": True,
            "provider": "codex",
            "current_job": None,
            "chatgpt_supported": True,
            "device_auth_supported": True,
            "api_key_supported": True,
            "provider_statuses": [],
            "notes": ["Auth looks healthy."],
        },
    )
    monkeypatch.setattr(
        client,
        "get_codex_status",
        lambda: {
            "selected_provider": "codex",
            "selected_provider_label": "Codex",
            "cli_detected": True,
            "cli_path": "C:/Tools/codex.exe",
            "cli_path_exists": True,
            "cli_execution_available": True,
            "cli_version": "1.0.0",
            "login_status": "authenticated",
            "auth_mode": "device_auth",
            "authenticated": True,
            "runtime_ready": True,
            "runtime_summary": "Codex runtime is ready.",
            "app_server_supported": True,
            "app_server_handshake_status": "connected",
            "app_server_transport": "http",
            "effective_runner_mode": "auto",
            "dry_run_available": True,
            "runtime_directory": "C:/Runtime",
            "diagnostics_directory": "C:/Runtime/diagnostics",
            "repo_root": "C:/Repo",
            "launcher_root": "C:/Launcher",
            "plugin_source_root": "C:/Repo/plugins/mission-control",
            "backend_host": "127.0.0.1",
            "backend_port": 8010,
            "backend_base_url": "http://127.0.0.1:8010",
            "configured_backend_port": 8010,
            "backend_binding_source": "config",
            "frontend_port": 4173,
            "active_runs": [],
            "current_settings_summary": None,
            "selected_manager_model": "gpt-5-codex",
            "selected_default_worker_model": "gpt-5-codex",
            "available_models": ["gpt-5-codex"],
            "model_advisories": [],
            "provider_statuses": [],
            "mcp_servers": [],
            "configured_mcp_servers": [],
            "mcp_state": {"healthy": True},
            "configured_plugins": ["mission-control"],
            "local_skills": ["mission-control"],
            "current_auth_job": None,
            "notes": ["Codex ready."],
            "startup_summary": None,
            "app_state_summary": None,
        },
    )
    monkeypatch.setattr(
        client,
        "get_startup_status",
        lambda: {
            "mode": "normal",
            "first_run_completed": True,
            "onboarding_complete": True,
            "setup_version_completed": "1.3.0",
            "current_setup_version": "1.3.0",
            "install_id": "install-demo",
            "startup_attempt": 1,
            "max_startup_attempts": 3,
            "overall_status": "ready",
            "backend_ready": True,
            "checks": [
                {
                    "name": "backend",
                    "required": True,
                    "status": "passed",
                    "summary": "Backend is reachable.",
                    "details": {},
                }
            ],
            "recommended_route": "dashboard",
            "error_code": None,
            "error_summary": None,
            "diagnostic_report_path": None,
            "degraded_reasons": [],
            "failed_checks": [],
            "status_source": "fresh",
            "startup_started_at": "2026-06-03T12:00:00Z",
            "last_completed_at": "2026-06-03T12:00:01Z",
            "checked_at": "2026-06-03T12:00:02Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_dashboard_summary",
        lambda: {
            "sidebar_projects": [{"id": 7, "name": "Demo"}],
            "recent_projects": [{"id": 7, "name": "Demo"}],
            "archive_count": 1,
            "active_builds": [],
            "attention_items": [{"kind": "risk", "summary": "Validation drift is open."}],
            "blocked_agents": [],
            "recent_handoffs": [],
            "runner_status": {"status": "ready"},
            "connected_accounts": {"codex": True},
            "model_defaults": {"manager_model": "gpt-5-codex"},
            "widgets": ["Connected Accounts"],
            "available_widgets": ["Connected Accounts", "Needs Attention"],
            "widget_instances": [],
            "widget_data": [],
            "widget_catalog": [],
        },
    )
    monkeypatch.setattr(
        client,
        "get_widget_catalog",
        lambda scope=None: [
            {
                "id": 1,
                "widget_type": "Connected Accounts",
                "title": "Connected Accounts",
                "description": "Shows account connections.",
                "scope": scope or "dashboard",
                "default_area": "dashboard_main",
                "default_size": "small",
                "category": "diagnostics",
                "requires_project": False,
                "requires_tool": None,
                "coming_soon": False,
                "risk_level": "low",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "list_widget_instances",
        lambda: [
            {
                "id": 301,
                "scope": "dashboard",
                "project_id": None,
                "widget_type": "recent_projects",
                "area": "dashboard_main",
                "order_index": 0,
                "size": "large",
                "collapsed": False,
                "enabled": True,
                "updated_at": "2026-06-03T12:48:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_project_widget_instances",
        lambda project_id: [
            {
                "id": 302,
                "scope": "project",
                "project_id": project_id,
                "widget_type": "runbook_status",
                "area": "project_right_sidebar",
                "order_index": 0,
                "size": "medium",
                "collapsed": False,
                "enabled": True,
                "updated_at": "2026-06-03T12:49:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_widget_instance_data",
        lambda instance_id: {
            "widget_instance_id": instance_id,
            "widget_type": "recent_projects",
            "title": "Recent Projects",
            "status": "ready",
            "data_json": {"project_count": 1, "project_names": ["Demo"]},
            "empty_state": None,
            "warnings_json": [],
            "updated_at": "2026-06-03T12:50:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_project_widget_summary",
        lambda project_id: {
            "scope": "project",
            "project_id": project_id,
            "instances": [
                {
                    "id": 3,
                    "widget_type": "runbook_status",
                    "title": "Runbook Status",
                    "scope": "project",
                    "project_id": project_id,
                    "area": "sidebar",
                    "size": "medium",
                    "position": 0,
                    "config_json": {},
                    "created_at": "2026-06-03T12:30:00Z",
                    "updated_at": "2026-06-03T12:31:00Z",
                }
            ],
            "data": [
                {
                    "widget_instance_id": 3,
                    "widget_type": "runbook_status",
                    "title": "Runbook Status",
                    "status": "ready",
                    "data_json": {"exists": True},
                    "empty_state": None,
                    "warnings_json": [],
                    "updated_at": "2026-06-03T12:31:00Z",
                }
            ],
            "catalog": [
                {
                    "widget_type": "runbook_status",
                    "title": "Runbook Status",
                    "description": "Shows runbook readiness.",
                    "scope": "project",
                    "default_area": "sidebar",
                    "default_size": "medium",
                    "supports_multiple_instances": False,
                    "config_schema_json": {},
                }
            ],
        },
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
    monkeypatch.setattr(
        client,
        "get_skills",
        lambda: [
            {
                "name": "mission-control",
                "label": "Mission Control",
                "category": "orchestration",
                "status": "ready",
                "summary": "Bridge skill for headless orchestration.",
            }
        ],
    )
    monkeypatch.setattr(
        client,
        "get_project_understanding",
        lambda project_id: {
            "project_id": project_id,
            "summary": "Repo is a headless orchestration bridge.",
            "known_facts_json": {"runtime": "python", "ui_required": False},
            "unknowns_json": {"deployment_topology": "not fully mapped"},
            "assumptions_json": ["Dashboard remains optional."],
            "constraints_json": ["Avoid UI edits unless asked."],
            "confidence_by_category_json": {"architecture": 0.92, "deployment": 0.41},
            "updated_at": "2026-06-03T12:00:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_interview",
        lambda project_id: {
            "id": 4,
            "project_id": project_id,
            "question_budget": 6,
            "questions_asked": 3,
            "questions_remaining": 3,
            "questions_generated": 3,
            "questions_answered": 2,
            "pending_questions": 1,
            "generation_budget_remaining": 3,
            "manager_mode": "guided",
            "stopped_early": False,
            "stop_reason": None,
            "confidence": {"scope": 0.7},
            "understanding_summary": "Need one more answer on deployment posture.",
            "known_facts": {"runtime": "python"},
            "unknowns": {"deployment": "pending"},
            "assumptions": ["Single daemon instance."],
            "constraints": ["No dashboard dependency."],
            "generation_sources": ["manager_generated"],
            "question_count": 3,
            "current_index": 2,
            "status": "active",
            "questions": [
                {
                    "id": 11,
                    "index": 0,
                    "question": "Should the daemon support multi-host orchestration?",
                    "category": "architecture",
                    "status": "answered",
                    "impact": "high",
                    "selected_option_id": "single-host",
                    "selected_text": "Single host is enough.",
                },
                {
                    "id": 12,
                    "index": 1,
                    "question": "Do you need persisted approval history?",
                    "category": "audit",
                    "status": "pending",
                    "impact": "medium",
                    "selected_option_id": None,
                    "selected_text": None,
                },
            ],
        },
    )
    monkeypatch.setattr(
        client,
        "get_plan",
        lambda project_id: {
            "id": 8,
            "project_id": project_id,
            "version": 2,
            "content_markdown": "## Manager plan\nShip the MCP bridge cleanup.",
            "status": "draft",
            "summary_json": {"milestones": ["Bridge parity", "Validation"], "risk_count": 2},
            "created_at": "2026-06-03T11:00:00Z",
            "updated_at": "2026-06-03T12:30:00Z",
        },
    )
    monkeypatch.setattr(
        client,
        "get_reservations",
        lambda project_id: [
            {
                "id": 51,
                "project_id": project_id,
                "task_id": 3,
                "agent_id": 9,
                "path": "apps/server/src/main.py",
                "created_at": "2026-06-03T12:05:00Z",
                "released_at": None,
            }
        ],
    )

    health = client.read_resource("mission-control://health")
    diagnostics_identity = client.read_resource("mission-control://diagnostics/identity")
    headless_health = client.read_resource("mission-control://headless/health")
    headless_diagnostic_summary = client.read_resource("mission-control://headless/diagnostic-summary")
    profile = client.read_resource("mission-control://profile")
    profile_summary = client.read_resource("mission-control://profile/summary")
    global_preferences = client.read_resource("mission-control://preferences")
    global_preference_summary = client.read_resource("mission-control://preferences/summary")
    integration_catalog = client.read_resource("mission-control://integrations/catalog")
    integration_connections = client.read_resource("mission-control://integrations/connections")
    integration_health = client.read_resource("mission-control://integrations/health")
    agent_archetypes = client.read_resource("mission-control://agent-archetypes")
    global_agent_reputation = client.read_resource("mission-control://agents/reputation")
    capability_benchmarks = client.read_resource("mission-control://capabilities/benchmarks")
    capability_matrix = client.read_resource("mission-control://capabilities/matrix")
    context_pack = client.read_resource("mission-control://context-packs/31")
    playbooks = client.read_resource("mission-control://playbooks")
    playbook_catalog_entry = client.read_resource("mission-control://playbooks/ai_local_tool")
    common_risks = client.read_resource("mission-control://risks/common")
    global_risk_summary = client.read_resource("mission-control://risks/summary")
    global_security_policy = client.read_resource("mission-control://security/policy")
    daemon_status = client.read_resource("mission-control://daemon/status")
    runners_status = client.read_resource("mission-control://runners/status")
    plugin_health = client.read_resource("mission-control://plugin/health")
    headless_config = client.read_resource("mission-control://headless/config")
    system_status = client.read_resource("mission-control://system/status")
    auth_state = client.read_resource("mission-control://system/auth-state")
    auth_job = client.read_resource("mission-control://system/auth-jobs/job-123")
    codex_status = client.read_resource("mission-control://system/codex-status")
    startup_status = client.read_resource("mission-control://startup/status")
    dashboard_summary = client.read_resource("mission-control://dashboard/summary")
    widget_catalog = client.read_resource("mission-control://widgets/catalog")
    project_widget_catalog = client.read_resource("mission-control://widgets/catalog/project")
    widget_instances = client.read_resource("mission-control://widgets/instances")
    widget_instance_data = client.read_resource("mission-control://widgets/instances/301/data")
    tool_catalog = client.read_resource("mission-control://tools")
    skills = client.read_resource("mission-control://skills")
    handoffs = client.read_resource("mission-control://handoffs")
    diagnostic_reports = client.read_resource("mission-control://diagnostics/reports")
    projects = client.read_resource("mission-control://projects")
    subagent_policy = client.read_resource("mission-control://subagent-policy")
    subagent_policy_summary = client.read_resource("mission-control://subagent-policy/summary")
    pending_questions = client.read_resource("mission-control://projects/7/questions/pending")
    pending_approvals = client.read_resource("mission-control://projects/7/approvals/pending")
    project_status_summary = client.read_resource("mission-control://projects/7/status-summary")
    agent_logs = client.read_resource("mission-control://projects/7/agents/15/logs")
    event_digest = client.read_resource("mission-control://projects/7/event-digest")
    handoff_summary = client.read_resource("mission-control://projects/7/handoff-summary")
    snapshot = client.read_resource("mission-control://projects/7/operator-snapshot")
    instincts = client.read_resource("mission-control://projects/7/instincts")
    verification = client.read_resource("mission-control://projects/7/verification-brief")
    capability_report = client.read_resource("mission-control://projects/7/capability-report")
    capability_section = client.read_resource("mission-control://projects/7/capability-report/semantic_code_impact_mapping")
    latest_diagnostic_report = client.read_resource("mission-control://projects/7/diagnostics/latest-report")
    handoff_evidence = client.read_resource("mission-control://projects/7/handoff/evidence")
    handoff_evidence_preview = client.read_resource("mission-control://projects/7/handoff/evidence/preview")
    codebase_understanding = client.read_resource("mission-control://projects/7/codebase-understanding")
    import_safety = client.read_resource("mission-control://projects/7/import-safety")
    project_integrations = client.read_resource("mission-control://projects/7/integrations")
    project_integration_family = client.read_resource("mission-control://projects/7/integrations/source_control")
    project_integration_actions = client.read_resource("mission-control://projects/7/integrations/source_control/actions")
    integration_action_preview = client.read_resource("mission-control://projects/7/integrations/source_control/actions/create_issue/preview")
    project_settings = client.read_resource("mission-control://projects/7/settings")
    project_details = client.read_resource("mission-control://projects/7/details")
    project_understanding = client.read_resource("mission-control://projects/7/understanding")
    interview = client.read_resource("mission-control://projects/7/interview")
    plan = client.read_resource("mission-control://projects/7/plan")
    orchestration_session = client.read_resource("mission-control://projects/7/orchestrations/14")
    orchestration_status_summary = client.read_resource("mission-control://projects/7/orchestrations/14/status-summary")
    orchestration_event_digest = client.read_resource("mission-control://projects/7/orchestrations/14/event-digest")
    orchestration_handoff_summary = client.read_resource("mission-control://projects/7/orchestrations/14/handoff-summary")
    orchestration_handoff = client.read_resource("mission-control://projects/7/orchestrations/14/handoff")
    orchestration_pending_decisions = client.read_resource("mission-control://projects/7/orchestrations/14/pending-decisions")
    active_orchestration = client.read_resource("mission-control://projects/7/orchestrations/active")
    workspace = client.read_resource("mission-control://projects/7/workspace")
    tooling = client.read_resource("mission-control://projects/7/workspace-tooling")
    project_security_policy = client.read_resource("mission-control://projects/7/security/policy")
    decision_bridge_message = client.read_resource("mission-control://projects/7/decisions/31/bridge-message")
    project_action = client.read_resource("mission-control://projects/7/action")
    project_actions = client.read_resource("mission-control://projects/7/actions")
    manager_messages = client.read_resource("mission-control://projects/7/manager/messages")
    manager_queue = client.read_resource("mission-control://projects/7/manager/queue")
    runbook = client.read_resource("mission-control://projects/7/runbook")
    runbook_summary = client.read_resource("mission-control://projects/7/runbook/summary")
    safe_mode = client.read_resource("mission-control://projects/7/safe-mode")
    recovery_plans = client.read_resource("mission-control://projects/7/recovery-plans")
    recovery_plans_preview = client.read_resource("mission-control://projects/7/recovery-plans/preview")
    snapshots = client.read_resource("mission-control://projects/7/snapshots")
    restore_plan = client.read_resource("mission-control://projects/7/snapshots/61/restore-plan")
    playbook = client.read_resource("mission-control://projects/7/playbook")
    playbook_recommendations = client.read_resource("mission-control://projects/7/playbook/recommendations")
    context_packs = client.read_resource("mission-control://projects/7/context-packs")
    project_agent_reputation = client.read_resource("mission-control://projects/7/agents/reputation")
    project_preferences = client.read_resource("mission-control://projects/7/preferences")
    project_preference_summary = client.read_resource("mission-control://projects/7/preferences/summary")
    effective_preferences = client.read_resource("mission-control://projects/7/preferences/effective")
    widget_summary = client.read_resource("mission-control://projects/7/widgets/summary")
    project_widget_instances = client.read_resource("mission-control://projects/7/widgets/instances")
    project_risk_summary = client.read_resource("mission-control://projects/7/risks/summary")
    agent_contracts = client.read_resource("mission-control://projects/7/agent-contracts")
    validation_summary = client.read_resource("mission-control://projects/7/validation-summary")
    validation_coverage = client.read_resource("mission-control://projects/7/validation-coverage")
    validation_coverage_summary = client.read_resource("mission-control://projects/7/validation-coverage/summary")
    decision_ledger = client.read_resource("mission-control://projects/7/decision-ledger")
    execution_policy = client.read_resource("mission-control://projects/7/execution-policy/summary")
    coordination = client.read_resource("mission-control://projects/7/coordination/summary")
    agents_md_status = client.read_resource("mission-control://projects/7/agents-md/status")
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
    swarm_preferences = client.read_resource("mission-control://projects/7/swarm/preferences")
    subagent_batches = client.read_resource("mission-control://projects/7/subagent-batches")
    subagent_batch = client.read_resource("mission-control://projects/7/subagent-batches/51")
    swarm_events = client.read_resource("mission-control://projects/7/swarm/events")
    swarm_simulations = client.read_resource("mission-control://projects/7/swarm/simulations")
    global_security_audit = client.read_resource("mission-control://security/audit-log")
    project_security_audit = client.read_resource("mission-control://projects/7/security/audit-log")
    scope_creep = client.read_resource("mission-control://projects/7/scope-creep")
    tasks = client.read_resource("mission-control://projects/7/tasks")
    reservations = client.read_resource("mission-control://projects/7/reservations")
    events = client.read_resource("mission-control://projects/7/events")
    latest_simulation = client.read_resource("mission-control://projects/7/swarm/simulations/latest")

    assert health["status"] == "ok"
    assert diagnostics_identity["service"] == "mission-control-daemon"
    assert headless_health["status"] == "ready"
    assert headless_diagnostic_summary["message_type"] == "diagnostic_summary"
    assert profile["display_name"] == "Mike"
    assert profile["provider_endpoint_configured"] is False
    assert profile["tool_permission_overrides_json"] == {"git push": "ask"}
    assert profile_summary["display_name"] == "Mike"
    assert global_preferences["scope"] == "global"
    assert global_preferences["item_count"] == 1
    assert global_preferences["items"][0]["key"] == "review_depth"
    assert global_preference_summary["scope"] == "global"
    assert global_preference_summary["item_count"] == 1
    assert integration_catalog["family_count"] == 1
    assert integration_catalog["connected_family_count"] == 1
    assert integration_catalog["families"][0]["action_count"] == 1
    assert integration_connections["connection_count"] == 1
    assert integration_connections["host_imported_count"] == 1
    assert integration_connections["connections"][0]["approval_policy"] == "ask_every_time"
    assert integration_health["family_count"] == 30
    assert integration_health["authoritative_connection_count"] == 1
    assert integration_health["host_import_roots"]["codex"] == ["C:/demo"]
    assert subagent_policy["enabled"] is True
    assert subagent_policy["default_mode"] == "limited_write"
    assert subagent_policy["allowed_task_types_json"] == ["review", "planning", "failure_diagnosis"]
    assert agent_archetypes["archetype_count"] == 1
    assert agent_archetypes["archetypes"][0]["name"] == "reviewer"
    assert global_agent_reputation["reputation_count"] == 1
    assert global_agent_reputation["reputations"][0]["archetype"] == "reviewer"
    assert capability_benchmarks["benchmark_count"] == 1
    assert capability_benchmarks["benchmarks"][0]["capability_key"] == "bridge_runtime_reads"
    assert capability_matrix["entry_count"] == 1
    assert capability_matrix["entries"][0]["capability_key"] == "mcp_runtime"
    assert context_pack["id"] == 31
    assert playbooks["playbooks"][0]["key"] == "ai_local_tool"
    assert playbook_catalog_entry["key"] == "ai_local_tool"
    assert common_risks["common_risk_count"] == 1
    assert common_risks["common_risks"][0]["title"] == "Metadata drift"
    assert global_risk_summary["project_id"] is None
    assert global_risk_summary["open_count"] == 3
    assert global_security_policy["approval_mode"] == "on-request"
    assert daemon_status["healthy"] is True
    assert runners_status["runner_count"] == 2
    assert plugin_health["status"] == "ready"
    assert headless_config["enabled"] is True
    assert system_status["runtime_ready"] is True
    assert auth_state["authenticated"] is True
    assert auth_job["job_id"] == "job-123"
    assert auth_job["status"] == "running"
    assert codex_status["runtime_summary"] == "Codex runtime is ready."
    assert startup_status["overall_status"] == "ready"
    assert dashboard_summary["archive_count"] == 1
    assert widget_catalog["scope"] == "all"
    assert widget_catalog["catalog"][0]["widget_type"] == "Connected Accounts"
    assert project_widget_catalog["scope"] == "project"
    assert project_widget_catalog["catalog"][0]["scope"] == "project"
    assert widget_instances["instance_count"] == 1
    assert widget_instances["instances"][0]["widget_type"] == "recent_projects"
    assert widget_instance_data["widget_instance_id"] == 301
    assert widget_instance_data["data_keys"] == ["project_count", "project_names"]
    assert tool_catalog["tool_count"] == 1
    assert tool_catalog["tools"][0]["name"] == "mission_control_attach_workspace"
    assert skills["skill_count"] == 1
    assert skills["skills"][0]["name"] == "mission-control"
    assert handoffs["handoff_count"] == 1
    assert handoffs["handoffs"][0]["project_name"] == "Demo"
    assert diagnostic_reports["report_count"] == 1
    assert diagnostic_reports["reports"][0]["status"] == "warning"
    assert projects["project_count"] == 1
    assert projects["projects"][0]["pinned"] is True
    assert subagent_policy_summary["default_mode"] == "limited_write"
    assert pending_questions["question_count"] == 1
    assert pending_questions["questions"][0]["category"] == "scope"
    assert pending_approvals["approval_count"] == 1
    assert pending_approvals["approvals"][0]["risk_level"] == "medium"
    assert project_status_summary["message_type"] == "status_summary"
    assert agent_logs["agent_id"] == 15
    assert agent_logs["line_count"] == 3
    assert agent_logs["tail_lines"][-1] == "waiting for approval"
    assert event_digest["message_type"] == "event_digest"
    assert handoff_summary["message_type"] == "handoff_ready"
    assert snapshot["project_name"] == "Demo"
    assert snapshot["recommended_next_action"] == "Run the named pytest lane."
    assert instincts["instincts"][0]["key"] == "ship-with-evidence"
    assert verification["readiness"] == "blocked"
    assert verification["required_checks"] == ["python -m pytest apps/server/tests/test_operator_surfaces.py -q"]
    assert capability_report["section_count"] == 2
    assert capability_report["sections"][0]["key"] == "issue_to_execution_profiles"
    assert capability_section["section_key"] == "semantic_code_impact_mapping"
    assert capability_section["metadata_json"]["semantic_backend"] == "python-ast-graph"
    assert latest_diagnostic_report["exists"] is True
    assert latest_diagnostic_report["report"]["report_id"] == 121
    assert handoff_evidence["evidence_count"] == 1
    assert handoff_evidence["evidence_items"][0]["evidence_type"] == "test_result"
    assert handoff_evidence_preview["derived_candidate_count"] == 1
    assert codebase_understanding["recommended_interview_mode"] == "targeted"
    assert import_safety["safe_to_import"] is True
    assert project_integrations["project_id"] == 7
    assert project_integrations["ready_family_count"] == 1
    assert project_integrations["families"][0]["resolved_provider"] == "github"
    assert project_integration_family["family"] == "source_control"
    assert project_integration_family["action_count"] == 1
    assert project_integration_family["available_actions"][0]["action_id"] == "create_issue"
    assert project_integration_actions["family"] == "source_control"
    assert project_integration_actions["action_count"] == 1
    assert project_integration_actions["requires_confirmation_count"] == 1
    assert project_integration_actions["actions"][0]["missing_params"] == ["title"]
    assert integration_action_preview["family"] == "source_control"
    assert integration_action_preview["action_id"] == "create_issue"
    assert integration_action_preview["requires_confirmation"] is True
    assert project_settings["preferred_runner_mode"] == "auto"
    assert project_details["project_name"] == "Demo"
    assert project_details["display_status"] == "needs_review"
    assert project_understanding["summary"] == "Repo is a headless orchestration bridge."
    assert project_understanding["known_fact_count"] == 2
    assert interview["exists"] is True
    assert interview["question_count"] == 3
    assert interview["questions"][0]["selected_option_id"] == "single-host"
    assert plan["exists"] is True
    assert plan["version"] == 2
    assert plan["summary_json"]["risk_count"] == 2
    assert orchestration_session["orchestration_id"] == 14
    assert orchestration_session["manager_status"] == "awaiting_validation"
    assert orchestration_status_summary["orchestration_id"] == 14
    assert orchestration_status_summary["message_type"] == "status_summary"
    assert orchestration_event_digest["orchestration_id"] == 14
    assert orchestration_event_digest["message_type"] == "event_digest"
    assert orchestration_handoff_summary["orchestration_id"] == 14
    assert orchestration_handoff_summary["message_type"] == "handoff_ready"
    assert orchestration_handoff["status"] == "needs_review"
    assert orchestration_pending_decisions["decision_count"] == 1
    assert active_orchestration["exists"] is True
    assert active_orchestration["orchestration_id"] == 14
    assert active_orchestration["manager_status"] == "awaiting_validation"
    assert workspace["git_branch"] == "main"
    assert tooling["validation_commands"] == ["uv run pytest", "ruff check ."]
    assert project_security_policy["project_id"] == 7
    assert decision_bridge_message["message_type"] == "pending_decision"
    assert project_action["action_id"] == "run_validation"
    assert project_actions["action_count"] == 2
    assert manager_messages["message_count"] == 1
    assert manager_queue["pending_action_count"] == 2
    assert runbook["exists"] is True
    assert runbook["generated_from_handoff_id"] == 3
    assert runbook_summary["section_count"] == 2
    assert runbook_summary["run_commands"] == ["python -m pytest"]
    assert safe_mode["enabled"] is True
    assert safe_mode["bridge_message"]["summary"] == "Safe mode enabled."
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
    assert context_packs["context_pack_count"] == 1
    assert context_packs["context_packs"][0]["title"] == "Bridge Runtime Pack"
    assert project_agent_reputation["project_id"] == 7
    assert project_agent_reputation["reputations"][0]["archetype"] == "implementer"
    assert project_preferences["project_id"] == 7
    assert project_preferences["items"][0]["key"] == "validation_depth"
    assert project_preference_summary["scope"] == "project"
    assert project_preference_summary["inherited_count"] == 1
    assert effective_preferences["item_count"] == 2
    assert effective_preferences["items"][1]["inherited"] is True
    assert widget_summary["project_id"] == 7
    assert widget_summary["instances"][0]["widget_type"] == "runbook_status"
    assert project_widget_instances["project_id"] == 7
    assert project_widget_instances["instances"][0]["widget_type"] == "runbook_status"
    assert project_risk_summary["project_id"] == 7
    assert project_risk_summary["top_risks"][0]["title"] == "Validation drift"
    assert agent_contracts["contract_count"] == 1
    assert agent_contracts["contracts"][0]["agent_name"] == "Reviewer"
    assert agent_contracts["contracts"][0]["allowed_paths"] == ["apps/server/src", "apps/server/tests"]
    assert validation_summary["coverage_counts"] == {"passed": 1, "failed": 1}
    assert validation_summary["notable_gaps"] == ["recovery"]
    assert validation_coverage["project_id"] == 7
    assert validation_coverage["gap_count"] == 1
    assert validation_coverage["items"][1]["area"] == "recovery"
    assert validation_coverage_summary["gap_count"] == 1
    assert validation_coverage_summary["items"][0]["area"] == "api"
    assert decision_ledger["decision_count"] == 1
    assert decision_ledger["recent_decisions"][0]["title"] == "Keep direct pushes temporary"
    assert decision_ledger["recent_decisions"][0]["made_by"] == "operator"
    assert execution_policy["model_policy_name"] == "default"
    assert execution_policy["approval_required_tools"] == ["git push"]
    assert coordination["decision_count"] == 4
    assert coordination["low_confidence_categories"] == ["validation"]
    assert agents_md_status["has_agents_md"] is True
    assert agents_md_status["path"] == ".agents/AGENTS.md"
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
    assert swarm_preferences["max_agents"] == 4
    assert subagent_batches["project_id"] == 7
    assert subagent_batches["batch_count"] == 1
    assert subagent_batches["batches"][0]["task_type"] == "review"
    assert subagent_batch["project_id"] == 7
    assert subagent_batch["batch_id"] == 51
    assert subagent_batch["results"][0]["agent_name"] == "Reviewer A"
    assert swarm_events["event_count"] == 1
    assert swarm_events["events"][0]["event_type"] == "agent_spawned"
    assert swarm_simulations["simulation_count"] == 1
    assert swarm_simulations["simulations"][0]["recommended_agent_count"] == 3
    assert global_security_audit["audit_entry_count"] == 1
    assert global_security_audit["entries"][0]["decision"] == "approved_once"
    assert project_security_audit["project_id"] == 7
    assert project_security_audit["entries"][0]["project_id"] == 7
    assert scope_creep["signal_count"] == 1
    assert scope_creep["signals"][0]["suggested_action"] == "defer"
    assert tasks["task_count"] == 2
    assert reservations["active_reservation_count"] == 1
    assert reservations["reservations"][0]["path"] == "apps/server/src/main.py"
    assert events["event_count"] == 1
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


def test_daemon_client_active_project_orchestration_remembers_mapping(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    monkeypatch.setattr(
        client,
        "_request",
        lambda method, path, **kwargs: {
            "id": 14,
            "project_id": 7,
            "workspace_path": "C:/demo",
            "source": "codex_plugin",
            "user_request": "Check runtime parity.",
            "status": "running",
            "manager_status": "active",
            "mode": "delegate",
            "created_at": "2026-06-03T12:00:00Z",
            "updated_at": "2026-06-03T12:10:00Z",
            "completed_at": None,
            "metadata_json": {},
        },
    )

    payload = client.active_project_orchestration(7)

    assert payload["id"] == 14
    assert client._orchestration_project_ids[14] == 7


def test_daemon_client_active_orchestration_resource_returns_stable_missing_payload(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    monkeypatch.setattr(client, "active_project_orchestration", lambda project_id: None)

    payload = client.read_resource("mission-control://projects/7/orchestrations/active")

    assert payload == {
        "project_id": 7,
        "exists": False,
        "orchestration_id": None,
        "status": None,
        "manager_status": None,
        "mode": None,
        "source": None,
        "user_request": None,
        "workspace_path": None,
        "metadata_json": {},
        "created_at": None,
        "updated_at": None,
        "completed_at": None,
    }


def test_daemon_client_bridge_auth_protected_reads_include_token(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    calls: list[tuple[str, str, bool]] = []

    def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, bool(kwargs.get("requires_token", True))))
        return {}

    monkeypatch.setattr(client, "_request", fake_request)

    client.get_health()
    client.get_diagnostics_identity()
    client.get_headless_health()
    client.get_headless_diagnostic_summary()
    client.daemon_status()
    client.get_profile()
    client.get_auth_job("job-123")
    client.get_handoff(orchestration_id=14, project_id=7)
    client.get_pending_decisions(orchestration_id=14, project_id=7)
    client.get_project_handoff(7)
    client.get_codebase_map(7)
    client.get_codebase_understanding(7)
    client.get_import_safety(7)
    client.preview_project_integration_action(7, "source_control", "create_issue")
    client.get_project_settings(7)
    client.get_agent_logs(7, 15)
    client.get_orchestration(14, project_id=7)
    client.get_status_summary(orchestration_id=14, project_id=7)
    client.get_event_digest(orchestration_id=14, project_id=7)
    client.get_handoff_summary(orchestration_id=14, project_id=7)
    client.get_status_summary(project_id=7)
    client.list_projects()
    client.get_project(7)
    client.get_tool_catalog()
    client.get_skills()
    client.get_preferences()
    client.get_subagent_policy()
    client.list_widget_instances()
    client.get_project_widget_instances(7)
    client.get_widget_instance_data(301)
    client.get_project_understanding(7)
    client.get_interview(7)
    client.get_plan(7)
    client.get_swarm_preferences(7)
    client.get_swarm_events(7)
    client.get_agent_archetypes()
    client.get_agent_reputation()
    client.get_agent_reputation(7)
    client.get_capability_benchmarks()
    client.get_capability_matrix()
    client.get_context_packs(7)
    client.get_context_pack(31, project_id=7)
    client.get_project_preferences(7)
    client.get_common_risks()
    client.get_scope_creep(7)
    client.get_security_policy()
    client.get_security_policy(7)
    client.get_security_audit_log()
    client.get_security_audit_log(7)
    client.get_decision_bridge_message(31, project_id=7)
    client.list_swarm_simulations(7)
    client.get_validation_coverage(7)
    client.get_project_workspace(7)
    client.get_project_action(7)
    client.list_project_actions(7)
    client.get_manager_messages(7)
    client.get_manager_queue(7)
    client.get_project_tasks(7)
    client.get_reservations(7)
    client.get_project_events(7)
    client.get_project_subagent_batches(7)
    client.get_subagent_batch(7, 51)
    client.list_handoffs()
    client.list_diagnostic_reports()
    client.list_diagnostic_reports(7)
    client.active_project_orchestration(7)

    assert calls == [
        ("GET", "/api/health", False),
        ("GET", "/api/diagnostics/identity", True),
        ("GET", "/api/headless/health", True),
        ("GET", "/api/headless/diagnostic-summary", True),
        ("GET", "/api/daemon/status", True),
        ("GET", "/api/profile", True),
        ("GET", "/api/system/auth-jobs/job-123", True),
        ("GET", "/api/orchestrations/14/handoff", True),
        ("GET", "/api/orchestrations/14/pending-decisions", True),
        ("GET", "/api/projects/7/handoff", True),
        ("GET", "/api/projects/7/codebase-map", True),
        ("GET", "/api/projects/7/codebase-understanding", True),
        ("GET", "/api/projects/7/import-safety", True),
        ("POST", "/api/projects/7/integrations/source_control/actions/create_issue/preview", True),
        ("GET", "/api/settings", True),
        ("GET", "/api/agents/15/logs", True),
        ("GET", "/api/orchestrations/14", True),
        ("GET", "/api/orchestrations/14/status-summary", True),
        ("GET", "/api/orchestrations/14/event-digest", True),
        ("GET", "/api/orchestrations/14/handoff-summary", True),
        ("GET", "/api/projects/7/orchestrations/active", True),
        ("GET", "/api/projects/7/status-summary", True),
        ("GET", "/api/projects", True),
        ("GET", "/api/projects/7", True),
        ("GET", "/api/tools", True),
        ("GET", "/api/skills", True),
        ("GET", "/api/preferences", True),
        ("GET", "/api/subagent-policy", True),
        ("GET", "/api/widgets/instances", True),
        ("GET", "/api/projects/7/widgets/instances", True),
        ("GET", "/api/widgets/instances/301/data", True),
        ("GET", "/api/projects/7/understanding", True),
        ("GET", "/api/projects/7/interview", True),
        ("GET", "/api/projects/7/plan", True),
        ("GET", "/api/projects/7/swarm/preferences", True),
        ("GET", "/api/projects/7/swarm/events", True),
        ("GET", "/api/agent-archetypes", True),
        ("GET", "/api/agents/reputation", True),
        ("GET", "/api/projects/7/agents/reputation", True),
        ("GET", "/api/capabilities/benchmarks", True),
        ("GET", "/api/capabilities/matrix", True),
        ("GET", "/api/projects/7/context-packs", True),
        ("GET", "/api/context-packs/31", True),
        ("GET", "/api/projects/7/preferences", True),
        ("GET", "/api/risks/common", True),
        ("GET", "/api/projects/7/scope-creep", True),
        ("GET", "/api/security/policy", True),
        ("GET", "/api/projects/7/security/policy", True),
        ("GET", "/api/security/audit-log", True),
        ("GET", "/api/projects/7/security/audit-log", True),
        ("GET", "/api/decisions/31/bridge-message", True),
        ("GET", "/api/projects/7/swarm/simulations", True),
        ("GET", "/api/projects/7/validation-coverage", True),
        ("GET", "/api/projects/7/workspace", True),
        ("GET", "/api/projects/7/action", True),
        ("GET", "/api/projects/7/actions", True),
        ("GET", "/api/projects/7/manager/messages", True),
        ("GET", "/api/projects/7/manager/queue", True),
        ("GET", "/api/projects/7/tasks", True),
        ("GET", "/api/projects/7/reservations", True),
        ("GET", "/api/projects/7/events", True),
        ("GET", "/api/projects/7/subagent-batches", True),
        ("GET", "/api/subagents/batches/51", True),
        ("GET", "/api/handoffs", True),
        ("GET", "/api/diagnostics/reports", True),
        ("GET", "/api/diagnostics/reports", True),
        ("GET", "/api/projects/7/orchestrations/active", True),
    ]


def test_daemon_client_get_context_pack_passes_project_scope_when_provided(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    seen: dict[str, object] = {}

    def fake_request(method: str, path: str, **kwargs):
        seen["method"] = method
        seen["path"] = path
        seen["params"] = kwargs.get("params")
        return {}

    monkeypatch.setattr(client, "_request", fake_request)

    client.get_context_pack(31, project_id=7)

    assert seen == {
        "method": "GET",
        "path": "/api/context-packs/31",
        "params": {"project_id": 7},
    }


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


def test_daemon_client_interview_resource_returns_stable_missing_payload(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    monkeypatch.setattr(client, "get_interview", lambda project_id: None)

    payload = client.read_resource("mission-control://projects/7/interview")

    assert payload == {
        "project_id": 7,
        "exists": False,
        "status": None,
        "question_budget": 0,
        "question_count": 0,
        "questions_answered": 0,
        "pending_questions": 0,
        "manager_mode": None,
        "understanding_summary": None,
        "questions": [],
    }


def test_daemon_client_plan_resource_returns_stable_missing_payload(monkeypatch) -> None:
    client = MissionControlDaemonClient(base_url="http://127.0.0.1:8010", timeout=0.1)
    monkeypatch.setattr(client, "get_plan", lambda project_id: None)

    payload = client.read_resource("mission-control://projects/7/plan")

    assert payload == {
        "project_id": 7,
        "exists": False,
        "status": None,
        "version": None,
        "summary_json": None,
        "content_markdown": None,
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
