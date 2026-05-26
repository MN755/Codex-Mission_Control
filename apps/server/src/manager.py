from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app_profile import display_name_or_default, get_or_create_app_profile, update_app_profile
from capabilities import CAPABILITY_CATEGORIES, capability_service
from codex_auth import auth_service
from codex_runner.app_server_runner import AppServerCodexRunner
from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerSettings
from codex_runner.claude_code_runner import ClaudeCodeRunner
from codex_runner.cli_runner import CliCodexRunner
from codex_runner.dry_run_runner import DryRunRunner
from codex_runner.external_adapter_runner import ExternalAdapterRunner
from config import (
    DEFAULT_APPROVAL_POLICY,
    DEFAULT_MANAGER_MODE,
    DEFAULT_RUNNER_MODE,
    DEFAULT_SANDBOX,
    WORKTREE_ROOT,
)
from context_packs import context_pack_service
from device_profile import recommended_swarm_max_agents
from events import EventService
from intelligence import planning_intelligence_service, reputation_service, scope_creep_service
from interview import INTERVIEW_CATEGORIES, select_fallback_questions
from diagnostics import list_diagnostic_reports
from imported_codebase import import_service
from models import (
    Agent,
    AgentArchetype,
    AgentRun,
    AgentInstructionsStatus,
    AppProfile,
    AppEvent,
    ApprovalRequest,
    AgentContract,
    AgentExecutionTrace,
    AgentStuckSignal,
    ChangeRequest,
    ConflictRecord,
    DecisionRecord,
    CodebaseMap,
    CodebaseUnderstanding,
    EvidenceBasedHandoff,
    HandoffEvidence,
    ImportedCodebaseSafety,
    InterviewQuestion,
    InterviewSession,
    HandoffQualityPreference,
    ManagerMessage,
    ManagerAssumption,
    ManagerQuestion,
    ModelPolicy,
    PathReservation,
    PathLock,
    Plan,
    Project,
    ProjectConfidence,
    ProjectEvent,
    ProjectSnapshot,
    ProjectSettings,
    ProjectTimelineEvent,
    ProjectUnderstanding,
    RecoveryPlan,
    RepoIntelligenceSummary,
    ReviewGate,
    Runbook,
    SandboxProfile,
    SwarmBudget,
    SwarmAgentSpec,
    SwarmEvent,
    SwarmPlan,
    SwarmPreferences,
    Task,
    ToolRoutingPolicy,
    ValidationRecipe,
    WidgetDefinition,
    WidgetInstance,
    AgentLoadSnapshot,
    utc_now,
)
from playbooks import playbook_service
from preferences import preference_service
from planner import build_plan_markdown
from project_settings import (
    ResolvedRunSettings,
    get_or_create_project_settings,
    normalize_provider_adapter_settings,
    normalize_provider_endpoint,
    resolve_manager_settings,
    resolve_worker_settings,
    resolved_run_settings_payload,
    settings_summary,
)
from prompts import (
    MANAGER_DOC_UPDATE_SCHEMA,
    MANAGER_HANDOFF_SCHEMA,
    MANAGER_INTERVIEW_SCHEMA,
    MANAGER_PLAN_SCHEMA,
    MANAGER_SWARM_PLAN_SCHEMA,
    MANAGER_TASK_DECOMPOSITION_SCHEMA,
    MANAGER_WORKER_DECISION_SCHEMA,
    docs_manifest_path,
    manager_action_prompt,
    manager_interview_prompt,
    manager_message_prompt,
    manager_swarm_prompt,
)
from provider_support import default_label, normalize_provider, provider_label, provider_uses_adapter
from risk import risk_service
from security import redact_text, redact_value, security_service
from security.path_validation import resolve_local_path, resolve_relative_to_root
from schemas import (
    AppProfileUpdate,
    ManagerDocFile,
    ManagerDocUpdate,
    ManagerHandoff,
    ManagerPlan,
    ManagerTaskDecomposition,
    ManagerTaskItem,
    ManagerWorkerDecision,
    ProjectSettingsUpdate,
    SwarmPreferencesUpdate,
    WorkerReport,
)
from swarm import AGENT_ARCHETYPE_CATALOG, SWARM_RISK_LEVELS
from simulation import simulation_service
from task_board import build_initial_tasks, can_assign_task, conflicting_agents, paths_conflict
from tool_catalog import TOOL_CATALOG, catalog_with_permissions
from validation_coverage import validation_coverage_service
from widget_catalog import (
    DASHBOARD_WIDGET_DEFAULTS,
    DASHBOARD_WIDGET_TYPES,
    PROJECT_WIDGET_DEFAULTS,
    PROJECT_WIDGET_TYPES,
    WIDGET_CATALOG,
    WIDGET_CATALOG_BY_TYPE,
    validate_widget_types,
)


DOC_FILENAMES = [
    "PROJECT_BRIEF.md",
    "PRODUCT_VISION.md",
    "USER_GOALS.md",
    "MVP_SCOPE.md",
    "ARCHITECTURE_NOTES.md",
    "RISKS_AND_UNKNOWNS.md",
    "AGENT_PLAN.md",
    "TASK_BOARD.md",
]
TASK_OPEN_STATUSES = {"backlog", "assigned", "working", "waiting_on_paths", "needs_review", "blocked"}
TASK_STARTABLE_STATUSES = {"backlog", "assigned", "waiting_on_paths"}
WORKSPACE_WIDGETS = [
    "Milestones",
    "Test Status",
    "Changed Files",
    "Artifacts",
    "Path Locks",
    "Model Usage",
    "Connected Tools",
    "Recent Decisions",
    "Handoff Progress",
]
WORKFLOW_PHASES = [
    ("intake", "Intake"),
    ("interview", "Interview"),
    ("plan_review", "Plan Review"),
    ("build", "Build"),
    ("validation", "Validation"),
    ("handoff", "Handoff"),
]
OVERVIEW_SECTIONS = [
    ("architecture", "Architecture"),
    ("frontend", "Frontend"),
    ("backend", "Backend"),
    ("auth_security", "Auth & Security"),
    ("testing", "Testing"),
    ("documentation", "Documentation"),
]
SWARM_DEFAULT_PREFERENCES = {
    "optimization_mode": "balanced",
    "swarm_aggressiveness": "medium",
    "max_agents": 8,
    "require_approval_above_agent_count": 10,
    "allow_dynamic_spawning": True,
    "allow_dynamic_retirement": True,
    "docs_depth": "standard",
    "testing_depth": "standard",
}
DASHBOARD_WIDGETS = [
    "Needs Attention",
    "Active Builds",
    "Recent Handoffs",
    "Runner & Provider Status",
    "Connected Accounts",
    "Model Defaults",
    "Blocked Agents",
    "Diagnostics Summary",
]
DASHBOARD_DEFAULT_WIDGETS = [
    "Needs Attention",
    "Active Builds",
    "Recent Handoffs",
    "Runner & Provider Status",
]
WIDGET_EMPTY_STATE = "Select the plus symbol in the bottom-right corner to add customizable widgets!"
INTERVIEW_CATEGORY_SET = set(INTERVIEW_CATEGORIES)
DISPLAY_STATUS_PRIORITY = {
    "blocked": 0,
    "error": 0,
    "running": 1,
    "coding": 1,
    "active": 1,
    "thinking": 2,
    "reviewing": 2,
    "monitoring": 2,
    "waiting": 3,
    "idle": 4,
    "retired": 5,
}
ATTENTION_PRIORITY = {
    "error": 0,
    "blocker": 1,
    "command_approval": 2,
    "tool_approval": 2,
    "manager_question": 3,
    "handoff_ready": 4,
    "degraded": 5,
}
SWARM_COORDINATION_PRIORITY = {"low": 0, "medium": 1, "high": 2}
TManagerModel = TypeVar("TManagerModel", bound=BaseModel)


def _dump_model(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _validate_model(schema: type[TManagerModel], payload: dict[str, Any]) -> TManagerModel:
    if hasattr(schema, "model_validate"):
        return schema.model_validate(payload)  # type: ignore[attr-defined]
    return schema.parse_obj(payload)  # type: ignore[attr-defined]


class InterviewGeneration(BaseModel):
    questions: list[dict[str, Any]]


class InterviewUnderstandingPayload(BaseModel):
    summary: str
    known_facts: dict[str, Any] = Field(default_factory=dict)
    unknowns: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    confidence_by_category: dict[str, float] = Field(default_factory=dict)


class InterviewTurnQuestion(BaseModel):
    question: str
    why: str
    category: str
    impact: str
    options: list[dict[str, str]] = Field(default_factory=list)
    allow_custom_answer: bool = False
    affects: list[str] = Field(default_factory=list)


class InterviewTurnPayload(BaseModel):
    understanding: InterviewUnderstandingPayload
    next_questions: list[InterviewTurnQuestion] = Field(default_factory=list)
    more_questions_needed: bool = False
    stop_reason: str | None = None


class ManagerSwarmSpecPayload(BaseModel):
    archetype: str
    name: str
    mission: str
    model_policy: str
    toolset: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=list)
    spawn_phase: str = "build_start"
    retire_when: str
    priority: int = 50


class ManagerSwarmPlanPayload(BaseModel):
    mode: str
    goal: str
    recommended_agent_count: int
    coordination_risk: str
    path_conflict_risk: str
    expected_bottlenecks: list[str] = Field(default_factory=list)
    strategy_summary: str
    validation_strategy: list[str] = Field(default_factory=list)
    specs: list[ManagerSwarmSpecPayload] = Field(default_factory=list)


class RunnerRegistry:
    def __init__(self) -> None:
        self.runners: dict[str, BaseCodexRunner] = {
            "dry_run": DryRunRunner(),
            "codex_cli": CliCodexRunner(),
            "codex_app_server": AppServerCodexRunner(),
            "claude_code_cli": ClaudeCodeRunner(),
            "external_adapter": ExternalAdapterRunner(),
        }
        self._auto_app_server_enabled: bool | None = None
        self._codex_cli_enabled: bool | None = None
        self._claude_cli_enabled: bool | None = None

    async def codex_cli_available(self) -> bool:
        if self._codex_cli_enabled is not True:
            self._codex_cli_enabled = await self.runners["codex_cli"].handshake()
        return self._codex_cli_enabled

    async def app_server_available(self) -> bool:
        if self._auto_app_server_enabled is not True:
            self._auto_app_server_enabled = await self.runners["codex_app_server"].handshake()
        return self._auto_app_server_enabled

    async def claude_cli_available(self) -> bool:
        if self._claude_cli_enabled is not True:
            self._claude_cli_enabled = await self.runners["claude_code_cli"].handshake()
        return self._claude_cli_enabled

    async def effective_runner_type(self, resolved: ResolvedRunSettings) -> str:
        provider = normalize_provider(resolved.provider)
        requested_mode = resolved.runner_mode or DEFAULT_RUNNER_MODE
        if requested_mode == "dry_run":
            return "dry_run"
        if provider == "codex":
            if requested_mode == "app_server":
                return "codex_app_server" if await self.app_server_available() else "unavailable"
            if requested_mode == "cli":
                return "codex_cli" if await self.codex_cli_available() else "unavailable"
            if requested_mode == "auto":
                if await self.app_server_available():
                    return "codex_app_server"
                if await self.codex_cli_available():
                    return "codex_cli"
                return "unavailable"
        if provider == "claude_code":
            if requested_mode == "app_server":
                return "unavailable"
            if requested_mode in {"auto", "cli"}:
                return "claude_code_cli" if await self.claude_cli_available() else "unavailable"
        if provider_uses_adapter(provider):
            if requested_mode == "app_server":
                return "unavailable"
            if requested_mode in {"auto", "cli"}:
                return "external_adapter" if await self.runners["external_adapter"].handshake(
                    RunnerSettings(
                        provider=resolved.provider,
                        sandbox_mode=resolved.sandbox_mode,
                        approval_policy=resolved.approval_policy,
                        model=resolved.model,
                        reasoning_effort=resolved.reasoning_effort,
                        provider_endpoint=resolved.provider_endpoint,
                        adapter_command=resolved.adapter_command,
                        adapter_args=list(resolved.adapter_args),
                    )
                ) else "unavailable"
        return "unavailable"

    async def effective_mode(self, resolved: ResolvedRunSettings) -> str:
        runner_type = await self.effective_runner_type(resolved)
        if runner_type == "codex_app_server":
            return "app_server"
        if runner_type in {"codex_cli", "claude_code_cli", "external_adapter"}:
            return "cli"
        if runner_type == "dry_run":
            return "dry_run"
        return "unavailable"

    async def get_runner_for_settings(self, resolved: ResolvedRunSettings) -> BaseCodexRunner:
        runner_type = await self.effective_runner_type(resolved)
        if runner_type == "unavailable":
            raise RuntimeError(f"No available runner for provider {resolved.provider} in mode {resolved.runner_mode}.")
        return self.runners[runner_type]

    async def get_runner(self, runner_type: str) -> BaseCodexRunner:
        if runner_type in self.runners:
            return self.runners[runner_type]
        if runner_type == "cli":
            return self.runners["codex_cli"]
        if runner_type == "app_server":
            return self.runners["codex_app_server"]
        raise KeyError(f"Unknown runner type: {runner_type}")

    async def inventory(self) -> list[dict[str, Any]]:
        codex_cli_ready = await self.codex_cli_available()
        app_server_ready = await self.app_server_available()
        claude_ready = await self.claude_cli_available()
        return [
            {
                "runner_type": "dry_run",
                "availability": True,
                "config_status": "ready",
                "supports_background": True,
                "supports_streaming": True,
                "supports_approvals": True,
                "notes": ["Always available for offline orchestration simulation."],
            },
            {
                "runner_type": "codex_cli",
                "availability": codex_cli_ready,
                "config_status": "ready" if codex_cli_ready else "missing_or_not_logged_in",
                "supports_background": True,
                "supports_streaming": False,
                "supports_approvals": True,
                "notes": ["Uses the local Codex CLI session and approval flow."],
            },
            {
                "runner_type": "codex_app_server",
                "availability": app_server_ready,
                "config_status": "ready" if app_server_ready else "experimental_or_unavailable",
                "supports_background": True,
                "supports_streaming": True,
                "supports_approvals": True,
                "notes": ["Experimental app-server path for Codex-backed background work."],
            },
            {
                "runner_type": "claude_code_cli",
                "availability": claude_ready,
                "config_status": "ready" if claude_ready else "missing_or_unavailable",
                "supports_background": True,
                "supports_streaming": False,
                "supports_approvals": True,
                "notes": ["Uses the locally configured Claude Code CLI when available."],
            },
            {
                "runner_type": "external_adapter",
                "availability": False,
                "config_status": "requires_project_settings",
                "supports_background": True,
                "supports_streaming": False,
                "supports_approvals": True,
                "notes": ["Availability depends on the project's configured adapter command."],
            },
        ]


class MissionControlService:
    def __init__(self) -> None:
        self.events = EventService()
        self.runners = RunnerRegistry()
        self.active_monitors: dict[int, asyncio.Task] = {}
        self.run_input_snapshots: dict[int, dict[str, str]] = {}

    async def on_shutdown(self) -> None:
        active = list(self.active_monitors.values())
        self.active_monitors.clear()
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)

    def _project_docs_dir(self, project: Project) -> Path:
        return Path(project.workspace_path) / "mission-control"

    def _task_workspace_snapshot(self, project: Project, task: Task | None) -> dict[str, str]:
        root = Path(project.workspace_path)
        if not root.exists():
            return {}
        allowed_paths = list(task.allowed_paths_json or []) if task else []
        if not allowed_paths:
            allowed_paths = ["."]
        ignored = {"__pycache__", ".git", "node_modules", ".venv", "venv", "mission-control"}
        snapshot: dict[str, str] = {}
        captured = 0
        resolved_root = root.resolve()
        for relative in allowed_paths:
            candidate = (resolved_root / relative).resolve() if relative not in {"", "."} else resolved_root
            try:
                candidate.relative_to(resolved_root)
            except ValueError:
                continue
            if not candidate.exists():
                continue
            files = [candidate] if candidate.is_file() else [path for path in candidate.rglob("*") if path.is_file()]
            for file_path in files:
                if any(part in ignored for part in file_path.parts):
                    continue
                rel_path = file_path.relative_to(resolved_root).as_posix()
                try:
                    digest = hashlib.sha1(file_path.read_bytes()).hexdigest()
                except OSError:
                    continue
                snapshot[rel_path] = digest
                captured += 1
                if captured >= 250:
                    return snapshot
        return snapshot

    def _task_expects_file_changes(self, task: Task | None) -> bool:
        if task is None:
            return False
        text = " ".join(filter(None, [task.title, task.goal, task.scope])).lower()
        tokens = {token for token in re.split(r"[^a-z0-9]+", text) if token}
        edit_markers = {"fix", "implement", "edit", "change", "update", "build", "write", "correct"}
        non_edit_markers = {"reproduce", "validate", "validation", "handoff", "review", "document"}
        return bool(tokens & edit_markers) and not bool(tokens & non_edit_markers)

    def _verify_worker_report_evidence(self, project: Project, task: Task | None, report: WorkerReport, before_snapshot: dict[str, str] | None) -> WorkerReport:
        if task is None or report.status not in {"done", "needs_review"}:
            return report
        before = before_snapshot or {}
        after = self._task_workspace_snapshot(project, task)
        changed_paths = sorted(
            {
                *[path for path, digest in after.items() if before.get(path) != digest],
                *[path for path in before if path not in after],
            }
        )
        verified_claims = [
            path
            for path in report.files_changed
            if path in changed_paths or any(changed.endswith(path) or path.endswith(changed) for changed in changed_paths)
        ]
        if report.files_changed and verified_claims != list(report.files_changed):
            report = report.model_copy(update={"files_changed": verified_claims})
        if self._task_expects_file_changes(task) and not changed_paths:
            risks = list(report.risks or [])
            warning = "Mission Control could not verify any workspace file changes for this run."
            if warning not in risks:
                risks.append(warning)
            return report.model_copy(
                update={
                    "status": "needs_review",
                    "summary": f"{report.summary} Mission Control could not verify any workspace file changes for this claimed implementation step.",
                    "files_changed": [],
                    "risks": risks,
                }
            )
        if changed_paths and not report.files_changed and self._task_expects_file_changes(task):
            report = report.model_copy(update={"files_changed": changed_paths[:20]})
        return report

    def _ensure_project_workspace(self, project: Project) -> Path:
        docs_dir = self._project_docs_dir(project)
        docs_dir.mkdir(parents=True, exist_ok=True)
        project.docs_path = str(docs_dir)
        return docs_dir

    def _latest_plan(self, db: Session, project_id: int) -> Plan | None:
        return db.scalar(select(Plan).where(Plan.project_id == project_id).order_by(Plan.version.desc()))

    def _latest_session(self, db: Session, project_id: int) -> InterviewSession | None:
        return db.scalar(select(InterviewSession).where(InterviewSession.project_id == project_id).order_by(InterviewSession.id.desc()))

    def _manager_agent(self, db: Session, project_id: int) -> Agent:
        manager_agent = db.scalar(select(Agent).where(Agent.project_id == project_id, Agent.kind == "manager"))
        if not manager_agent:
            raise ValueError("Manager agent not found")
        return manager_agent

    def _project_settings(self, db: Session, project: Project) -> ProjectSet...