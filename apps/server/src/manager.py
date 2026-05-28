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
    OrchestrationSession,
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
WIDGET_AREAS_BY_SCOPE = {
    "dashboard": {"dashboard_main", "dashboard_right", "dashboard_bottom", "dashboard_custom"},
    "project": {"project_right_sidebar", "project_bottom", "project_overview", "project_custom"},
}
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

    def _project_settings(self, db: Session, project: Project) -> ProjectSettings:
        if project.settings is not None:
            return project.settings
        profile = self._app_profile(db)
        timestamp = utc_now()
        return ProjectSettings(
            project_id=project.id,
            provider=normalize_provider(profile.selected_provider or "codex"),
            manager_model=profile.manager_model,
            default_worker_model=profile.default_worker_model,
            manager_reasoning_effort=profile.manager_reasoning_effort,
            default_worker_reasoning_effort=profile.default_worker_reasoning_effort,
            per_role_model_overrides_json={},
            per_role_reasoning_overrides_json={},
            adapter_command=profile.adapter_command,
            adapter_args_json=list(profile.adapter_args_json or []),
            runner_mode=project.runner_mode or profile.default_runner_mode or DEFAULT_RUNNER_MODE,
            sandbox_mode=profile.sandbox_mode,
            approval_policy=profile.approval_policy,
            workspace_widgets_json=[],
            approval_overrides_json={},
            created_at=timestamp,
            updated_at=timestamp,
        )

    def _ensure_project_settings(self, db: Session, project: Project) -> ProjectSettings:
        return get_or_create_project_settings(db, project)

    def _app_profile_preview(self, db: Session) -> AppProfile:
        profile = db.get(AppProfile, 1)
        if profile is not None:
            return profile
        timestamp = utc_now()
        return AppProfile(
            id=1,
            display_name=None,
            install_id=None,
            preferred_provider_choice="codex",
            preferred_start_mode="new_project",
            selected_provider="codex",
            auth_mode=None,
            connected_accounts_json={},
            first_run_completed=False,
            setup_version_completed=None,
            onboarding_completed=False,
            default_runner_mode=DEFAULT_RUNNER_MODE,
            manager_model=None,
            default_worker_model=None,
            manager_reasoning_effort=None,
            default_worker_reasoning_effort=None,
            sandbox_mode=DEFAULT_SANDBOX,
            approval_policy=DEFAULT_APPROVAL_POLICY,
            theme="system",
            startup_behavior="dashboard",
            notification_preferences_json={},
            dashboard_widgets_json=[],
            dashboard_widget_preferences_json={},
            tool_permission_overrides_json={},
            provider_endpoint=None,
            adapter_command=None,
            adapter_args_json=[],
            recent_startup_error_json=None,
            created_at=timestamp,
            updated_at=timestamp,
            last_opened_at=timestamp,
        )

    def _project_settings_preview(self, db: Session, project: Project) -> ProjectSettings:
        if project.settings is not None:
            return project.settings
        profile = self._app_profile_preview(db)
        timestamp = utc_now()
        return ProjectSettings(
            project_id=project.id,
            provider=normalize_provider(profile.selected_provider or "codex"),
            manager_model=profile.manager_model,
            default_worker_model=profile.default_worker_model,
            manager_reasoning_effort=profile.manager_reasoning_effort,
            default_worker_reasoning_effort=profile.default_worker_reasoning_effort,
            per_role_model_overrides_json={},
            per_role_reasoning_overrides_json={},
            adapter_command=profile.adapter_command,
            adapter_args_json=list(profile.adapter_args_json or []),
            runner_mode=project.runner_mode or profile.default_runner_mode or DEFAULT_RUNNER_MODE,
            sandbox_mode=profile.sandbox_mode,
            approval_policy=profile.approval_policy,
            workspace_widgets_json=[],
            approval_overrides_json={},
            created_at=timestamp,
            updated_at=timestamp,
        )

    def _swarm_preferences(self, project: Project) -> SwarmPreferences:
        if project.swarm_preferences is not None:
            return project.swarm_preferences
        timestamp = utc_now()
        return SwarmPreferences(
            project_id=project.id,
            optimization_mode=SWARM_DEFAULT_PREFERENCES["optimization_mode"],
            swarm_aggressiveness=SWARM_DEFAULT_PREFERENCES["swarm_aggressiveness"],
            max_agents=SWARM_DEFAULT_PREFERENCES["max_agents"],
            require_approval_above_agent_count=SWARM_DEFAULT_PREFERENCES["require_approval_above_agent_count"],
            allow_dynamic_spawning=SWARM_DEFAULT_PREFERENCES["allow_dynamic_spawning"],
            allow_dynamic_retirement=SWARM_DEFAULT_PREFERENCES["allow_dynamic_retirement"],
            docs_depth=SWARM_DEFAULT_PREFERENCES["docs_depth"],
            testing_depth=SWARM_DEFAULT_PREFERENCES["testing_depth"],
            created_at=timestamp,
            updated_at=timestamp,
        )

    def _ensure_swarm_preferences(self, db: Session, project: Project) -> SwarmPreferences:
        preferences = project.swarm_preferences
        if preferences is not None:
            return preferences
        preferences = self._swarm_preferences(project)
        db.add(preferences)
        db.flush()
        project.swarm_preferences = preferences
        return preferences

    def _serialize_swarm_preferences(self, preferences: SwarmPreferences) -> dict[str, Any]:
        return {
            "project_id": preferences.project_id,
            "optimization_mode": preferences.optimization_mode,
            "swarm_aggressiveness": preferences.swarm_aggressiveness,
            "max_agents": preferences.max_agents,
            "require_approval_above_agent_count": preferences.require_approval_above_agent_count,
            "allow_dynamic_spawning": preferences.allow_dynamic_spawning,
            "allow_dynamic_retirement": preferences.allow_dynamic_retirement,
            "docs_depth": preferences.docs_depth,
            "testing_depth": preferences.testing_depth,
            "created_at": preferences.created_at,
            "updated_at": preferences.updated_at,
        }

    def _ensure_agent_archetypes(self, db: Session) -> list[AgentArchetype]:
        existing = {entry.name: entry for entry in db.scalars(select(AgentArchetype).order_by(AgentArchetype.name.asc()))}
        created = False
        for payload in AGENT_ARCHETYPE_CATALOG:
            entry = existing.get(str(payload["name"]))
            if entry is None:
                entry = AgentArchetype(name=str(payload["name"]))
                db.add(entry)
                existing[entry.name] = entry
                created = True
            entry.purpose = str(payload["purpose"])
            entry.default_guidelines = str(payload["default_guidelines"])
            entry.default_tools_json = list(payload.get("default_tools_json") or [])
            entry.default_permissions_json = dict(payload.get("default_permissions_json") or {})
            entry.spawn_triggers_json = list(payload.get("spawn_triggers_json") or [])
            entry.retirement_triggers_json = list(payload.get("retirement_triggers_json") or [])
            entry.risk_profile = str(payload.get("risk_profile") or "medium")
        if created:
            db.flush()
        return sorted(existing.values(), key=lambda item: item.name.lower())

    def _agent_archetypes_preview(self) -> list[AgentArchetype]:
        return [
            AgentArchetype(
                name=str(payload["name"]),
                purpose=str(payload["purpose"]),
                default_guidelines=str(payload["default_guidelines"]),
                default_tools_json=list(payload.get("default_tools_json") or []),
                default_permissions_json=dict(payload.get("default_permissions_json") or {}),
                spawn_triggers_json=list(payload.get("spawn_triggers_json") or []),
                retirement_triggers_json=list(payload.get("retirement_triggers_json") or []),
                risk_profile=str(payload.get("risk_profile") or "medium"),
            )
            for payload in AGENT_ARCHETYPE_CATALOG
        ]

    def _archetype_lookup(self, db: Session) -> dict[str, AgentArchetype]:
        return {entry.name: entry for entry in self._ensure_agent_archetypes(db)}

    def _archetype_lookup_preview(self) -> dict[str, AgentArchetype]:
        return {entry.name: entry for entry in self._agent_archetypes_preview()}

    def _app_profile(self, db: Session) -> AppProfile:
        return get_or_create_app_profile(db)

    def _preferred_user_name(self, db: Session, project: Project | None = None) -> str:
        profile = self._app_profile(db)
        if profile.display_name:
            return display_name_or_default(profile.display_name)
        if project and project.created_by:
            return display_name_or_default(project.created_by)
        return display_name_or_default(None)

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
        return slug or "project"

    def _effective_project_slug(self, project: Project) -> str:
        return project.slug or self._slugify(project.name)

    def _ensure_project_slug(self, project: Project) -> str:
        if not project.slug:
            project.slug = self._slugify(project.name)
        return project.slug

    def _project_route(self, project: Project) -> str:
        slug = self._effective_project_slug(project)
        return f"/projects/{project.id}/{slug}" if slug else f"/projects/{project.id}"

    def _project_understanding(self, project: Project) -> ProjectUnderstanding:
        if project.understanding is not None:
            return project.understanding
        return ProjectUnderstanding(
            project_id=project.id,
            summary="",
            known_facts_json={},
            unknowns_json={},
            assumptions_json=[],
            constraints_json=[],
            confidence_by_category_json={},
            updated_at=utc_now(),
        )

    def _ensure_project_understanding(self, db: Session, project: Project) -> ProjectUnderstanding:
        understanding = project.understanding
        if understanding is not None:
            return understanding
        understanding = ProjectUnderstanding(
            project_id=project.id,
            summary="",
            known_facts_json={},
            unknowns_json={},
            assumptions_json=[],
            constraints_json=[],
            confidence_by_category_json={},
            updated_at=utc_now(),
        )
        db.add(understanding)
        db.flush()
        project.understanding = understanding
        return understanding

    @staticmethod
    def _normalize_interview_budget(question_budget: int | None, legacy_question_count: int | None = None) -> int:
        raw_value = question_budget if question_budget is not None else legacy_question_count
        if raw_value is None:
            return 20
        return max(0, min(500, int(raw_value)))

    @staticmethod
    def _normalize_confidence_map(payload: dict[str, Any] | None) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for key, value in (payload or {}).items():
            key_text = str(key).strip()
            if not key_text:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            normalized[key_text] = max(0.0, min(1.0, numeric))
        return normalized

    @staticmethod
    def _normalize_string_list(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [str(item).strip() for item in values if str(item).strip()]

    @staticmethod
    def _normalize_mapping_payload(values: Any) -> dict[str, Any]:
        if not isinstance(values, dict):
            return {}
        normalized: dict[str, Any] = {}
        for key, value in values.items():
            key_text = str(key).strip()
            if not key_text:
                continue
            normalized[key_text] = value
        return normalized

    @staticmethod
    def _question_answer_text(question: InterviewQuestion) -> str:
        if question.custom_answer:
            return question.custom_answer.strip()
        return (question.selected_text or "").strip()

    @staticmethod
    def _answered_interview_questions(session: InterviewSession) -> list[InterviewQuestion]:
        return [question for question in session.questions if question.status == "answered" or question.selected_option_id or question.selected_option]

    @staticmethod
    def _pending_interview_questions(session: InterviewSession) -> list[InterviewQuestion]:
        return sorted(
            [
                question
                for question in session.questions
                if question.status == "pending" and not question.selected_option_id and not question.selected_option
            ],
            key=lambda item: item.index,
        )

    def _default_understanding_payload(self, project: Project, *, question_budget: int) -> InterviewUnderstandingPayload:
        return InterviewUnderstandingPayload(
            summary=f"The manager is refining the project understanding for {project.name}.",
            known_facts={
                "project": [
                    {"label": "Project title", "value": project.name},
                    {"label": "Raw idea", "value": project.idea},
                ]
            },
            unknowns={
                "priority": [
                    "The best first user-facing slice is not fully confirmed yet.",
                    "Architecture and validation depth still depend on interview answers.",
                ]
            },
            assumptions=(["The manager will proceed with explicit assumptions because the question budget is zero."] if question_budget == 0 else []),
            constraints=[
                f"Runner mode preference: {project.runner_mode}",
                f"Manager mode preference: {project.manager_mode}",
            ],
            confidence_by_category={},
        )

    def _project_docs_summary(self, project: Project) -> dict[str, Any]:
        docs_root = Path(project.docs_path) if project.docs_path else self._project_docs_dir(project)
        if not docs_root.exists():
            return {"docs_present": False, "snippets": []}

        snippets: list[dict[str, str]] = []
        for filename in ("PROJECT_BRIEF.md", "PRODUCT_VISION.md", "MVP_SCOPE.md", "ARCHITECTURE_NOTES.md", "README.md"):
            path = docs_root / filename
            if not path.exists() or not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                continue
            if not content:
                continue
            snippets.append({"filename": filename, "excerpt": content[:700]})
            if len(snippets) >= 3:
                break
        return {"docs_present": bool(snippets), "snippets": snippets}

    def _workspace_manifest_summary(self, project: Project) -> dict[str, Any]:
        workspace = Path(project.workspace_path)
        if not workspace.exists():
            return {"exists": False, "detected_files": [], "top_level_directories": [], "entry_count": 0}
        detected_files = [
            name
            for name in (
                "README.md",
                "package.json",
                "vite.config.ts",
                "vite.config.js",
                "pyproject.toml",
                "requirements.txt",
                "Cargo.toml",
                "go.mod",
                "docker-compose.yml",
                "Dockerfile",
            )
            if (workspace / name).exists()
        ]
        top_level_directories = sorted(
            [
                item.name
                for item in workspace.iterdir()
                if item.is_dir() and item.name not in {".git", ".venv", "node_modules", "__pycache__"}
            ]
        )[:12]
        return {
            "exists": True,
            "detected_files": detected_files,
            "top_level_directories": top_level_directories,
            "entry_count": len(top_level_directories) + len(detected_files),
        }

    async def _interview_context_payload(self, db: Session, project: Project, session: InterviewSession | None = None) -> dict[str, Any]:
        settings = self._project_settings(db, project)
        status = await self.get_system_status(db, project)
        tool_catalog = self.get_tool_catalog(db)
        understanding = self._project_understanding(project)
        active_session = session or self._latest_session(db, project.id)
        answered_questions = []
        if active_session is not None:
            answered_questions = [
                {
                    "index": question.index,
                    "question": question.question,
                    "category": question.category,
                    "answer": self._question_answer_text(question),
                    "selected_option_id": question.selected_option_id or question.selected_option,
                }
                for question in sorted(self._answered_interview_questions(active_session), key=lambda item: item.index)
            ]

        provider_status = next(
            (
                item
                for item in status.get("provider_statuses", [])
                if str(item.get("provider")) == str(status.get("selected_provider"))
            ),
            {},
        )
        return {
            "project_title": project.name,
            "raw_idea": project.idea,
            "workspace_path": project.workspace_path,
            "docs_path": project.docs_path,
            "existing_docs_summary": self._project_docs_summary(project),
            "workspace_manifest_summary": self._workspace_manifest_summary(project),
            "settings": {
                "provider": settings.provider,
                "manager_model": settings.manager_model,
                "default_worker_model": settings.default_worker_model,
                "manager_reasoning_effort": settings.manager_reasoning_effort,
                "default_worker_reasoning_effort": settings.default_worker_reasoning_effort,
                "runner_mode": settings.runner_mode,
                "sandbox_mode": settings.sandbox_mode,
                "approval_policy": settings.approval_policy,
            },
            "available_tools": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "availability": item["availability"],
                    "permission_policy": item["permission_policy"],
                    "risk_level": item["risk_level"],
                }
                for item in tool_catalog
            ],
            "provider_status": {
                "selected_provider": status.get("selected_provider"),
                "selected_manager_model": status.get("selected_manager_model"),
                "selected_default_worker_model": status.get("selected_default_worker_model"),
                "effective_runner_mode": status.get("effective_runner_mode"),
                "authenticated": status.get("authenticated"),
                "available_models": list(status.get("available_models", [])),
                "provider_notes": list(provider_status.get("notes", [])) if isinstance(provider_status, dict) else [],
            },
            "previous_answers": answered_questions,
            "known_facts": dict(understanding.known_facts_json or {}),
            "unknowns": dict(understanding.unknowns_json or {}),
            "assumptions": list(understanding.assumptions_json or []),
            "constraints": list(understanding.constraints_json or []),
            "confidence_by_category": dict(understanding.confidence_by_category_json or {}),
        }

    async def _swarm_context_payload(self, db: Session, project: Project, preferences: SwarmPreferences) -> dict[str, Any]:
        settings = self._project_settings(db, project)
        understanding = self._project_understanding(project)
        latest_plan = self._latest_plan(db, project.id)
        manifest = self._workspace_manifest_summary(project)
        status = await self.get_system_status(db, project)
        current_agents = [
            {
                "name": agent.name,
                "archetype": agent.archetype,
                "status": agent.status,
                "mission": agent.mission,
                "locked_paths": list(agent.locked_paths_json or []),
            }
            for agent in db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker").order_by(Agent.id.asc()))
        ]
        return {
            "project": {
                "name": project.name,
                "idea": project.idea,
                "status": project.status,
                "workspace_path": project.workspace_path,
                "docs_path": project.docs_path,
                "latest_milestone": project.latest_milestone,
            },
            "preferences": self._serialize_swarm_preferences(preferences),
            "settings": {
                "provider": settings.provider,
                "runner_mode": settings.runner_mode,
                "sandbox_mode": settings.sandbox_mode,
                "approval_policy": settings.approval_policy,
                "manager_model": settings.manager_model,
                "default_worker_model": settings.default_worker_model,
            },
            "understanding": self.get_project_understanding(project),
            "docs_summary": self._project_docs_summary(project),
            "repo_summary": manifest,
            "plan_summary": latest_plan.summary_json if latest_plan else None,
            "available_tools": [
                {
                    "id": item["id"],
                    "availability": item["availability"],
                    "permission_policy": item["permission_policy"],
                    "risk_level": item["risk_level"],
                }
                for item in self.get_tool_catalog(db)
            ],
            "provider_status": {
                "selected_provider": status.get("selected_provider"),
                "effective_runner_mode": status.get("effective_runner_mode"),
                "authenticated": status.get("authenticated"),
                "available_models": list(status.get("available_models", [])),
            },
            "current_agents": current_agents,
            "open_tasks": [
                {"title": task.title, "status": task.status, "agent_role": task.agent_role}
                for task in db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc()))
            ],
        }

    @staticmethod
    def _titleize_path_label(value: str) -> str:
        parts = [part for part in re.split(r"[^a-zA-Z0-9]+", value) if part]
        return " ".join(part[:1].upper() + part[1:] for part in parts) or "General"

    def _repo_path_buckets(self, manifest: dict[str, Any]) -> dict[str, list[str]]:
        directories = [str(item) for item in manifest.get("top_level_directories", []) if str(item).strip()]
        frontend = [item for item in directories if item.lower() in {"app", "src", "ui", "web", "frontend", "client", "components"}]
        backend = [item for item in directories if item.lower() in {"server", "backend", "api", "services", "worker"}]
        docs = [item for item in directories if "doc" in item.lower() or item.lower() in {"examples", "guides"}]
        tests = [item for item in directories if "test" in item.lower() or "spec" in item.lower() or item.lower() == "e2e"]
        data = [item for item in directories if item.lower() in {"data", "db", "database", "migrations", "sql"}]
        ops = [item for item in directories if item.lower() in {"ops", "infra", "deploy", "scripts", ".github"}]
        subsystems = [item for item in directories if item not in {".github"}][:5]
        if not frontend and "package.json" in manifest.get("detected_files", []):
            frontend = ["src"]
        if not backend and any(item in manifest.get("detected_files", []) for item in {"pyproject.toml", "requirements.txt", "go.mod"}):
            backend = ["server"]
        if not docs:
            docs = ["docs", "README.md"]
        if not tests:
            tests = ["tests"]
        return {
            "frontend": frontend[:3],
            "backend": backend[:3],
            "docs": docs[:5],
            "tests": tests[:3],
            "data": data[:3],
            "ops": ops[:3],
            "subsystems": subsystems[:5] or ["src"],
        }

    def _choose_swarm_mode(
        self,
        project: Project,
        preferences: SwarmPreferences,
        understanding: ProjectUnderstanding,
        manifest: dict[str, Any],
    ) -> str:
        if preferences.optimization_mode != "manager_decides":
            return preferences.optimization_mode
        idea = f"{project.name}\n{project.idea}".lower()
        unknowns = len(understanding.unknowns_json or {})
        if preferences.docs_depth in {"detailed", "publishable"} or any(token in idea for token in {"docs", "documentation", "guide", "developer portal"}):
            return "documentation_heavy"
        if preferences.testing_depth in {"extensive", "release_grade"} or any(token in idea for token in {"security", "auth", "payments", "compliance"}):
            return "high_quality"
        if len(manifest.get("top_level_directories", [])) >= 6:
            return "massive_codebase"
        if unknowns >= 3 or project.status in {"draft", "plan_ready"}:
            return "research_planning"
        if preferences.swarm_aggressiveness in {"large", "maximum"} or any(token in idea for token in {"mvp", "prototype", "ship fast", "quickly"}):
            return "fastest_build"
        return "balanced"

    def _swarm_capacity_limit(self, preferences: SwarmPreferences) -> int:
        aggressiveness_cap = {
            "small": 4,
            "medium": 6,
            "large": 8,
            "maximum": 12,
            "manager_decides": preferences.max_agents,
        }.get(preferences.swarm_aggressiveness, preferences.max_agents)
        return max(1, min(preferences.max_agents, aggressiveness_cap, recommended_swarm_max_agents()))

    def _make_swarm_spec(
        self,
        archetype: str,
        name: str,
        mission: str,
        model_policy: str,
        allowed_paths: list[str],
        forbidden_paths: list[str],
        spawn_phase: str,
        retire_when: str,
        priority: int,
        toolset: list[str] | None = None,
    ) -> ManagerSwarmSpecPayload:
        deduped_allowed: list[str] = []
        for item in allowed_paths:
            text = str(item).strip()
            if text and text not in deduped_allowed:
                deduped_allowed.append(text)
        deduped_forbidden: list[str] = []
        for item in forbidden_paths:
            text = str(item).strip()
            if text and text not in deduped_forbidden and text not in deduped_allowed:
                deduped_forbidden.append(text)
        return ManagerSwarmSpecPayload(
            archetype=archetype,
            name=name,
            mission=mission,
            model_policy=model_policy,
            toolset=list(toolset or []),
            allowed_paths=deduped_allowed,
            forbidden_paths=deduped_forbidden,
            spawn_phase=spawn_phase,
            retire_when=retire_when,
            priority=priority,
        )

    def _deterministic_swarm_plan(
        self,
        project: Project,
        preferences: SwarmPreferences,
        manifest: dict[str, Any],
        understanding: ProjectUnderstanding,
        latest_plan: Plan | None = None,
        *,
        intelligence_context: dict[str, Any] | None = None,
        goal_override: str | None = None,
        scale_hint: str | None = None,
    ) -> ManagerSwarmPlanPayload:
        intelligence_context = intelligence_context or {}
        mode = self._choose_swarm_mode(project, preferences, understanding, manifest)
        playbook = intelligence_context.get("playbook") or {}
        if preferences.optimization_mode == "manager_decides" and playbook.get("status") in {"suggested", "applied"}:
            playbook_key = playbook.get("key")
            if playbook_key in {"fastapi_react_web_app", "generic_custom", "local_desktop_app"}:
                mode = "balanced"
            elif playbook_key == "existing_repo_cleanup":
                mode = "massive_codebase"
            elif playbook_key in {"browser_extension", "data_ingestion_pipeline"}:
                mode = "high_quality"
            elif playbook_key in {"static_docs_site", "osint_dashboard"}:
                mode = "documentation_heavy"
            elif playbook_key == "ai_local_tool":
                mode = "research_planning"
        buckets = self._repo_path_buckets(manifest)
        capacity = self._swarm_capacity_limit(preferences)
        goal = goal_override or f"Plan the most useful worker swarm for {project.name} during {project.status}."
        specs: list[ManagerSwarmSpecPayload] = []
        bottlenecks: list[str] = []
        validation_strategy: list[str] = [
            "Keep validation aligned with the swarm mode and explicit project risk.",
            "Record what was actually tested, reviewed, or deferred.",
        ]

        def add(spec: ManagerSwarmSpecPayload) -> None:
            if len(specs) < capacity:
                specs.append(spec)

        def model_policy_for(category: str, fallback: str) -> str:
            recommendation = intelligence_context.get("model_policy_hints", {}).get(category)
            return str(recommendation or fallback)

        def frontend_paths() -> list[str]:
            return buckets["frontend"] or ["src"]

        def backend_paths() -> list[str]:
            return buckets["backend"] or ["server"]

        def docs_paths() -> list[str]:
            return buckets["docs"] or ["docs", "README.md"]

        def test_paths() -> list[str]:
            return buckets["tests"] or ["tests"]

        if mode == "fastest_build":
            add(
                self._make_swarm_spec(
                    archetype="feature",
                    name="Vertical Slice Builder",
                    mission="Own the first usable end-to-end slice and keep it runnable early.",
                    model_policy=model_policy_for("code_editing", "Prefer the default worker model with medium reasoning for fast iteration."),
                    allowed_paths=frontend_paths(),
                    forbidden_paths=docs_paths(),
                    spawn_phase="build_start",
                    retire_when="The first runnable vertical slice is merged and demoable.",
                    priority=10,
                    toolset=["feature_work", "tests"],
                )
            )
            add(
                self._make_swarm_spec(
                    archetype="backend",
                    name="Core Flow Builder",
                    mission="Implement the main backend or domain flow that unblocks the MVP path.",
                    model_policy=model_policy_for("bug_fixing", "Prefer the default worker model with medium reasoning."),
                    allowed_paths=backend_paths(),
                    forbidden_paths=docs_paths(),
                    spawn_phase="build_start",
                    retire_when="The core flow behind the vertical slice is stable.",
                    priority=15,
                    toolset=["api_editing", "tests"],
                )
            )
            add(
                self._make_swarm_spec(
                    archetype="integration",
                    name="Slice Integrator",
                    mission="Bridge UI and backend edges once the first slice exists.",
                    model_policy=model_policy_for("long_context_planning", "Prefer the default worker model with medium reasoning."),
                    allowed_paths=frontend_paths() + backend_paths(),
                    forbidden_paths=docs_paths(),
                    spawn_phase="after_first_slice",
                    retire_when="The primary workflow can be demonstrated without manual stitching.",
                    priority=25,
                    toolset=["integration_work"],
                )
            )
            add(
                self._make_swarm_spec(
                    archetype="test",
                    name="Smoke Test Runner",
                    mission="Validate the fast slice without slowing the build loop with excessive ceremony.",
                    model_policy=model_policy_for("test_generation", "Prefer a careful model only when commands need explanation."),
                    allowed_paths=test_paths(),
                    forbidden_paths=[],
                    spawn_phase="after_first_slice",
                    retire_when="Smoke validation is recorded and obvious breakages are fixed or documented.",
                    priority=35,
                    toolset=["test_runner", "smoke_checks"],
                )
            )
            bottlenecks.extend(
                [
                    "Parallel implementation will stall if UI and backend paths are not kept separate.",
                    "Fast slicing can outrun validation if the smoke tester is starved too long.",
                ]
            )
            validation_strategy.insert(0, "Prioritize a runnable vertical slice, then smoke-check it immediately.")
        elif mode == "high_quality":
            add(self._make_swarm_spec("architect", "Architecture Steward", "Stabilize boundaries before high-scrutiny work fans out.", model_policy_for("long_context_planning", "Prefer the default worker model with higher reasoning."), buckets["subsystems"][:2], docs_paths(), "plan_review", "Architecture and path ownership are accepted.", 10, ["repo_mapping", "design_notes"]))
            add(self._make_swarm_spec("feature", "Implementation Specialist", "Build the main feature slice with explicit review handoff points.", model_policy_for("code_editing", "Prefer the default worker model with medium reasoning."), frontend_paths() + backend_paths(), docs_paths(), "build_start", "Main implementation slice is complete and in review.", 20, ["feature_work", "tests"]))
            add(self._make_swarm_spec("test", "Validation Specialist", "Expand test depth and regression coverage before handoff.", model_policy_for("test_generation", "Prefer a more careful model when explaining failures."), test_paths() + backend_paths(), [], "build_start", "Validation coverage matches the requested quality bar.", 30, ["test_runner", "smoke_checks"]))
            add(self._make_swarm_spec("reviewer", "Code Review Specialist", "Review risky changes for regressions, gaps, and weak assumptions.", model_policy_for("reliability", "Prefer the default worker model with higher reasoning."), frontend_paths() + backend_paths(), [], "after_first_implementation", "Review queue is cleared or converted into specific follow-ups.", 35, ["code_review", "diff_analysis"]))
            add(self._make_swarm_spec("security", "Security Review Specialist", "Audit auth, secrets, and approval-sensitive flows.", model_policy_for("shell_command_reasoning", "Prefer a careful reasoning profile for security-sensitive review."), backend_paths() + buckets["data"], [], "after_architecture", "Security-sensitive decisions are documented and reviewed.", 40, ["security_review", "config_audit"]))
            if preferences.docs_depth != "minimal":
                add(self._make_swarm_spec("release_handoff", "Release Handoff Writer", "Prepare evidence-backed handoff notes and validation summary.", model_policy_for("docs_writing", "Prefer the default worker model with medium reasoning."), docs_paths(), frontend_paths() + backend_paths(), "validation", "Handoff notes and run instructions are complete.", 45, ["handoff_packaging", "release_notes"]))
            bottlenecks.extend(
                [
                    "Review and security feedback can bottleneck the main implementation if scope stays fuzzy.",
                    "High-quality mode slows down when tests and implementation touch the same unstable paths.",
                ]
            )
            validation_strategy.insert(0, "Require review, security, and testing coverage before calling the build ready.")
        elif mode == "documentation_heavy":
            add(self._make_swarm_spec("feature", "Core Builder", "Ship the working slice that the documentation will explain.", "Prefer the default worker model with medium reasoning.", frontend_paths() + backend_paths(), docs_paths(), "build_start", "The documented product path is real and stable enough to describe.", 10, ["feature_work"]))
            add(self._make_swarm_spec("docs", "README Writer", "Own the quick-start README and project orientation copy.", "Prefer the default worker model for concise docs writing.", ["README.md", *docs_paths()], frontend_paths() + backend_paths(), "build_start", "README and setup instructions are accurate.", 20, ["docs_editing"]))
            add(self._make_swarm_spec("docs", "User Guide Writer", "Document user-facing workflows and examples.", "Prefer the default worker model for end-user docs.", docs_paths(), backend_paths(), "after_first_slice", "User workflows are documented with realistic examples.", 25, ["docs_editing"]))
            add(self._make_swarm_spec("docs", "API Docs Writer", "Document API behavior, payloads, and constraints if the project has backend flows.", "Prefer the default worker model for reference docs.", docs_paths() + backend_paths(), frontend_paths(), "after_backend_stabilizes", "API docs reflect the current backend behavior.", 30, ["docs_editing"]))
            add(self._make_swarm_spec("docs", "Example Flow Writer", "Create example snippets and handoff-ready walkthroughs.", "Prefer the default worker model for examples and usage notes.", ["examples", *docs_paths()], backend_paths(), "validation", "Examples are usable and handoff-ready.", 35, ["docs_editing", "handoff_notes"]))
            add(self._make_swarm_spec("reviewer", "Docs Reviewer", "Catch stale claims, missing steps, and confusing explanations.", "Prefer the default worker model with higher reasoning.", docs_paths(), [], "validation", "Documentation review comments are closed.", 40, ["code_review"]))
            bottlenecks.extend(
                [
                    "Documentation quality will collapse if the product path is still moving underneath multiple writers.",
                    "API docs should wait until backend behavior stabilizes enough to avoid rewriting everything twice.",
                ]
            )
            validation_strategy.insert(0, "Validate that every major doc artifact maps to a real runnable or reviewable product path.")
        elif mode == "research_planning":
            add(self._make_swarm_spec("research", "Discovery Researcher", "Reduce the highest-impact unknowns before broad implementation begins.", "Prefer the default worker model with higher reasoning.", docs_paths() + buckets["subsystems"][:2], frontend_paths() + backend_paths(), "plan_review", "The biggest architectural and scope unknowns are reduced.", 10, ["research", "option_analysis"]))
            add(self._make_swarm_spec("planner", "Scope Planner", "Turn research and interview signals into milestone-safe work packages.", "Prefer the default worker model with medium reasoning.", docs_paths(), frontend_paths() + backend_paths(), "plan_review", "Milestones and path-safe tasks are clear enough for worker execution.", 15, ["task_planning", "doc_updates"]))
            add(self._make_swarm_spec("architect", "System Architect", "Decide boundaries and ownership before spawning multiple builders.", "Prefer the default worker model with higher reasoning.", buckets["subsystems"][:3], docs_paths(), "plan_review", "Architecture and ownership are explicit enough for execution.", 20, ["repo_mapping", "design_notes"]))
            add(self._make_swarm_spec("feature", "Prototype Builder", "Prepare a minimal implementation spike once research converges.", "Prefer the default worker model with medium reasoning.", frontend_paths() + backend_paths(), docs_paths(), "after_architecture", "The first prototype confirms the chosen direction.", 30, ["feature_work"]))
            bottlenecks.extend(
                [
                    "Research-heavy mode stalls if implementation starts before decisions actually converge.",
                    "The planner and architect need current docs or they will optimize stale assumptions.",
                ]
            )
            validation_strategy.insert(0, "Treat architecture confidence as the gate before aggressive build parallelism.")
        elif mode == "massive_codebase":
            add(self._make_swarm_spec("research", "Repo Mapper", "Map the repo before anyone starts broad edits.", "Prefer the default worker model with higher reasoning.", buckets["subsystems"], [], "plan_review", "Subsystem ownership is mapped and documented.", 10, ["repo_mapping"]))
            add(self._make_swarm_spec("architect", "Ownership Architect", "Set path ownership, review gates, and interface boundaries.", "Prefer the default worker model with higher reasoning.", buckets["subsystems"], [], "plan_review", "Path strategy is explicit and accepted.", 15, ["design_notes"]))
            for index, subsystem in enumerate(buckets["subsystems"][: max(1, min(3, capacity - 3))], start=1):
                add(
                    self._make_swarm_spec(
                        archetype="feature",
                        name=f"{self._titleize_path_label(subsystem)} Subsystem Builder",
                        mission=f"Own implementation work under {subsystem} without crossing subsystem boundaries.",
                        model_policy="Prefer the default worker model with medium reasoning and strict path ownership.",
                        allowed_paths=[subsystem],
                        forbidden_paths=[item for item in buckets["subsystems"] if item != subsystem],
                        spawn_phase="after_path_mapping",
                        retire_when=f"The {subsystem} slice is complete or handed off for review.",
                        priority=20 + index * 5,
                        toolset=["feature_work", "tests"],
                    )
                )
            add(self._make_swarm_spec("integration", "Subsystem Integrator", "Resolve contract edges between subsystem builders.", "Prefer the default worker model with higher reasoning.", buckets["subsystems"], docs_paths(), "after_subsystem_progress", "Cross-subsystem interfaces are stable.", 45, ["integration_work"]))
            add(self._make_swarm_spec("reviewer", "Regression Reviewer", "Review boundary changes and path conflicts before they spread.", "Prefer the default worker model with higher reasoning.", buckets["subsystems"], [], "validation", "Boundary-risk review is complete.", 50, ["code_review"]))
            bottlenecks.extend(
                [
                    "Without strict path ownership, subsystem builders will collide and waste time.",
                    "Integration becomes the choke point once subsystem work lands in parallel.",
                ]
            )
            validation_strategy.insert(0, "Validate subsystem contracts and path ownership before parallel changes merge.")
        else:
            add(self._make_swarm_spec("planner", "Execution Planner", "Keep milestones and task routing coherent while the build moves.", "Prefer the default worker model with medium reasoning.", docs_paths(), frontend_paths() + backend_paths(), "plan_review", "Milestone routing is stable enough to hand off.", 10, ["task_planning"]))
            add(self._make_swarm_spec("frontend", "UI Workflow Builder", "Own the user-facing surface and key interaction flow.", "Prefer the default worker model with medium reasoning.", frontend_paths(), backend_paths(), "build_start", "Core UI flow is implemented and reviewable.", 20, ["ui_editing"]))
            add(self._make_swarm_spec("backend", "Service Flow Builder", "Own the main backend or service logic for the MVP.", "Prefer the default worker model with medium reasoning.", backend_paths(), frontend_paths(), "build_start", "Core service behavior is stable enough for review.", 25, ["api_editing"]))
            add(self._make_swarm_spec("test", "Validation Specialist", "Keep testing honest without overwhelming the main build loop.", "Prefer a careful model when reporting failures.", test_paths() + backend_paths(), [], "after_first_slice", "The main user workflow has explicit validation evidence.", 35, ["test_runner"]))
            if preferences.docs_depth != "minimal":
                add(self._make_swarm_spec("docs", "Handoff Writer", "Keep handoff docs current enough that they do not become an afterthought.", "Prefer the default worker model for concise operational docs.", docs_paths(), frontend_paths() + backend_paths(), "validation", "Handoff notes and run instructions are complete.", 40, ["docs_editing", "handoff_notes"]))
            bottlenecks.extend(
                [
                    "Balanced mode still needs clear ownership or the build will drift into parallel chaos.",
                    "Validation and docs can lag if implementation keeps changing late.",
                ]
            )
            validation_strategy.insert(0, "Keep one validation specialist close enough to the main build to catch regressions early.")

        if preferences.testing_depth in {"extensive", "release_grade"} and all(spec.archetype != "security" for spec in specs) and len(specs) < capacity:
            add(self._make_swarm_spec("security", "Release Risk Auditor", "Review high-risk auth, secrets, and approval-sensitive behavior before handoff.", "Prefer a careful reasoning profile for release-grade risk checks.", backend_paths() + buckets["data"], [], "validation", "Release-grade risks are either closed or documented.", 60, ["security_review"]))
        if preferences.docs_depth == "publishable" and len([spec for spec in specs if spec.archetype == "docs"]) < 3 and len(specs) < capacity:
            add(self._make_swarm_spec("docs", "Developer Guide Writer", "Document internal development and extension flows for maintainers.", "Prefer the default worker model for structured docs.", docs_paths(), frontend_paths() + backend_paths(), "validation", "Developer-facing docs are publishable and current.", 55, ["docs_editing"]))

        if scale_hint == "up" and len(specs) < capacity:
            add(self._make_swarm_spec("feature", "Overflow Implementation Agent", "Pick up an isolated slice when the current bottleneck is raw implementation throughput.", model_policy_for("speed", "Prefer the default worker model with medium reasoning."), frontend_paths() or backend_paths(), docs_paths(), "build_start", "The overflow slice is complete or unnecessary.", 70, ["feature_work"]))
            bottlenecks.insert(0, "Scale-up requested: implementation throughput was judged more valuable than tighter coordination.")
        if scale_hint == "down" and len(specs) > 2:
            specs = specs[:-1]
            bottlenecks.insert(0, "Scale-down requested: retire the least critical parallel lane before it turns into overhead.")

        open_risks = intelligence_context.get("open_risks") or []
        for risk in open_risks[:2]:
            bottlenecks.append(f"Risk pressure: {risk.get('title')}")
        coverage = intelligence_context.get("validation_coverage") or []
        missing_coverage = [item.get("area") for item in coverage if item.get("coverage_status") in {"none", "failed"}]
        for area in missing_coverage[:3]:
            validation_strategy.append(f"Add explicit validation coverage for {area}.")

        recommended = max(1, min(capacity, len(specs)))
        coordination_risk = "high" if recommended >= 7 or mode == "massive_codebase" else "medium" if recommended >= 5 or mode in {"documentation_heavy", "high_quality"} else "low"
        path_conflict_risk = "high" if mode == "massive_codebase" else "medium" if any(len(spec.allowed_paths) > 1 for spec in specs) else "low"
        strategy_summary = (
            f"{self._titleize_path_label(mode.replace('_', ' '))} mode with {recommended} worker lane(s). "
            f"Bias toward {('throughput' if mode == 'fastest_build' else 'review depth' if mode == 'high_quality' else 'documentation quality' if mode == 'documentation_heavy' else 'research clarity' if mode == 'research_planning' else 'subsystem ownership' if mode == 'massive_codebase' else 'balanced execution')} "
            f"while keeping path ownership explicit."
        )
        return ManagerSwarmPlanPayload(
            mode=mode,
            goal=goal,
            recommended_agent_count=recommended,
            coordination_risk=coordination_risk,
            path_conflict_risk=path_conflict_risk,
            expected_bottlenecks=bottlenecks[:5],
            strategy_summary=strategy_summary,
            validation_strategy=validation_strategy[:4],
            specs=specs[:capacity],
        )

    def _update_project_understanding(
        self,
        db: Session,
        project: Project,
        payload: InterviewUnderstandingPayload,
    ) -> ProjectUnderstanding:
        understanding = self._ensure_project_understanding(db, project)
        understanding.summary = payload.summary.strip()
        understanding.known_facts_json = self._normalize_mapping_payload(payload.known_facts)
        understanding.unknowns_json = self._normalize_mapping_payload(payload.unknowns)
        understanding.assumptions_json = self._normalize_string_list(payload.assumptions)
        understanding.constraints_json = self._normalize_string_list(payload.constraints)
        understanding.confidence_by_category_json = self._normalize_confidence_map(payload.confidence_by_category)
        understanding.updated_at = utc_now()
        db.flush()
        self.events.publish(db, project.id, "project_understanding.updated", {"project_id": project.id})
        return understanding

    def _mirror_session_understanding(self, session: InterviewSession, understanding: ProjectUnderstanding) -> None:
        session.confidence_json = dict(understanding.confidence_by_category_json or {})
        session.known_facts_json = dict(understanding.known_facts_json or {})
        session.unknowns_json = dict(understanding.unknowns_json or {})

    def _refresh_interview_session_state(self, session: InterviewSession, *, project: Project | None = None) -> InterviewSession:
        pending = self._pending_interview_questions(session)
        answered = sorted(self._answered_interview_questions(session), key=lambda item: item.index)
        session.current_index = pending[0].index if pending else min(len(answered), max(session.question_count - 1, 0))
        if session.status != "superseded":
            if pending:
                session.status = "in_progress"
                if project is not None:
                    project.status = "interview_in_progress"
            elif session.status == "completed":
                session.status = "completed"
                if project is not None:
                    project.status = "interview_complete"
            elif project is not None:
                project.status = "interview_in_progress"
        return session

    def _build_interview_summary(self, project: Project, understanding: ProjectUnderstanding) -> str:
        if understanding.summary.strip():
            return understanding.summary.strip()
        known_count = sum(len(value) for value in understanding.known_facts_json.values() if isinstance(value, list))
        if known_count:
            return f"The manager has captured {known_count} project decisions for {project.name}."
        return f"The manager is still collecting the minimum signal required to plan {project.name}."

    def _append_local_answer_to_understanding(self, understanding: ProjectUnderstanding, question: InterviewQuestion) -> None:
        category = (question.category or "core features").strip()
        known_facts = dict(understanding.known_facts_json or {})
        category_entries = list(known_facts.get(category, [])) if isinstance(known_facts.get(category), list) else []
        category_entries.append(
            {
                "question": question.question,
                "answer": self._question_answer_text(question),
                "selected_option_id": question.selected_option_id or question.selected_option,
                "affects": list(question.affects_json or []),
            }
        )
        known_facts[category] = category_entries
        understanding.known_facts_json = known_facts

        confidence = dict(understanding.confidence_by_category_json or {})
        confidence[category] = max(float(confidence.get(category, 0.0)), 0.65 if question.custom_answer else 0.55)
        understanding.confidence_by_category_json = self._normalize_confidence_map(confidence)
        understanding.updated_at = utc_now()
        understanding.summary = self._build_interview_summary(question.session.project, understanding)

    def _serialize_understanding_record(self, project: Project, understanding: ProjectUnderstanding) -> dict[str, Any]:
        return {
            "project_id": project.id,
            "summary": self._build_interview_summary(project, understanding),
            "known_facts_json": dict(understanding.known_facts_json or {}),
            "unknowns_json": dict(understanding.unknowns_json or {}),
            "assumptions_json": list(understanding.assumptions_json or []),
            "constraints_json": list(understanding.constraints_json or []),
            "confidence_by_category_json": self._normalize_confidence_map(dict(understanding.confidence_by_category_json or {})),
            "updated_at": understanding.updated_at,
        }

    def _serialize_widget_definition(self, definition: WidgetDefinition) -> dict[str, Any]:
        return {
            "id": definition.id,
            "widget_type": definition.widget_type,
            "title": definition.title,
            "description": definition.description,
            "scope": definition.scope,
            "default_area": definition.default_area,
            "default_size": definition.default_size,
            "category": definition.category,
            "requires_project": definition.requires_project,
            "requires_tool": definition.requires_tool,
            "coming_soon": definition.coming_soon,
            "risk_level": definition.risk_level,
        }

    def _serialize_widget_instance(self, instance: WidgetInstance) -> dict[str, Any]:
        return {
            "id": instance.id,
            "scope": instance.scope,
            "project_id": instance.project_id,
            "widget_type": instance.widget_type,
            "area": instance.area,
            "order_index": instance.order_index,
            "size": instance.size,
            "collapsed": instance.collapsed,
            "enabled": instance.enabled,
            "config_json": dict(instance.config_json or {}),
            "created_at": instance.created_at,
            "updated_at": instance.updated_at,
        }

    def _serialize_widget_data(
        self,
        instance: WidgetInstance,
        *,
        status: str,
        data_json: dict[str, Any] | None = None,
        empty_state: str | None = None,
        warnings_json: list[str] | None = None,
        updated_at: datetime | None = None,
    ) -> dict[str, Any]:
        definition = WIDGET_CATALOG_BY_TYPE.get(instance.widget_type, {})
        return {
            "widget_instance_id": instance.id,
            "widget_type": instance.widget_type,
            "title": str(definition.get("title") or instance.widget_type),
            "status": status,
            "data_json": dict(data_json or {}),
            "empty_state": empty_state,
            "warnings_json": list(warnings_json or []),
            "updated_at": updated_at or instance.updated_at,
        }

    def _widget_definition_snapshot(
        self,
        payload: dict[str, Any],
        override: WidgetDefinition | None = None,
        *,
        synthetic_id: int,
    ) -> WidgetDefinition:
        return WidgetDefinition(
            id=override.id if override is not None else synthetic_id,
            widget_type=str(override.widget_type if override is not None else payload["widget_type"]),
            title=str(override.title if override is not None else payload["title"]),
            description=str(override.description if override is not None else payload["description"]),
            scope=str(override.scope if override is not None else payload["scope"]),
            default_area=str(override.default_area if override is not None else payload["default_area"]),
            default_size=str(override.default_size if override is not None else payload["default_size"]),
            category=str(override.category if override is not None else payload["category"]),
            requires_project=bool(override.requires_project if override is not None else payload.get("requires_project", False)),
            requires_tool=override.requires_tool if override is not None else (str(payload["requires_tool"]) if payload.get("requires_tool") else None),
            coming_soon=bool(override.coming_soon if override is not None else payload.get("coming_soon", False)),
            risk_level=override.risk_level if override is not None else (str(payload["risk_level"]) if payload.get("risk_level") else None),
        )

    def _widget_definitions_view(self, db: Session) -> list[WidgetDefinition]:
        existing = {item.widget_type: item for item in db.scalars(select(WidgetDefinition).order_by(WidgetDefinition.widget_type.asc()))}
        merged: list[WidgetDefinition] = []
        seen: set[str] = set()
        for index, payload in enumerate(WIDGET_CATALOG, start=1):
            widget_type = str(payload["widget_type"])
            merged.append(self._widget_definition_snapshot(payload, existing.get(widget_type), synthetic_id=-index))
            seen.add(widget_type)
        for widget_type, definition in existing.items():
            if widget_type in seen:
                continue
            merged.append(self._widget_definition_snapshot({"widget_type": widget_type}, definition, synthetic_id=definition.id))
        return sorted(merged, key=lambda item: (item.scope, item.title.lower()))

    def _widget_catalog_for_scope(self, db: Session, scope: str) -> list[dict[str, Any]]:
        return [
            self._serialize_widget_definition(definition)
            for definition in self._widget_definitions_view(db)
            if definition.scope == scope
        ]

    def _widget_instances_query(self, db: Session, *, scope: str, project_id: int | None) -> list[WidgetInstance]:
        query = select(WidgetInstance).where(WidgetInstance.scope == scope)
        if project_id is None:
            query = query.where(WidgetInstance.project_id.is_(None))
        else:
            query = query.where(WidgetInstance.project_id == project_id)
        query = query.order_by(WidgetInstance.area.asc(), WidgetInstance.order_index.asc(), WidgetInstance.id.asc())
        return list(db.scalars(query))

    def _normalize_widget_order(self, db: Session, *, scope: str, project_id: int | None) -> None:
        counters: dict[str, int] = {}
        for instance in self._widget_instances_query(db, scope=scope, project_id=project_id):
            next_index = counters.get(instance.area, 0)
            if instance.order_index != next_index:
                instance.order_index = next_index
            counters[instance.area] = next_index + 1
        db.flush()

    def _seed_widget_instances(
        self,
        db: Session,
        *,
        scope: str,
        project_id: int | None,
        widget_types: list[str],
    ) -> list[WidgetInstance]:
        definitions = {item.widget_type: item for item in self._widget_definitions_view(db)}
        allowed_widget_types = DASHBOARD_WIDGET_TYPES if scope == "dashboard" else PROJECT_WIDGET_TYPES
        instances: list[WidgetInstance] = []
        area_counts: Counter[str] = Counter()
        for widget_type in widget_types:
            if widget_type not in allowed_widget_types:
                continue
            definition = definitions.get(widget_type)
            if definition is None:
                continue
            instance = WidgetInstance(
                scope=scope,
                project_id=project_id,
                widget_type=widget_type,
                area=definition.default_area,
                order_index=area_counts[definition.default_area],
                size=definition.default_size,
                collapsed=False,
                enabled=True,
                config_json={},
            )
            area_counts[definition.default_area] += 1
            db.add(instance)
            instances.append(instance)
        db.flush()
        return instances

    def _mirror_dashboard_widget_legacy(self, profile: AppProfile, instances: list[WidgetInstance]) -> None:
        profile.dashboard_widgets_json = [instance.widget_type for instance in instances if instance.enabled]
        preferences = dict(profile.dashboard_widget_preferences_json or {})
        preferences["initialized"] = True
        profile.dashboard_widget_preferences_json = preferences

    def _mirror_project_widget_legacy(self, settings: ProjectSettings, instances: list[WidgetInstance]) -> None:
        settings.workspace_widgets_json = [instance.widget_type for instance in instances if instance.enabled]

    def _dashboard_widget_instances(self, db: Session, profile: AppProfile, *, create_if_missing: bool = True) -> list[WidgetInstance]:
        instances = self._widget_instances_query(db, scope="dashboard", project_id=None)
        if not instances and create_if_missing:
            configured = [item for item in (profile.dashboard_widgets_json or []) if item in DASHBOARD_WIDGET_TYPES]
            preferences = dict(profile.dashboard_widget_preferences_json or {})
            seed_types = configured or ([] if preferences.get("initialized") else list(DASHBOARD_WIDGET_DEFAULTS))
            instances = self._seed_widget_instances(db, scope="dashboard", project_id=None, widget_types=seed_types)
        if create_if_missing:
            self._normalize_widget_order(db, scope="dashboard", project_id=None)
            instances = self._widget_instances_query(db, scope="dashboard", project_id=None)
            self._mirror_dashboard_widget_legacy(profile, instances)
        return instances

    def _project_widget_instances(
        self,
        db: Session,
        project: Project,
        settings: ProjectSettings,
        *,
        create_if_missing: bool = True,
    ) -> list[WidgetInstance]:
        instances = self._widget_instances_query(db, scope="project", project_id=project.id)
        if not instances and create_if_missing:
            configured = [item for item in (settings.workspace_widgets_json or []) if item in PROJECT_WIDGET_TYPES]
            seed_types = configured or list(PROJECT_WIDGET_DEFAULTS)
            instances = self._seed_widget_instances(db, scope="project", project_id=project.id, widget_types=seed_types)
        if create_if_missing:
            self._normalize_widget_order(db, scope="project", project_id=project.id)
            instances = self._widget_instances_query(db, scope="project", project_id=project.id)
            self._mirror_project_widget_legacy(settings, instances)
        return instances

    def _workspace_widgets(self, db: Session, project: Project, settings: ProjectSettings) -> list[str]:
        return [instance.widget_type for instance in self._project_widget_instances(db, project, settings) if instance.enabled]

    def _dashboard_widgets(self, db: Session, profile: AppProfile) -> list[str]:
        return [instance.widget_type for instance in self._dashboard_widget_instances(db, profile) if instance.enabled]

    def _validate_project_related_refs(
        self,
        db: Session,
        project: Project,
        *,
        related_agent_id: int | None = None,
        related_task_id: int | None = None,
        agent_label: str = "Related agent",
        task_label: str = "Related task",
    ) -> None:
        if related_agent_id is not None:
            agent = db.get(Agent, related_agent_id)
            if agent is None or agent.project_id != project.id:
                raise ValueError(f"{agent_label} not found in this project")
        if related_task_id is not None:
            task = db.get(Task, related_task_id)
            if task is None or task.project_id != project.id:
                raise ValueError(f"{task_label} not found in this project")

    def _validate_project_evidence_refs(
        self,
        db: Session,
        project: Project,
        *,
        evidence_ids: list[int] | None = None,
        evidence_label: str = "Related evidence",
    ) -> list[int]:
        normalized = [int(item) for item in (evidence_ids or [])]
        if not normalized:
            return normalized
        valid_ids = set(
            db.scalars(
                select(HandoffEvidence.id).where(
                    HandoffEvidence.project_id == project.id,
                    HandoffEvidence.id.in_(normalized),
                )
            )
        )
        for evidence_id in normalized:
            if evidence_id not in valid_ids:
                raise ValueError(f"{evidence_label} not found in this project")
        return normalized

    def _validate_project_task_refs(
        self,
        db: Session,
        project: Project,
        *,
        task_ids: list[int] | None = None,
        task_label: str = "Related task",
    ) -> list[int]:
        normalized = [int(item) for item in (task_ids or [])]
        if not normalized:
            return normalized
        valid_ids = set(
            db.scalars(
                select(Task.id).where(
                    Task.project_id == project.id,
                    Task.id.in_(normalized),
                )
            )
        )
        for task_id in normalized:
            if task_id not in valid_ids:
                raise ValueError(f"{task_label} not found in this project")
        return normalized

    def _validate_project_handoff_ref(
        self,
        db: Session,
        project: Project,
        *,
        related_handoff_id: int | None = None,
        handoff_label: str = "Related handoff",
    ) -> int | None:
        if related_handoff_id is None:
            return None
        handoff = db.get(EvidenceBasedHandoff, int(related_handoff_id))
        if handoff is None or handoff.project_id != project.id:
            raise ValueError(f"{handoff_label} not found in this project")
        return handoff.id

    def _record_decision(
        self,
        db: Session,
        project: Project,
        *,
        decision_type: str,
        title: str,
        decision: str,
        reason: str,
        made_by: str,
        impact_areas: list[str] | None = None,
        related_task_id: int | None = None,
        related_agent_id: int | None = None,
        reversible: bool = False,
    ) -> DecisionRecord:
        self._validate_project_related_refs(
            db,
            project,
            related_agent_id=related_agent_id,
            related_task_id=related_task_id,
            agent_label="Decision related agent",
            task_label="Decision related task",
        )
        existing = db.scalar(
            select(DecisionRecord)
            .where(
                DecisionRecord.project_id == project.id,
                DecisionRecord.decision_type == decision_type,
                DecisionRecord.title == title,
                DecisionRecord.decision == decision,
            )
            .order_by(DecisionRecord.id.desc())
        )
        if existing is not None:
            return existing
        record = DecisionRecord(
            project_id=project.id,
            decision_type=decision_type,
            title=title,
            decision=decision,
            reason=reason,
            made_by=made_by,
            impact_area_json=list(impact_areas or []),
            related_task_id=related_task_id,
            related_agent_id=related_agent_id,
            reversible=reversible,
        )
        db.add(record)
        db.flush()
        self.events.publish(
            db,
            project.id,
            "decision_record_created",
            {"project_id": project.id, "decision_record_id": record.id, "decision_type": decision_type, "title": title},
        )
        return record

    def _record_timeline_event(
        self,
        db: Session,
        project: Project,
        *,
        event_type: str,
        title: str,
        summary: str,
        severity: str = "info",
        related_agent_id: int | None = None,
        related_task_id: int | None = None,
        related_handoff_id: int | None = None,
    ) -> ProjectTimelineEvent:
        self._validate_project_related_refs(
            db,
            project,
            related_agent_id=related_agent_id,
            related_task_id=related_task_id,
            agent_label="Timeline event related agent",
            task_label="Timeline event related task",
        )
        related_handoff_id = self._validate_project_handoff_ref(
            db,
            project,
            related_handoff_id=related_handoff_id,
            handoff_label="Timeline event related handoff",
        )
        existing = db.scalar(
            select(ProjectTimelineEvent)
            .where(
                ProjectTimelineEvent.project_id == project.id,
                ProjectTimelineEvent.event_type == event_type,
                ProjectTimelineEvent.title == title,
                ProjectTimelineEvent.summary == summary,
            )
            .order_by(ProjectTimelineEvent.id.desc())
        )
        if existing is not None:
            return existing
        event = ProjectTimelineEvent(
            project_id=project.id,
            event_type=event_type,
            title=title,
            summary=summary,
            severity=severity,
            related_agent_id=related_agent_id,
            related_task_id=related_task_id,
            related_handoff_id=related_handoff_id,
        )
        db.add(event)
        db.flush()
        self.events.publish(
            db,
            project.id,
            "timeline_event_created",
            {
                "project_id": project.id,
                "timeline_event_id": event.id,
                "event_type": event_type,
                "severity": severity,
            },
        )
        return event

    @staticmethod
    def _markdown_list(items: list[str]) -> str:
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        if not cleaned:
            return "- Not recorded."
        return "\n".join(f"- {item}" for item in cleaned)

    @staticmethod
    def _handoff_evidence_key(
        *,
        evidence_type: str,
        claim: str,
        summary: str,
        source_path: str | None,
        command: str | None,
        status: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> tuple[str, str, str, str | None, str | None, str | None, str]:
        return (
            evidence_type,
            claim,
            summary,
            source_path,
            command,
            status,
            json.dumps(metadata_json or {}, sort_keys=True, separators=(",", ":")),
        )

    def _handoff_evidence_or_create(
        self,
        db: Session,
        project: Project,
        *,
        evidence_type: str,
        claim: str,
        summary: str,
        status: str,
        source_path: str | None = None,
        command: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        handoff_id: int | None = None,
    ) -> HandoffEvidence:
        claim = redact_text(claim)
        summary = redact_text(summary)
        command = redact_text(command) if command else None
        metadata_json = redact_value(metadata_json or {})
        existing = db.scalar(
            select(HandoffEvidence)
            .where(
                HandoffEvidence.project_id == project.id,
                HandoffEvidence.evidence_type == evidence_type,
                HandoffEvidence.claim == claim,
                HandoffEvidence.summary == summary,
                HandoffEvidence.source_path == source_path,
                HandoffEvidence.command == command,
                HandoffEvidence.status == status,
            )
            .order_by(HandoffEvidence.id.desc())
        )
        if existing is not None and dict(existing.metadata_json or {}) != dict(metadata_json):
            existing = None
        if existing is None:
            existing = HandoffEvidence(
                project_id=project.id,
                handoff_id=handoff_id,
                evidence_type=evidence_type,
                claim=claim,
                summary=summary,
                source_path=source_path,
                command=command,
                status=status,
                metadata_json=dict(metadata_json),
            )
            db.add(existing)
        else:
            existing.handoff_id = handoff_id or existing.handoff_id
            existing.status = status
            existing.metadata_json = dict(metadata_json or existing.metadata_json or {})
        db.flush()
        return existing

    def _latest_evidence_handoff(self, db: Session, project_id: int) -> EvidenceBasedHandoff | None:
        return db.scalar(
            select(EvidenceBasedHandoff)
            .where(EvidenceBasedHandoff.project_id == project_id)
            .order_by(EvidenceBasedHandoff.created_at.desc(), EvidenceBasedHandoff.id.desc())
        )

    def _ensure_agent_execution_traces(self, db: Session, project: Project) -> list[AgentExecutionTrace]:
        agent_ids = [agent.id for agent in db.scalars(select(Agent).where(Agent.project_id == project.id))]
        if not agent_ids:
            return []
        runs = list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.agent_id.in_(agent_ids))
                .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
            )
        )
        existing_run_ids = {
            trace.run_id
            for trace in db.scalars(select(AgentExecutionTrace).where(AgentExecutionTrace.project_id == project.id))
            if trace.run_id is not None
        }
        agents_by_id = {agent.id: agent for agent in db.scalars(select(Agent).where(Agent.project_id == project.id))}
        tasks_by_id = {task.id: task for task in db.scalars(select(Task).where(Task.project_id == project.id))}
        for run in runs:
            if run.id in existing_run_ids:
                continue
            agent = agents_by_id.get(run.agent_id)
            task = tasks_by_id.get(run.task_id) if run.task_id is not None else None
            raw_report = self._redact_payload(run.report_json or {})
            files_changed = [str(item) for item in (raw_report.get("files_changed") or []) if str(item).strip()]
            tests_run = [str(item) for item in (raw_report.get("tests_run") or []) if str(item).strip()]
            approvals = [
                self._serialize_approval(entry)
                for entry in db.scalars(
                    select(ApprovalRequest)
                    .where(
                        ApprovalRequest.project_id == project.id,
                        ApprovalRequest.requesting_agent_id == run.agent_id,
                        ApprovalRequest.task_id == run.task_id,
                    )
                    .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
                )
            ][:5]
            prompt_bits = [agent.mission if agent and agent.mission else None, task.goal if task else None, task.scope if task else None]
            prompt_summary = " | ".join(bit for bit in prompt_bits if bit) or f"{agent.name if agent else 'Worker'} executed a recorded run."
            response_summary = str(raw_report.get("summary") or run.status or "Run completed.")
            commands_attempted = []
            if run.runner_type:
                commands_attempted.append(f"runner:{run.runner_type}")
            commands_attempted.extend(tests_run[:3])
            trace = AgentExecutionTrace(
                project_id=project.id,
                agent_id=run.agent_id,
                task_id=run.task_id,
                run_id=run.id,
                prompt_summary=prompt_summary[:1000],
                prompt_path=run.logs_path or run.event_log_path,
                response_summary=response_summary[:1000],
                report_json=raw_report if isinstance(raw_report, dict) else {},
                files_changed_json=files_changed[:40],
                approvals_requested_json=approvals,
                commands_attempted_json=commands_attempted[:20],
                manager_decision_after=run.manager_action,
                redaction_status="redacted_summary",
            )
            db.add(trace)
        db.flush()
        return list(
            db.scalars(
                select(AgentExecutionTrace)
                .where(AgentExecutionTrace.project_id == project.id)
                .order_by(AgentExecutionTrace.created_at.desc(), AgentExecutionTrace.id.desc())
            )
        )

    def _sync_agent_load_snapshots(self, db: Session, project: Project) -> list[AgentLoadSnapshot]:
        agents = list(db.scalars(select(Agent).where(Agent.project_id == project.id).order_by(Agent.id.asc())))
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.id.asc())))
        latest_by_agent = {
            entry.agent_id: entry
            for entry in db.scalars(
                select(AgentLoadSnapshot)
                .where(AgentLoadSnapshot.project_id == project.id)
                .order_by(AgentLoadSnapshot.created_at.desc(), AgentLoadSnapshot.id.desc())
            )
        }
        now = utc_now()
        snapshots: list[AgentLoadSnapshot] = []
        for agent in agents:
            if agent.kind != "worker":
                continue
            active_task_count = sum(1 for task in tasks if task.assigned_agent_id == agent.id and task.status == "working")
            waiting_task_count = sum(1 for task in tasks if task.assigned_agent_id == agent.id and task.status in {"assigned", "waiting_on_paths", "needs_review"})
            blocked_task_count = sum(1 for task in tasks if task.assigned_agent_id == agent.id and task.status == "blocked")
            idle_duration_seconds = None
            if agent.status in {"idle", "waiting", "done", "stopped"}:
                last_update = agent.last_update if agent.last_update.tzinfo else agent.last_update.replace(tzinfo=timezone.utc)
                idle_duration_seconds = max(0, int((now - last_update).total_seconds()))
            if blocked_task_count or agent.status in {"blocked", "error"}:
                load_level = "blocked"
            elif active_task_count >= 3:
                load_level = "heavy"
            elif active_task_count >= 1 or waiting_task_count >= 2:
                load_level = "normal"
            elif waiting_task_count == 1:
                load_level = "light"
            else:
                load_level = "idle"
            latest = latest_by_agent.get(agent.id)
            if latest is None or (
                latest.active_task_count != active_task_count
                or latest.waiting_task_count != waiting_task_count
                or latest.blocked_task_count != blocked_task_count
                or latest.idle_duration_seconds != idle_duration_seconds
                or latest.load_level != load_level
            ):
                latest = AgentLoadSnapshot(
                    project_id=project.id,
                    agent_id=agent.id,
                    active_task_count=active_task_count,
                    waiting_task_count=waiting_task_count,
                    blocked_task_count=blocked_task_count,
                    idle_duration_seconds=idle_duration_seconds,
                    load_level=load_level,
                )
                db.add(latest)
            snapshots.append(latest)
        db.flush()
        self.events.publish(db, project.id, "agent_load_updated", {"project_id": project.id, "snapshot_count": len(snapshots)})
        return snapshots

    def _ensure_derived_handoff_evidence(
        self,
        db: Session,
        project: Project,
        *,
        handoff_id: int | None = None,
    ) -> list[HandoffEvidence]:
        agent_ids = [agent.id for agent in db.scalars(select(Agent).where(Agent.project_id == project.id))]
        runs = list(db.scalars(select(AgentRun).where(AgentRun.agent_id.in_(agent_ids)).order_by(AgentRun.id.asc()))) if agent_ids else []
        evidence: list[HandoffEvidence] = []
        for run in runs:
            raw_report = run.report_json or {}
            tests_run = [str(item) for item in raw_report.get("tests_run", []) if str(item).strip()]
            files_changed = [str(item) for item in raw_report.get("files_changed", []) if str(item).strip()]
            if files_changed:
                evidence.append(
                    self._handoff_evidence_or_create(
                        db,
                        project,
                        handoff_id=handoff_id,
                        evidence_type="file_change",
                        claim=f"Recorded file changes from run {run.id}",
                        summary=", ".join(files_changed[:6]),
                        status="passed" if run.status not in {"error", "failed"} else "failed",
                        source_path=run.logs_path or run.event_log_path,
                        metadata_json={"run_id": run.id, "files_changed": files_changed[:20]},
                    )
                )
            for test_name in tests_run:
                evidence.append(
                    self._handoff_evidence_or_create(
                        db,
                        project,
                        handoff_id=handoff_id,
                        evidence_type="test_result",
                        claim=test_name,
                        summary=f"Recorded from run {run.id}.",
                        status="passed" if run.status not in {"error", "failed"} and run.exit_code in {None, 0} else "failed",
                        source_path=run.logs_path or run.stdout_path,
                        command=test_name,
                        metadata_json={"run_id": run.id, "runner_type": run.runner_type},
                    )
                )
            if raw_report.get("summary"):
                evidence.append(
                    self._handoff_evidence_or_create(
                        db,
                        project,
                        handoff_id=handoff_id,
                        evidence_type="report",
                        claim=f"Worker report from run {run.id}",
                        summary=str(raw_report.get("summary")),
                        status="passed" if run.status not in {"error", "failed"} else "failed",
                        source_path=run.logs_path,
                        metadata_json={"run_id": run.id, "runner_type": run.runner_type},
                    )
                )
        return list(
            db.scalars(
                select(HandoffEvidence)
                .where(HandoffEvidence.project_id == project.id)
                .order_by(HandoffEvidence.created_at.desc(), HandoffEvidence.id.desc())
            )
        )

    def _derive_handoff_evidence_preview(self, db: Session, project: Project) -> list[dict[str, Any]]:
        agent_ids = [agent.id for agent in db.scalars(select(Agent).where(Agent.project_id == project.id))]
        runs = list(db.scalars(select(AgentRun).where(AgentRun.agent_id.in_(agent_ids)).order_by(AgentRun.id.asc()))) if agent_ids else []
        preview_rows: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str, str, str | None, str | None, str | None, str]] = set()
        for run in runs:
            raw_report = run.report_json or {}
            tests_run = [str(item) for item in raw_report.get("tests_run", []) if str(item).strip()]
            files_changed = [str(item) for item in raw_report.get("files_changed", []) if str(item).strip()]
            candidates: list[dict[str, Any]] = []
            if files_changed:
                candidates.append(
                    {
                        "project_id": project.id,
                        "evidence_type": "file_change",
                        "claim": redact_text(f"Recorded file changes from run {run.id}"),
                        "summary": redact_text(", ".join(files_changed[:6])),
                        "source_path": run.logs_path or run.event_log_path,
                        "command": None,
                        "status": "passed" if run.status not in {"error", "failed"} else "failed",
                        "metadata_json": redact_value({"run_id": run.id, "files_changed": files_changed[:20]}),
                        "derived_from_run_id": run.id,
                    }
                )
            for test_name in tests_run:
                candidates.append(
                    {
                        "project_id": project.id,
                        "evidence_type": "test_result",
                        "claim": redact_text(test_name),
                        "summary": redact_text(f"Recorded from run {run.id}."),
                        "source_path": run.logs_path or run.stdout_path,
                        "command": redact_text(test_name),
                        "status": "passed" if run.status not in {"error", "failed"} and run.exit_code in {None, 0} else "failed",
                        "metadata_json": redact_value({"run_id": run.id, "runner_type": run.runner_type}),
                        "derived_from_run_id": run.id,
                    }
                )
            if raw_report.get("summary"):
                candidates.append(
                    {
                        "project_id": project.id,
                        "evidence_type": "report",
                        "claim": redact_text(f"Worker report from run {run.id}"),
                        "summary": redact_text(str(raw_report.get("summary"))),
                        "source_path": run.logs_path,
                        "command": None,
                        "status": "passed" if run.status not in {"error", "failed"} else "failed",
                        "metadata_json": redact_value({"run_id": run.id, "runner_type": run.runner_type}),
                        "derived_from_run_id": run.id,
                    }
                )
            for candidate in candidates:
                key = self._handoff_evidence_key(
                    evidence_type=str(candidate["evidence_type"]),
                    claim=str(candidate["claim"]),
                    summary=str(candidate["summary"]),
                    source_path=candidate.get("source_path"),
                    command=candidate.get("command"),
                    status=str(candidate.get("status") or ""),
                    metadata_json=dict(candidate.get("metadata_json") or {}),
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                preview_rows.append(candidate)
        return preview_rows

    def _missing_handoff_evidence(self, review_gates: list[ReviewGate], evidence: list[HandoffEvidence]) -> list[str]:
        missing: list[str] = []
        has_passed_test = any(item.evidence_type in {"test_result", "build_result"} and item.status == "passed" for item in evidence)
        has_any_evidence = bool(evidence)
        required_failed = [gate.title for gate in review_gates if gate.required and gate.status == "failed"]
        required_pending = [gate.title for gate in review_gates if gate.required and gate.status == "pending"]
        if not has_passed_test:
            missing.append("No passing build or test evidence is recorded.")
        if not has_any_evidence:
            missing.append("No handoff evidence has been recorded yet.")
        missing.extend(f"Required gate unresolved: {title}" for title in required_failed + required_pending)
        return missing

    def _handoff_confidence_level(self, *, dry_run: bool, review_gates: list[ReviewGate], evidence: list[HandoffEvidence], missing_evidence: list[str]) -> str:
        if any(gate.required and gate.status == "failed" for gate in review_gates):
            return "low"
        if missing_evidence:
            return "medium" if evidence else "low"
        if dry_run:
            return "medium"
        return "high"

    def _serialize_handoff_record(self, db: Session, project: Project, handoff: EvidenceBasedHandoff | None) -> dict[str, Any]:
        if handoff is None:
            return {
                "project_id": project.id,
                "project_name": project.name,
                "project_slug": self._effective_project_slug(project),
                "created_at": project.updated_at,
                "status": "not_ready",
                "summary": "No handoff is recorded yet.",
                "artifacts_path": project.docs_path or str(self._project_docs_dir(project)),
                "tests_count": 0,
                "run_instructions": [],
                "known_limitations": [],
                "confidence_level": "low",
                "evidence_status": "missing",
                "missing_evidence": ["No evidence-backed handoff has been generated yet."],
                "dry_run": project.runner_mode == "dry_run",
            }
        return {
            "project_id": project.id,
            "project_name": project.name,
            "project_slug": self._effective_project_slug(project),
            "created_at": handoff.created_at,
            "status": "ready" if handoff.confidence_level != "low" else "needs_review",
            "summary": redact_text(handoff.summary),
            "artifacts_path": project.docs_path or str(self._project_docs_dir(project)),
            "tests_count": len(handoff.tests_run_json or []),
            "run_instructions": [line.strip("- ").strip() for line in handoff.how_to_run.splitlines() if line.strip()],
            "known_limitations": [redact_text(str(item)) for item in list(handoff.known_limitations_json or [])],
            "confidence_level": handoff.confidence_level,
            "evidence_status": "backed" if handoff.evidence_ids_json else "missing",
            "missing_evidence": list((project.final_report_json or {}).get("missing_evidence") or []),
            "dry_run": handoff.dry_run,
        }

    def detect_conflicts(self, db: Session, project: Project) -> list[ConflictRecord]:
        reservations = self._active_reservations(db, project.id)
        tasks_by_id = {task.id: task for task in db.scalars(select(Task).where(Task.project_id == project.id))}
        existing = {
            (entry.conflict_type, entry.title): entry
            for entry in db.scalars(
                select(ConflictRecord)
                .where(ConflictRecord.project_id == project.id, ConflictRecord.status != "resolved")
                .order_by(ConflictRecord.id.asc())
            )
        }
        active_keys: set[tuple[str, str]] = set()
        by_path: dict[str, list[PathReservation]] = {}
        for reservation in reservations:
            by_path.setdefault(reservation.path, []).append(reservation)
        for path, items in by_path.items():
            agent_ids = sorted({item.agent_id for item in items})
            task_ids = sorted({item.task_id for item in items})
            if len(agent_ids) < 2:
                continue
            conflict_type = "file_edit_collision" if "." in Path(path).name else "path_overlap"
            title = f"Parallel edit pressure on {path}"
            summary = f"{len(agent_ids)} agents currently claim the same path target."
            key = (conflict_type, title)
            active_keys.add(key)
            record = existing.get(key)
            if record is None:
                record = ConflictRecord(
                    project_id=project.id,
                    conflict_type=conflict_type,
                    title=title,
                    summary=summary,
                    involved_agent_ids_json=agent_ids,
                    involved_task_ids_json=task_ids,
                    affected_paths_json=[path],
                    severity="high",
                    status="manager_review",
                    suggested_resolution_json=[
                        "serialize_tasks",
                        "split_file_ownership",
                        "spawn_conflict_resolver_agent",
                        "ask_user",
                    ],
                )
                db.add(record)
                self._record_manager_message(
                    db,
                    project,
                    role="system",
                    message_type="blocker_report",
                    content_markdown=(
                        f"Conflict detected: **{title}**\n\n"
                        f"{summary}\n\n"
                        "Manager should pick a resolution strategy before parallel edits turn into a merge-conflict confetti cannon."
                    ),
                    metadata_json={"conflict_type": conflict_type, "response_mode": "reliability_conflict"},
                )
                self._record_timeline_event(
                    db,
                    project,
                    event_type="conflict_detected",
                    title=title,
                    summary=summary,
                    severity="warning",
                )
            else:
                record.summary = summary
                record.involved_agent_ids_json = agent_ids
                record.involved_task_ids_json = task_ids
                record.affected_paths_json = [path]
                record.severity = "high"
                record.status = "manager_review"
        for task in tasks_by_id.values():
            if task.status != "waiting_on_paths":
                continue
            blocked_paths = [path for path in task.allowed_paths_json if path in by_path]
            if not blocked_paths:
                continue
            title = f"Task dependency conflict for {task.title}"
            summary = f"{task.title} is waiting on {len(blocked_paths)} locked path(s)."
            key = ("task_dependency", title)
            active_keys.add(key)
            record = existing.get(key)
            if record is None:
                db.add(
                    ConflictRecord(
                        project_id=project.id,
                        conflict_type="task_dependency",
                        title=title,
                        summary=summary,
                        involved_agent_ids_json=sorted({reservation.agent_id for path in blocked_paths for reservation in by_path.get(path, [])}),
                        involved_task_ids_json=[task.id],
                        affected_paths_json=blocked_paths[:10],
                        severity="medium",
                        status="detected",
                        suggested_resolution_json=["serialize_tasks", "split_file_ownership", "ask_user"],
                    )
                )
        for key, record in existing.items():
            if key not in active_keys and record.status != "resolved":
                record.status = "dismissed"
                record.resolved_at = utc_now()
        db.flush()
        conflicts = list(
            db.scalars(
                select(ConflictRecord)
                .where(ConflictRecord.project_id == project.id)
                .order_by(ConflictRecord.created_at.desc(), ConflictRecord.id.desc())
            )
        )
        if conflicts:
            self.events.publish(db, project.id, "conflict_detected", {"project_id": project.id, "count": len([item for item in conflicts if item.status != "resolved"])})
        return conflicts

    def _preview_conflicts(self, db: Session, project: Project) -> list[ConflictRecord]:
        reservations = self._active_reservations(db, project.id)
        tasks_by_id = {task.id: task for task in db.scalars(select(Task).where(Task.project_id == project.id))}
        existing_rows = list(
            db.scalars(
                select(ConflictRecord)
                .where(ConflictRecord.project_id == project.id, ConflictRecord.status != "resolved")
                .order_by(ConflictRecord.id.asc())
            )
        )
        existing = {(entry.conflict_type, entry.title): entry for entry in existing_rows}
        preview: dict[tuple[str, str], ConflictRecord] = {}
        active_keys: set[tuple[str, str]] = set()
        now = utc_now()

        def clone_conflict(
            *,
            template: ConflictRecord | None = None,
            conflict_type: str,
            title: str,
            summary: str,
            involved_agent_ids: list[int],
            involved_task_ids: list[int],
            affected_paths: list[str],
            severity: str,
            status: str,
            suggested_resolution: list[str],
        ) -> ConflictRecord:
            record = ConflictRecord(
                project_id=project.id,
                conflict_type=conflict_type,
                title=title,
                summary=summary,
                involved_agent_ids_json=involved_agent_ids,
                involved_task_ids_json=involved_task_ids,
                affected_paths_json=affected_paths,
                severity=severity,
                status=status,
                suggested_resolution_json=suggested_resolution,
                selected_resolution=template.selected_resolution if template is not None else None,
            )
            if template is not None:
                record.id = template.id
                record.created_at = template.created_at
                record.resolved_at = template.resolved_at
            else:
                record.created_at = now
            return record

        by_path: dict[str, list[PathReservation]] = {}
        for reservation in reservations:
            by_path.setdefault(reservation.path, []).append(reservation)

        for path, items in by_path.items():
            agent_ids = sorted({item.agent_id for item in items})
            task_ids = sorted({item.task_id for item in items})
            if len(agent_ids) < 2:
                continue
            conflict_type = "file_edit_collision" if "." in Path(path).name else "path_overlap"
            title = f"Parallel edit pressure on {path}"
            summary = f"{len(agent_ids)} agents currently claim the same path target."
            key = (conflict_type, title)
            active_keys.add(key)
            preview[key] = clone_conflict(
                template=existing.get(key),
                conflict_type=conflict_type,
                title=title,
                summary=summary,
                involved_agent_ids=agent_ids,
                involved_task_ids=task_ids,
                affected_paths=[path],
                severity="high",
                status="manager_review",
                suggested_resolution=[
                    "serialize_tasks",
                    "split_file_ownership",
                    "spawn_conflict_resolver_agent",
                    "ask_user",
                ],
            )

        for task in tasks_by_id.values():
            if task.status != "waiting_on_paths":
                continue
            blocked_paths = [path for path in task.allowed_paths_json if path in by_path]
            if not blocked_paths:
                continue
            title = f"Task dependency conflict for {task.title}"
            summary = f"{task.title} is waiting on {len(blocked_paths)} locked path(s)."
            key = ("task_dependency", title)
            active_keys.add(key)
            preview[key] = clone_conflict(
                template=existing.get(key),
                conflict_type="task_dependency",
                title=title,
                summary=summary,
                involved_agent_ids=sorted({reservation.agent_id for path in blocked_paths for reservation in by_path.get(path, [])}),
                involved_task_ids=[task.id],
                affected_paths=blocked_paths[:10],
                severity="medium",
                status="detected",
                suggested_resolution=["serialize_tasks", "split_file_ownership", "ask_user"],
            )

        for key, record in existing.items():
            if key in preview or record.status == "resolved":
                continue
            preview[key] = clone_conflict(
                template=record,
                conflict_type=record.conflict_type,
                title=record.title,
                summary=record.summary,
                involved_agent_ids=list(record.involved_agent_ids_json or []),
                involved_task_ids=list(record.involved_task_ids_json or []),
                affected_paths=list(record.affected_paths_json or []),
                severity=record.severity,
                status=record.status,
                suggested_resolution=list(record.suggested_resolution_json or []),
            )

        def sort_key(item: ConflictRecord) -> tuple[datetime, int]:
            created_at = item.created_at or now
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            return (created_at, item.id or 0)

        return sorted(preview.values(), key=sort_key, reverse=True)

    def resolve_conflict(self, db: Session, conflict_id: int, resolution: str) -> ConflictRecord:
        conflict = db.get(ConflictRecord, conflict_id)
        if conflict is None:
            raise ValueError("Conflict not found")
        project = db.get(Project, conflict.project_id)
        if project is None:
            raise ValueError("Project not found")
        conflict.selected_resolution = resolution
        conflict.status = "resolved"
        conflict.resolved_at = utc_now()
        related_tasks = list(db.scalars(select(Task).where(Task.id.in_(conflict.involved_task_ids_json or []))))
        if resolution == "serialize_tasks" and len(related_tasks) > 1:
            for task in related_tasks[1:]:
                if task.status in TASK_OPEN_STATUSES:
                    task.status = "waiting_on_paths"
                    task.waiting_reason = f"Serialized after conflict resolution for {conflict.title}."
        elif resolution in {"choose_agent_a", "choose_agent_b"} and related_tasks:
            preferred_index = 0 if resolution == "choose_agent_a" else 1
            keep_task_id = conflict.involved_task_ids_json[preferred_index] if len(conflict.involved_task_ids_json or []) > preferred_index else related_tasks[0].id
            for task in related_tasks:
                if task.id != keep_task_id and task.status in TASK_OPEN_STATUSES:
                    task.status = "waiting_on_paths"
                    task.waiting_reason = f"Paused after {resolution} resolved {conflict.title}."
        self._record_decision(
            db,
            project,
            decision_type="conflict_resolution",
            title=conflict.title,
            decision=resolution,
            reason=conflict.summary,
            made_by="manager",
            impact_areas=["reliability", "conflicts"],
            reversible=resolution != "rollback_one_side",
        )
        self._record_manager_message(
            db,
            project,
            role="system",
            message_type="system_notice",
            content_markdown=f"Conflict resolved: **{conflict.title}** -> `{resolution}`",
            metadata_json={"conflict_id": conflict.id, "resolution": resolution, "response_mode": "reliability_conflict"},
        )
        self._record_timeline_event(
            db,
            project,
            event_type="conflict_resolved",
            title=conflict.title,
            summary=f"Resolved with strategy: {resolution}.",
            severity="success",
        )
        self.events.publish(db, project.id, "conflict_resolved", {"project_id": project.id, "conflict_id": conflict.id, "resolution": resolution})
        db.flush()
        return conflict

    def list_conflicts(self, db: Session, project: Project) -> list[ConflictRecord]:
        return list(
            db.scalars(
                select(ConflictRecord)
                .where(ConflictRecord.project_id == project.id)
                .order_by(ConflictRecord.created_at.desc(), ConflictRecord.id.desc())
            )
        )

    def add_handoff_evidence(self, db: Session, project: Project, payload: dict[str, Any]) -> HandoffEvidence:
        evidence = self._handoff_evidence_or_create(
            db,
            project,
            evidence_type=str(payload["evidence_type"]),
            claim=str(payload["claim"]).strip(),
            summary=str(payload["summary"]).strip(),
            source_path=payload.get("source_path"),
            command=payload.get("command"),
            status=str(payload.get("status") or "unknown"),
            metadata_json=dict(payload.get("metadata_json") or {}),
        )
        self.events.publish(db, project.id, "handoff_evidence_created", {"project_id": project.id, "evidence_id": evidence.id})
        self._record_timeline_event(
            db,
            project,
            event_type="handoff_evidence_created",
            title=f"Evidence added: {evidence.claim[:120]}",
            summary=evidence.summary,
            severity="info",
        )
        return evidence

    def list_handoff_evidence(self, db: Session, project: Project) -> list[HandoffEvidence]:
        return list(
            db.scalars(
                select(HandoffEvidence)
                .where(HandoffEvidence.project_id == project.id)
                .order_by(HandoffEvidence.created_at.desc(), HandoffEvidence.id.desc())
            )
        )

    def preview_handoff_evidence(self, db: Session, project: Project) -> dict[str, Any]:
        persisted = self.list_handoff_evidence(db, project)
        persisted_keys = {
            self._handoff_evidence_key(
                evidence_type=item.evidence_type,
                claim=item.claim,
                summary=item.summary,
                source_path=item.source_path,
                command=item.command,
                status=item.status,
                metadata_json=dict(item.metadata_json or {}),
            )
            for item in persisted
        }
        derived_candidates = [
            item
            for item in self._derive_handoff_evidence_preview(db, project)
            if self._handoff_evidence_key(
                evidence_type=str(item["evidence_type"]),
                claim=str(item["claim"]),
                summary=str(item["summary"]),
                source_path=item.get("source_path"),
                command=item.get("command"),
                status=str(item.get("status") or ""),
                metadata_json=dict(item.get("metadata_json") or {}),
            )
            not in persisted_keys
        ]
        return {
            "project_id": project.id,
            "persisted": persisted,
            "derived_candidates": derived_candidates,
            "stored_count": len(persisted),
            "derived_candidate_count": len(derived_candidates),
            "generated_at": utc_now(),
        }

    def generate_evidence_handoff(self, db: Session, project: Project) -> EvidenceBasedHandoff:
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        overview = self._project_overview(db, project, tasks, self._derive_current_action(db, project, []))
        review_gates = self._sync_review_gates(
            db,
            project,
            tasks=tasks,
            overview=overview,
            testing_depth=self._ensure_swarm_preferences(db, project).testing_depth,
            conflicts=self.detect_conflicts(db, project),
        )
        evidence = self._ensure_derived_handoff_evidence(db, project)
        done_titles = [task.title for task in tasks if task.status == "done"]
        final_report = project.final_report_json or {}
        what_was_built = self._markdown_list([*done_titles, *[str(item) for item in final_report.get("what_was_built", []) if str(item).strip()]])
        how_to_run_items = [redact_text(str(item)) for item in final_report.get("how_to_run", []) if str(item).strip()]
        if not how_to_run_items:
            repo = self._scan_repo_intelligence(db, project)
            how_to_run_items = list(repo.build_commands_json[:1]) + list(repo.test_commands_json[:1])
            if not how_to_run_items:
                how_to_run_items = ["No verified run commands are recorded yet."]
        how_to_use_items = [redact_text(str(item)) for item in final_report.get("how_to_use", []) if str(item).strip()] or ["Use the Manager workspace to review current state and follow the runbook for local operation."]
        limitations = [redact_text(str(item)) for item in final_report.get("known_limitations", []) if str(item).strip()]
        if not limitations and project.runner_mode == "dry_run":
            limitations.append("This handoff was produced in dry-run mode, so execution claims are limited to recorded simulation evidence.")
        tests_run_json = [
            {
                "claim": item.claim,
                "status": item.status,
                "summary": item.summary,
                "command": item.command,
            }
            for item in evidence
            if item.evidence_type in {"test_result", "build_result", "command_output"}
        ]
        missing_evidence = self._missing_handoff_evidence(review_gates, evidence)
        confidence = self._handoff_confidence_level(
            dry_run=project.runner_mode == "dry_run",
            review_gates=review_gates,
            evidence=evidence,
            missing_evidence=missing_evidence,
        )
        next_steps = [redact_text(str(item)) for item in final_report.get("suggested_next_improvements", []) if str(item).strip()]
        if any(gate.required and gate.status != "passed" for gate in review_gates):
            next_steps.append("Resolve remaining required review gates before calling this handoff production-ready.")
        handoff = EvidenceBasedHandoff(
            project_id=project.id,
            title=f"{project.name} evidence-backed handoff",
            summary=redact_text(str(final_report.get("summary_markdown") or final_report.get("summary") or f"{project.name} is ready for handoff review.")),
            what_was_built=what_was_built,
            how_to_run=self._markdown_list(how_to_run_items),
            how_to_use=self._markdown_list(how_to_use_items),
            tests_run_json=tests_run_json or [{"claim": "Validation", "status": "not_run", "summary": "No verified test or build evidence is recorded yet.", "command": None}],
            known_limitations_json=limitations,
            suggested_next_steps_json=next_steps,
            evidence_ids_json=[item.id for item in evidence],
            confidence_level=confidence,
            dry_run=project.runner_mode == "dry_run",
        )
        db.add(handoff)
        db.flush()
        for item in evidence:
            item.handoff_id = handoff.id
        project.status = "handoff_ready" if confidence in {"medium", "high"} else project.status
        project.handoff_status = "ready" if confidence == "high" else "needs_review"
        project.final_report_json = {
            "summary_markdown": handoff.summary,
            "what_was_built": [line[2:] for line in handoff.what_was_built.splitlines() if line.startswith("- ")],
            "how_to_run": [line[2:] for line in handoff.how_to_run.splitlines() if line.startswith("- ")],
            "how_to_use": [line[2:] for line in handoff.how_to_use.splitlines() if line.startswith("- ")],
            "tests_builds_run": [f"{entry['status']}: {entry['claim']}" for entry in handoff.tests_run_json],
            "known_limitations": list(handoff.known_limitations_json or []),
            "suggested_next_improvements": list(handoff.suggested_next_steps_json or []),
            "missing_evidence": missing_evidence,
            "confidence_level": confidence,
            "dry_run": handoff.dry_run,
            "evidence_ids": list(handoff.evidence_ids_json or []),
        }
        self._record_timeline_event(
            db,
            project,
            event_type="handoff_updated",
            title="Evidence-based handoff updated",
            summary=f"Handoff confidence is {confidence}.",
            severity="success" if confidence == "high" else "warning",
            related_handoff_id=handoff.id,
        )
        if missing_evidence:
            self._record_manager_message(
                db,
                project,
                role="system",
                message_type="handoff_report",
                content_markdown=(
                    "Handoff evidence warning:\n\n"
                    + "\n".join(f"- {item}" for item in missing_evidence)
                ),
                metadata_json={"handoff_id": handoff.id, "response_mode": "reliability_handoff"},
            )
        self.events.publish(db, project.id, "handoff_updated", {"project_id": project.id, "handoff_id": handoff.id, "confidence_level": confidence})
        db.flush()
        return handoff

    def generate_runbook(self, db: Session, project: Project) -> Runbook:
        repo = self._scan_repo_intelligence(db, project)
        handoff = self._latest_evidence_handoff(db, project.id)
        runbook = db.scalar(select(Runbook).where(Runbook.project_id == project.id).order_by(Runbook.updated_at.desc(), Runbook.id.desc()))
        build_command = repo.build_commands_json[0] if repo.build_commands_json else "No build command detected."
        test_command = repo.test_commands_json[0] if repo.test_commands_json else "No automated test command detected."
        logs_location = str(self._project_docs_dir(project))
        deploy_note = "No deployment config detected." if not repo.deployment_config_json else f"Deployment config: {', '.join(repo.deployment_config_json[:3])}"
        content = "\n\n".join(
            [
                "# Runbook",
                "## How to start dev server\n" + self._markdown_list([
                    "Backend: cd apps/server && python -m uvicorn main:app --app-dir src --reload",
                    "Frontend: cd apps/dashboard && npm run dev",
                ]),
                "## How to run tests\n" + self._markdown_list([test_command]),
                "## How to build\n" + self._markdown_list([build_command]),
                "## How to debug common failures\n" + self._markdown_list([
                    "Check Manager Chat for approval blockers, conflicts, and recovery plans.",
                    "Inspect Agent Black Box traces for redacted execution summaries.",
                    "Use Snapshots restore plans before any destructive rollback idea gets clever.",
                ]),
                "## How to reset local state\n" + self._markdown_list([
                    "Re-run startup checks from Diagnostics if provider/runtime state drifted.",
                    "Archive or pause the project before reassigning tasks aggressively.",
                ]),
                "## Where logs live\n" + self._markdown_list([logs_location]),
                "## How to deploy if configured\n" + self._markdown_list([deploy_note]),
                "## Known operational risks\n" + self._markdown_list(
                    list(handoff.known_limitations_json if handoff else []) or ["No handoff-backed operational risks are recorded yet."]
                ),
            ]
        )
        if runbook is None:
            runbook = Runbook(project_id=project.id, content_markdown=content, generated_from_handoff_id=handoff.id if handoff else None)
            db.add(runbook)
        else:
            runbook.content_markdown = content
            runbook.generated_from_handoff_id = handoff.id if handoff else None
            runbook.generated_at = utc_now()
        db.flush()
        self._record_timeline_event(db, project, event_type="runbook_updated", title="Runbook updated", summary="Operational runbook was generated from current repo and handoff state.")
        self.events.publish(db, project.id, "runbook_updated", {"project_id": project.id, "runbook_id": runbook.id})
        return runbook

    def update_runbook(self, db: Session, project: Project, content_markdown: str) -> Runbook:
        runbook = db.scalar(select(Runbook).where(Runbook.project_id == project.id).order_by(Runbook.updated_at.desc(), Runbook.id.desc()))
        if runbook is None:
            runbook = Runbook(project_id=project.id, content_markdown=content_markdown)
            db.add(runbook)
        else:
            runbook.content_markdown = content_markdown
        db.flush()
        self.events.publish(db, project.id, "runbook_updated", {"project_id": project.id, "runbook_id": runbook.id})
        return runbook

    def get_runbook(self, db: Session, project: Project) -> Runbook | None:
        return db.scalar(select(Runbook).where(Runbook.project_id == project.id).order_by(Runbook.updated_at.desc(), Runbook.id.desc()))

    def list_agent_traces(self, db: Session, project: Project) -> list[AgentExecutionTrace]:
        return self._ensure_agent_execution_traces(db, project)

    def get_agent_trace(self, db: Session, trace_id: int) -> AgentExecutionTrace:
        trace = db.get(AgentExecutionTrace, trace_id)
        if trace is None:
            raise ValueError("Agent trace not found")
        return trace

    def create_project_snapshot(
        self,
        db: Session,
        project: Project,
        *,
        label: str,
        description: str,
        created_before_task_id: int | None = None,
        created_before_agent_id: int | None = None,
    ) -> ProjectSnapshot:
        self._validate_project_related_refs(
            db,
            project,
            related_agent_id=created_before_agent_id,
            related_task_id=created_before_task_id,
            agent_label="Snapshot agent",
            task_label="Snapshot task",
        )
        workspace = Path(project.workspace_path)
        metadata: dict[str, Any] = {"workspace_path": str(workspace)}
        snapshot_type = "filesystem_marker"
        status = "unsupported"
        git_ref = None
        if self._is_git_workspace(project):
            try:
                head = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=project.workspace_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                branch = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=project.workspace_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                dirty = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=project.workspace_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                snapshot_type = "git_commit"
                status = "available"
                git_ref = head.stdout.strip() or None
                metadata.update({"branch": branch.stdout.strip(), "dirty": bool(dirty.stdout.strip())})
            except (subprocess.SubprocessError, FileNotFoundError):
                metadata["error"] = "Git metadata could not be collected."
        else:
            metadata["note"] = "Workspace is not a Git repository, so only a non-destructive marker can be recorded."
        snapshot = ProjectSnapshot(
            project_id=project.id,
            snapshot_type=snapshot_type,
            label=label,
            description=description,
            git_ref=git_ref,
            created_before_task_id=created_before_task_id,
            created_before_agent_id=created_before_agent_id,
            status=status,
            metadata_json=metadata,
        )
        db.add(snapshot)
        db.flush()
        self._record_timeline_event(
            db,
            project,
            event_type="snapshot_created",
            title=f"Snapshot created: {label}",
            summary=description,
            severity="info",
        )
        self.events.publish(db, project.id, "snapshot_created", {"project_id": project.id, "snapshot_id": snapshot.id, "status": status})
        return snapshot

    def list_snapshots(self, db: Session, project: Project) -> list[ProjectSnapshot]:
        return list(
            db.scalars(
                select(ProjectSnapshot)
                .where(ProjectSnapshot.project_id == project.id)
                .order_by(ProjectSnapshot.created_at.desc(), ProjectSnapshot.id.desc())
            )
        )

    def build_restore_plan(self, db: Session, snapshot_id: int) -> dict[str, Any]:
        snapshot = db.get(ProjectSnapshot, snapshot_id)
        if snapshot is None:
            raise ValueError("Snapshot not found")
        warnings: list[str] = []
        steps: list[str] = []
        summary = "Restore plan prepared."
        if snapshot.status != "available" or snapshot.snapshot_type != "git_commit" or not snapshot.git_ref:
            summary = "Snapshot restore is not directly supported for this workspace."
            warnings.append("No safe Git restore target is recorded. Do not invent a rollback and call it a feature.")
            steps.append("Review workspace state manually.")
        else:
            if snapshot.metadata_json.get("dirty"):
                warnings.append("Working tree was dirty when this snapshot was recorded. A restore must account for uncommitted changes.")
            steps.extend(
                [
                    f"Review current changes with: git status",
                    f"Inspect diff against snapshot: git diff {snapshot.git_ref}..HEAD",
                    "Create a fresh safety branch before any restore operation.",
                    f"Only after approval, consider checking out or branching from {snapshot.git_ref}.",
                ]
            )
        return {
            "snapshot_id": snapshot.id,
            "project_id": snapshot.project_id,
            "status": snapshot.status,
            "summary": summary,
            "steps": steps,
            "warnings": warnings,
        }

    def create_recovery_plan(self, db: Session, project: Project, payload: dict[str, Any]) -> RecoveryPlan:
        self._validate_project_related_refs(
            db,
            project,
            related_agent_id=payload.get("related_agent_id"),
            related_task_id=payload.get("related_task_id"),
            agent_label="Recovery plan related agent",
            task_label="Recovery plan related task",
        )
        plan = RecoveryPlan(
            project_id=project.id,
            trigger_type=str(payload["trigger_type"]).strip(),
            trigger_summary=str(payload["trigger_summary"]).strip(),
            related_agent_id=payload.get("related_agent_id"),
            related_task_id=payload.get("related_task_id"),
            suggested_actions_json=[str(item) for item in (payload.get("suggested_actions_json") or []) if str(item).strip()],
            status="proposed",
        )
        db.add(plan)
        db.flush()
        self._record_manager_message(
            db,
            project,
            role="system",
            message_type="blocker_report",
            content_markdown=f"Recovery plan proposed: **{plan.trigger_summary}**",
            related_agent_id=plan.related_agent_id,
            related_task_id=plan.related_task_id,
            metadata_json={"recovery_plan_id": plan.id, "response_mode": "reliability_recovery"},
        )
        self._record_timeline_event(db, project, event_type="recovery_plan_created", title="Recovery plan proposed", summary=plan.trigger_summary, severity="warning", related_agent_id=plan.related_agent_id, related_task_id=plan.related_task_id)
        self.events.publish(db, project.id, "recovery_plan_created", {"project_id": project.id, "plan_id": plan.id})
        return plan

    def list_recovery_plans(self, db: Session, project: Project) -> list[RecoveryPlan]:
        return list(
            db.scalars(
                select(RecoveryPlan)
                .where(RecoveryPlan.project_id == project.id)
                .order_by(RecoveryPlan.created_at.desc(), RecoveryPlan.id.desc())
            )
        )

    def select_recovery_action(self, db: Session, plan_id: int, action: str) -> RecoveryPlan:
        plan = db.get(RecoveryPlan, plan_id)
        if plan is None:
            raise ValueError("Recovery plan not found")
        project = db.get(Project, plan.project_id)
        if project is None:
            raise ValueError("Project not found")
        normalized_action = self._normalize_recovery_action(action)
        if normalized_action is None:
            raise ValueError("Recovery action is not recognized")
        suggested_actions = {
            normalized
            for normalized in (
                self._normalize_recovery_action(item) for item in (plan.suggested_actions_json or [])
            )
            if normalized is not None
        }
        if suggested_actions and normalized_action not in suggested_actions:
            raise ValueError("Recovery action was not proposed for this plan")
        plan.selected_action = normalized_action
        plan.status = "accepted"
        plan.resolved_at = utc_now() if normalized_action in {"pause_project", "ask_user"} else plan.resolved_at
        self._record_decision(
            db,
            project,
            decision_type="recovery_plan",
            title=f"Recovery: {plan.trigger_type}",
            decision=normalized_action,
            reason=plan.trigger_summary,
            made_by="manager",
            impact_areas=["reliability", "recovery"],
            related_task_id=plan.related_task_id,
            related_agent_id=plan.related_agent_id,
            reversible=normalized_action not in {"simplify_scope"},
        )
        self.events.publish(db, project.id, "recovery_action_selected", {"project_id": project.id, "plan_id": plan.id, "action": normalized_action})
        return plan

    def _normalize_recovery_action(self, action: str | None) -> str | None:
        normalized = " ".join(str(action or "").strip().lower().split())
        if not normalized:
            return None
        aliases = {
            "pause_project": "pause_project",
            "pause project": "pause_project",
            "ask_user": "ask_user",
            "ask user": "ask_user",
            "ask manager": "ask_user",
            "ask user / ask manager": "ask_user",
            "retry_same_agent": "retry_same_agent",
            "retry same agent": "retry_same_agent",
            "split_task": "split_task",
            "split task": "split_task",
            "simplify_scope": "simplify_scope",
            "simplify scope": "simplify_scope",
            "spawn_debug_agent": "spawn_debug_agent",
            "spawn debug agent": "spawn_debug_agent",
        }
        return aliases.get(normalized)

    def get_agent_load(self, db: Session, project: Project) -> list[AgentLoadSnapshot]:
        return self._sync_agent_load_snapshots(db, project)

    def _derive_current_action_preview(self, db: Session, project: Project, degraded_notices: list[str]) -> dict[str, Any]:
        pending_approval = db.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.project_id == project.id, ApprovalRequest.status == "pending")
            .order_by(ApprovalRequest.created_at.asc())
        )
        if pending_approval:
            request_label = "tool approval" if pending_approval.request_type != "command" else "command approval"
            return {
                "id": f"approval-{pending_approval.id}",
                "project_id": project.id,
                "type": "tool_approval" if pending_approval.request_type != "command" else "command_approval",
                "severity": "warning",
                "title": f"Action needed: approve {request_label}.",
                "message": pending_approval.reason_short,
                "requesting_agent_id": pending_approval.requesting_agent_id,
                "related_task_id": pending_approval.task_id,
                "command_id": pending_approval.id if pending_approval.request_type == "command" else None,
                "tool_request_id": pending_approval.id if pending_approval.request_type != "command" else None,
                "question_id": None,
                "created_at": pending_approval.created_at,
                "expires_at": None,
                "auto_decide_at": None,
                "resolved_at": None,
                "actions_json": [{"id": "approve_once", "label": "Approve once"}, {"id": "deny", "label": "Deny"}],
            }
        pending_question = db.scalar(
            select(ManagerQuestion)
            .where(ManagerQuestion.project_id == project.id, ManagerQuestion.status == "pending")
            .order_by(ManagerQuestion.created_at.asc())
        )
        if pending_question:
            return {
                "id": f"question-{pending_question.id}",
                "project_id": project.id,
                "type": "manager_question",
                "severity": "warning" if pending_question.impact == "high" else "info",
                "title": "Manager question: choose an option.",
                "message": pending_question.question,
                "requesting_agent_id": pending_question.related_agent_id,
                "related_task_id": pending_question.related_task_id,
                "command_id": None,
                "tool_request_id": None,
                "question_id": pending_question.id,
                "created_at": pending_question.created_at,
                "expires_at": pending_question.auto_decide_at,
                "auto_decide_at": pending_question.auto_decide_at,
                "resolved_at": None,
                "actions_json": list(pending_question.options_json or []),
            }
        if project.status == "paused":
            return {
                "id": f"paused-{project.id}",
                "project_id": project.id,
                "type": "paused",
                "severity": "warning",
                "title": "Project paused.",
                "message": "New work assignment is paused until you resume the project.",
                "requesting_agent_id": None,
                "related_task_id": None,
                "command_id": None,
                "tool_request_id": None,
                "question_id": None,
                "created_at": project.updated_at,
                "expires_at": None,
                "auto_decide_at": None,
                "resolved_at": None,
                "actions_json": [],
            }
        blocked_task = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status.in_(["blocked", "waiting_on_paths"]))
            .order_by(Task.priority.asc(), Task.id.asc())
        )
        if blocked_task:
            return {
                "id": f"task-{blocked_task.id}",
                "project_id": project.id,
                "type": "blocker",
                "severity": "danger",
                "title": "Blocked",
                "message": blocked_task.waiting_reason or f"{blocked_task.title} is blocked.",
                "requesting_agent_id": None,
                "related_task_id": blocked_task.id,
                "command_id": None,
                "tool_request_id": None,
                "question_id": None,
                "created_at": blocked_task.updated_at,
                "expires_at": None,
                "auto_decide_at": None,
                "resolved_at": None,
                "actions_json": [],
            }
        if degraded_notices:
            return {
                "id": f"degraded-{project.id}",
                "project_id": project.id,
                "type": "degraded",
                "severity": "warning",
                "title": degraded_notices[0],
                "message": "Mission Control can still continue in degraded mode.",
                "requesting_agent_id": None,
                "related_task_id": None,
                "command_id": None,
                "tool_request_id": None,
                "question_id": None,
                "created_at": utc_now(),
                "expires_at": None,
                "auto_decide_at": None,
                "resolved_at": None,
                "actions_json": [],
            }
        if project.status == "handoff_ready":
            return {
                "id": f"handoff-{project.id}",
                "project_id": project.id,
                "type": "handoff_ready",
                "severity": "success",
                "title": "Ready for handoff.",
                "message": "The manager considers this project ready for the final handoff.",
                "requesting_agent_id": None,
                "related_task_id": None,
                "command_id": None,
                "tool_request_id": None,
                "question_id": None,
                "created_at": project.updated_at,
                "expires_at": None,
                "auto_decide_at": None,
                "resolved_at": None,
                "actions_json": [],
            }
        working_agents = db.scalar(select(func.count(Agent.id)).where(Agent.project_id == project.id, Agent.kind == "worker", Agent.status.in_(["working", "starting"]))) or 0
        return {
            "id": f"no-action-{project.id}",
            "project_id": project.id,
            "type": "no_action",
            "severity": "info",
            "title": f"No action needed. {working_agents} agents are working." if working_agents else "No action needed.",
            "message": "The manager is monitoring the workspace and will ask if anything needs a decision.",
            "requesting_agent_id": None,
            "related_task_id": None,
            "command_id": None,
            "tool_request_id": None,
            "question_id": None,
            "created_at": project.updated_at,
            "expires_at": None,
            "auto_decide_at": None,
            "resolved_at": None,
            "actions_json": [],
        }

    def _preview_stuck_signals(self, db: Session, project: Project) -> list[dict[str, Any]]:
        agents = list(db.scalars(select(Agent).where(Agent.project_id == project.id).order_by(Agent.id.asc())))
        now = utc_now()
        preview_rows: list[dict[str, Any]] = []
        for agent in agents:
            signal_type: str | None = None
            message: str | None = None
            severity = "medium"
            last_update = agent.last_update
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=timezone.utc)
            if agent.status in {"blocked", "error"}:
                signal_type = "repeated_error"
                message = agent.last_report_summary or agent.current_action or f"{agent.name} is blocked."
                severity = "high"
            elif agent.status in {"working", "starting"} and (now - last_update) > timedelta(minutes=20):
                signal_type = "no_output_for_threshold"
                message = f"No meaningful update from {agent.name} in more than 20 minutes."
            elif agent.failure_count >= 3:
                signal_type = "task_timeout"
                message = f"{agent.name} has failed or timed out repeatedly."
                severity = "high"
            if signal_type is None or message is None:
                continue
            preview_rows.append(
                {
                    "project_id": project.id,
                    "agent_id": agent.id,
                    "signal_type": signal_type,
                    "message": message,
                    "severity": severity,
                    "detected_at": now,
                }
            )
        return preview_rows

    def _preview_agent_execution_traces(self, db: Session, project: Project) -> list[dict[str, Any]]:
        agent_ids = [agent.id for agent in db.scalars(select(Agent).where(Agent.project_id == project.id))]
        if not agent_ids:
            return []
        runs = list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.agent_id.in_(agent_ids))
                .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
            )
        )
        tasks_by_id = {task.id: task for task in db.scalars(select(Task).where(Task.project_id == project.id))}
        agents_by_id = {agent.id: agent for agent in db.scalars(select(Agent).where(Agent.project_id == project.id))}
        preview_rows: list[dict[str, Any]] = []
        for run in runs:
            agent = agents_by_id.get(run.agent_id)
            task = tasks_by_id.get(run.task_id) if run.task_id is not None else None
            raw_report = self._redact_payload(run.report_json or {})
            files_changed = [str(item) for item in (raw_report.get("files_changed") or []) if str(item).strip()]
            tests_run = [str(item) for item in (raw_report.get("tests_run") or []) if str(item).strip()]
            prompt_bits = [agent.mission if agent and agent.mission else None, task.goal if task else None, task.scope if task else None]
            prompt_summary = " | ".join(bit for bit in prompt_bits if bit) or f"{agent.name if agent else 'Worker'} executed a recorded run."
            preview_rows.append(
                {
                    "id": None,
                    "project_id": project.id,
                    "agent_id": run.agent_id,
                    "task_id": run.task_id,
                    "run_id": run.id,
                    "prompt_summary": prompt_summary[:1000],
                    "response_summary": str(raw_report.get("summary") or run.status or "Run completed.")[:1000],
                    "files_changed_json": files_changed[:40],
                    "commands_attempted_json": ([f"runner:{run.runner_type}"] if run.runner_type else []) + tests_run[:3],
                    "manager_decision_after": run.manager_action,
                    "redaction_status": "redacted_summary",
                    "created_at": run.started_at or run.finished_at or utc_now(),
                    "source": "computed",
                }
            )
        return preview_rows

    def _preview_agent_load_snapshots(self, db: Session, project: Project) -> list[dict[str, Any]]:
        agents = list(db.scalars(select(Agent).where(Agent.project_id == project.id).order_by(Agent.id.asc())))
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.id.asc())))
        now = utc_now()
        preview_rows: list[dict[str, Any]] = []
        for agent in agents:
            if agent.kind != "worker":
                continue
            active_task_count = sum(1 for task in tasks if task.assigned_agent_id == agent.id and task.status == "working")
            waiting_task_count = sum(1 for task in tasks if task.assigned_agent_id == agent.id and task.status in {"assigned", "waiting_on_paths", "needs_review"})
            blocked_task_count = sum(1 for task in tasks if task.assigned_agent_id == agent.id and task.status == "blocked")
            idle_duration_seconds = None
            if agent.status in {"idle", "waiting", "done", "stopped"}:
                last_update = agent.last_update if agent.last_update.tzinfo else agent.last_update.replace(tzinfo=timezone.utc)
                idle_duration_seconds = max(0, int((now - last_update).total_seconds()))
            if blocked_task_count or agent.status in {"blocked", "error"}:
                load_level = "blocked"
            elif active_task_count >= 3:
                load_level = "heavy"
            elif active_task_count >= 1 or waiting_task_count >= 2:
                load_level = "normal"
            elif waiting_task_count == 1:
                load_level = "light"
            else:
                load_level = "idle"
            preview_rows.append(
                {
                    "id": None,
                    "project_id": project.id,
                    "agent_id": agent.id,
                    "active_task_count": active_task_count,
                    "waiting_task_count": waiting_task_count,
                    "blocked_task_count": blocked_task_count,
                    "idle_duration_seconds": idle_duration_seconds,
                    "load_level": load_level,
                    "created_at": now,
                    "source": "computed",
                }
            )
        return preview_rows

    def _preview_agent_rebalance_plan(self, db: Session, project: Project) -> dict[str, Any]:
        snapshots = self._preview_agent_load_snapshots(db, project)
        agents_by_id = {agent.id: agent for agent in db.scalars(select(Agent).where(Agent.project_id == project.id))}
        overloaded = [snap for snap in snapshots if snap["load_level"] in {"heavy", "blocked"}]
        idle = [snap for snap in snapshots if snap["load_level"] == "idle"]
        suggested_reassignments: list[dict[str, Any]] = []
        for overloaded_entry, idle_entry in zip(overloaded, idle):
            overloaded_agent = agents_by_id.get(overloaded_entry["agent_id"])
            idle_agent = agents_by_id.get(idle_entry["agent_id"])
            if not overloaded_agent or not idle_agent:
                continue
            suggested_reassignments.append(
                {
                    "from_agent_id": overloaded_agent.id,
                    "from_agent_name": overloaded_agent.name,
                    "to_agent_id": idle_agent.id,
                    "to_agent_name": idle_agent.name,
                    "note": "Reassign only if the task boundaries and path locks stay compatible.",
                }
            )
        return {
            "overloaded_agents": [
                {
                    "agent_id": snap["agent_id"],
                    "agent_name": agents_by_id.get(snap["agent_id"]).name if agents_by_id.get(snap["agent_id"]) else f"Agent {snap['agent_id']}",
                    "load_level": snap["load_level"],
                    "active_task_count": snap["active_task_count"],
                    "blocked_task_count": snap["blocked_task_count"],
                }
                for snap in overloaded
            ],
            "idle_agents": [
                {
                    "agent_id": snap["agent_id"],
                    "agent_name": agents_by_id.get(snap["agent_id"]).name if agents_by_id.get(snap["agent_id"]) else f"Agent {snap['agent_id']}",
                    "load_level": snap["load_level"],
                    "idle_duration_seconds": snap["idle_duration_seconds"],
                }
                for snap in idle
            ],
            "suggested_reassignments": suggested_reassignments,
            "risks": [
                "Do not rebalance high-risk work without checking contracts and path locks.",
                "Idle agents are not free if their archetype does not match the task.",
            ],
        }

    def _preview_manager_assumptions(self, db: Session, project: Project) -> list[dict[str, Any]]:
        understanding = self._project_understanding(project)
        assumptions = [str(item).strip() for item in (understanding.assumptions_json or []) if str(item).strip()]
        preview_rows: list[dict[str, Any]] = [
            {
                "assumption": assumption,
                "reason": "Captured from the Manager's current project understanding.",
                "confidence": 60,
                "status": "active",
                "created_at": understanding.updated_at,
                "source": "computed",
            }
            for assumption in assumptions
        ]
        for question in db.scalars(
            select(ManagerQuestion).where(ManagerQuestion.project_id == project.id, ManagerQuestion.status == "auto_decided").order_by(ManagerQuestion.id.asc())
        ):
            preview_rows.append(
                {
                    "assumption": f"{question.question} -> {question.selected_text or question.selected_option_id or 'Auto-decided'}",
                    "reason": "Auto-decided by the Manager based on project context and configured thresholds.",
                    "confidence": 55,
                    "status": "active",
                    "created_at": question.resolved_at or question.created_at,
                    "source": "computed",
                }
            )
        return preview_rows

    def _compute_repo_intelligence_payload(self, project: Project) -> dict[str, Any]:
        root = Path(project.workspace_path)
        if not root.exists() or not root.is_dir():
            return {
                "languages_json": [],
                "frameworks_json": [],
                "package_managers_json": [],
                "entry_points_json": [],
                "build_commands_json": [],
                "test_commands_json": [],
                "important_folders_json": [],
                "risky_files_json": [],
                "docs_found_json": [],
                "ci_config_json": [],
                "deployment_config_json": [],
                "last_indexed_at": utc_now(),
            }
        file_paths = [path for path in root.rglob("*") if path.is_file()][:1200]
        extensions = Counter(path.suffix.lower() for path in file_paths)
        language_map = {
            ".py": "Python",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".cs": "C#",
            ".rb": "Ruby",
        }
        languages = sorted({language for ext, language in language_map.items() if extensions.get(ext)})
        frameworks: set[str] = set()
        package_managers: set[str] = set()
        build_commands: list[str] = []
        test_commands: list[str] = []
        entry_points: list[str] = []
        package_json = root / "package.json"
        if package_json.exists():
            try:
                package_data = json.loads(package_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                package_data = {}
            deps = {
                **dict(package_data.get("dependencies") or {}),
                **dict(package_data.get("devDependencies") or {}),
            }
            if "react" in deps:
                frameworks.add("React")
            if "vite" in deps:
                frameworks.add("Vite")
            if "next" in deps:
                frameworks.add("Next.js")
            if "fastify" in deps:
                frameworks.add("Fastify")
            if "express" in deps:
                frameworks.add("Express")
            scripts = dict(package_data.get("scripts") or {})
            if scripts.get("build"):
                build_commands.append(f"npm run build ({scripts['build']})")
            if scripts.get("test"):
                test_commands.append(f"npm run test ({scripts['test']})")
            if (root / "package-lock.json").exists():
                package_managers.add("npm")
            if (root / "pnpm-lock.yaml").exists():
                package_managers.add("pnpm")
            if (root / "yarn.lock").exists():
                package_managers.add("yarn")
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            package_managers.add("pip")
            try:
                pyproject_text = pyproject.read_text(encoding="utf-8").lower()
            except OSError:
                pyproject_text = ""
            if "fastapi" in pyproject_text:
                frameworks.add("FastAPI")
            if "django" in pyproject_text:
                frameworks.add("Django")
            if "flask" in pyproject_text:
                frameworks.add("Flask")
        requirements = root / "requirements.txt"
        if requirements.exists():
            package_managers.add("pip")
            try:
                requirements_text = requirements.read_text(encoding="utf-8").lower()
            except OSError:
                requirements_text = ""
            if "fastapi" in requirements_text:
                frameworks.add("FastAPI")
        for candidate in ["main.py", "app.py", "manage.py", "src/main.ts", "src/main.tsx", "src/index.tsx", "src/index.ts", "server.py"]:
            if (root / candidate).exists():
                entry_points.append(candidate)
        important_folders = [folder.name for folder in root.iterdir() if folder.is_dir() and folder.name in {"src", "app", "apps", "server", "client", "docs", "tests", "scripts"}]
        risky_files = [str(path.relative_to(root)) for path in file_paths if path.name.lower().startswith(".env") or "secret" in path.name.lower()][:12]
        docs_found = [str(path.relative_to(root)) for path in file_paths if path.suffix.lower() == ".md" and ("readme" in path.name.lower() or "docs" in path.parts)]
        ci_config = [str(path.relative_to(root)) for path in file_paths if ".github" in path.parts or path.name.lower() in {"azure-pipelines.yml", "azure-pipelines.yaml", ".gitlab-ci.yml"}]
        deployment_config = [
            str(path.relative_to(root))
            for path in file_paths
            if path.name.lower() in {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "vercel.json", "fly.toml", "render.yaml", "netlify.toml"}
        ]
        return {
            "languages_json": languages,
            "frameworks_json": sorted(frameworks),
            "package_managers_json": sorted(package_managers),
            "entry_points_json": entry_points,
            "build_commands_json": build_commands,
            "test_commands_json": test_commands,
            "important_folders_json": important_folders,
            "risky_files_json": risky_files,
            "docs_found_json": docs_found[:20],
            "ci_config_json": ci_config[:20],
            "deployment_config_json": deployment_config[:20],
            "last_indexed_at": utc_now(),
        }

    def _preview_repo_intelligence(self, project: Project) -> dict[str, Any]:
        return self._compute_repo_intelligence_payload(project)

    def _recovery_plan_trigger_specs(
        self,
        *,
        current_action: dict[str, Any],
        stuck_signal_count: int,
        first_stuck_agent_id: int | None,
        tasks: list[Task],
    ) -> list[tuple[str, str, int | None, int | None, list[str]]]:
        triggers: list[tuple[str, str, int | None, int | None, list[str]]] = []
        blocked_tasks = [task for task in tasks if task.status == "blocked"]
        if current_action["type"] in {"blocker", "error", "degraded"}:
            triggers.append(
                (
                    current_action["type"],
                    str(current_action["message"]),
                    current_action.get("requesting_agent_id"),
                    current_action.get("related_task_id"),
                    ["Retry same agent", "Spawn Debug Agent", "Simplify scope", "Ask user / ask Manager"],
                )
            )
        if blocked_tasks:
            triggers.append(
                (
                    "blocked_task",
                    f"{len(blocked_tasks)} task(s) are blocked.",
                    blocked_tasks[0].assigned_agent_id if blocked_tasks else None,
                    blocked_tasks[0].id if blocked_tasks else None,
                    ["Retry same agent", "Split task", "Simplify scope", "Ask user / ask Manager"],
                )
            )
        if stuck_signal_count:
            triggers.append(
                (
                    "stuck_agents",
                    f"{stuck_signal_count} agent(s) may be stuck.",
                    first_stuck_agent_id,
                    None,
                    ["Retry same agent", "Spawn Debug Agent", "Split task", "Ask user / ask Manager"],
                )
            )
        return triggers

    def preview_recovery_plans(self, db: Session, project: Project) -> dict[str, Any]:
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        degraded_notices: list[str] = []
        current_action = self._derive_current_action_preview(db, project, degraded_notices)
        stuck_signals = self._preview_stuck_signals(db, project)
        candidates = [
            {
                "project_id": project.id,
                "trigger_type": trigger_type,
                "trigger_summary": summary,
                "related_agent_id": related_agent_id,
                "related_task_id": related_task_id,
                "suggested_actions_json": actions,
                "status": "proposed",
                "source": "computed",
            }
            for trigger_type, summary, related_agent_id, related_task_id, actions in self._recovery_plan_trigger_specs(
                current_action=current_action,
                stuck_signal_count=len(stuck_signals),
                first_stuck_agent_id=stuck_signals[0]["agent_id"] if stuck_signals else None,
                tasks=tasks,
            )
        ]
        persisted = self.list_recovery_plans(db, project)
        active_keys = {
            (plan.trigger_type, plan.trigger_summary)
            for plan in persisted
            if plan.resolved_at is None
        }
        derived_candidates = [
            item for item in candidates if (str(item["trigger_type"]), str(item["trigger_summary"])) not in active_keys
        ]
        return {
            "project_id": project.id,
            "current_action": current_action,
            "blocked_task_count": sum(1 for task in tasks if task.status == "blocked"),
            "stuck_signal_count": len(stuck_signals),
            "persisted": persisted,
            "derived_candidates": derived_candidates,
            "stored_count": len(persisted),
            "derived_candidate_count": len(derived_candidates),
            "generated_at": utc_now(),
        }

    def build_agent_rebalance_plan(self, db: Session, project: Project) -> dict[str, Any]:
        snapshots = self._sync_agent_load_snapshots(db, project)
        agents_by_id = {agent.id: agent for agent in db.scalars(select(Agent).where(Agent.project_id == project.id))}
        overloaded = [snap for snap in snapshots if snap.load_level in {"heavy", "blocked"}]
        idle = [snap for snap in snapshots if snap.load_level == "idle"]
        suggested_reassignments: list[dict[str, Any]] = []
        for overloaded_entry, idle_entry in zip(overloaded, idle):
            overloaded_agent = agents_by_id.get(overloaded_entry.agent_id)
            idle_agent = agents_by_id.get(idle_entry.agent_id)
            if not overloaded_agent or not idle_agent:
                continue
            suggested_reassignments.append(
                {
                    "from_agent_id": overloaded_agent.id,
                    "from_agent_name": overloaded_agent.name,
                    "to_agent_id": idle_agent.id,
                    "to_agent_name": idle_agent.name,
                    "note": "Reassign only if the task boundaries and path locks stay compatible.",
                }
            )
        return {
            "overloaded_agents": [
                {
                    "agent_id": snap.agent_id,
                    "agent_name": agents_by_id.get(snap.agent_id).name if agents_by_id.get(snap.agent_id) else f"Agent {snap.agent_id}",
                    "load_level": snap.load_level,
                    "active_task_count": snap.active_task_count,
                    "blocked_task_count": snap.blocked_task_count,
                }
                for snap in overloaded
            ],
            "idle_agents": [
                {
                    "agent_id": snap.agent_id,
                    "agent_name": agents_by_id.get(snap.agent_id).name if agents_by_id.get(snap.agent_id) else f"Agent {snap.agent_id}",
                    "load_level": snap.load_level,
                    "idle_duration_seconds": snap.idle_duration_seconds,
                }
                for snap in idle
            ],
            "suggested_reassignments": suggested_reassignments,
            "risks": [
                "Do not rebalance high-risk work without checking contracts and path locks.",
                "Idle agents are not free if their archetype does not match the task.",
            ],
        }

    def create_review_gate(self, db: Session, project: Project, payload: dict[str, Any]) -> ReviewGate:
        self._validate_project_related_refs(
            db,
            project,
            related_agent_id=payload.get("related_agent_id"),
            related_task_id=payload.get("related_task_id"),
            agent_label="Review gate related agent",
            task_label="Review gate related task",
        )
        evidence_ids = self._validate_project_evidence_refs(
            db,
            project,
            evidence_ids=payload.get("evidence_ids_json"),
            evidence_label="Review gate evidence",
        )
        gate = ReviewGate(
            project_id=project.id,
            gate_type=str(payload["gate_type"]).strip(),
            title=str(payload["title"]).strip(),
            status=str(payload.get("status") or "pending"),
            required=bool(payload.get("required", True)),
            related_task_id=payload.get("related_task_id"),
            related_agent_id=payload.get("related_agent_id"),
            required_checks_json=[str(item) for item in (payload.get("required_checks_json") or []) if str(item).strip()],
            evidence_ids_json=evidence_ids,
            result_summary=payload.get("result_summary"),
        )
        db.add(gate)
        db.flush()
        self.events.publish(db, project.id, "review_gate_updated", {"project_id": project.id, "gate_id": gate.id, "status": gate.status})
        return gate

    def update_review_gate(self, db: Session, gate_id: int, payload: dict[str, Any]) -> ReviewGate:
        gate = db.get(ReviewGate, gate_id)
        if gate is None:
            raise ValueError("Review gate not found")
        project = db.get(Project, gate.project_id)
        if project is None:
            raise ValueError("Project not found for review gate")
        self._validate_project_related_refs(
            db,
            project,
            related_agent_id=payload.get("related_agent_id") if "related_agent_id" in payload else None,
            related_task_id=payload.get("related_task_id") if "related_task_id" in payload else None,
            agent_label="Review gate related agent",
            task_label="Review gate related task",
        )
        for field in ["status", "required", "related_task_id", "related_agent_id", "result_summary"]:
            if field in payload and payload[field] is not None:
                setattr(gate, field, payload[field])
        if "required_checks_json" in payload and payload["required_checks_json"] is not None:
            gate.required_checks_json = [str(item) for item in payload["required_checks_json"]]
        if "evidence_ids_json" in payload and payload["evidence_ids_json"] is not None:
            gate.evidence_ids_json = self._validate_project_evidence_refs(
                db,
                project,
                evidence_ids=payload["evidence_ids_json"],
                evidence_label="Review gate evidence",
            )
        db.flush()
        self.events.publish(db, gate.project_id, "review_gate_updated", {"project_id": gate.project_id, "gate_id": gate.id, "status": gate.status})
        return gate

    def get_project_health(self, db: Session, project: Project) -> dict[str, Any]:
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        settings = self._project_settings(db, project)
        _ = settings
        degraded: list[str] = []
        current_action = self._derive_current_action(db, project, degraded)
        overview = self._project_overview(db, project, tasks, current_action)
        support = self._ensure_widget_support_records(db, project, tasks=tasks, degraded_notices=degraded, current_action=current_action, overview=overview)
        return support["health"]

    def get_project_health_preview(self, db: Session, project: Project) -> dict[str, Any]:
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        settings = self._project_settings_preview(db, project)
        _ = settings
        degraded: list[str] = []
        current_action = self._derive_current_action_preview(db, project, degraded)
        overview = self._project_overview(db, project, tasks, current_action)
        support = self._preview_widget_support_records(
            db,
            project,
            tasks=tasks,
            degraded_notices=degraded,
            current_action=current_action,
            overview=overview,
        )
        return support["health"]

    def list_change_requests(self, db: Session, project: Project) -> list[ChangeRequest]:
        return list(
            db.scalars(
                select(ChangeRequest)
                .where(ChangeRequest.project_id == project.id)
                .order_by(ChangeRequest.updated_at.desc(), ChangeRequest.id.desc())
            )
        )

    def triage_change_request(self, db: Session, change_request_id: int) -> dict[str, Any]:
        record = db.get(ChangeRequest, change_request_id)
        if record is None:
            raise ValueError("Change request not found")
        text = record.request_text.lower()
        if any(token in text for token in {"bug", "fix", "broken", "error"}):
            classification = "bugfix"
        elif any(token in text for token in {"docs", "readme", "guide"}):
            classification = "docs"
        elif any(token in text for token in {"test", "coverage", "validate"}):
            classification = "test"
        elif any(token in text for token in {"deploy", "release", "hosting"}):
            classification = "deployment"
        elif any(token in text for token in {"refactor", "cleanup"}):
            classification = "refactor"
        elif any(token in text for token in {"polish", "ux", "ui"}):
            classification = "polish"
        else:
            classification = "feature"
        impact = "architectural" if any(token in text for token in {"architecture", "database", "rewrite", "platform"}) else "large" if len(text) > 180 else "medium" if len(text) > 80 else "small"
        record.classification = classification
        record.impact_estimate = impact
        record.status = "triaged"
        db.flush()
        project = db.get(Project, record.project_id)
        if project is not None:
            self._record_manager_message(
                db,
                project,
                role="system",
                message_type="system_notice",
                content_markdown=f"Change request triaged: **{classification}** / **{impact}** for _{record.request_text}_",
                metadata_json={"change_request_id": record.id, "response_mode": "reliability_change_request"},
            )
            self._record_timeline_event(db, project, event_type="change_request_updated", title="Change request triaged", summary=record.request_text, severity="info")
            self.events.publish(db, project.id, "change_request_updated", {"project_id": project.id, "change_request_id": record.id, "status": record.status})
        return {
            "id": record.id,
            "classification": classification,
            "impact_estimate": impact,
            "status": record.status,
            "note": "Triage is deterministic for now. It is better than random, which is not saying much, but still useful.",
        }

    def update_change_request(self, db: Session, change_request_id: int, payload: dict[str, Any]) -> ChangeRequest:
        record = db.get(ChangeRequest, change_request_id)
        if record is None:
            raise ValueError("Change request not found")
        project = db.get(Project, record.project_id)
        if project is None:
            raise ValueError("Project not found for change request")
        related_handoff_id = (
            self._validate_project_handoff_ref(
                db,
                project,
                related_handoff_id=payload.get("related_handoff_id"),
                handoff_label="Change request related handoff",
            )
            if "related_handoff_id" in payload
            else None
        )
        related_tasks_json = (
            self._validate_project_task_refs(
                db,
                project,
                task_ids=payload.get("related_tasks_json"),
                task_label="Change request related task",
            )
            if "related_tasks_json" in payload and payload["related_tasks_json"] is not None
            else None
        )
        for field in ["classification", "impact_estimate", "status", "related_handoff_id"]:
            if field in payload and payload[field] is not None:
                setattr(record, field, related_handoff_id if field == "related_handoff_id" else payload[field])
        if related_tasks_json is not None:
            record.related_tasks_json = related_tasks_json
        db.flush()
        self.events.publish(db, record.project_id, "change_request_updated", {"project_id": record.project_id, "change_request_id": record.id, "status": record.status})
        return record

    def list_timeline_events(self, db: Session, project: Project) -> list[ProjectTimelineEvent]:
        return list(
            db.scalars(
                select(ProjectTimelineEvent)
                .where(ProjectTimelineEvent.project_id == project.id)
                .order_by(ProjectTimelineEvent.created_at.desc(), ProjectTimelineEvent.id.desc())
            )
        )

    def create_timeline_event(self, db: Session, project: Project, payload: dict[str, Any]) -> ProjectTimelineEvent:
        return self._record_timeline_event(
            db,
            project,
            event_type=str(payload["event_type"]).strip(),
            title=str(payload["title"]).strip(),
            summary=str(payload["summary"]).strip(),
            severity=str(payload.get("severity") or "info"),
            related_agent_id=payload.get("related_agent_id"),
            related_task_id=payload.get("related_task_id"),
            related_handoff_id=payload.get("related_handoff_id"),
        )

    def create_change_request(self, db: Session, project: Project, request_text: str) -> ChangeRequest:
        normalized = " ".join(str(request_text or "").strip().split())
        if not normalized:
            raise ValueError("Change request text cannot be empty.")
        existing = db.scalar(
            select(ChangeRequest)
            .where(
                ChangeRequest.project_id == project.id,
                ChangeRequest.request_text == normalized,
                ChangeRequest.status != "rejected",
            )
            .order_by(ChangeRequest.updated_at.desc(), ChangeRequest.id.desc())
        )
        if existing is not None:
            return existing
        record = ChangeRequest(
            project_id=project.id,
            request_text=normalized,
            classification="needs_triage",
            impact_estimate="unknown",
            status="new",
        )
        db.add(record)
        db.flush()
        self.events.publish(
            db,
            project.id,
            "change_request_updated",
            {
                "project_id": project.id,
                "change_request_id": record.id,
                "status": record.status,
                "classification": record.classification,
                "action": "created",
            },
        )
        self._record_manager_message(
            db,
            project,
            role="system",
            message_type="system_notice",
            content_markdown=(
                f"Change request logged: **{normalized}**\n\n"
                "Ask the Manager to classify scope, estimate impact, and decide whether it belongs in the current milestone."
            ),
            metadata_json={"change_request_id": record.id, "response_mode": "system_notice"},
        )
        signals = scope_creep_service.analyze(
            db,
            project,
            {"source": "change_request", "summary": normalized, "related_message_id": None, "related_task_id": None},
        )
        high_signal = next((item for item in signals if item.severity == "high" and item.status == "open"), None)
        if high_signal is not None:
            existing_scope_question = db.scalar(
                select(ManagerQuestion)
                .where(
                    ManagerQuestion.project_id == project.id,
                    ManagerQuestion.status == "pending",
                )
                .order_by(ManagerQuestion.id.desc())
            )
            if existing_scope_question is None or not (
                existing_scope_question.metadata_json
                and existing_scope_question.metadata_json.get("scope_signal_id") == high_signal.id
            ):
                self._create_question(
                    db,
                    project,
                    question="This expands scope beyond the approved MVP. Include now, defer, or create future milestone?",
                    options_json=[
                        {"id": "include_now", "label": "Include now"},
                        {"id": "defer", "label": "Defer"},
                        {"id": "create_future_milestone", "label": "Create future milestone"},
                    ],
                    impact="high",
                    manager_recommendation="create_future_milestone",
                    metadata_json={"scope_signal_id": high_signal.id, "question_type": "scope_creep"},
                )
        self._record_timeline_event(
            db,
            project,
            event_type="change_request_created",
            title="Change request logged",
            summary=normalized,
            severity="info",
        )
        return record

    def _sync_swarm_budget(self, db: Session, project: Project) -> SwarmBudget:
        preferences = self._ensure_swarm_preferences(db, project)
        settings = self._project_settings(db, project)
        budget = project.swarm_budget
        if budget is None:
            budget = SwarmBudget(project_id=project.id)
            db.add(budget)
            db.flush()
            project.swarm_budget = budget
        return self._populate_swarm_budget(db, project, preferences=preferences, settings=settings, budget=budget)

    def _populate_swarm_budget(
        self,
        db: Session,
        project: Project,
        *,
        preferences: SwarmPreferences,
        settings: ProjectSettings,
        budget: SwarmBudget,
    ) -> SwarmBudget:
        active_agents = [
            agent
            for agent in db.scalars(select(Agent).where(Agent.project_id == project.id).order_by(Agent.id.asc()))
            if agent.kind == "worker" and agent.status not in {"done", "stopped"}
        ]
        budget.max_agents = self._swarm_capacity_limit(preferences)
        budget.require_approval_above_agent_count = preferences.require_approval_above_agent_count
        budget.current_active_agents = len(active_agents)
        budget.dynamic_spawning_paused = not preferences.allow_dynamic_spawning
        budget.prefer_local_models = settings.provider in {"ollama", "claude_code"} or settings.runner_mode == "dry_run"
        premium_roles: list[str] = []
        for role_name, model in {
            "manager": settings.manager_model,
            "worker": settings.default_worker_model,
        }.items():
            label = (model or "").lower()
            if any(token in label for token in ("gpt", "claude", "sonnet", "opus")):
                premium_roles.append(role_name)
        budget.premium_models_only_for = premium_roles
        ratio = (budget.current_active_agents / max(1, budget.max_agents)) if budget.max_agents else 0
        if budget.current_active_agents >= max(1, budget.max_agents):
            budget.current_intensity = "extreme"
        elif ratio >= 0.75:
            budget.current_intensity = "high"
        elif ratio >= 0.4:
            budget.current_intensity = "medium"
        else:
            budget.current_intensity = "low"
        return budget

    def _preview_swarm_budget(self, db: Session, project: Project) -> SwarmBudget:
        preferences = project.swarm_preferences or self._swarm_preferences(project)
        settings = project.settings or self._project_settings_preview(db, project)
        budget = project.swarm_budget or SwarmBudget(project_id=project.id)
        return self._populate_swarm_budget(db, project, preferences=preferences, settings=settings, budget=budget)

    def _agent_contract_payloads(self, db: Session, project: Project) -> list[dict[str, Any]]:
        plan = self._current_swarm_plan_record(db, project.id)
        specs = self._swarm_specs_for_plan(db, plan.id) if plan is not None else []
        agents = list(db.scalars(select(Agent).where(Agent.project_id == project.id).order_by(Agent.id.asc())))
        agent_lookup = {agent.name: agent for agent in agents}
        sources: list[dict[str, Any]] = []
        if specs:
            for spec in specs:
                sources.append(
                    {
                        "agent_name": spec.name,
                        "agent_id": agent_lookup.get(spec.name).id if agent_lookup.get(spec.name) else None,
                        "archetype": spec.archetype,
                        "mission": spec.mission,
                        "allowed_paths_json": list(spec.allowed_paths_json or []),
                        "forbidden_paths_json": list(spec.forbidden_paths_json or []),
                        "allowed_tools_json": list(spec.toolset_json or []),
                        "expected_output": f"Complete the {spec.name} mission and report changed files, validations, blockers, and recommended next steps.",
                        "validation_required_json": list(plan.validation_strategy_json or []),
                        "stop_conditions_json": [spec.retire_when],
                        "escalation_conditions_json": ["Path conflict prevents safe progress.", "Required approval blocks execution."],
                        "completion_report_schema_json": {
                            "summary": "string",
                            "files_changed": ["string"],
                            "tests_run": ["string"],
                            "blockers": ["string"],
                        },
                        "status": "active" if spec.status in {"spawned", "planned"} else spec.status,
                    }
                )
        else:
            for agent in agents:
                if agent.kind != "worker":
                    continue
                sources.append(
                    {
                        "agent_name": agent.name,
                        "agent_id": agent.id,
                        "archetype": agent.archetype or "feature",
                        "mission": agent.mission or agent.role,
                        "allowed_paths_json": list(agent.locked_paths_json or []),
                        "forbidden_paths_json": [],
                        "allowed_tools_json": [],
                        "expected_output": f"Complete the current mission for {agent.name} and report status cleanly.",
                        "validation_required_json": [],
                        "stop_conditions_json": [agent.retire_when or "Mission is complete."],
                        "escalation_conditions_json": ["Task is blocked.", "Approval is required."],
                        "completion_report_schema_json": {"summary": "string", "blockers": ["string"]},
                        "status": "active" if agent.status not in {"done", "stopped"} else "retired",
                    }
                )
        return sources

    def _sync_agent_contracts(self, db: Session, project: Project) -> list[AgentContract]:
        existing = {entry.agent_name: entry for entry in db.scalars(select(AgentContract).where(AgentContract.project_id == project.id))}
        active_names: set[str] = set()
        for payload in self._agent_contract_payloads(db, project):
            active_names.add(str(payload["agent_name"]))
            contract = existing.get(str(payload["agent_name"]))
            if contract is None:
                contract = AgentContract(project_id=project.id, agent_name=str(payload["agent_name"]), archetype=str(payload["archetype"]), mission=str(payload["mission"]), expected_output=str(payload["expected_output"]))
                db.add(contract)
                existing[contract.agent_name] = contract
            contract.agent_id = payload["agent_id"]
            contract.archetype = str(payload["archetype"])
            contract.mission = str(payload["mission"])
            contract.allowed_paths_json = list(payload["allowed_paths_json"])
            contract.forbidden_paths_json = list(payload["forbidden_paths_json"])
            contract.allowed_tools_json = list(payload["allowed_tools_json"])
            contract.expected_output = str(payload["expected_output"])
            contract.validation_required_json = list(payload["validation_required_json"])
            contract.stop_conditions_json = list(payload["stop_conditions_json"])
            contract.escalation_conditions_json = list(payload["escalation_conditions_json"])
            contract.completion_report_schema_json = dict(payload["completion_report_schema_json"])
            contract.status = str(payload["status"])
        for name, contract in existing.items():
            if name not in active_names and contract.status not in {"completed", "retired"}:
                contract.status = "retired"
        db.flush()
        return list(db.scalars(select(AgentContract).where(AgentContract.project_id == project.id).order_by(AgentContract.updated_at.desc(), AgentContract.id.asc())))

    def _preview_agent_contracts(self, db: Session, project: Project) -> list[AgentContract]:
        existing = {entry.agent_name: entry for entry in list(project.agent_contracts or [])}
        active_names: set[str] = set()
        now = utc_now()
        for payload in self._agent_contract_payloads(db, project):
            active_names.add(str(payload["agent_name"]))
            contract = existing.get(str(payload["agent_name"]))
            if contract is None:
                contract = AgentContract(
                    project_id=project.id,
                    agent_name=str(payload["agent_name"]),
                    archetype=str(payload["archetype"]),
                    mission=str(payload["mission"]),
                    expected_output=str(payload["expected_output"]),
                    created_at=now,
                    updated_at=now,
                )
                existing[contract.agent_name] = contract
            contract.agent_id = payload["agent_id"]
            contract.archetype = str(payload["archetype"])
            contract.mission = str(payload["mission"])
            contract.allowed_paths_json = list(payload["allowed_paths_json"])
            contract.forbidden_paths_json = list(payload["forbidden_paths_json"])
            contract.allowed_tools_json = list(payload["allowed_tools_json"])
            contract.expected_output = str(payload["expected_output"])
            contract.validation_required_json = list(payload["validation_required_json"])
            contract.stop_conditions_json = list(payload["stop_conditions_json"])
            contract.escalation_conditions_json = list(payload["escalation_conditions_json"])
            contract.completion_report_schema_json = dict(payload["completion_report_schema_json"])
            contract.status = str(payload["status"])
        for name, contract in existing.items():
            if name not in active_names and contract.status not in {"completed", "retired"}:
                contract.status = "retired"
        return sorted(existing.values(), key=lambda item: ((item.updated_at or item.created_at or now), item.id or 0), reverse=True)

    def _sync_path_locks(self, db: Session, project: Project) -> list[PathLock]:
        reservations = self.list_reservations(db, project.id)
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.id.asc())))
        existing = {
            (entry.path_pattern, entry.owner_agent_id, entry.owner_task_id, entry.status): entry
            for entry in db.scalars(select(PathLock).where(PathLock.project_id == project.id))
        }
        active_keys: set[tuple[str, int | None, int | None, str]] = set()
        for reservation in reservations:
            key = (reservation.path, reservation.agent_id, reservation.task_id, "active")
            active_keys.add(key)
            lock = existing.get(key)
            if lock is None:
                lock = PathLock(
                    project_id=project.id,
                    path_pattern=reservation.path,
                    owner_agent_id=reservation.agent_id,
                    owner_task_id=reservation.task_id,
                    reason="Reserved for active task execution.",
                    status="active",
                )
                db.add(lock)
        for task in tasks:
            if task.status != "waiting_on_paths":
                continue
            for path_pattern in task.allowed_paths_json or []:
                key = (path_pattern, None, task.id, "waiting")
                active_keys.add(key)
                if existing.get(key) is None:
                    db.add(
                        PathLock(
                            project_id=project.id,
                            path_pattern=path_pattern,
                            owner_agent_id=None,
                            owner_task_id=task.id,
                            reason=task.waiting_reason or "Waiting for path ownership to clear.",
                            status="waiting",
                        )
                    )
        for key, lock in existing.items():
            if key not in active_keys and lock.status != "released":
                lock.status = "released"
                lock.released_at = utc_now()
        db.flush()
        return list(db.scalars(select(PathLock).where(PathLock.project_id == project.id).order_by(PathLock.status.asc(), PathLock.created_at.desc())))

    def _preview_path_locks(self, db: Session, project: Project) -> list[PathLock]:
        reservations = self.list_reservations(db, project.id)
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.id.asc())))
        now = utc_now()
        preview = {
            (entry.path_pattern, entry.owner_agent_id, entry.owner_task_id, entry.status): entry
            for entry in list(project.path_locks or [])
        }
        active_keys: set[tuple[str, int | None, int | None, str]] = set()
        for reservation in reservations:
            key = (reservation.path, reservation.agent_id, reservation.task_id, "active")
            active_keys.add(key)
            if preview.get(key) is None:
                preview[key] = PathLock(
                    project_id=project.id,
                    path_pattern=reservation.path,
                    owner_agent_id=reservation.agent_id,
                    owner_task_id=reservation.task_id,
                    reason="Reserved for active task execution.",
                    status="active",
                    created_at=now,
                )
        for task in tasks:
            if task.status != "waiting_on_paths":
                continue
            for path_pattern in task.allowed_paths_json or []:
                key = (path_pattern, None, task.id, "waiting")
                active_keys.add(key)
                if preview.get(key) is None:
                    preview[key] = PathLock(
                        project_id=project.id,
                        path_pattern=path_pattern,
                        owner_agent_id=None,
                        owner_task_id=task.id,
                        reason=task.waiting_reason or "Waiting for path ownership to clear.",
                        status="waiting",
                        created_at=now,
                    )
        for key, lock in preview.items():
            if key not in active_keys and lock.status != "released":
                lock.status = "released"
                lock.released_at = now
        return sorted(preview.values(), key=lambda item: (item.status, item.created_at or now))

    def _sync_project_confidence(self, db: Session, project: Project) -> list[ProjectConfidence]:
        understanding = self._ensure_project_understanding(db, project)
        existing = {
            entry.category: entry
            for entry in db.scalars(select(ProjectConfidence).where(ProjectConfidence.project_id == project.id))
        }
        entries = self._project_confidence_entries(project, understanding, existing=existing)
        for entry in entries:
            if entry.id is None:
                db.add(entry)
        db.flush()
        return list(
            db.scalars(
                select(ProjectConfidence)
                .where(ProjectConfidence.project_id == project.id)
                .order_by(ProjectConfidence.confidence_score.asc(), ProjectConfidence.category.asc())
            )
        )

    def _project_confidence_entries(
        self,
        project: Project,
        understanding: ProjectUnderstanding,
        *,
        existing: dict[str, ProjectConfidence] | None = None,
    ) -> list[ProjectConfidence]:
        default_categories = [
            "architecture",
            "UI requirements",
            "testing",
            "deployment",
            "security",
            "integrations",
            "documentation",
            "data/storage",
            "performance",
            "user goals",
        ]
        existing = existing or {}
        confidence_map = self._normalize_confidence_map(dict(understanding.confidence_by_category_json or {}))
        unknowns_map = dict(understanding.unknowns_json or {})
        for category in default_categories:
            entry = existing.get(category)
            if entry is None:
                entry = ProjectConfidence(project_id=project.id, category=category, reason="Confidence has not been assessed yet.")
                existing[category] = entry
            raw_score = confidence_map.get(category) or confidence_map.get(category.lower()) or 0.0
            score = int(round(float(raw_score) * 100)) if raw_score <= 1 else int(raw_score)
            unknowns = unknowns_map.get(category) or unknowns_map.get(category.lower()) or []
            if isinstance(unknowns, str):
                unknowns = [unknowns]
            entry.confidence_score = max(0, min(100, score))
            entry.unknowns_json = [str(item) for item in unknowns if str(item).strip()]
            if entry.unknowns_json:
                entry.reason = f"Confidence is limited by unresolved items in {category}."
            elif entry.confidence_score >= 75:
                entry.reason = f"{category} looks reasonably well understood."
            elif entry.confidence_score >= 40:
                entry.reason = f"{category} is partially understood but still needs clarification."
            else:
                entry.reason = f"{category} is still underspecified."
        return sorted(existing.values(), key=lambda item: (item.confidence_score, item.category.lower()))

    def _preview_project_confidence(self, project: Project) -> list[ProjectConfidence]:
        understanding = self._project_understanding(project)
        existing = {
            entry.category: entry
            for entry in list(project.project_confidence or [])
        }
        return self._project_confidence_entries(project, understanding, existing=existing)

    def _ensure_stuck_signals(self, db: Session, project: Project) -> list[AgentStuckSignal]:
        agents = list(db.scalars(select(Agent).where(Agent.project_id == project.id).order_by(Agent.id.asc())))
        existing = {
            (entry.agent_id, entry.signal_type): entry
            for entry in db.scalars(select(AgentStuckSignal).where(AgentStuckSignal.project_id == project.id, AgentStuckSignal.resolved_at.is_(None)))
        }
        active_keys: set[tuple[int, str]] = set()
        now = utc_now()
        for agent in agents:
            signal_type: str | None = None
            message: str | None = None
            severity = "medium"
            last_update = agent.last_update
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=timezone.utc)
            if agent.status in {"blocked", "error"}:
                signal_type = "repeated_error"
                message = agent.last_report_summary or agent.current_action or f"{agent.name} is blocked."
                severity = "high"
            elif agent.status in {"working", "starting"} and (now - last_update) > timedelta(minutes=20):
                signal_type = "no_output_for_threshold"
                message = f"No meaningful update from {agent.name} in more than 20 minutes."
            elif agent.failure_count >= 3:
                signal_type = "task_timeout"
                message = f"{agent.name} has failed or timed out repeatedly."
                severity = "high"
            if signal_type is None or message is None:
                continue
            key = (agent.id, signal_type)
            active_keys.add(key)
            signal = existing.get(key)
            if signal is None:
                signal = AgentStuckSignal(project_id=project.id, agent_id=agent.id, signal_type=signal_type, message=message, severity=severity)
                db.add(signal)
            else:
                signal.message = message
                signal.severity = severity
        for key, signal in existing.items():
            if key not in active_keys:
                signal.resolved_at = now
        db.flush()
        return list(
            db.scalars(
                select(AgentStuckSignal)
                .where(AgentStuckSignal.project_id == project.id, AgentStuckSignal.resolved_at.is_(None))
                .order_by(AgentStuckSignal.detected_at.desc())
            )
        )

    def _ensure_recovery_plans(
        self,
        db: Session,
        project: Project,
        *,
        current_action: dict[str, Any],
        stuck_signals: list[AgentStuckSignal],
        tasks: list[Task],
    ) -> list[RecoveryPlan]:
        triggers = self._recovery_plan_trigger_specs(
            current_action=current_action,
            stuck_signal_count=len(stuck_signals),
            first_stuck_agent_id=stuck_signals[0].agent_id if stuck_signals else None,
            tasks=tasks,
        )
        existing = {
            (entry.trigger_type, entry.trigger_summary): entry
            for entry in db.scalars(select(RecoveryPlan).where(RecoveryPlan.project_id == project.id, RecoveryPlan.resolved_at.is_(None)))
        }
        active_keys: set[tuple[str, str]] = set()
        for trigger_type, summary, related_agent_id, related_task_id, actions in triggers:
            key = (trigger_type, summary)
            active_keys.add(key)
            entry = existing.get(key)
            if entry is None:
                entry = RecoveryPlan(
                    project_id=project.id,
                    trigger_type=trigger_type,
                    trigger_summary=summary,
                    related_agent_id=related_agent_id,
                    related_task_id=related_task_id,
                    suggested_actions_json=actions,
                    status="proposed",
                )
                db.add(entry)
                self._record_timeline_event(
                    db,
                    project,
                    event_type="recovery_plan_created",
                    title=f"Recovery proposed: {trigger_type}",
                    summary=summary,
                    severity="warning",
                    related_agent_id=related_agent_id,
                    related_task_id=related_task_id,
                )
        for key, entry in existing.items():
            if key not in active_keys:
                entry.resolved_at = utc_now()
                if entry.status == "proposed":
                    entry.status = "completed"
        db.flush()
        return list(
            db.scalars(
                select(RecoveryPlan)
                .where(RecoveryPlan.project_id == project.id)
                .order_by(RecoveryPlan.created_at.desc(), RecoveryPlan.id.desc())
            )
        )

    def _review_gate_requirements(
        self,
        project: Project,
        *,
        tasks: list[Task],
        overview: dict[str, Any],
        testing_depth: str,
        latest_handoff: EvidenceBasedHandoff | None,
        conflicts: list[ConflictRecord] | None = None,
    ) -> dict[str, dict[str, Any]]:
        conflicts = conflicts or []
        task_status_counts = Counter(task.status for task in tasks)
        latest_handoff_evidence_ids = list(latest_handoff.evidence_ids_json or []) if latest_handoff is not None else []
        unresolved_conflicts = [entry for entry in conflicts if entry.status not in {"resolved", "dismissed"}]
        missing_evidence = list((project.final_report_json or {}).get("missing_evidence") or [])
        return {
            "code_review": {
                "title": "Code review gate",
                "required": True,
                "checks": ["No tasks remain in review.", "No unresolved blockers remain."],
                "status": "passed" if task_status_counts.get("needs_review", 0) == 0 else "pending",
                "summary": "Review tasks are clear." if task_status_counts.get("needs_review", 0) == 0 else "Tasks still require review.",
                "evidence_ids": [],
            },
            "test": {
                "title": "Validation gate",
                "required": testing_depth != "minimal",
                "checks": ["Validation recipe is defined.", "Critical tests or smoke checks are accounted for."],
                "status": "passed" if overview["checklist"][4]["status"] == "complete" else ("failed" if task_status_counts.get("blocked", 0) else "pending"),
                "summary": overview["checklist"][4]["detail"],
                "evidence_ids": latest_handoff_evidence_ids,
            },
            "security": {
                "title": "Security gate",
                "required": testing_depth in {"extensive", "release_grade"},
                "checks": ["Security-sensitive areas reviewed when required."],
                "status": "passed" if overview["checklist"][3]["status"] == "complete" else "pending",
                "summary": overview["checklist"][3]["detail"],
                "evidence_ids": [],
            },
            "docs": {
                "title": "Documentation gate",
                "required": True,
                "checks": ["README, handoff notes, and run instructions are ready enough."],
                "status": "passed" if overview["checklist"][5]["status"] == "complete" else "pending",
                "summary": overview["checklist"][5]["detail"],
                "evidence_ids": [],
            },
            "handoff": {
                "title": "Handoff gate",
                "required": True,
                "checks": ["Overall readiness is acceptable for handoff."],
                "status": "passed" if latest_handoff is not None and latest_handoff.confidence_level == "high" and not missing_evidence else ("failed" if missing_evidence else "pending"),
                "summary": f"Handoff progress is {overview['handoff_progress']}%." if not missing_evidence else "; ".join(missing_evidence[:3]),
                "evidence_ids": latest_handoff_evidence_ids,
            },
            "conflict_resolution": {
                "title": "Conflict resolution gate",
                "required": bool(unresolved_conflicts),
                "checks": ["Parallel edit conflicts are resolved before handoff or risky reassignment."],
                "status": "passed" if not unresolved_conflicts else ("failed" if any(item.severity in {"high", "critical"} for item in unresolved_conflicts) else "pending"),
                "summary": "No active conflicts." if not unresolved_conflicts else f"{len(unresolved_conflicts)} unresolved conflict(s) remain.",
                "evidence_ids": [],
            },
        }

    def _review_gate_entries(
        self,
        project: Project,
        requirements: dict[str, dict[str, Any]],
        *,
        existing: dict[str, ReviewGate] | None = None,
    ) -> list[ReviewGate]:
        existing = existing or {}
        for gate_type, payload in requirements.items():
            gate = existing.get(gate_type)
            if gate is None:
                gate = ReviewGate(project_id=project.id, gate_type=gate_type, title=payload["title"])
                existing[gate_type] = gate
            gate.title = payload["title"]
            gate.required = bool(payload["required"])
            gate.required_checks_json = list(payload["checks"])
            gate.status = str(payload["status"])
            gate.result_summary = str(payload["summary"])
            gate.evidence_ids_json = list(payload.get("evidence_ids", []))
        return sorted(existing.values(), key=lambda item: (not item.required, item.gate_type))

    def _sync_review_gates(
        self,
        db: Session,
        project: Project,
        *,
        tasks: list[Task],
        overview: dict[str, Any],
        testing_depth: str,
        conflicts: list[ConflictRecord] | None = None,
    ) -> list[ReviewGate]:
        latest_handoff = self._latest_evidence_handoff(db, project.id)
        requirements = self._review_gate_requirements(
            project,
            tasks=tasks,
            overview=overview,
            testing_depth=testing_depth,
            latest_handoff=latest_handoff,
            conflicts=conflicts,
        )
        existing = {
            entry.gate_type: entry
            for entry in db.scalars(select(ReviewGate).where(ReviewGate.project_id == project.id))
        }
        gates = self._review_gate_entries(project, requirements, existing=existing)
        for gate in gates:
            if gate.id is None:
                db.add(gate)
        db.flush()
        return list(db.scalars(select(ReviewGate).where(ReviewGate.project_id == project.id).order_by(ReviewGate.required.desc(), ReviewGate.gate_type.asc())))

    def _preview_review_gates(
        self,
        db: Session,
        project: Project,
        *,
        tasks: list[Task],
        overview: dict[str, Any],
        testing_depth: str,
        conflicts: list[ConflictRecord] | None = None,
    ) -> list[ReviewGate]:
        latest_handoff = self._latest_evidence_handoff(db, project.id)
        requirements = self._review_gate_requirements(
            project,
            tasks=tasks,
            overview=overview,
            testing_depth=testing_depth,
            latest_handoff=latest_handoff,
            conflicts=conflicts,
        )
        existing = {entry.gate_type: entry for entry in list(project.review_gates or [])}
        return self._review_gate_entries(project, requirements, existing=existing)

    def _model_policy_values(self, project: Project, settings: ProjectSettings) -> dict[str, Any]:
        provider = settings.provider
        fallback = default_label(provider)
        worker_default = settings.default_worker_model or fallback
        return {
            "policy_name": (
                "local_first"
                if provider in {"ollama", "claude_code"} or settings.runner_mode == "dry_run"
                else "custom"
                if settings.manager_model or settings.default_worker_model
                else "balanced"
            ),
            "manager_model": settings.manager_model or resolve_manager_settings(project, settings).effective_model_label,
            "coding_model": settings.per_role_model_overrides_json.get("feature") or worker_default,
            "docs_model": settings.per_role_model_overrides_json.get("docs") or worker_default,
            "review_model": settings.per_role_model_overrides_json.get("reviewer") or worker_default,
            "test_model": settings.per_role_model_overrides_json.get("test") or worker_default,
            "research_model": settings.per_role_model_overrides_json.get("research") or worker_default,
            "security_model": settings.per_role_model_overrides_json.get("security") or worker_default,
            "fallback_model": fallback,
            "notes": "Mirrors current Project Settings so widgets can summarize role-to-model routing honestly.",
        }

    def _ensure_model_policy(self, db: Session, project: Project) -> ModelPolicy:
        settings = self._project_settings(db, project)
        policy = db.scalar(select(ModelPolicy).where(ModelPolicy.project_id == project.id).order_by(ModelPolicy.id.asc()))
        if policy is None:
            policy = ModelPolicy(project_id=project.id, policy_name="balanced")
            db.add(policy)
            db.flush()
        for field, value in self._model_policy_values(project, settings).items():
            setattr(policy, field, value)
        db.flush()
        return policy

    def _preview_model_policy(self, db: Session, project: Project) -> ModelPolicy:
        settings = project.settings or self._project_settings_preview(db, project)
        policy = next(iter(project.model_policies or []), None) or ModelPolicy(project_id=project.id, policy_name="balanced")
        for field, value in self._model_policy_values(project, settings).items():
            setattr(policy, field, value)
        return policy

    def _tool_routing_entries(
        self,
        db: Session,
        project: Project,
        *,
        settings: ProjectSettings,
        existing: dict[str, ToolRoutingPolicy] | None = None,
        use_preview_archetypes: bool = False,
    ) -> list[ToolRoutingPolicy]:
        profile = self._app_profile_preview(db)
        tool_catalog = catalog_with_permissions(
            provider=settings.provider,
            connected_accounts=dict(profile.connected_accounts_json or {}),
            permission_overrides=dict(profile.tool_permission_overrides_json or {}),
        )
        availability_by_tool = {item["id"]: item for item in tool_catalog}
        existing = existing or {}
        archetypes = self._archetype_lookup_preview() if use_preview_archetypes else self._archetype_lookup(db)
        for archetype_name in ["manager", "planner", "research", "frontend", "backend", "feature", "test", "reviewer", "security", "docs", "ops"]:
            entry = existing.get(archetype_name)
            if entry is None:
                entry = ToolRoutingPolicy(project_id=project.id, agent_archetype=archetype_name)
                existing[archetype_name] = entry
            defaults = list((archetypes.get(archetype_name).default_tools_json if archetypes.get(archetype_name) else []) or [])
            allowed: list[str] = []
            approval: list[str] = []
            blocked: list[str] = []
            for tool_id in defaults:
                tool = availability_by_tool.get(tool_id)
                if tool is None:
                    blocked.append(tool_id)
                    continue
                if tool["availability"] in {"coming_soon", "unsupported_on_device"}:
                    blocked.append(tool_id)
                    continue
                allowed.append(tool_id)
                if tool["permission_policy"] in {"ask_every_time", "ask_once_per_project"}:
                    approval.append(tool_id)
            entry.allowed_tools_json = allowed
            entry.requires_approval_tools_json = approval
            entry.blocked_tools_json = blocked
            entry.notes = "Derived from agent archetype defaults and current Skills & Tools availability."
        return sorted(existing.values(), key=lambda item: item.agent_archetype.lower())

    def _ensure_tool_routing_policies(self, db: Session, project: Project) -> list[ToolRoutingPolicy]:
        settings = self._project_settings(db, project)
        existing = {
            entry.agent_archetype: entry
            for entry in db.scalars(select(ToolRoutingPolicy).where(ToolRoutingPolicy.project_id == project.id))
        }
        entries = self._tool_routing_entries(db, project, settings=settings, existing=existing)
        for entry in entries:
            if entry.id is None:
                db.add(entry)
        db.flush()
        return list(
            db.scalars(
                select(ToolRoutingPolicy)
                .where(ToolRoutingPolicy.project_id == project.id)
                .order_by(ToolRoutingPolicy.agent_archetype.asc())
            )
        )

    def _preview_tool_routing_policies(self, db: Session, project: Project) -> list[ToolRoutingPolicy]:
        settings = project.settings or self._project_settings_preview(db, project)
        existing = {entry.agent_archetype: entry for entry in list(project.tool_routing_policies or [])}
        return self._tool_routing_entries(db, project, settings=settings, existing=existing, use_preview_archetypes=True)

    def _default_sandbox_profiles(self) -> list[tuple[str, str, str, str, str, str, str, bool]]:
        return [
            ("strict", "Tightest filesystem and command posture.", "blocked", "read_only", "ask_every_time", "blocked", "blocked", False),
            ("balanced", "Good default for normal local builds.", "limited", "workspace_write", "on_request", "limited", "blocked", True),
            ("build_friendly", "Looser workspace writes for active implementation.", "limited", "workspace_write", "on_request", "limited", "blocked", False),
            ("deployment", "Allows deployment-oriented behavior with approvals.", "limited", "workspace_write", "on_request", "limited", "approval_required", False),
            ("research", "Network-friendly profile for research and planning work.", "limited", "read_only", "on_request", "limited", "blocked", False),
            ("local_only", "No network and local writes only.", "blocked", "workspace_write", "on_request", "blocked", "blocked", False),
        ]

    def _sandbox_profile_entries(
        self,
        existing: dict[str, SandboxProfile] | None = None,
    ) -> list[SandboxProfile]:
        existing = existing or {}
        for name, description, network, file_write, command_approval, external_tool, deployment, is_default in self._default_sandbox_profiles():
            entry = existing.get(name)
            if entry is None:
                entry = SandboxProfile(name=name, description=description, network_policy=network, file_write_policy=file_write, command_approval_policy=command_approval, external_tool_policy=external_tool, deployment_policy=deployment, is_default=is_default)
                existing[name] = entry
            else:
                entry.description = description
                entry.network_policy = network
                entry.file_write_policy = file_write
                entry.command_approval_policy = command_approval
                entry.external_tool_policy = external_tool
                entry.deployment_policy = deployment
                entry.is_default = is_default
        return sorted(
            existing.values(),
            key=lambda item: (item.id is None, item.id if item.id is not None else item.name.lower()),
        )

    def _ensure_sandbox_profiles(self, db: Session, project: Project) -> list[SandboxProfile]:
        existing = {entry.name: entry for entry in db.scalars(select(SandboxProfile).where(SandboxProfile.project_id.is_(None)))}
        entries = self._sandbox_profile_entries(existing=existing)
        for entry in entries:
            if entry.id is None:
                db.add(entry)
        db.flush()
        return list(db.scalars(select(SandboxProfile).where(SandboxProfile.project_id.is_(None)).order_by(SandboxProfile.id.asc())))

    def _preview_sandbox_profiles(self, db: Session, project: Project) -> list[SandboxProfile]:
        existing = {
            entry.name: entry
            for entry in db.scalars(select(SandboxProfile).where(SandboxProfile.project_id.is_(None)).order_by(SandboxProfile.id.asc()))
        }
        return self._sandbox_profile_entries(existing=existing)

    def _ensure_manager_assumptions(self, db: Session, project: Project) -> list[ManagerAssumption]:
        understanding = self._ensure_project_understanding(db, project)
        existing = {
            entry.assumption: entry
            for entry in db.scalars(
                select(ManagerAssumption).where(ManagerAssumption.project_id == project.id).order_by(ManagerAssumption.id.asc())
            )
        }
        assumptions = [str(item).strip() for item in (understanding.assumptions_json or []) if str(item).strip()]
        for assumption in assumptions:
            entry = existing.get(assumption)
            if entry is None:
                entry = ManagerAssumption(
                    project_id=project.id,
                    assumption=assumption,
                    reason="Captured from the Manager's current project understanding.",
                    impact_area_json=[],
                    confidence=60,
                    status="active",
                )
                db.add(entry)
        auto_questions = db.scalars(
            select(ManagerQuestion).where(ManagerQuestion.project_id == project.id, ManagerQuestion.status == "auto_decided").order_by(ManagerQuestion.id.asc())
        )
        for question in auto_questions:
            assumption = f"{question.question} -> {question.selected_text or question.selected_option_id or 'Auto-decided'}"
            if assumption not in existing:
                db.add(
                    ManagerAssumption(
                        project_id=project.id,
                        assumption=assumption,
                        reason="Auto-decided by the Manager based on project context and configured thresholds.",
                        impact_area_json=[],
                        confidence=55,
                        status="active",
                    )
                )
        db.flush()
        return list(
            db.scalars(
                select(ManagerAssumption)
                .where(ManagerAssumption.project_id == project.id)
                .order_by(ManagerAssumption.created_at.desc(), ManagerAssumption.id.desc())
            )
        )

    def _scan_repo_intelligence(self, db: Session, project: Project) -> RepoIntelligenceSummary:
        summary = project.repo_intelligence
        if summary is None:
            summary = RepoIntelligenceSummary(project_id=project.id)
            db.add(summary)
            db.flush()
            project.repo_intelligence = summary
        payload = self._compute_repo_intelligence_payload(project)
        summary.languages_json = list(payload["languages_json"])
        summary.frameworks_json = list(payload["frameworks_json"])
        summary.package_managers_json = list(payload["package_managers_json"])
        summary.entry_points_json = list(payload["entry_points_json"])
        summary.build_commands_json = list(payload["build_commands_json"])
        summary.test_commands_json = list(payload["test_commands_json"])
        summary.important_folders_json = list(payload["important_folders_json"])
        summary.risky_files_json = list(payload["risky_files_json"])
        summary.docs_found_json = list(payload["docs_found_json"])
        summary.ci_config_json = list(payload["ci_config_json"])
        summary.deployment_config_json = list(payload["deployment_config_json"])
        summary.last_indexed_at = payload["last_indexed_at"]
        db.flush()
        return summary

    def _ensure_validation_recipe(self, db: Session, project: Project) -> ValidationRecipe:
        recipe = db.scalar(select(ValidationRecipe).where(ValidationRecipe.project_id == project.id).order_by(ValidationRecipe.id.asc()))
        if recipe is None:
            recipe = ValidationRecipe(project_id=project.id, name="Default validation recipe", status="draft")
            db.add(recipe)
            db.flush()
        repo = self._scan_repo_intelligence(db, project)
        preferences = self._ensure_swarm_preferences(db, project)
        recipe.steps_json = self._validation_recipe_steps(repo.build_commands_json, repo.test_commands_json, preferences.testing_depth)
        recipe.status = "active"
        db.flush()
        return recipe

    def _validation_recipe_steps(
        self,
        build_commands: list[str] | None,
        test_commands: list[str] | None,
        testing_depth: str,
    ) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for command in list(build_commands or [])[:1]:
            steps.append({"title": "Build the project", "command": command, "type": "build", "requires_approval": True, "status": "pending"})
        for command in list(test_commands or [])[:1]:
            steps.append({"title": "Run automated tests", "command": command, "type": "test", "requires_approval": True, "status": "pending"})
        if testing_depth != "minimal":
            steps.append({"title": "Run smoke validation", "command": None, "type": "smoke", "requires_approval": False, "status": "pending"})
        steps.append({"title": "Review docs and handoff notes", "command": None, "type": "docs", "requires_approval": False, "status": "pending"})
        if not steps:
            steps.append({"title": "Manual validation still needs to be defined.", "command": None, "type": "manual", "requires_approval": False, "status": "pending"})
        return steps

    def _preview_validation_recipe(self, db: Session, project: Project) -> ValidationRecipe:
        recipe = next(iter(project.validation_recipes or []), None) or ValidationRecipe(project_id=project.id, name="Default validation recipe", status="draft")
        repo = project.repo_intelligence
        repo_payload = (
            {
                "build_commands_json": list(repo.build_commands_json or []),
                "test_commands_json": list(repo.test_commands_json or []),
            }
            if repo is not None
            else self._preview_repo_intelligence(project)
        )
        preferences = project.swarm_preferences or self._swarm_preferences(project)
        recipe.steps_json = self._validation_recipe_steps(
            repo_payload.get("build_commands_json"),
            repo_payload.get("test_commands_json"),
            preferences.testing_depth,
        )
        recipe.status = "active"
        return recipe

    def _ensure_handoff_quality(self, db: Session, project: Project) -> HandoffQualityPreference:
        preference = project.handoff_quality_preference
        if preference is None:
            preference = HandoffQualityPreference(project_id=project.id)
        return preference

    def _project_health(
        self,
        project: Project,
        *,
        current_action: dict[str, Any],
        overview: dict[str, Any],
        stuck_signals: list[AgentStuckSignal],
        review_gates: list[ReviewGate],
        pending_approvals: list[dict[str, Any]],
        blocked_agents: list[dict[str, Any]],
        conflicts: list[ConflictRecord] | None = None,
        evidence: list[HandoffEvidence] | None = None,
    ) -> dict[str, Any]:
        conflicts = conflicts or []
        evidence = evidence or []
        reasons: list[str] = []
        risks: list[str] = []
        score = 80
        if current_action["type"] in {"blocker", "error"}:
            reasons.append(str(current_action["message"]))
            risks.append("A blocker or error needs attention.")
            score -= 35
        if blocked_agents:
            reasons.append(f"{len(blocked_agents)} agent(s) are blocked.")
            risks.append("Blocked agents slow the swarm down and tend to create follow-on chaos.")
            score -= 15
        if pending_approvals:
            reasons.append(f"{len(pending_approvals)} approval request(s) are still open.")
            score -= 10
        if stuck_signals:
            reasons.append(f"{len(stuck_signals)} stuck-signal(s) detected.")
            risks.append("At least one agent is stalled or repeatedly failing.")
            score -= 15
        unresolved_conflicts = [conflict for conflict in conflicts if conflict.status not in {"resolved", "dismissed"}]
        if unresolved_conflicts:
            reasons.append(f"{len(unresolved_conflicts)} unresolved conflict(s) remain.")
            risks.append("Parallel work is colliding instead of cooperating.")
            score -= 20
        failed_gates = [gate for gate in review_gates if gate.status == "failed"]
        pending_gates = [gate for gate in review_gates if gate.required and gate.status == "pending"]
        if failed_gates:
            reasons.append(f"{len(failed_gates)} review gate(s) failed.")
            risks.append("Required quality gates are not passing.")
            score -= 20
        elif pending_gates:
            reasons.append(f"{len(pending_gates)} required gate(s) are still pending.")
            score -= 8
        missing_evidence = self._missing_handoff_evidence(review_gates, evidence)
        if missing_evidence:
            reasons.append(f"{len(missing_evidence)} handoff evidence gap(s) exist.")
            risks.append("Handoff confidence is weaker than it should be because proof is missing.")
            score -= 10
        readiness = str(overview["readiness_label"]).lower()
        if readiness == "good" and score >= 75 and not reasons:
            state = "healthy"
        elif "handoff" in project.status or overview["handoff_progress"] >= 95:
            state = "ready_for_handoff"
        elif current_action["type"] in {"blocker", "error"} or unresolved_conflicts:
            state = "blocked"
        elif stuck_signals or failed_gates:
            state = "unstable"
        elif reasons:
            state = "needs_review"
        else:
            state = "unknown"
        return {
            "state": state,
            "score": max(0, min(100, score)),
            "reasons": reasons or ["No major health warnings are recorded right now."],
            "top_risks": risks or ["No acute risks recorded right now."],
            "next_action": current_action["title"] if current_action["type"] != "no_action" else "Keep the current plan moving.",
        }

    def _sync_decision_records(self, db: Session, project: Project) -> list[DecisionRecord]:
        for decision in self._preview_decision_records(db, project, include_existing=False):
            self._record_decision(
                db,
                project,
                decision_type=decision.decision_type,
                title=decision.title,
                decision=decision.decision,
                reason=decision.reason,
                made_by=decision.made_by,
                impact_areas=list(decision.impact_area_json or []),
                related_task_id=decision.related_task_id,
                related_agent_id=decision.related_agent_id,
                reversible=decision.reversible,
            )
        return list(
            db.scalars(
                select(DecisionRecord)
                .where(DecisionRecord.project_id == project.id)
                .order_by(DecisionRecord.created_at.desc(), DecisionRecord.id.desc())
            )
        )

    def _preview_decision_records(
        self,
        db: Session,
        project: Project,
        *,
        include_existing: bool = True,
    ) -> list[DecisionRecord]:
        preview: dict[tuple[str, str], DecisionRecord] = {}
        now = utc_now()
        if include_existing:
            for existing in list(project.decision_records or []):
                preview[(existing.decision_type, existing.title)] = existing
        approvals = db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.project_id == project.id, ApprovalRequest.status != "pending")
            .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
        )
        for approval in approvals:
            preview[(f"{approval.request_type}_approval", approval.title)] = DecisionRecord(
                project_id=project.id,
                decision_type=f"{approval.request_type}_approval",
                title=approval.title,
                decision=approval.status,
                reason=approval.reason_short,
                made_by="user",
                impact_area_json=["approvals", approval.request_type],
                related_task_id=approval.task_id,
                related_agent_id=approval.requesting_agent_id,
                reversible=approval.status != "allowed_for_project",
                created_at=approval.created_at or now,
            )
        questions = db.scalars(
            select(ManagerQuestion)
            .where(ManagerQuestion.project_id == project.id, ManagerQuestion.status != "pending")
            .order_by(ManagerQuestion.created_at.desc(), ManagerQuestion.id.desc())
        )
        for question in questions:
            title = question.question[:220]
            preview[("manager_question", title)] = DecisionRecord(
                project_id=project.id,
                decision_type="manager_question",
                title=question.question[:220],
                decision=question.selected_text or question.selected_option_id or question.status,
                reason=question.manager_recommendation or "Resolved through the Manager queue.",
                made_by="auto_manager" if question.status == "auto_decided" else "user",
                impact_area_json=["requirements"],
                related_task_id=question.related_task_id,
                related_agent_id=question.related_agent_id,
                reversible=question.status != "auto_decided",
                created_at=question.resolved_at or question.created_at or now,
            )
        swarm_plan = self._current_swarm_plan_record(db, project.id)
        if swarm_plan is not None:
            title = f"Swarm strategy: {swarm_plan.mode}"
            preview[("swarm_strategy", title)] = DecisionRecord(
                project_id=project.id,
                decision_type="swarm_strategy",
                title=title,
                decision=swarm_plan.status,
                reason=swarm_plan.strategy_summary,
                made_by="user" if swarm_plan.approved_by_user else "manager",
                impact_area_json=["swarm"],
                reversible=True,
                created_at=swarm_plan.updated_at or swarm_plan.created_at or now,
            )
        return sorted(preview.values(), key=lambda item: (item.created_at or now, item.id or 0), reverse=True)

    def _ensure_widget_support_records(
        self,
        db: Session,
        project: Project,
        *,
        tasks: list[Task] | None = None,
        degraded_notices: list[str] | None = None,
        current_action: dict[str, Any] | None = None,
        overview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tasks = tasks or list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        degraded_notices = degraded_notices or []
        current_action = current_action or self._derive_current_action(db, project, degraded_notices)
        overview = overview or self._project_overview(db, project, tasks, current_action)
        budget = self._sync_swarm_budget(db, project)
        contracts = self._sync_agent_contracts(db, project)
        path_locks = self._sync_path_locks(db, project)
        conflicts = self.detect_conflicts(db, project)
        confidence = self._sync_project_confidence(db, project)
        stuck_signals = self._ensure_stuck_signals(db, project)
        recovery_plans = self._ensure_recovery_plans(db, project, current_action=current_action, stuck_signals=stuck_signals, tasks=tasks)
        review_gates = self._sync_review_gates(
            db,
            project,
            tasks=tasks,
            overview=overview,
            testing_depth=self._ensure_swarm_preferences(db, project).testing_depth,
            conflicts=conflicts,
        )
        model_policy = self._ensure_model_policy(db, project)
        tool_routing = self._ensure_tool_routing_policies(db, project)
        sandbox_profiles = self._ensure_sandbox_profiles(db, project)
        assumptions = self._ensure_manager_assumptions(db, project)
        repo = self._scan_repo_intelligence(db, project)
        validation_recipe = self._ensure_validation_recipe(db, project)
        handoff_quality = self._ensure_handoff_quality(db, project)
        traces = self._ensure_agent_execution_traces(db, project)
        snapshots = self.list_snapshots(db, project)
        agent_load = self._sync_agent_load_snapshots(db, project)
        timeline = self.list_timeline_events(db, project)
        evidence = self.list_handoff_evidence(db, project)
        latest_handoff = self._latest_evidence_handoff(db, project.id)
        runbook = self.get_runbook(db, project)
        decisions = self._sync_decision_records(db, project)
        blocked_agents = [agent for agent in self._sorted_workspace_agents(db, project.id) if agent["display_status"] in {"blocked", "error"}]
        pending_approvals = self.list_pending_approvals(db, project)
        health = self._project_health(
            project,
            current_action=current_action,
            overview=overview,
            stuck_signals=stuck_signals,
            review_gates=review_gates,
            pending_approvals=pending_approvals,
            blocked_agents=blocked_agents,
            conflicts=conflicts,
            evidence=evidence,
        )
        return {
            "budget": budget,
            "contracts": contracts,
            "path_locks": path_locks,
            "conflicts": conflicts,
            "confidence": confidence,
            "stuck_signals": stuck_signals,
            "recovery_plans": recovery_plans,
            "review_gates": review_gates,
            "model_policy": model_policy,
            "tool_routing": tool_routing,
            "sandbox_profiles": sandbox_profiles,
            "assumptions": assumptions,
            "repo": repo,
            "validation_recipe": validation_recipe,
            "handoff_quality": handoff_quality,
            "handoff_evidence": evidence,
            "latest_handoff": latest_handoff,
            "runbook": runbook,
            "agent_traces": traces,
            "snapshots": snapshots,
            "agent_load": agent_load,
            "timeline": timeline,
            "decisions": decisions,
            "health": health,
            "blocked_agents": blocked_agents,
            "pending_approvals": pending_approvals,
        }

    def _preview_widget_support_records(
        self,
        db: Session,
        project: Project,
        *,
        tasks: list[Task] | None = None,
        degraded_notices: list[str] | None = None,
        current_action: dict[str, Any] | None = None,
        overview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tasks = tasks or list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        degraded_notices = degraded_notices or []
        current_action = current_action or self._derive_current_action(db, project, degraded_notices)
        overview = overview or self._project_overview(db, project, tasks, current_action)
        preferences = project.swarm_preferences or self._swarm_preferences(project)
        budget = project.swarm_budget or self._preview_swarm_budget(db, project)
        contracts = list(project.agent_contracts or []) or self._preview_agent_contracts(db, project)
        path_locks = list(project.path_locks or []) or self._preview_path_locks(db, project)
        conflicts = self._preview_conflicts(db, project)
        confidence = list(project.project_confidence or []) or self._preview_project_confidence(project)
        persisted_stuck_signals = list(
            db.scalars(
                select(AgentStuckSignal)
                .where(AgentStuckSignal.project_id == project.id, AgentStuckSignal.resolved_at.is_(None))
                .order_by(AgentStuckSignal.detected_at.desc())
            )
        )
        stuck_signals: list[AgentStuckSignal] | list[dict[str, Any]] = persisted_stuck_signals or self._preview_stuck_signals(db, project)
        recovery_preview = self.preview_recovery_plans(db, project)
        recovery_plans = list(recovery_preview["persisted"])
        review_gates = list(project.review_gates or []) or self._preview_review_gates(
            db,
            project,
            tasks=tasks,
            overview=overview,
            testing_depth=preferences.testing_depth,
            conflicts=conflicts,
        )
        model_policy = next(iter(project.model_policies or []), None) or self._preview_model_policy(db, project)
        tool_routing = list(project.tool_routing_policies or []) or self._preview_tool_routing_policies(db, project)
        sandbox_profiles = self._preview_sandbox_profiles(db, project)
        assumptions = [
            {
                "assumption": entry.assumption,
                "reason": entry.reason,
                "confidence": entry.confidence,
                "status": entry.status,
                "created_at": entry.created_at,
                "source": "persisted",
            }
            for entry in list(
                db.scalars(
                    select(ManagerAssumption)
                    .where(ManagerAssumption.project_id == project.id)
                    .order_by(ManagerAssumption.created_at.desc(), ManagerAssumption.id.desc())
                )
            )
        ] or self._preview_manager_assumptions(db, project)
        persisted_repo = project.repo_intelligence
        persisted_has_signal = persisted_repo is not None and any(
            [
                persisted_repo.languages_json,
                persisted_repo.frameworks_json,
                persisted_repo.important_folders_json,
                persisted_repo.entry_points_json,
                persisted_repo.build_commands_json,
                persisted_repo.test_commands_json,
            ]
        )
        repo = (
            {
                "languages_json": list(persisted_repo.languages_json or []),
                "frameworks_json": list(persisted_repo.frameworks_json or []),
                "package_managers_json": list(persisted_repo.package_managers_json or []),
                "entry_points_json": list(persisted_repo.entry_points_json or []),
                "build_commands_json": list(persisted_repo.build_commands_json or []),
                "test_commands_json": list(persisted_repo.test_commands_json or []),
                "important_folders_json": list(persisted_repo.important_folders_json or []),
                "docs_found_json": list(persisted_repo.docs_found_json or []),
                "ci_config_json": list(persisted_repo.ci_config_json or []),
                "deployment_config_json": list(persisted_repo.deployment_config_json or []),
                "risky_files_json": list(persisted_repo.risky_files_json or []),
                "last_indexed_at": persisted_repo.last_indexed_at,
                "source": "persisted",
            }
            if persisted_has_signal
            else {**self._preview_repo_intelligence(project), "source": "computed"}
        )
        validation_recipe = next(iter(project.validation_recipes or []), None) or self._preview_validation_recipe(db, project)
        handoff_quality = project.handoff_quality_preference or HandoffQualityPreference(project_id=project.id)
        traces = [
            {
                "id": trace.id,
                "prompt_summary": trace.prompt_summary,
                "response_summary": trace.response_summary,
                "files_changed_json": list(trace.files_changed_json or []),
                "commands_attempted_json": list(trace.commands_attempted_json or []),
                "manager_decision_after": trace.manager_decision_after,
                "redaction_status": trace.redaction_status,
                "created_at": trace.created_at,
                "source": "persisted",
            }
            for trace in list(
                db.scalars(
                    select(AgentExecutionTrace)
                    .where(AgentExecutionTrace.project_id == project.id)
                    .order_by(AgentExecutionTrace.created_at.desc(), AgentExecutionTrace.id.desc())
                )
            )
        ] or self._preview_agent_execution_traces(db, project)
        snapshots = self.list_snapshots(db, project)
        agent_load = [
            {
                "agent_id": snapshot.agent_id,
                "load_level": snapshot.load_level,
                "active_task_count": snapshot.active_task_count,
                "blocked_task_count": snapshot.blocked_task_count,
                "idle_duration_seconds": snapshot.idle_duration_seconds,
                "created_at": snapshot.created_at,
                "source": "persisted",
            }
            for snapshot in list(
                db.scalars(
                    select(AgentLoadSnapshot)
                    .where(AgentLoadSnapshot.project_id == project.id)
                    .order_by(AgentLoadSnapshot.created_at.desc(), AgentLoadSnapshot.id.desc())
                )
            )
        ] or self._preview_agent_load_snapshots(db, project)
        timeline = self.list_timeline_events(db, project)
        evidence = self.list_handoff_evidence(db, project)
        latest_handoff = self._latest_evidence_handoff(db, project.id)
        runbook = self.get_runbook(db, project)
        decisions = list(project.decision_records or []) or self._preview_decision_records(db, project)
        blocked_agents = [agent for agent in self._sorted_workspace_agents(db, project.id) if agent["display_status"] in {"blocked", "error"}]
        pending_approvals = self.list_pending_approvals(db, project)
        health = self._project_health(
            project,
            current_action=current_action,
            overview=overview,
            stuck_signals=stuck_signals,
            review_gates=review_gates,
            pending_approvals=pending_approvals,
            blocked_agents=blocked_agents,
            conflicts=conflicts,
            evidence=evidence,
        )
        return {
            "budget": budget,
            "contracts": contracts,
            "path_locks": path_locks,
            "conflicts": conflicts,
            "confidence": confidence,
            "stuck_signals": stuck_signals,
            "recovery_plans": recovery_plans,
            "review_gates": review_gates,
            "model_policy": model_policy,
            "tool_routing": tool_routing,
            "sandbox_profiles": sandbox_profiles,
            "assumptions": assumptions,
            "repo": repo,
            "validation_recipe": validation_recipe,
            "handoff_quality": handoff_quality,
            "handoff_evidence": evidence,
            "latest_handoff": latest_handoff,
            "runbook": runbook,
            "agent_traces": traces,
            "snapshots": snapshots,
            "agent_load": agent_load,
            "timeline": timeline,
            "decisions": decisions,
            "health": health,
            "blocked_agents": blocked_agents,
            "pending_approvals": pending_approvals,
        }

    def list_widget_catalog(self, db: Session, scope: str | None = None) -> list[dict[str, Any]]:
        catalog = self._widget_definitions_view(db)
        return [
            self._serialize_widget_definition(definition)
            for definition in catalog
            if scope is None or definition.scope == scope
        ]

    def list_dashboard_widget_instances(self, db: Session) -> list[dict[str, Any]]:
        profile = self._app_profile(db)
        return [
            self._serialize_widget_instance(item)
            for item in self._dashboard_widget_instances(db, profile, create_if_missing=False)
        ]

    def list_project_widget_instances(self, db: Session, project: Project) -> list[dict[str, Any]]:
        settings = self._project_settings(db, project)
        return [
            self._serialize_widget_instance(item)
            for item in self._project_widget_instances(db, project, settings, create_if_missing=False)
        ]

    def _widget_instance_or_error(self, db: Session, instance_id: int, *, project: Project | None = None) -> WidgetInstance:
        instance = db.get(WidgetInstance, instance_id)
        if instance is None:
            raise ValueError("Widget instance not found")
        if instance.scope == "project":
            if project is None:
                raise ValueError("Project widget operations require project_id")
            if instance.project_id != project.id:
                raise ValueError("Widget instance not found in this project")
        elif project is not None:
            raise ValueError("Dashboard widgets do not accept project_id")
        return instance

    def _widget_definition_or_error(self, db: Session, widget_type: str) -> WidgetDefinition:
        definition = next((item for item in self._widget_definitions_view(db) if item.widget_type == widget_type), None)
        if definition is None:
            raise ValueError("Unknown widget type")
        return definition

    def _validate_widget_area_for_scope(self, scope: str, area: str | None) -> str | None:
        if area is None:
            return None
        normalized = str(area)
        allowed = WIDGET_AREAS_BY_SCOPE.get(scope, set())
        if normalized not in allowed:
            raise ValueError(f"Widget area {normalized!r} is not valid for {scope} widgets.")
        return normalized

    def _publish_widget_instance_change(self, db: Session, *, project_id: int | None, event_type: str, payload: dict[str, Any]) -> None:
        if project_id is None:
            self.events.publish_app(db, event_type, payload)
            return
        self.events.publish(db, project_id, event_type, payload)

    def create_widget_instance(
        self,
        db: Session,
        *,
        scope: str,
        project: Project | None,
        widget_type: str,
        area: str | None = None,
        size: str | None = None,
        order_index: int | None = None,
        collapsed: bool = False,
        enabled: bool = True,
        config_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        definition = self._widget_definition_or_error(db, widget_type)
        if definition.scope != scope:
            raise ValueError("Widget scope does not match the requested placement.")
        if scope == "dashboard" and project is not None:
            raise ValueError("Dashboard widgets do not accept project_id.")
        if scope == "project" and project is None:
            raise ValueError("Project widgets require a project context.")
        project_id = project.id if project is not None else None
        target_area = self._validate_widget_area_for_scope(scope, area) or definition.default_area
        existing = db.scalar(
            select(WidgetInstance).where(
                WidgetInstance.scope == scope,
                WidgetInstance.project_id == project_id,
                WidgetInstance.widget_type == widget_type,
            )
        )
        if existing is not None:
            if not existing.enabled:
                existing.enabled = True
                existing.area = target_area
                existing.size = size or definition.default_size
                existing.collapsed = collapsed
                existing.config_json = dict(config_json or {})
                if order_index is not None:
                    existing.order_index = int(order_index)
                existing.updated_at = utc_now()
                db.flush()
                self._normalize_widget_order(db, scope=scope, project_id=project_id)
                if scope == "dashboard":
                    self._mirror_dashboard_widget_legacy(self._app_profile(db), self._widget_instances_query(db, scope="dashboard", project_id=None))
                elif project is not None:
                    self._mirror_project_widget_legacy(self._ensure_project_settings(db, project), self._widget_instances_query(db, scope="project", project_id=project.id))
                self._publish_widget_instance_change(
                    db,
                    project_id=project_id,
                    event_type="widget_instances_updated",
                    payload={"scope": scope, "project_id": project_id, "widget_instance_id": existing.id, "widget_type": widget_type, "action": "enabled"},
                )
            return self._serialize_widget_instance(existing)
        if order_index is None:
            siblings = [item for item in self._widget_instances_query(db, scope=scope, project_id=project_id) if item.area == target_area]
            order_index = len(siblings)
        instance = WidgetInstance(
            scope=scope,
            project_id=project_id,
            widget_type=widget_type,
            area=target_area,
            order_index=order_index,
            size=size or definition.default_size,
            collapsed=collapsed,
            enabled=enabled,
            config_json=dict(config_json or {}),
        )
        db.add(instance)
        db.flush()
        self._normalize_widget_order(db, scope=scope, project_id=project_id)
        if scope == "dashboard":
            self._mirror_dashboard_widget_legacy(self._app_profile(db), self._widget_instances_query(db, scope="dashboard", project_id=None))
        elif project is not None:
            self._mirror_project_widget_legacy(self._ensure_project_settings(db, project), self._widget_instances_query(db, scope="project", project_id=project.id))
        self._publish_widget_instance_change(
            db,
            project_id=project_id,
            event_type="widget_instances_updated",
            payload={"scope": scope, "project_id": project_id, "widget_instance_id": instance.id, "widget_type": widget_type, "action": "created"},
        )
        return self._serialize_widget_instance(instance)

    def update_widget_instance(
        self,
        db: Session,
        instance_id: int,
        payload: dict[str, Any],
        *,
        project: Project | None = None,
    ) -> dict[str, Any]:
        instance = self._widget_instance_or_error(db, instance_id, project=project)
        original_area = instance.area
        if payload.get("area"):
            instance.area = self._validate_widget_area_for_scope(instance.scope, payload["area"]) or instance.area
        if payload.get("size"):
            instance.size = str(payload["size"])
        if "order_index" in payload and payload["order_index"] is not None:
            instance.order_index = int(payload["order_index"])
        if "collapsed" in payload and payload["collapsed"] is not None:
            instance.collapsed = bool(payload["collapsed"])
        if "enabled" in payload and payload["enabled"] is not None:
            instance.enabled = bool(payload["enabled"])
        if payload.get("config_json") is not None:
            instance.config_json = dict(payload["config_json"] or {})
        db.flush()
        self._normalize_widget_order(db, scope=instance.scope, project_id=instance.project_id)
        if instance.scope == "dashboard":
            self._mirror_dashboard_widget_legacy(self._app_profile(db), self._widget_instances_query(db, scope="dashboard", project_id=None))
        elif instance.project_id is not None:
            project = db.get(Project, instance.project_id)
            if project is not None:
                self._mirror_project_widget_legacy(self._ensure_project_settings(db, project), self._widget_instances_query(db, scope="project", project_id=project.id))
        self._publish_widget_instance_change(
            db,
            project_id=instance.project_id,
            event_type="widget_instances_updated",
            payload={
                "scope": instance.scope,
                "project_id": instance.project_id,
                "widget_instance_id": instance.id,
                "widget_type": instance.widget_type,
                "action": "updated",
                "area_changed": original_area != instance.area,
            },
        )
        return self._serialize_widget_instance(instance)

    def delete_widget_instance(self, db: Session, instance_id: int, *, project: Project | None = None) -> None:
        instance = self._widget_instance_or_error(db, instance_id, project=project)
        scope = instance.scope
        project_id = instance.project_id
        widget_type = instance.widget_type
        db.delete(instance)
        db.flush()
        self._normalize_widget_order(db, scope=scope, project_id=project_id)
        if scope == "dashboard":
            self._mirror_dashboard_widget_legacy(self._app_profile(db), self._widget_instances_query(db, scope="dashboard", project_id=None))
        elif project_id is not None:
            project = db.get(Project, project_id)
            if project is not None:
                self._mirror_project_widget_legacy(self._ensure_project_settings(db, project), self._widget_instances_query(db, scope="project", project_id=project_id))
        self._publish_widget_instance_change(
            db,
            project_id=project_id,
            event_type="widget_instances_updated",
            payload={"scope": scope, "project_id": project_id, "widget_type": widget_type, "action": "deleted"},
        )

    def add_dashboard_widget(self, db: Session, widget_type: str, area: str | None = None, size: str | None = None) -> dict[str, Any]:
        return self.create_widget_instance(db, scope="dashboard", project=None, widget_type=widget_type, area=area, size=size)

    def add_project_widget(self, db: Session, project: Project, widget_type: str, area: str | None = None, size: str | None = None) -> dict[str, Any]:
        return self.create_widget_instance(db, scope="project", project=project, widget_type=widget_type, area=area, size=size)

    async def _dashboard_widget_data_for_instance(
        self,
        db: Session,
        instance: WidgetInstance,
        *,
        projects: list[Project],
        profile: AppProfile,
        system_status: dict[str, Any],
        active_builds: list[dict[str, Any]],
        attention_items: list[dict[str, Any]],
        blocked_agents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        recent_handoffs = self.list_handoffs(db)[:5]
        if instance.widget_type == "Needs Attention":
            if not attention_items:
                return self._serialize_widget_data(instance, status="empty", empty_state="No attention needed. Everything is moving.")
            return self._serialize_widget_data(instance, status="warning", data_json={"items": attention_items[:6]})
        if instance.widget_type == "Active Builds":
            if not active_builds:
                return self._serialize_widget_data(instance, status="empty", empty_state="No active builds. Start a project or resume one from Recent Projects.")
            return self._serialize_widget_data(instance, status="ready", data_json={"items": active_builds[:6]})
        if instance.widget_type == "Recent Handoffs":
            if not recent_handoffs:
                return self._serialize_widget_data(instance, status="empty", empty_state="No handoffs yet. Completed work will appear here.")
            return self._serialize_widget_data(
                instance,
                status="warning" if any(item.get("missing_evidence") for item in recent_handoffs[:5]) else "ready",
                data_json={"items": recent_handoffs[:5]},
            )
        if instance.widget_type == "Runner & Provider Status":
            provider_rows = [
                {
                    "label": row["label"],
                    "provider": row["provider"],
                    "status": row["login_status"],
                    "models": list(row.get("available_models") or []),
                    "authenticated": bool(row.get("authenticated")),
                }
                for row in system_status.get("provider_statuses", [])
            ]
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "selected_provider": system_status.get("selected_provider_label"),
                    "effective_runner_mode": system_status.get("effective_runner_mode"),
                    "cli_detected": system_status.get("cli_detected"),
                    "app_server_handshake_status": system_status.get("app_server_handshake_status"),
                    "providers": provider_rows,
                },
            )
        if instance.widget_type == "Connected Accounts":
            rows = [{"name": key, **dict(value or {})} for key, value in dict(profile.connected_accounts_json or {}).items()]
            if system_status.get("authenticated"):
                rows.insert(0, {"name": "codex", "status": "connected"})
            if not rows:
                return self._serialize_widget_data(instance, status="empty", empty_state="No connected accounts are configured yet.")
            return self._serialize_widget_data(instance, status="ready", data_json={"items": rows})
        if instance.widget_type == "Model Defaults":
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "manager_model": profile.manager_model,
                    "default_worker_model": profile.default_worker_model,
                    "manager_reasoning_effort": profile.manager_reasoning_effort,
                    "default_worker_reasoning_effort": profile.default_worker_reasoning_effort,
                },
            )
        if instance.widget_type == "Diagnostics Summary":
            startup_summary = dict(system_status.get("startup_summary") or {})
            notes = list(system_status.get("notes") or [])
            return self._serialize_widget_data(
                instance,
                status="warning" if startup_summary.get("overall_status") in {"degraded", "error"} else "ready",
                data_json={
                    "startup_summary": startup_summary,
                    "notes": notes[:5],
                    "runtime_directory": system_status.get("runtime_directory"),
                },
            )
        if instance.widget_type == "Swarm Budget Overview":
            items = []
            warnings: list[str] = []
            for project in projects[:8]:
                support = self._preview_widget_support_records(db, project)
                budget = support["budget"]
                items.append(
                    {
                        "project_id": project.id,
                        "project_name": project.name,
                        "project_slug": self._effective_project_slug(project),
                        "active_agents": budget.current_active_agents,
                        "max_agents": budget.max_agents,
                        "intensity": budget.current_intensity,
                        "dynamic_spawning_paused": budget.dynamic_spawning_paused,
                        "approval_threshold": budget.require_approval_above_agent_count,
                    }
                )
                if budget.current_intensity in {"high", "extreme"}:
                    warnings.append(f"{project.name} is running at {budget.current_intensity} swarm intensity.")
            if not items:
                return self._serialize_widget_data(instance, status="empty", empty_state="No active swarm budgets exist yet.")
            return self._serialize_widget_data(instance, status="warning" if warnings else "ready", data_json={"items": items}, warnings_json=warnings[:5])
        if instance.widget_type == "Model Capability Overview":
            summary = capability_service.benchmark_summary(db)
            if not summary["has_data"]:
                return self._serialize_widget_data(instance, status="empty", empty_state="No benchmark data yet. Manager will use default policy.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "items": [
                        {
                            "title": category.replace("_", " "),
                            "detail": f"{entry['provider']} / {entry['model']} • score {entry['score']}",
                        }
                        for category, entry in summary["top_categories"].items()
                    ],
                    "matrix": summary["matrix"],
                },
            )
        if instance.widget_type == "Global Agent Reputation":
            reputation = reputation_service.summarize(db)
            if not reputation:
                return self._serialize_widget_data(instance, status="empty", empty_state="Not enough history yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "items": [
                        {
                            "title": f"{item['archetype']} ({item['model'] or item['provider'] or 'default'})",
                            "detail": f"success {int(item['success_rate'] * 100)}% • confidence {item['confidence']}",
                        }
                        for item in reputation[:8]
                    ]
                },
            )
        if instance.widget_type == "Common Risks":
            items = risk_service.common_risks(db)
            if not items:
                return self._serialize_widget_data(instance, status="empty", empty_state="No common risks are active right now.")
            return self._serialize_widget_data(instance, status="warning", data_json={"items": items})
        if instance.widget_type == "Recent Scope Changes":
            signals = scope_creep_service.recent_signals(db, limit=10)
            if not signals:
                return self._serialize_widget_data(instance, status="empty", empty_state="No scope changes have been recorded yet.")
            return self._serialize_widget_data(
                instance,
                status="warning" if any(item.severity == "high" and item.status == "open" for item in signals) else "ready",
                data_json={
                    "items": [
                        {
                            "title": item.summary,
                            "detail": f"{item.severity} • {item.suggested_action} • {item.status}",
                        }
                        for item in signals
                    ]
                },
            )
        if instance.widget_type == "Preference Summary":
            preferences = preference_service.get_effective_preferences(db, project=None)
            if not preferences:
                return self._serialize_widget_data(instance, status="empty", empty_state="No global preferences are stored yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "items": [
                        {
                            "title": item.key,
                            "detail": f"{item.value_json} • {item.source}",
                        }
                        for item in preferences[:8]
                    ]
                },
            )
        if instance.widget_type == "Blocked Agents":
            if not blocked_agents:
                return self._serialize_widget_data(instance, status="empty", empty_state="No agents are currently blocked.")
            return self._serialize_widget_data(instance, status="warning", data_json={"items": blocked_agents[:8]})
        if instance.widget_type == "Recent Decisions":
            decisions = list(
                db.scalars(
                    select(DecisionRecord)
                    .order_by(DecisionRecord.created_at.desc(), DecisionRecord.id.desc())
                )
            )[:10]
            if not decisions:
                return self._serialize_widget_data(instance, status="empty", empty_state="No decisions have been recorded yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={"items": [
                    {
                        "project_id": item.project_id,
                        "title": item.title,
                        "decision": item.decision,
                        "reason": item.reason,
                        "made_by": item.made_by,
                        "created_at": item.created_at,
                    }
                    for item in decisions
                ]},
            )
        if instance.widget_type == "Project Health Overview":
            items = []
            for project in projects[:8]:
                tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
                settings = self._project_settings_preview(db, project)
                degraded = await self._workspace_degraded_notices(project, settings)
                current_action = self._derive_current_action(db, project, degraded)
                overview = self._project_overview(db, project, tasks, current_action)
                support = self._preview_widget_support_records(
                    db,
                    project,
                    tasks=tasks,
                    degraded_notices=degraded,
                    current_action=current_action,
                    overview=overview,
                )
                items.append(
                    {
                        "project_id": project.id,
                        "project_name": project.name,
                        "project_slug": self._effective_project_slug(project),
                        **support["health"],
                    }
                )
            if not items:
                return self._serialize_widget_data(instance, status="empty", empty_state="No project health data exists yet.")
            return self._serialize_widget_data(instance, status="ready", data_json={"items": items})
        if instance.widget_type == "Recent Change Requests":
            items = list(
                db.scalars(
                    select(ChangeRequest).order_by(ChangeRequest.updated_at.desc(), ChangeRequest.id.desc())
                )
            )[:10]
            if not items:
                return self._serialize_widget_data(instance, status="empty", empty_state="No change requests have been logged yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={"items": [
                    {
                        "project_id": item.project_id,
                        "request_text": item.request_text,
                        "classification": item.classification,
                        "impact_estimate": item.impact_estimate,
                        "status": item.status,
                        "updated_at": item.updated_at,
                    }
                    for item in items
                ]},
            )
        if instance.widget_type == "Active Conflicts":
            items = []
            for project in projects[:10]:
                for conflict in self.list_conflicts(db, project):
                    if conflict.status in {"resolved", "dismissed"}:
                        continue
                    items.append(
                        {
                            "project_id": project.id,
                            "project_name": project.name,
                            "title": conflict.title,
                            "detail": conflict.summary,
                            "severity": conflict.severity,
                            "status": conflict.status,
                        }
                    )
            if not items:
                return self._serialize_widget_data(instance, status="empty", empty_state="No active cross-project conflicts are recorded.")
            return self._serialize_widget_data(instance, status="warning", data_json={"items": items[:10]})
        if instance.widget_type == "Recovery Needed":
            items = []
            for project in projects[:10]:
                for plan in self.list_recovery_plans(db, project):
                    if plan.status in {"completed", "rejected"} or plan.resolved_at is not None:
                        continue
                    items.append(
                        {
                            "project_id": project.id,
                            "project_name": project.name,
                            "title": plan.trigger_summary,
                            "detail": f"{plan.trigger_type} · {plan.status}",
                        }
                    )
            if not items:
                return self._serialize_widget_data(instance, status="empty", empty_state="No active recovery plans are waiting right now.")
            return self._serialize_widget_data(instance, status="warning", data_json={"items": items[:10]})
        if instance.widget_type == "Imported Projects":
            imported = [
                {
                    "project_id": item.id,
                    "project_name": item.name,
                    "project_slug": self._effective_project_slug(item),
                    "source_path": item.source_path or item.workspace_path,
                    "scan_status": item.scan_status,
                    "write_permission_status": item.write_permission_status,
                    "codebase_size": (item.codebase_map.codebase_size if item.codebase_map else "unknown"),
                }
                for item in projects
                if item.source_type in {"existing_folder", "cloned_repo", "docs_import"}
            ][:10]
            if not imported:
                return self._serialize_widget_data(instance, status="empty", empty_state="No imported projects exist yet.")
            return self._serialize_widget_data(instance, status="ready", data_json={"items": imported})
        return self._serialize_widget_data(instance, status="empty", empty_state=WIDGET_EMPTY_STATE)

    async def _project_widget_data_for_instance(
        self,
        db: Session,
        instance: WidgetInstance,
        *,
        project: Project,
        tasks: list[Task],
        current_action: dict[str, Any],
        overview: dict[str, Any],
        degraded_notices: list[str],
        preview_support: bool = False,
    ) -> dict[str, Any]:
        support_records: dict[str, Any] | None = None

        def get_support() -> dict[str, Any]:
            nonlocal support_records
            if support_records is None:
                if preview_support:
                    support_records = self._preview_widget_support_records(
                        db,
                        project,
                        tasks=tasks,
                        degraded_notices=degraded_notices,
                        current_action=current_action,
                        overview=overview,
                    )
                else:
                    support_records = self._ensure_widget_support_records(
                        db,
                        project,
                        tasks=tasks,
                        degraded_notices=degraded_notices,
                        current_action=current_action,
                        overview=overview,
                    )
            return support_records

        swarm_plan = self._serialize_swarm_plan(db, project, self._current_swarm_plan_record(db, project.id))
        if instance.widget_type == "Swarm Strategy":
            if swarm_plan is None:
                return self._serialize_widget_data(instance, status="empty", empty_state="No swarm plan exists yet. Ask the Manager to generate one.")
            warnings = [swarm_plan["usage_warning"]] if swarm_plan.get("usage_warning") else []
            return self._serialize_widget_data(instance, status="warning" if warnings else "ready", data_json=swarm_plan, warnings_json=warnings)
        if instance.widget_type == "Model Capability Matrix":
            matrix = capability_service.capability_matrix(db)
            if not matrix:
                return self._serialize_widget_data(instance, status="empty", empty_state="No benchmark data yet. Manager will use default policy.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "categories": CAPABILITY_CATEGORIES,
                    "rows": matrix,
                    "recommendation_note": "No benchmark data yet. Manager will use default policy." if not matrix else "",
                },
            )
        if instance.widget_type == "Agent Reputation":
            reputation = reputation_service.summarize(db, project)
            if not reputation:
                return self._serialize_widget_data(instance, status="empty", empty_state="Not enough history yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "items": [
                        {
                            "title": f"{item['archetype']} ({item['model'] or item['provider'] or 'default'})",
                            "detail": f"success {int(item['success_rate'] * 100)}% • best: {', '.join(item['recommended_for']) or 'unknown'}",
                            "weak_spots": item["avoid_for"],
                        }
                        for item in reputation[:8]
                    ]
                },
            )
        if instance.widget_type == "Project Playbook":
            state = playbook_service.project_playbook_state(db, project)
            playbook = state.get("playbook")
            if playbook is None:
                return self._serialize_widget_data(instance, status="empty", empty_state="No playbook is selected yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "playbook_key": state.get("playbook_key"),
                    "playbook_name": playbook.name,
                    "status": state.get("status"),
                    "why": state.get("why"),
                    "common_risks": list(playbook.common_risks_json or []),
                    "validation": list(playbook.suggested_validation_recipe_json or []),
                },
            )
        if instance.widget_type == "Context Packs":
            packs = context_pack_service.list_context_packs(db, project)[:8]
            if not packs:
                return self._serialize_widget_data(instance, status="empty", empty_state="No context packs have been built yet.")
            return self._serialize_widget_data(
                instance,
                status="warning" if any(item["warnings_json"] for item in packs) else "ready",
                data_json={
                    "items": [
                        {
                            "title": item["title"],
                            "detail": f"files {len(item['included_files_json'])} • docs {len(item['included_docs_json'])} • warnings {len(item['warnings_json'])}",
                            "task_id": item["task_id"],
                            "agent_id": item["agent_id"],
                        }
                        for item in packs
                    ]
                },
            )
        if instance.widget_type == "Risk Register":
            risks = risk_service.list_risks(db, project)
            if not risks:
                return self._serialize_widget_data(instance, status="empty", empty_state="No risks are recorded yet.")
            return self._serialize_widget_data(
                instance,
                status="warning" if any(item.severity in {"high", "critical"} and item.status in {"open", "monitoring"} for item in risks) else "ready",
                data_json={
                    "items": [
                        {
                            "title": item.title,
                            "detail": f"{item.severity}/{item.likelihood} • {item.status} • mitigation: {item.mitigation or 'none'}",
                            "owner": item.owner_agent_id,
                        }
                        for item in risks[:10]
                    ]
                },
            )
        if instance.widget_type == "Security Policy":
            policy = security_service.get_policy(db, project=project, create_if_missing=False)
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "rows": [
                        {"label": "Command policy", "value": policy.default_command_policy},
                        {"label": "Tool policy", "value": policy.default_tool_policy},
                        {"label": "Network", "value": policy.network_access_policy},
                        {"label": "Writes", "value": policy.write_access_policy},
                        {"label": "External accounts", "value": policy.external_account_policy},
                        {"label": "Deployment", "value": policy.deployment_policy},
                        {"label": "Destructive actions", "value": policy.destructive_action_policy},
                    ],
                    "notes": [
                        "High-risk actions require explicit user approval."
                        if policy.high_risk_requires_user
                        else "High-risk actions are not manually gated. Review this policy carefully."
                    ],
                },
            )
        if instance.widget_type == "Approval Audit Log":
            logs = security_service.list_audit_logs(db, project=project)[:10]
            if not logs:
                return self._serialize_widget_data(instance, status="empty", empty_state="No approval audit entries exist yet.")
            return self._serialize_widget_data(
                instance,
                status="warning" if any(item.decision == "blocked" for item in logs) else "ready",
                data_json={
                    "items": [
                        {
                            "title": item.action_summary,
                            "detail": f"{item.decision} - {item.risk_level} - {item.decided_by}",
                        }
                        for item in logs
                    ]
                },
            )
        if instance.widget_type == "Risk Assessment":
            assessments = security_service.recent_risk_assessments(db, project=project)[:10]
            if not assessments:
                return self._serialize_widget_data(instance, status="empty", empty_state="No risk assessments have been recorded yet.")
            return self._serialize_widget_data(
                instance,
                status="warning" if any(item.risk_level in {"high", "critical"} for item in assessments) else "ready",
                data_json={
                    "items": [
                        {
                            "title": item.title,
                            "detail": f"{item.risk_level} - {item.recommended_policy}",
                        }
                        for item in assessments
                    ]
                },
            )
        if instance.widget_type == "Scope Creep":
            signals = [item for item in scope_creep_service.list_signals(db, project) if item.status == "open"]
            if not signals:
                return self._serialize_widget_data(instance, status="empty", empty_state="No open scope changes exist right now.")
            return self._serialize_widget_data(
                instance,
                status="warning" if any(item.severity == "high" for item in signals) else "ready",
                data_json={
                    "items": [
                        {
                            "title": item.summary,
                            "detail": f"{item.severity} • {item.suggested_action} • {item.status}",
                        }
                        for item in signals[:10]
                    ]
                },
            )
        if instance.widget_type == "Agent Launch Simulation":
            simulation = simulation_service.latest_simulation(db, project)
            if simulation is None:
                return self._serialize_widget_data(instance, status="empty", empty_state="No launch simulation exists yet. Generate or revise a swarm plan first.")
            return self._serialize_widget_data(
                instance,
                status="warning" if simulation.should_wait_count or simulation.conflict_warnings_json else "ready",
                data_json={
                    "safe_to_launch_count": simulation.safe_to_launch_count,
                    "should_wait_count": simulation.should_wait_count,
                    "needs_user_approval_count": simulation.needs_user_approval_count,
                    "conflicts": list(simulation.conflict_warnings_json or []),
                    "bottlenecks": list(simulation.bottlenecks_json or []),
                    "recommended_launch_order": list(simulation.recommended_launch_order_json or []),
                },
            )
        if instance.widget_type == "Validation Coverage":
            coverage = validation_coverage_service.coverage_summary(db, project)
            items = coverage["items"]
            if not items:
                return self._serialize_widget_data(instance, status="empty", empty_state="No validation coverage exists yet.")
            return self._serialize_widget_data(
                instance,
                status="warning" if coverage["gaps"] else "ready",
                data_json={
                    "items": [
                        {
                            "title": item["area"] if isinstance(item, dict) else item.area,
                            "detail": (
                                f"{item['coverage_status']} • {item.get('evidence_summary') or 'No evidence recorded yet.'}"
                                if isinstance(item, dict)
                                else f"{item.coverage_status} • {item.evidence_summary or 'No evidence recorded yet.'}"
                            ),
                        }
                        for item in items
                    ],
                    "gaps": coverage["gaps"],
                },
            )
        if instance.widget_type == "Preference Memory":
            preferences = preference_service.get_effective_preferences(db, project)
            if not preferences:
                return self._serialize_widget_data(instance, status="empty", empty_state="No active preferences affect this project yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "items": [
                        {
                            "title": item.key,
                            "detail": f"{item.value_json} • {item.source} • {item.scope}",
                        }
                        for item in preferences[:10]
                    ]
                },
            )
        if instance.widget_type == "Swarm Budget":
            budget = project.swarm_budget or self._preview_swarm_budget(db, project)
            warnings = []
            if budget.current_intensity in {"high", "extreme"}:
                warnings.append(f"Swarm intensity is {budget.current_intensity}. More agents are not free speed; they are coordination debt in nicer clothing.")
            if budget.premium_models_only_for:
                warnings.append(f"Premium model roles configured: {', '.join(budget.premium_models_only_for)}")
            return self._serialize_widget_data(
                instance,
                status="warning" if warnings else "ready",
                data_json={
                    "active_agents": budget.current_active_agents,
                    "max_agents": budget.max_agents,
                    "approval_threshold": budget.require_approval_above_agent_count,
                    "intensity": budget.current_intensity,
                    "dynamic_spawning_paused": budget.dynamic_spawning_paused,
                    "prefer_local_models": budget.prefer_local_models,
                    "premium_models_only_for": list(budget.premium_models_only_for or []),
                },
                warnings_json=warnings,
            )
        if instance.widget_type == "Parallelism Safety Meter":
            path_locks = self._preview_path_locks(db, project)
            active_locks = [entry for entry in path_locks if entry.status == "active"]
            waiting_locks = [entry for entry in path_locks if entry.status == "waiting"]
            risk = swarm_plan["path_conflict_risk"] if swarm_plan else "low"
            score = max(0, 100 - (len(waiting_locks) * 15) - (30 if risk == "high" else 15 if risk == "medium" else 0))
            return self._serialize_widget_data(
                instance,
                status="warning" if waiting_locks or risk == "high" else "ready",
                data_json={
                    "score": score,
                    "active_locks": len(active_locks),
                    "waiting_locks": len(waiting_locks),
                    "path_conflict_risk": risk,
                    "coordination_risk": swarm_plan["coordination_risk"] if swarm_plan else "low",
                },
            )
        if instance.widget_type == "Conflict Resolver":
            support = get_support()
            conflicts: list[ConflictRecord] = [entry for entry in support["conflicts"] if entry.status not in {"resolved", "dismissed"}]
            if not conflicts:
                return self._serialize_widget_data(instance, status="empty", empty_state="No active conflicts are recorded right now.")
            return self._serialize_widget_data(
                instance,
                status="warning",
                data_json={
                    "items": [
                        {
                            "id": entry.id,
                            "title": entry.title,
                            "detail": entry.summary,
                            "severity": entry.severity,
                            "status": entry.status,
                            "affected_paths": list(entry.affected_paths_json or []),
                            "involved_agents": list(entry.involved_agent_ids_json or []),
                            "suggested_resolution": list(entry.suggested_resolution_json or []),
                        }
                        for entry in conflicts[:10]
                    ]
                },
            )
        if instance.widget_type == "Evidence Handoff":
            support = get_support()
            latest_handoff: EvidenceBasedHandoff | None = support["latest_handoff"]
            evidence: list[HandoffEvidence] = support["handoff_evidence"]
            if latest_handoff is None and not evidence:
                return self._serialize_widget_data(instance, status="empty", empty_state="No evidence-backed handoff exists yet.")
            missing_evidence = list((project.final_report_json or {}).get("missing_evidence") or [])
            return self._serialize_widget_data(
                instance,
                status="warning" if missing_evidence else "ready",
                data_json={
                    "title": latest_handoff.title if latest_handoff else f"{project.name} handoff",
                    "summary": latest_handoff.summary if latest_handoff else "Evidence exists but no handoff summary has been generated yet.",
                    "confidence_level": latest_handoff.confidence_level if latest_handoff else "low",
                    "dry_run": latest_handoff.dry_run if latest_handoff else project.runner_mode == "dry_run",
                    "evidence_count": len(evidence),
                    "missing_evidence": missing_evidence,
                    "claims": [
                        {"claim": item.claim, "summary": item.summary, "status": item.status}
                        for item in evidence[:8]
                    ],
                },
                warnings_json=missing_evidence,
            )
        if instance.widget_type == "Runbook":
            support = get_support()
            runbook: Runbook | None = support["runbook"]
            if runbook is None:
                return self._serialize_widget_data(instance, status="empty", empty_state="No runbook has been generated yet.")
            sections = [line[3:].strip() for line in runbook.content_markdown.splitlines() if line.startswith("## ")]
            expected_sections = [
                "How to start dev server",
                "How to run tests",
                "How to build",
                "How to debug common failures",
                "How to reset local state",
                "Where logs live",
                "How to deploy if configured",
                "Known operational risks",
            ]
            missing_sections = [section for section in expected_sections if section not in sections]
            return self._serialize_widget_data(
                instance,
                status="warning" if missing_sections else "ready",
                data_json={
                    "last_generated": runbook.generated_at,
                    "updated_at": runbook.updated_at,
                    "missing_sections": missing_sections,
                    "content_preview": runbook.content_markdown[:1200],
                    "run_commands": [line[2:] for line in runbook.content_markdown.splitlines() if line.startswith("- ")][:6],
                },
                warnings_json=[f"Missing section: {section}" for section in missing_sections[:4]],
            )
        if instance.widget_type == "Agent Black Box":
            traces = [
                {
                    "id": trace.id,
                    "title": trace.prompt_summary,
                    "detail": trace.response_summary,
                    "files_changed": list(trace.files_changed_json or []),
                    "commands_attempted": list(trace.commands_attempted_json or []),
                    "manager_decision_after": trace.manager_decision_after,
                    "redaction_status": trace.redaction_status,
                    "created_at": trace.created_at,
                    "source": "persisted",
                }
                for trace in list(
                    db.scalars(
                        select(AgentExecutionTrace)
                        .where(AgentExecutionTrace.project_id == project.id)
                        .order_by(AgentExecutionTrace.created_at.desc(), AgentExecutionTrace.id.desc())
                    )
                )
            ]
            if not traces:
                traces = [
                    {
                        "id": trace["id"],
                        "title": trace["prompt_summary"],
                        "detail": trace["response_summary"],
                        "files_changed": list(trace["files_changed_json"]),
                        "commands_attempted": list(trace["commands_attempted_json"]),
                        "manager_decision_after": trace["manager_decision_after"],
                        "redaction_status": trace["redaction_status"],
                        "created_at": trace["created_at"],
                        "source": trace["source"],
                    }
                    for trace in self._preview_agent_execution_traces(db, project)
                ]
            if not traces:
                return self._serialize_widget_data(instance, status="empty", empty_state="No agent execution traces have been recorded yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "items": traces[:10]
                },
            )
        if instance.widget_type == "Snapshots":
            support = get_support()
            snapshots: list[ProjectSnapshot] = support["snapshots"]
            if not snapshots:
                return self._serialize_widget_data(instance, status="empty", empty_state="No snapshots have been recorded for this project yet.")
            return self._serialize_widget_data(
                instance,
                status="warning" if any(entry.status != "available" for entry in snapshots[:6]) else "ready",
                data_json={
                    "items": [
                        {
                            "id": entry.id,
                            "title": entry.label,
                            "detail": entry.description,
                            "snapshot_type": entry.snapshot_type,
                            "status": entry.status,
                            "git_ref": entry.git_ref,
                        }
                        for entry in snapshots[:8]
                    ]
                },
            )
        if instance.widget_type == "Agent Load Balancer":
            load_snapshots = self._preview_agent_load_snapshots(db, project)
            if not load_snapshots:
                return self._serialize_widget_data(instance, status="empty", empty_state="No agent load snapshots exist yet.")
            rebalance = self._preview_agent_rebalance_plan(db, project)
            return self._serialize_widget_data(
                instance,
                status="warning" if rebalance["overloaded_agents"] else "ready",
                data_json={
                    "idle_agents": rebalance["idle_agents"],
                    "overloaded_agents": rebalance["overloaded_agents"],
                    "suggested_reassignments": rebalance["suggested_reassignments"],
                    "risks": rebalance["risks"],
                },
                warnings_json=list(rebalance["risks"][:3]),
            )
        if instance.widget_type == "Agent Contracts":
            contracts = list(project.agent_contracts or []) or self._preview_agent_contracts(db, project)
            if not contracts:
                return self._serialize_widget_data(instance, status="empty", empty_state="No active agent contracts exist yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "items": [
                        {
                            "id": entry.id,
                            "agent_name": entry.agent_name,
                            "archetype": entry.archetype,
                            "mission": entry.mission,
                            "allowed_paths": list(entry.allowed_paths_json or []),
                            "forbidden_paths": list(entry.forbidden_paths_json or []),
                            "allowed_tools": list(entry.allowed_tools_json or []),
                            "status": entry.status,
                            "expected_output": entry.expected_output,
                        }
                        for entry in contracts[:12]
                    ]
                },
            )
        if instance.widget_type == "Path Ownership Map":
            path_locks = list(project.path_locks or []) or self._preview_path_locks(db, project)
            if not path_locks:
                return self._serialize_widget_data(instance, status="empty", empty_state="No path ownership data exists yet.")
            waiting = [entry for entry in path_locks if entry.status == "waiting"]
            warnings = [f"{len(waiting)} task(s) are waiting on path ownership."] if waiting else []
            return self._serialize_widget_data(
                instance,
                status="warning" if warnings else "ready",
                data_json={
                    "locks": [
                        {
                            "path_pattern": entry.path_pattern,
                            "owner_agent_id": entry.owner_agent_id,
                            "owner_task_id": entry.owner_task_id,
                            "reason": entry.reason,
                            "status": entry.status,
                        }
                        for entry in path_locks[:20]
                    ]
                },
                warnings_json=warnings,
            )
        if instance.widget_type == "Decision Ledger":
            decisions = list(project.decision_records or []) or self._preview_decision_records(db, project)
            if not decisions:
                return self._serialize_widget_data(instance, status="empty", empty_state="No decisions have been recorded yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={"items": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "decision": item.decision,
                        "reason": item.reason,
                        "made_by": item.made_by,
                        "decision_type": item.decision_type,
                        "impact_areas": list(item.impact_area_json or []),
                        "created_at": item.created_at,
                    }
                    for item in decisions[:12]
                ]},
            )
        if instance.widget_type == "Confidence Tracker":
            confidence = list(project.project_confidence or []) or self._preview_project_confidence(project)
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "items": [
                        {
                            "category": entry.category,
                            "confidence_score": entry.confidence_score,
                            "reason": entry.reason,
                            "unknowns": list(entry.unknowns_json or []),
                        }
                        for entry in confidence
                    ],
                    "lowest_confidence": [entry.category for entry in confidence[:3]],
                },
            )
        if instance.widget_type == "Failure Recovery":
            preview = self.preview_recovery_plans(db, project)
            open_plans = [
                {
                    "id": entry.id,
                    "trigger_type": entry.trigger_type,
                    "trigger_summary": entry.trigger_summary,
                    "suggested_actions": list(entry.suggested_actions_json or []),
                    "selected_action": entry.selected_action,
                    "status": entry.status,
                    "source": "persisted",
                }
                for entry in preview["persisted"]
                if entry.resolved_at is None
            ]
            if not open_plans:
                open_plans = [
                    {
                        "id": None,
                        "trigger_type": entry["trigger_type"],
                        "trigger_summary": entry["trigger_summary"],
                        "suggested_actions": list(entry["suggested_actions_json"]),
                        "selected_action": None,
                        "status": entry["status"],
                        "source": entry["source"],
                    }
                    for entry in preview["derived_candidates"]
                ]
            if not open_plans:
                return self._serialize_widget_data(instance, status="empty", empty_state="No recovery proposals are active right now.")
            return self._serialize_widget_data(
                instance,
                status="warning",
                data_json={"items": open_plans[:8]},
            )
        if instance.widget_type == "Agent Stuck Detection":
            persisted_signals = list(
                db.scalars(
                    select(AgentStuckSignal)
                    .where(AgentStuckSignal.project_id == project.id, AgentStuckSignal.resolved_at.is_(None))
                    .order_by(AgentStuckSignal.detected_at.desc())
                )
            )
            signals = [
                {
                    "agent_id": entry.agent_id,
                    "signal_type": entry.signal_type,
                    "message": entry.message,
                    "severity": entry.severity,
                    "detected_at": entry.detected_at,
                    "source": "persisted",
                }
                for entry in persisted_signals
            ] or [
                {
                    "agent_id": entry["agent_id"],
                    "signal_type": entry["signal_type"],
                    "message": entry["message"],
                    "severity": entry["severity"],
                    "detected_at": entry["detected_at"],
                    "source": "computed",
                }
                for entry in self._preview_stuck_signals(db, project)
            ]
            if not signals:
                return self._serialize_widget_data(instance, status="empty", empty_state="No agents appear stuck right now.")
            return self._serialize_widget_data(
                instance,
                status="warning",
                data_json={"items": signals[:10]},
            )
        if instance.widget_type == "Merge / Review Gates":
            preferences = project.swarm_preferences or self._swarm_preferences(project)
            gates = list(project.review_gates or []) or self._preview_review_gates(
                db,
                project,
                tasks=tasks,
                overview=overview,
                testing_depth=preferences.testing_depth,
                conflicts=self.list_conflicts(db, project),
            )
            return self._serialize_widget_data(
                instance,
                status="warning" if any(entry.status == "failed" for entry in gates) else "ready",
                data_json={"items": [
                    {
                        "gate_type": entry.gate_type,
                        "title": entry.title,
                        "status": entry.status,
                        "required": entry.required,
                        "required_checks": list(entry.required_checks_json or []),
                        "result_summary": entry.result_summary,
                    }
                    for entry in gates
                ]},
            )
        if instance.widget_type == "Project Health Score":
            support = get_support()
            return self._serialize_widget_data(instance, status="warning" if support["health"]["state"] in {"blocked", "unstable", "needs_review"} else "ready", data_json=support["health"])
        if instance.widget_type == "Model Assignment Policy":
            policy = next(iter(project.model_policies or []), None) or self._preview_model_policy(db, project)
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "policy_name": policy.policy_name,
                    "manager_model": policy.manager_model,
                    "coding_model": policy.coding_model,
                    "docs_model": policy.docs_model,
                    "review_model": policy.review_model,
                    "test_model": policy.test_model,
                    "research_model": policy.research_model,
                    "security_model": policy.security_model,
                    "fallback_model": policy.fallback_model,
                    "notes": policy.notes,
                },
            )
        if instance.widget_type == "Tool Routing Policy":
            policies = list(project.tool_routing_policies or []) or self._preview_tool_routing_policies(db, project)
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={"items": [
                    {
                        "agent_archetype": entry.agent_archetype,
                        "allowed_tools": list(entry.allowed_tools_json or []),
                        "requires_approval": list(entry.requires_approval_tools_json or []),
                        "blocked_tools": list(entry.blocked_tools_json or []),
                        "notes": entry.notes,
                    }
                    for entry in policies
                ]},
            )
        if instance.widget_type == "Sandbox Profiles":
            profiles = self._preview_sandbox_profiles(db, project)
            settings = self._project_settings(db, project)
            current_profile_name = "balanced" if settings.sandbox_mode == "workspace-write" else "strict"
            current_profile = next((entry for entry in profiles if entry.name == current_profile_name), profiles[0] if profiles else None)
            if current_profile is None:
                return self._serialize_widget_data(instance, status="empty", empty_state="No sandbox profiles are available.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "current_profile": {
                        "name": current_profile.name,
                        "description": current_profile.description,
                        "network_policy": current_profile.network_policy,
                        "file_write_policy": current_profile.file_write_policy,
                        "command_approval_policy": current_profile.command_approval_policy,
                        "external_tool_policy": current_profile.external_tool_policy,
                        "deployment_policy": current_profile.deployment_policy,
                    },
                    "profiles": [
                        {
                            "name": entry.name,
                            "description": entry.description,
                            "network_policy": entry.network_policy,
                            "file_write_policy": entry.file_write_policy,
                            "command_approval_policy": entry.command_approval_policy,
                            "external_tool_policy": entry.external_tool_policy,
                            "deployment_policy": entry.deployment_policy,
                            "is_default": entry.is_default,
                        }
                        for entry in profiles
                    ],
                },
            )
        if instance.widget_type == "Codebase Map":
            record: CodebaseMap = import_service.get_codebase_map(db, project, create_if_missing=False)
            if not record.languages_json and not record.frameworks_json and not record.important_folders_json and project.source_type == "idea":
                return self._serialize_widget_data(instance, status="empty", empty_state="This project was started from an idea, so imported-codebase mapping is not active.")
            if not record.languages_json and not record.frameworks_json and not record.important_folders_json:
                return self._serialize_widget_data(instance, status="empty", empty_state="Codebase map is not available yet. Run the read-only scan first.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "source_path": record.source_path,
                    "languages": list(record.languages_json or []),
                    "frameworks": list(record.frameworks_json or []),
                    "package_managers": list(record.package_managers_json or []),
                    "build_tools": list(record.build_tools_json or []),
                    "test_frameworks": list(record.test_frameworks_json or []),
                    "important_folders": list(record.important_folders_json or []),
                    "docs": list(record.docs_json or []),
                    "build_commands": list(record.build_commands_json or []),
                    "test_commands": list(record.test_commands_json or []),
                    "git_status": dict(record.git_status_json or {}),
                    "risk_flags": list(record.risk_flags_json or []),
                },
            )
        if instance.widget_type == "Codebase Understanding":
            record: CodebaseUnderstanding = import_service.get_codebase_understanding(db, project, create_if_missing=False)
            if not record.summary:
                return self._serialize_widget_data(instance, status="empty", empty_state="Codebase understanding is not available yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "summary": record.summary,
                    "architecture_summary": record.architecture_summary,
                    "detected_stack": list(record.detected_stack_json or []),
                    "likely_run_instructions": list(record.likely_run_instructions_json or []),
                    "likely_test_instructions": list(record.likely_test_instructions_json or []),
                    "risk_summary": record.risk_summary,
                    "missing_context": list(record.missing_context_json or []),
                    "suggested_next_steps": list(record.suggested_next_steps_json or []),
                    "recommended_interview_mode": record.recommended_interview_mode,
                    "generation_mode": record.generation_mode,
                    "confidence_by_area": dict(record.confidence_by_area_json or {}),
                },
            )
        if instance.widget_type == "Imported Codebase Safety":
            safety = import_service.ensure_safety(db, project, create_if_missing=False) or ImportedCodebaseSafety(
                project_id=project.id,
                read_only_scan_completed=False,
                write_permission_status=project.write_permission_status or "read_only",
                require_snapshot_before_edits=True,
                require_approval_for_dependency_changes=True,
                require_approval_for_test_commands=True,
                require_approval_for_build_commands=True,
                require_approval_for_formatting=True,
                require_approval_for_package_file_changes=True,
                destructive_commands_blocked=True,
            )
            if project.source_type == "idea":
                return self._serialize_widget_data(instance, status="empty", empty_state="Imported-codebase safety mode is only relevant for imported repos.")
            return self._serialize_widget_data(
                instance,
                status="warning" if safety.write_permission_status == "read_only" else "ready",
                data_json={
                    "read_only_scan_completed": safety.read_only_scan_completed,
                    "write_permission_status": safety.write_permission_status,
                    "require_snapshot_before_edits": safety.require_snapshot_before_edits,
                    "require_approval_for_dependency_changes": safety.require_approval_for_dependency_changes,
                    "require_approval_for_test_commands": safety.require_approval_for_test_commands,
                    "require_approval_for_build_commands": safety.require_approval_for_build_commands,
                    "require_approval_for_formatting": safety.require_approval_for_formatting,
                    "require_approval_for_package_file_changes": safety.require_approval_for_package_file_changes,
                    "destructive_commands_blocked": safety.destructive_commands_blocked,
                },
                warnings_json=["Write permission is still read-only."] if safety.write_permission_status == "read_only" else [],
            )
        if instance.widget_type == "AGENTS.md Status":
            status_record: AgentInstructionsStatus = import_service.get_agents_status(db, project, create_if_missing=False)
            if project.source_type == "idea" and not status_record.has_agents_md:
                return self._serialize_widget_data(instance, status="empty", empty_state="AGENTS.md status is mainly useful for imported repos.")
            return self._serialize_widget_data(
                instance,
                status="ready" if status_record.has_agents_md else "warning",
                data_json={
                    "has_agents_md": status_record.has_agents_md,
                    "path": status_record.agents_md_path,
                    "summary": status_record.summary,
                    "recommended_action": status_record.recommended_action,
                },
                warnings_json=["AGENTS.md is missing."] if not status_record.has_agents_md else [],
            )
        if instance.widget_type == "Scan Coverage":
            record: CodebaseMap = import_service.get_codebase_map(db, project)
            if not record.scan_depth:
                return self._serialize_widget_data(instance, status="empty", empty_state="Scan coverage is not available yet.")
            return self._serialize_widget_data(
                instance,
                status="warning" if record.unindexed_areas_json else "ready",
                data_json={
                    "scan_depth": record.scan_depth,
                    "codebase_size": record.codebase_size,
                    "recommended_scan_strategy": record.recommended_scan_strategy,
                    "indexed_areas": list(record.indexed_areas_json or []),
                    "unindexed_areas": list(record.unindexed_areas_json or []),
                },
                warnings_json=["Some areas still need targeted scan coverage."] if record.unindexed_areas_json else [],
            )
        if instance.widget_type == "Manager Assumptions":
            assumptions = [
                {
                    "assumption": entry.assumption,
                    "reason": entry.reason,
                    "confidence": entry.confidence,
                    "status": entry.status,
                    "created_at": entry.created_at,
                    "source": "persisted",
                }
                for entry in list(
                    db.scalars(
                        select(ManagerAssumption)
                        .where(ManagerAssumption.project_id == project.id)
                        .order_by(ManagerAssumption.created_at.desc(), ManagerAssumption.id.desc())
                    )
                )
            ] or self._preview_manager_assumptions(db, project)
            if not assumptions:
                return self._serialize_widget_data(instance, status="empty", empty_state="No active Manager assumptions are recorded right now.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={"items": [
                    {
                        "assumption": entry["assumption"],
                        "reason": entry["reason"],
                        "confidence": entry["confidence"],
                        "status": entry["status"],
                        "created_at": entry["created_at"],
                        "source": entry["source"],
                    }
                    for entry in assumptions[:12]
                ]},
            )
        if instance.widget_type == "Repo Intelligence":
            repo = None
            persisted_repo = project.repo_intelligence
            persisted_has_signal = persisted_repo is not None and any(
                [
                    persisted_repo.languages_json,
                    persisted_repo.frameworks_json,
                    persisted_repo.important_folders_json,
                    persisted_repo.entry_points_json,
                    persisted_repo.build_commands_json,
                    persisted_repo.test_commands_json,
                ]
            )
            if persisted_repo is not None and persisted_has_signal:
                repo = {
                    "languages_json": list(persisted_repo.languages_json or []),
                    "frameworks_json": list(persisted_repo.frameworks_json or []),
                    "package_managers_json": list(persisted_repo.package_managers_json or []),
                    "entry_points_json": list(persisted_repo.entry_points_json or []),
                    "build_commands_json": list(persisted_repo.build_commands_json or []),
                    "test_commands_json": list(persisted_repo.test_commands_json or []),
                    "important_folders_json": list(persisted_repo.important_folders_json or []),
                    "docs_found_json": list(persisted_repo.docs_found_json or []),
                    "ci_config_json": list(persisted_repo.ci_config_json or []),
                    "deployment_config_json": list(persisted_repo.deployment_config_json or []),
                    "risky_files_json": list(persisted_repo.risky_files_json or []),
                    "last_indexed_at": persisted_repo.last_indexed_at,
                    "source": "persisted",
                }
            else:
                repo = {**self._preview_repo_intelligence(project), "source": "computed"}
            if not repo["languages_json"] and not repo["frameworks_json"] and not repo["important_folders_json"]:
                return self._serialize_widget_data(instance, status="empty", empty_state="Repository intelligence is not available yet. Re-index after the workspace exists.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "languages": list(repo["languages_json"]),
                    "frameworks": list(repo["frameworks_json"]),
                    "package_managers": list(repo["package_managers_json"]),
                    "entry_points": list(repo["entry_points_json"]),
                    "build_commands": list(repo["build_commands_json"]),
                    "test_commands": list(repo["test_commands_json"]),
                    "important_folders": list(repo["important_folders_json"]),
                    "docs_found": list(repo["docs_found_json"]),
                    "ci_config": list(repo["ci_config_json"]),
                    "deployment_config": list(repo["deployment_config_json"]),
                    "risky_files": list(repo["risky_files_json"]),
                    "last_indexed_at": repo["last_indexed_at"],
                    "source": repo["source"],
                },
            )
        if instance.widget_type == "Validation Recipe":
            recipe = next(iter(project.validation_recipes or []), None) or self._preview_validation_recipe(db, project)
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "name": recipe.name,
                    "steps": list(recipe.steps_json or []),
                    "status": recipe.status,
                    "last_run_at": recipe.last_run_at,
                    "last_result": recipe.last_result,
                    "can_run": False,
                },
            )
        if instance.widget_type == "Handoff Quality":
            support = get_support()
            handoff_quality: HandoffQualityPreference = support["handoff_quality"]
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={
                    "quality_level": handoff_quality.quality_level,
                    "include_run_commands": handoff_quality.include_run_commands,
                    "include_known_limitations": handoff_quality.include_known_limitations,
                    "include_artifacts": handoff_quality.include_artifacts,
                    "include_tests": handoff_quality.include_tests,
                    "include_next_steps": handoff_quality.include_next_steps,
                    "handoff_progress": overview["handoff_progress"],
                    "readiness_label": overview["readiness_label"],
                },
            )
        if instance.widget_type == "Change Request Mode":
            change_requests = list(
                db.scalars(
                    select(ChangeRequest)
                    .where(ChangeRequest.project_id == project.id)
                    .order_by(ChangeRequest.updated_at.desc(), ChangeRequest.id.desc())
                )
            )
            if not change_requests:
                return self._serialize_widget_data(instance, status="empty", empty_state="No change requests have been logged for this project yet.")
            return self._serialize_widget_data(
                instance,
                status="ready",
                data_json={"items": [
                    {
                        "id": item.id,
                        "request_text": item.request_text,
                        "classification": item.classification,
                        "impact_estimate": item.impact_estimate,
                        "status": item.status,
                        "updated_at": item.updated_at,
                    }
                    for item in change_requests[:10]
                ]},
            )
        if instance.widget_type == "Handoff Progress":
            return self._serialize_widget_data(instance, status="ready", data_json=overview)
        if instance.widget_type == "What Changed Timeline":
            support = get_support()
            items = [
                {
                    "title": entry.title,
                    "detail": entry.summary,
                    "severity": entry.severity,
                    "created_at": entry.created_at,
                }
                for entry in support["timeline"][:10]
            ]
            if not items:
                return self._serialize_widget_data(instance, status="empty", empty_state="No project timeline entries exist yet.")
            return self._serialize_widget_data(instance, status="ready", data_json={"items": items})
        if instance.widget_type == "Agent Report Inbox":
            messages = [message for message in self.list_manager_messages(db, project) if message["role"] == "agent"][:10]
            if not messages:
                return self._serialize_widget_data(instance, status="empty", empty_state="No agent reports have been routed to the Manager yet.")
            return self._serialize_widget_data(instance, status="ready", data_json={"items": messages})
        if instance.widget_type == "Human Attention Queue":
            pending_questions = self.list_pending_questions(db, project)
            pending_approvals = self.list_pending_approvals(db, project)
            items = []
            if current_action["type"] != "no_action":
                items.append({"kind": current_action["type"], "title": current_action["title"], "message": current_action["message"]})
            items.extend({"kind": "manager_question", "title": item["question"], "message": item.get("selected_text") or ""} for item in pending_questions[:5])
            items.extend({"kind": approval["request_type"], "title": approval["title"], "message": approval["reason_short"]} for approval in pending_approvals[:5])
            if not items:
                return self._serialize_widget_data(instance, status="empty", empty_state="No human attention is needed right now.")
            return self._serialize_widget_data(instance, status="warning", data_json={"items": items[:10]})
        if instance.widget_type == "Live Project Map":
            return self._serialize_widget_data(instance, status="coming_soon", empty_state="Live Project Map is still experimental and not ready to pretend otherwise.")
        return self._serialize_widget_data(instance, status="empty", empty_state=WIDGET_EMPTY_STATE)

    async def get_widget_instance_data(self, db: Session, instance_id: int, *, project: Project | None = None) -> dict[str, Any]:
        instance = self._widget_instance_or_error(db, instance_id, project=project)
        if instance.scope == "dashboard":
            profile = self._app_profile_preview(db)
            projects = self._ordered_projects(db, include_archived=False)
            active_builds = await self._dashboard_active_builds(db, projects)
            attention_items = await self._dashboard_attention_items(db, projects)
            blocked_agents = []
            for project in projects:
                for agent_payload in self._sorted_workspace_agents(db, project.id):
                    if agent_payload["display_status"] in {"blocked", "error"}:
                        blocked_agents.append(agent_payload)
            system_status = await self.get_system_status(db)
            return await self._dashboard_widget_data_for_instance(
                db,
                instance,
                projects=projects,
                profile=profile,
                system_status=system_status,
                active_builds=active_builds,
                attention_items=attention_items,
                blocked_agents=blocked_agents,
            )
        if instance.project_id is None:
            raise ValueError("Project widget instance is missing its project context.")
        project = db.get(Project, instance.project_id)
        if project is None:
            raise ValueError("Project not found")
        settings = self._project_settings_preview(db, project)
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        degraded_notices = await self._workspace_degraded_notices(project, settings)
        current_action = self._derive_current_action_preview(db, project, degraded_notices)
        overview = self._project_overview(db, project, tasks, current_action)
        return await self._project_widget_data_for_instance(
            db,
            instance,
            project=project,
            tasks=tasks,
            current_action=current_action,
            overview=overview,
            degraded_notices=degraded_notices,
        )

    async def get_dashboard_widget_summary(self, db: Session) -> dict[str, Any]:
        profile = self._app_profile_preview(db)
        instances = [item for item in self._dashboard_widget_instances(db, profile, create_if_missing=False) if item.enabled]
        projects = self._ordered_projects(db, include_archived=False)
        active_builds = await self._dashboard_active_builds(db, projects)
        attention_items = await self._dashboard_attention_items(db, projects)
        blocked_agents = []
        for project in projects:
            for agent_payload in self._sorted_workspace_agents(db, project.id):
                if agent_payload["display_status"] in {"blocked", "error"}:
                    blocked_agents.append(agent_payload)
        system_status = await self.get_system_status(db)
        data = [
            await self._dashboard_widget_data_for_instance(
                db,
                instance,
                projects=projects,
                profile=profile,
                system_status=system_status,
                active_builds=active_builds,
                attention_items=attention_items,
                blocked_agents=blocked_agents,
            )
            for instance in instances
        ]
        return {
            "scope": "dashboard",
            "project_id": None,
            "instances": [self._serialize_widget_instance(item) for item in instances],
            "data": data,
            "catalog": self._widget_catalog_for_scope(db, "dashboard"),
        }

    async def get_project_widget_summary(self, db: Session, project: Project) -> dict[str, Any]:
        settings = self._project_settings_preview(db, project)
        instances = [item for item in self._project_widget_instances(db, project, settings, create_if_missing=False) if item.enabled]
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        degraded_notices = await self._workspace_degraded_notices(project, settings)
        current_action = self._derive_current_action_preview(db, project, degraded_notices)
        overview = self._project_overview(db, project, tasks, current_action)
        data = [
            await self._project_widget_data_for_instance(
                db,
                instance,
                project=project,
                tasks=tasks,
                current_action=current_action,
                overview=overview,
                degraded_notices=degraded_notices,
                preview_support=True,
            )
            for instance in instances
        ]
        return {
            "scope": "project",
            "project_id": project.id,
            "instances": [self._serialize_widget_instance(item) for item in instances],
            "data": data,
            "catalog": self._widget_catalog_for_scope(db, "project"),
        }

    def _project_display_status(self, project: Project) -> str:
        if project.archived_at:
            return "archived"
        if project.status in {"import_scanning"}:
            return "import_scanning"
        if project.status in {"import_review"}:
            return "import_review"
        if project.status in {"handoff_ready"}:
            return "ready_for_handoff"
        if project.status in {"blocked"}:
            return "blocked"
        if project.status in {"interview_in_progress", "interview_complete"}:
            return "interviewing"
        if project.status in {"draft", "docs_ready", "plan_ready", "pending_approval"}:
            return "planning"
        if project.status in {"paused"}:
            return "paused"
        if project.status in {"building"}:
            return "building"
        return project.status or "planning"

    @staticmethod
    def _status_label(status: str | None) -> str:
        if not status:
            return "Planning"
        return status.replace("_", " ").title()

    def _project_latest_activity(self, db: Session, project: Project) -> str | None:
        latest_message = db.scalar(
            select(ManagerMessage)
            .where(ManagerMessage.project_id == project.id)
            .order_by(ManagerMessage.created_at.desc())
        )
        if latest_message and latest_message.content_markdown:
            return latest_message.content_markdown.strip().splitlines()[0][:180]
        latest_task = db.scalar(select(Task).where(Task.project_id == project.id).order_by(Task.updated_at.desc(), Task.id.desc()))
        if latest_task:
            return latest_task.title
        return project.idea.strip().splitlines()[0][:180] if project.idea else None

    def _project_card_data(self, db: Session, project: Project) -> dict[str, Any]:
        latest_task = db.scalar(select(Task).where(Task.project_id == project.id).order_by(Task.updated_at.desc(), Task.id.desc()))
        latest_milestone = latest_task.milestone if latest_task and latest_task.milestone else project.latest_milestone
        latest_activity = self._project_latest_activity(db, project)
        handoff_status = "ready" if project.status == "handoff_ready" or project.final_report_json else "not_ready"
        docs_path = project.docs_path or str(self._project_docs_dir(project))
        return {
            "id": project.id,
            "name": project.name,
            "slug": self._effective_project_slug(project),
            "idea": project.idea,
            "workspace_path": project.workspace_path,
            "status": project.status,
            "runner_mode": project.runner_mode,
            "manager_mode": project.manager_mode,
            "created_by": project.created_by,
            "docs_path": docs_path,
            "final_report_json": project.final_report_json,
            "pinned": project.pinned,
            "archived_at": project.archived_at,
            "last_opened_at": project.last_opened_at,
            "latest_milestone": latest_milestone,
            "latest_activity": latest_activity,
            "handoff_status": handoff_status,
            "source_type": project.source_type,
            "source_path": project.source_path,
            "import_mode": project.import_mode,
            "imported_at": project.imported_at,
            "scan_status": project.scan_status,
            "last_indexed_at": project.last_indexed_at,
            "write_permission_status": project.write_permission_status,
            "display_status": self._project_display_status(project),
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }

    def _serialize_project_card(self, db: Session, project: Project) -> dict[str, Any]:
        return self._project_card_data(db, project)

    def _ordered_projects(self, db: Session, *, include_archived: bool) -> list[Project]:
        projects = list(
            db.scalars(
                select(Project).order_by(
                    Project.pinned.desc(),
                    Project.last_opened_at.desc().nullslast(),
                    Project.updated_at.desc(),
                    Project.id.desc(),
                )
            )
        )
        if not include_archived:
            projects = [project for project in projects if not project.archived_at]
        return projects

    def _sidebar_projects(self, projects: list[Project]) -> list[Project]:
        active_projects = [project for project in projects if not project.archived_at]
        return active_projects[:3]

    def _redact_payload(self, value: Any) -> Any:
        return redact_value(value)

    def _publish_workspace_state(self, db: Session, project_id: int) -> None:
        self.events.publish(db, project_id, "project_action_updated", {"project_id": project_id})
        self.events.publish(db, project_id, "manager_queue_updated", {"project_id": project_id})

    def _approval_signature(self, approval: ApprovalRequest) -> str:
        payload = approval.request_payload_json or {}
        command = str(payload.get("command") or approval.title).strip().lower()
        cwd = (approval.cwd or "").strip().lower()
        return f"{approval.request_type}:{command}:{cwd}"

    def _record_manager_message(
        self,
        db: Session,
        project: Project,
        *,
        role: str,
        message_type: str,
        content_markdown: str,
        related_agent_id: int | None = None,
        related_task_id: int | None = None,
        actions_json: list[dict[str, Any]] | None = None,
        resolved_at: datetime | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> ManagerMessage:
        self._validate_project_related_refs(
            db,
            project,
            related_agent_id=related_agent_id,
            related_task_id=related_task_id,
            agent_label="Manager message related agent",
            task_label="Manager message related task",
        )
        message = ManagerMessage(
            project_id=project.id,
            role=role,
            message_type=message_type,
            content_markdown=content_markdown,
            related_agent_id=related_agent_id,
            related_task_id=related_task_id,
            actions_json=actions_json,
            resolved_at=resolved_at,
            metadata_json=metadata_json,
        )
        db.add(message)
        db.flush()
        self.events.publish(
            db,
            project.id,
            "manager_message_created",
            {
                "message_id": message.id,
                "role": role,
                "message_type": message_type,
                "related_agent_id": related_agent_id,
                "related_task_id": related_task_id,
            },
        )
        return message

    def _serialize_manager_message(self, message: ManagerMessage) -> dict[str, Any]:
        return {
            "id": message.id,
            "project_id": message.project_id,
            "role": message.role,
            "message_type": message.message_type,
            "content_markdown": message.content_markdown,
            "created_at": message.created_at,
            "related_agent_id": message.related_agent_id,
            "related_task_id": message.related_task_id,
            "actions_json": message.actions_json,
            "resolved_at": message.resolved_at,
            "metadata_json": message.metadata_json,
        }

    def _serialize_question(self, question: ManagerQuestion) -> dict[str, Any]:
        question_markdown = question.question
        options = list(question.options_json or [])
        if options:
            rendered_options = []
            for option in options:
                label = str(option.get("label") or option.get("id") or "").strip()
                description = str(option.get("description") or "").strip()
                if label and description:
                    rendered_options.append(f"- **{label}**: {description}")
                elif label:
                    rendered_options.append(f"- **{label}**")
            if rendered_options:
                question_markdown = "\n".join([question.question, "", "### Options", *rendered_options])
        return {
            "id": question.id,
            "project_id": question.project_id,
            "question": question.question,
            "question_markdown": question_markdown,
            "options_json": options,
            "impact": question.impact,
            "status": question.status,
            "selected_option_id": question.selected_option_id,
            "selected_text": question.selected_text,
            "manager_recommendation": question.manager_recommendation,
            "auto_decide_at": question.auto_decide_at,
            "created_at": question.created_at,
            "resolved_at": question.resolved_at,
            "related_task_id": question.related_task_id,
            "related_agent_id": question.related_agent_id,
            "metadata_json": question.metadata_json,
        }

    @staticmethod
    def _normalize_report_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _format_provider_manager_reply(self, reply: str) -> str:
        text = (reply or "").strip()
        if not text:
            return reply
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return reply
        if not isinstance(payload, dict):
            return reply
        markdown = str(payload.get("reply_markdown") or "").strip()
        if markdown:
            return markdown

        request_payload = payload.get("request")
        if not isinstance(request_payload, dict):
            request_payload = {}

        def _first_value(*keys: str, source: dict[str, Any] | None = None) -> Any:
            target = source if source is not None else payload
            for key in keys:
                if key not in target:
                    continue
                value = target.get(key)
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                return value
            return None

        lines: list[str] = []
        title = str(_first_value("title") or "").strip()
        project_name = str(_first_value("project", "project_name", "projectName") or "").strip()
        if title:
            lines.append(f"## {title}")
        elif project_name:
            lines.append(f"## Mission Control Manager: {project_name}")

        status = str(_first_value("status") or _first_value("status", source=request_payload) or "").strip()
        if status:
            lines.extend(["", f"**Status:** {status.replace('_', ' ')}"])

        summary = str(
            _first_value("summary", "description", "message")
            or _first_value("summary", "description", source=request_payload)
            or ""
        ).strip()
        if summary:
            lines.extend(["", summary])

        message_payload = _first_value("message")
        if isinstance(message_payload, dict):
            content = str(message_payload.get("content") or "").strip()
            if content:
                lines.extend(["", content])
        elif isinstance(message_payload, str) and message_payload.strip():
            lines.extend(["", message_payload.strip()])

        def _append_section(title_text: str, items: Any, *, key: str = "description") -> None:
            if not isinstance(items, list):
                return
            rendered: list[str] = []
            for item in items[:6]:
                if isinstance(item, dict):
                    value = str(item.get(key) or item.get("summary") or item.get("title") or item.get("question") or "").strip()
                else:
                    value = str(item).strip()
                if value:
                    rendered.append(f"- {value}")
            if rendered:
                lines.extend(["", f"### {title_text}", *rendered])

        _append_section("Next steps", _first_value("next_steps", "nextSteps") or _first_value("next_steps", "nextSteps", source=request_payload))
        _append_section("Questions", _first_value("questions") or _first_value("questions", source=request_payload), key="question")
        _append_section("Blockers", _first_value("blockers") or _first_value("blockers", source=request_payload), key="summary")
        _append_section("Risks", _first_value("risks") or _first_value("risks", source=request_payload), key="summary")

        normalized = "\n".join(lines).strip()
        return self._sanitize_provider_markdown(normalized or reply)

    @staticmethod
    def _sanitize_provider_markdown(text: str) -> str:
        if not text:
            return text

        def _is_echo_payload(line: str) -> bool:
            compact = line.strip()
            if not compact:
                return False
            if compact.startswith(("{", "[")) and any(token in compact for token in ("'from'", '"from"', "'content'", '"content"')):
                return True
            return False

        cleaned_lines: list[str] = []
        previous_normalized = ""
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if _is_echo_payload(stripped):
                continue
            stripped = re.sub(r"^(Understood|Certainly|Absolutely|Got it)[,!\s]+(?:Operator|user)?[.!:\s-]*", "", stripped, flags=re.IGNORECASE)
            line = stripped if stripped else ""
            normalized_line = re.sub(r"\s+", " ", stripped.lower()).strip(":.- ")
            if normalized_line and normalized_line == previous_normalized:
                continue
            if normalized_line:
                previous_normalized = normalized_line
            cleaned_lines.append(line)

        sanitized = "\n".join(cleaned_lines)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
        return sanitized or text.strip()

    def _interview_question_mirrors(self, db: Session, project: Project, session: InterviewSession) -> list[ManagerQuestion]:
        questions = list(
            db.scalars(
                select(ManagerQuestion)
                .where(ManagerQuestion.project_id == project.id)
                .order_by(ManagerQuestion.created_at.asc(), ManagerQuestion.id.asc())
            )
        )
        return [
            question
            for question in questions
            if isinstance(question.metadata_json, dict)
            and question.metadata_json.get("question_type") == "interview"
            and int(question.metadata_json.get("interview_session_id") or 0) == session.id
        ]

    def _resolve_interview_question_mirrors(self, db: Session, project: Project, session: InterviewSession, *, reason: str) -> None:
        for mirror in self._interview_question_mirrors(db, project, session):
            if mirror.status != "pending":
                continue
            mirror.status = "auto_decided"
            mirror.selected_option_id = "superseded"
            mirror.selected_text = reason
            mirror.resolved_at = utc_now()
        self._publish_workspace_state(db, project.id)

    def _sync_interview_question_mirror(self, db: Session, project: Project, session: InterviewSession) -> ManagerQuestion | None:
        pending_questions = self._pending_interview_questions(session)
        pending_question = pending_questions[0] if pending_questions else None
        mirrors = self._interview_question_mirrors(db, project, session)
        active_mirror = next((mirror for mirror in mirrors if mirror.status == "pending"), None)

        if pending_question is None:
            self._resolve_interview_question_mirrors(
                db,
                project,
                session,
                reason="Interview moved forward without a pending intake question.",
            )
            return None

        metadata_json = {
            "question_type": "interview",
            "interview_session_id": session.id,
            "interview_question_id": pending_question.id,
        }
        if active_mirror is None:
            active_mirror = self._create_question(
                db,
                project,
                question=pending_question.question,
                options_json=list(pending_question.options_json or []),
                impact=pending_question.impact,
                manager_recommendation=None,
                related_task_id=None,
                related_agent_id=None,
                metadata_json=metadata_json,
            )
        else:
            active_mirror.question = pending_question.question
            active_mirror.options_json = list(pending_question.options_json or [])
            active_mirror.impact = pending_question.impact
            active_mirror.manager_recommendation = None
            active_mirror.status = "pending"
            active_mirror.selected_option_id = None
            active_mirror.selected_text = None
            active_mirror.resolved_at = None
            active_mirror.metadata_json = metadata_json

        for mirror in mirrors:
            if mirror.id == active_mirror.id or mirror.status != "pending":
                continue
            mirror.status = "auto_decided"
            mirror.selected_option_id = "superseded"
            mirror.selected_text = "Superseded by a newer interview question."
            mirror.resolved_at = utc_now()

        self._publish_workspace_state(db, project.id)
        return active_mirror

    def _serialize_approval(self, approval: ApprovalRequest) -> dict[str, Any]:
        return {
            "id": approval.id,
            "project_id": approval.project_id,
            "request_type": approval.request_type,
            "requesting_agent_id": approval.requesting_agent_id,
            "task_id": approval.task_id,
            "title": approval.title,
            "reason_short": approval.reason_short,
            "risk_level": approval.risk_level,
            "status": approval.status,
            "cwd": approval.cwd,
            "request_payload_json": self._redact_payload(approval.request_payload_json or {}),
            "runner_ref": approval.runner_ref,
            "resolved_by": approval.resolved_by,
            "created_at": approval.created_at,
            "resolved_at": approval.resolved_at,
        }

    def _display_status(self, agent: Agent, needs_approval: bool) -> str:
        if needs_approval:
            return "blocked"
        if agent.status == "error":
            return "error"
        if agent.status in {"done", "stopped"}:
            return "retired"
        if agent.status == "blocked":
            return "blocked"
        if agent.status == "needs_review":
            return "reviewing"
        action = (agent.current_action or "").lower()
        if agent.status == "starting":
            return "thinking"
        if agent.status == "working":
            if any(token in action for token in {"test", "run", "validate"}):
                return "running"
            if any(token in action for token in {"review", "handoff"}):
                return "reviewing"
            if any(token in action for token in {"monitor", "watch"}):
                return "monitoring"
            if any(token in action for token in {"code", "implement", "build", "patch"}):
                return "coding"
            return "active"
        if agent.status == "waiting":
            return "waiting"
        return "idle"

    def _serialize_agent(self, db: Session, agent: Agent) -> dict[str, Any]:
        pending_approval = db.scalar(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.project_id == agent.project_id,
                ApprovalRequest.requesting_agent_id == agent.id,
                ApprovalRequest.status == "pending",
            )
            .order_by(ApprovalRequest.created_at.asc())
        )
        current_task = db.get(Task, agent.current_task_id) if agent.current_task_id else None
        display_status = self._display_status(agent, pending_approval is not None)
        return {
            "id": agent.id,
            "project_id": agent.project_id,
            "name": agent.name,
            "role": agent.role,
            "kind": agent.kind,
            "status": agent.status,
            "current_task_id": agent.current_task_id,
            "swarm_plan_id": agent.swarm_plan_id,
            "workspace_path": agent.workspace_path,
            "archetype": agent.archetype,
            "mission": agent.mission,
            "retire_when": agent.retire_when,
            "session_ref": agent.session_ref,
            "locked_paths_json": agent.locked_paths_json,
            "failure_count": agent.failure_count,
            "last_report_summary": agent.last_report_summary,
            "active_model": agent.active_model,
            "active_reasoning_effort": agent.active_reasoning_effort,
            "active_runner_type": agent.active_runner_type,
            "current_action": agent.current_action,
            "current_task_title": current_task.title if current_task else None,
            "display_status": display_status,
            "runner_mode": agent.active_runner_type or "idle",
            "needs_approval": pending_approval is not None,
            "last_update": agent.last_update,
        }

    def _record_swarm_event(
        self,
        db: Session,
        project: Project,
        *,
        event_type: str,
        message: str,
        swarm_plan_id: int | None = None,
        agent_id: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> SwarmEvent:
        event = SwarmEvent(
            project_id=project.id,
            swarm_plan_id=swarm_plan_id,
            event_type=event_type,
            message=message,
            agent_id=agent_id,
            metadata_json=dict(metadata_json or {}),
        )
        db.add(event)
        db.flush()
        self.events.publish(
            db,
            project.id,
            event_type,
            {
                "swarm_event_id": event.id,
                "swarm_plan_id": swarm_plan_id,
                "agent_id": agent_id,
                **dict(metadata_json or {}),
            },
        )
        self._publish_workspace_state(db, project.id)
        return event

    def _current_swarm_plan_record(self, db: Session, project_id: int) -> SwarmPlan | None:
        return db.scalar(
            select(SwarmPlan)
            .where(SwarmPlan.project_id == project_id, SwarmPlan.status != "superseded")
            .order_by(SwarmPlan.updated_at.desc(), SwarmPlan.id.desc())
        )

    def _swarm_specs_for_plan(self, db: Session, swarm_plan_id: int) -> list[SwarmAgentSpec]:
        return list(
            db.scalars(
                select(SwarmAgentSpec)
                .where(SwarmAgentSpec.swarm_plan_id == swarm_plan_id)
                .order_by(SwarmAgentSpec.priority.asc(), SwarmAgentSpec.id.asc())
            )
        )

    def _swarm_approval_required(self, plan: SwarmPlan, preferences: SwarmPreferences) -> bool:
        return plan.recommended_agent_count > preferences.require_approval_above_agent_count

    def _serialize_swarm_spec(self, spec: SwarmAgentSpec) -> dict[str, Any]:
        return {
            "id": spec.id,
            "swarm_plan_id": spec.swarm_plan_id,
            "project_id": spec.project_id,
            "archetype": spec.archetype,
            "name": spec.name,
            "mission": spec.mission,
            "model_policy": spec.model_policy,
            "toolset_json": list(spec.toolset_json or []),
            "allowed_paths_json": list(spec.allowed_paths_json or []),
            "forbidden_paths_json": list(spec.forbidden_paths_json or []),
            "spawn_phase": spec.spawn_phase,
            "retire_when": spec.retire_when,
            "priority": spec.priority,
            "status": spec.status,
        }

    def _swarm_usage_warning(self, plan: SwarmPlan, preferences: SwarmPreferences) -> str | None:
        if plan.recommended_agent_count >= max(preferences.require_approval_above_agent_count, 10):
            return "Large swarm: expect higher coordination overhead and more provider/runtime intensity."
        if plan.coordination_risk == "high" or plan.path_conflict_risk == "high":
            return "Coordination risk is high enough that path ownership and review gates matter."
        return None

    def _swarm_spec_status_summary(self, specs: list[SwarmAgentSpec]) -> dict[str, int]:
        summary: dict[str, int] = {}
        for spec in specs:
            summary[spec.status] = summary.get(spec.status, 0) + 1
        return summary

    def _swarm_target_specs(
        self,
        specs: list[SwarmAgentSpec],
        *,
        recommended_agent_count: int,
        activate_deferred: bool,
    ) -> list[SwarmAgentSpec]:
        eligible = [
            spec
            for spec in sorted(specs, key=lambda item: (item.priority, item.id))
            if spec.status in {"planned", "spawned"} or (activate_deferred and spec.status == "deferred")
        ]
        if not eligible:
            return []
        return eligible[: max(1, recommended_agent_count)]

    def _swarm_launch_readiness(
        self,
        db: Session,
        project: Project,
        plan: SwarmPlan,
        specs: list[SwarmAgentSpec],
    ) -> tuple[dict[str, Any], str | None, str | None]:
        simulation = simulation_service.latest_simulation(db, project)
        if simulation is None or simulation.swarm_plan_id != plan.id:
            simulation = simulation_service.simulate_launch(db, project, plan)
        launch_order = list(simulation.recommended_launch_order_json or [])
        next_launch = next((item for item in launch_order if str(item.get("status")) == "launch"), None)
        next_wait = next((item for item in launch_order if str(item.get("status")) == "wait"), None)
        if next_launch is not None:
            wave_label = f"Launch next: {next_launch.get('name')}"
            next_step = "Spawn the current launch-ready wave before waking deferred specialists."
        elif next_wait is not None:
            wave_label = f"Deferred wave: {next_wait.get('spawn_phase') or 'later phase'}"
            next_step = "Clear the current bottleneck or finish the earlier wave before expanding the swarm."
        else:
            wave_label = "No launch recommendation"
            next_step = "Revise the swarm plan before spawning more workers."
        immediate_specs = self._swarm_target_specs(
            specs,
            recommended_agent_count=plan.recommended_agent_count,
            activate_deferred=False,
        )
        immediate_ids = {spec.id for spec in immediate_specs}
        readiness = {
            "safe_to_launch_count": simulation.safe_to_launch_count,
            "should_wait_count": simulation.should_wait_count,
            "needs_user_approval_count": simulation.needs_user_approval_count,
            "conflict_warnings": list(simulation.conflict_warnings_json or []),
            "bottlenecks": list(simulation.bottlenecks_json or []),
            "recommended_launch_order": launch_order,
            "immediate_specs": len(immediate_specs),
            "deferred_specs": len(
                [
                    spec
                    for spec in specs
                    if spec.id not in immediate_ids and spec.status in {"planned", "deferred", "spawned"}
                ]
            ),
        }
        return readiness, wave_label, next_step

    def _serialize_swarm_plan(self, db: Session, project: Project, plan: SwarmPlan | None) -> dict[str, Any] | None:
        if plan is None:
            return None
        preferences = self._swarm_preferences(project)
        specs = self._swarm_specs_for_plan(db, plan.id)
        spec_status_summary = self._swarm_spec_status_summary(specs)
        launch_readiness, recommended_wave_label, recommended_next_step = self._swarm_launch_readiness(db, project, plan, specs)
        active_agent_count = db.scalar(
            select(func.count(Agent.id)).where(
                Agent.project_id == project.id,
                Agent.kind == "worker",
                Agent.swarm_plan_id == plan.id,
                ~Agent.status.in_(["done", "stopped"]),
            )
        ) or 0
        return {
            "id": plan.id,
            "project_id": plan.project_id,
            "milestone_id": plan.milestone_id,
            "mode": plan.mode,
            "goal": plan.goal,
            "recommended_agent_count": plan.recommended_agent_count,
            "max_agent_count": plan.max_agent_count,
            "coordination_risk": plan.coordination_risk,
            "path_conflict_risk": plan.path_conflict_risk,
            "expected_bottlenecks_json": list(plan.expected_bottlenecks_json or []),
            "validation_strategy_json": list(plan.validation_strategy_json or []),
            "strategy_summary": plan.strategy_summary,
            "approved_by_user": plan.approved_by_user,
            "status": plan.status,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
            "approval_required": self._swarm_approval_required(plan, preferences),
            "usage_warning": self._swarm_usage_warning(plan, preferences),
            "active_agent_count": active_agent_count,
            "current_bottleneck": next(iter(plan.expected_bottlenecks_json or []), None),
            "dynamic_spawning_enabled": preferences.allow_dynamic_spawning,
            "dynamic_retirement_enabled": preferences.allow_dynamic_retirement,
            "spec_status_summary": spec_status_summary,
            "launch_readiness": launch_readiness,
            "recommended_wave_label": recommended_wave_label,
            "recommended_next_step": recommended_next_step,
            "specs": [self._serialize_swarm_spec(spec) for spec in specs],
        }

    def _serialize_swarm_event(self, event: SwarmEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "project_id": event.project_id,
            "swarm_plan_id": event.swarm_plan_id,
            "event_type": event.event_type,
            "message": event.message,
            "agent_id": event.agent_id,
            "created_at": event.created_at,
            "metadata_json": dict(event.metadata_json or {}),
        }

    def get_swarm_preferences(self, db: Session, project: Project, *, create_if_missing: bool = False) -> dict[str, Any]:
        preferences = self._ensure_swarm_preferences(db, project) if create_if_missing else self._swarm_preferences(project)
        return self._serialize_swarm_preferences(preferences)

    def update_swarm_preferences(self, db: Session, project: Project, payload: SwarmPreferencesUpdate) -> dict[str, Any]:
        preferences = self._ensure_swarm_preferences(db, project)
        fields_set = set(getattr(payload, "model_fields_set", set()))
        if not fields_set:
            fields_set = {
                field
                for field in [
                    "optimization_mode",
                    "swarm_aggressiveness",
                    "max_agents",
                    "require_approval_above_agent_count",
                    "allow_dynamic_spawning",
                    "allow_dynamic_retirement",
                    "docs_depth",
                    "testing_depth",
                ]
                if hasattr(payload, field)
            }
        if "optimization_mode" in fields_set and payload.optimization_mode is not None:
            preferences.optimization_mode = payload.optimization_mode
        if "swarm_aggressiveness" in fields_set and payload.swarm_aggressiveness is not None:
            preferences.swarm_aggressiveness = payload.swarm_aggressiveness
        if "max_agents" in fields_set and payload.max_agents is not None:
            preferences.max_agents = max(1, int(payload.max_agents))
        if "require_approval_above_agent_count" in fields_set and payload.require_approval_above_agent_count is not None:
            preferences.require_approval_above_agent_count = max(1, int(payload.require_approval_above_agent_count))
        if "allow_dynamic_spawning" in fields_set and payload.allow_dynamic_spawning is not None:
            preferences.allow_dynamic_spawning = payload.allow_dynamic_spawning
        if "allow_dynamic_retirement" in fields_set and payload.allow_dynamic_retirement is not None:
            preferences.allow_dynamic_retirement = payload.allow_dynamic_retirement
        if "docs_depth" in fields_set and payload.docs_depth is not None:
            preferences.docs_depth = payload.docs_depth
        if "testing_depth" in fields_set and payload.testing_depth is not None:
            preferences.testing_depth = payload.testing_depth
        db.flush()
        serialized = self._serialize_swarm_preferences(preferences)
        self.events.publish(
            db,
            project.id,
            "swarm.preferences.updated",
            {
                **serialized,
                "created_at": preferences.created_at.isoformat(),
                "updated_at": preferences.updated_at.isoformat(),
            },
        )
        self._publish_workspace_state(db, project.id)
        return serialized

    def list_agent_archetypes(self, db: Session) -> list[dict[str, Any]]:
        existing = {
            entry.name: entry
            for entry in db.scalars(select(AgentArchetype).order_by(AgentArchetype.name.asc()))
        }
        return [
            {
                "id": existing_entry.id if (existing_entry := existing.get(str(payload["name"]))) is not None else 0,
                "name": str(payload["name"]),
                "purpose": existing_entry.purpose if existing_entry is not None else str(payload["purpose"]),
                "default_guidelines": existing_entry.default_guidelines if existing_entry is not None else str(payload["default_guidelines"]),
                "default_tools_json": list(existing_entry.default_tools_json or []) if existing_entry is not None else list(payload.get("default_tools_json") or []),
                "default_permissions_json": dict(existing_entry.default_permissions_json or {}) if existing_entry is not None else dict(payload.get("default_permissions_json") or {}),
                "spawn_triggers_json": list(existing_entry.spawn_triggers_json or []) if existing_entry is not None else list(payload.get("spawn_triggers_json") or []),
                "retirement_triggers_json": list(existing_entry.retirement_triggers_json or []) if existing_entry is not None else list(payload.get("retirement_triggers_json") or []),
                "risk_profile": existing_entry.risk_profile if existing_entry is not None else str(payload.get("risk_profile") or "medium"),
            }
            for payload in AGENT_ARCHETYPE_CATALOG
        ]

    def get_swarm_plan(self, db: Session, project: Project) -> dict[str, Any] | None:
        return self._serialize_swarm_plan(db, project, self._current_swarm_plan_record(db, project.id))

    def list_swarm_events(self, db: Session, project: Project) -> list[dict[str, Any]]:
        events = list(
            db.scalars(
                select(SwarmEvent)
                .where(SwarmEvent.project_id == project.id)
                .order_by(SwarmEvent.created_at.desc(), SwarmEvent.id.desc())
            )
        )
        return [self._serialize_swarm_event(event) for event in events]

    def _sorted_workspace_agents(self, db: Session, project_id: int) -> list[dict[str, Any]]:
        agent_payloads = [self._serialize_agent(db, agent) for agent in db.scalars(select(Agent).where(Agent.project_id == project_id, Agent.kind == "worker"))]
        return sorted(
            agent_payloads,
            key=lambda item: (
                DISPLAY_STATUS_PRIORITY.get(str(item["display_status"]), 99),
                str(item["name"]).lower(),
            ),
        )

    def _serialize_queue_item(
        self,
        *,
        item_id: str,
        item_type: str,
        title: str,
        status: str,
        created_at: datetime,
        related_task_id: int | None = None,
        related_agent_id: int | None = None,
    ) -> dict[str, Any]:
        return {
            "id": item_id,
            "type": item_type,
            "title": title,
            "status": status,
            "related_task_id": related_task_id,
            "related_agent_id": related_agent_id,
            "created_at": created_at,
        }

    def _record_question_resolution_message(self, db: Session, project: Project, question: ManagerQuestion) -> None:
        decision_mode = "auto-decided" if question.status == "auto_decided" else "answered"
        self._record_manager_message(
            db,
            project,
            role="system",
            message_type="system_notice",
            content_markdown=f"Manager question {decision_mode}: **{question.selected_text or 'No answer'}**",
            related_agent_id=question.related_agent_id,
            related_task_id=question.related_task_id,
            resolved_at=question.resolved_at,
            metadata_json={"source": "manager_question", "question_id": question.id, "status": question.status},
        )

    def _record_approval_resolution_message(self, db: Session, project: Project, approval: ApprovalRequest) -> None:
        if approval.status == "denied":
            message_type = "blocker_report"
            content = f"Approval denied for **{approval.title}**. The manager will plan a safer workaround."
        else:
            message_type = "milestone_report"
            content = f"Approval recorded for **{approval.title}**. The manager can continue with the next safe step."
        self._record_manager_message(
            db,
            project,
            role="manager",
            message_type=message_type,
            content_markdown=content,
            related_agent_id=approval.requesting_agent_id,
            related_task_id=approval.task_id,
            resolved_at=approval.resolved_at,
            metadata_json={"source": "approval", "approval_id": approval.id, "status": approval.status},
        )

    def _create_question(
        self,
        db: Session,
        project: Project,
        *,
        question: str,
        options_json: list[dict[str, Any]],
        impact: str,
        manager_recommendation: str | None = None,
        auto_decide_at: datetime | None = None,
        related_task_id: int | None = None,
        related_agent_id: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> ManagerQuestion:
        self._validate_project_related_refs(
            db,
            project,
            related_agent_id=related_agent_id,
            related_task_id=related_task_id,
            agent_label="Manager question related agent",
            task_label="Manager question related task",
        )
        record = ManagerQuestion(
            project_id=project.id,
            question=question,
            options_json=options_json,
            impact=impact,
            status="pending",
            manager_recommendation=manager_recommendation,
            auto_decide_at=auto_decide_at,
            related_task_id=related_task_id,
            related_agent_id=related_agent_id,
            metadata_json=metadata_json,
        )
        db.add(record)
        db.flush()
        self.events.publish(db, project.id, "question_created", {"question_id": record.id, "impact": record.impact})
        self._publish_workspace_state(db, project.id)
        return record

    def _create_approval(
        self,
        db: Session,
        project: Project,
        *,
        request_type: str,
        title: str,
        reason_short: str,
        risk_level: str,
        cwd: str | None,
        request_payload_json: dict[str, Any],
        requesting_agent_id: int | None = None,
        task_id: int | None = None,
        runner_ref: str | None = None,
    ) -> ApprovalRequest:
        self._validate_project_related_refs(
            db,
            project,
            related_agent_id=requesting_agent_id,
            related_task_id=task_id,
            agent_label="Approval requesting agent",
            task_label="Approval related task",
        )
        evaluation = security_service.evaluate_action(
            db,
            {
                "project_id": project.id,
                "action_type": request_type,
                "title": title,
                "summary": reason_short,
                "command": request_payload_json.get("command"),
                "tool_name": request_payload_json.get("tool_name") or title,
                "cwd": cwd,
                "affected_paths_json": request_payload_json.get("affected_paths_json") or request_payload_json.get("affected_paths") or [],
                "external_access_requested": request_type in {"plugin", "connected_account"},
                "modifies_files": bool(request_payload_json.get("modifies_files")),
                "modifies_package_files": bool(request_payload_json.get("modifies_package_files")),
                "deletes_files": bool(request_payload_json.get("deletes_files")),
                "deploys": bool(request_payload_json.get("deploys")),
                "accesses_network": bool(request_payload_json.get("accesses_network")),
                "accesses_credentials": bool(request_payload_json.get("accesses_credentials")),
                "writes_outside_workspace": bool(request_payload_json.get("writes_outside_workspace")),
            },
            project=project,
        )
        assessed_risk = str(evaluation["assessment"]["risk_level"] or risk_level)
        initial_status = "pending"
        resolved_by: str | None = None
        resolved_at: datetime | None = None
        if evaluation["decision"] == "auto_approved":
            initial_status = "approved_once"
            resolved_by = "policy"
            resolved_at = utc_now()
        elif evaluation["decision"] == "blocked":
            initial_status = "denied"
            resolved_by = "policy"
            resolved_at = utc_now()
        approval = ApprovalRequest(
            project_id=project.id,
            request_type=request_type,
            requesting_agent_id=requesting_agent_id,
            task_id=task_id,
            title=title,
            reason_short=reason_short,
            risk_level=assessed_risk,
            status=initial_status,
            cwd=cwd,
            request_payload_json=self._redact_payload(request_payload_json),
            runner_ref=runner_ref,
            resolved_by=resolved_by,
            resolved_at=resolved_at,
        )
        db.add(approval)
        db.flush()
        self.events.publish(db, project.id, "approval_created", {"approval_id": approval.id, "request_type": approval.request_type})
        if initial_status != "pending":
            security_service.log_audit(
                db,
                project=project,
                action_type=request_type,
                action_summary=title,
                risk_level=approval.risk_level,
                decision="auto_approved" if initial_status == "approved_once" else "blocked",
                decided_by="policy",
                reason=str(evaluation["reason"]),
                metadata_json={"approval_id": approval.id, "cwd": cwd, "request_type": request_type},
            )
            self._record_approval_resolution_message(db, project, approval)
            self.events.publish(db, project.id, "approval_resolved", {"approval_id": approval.id, "status": approval.status})
            self._advance_dry_run_after_approval(db, project, approval)
        self._publish_workspace_state(db, project.id)
        return approval

    def _ensure_dry_run_workspace_seed(self, db: Session, project: Project) -> None:
        settings = self._ensure_project_settings(db, project)
        if settings.runner_mode != "dry_run":
            return
        seeded = (
            db.scalar(select(func.count(ManagerMessage.id)).where(ManagerMessage.project_id == project.id))
            or db.scalar(select(func.count(ManagerQuestion.id)).where(ManagerQuestion.project_id == project.id))
            or db.scalar(select(func.count(ApprovalRequest.id)).where(ApprovalRequest.project_id == project.id))
        )
        if seeded:
            return
        workers = self.initialize_build_roster(db, project)
        lead_agent = next(
            (worker for worker in workers if worker.archetype in {"feature", "frontend", "backend", "integration"}),
            workers[0] if workers else None,
        )
        demo_task = db.scalar(select(Task).where(Task.project_id == project.id).order_by(Task.id.asc()))
        if demo_task is None:
            demo_task = Task(
                project_id=project.id,
                assigned_agent_id=lead_agent.id if lead_agent else None,
                title="Simulated vertical slice",
                goal="Demonstrate the manager-led workspace loop in dry-run mode.",
                scope="Create a safe simulated build task that exercises question and approval handling.",
                agent_role=lead_agent.role if lead_agent else "Primary implementation",
                milestone="Dry-run workspace demo",
                allowed_paths_json=["src", "docs"],
                forbidden_paths_json=[],
                validation_steps_json=["Review the manager question", "Approve the simulated command if it looks safe"],
                success_criteria_json=["The workspace loop is visible without real execution."],
                estimated_complexity="small",
                dependencies_json=[],
                status="assigned",
                priority=10,
            )
            db.add(demo_task)
            db.flush()
        for worker in workers:
            if lead_agent and worker.id == lead_agent.id:
                continue
            if worker.archetype in {"research", "planner", "architect"}:
                worker.status = "waiting"
                worker.current_action = "Preparing the next swarm decision."
            elif worker.archetype == "docs":
                worker.status = "waiting"
                worker.current_action = "Queued for the documentation pass after the core flow stabilizes."
            elif worker.archetype in {"reviewer", "security", "test"}:
                worker.status = "idle"
                worker.current_action = "Waiting for implementation output before review or validation."
            else:
                worker.status = "idle"
                worker.current_action = "Standing by for a distinct slice of work."
        if lead_agent:
            lead_agent.status = "starting"
            lead_agent.current_task_id = demo_task.id
            lead_agent.current_action = "Preparing a simulated dry-run step"
            lead_agent.last_report_summary = "Dry-run workspace demo seeded."
            self.events.publish(db, project.id, "agent_updated", {"agent_id": lead_agent.id, "status": lead_agent.status})
        if project.status == "draft":
            project.status = "building"
        self._record_manager_message(
            db,
            project,
            role="manager",
            message_type="normal_update",
            content_markdown="Dry-run demo active. This workspace is simulating the manager and worker loop locally. No real provider execution has started yet.",
            related_agent_id=lead_agent.id if lead_agent else None,
            related_task_id=demo_task.id,
            metadata_json={"response_mode": "dry_run", "simulated": True},
        )
        self._create_question(
            db,
            project,
            question="Which slice should the manager validate first?",
            options_json=[
                {"id": "ui", "label": "UI shell", "description": "Prioritize the interface scaffolding and project shell."},
                {"id": "workflow", "label": "Workflow loop", "description": "Focus on approvals, questions, and the manager loop first."},
                {"id": "docs", "label": "Docs and handoff", "description": "Make the handoff and documentation surface airtight first."},
            ],
            impact="low",
            manager_recommendation="Workflow loop",
            auto_decide_at=utc_now() + timedelta(minutes=5),
            related_task_id=demo_task.id,
            related_agent_id=lead_agent.id if lead_agent else None,
            metadata_json={"simulated": True},
        )

    def _advance_dry_run_after_question(self, db: Session, project: Project, question: ManagerQuestion) -> None:
        settings = self._ensure_project_settings(db, project)
        if settings.runner_mode != "dry_run":
            return
        existing_pending = db.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.project_id == project.id, ApprovalRequest.status == "pending")
            .order_by(ApprovalRequest.id.asc())
        )
        if existing_pending:
            return
        if db.scalar(select(func.count(ApprovalRequest.id)).where(ApprovalRequest.project_id == project.id)) and question.status != "auto_decided":
            return
        agent = db.get(Agent, question.related_agent_id) if question.related_agent_id else None
        task = db.get(Task, question.related_task_id) if question.related_task_id else None
        if agent:
            agent.status = "blocked"
            agent.current_action = "Waiting for a simulated command approval"
            self.events.publish(db, project.id, "agent_updated", {"agent_id": agent.id, "status": agent.status})
        self._record_manager_message(
            db,
            project,
            role="manager",
            message_type="normal_update",
            content_markdown=f"Thanks. The manager is proceeding with **{question.selected_text or 'the chosen option'}** and needs one simulated approval to continue.",
            related_agent_id=agent.id if agent else None,
            related_task_id=task.id if task else None,
            metadata_json={"response_mode": "dry_run", "simulated": True},
        )
        approval = self._create_approval(
            db,
            project,
            request_type="command",
            title="Install the local validation package",
            reason_short="The validation agent wants to run a simulated dependency install so the workspace loop can demonstrate approval handling without changing your global environment.",
            risk_level="medium",
            cwd=task and project.workspace_path or project.workspace_path,
            request_payload_json={
                "command": "python -m pip install simulated-package",
                "sandbox_mode": settings.sandbox_mode,
                "approval_policy": settings.approval_policy,
                "simulated": True,
            },
            requesting_agent_id=agent.id if agent else None,
            task_id=task.id if task else None,
        )
        self._record_manager_message(
            db,
            project,
            role="manager",
            message_type="command_approval",
            content_markdown=f"Approval requested: **{approval.title}**",
            related_agent_id=approval.requesting_agent_id,
            related_task_id=approval.task_id,
            metadata_json={"approval_id": approval.id, "simulated": True},
        )

    def _advance_dry_run_after_approval(self, db: Session, project: Project, approval: ApprovalRequest) -> None:
        settings = self._project_settings(db, project)
        if settings.runner_mode != "dry_run":
            return
        agent = db.get(Agent, approval.requesting_agent_id) if approval.requesting_agent_id else None
        task = db.get(Task, approval.task_id) if approval.task_id else None
        if agent:
            if approval.status in {"approved_once", "allowed_for_project"}:
                agent.status = "working"
                agent.current_action = "Simulating the approved command"
                agent.last_report_summary = "Approval recorded. Dry-run is continuing with a simulated step."
            else:
                agent.status = "thinking"
                agent.current_action = "Planning a workaround after the denial"
                agent.last_report_summary = "Approval denied. Dry-run is simulating a safer workaround."
            self.events.publish(db, project.id, "agent_updated", {"agent_id": agent.id, "status": agent.status})
        if task:
            task.status = "working" if approval.status in {"approved_once", "allowed_for_project"} else "blocked"
            task.waiting_reason = None if task.status == "working" else "Simulated approval denial requires a safer path."
            self.events.publish(db, project.id, "task_updated", {"task_id": task.id, "status": task.status})

    def _resolve_question(self, db: Session, question: ManagerQuestion, *, option_id: str, selected_text: str, status: str) -> ManagerQuestion:
        project = db.get(Project, question.project_id)
        if not project:
            raise ValueError("Project not found")
        question.status = status
        question.selected_option_id = option_id
        question.selected_text = selected_text
        question.resolved_at = utc_now()
        self._record_question_resolution_message(db, project, question)
        self.events.publish(db, project.id, "question_resolved", {"question_id": question.id, "status": question.status})
        self._advance_dry_run_after_question(db, project, question)
        self._publish_workspace_state(db, project.id)
        return question

    def _auto_decide_due_questions(self, db: Session, project: Project) -> None:
        pending_questions = list(
            db.scalars(
                select(ManagerQuestion)
                .where(ManagerQuestion.project_id == project.id, ManagerQuestion.status == "pending")
                .order_by(ManagerQuestion.created_at.asc())
            )
        )
        for question in pending_questions:
            auto_decide_at = question.auto_decide_at
            if auto_decide_at is not None and auto_decide_at.tzinfo is None:
                auto_decide_at = auto_decide_at.replace(tzinfo=timezone.utc)
            if question.impact == "high" or auto_decide_at is None or auto_decide_at > utc_now():
                continue
            option = next(
                (
                    item
                    for item in (question.options_json or [])
                    if item.get("label") == question.manager_recommendation or item.get("id") == question.manager_recommendation
                ),
                None,
            )
            if option is None and question.options_json:
                option = question.options_json[0]
            if option is None:
                continue
            self._resolve_question(
                db,
                question,
                option_id=str(option.get("id") or "auto"),
                selected_text=str(option.get("label") or question.manager_recommendation or "Manager default"),
                status="auto_decided",
            )

    async def _workspace_degraded_notices(self, project: Project, settings: ProjectSettings) -> list[str]:
        notices: list[str] = []
        resolved = resolve_manager_settings(project, settings)
        effective_mode = await self.runners.effective_mode(resolved)
        if effective_mode == "unavailable":
            notices.append(f"Runner degraded: {provider_label(settings.provider)} is not currently available in {settings.runner_mode} mode.")
        return notices

    def _derive_current_action(
        self,
        db: Session,
        project: Project,
        degraded_notices: list[str],
        *,
        mutate: bool = True,
    ) -> dict[str, Any]:
        if mutate:
            self._auto_decide_due_questions(db, project)
        pending_approval = db.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.project_id == project.id, ApprovalRequest.status == "pending")
            .order_by(ApprovalRequest.created_at.asc())
        )
        if pending_approval:
            request_label = "tool approval" if pending_approval.request_type != "command" else "command approval"
            return {
                "id": f"approval-{pending_approval.id}",
                "project_id": project.id,
                "type": "tool_approval" if pending_approval.request_type != "command" else "command_approval",
                "severity": "warning",
                "title": f"Action needed: approve {request_label}.",
                "message": pending_approval.reason_short,
                "requesting_agent_id": pending_approval.requesting_agent_id,
                "related_task_id": pending_approval.task_id,
                "command_id": pending_approval.id if pending_approval.request_type == "command" else None,
                "tool_request_id": pending_approval.id if pending_approval.request_type != "command" else None,
                "question_id": None,
                "created_at": pending_approval.created_at,
                "expires_at": None,
                "auto_decide_at": None,
                "resolved_at": None,
                "actions_json": [{"id": "approve_once", "label": "Approve once"}, {"id": "deny", "label": "Deny"}],
            }
        pending_question = db.scalar(
            select(ManagerQuestion)
            .where(ManagerQuestion.project_id == project.id, ManagerQuestion.status == "pending")
            .order_by(ManagerQuestion.created_at.asc())
        )
        if pending_question:
            return {
                "id": f"question-{pending_question.id}",
                "project_id": project.id,
                "type": "manager_question",
                "severity": "warning" if pending_question.impact == "high" else "info",
                "title": "Manager question: choose an option.",
                "message": pending_question.question,
                "requesting_agent_id": pending_question.related_agent_id,
                "related_task_id": pending_question.related_task_id,
                "command_id": None,
                "tool_request_id": None,
                "question_id": pending_question.id,
                "created_at": pending_question.created_at,
                "expires_at": pending_question.auto_decide_at,
                "auto_decide_at": pending_question.auto_decide_at,
                "resolved_at": None,
                "actions_json": list(pending_question.options_json or []),
            }
        if project.status == "paused":
            return {
                "id": f"paused-{project.id}",
                "project_id": project.id,
                "type": "paused",
                "severity": "warning",
                "title": "Project paused.",
                "message": "New work assignment is paused until you resume the project.",
                "requesting_agent_id": None,
                "related_task_id": None,
                "command_id": None,
                "tool_request_id": None,
                "question_id": None,
                "created_at": project.updated_at,
                "expires_at": None,
                "auto_decide_at": None,
                "resolved_at": None,
                "actions_json": [],
            }
        blocked_task = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status.in_(["blocked", "waiting_on_paths"]))
            .order_by(Task.priority.asc(), Task.id.asc())
        )
        if blocked_task:
            return {
                "id": f"task-{blocked_task.id}",
                "project_id": project.id,
                "type": "blocker",
                "severity": "danger",
                "title": "Blocked",
                "message": blocked_task.waiting_reason or f"{blocked_task.title} is blocked.",
                "requesting_agent_id": None,
                "related_task_id": blocked_task.id,
                "command_id": None,
                "tool_request_id": None,
                "question_id": None,
                "created_at": blocked_task.updated_at,
                "expires_at": None,
                "auto_decide_at": None,
                "resolved_at": None,
                "actions_json": [],
            }
        if degraded_notices:
            return {
                "id": f"degraded-{project.id}",
                "project_id": project.id,
                "type": "degraded",
                "severity": "warning",
                "title": degraded_notices[0],
                "message": "Mission Control can still continue in degraded mode.",
                "requesting_agent_id": None,
                "related_task_id": None,
                "command_id": None,
                "tool_request_id": None,
                "question_id": None,
                "created_at": utc_now(),
                "expires_at": None,
                "auto_decide_at": None,
                "resolved_at": None,
                "actions_json": [],
            }
        if project.status == "handoff_ready":
            return {
                "id": f"handoff-{project.id}",
                "project_id": project.id,
                "type": "handoff_ready",
                "severity": "success",
                "title": "Ready for handoff.",
                "message": "The manager considers this project ready for the final handoff.",
                "requesting_agent_id": None,
                "related_task_id": None,
                "command_id": None,
                "tool_request_id": None,
                "question_id": None,
                "created_at": project.updated_at,
                "expires_at": None,
                "auto_decide_at": None,
                "resolved_at": None,
                "actions_json": [],
            }
        working_agents = db.scalar(select(func.count(Agent.id)).where(Agent.project_id == project.id, Agent.kind == "worker", Agent.status.in_(["working", "starting"]))) or 0
        return {
            "id": f"no-action-{project.id}",
            "project_id": project.id,
            "type": "no_action",
            "severity": "info",
            "title": f"No action needed. {working_agents} agents are working." if working_agents else "No action needed.",
            "message": "The manager is monitoring the workspace and will ask if anything needs a decision.",
            "requesting_agent_id": None,
            "related_task_id": None,
            "command_id": None,
            "tool_request_id": None,
            "question_id": None,
            "created_at": project.updated_at,
            "expires_at": None,
            "auto_decide_at": None,
            "resolved_at": None,
            "actions_json": [],
        }

    def _derive_action_history(self, db: Session, project: Project) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        recent_questions = list(
            db.scalars(
                select(ManagerQuestion)
                .where(ManagerQuestion.project_id == project.id, ManagerQuestion.status != "pending")
                .order_by(ManagerQuestion.resolved_at.desc(), ManagerQuestion.id.desc())
            )
        )[:5]
        for question in recent_questions:
            history.append(
                {
                    "id": f"resolved-question-{question.id}",
                    "project_id": project.id,
                    "type": "manager_question",
                    "severity": "info",
                    "title": "Manager question resolved",
                    "message": question.selected_text or question.question,
                    "requesting_agent_id": question.related_agent_id,
                    "related_task_id": question.related_task_id,
                    "command_id": None,
                    "tool_request_id": None,
                    "question_id": question.id,
                    "created_at": question.created_at,
                    "expires_at": question.auto_decide_at,
                    "auto_decide_at": question.auto_decide_at,
                    "resolved_at": question.resolved_at,
                    "actions_json": list(question.options_json or []),
                }
            )
        recent_approvals = list(
            db.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.project_id == project.id, ApprovalRequest.status != "pending")
                .order_by(ApprovalRequest.resolved_at.desc(), ApprovalRequest.id.desc())
            )
        )[:5]
        for approval in recent_approvals:
            history.append(
                {
                    "id": f"resolved-approval-{approval.id}",
                    "project_id": project.id,
                    "type": "tool_approval" if approval.request_type != "command" else "command_approval",
                    "severity": "danger" if approval.status == "denied" else "success",
                    "title": approval.title,
                    "message": approval.reason_short,
                    "requesting_agent_id": approval.requesting_agent_id,
                    "related_task_id": approval.task_id,
                    "command_id": approval.id if approval.request_type == "command" else None,
                    "tool_request_id": approval.id if approval.request_type != "command" else None,
                    "question_id": None,
                    "created_at": approval.created_at,
                    "expires_at": None,
                    "auto_decide_at": None,
                    "resolved_at": approval.resolved_at,
                    "actions_json": [],
                }
            )
        history.sort(key=lambda item: item["resolved_at"] or item["created_at"], reverse=True)
        return history[:8]

    def _manager_queue(self, db: Session, project: Project) -> dict[str, Any]:
        pending_questions = list(
            db.scalars(
                select(ManagerQuestion)
                .where(ManagerQuestion.project_id == project.id, ManagerQuestion.status == "pending")
                .order_by(ManagerQuestion.created_at.asc())
            )
        )
        pending_approvals = list(
            db.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.project_id == project.id, ApprovalRequest.status == "pending")
                .order_by(ApprovalRequest.created_at.asc())
            )
        )
        next_up_tasks = list(
            db.scalars(
                select(Task)
                .where(Task.project_id == project.id, Task.status.in_(["backlog", "assigned", "working"]))
                .order_by(Task.priority.asc(), Task.id.asc())
            )
        )[:4]
        deferred_tasks = list(
            db.scalars(
                select(Task)
                .where(Task.project_id == project.id, Task.status.in_(["blocked", "waiting_on_paths"]))
                .order_by(Task.updated_at.desc(), Task.id.desc())
            )
        )[:4]
        resolved_questions = list(
            db.scalars(
                select(ManagerQuestion)
                .where(ManagerQuestion.project_id == project.id, ManagerQuestion.status != "pending")
                .order_by(ManagerQuestion.resolved_at.desc(), ManagerQuestion.id.desc())
            )
        )[:3]
        resolved_approvals = list(
            db.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.project_id == project.id, ApprovalRequest.status != "pending")
                .order_by(ApprovalRequest.resolved_at.desc(), ApprovalRequest.id.desc())
            )
        )[:3]
        swarm_plan = self._current_swarm_plan_record(db, project.id)
        swarm_specs = self._swarm_specs_for_plan(db, swarm_plan.id) if swarm_plan else []
        recent_swarm_events = (
            list(
                db.scalars(
                    select(SwarmEvent)
                    .where(
                        SwarmEvent.project_id == project.id,
                        SwarmEvent.event_type.in_(
                            [
                                "swarm_plan_approved",
                                "agent_retired",
                                "agent_reassigned",
                                "swarm_scaled_up",
                                "swarm_scaled_down",
                                "strategy_changed",
                            ]
                        ),
                    )
                    .order_by(SwarmEvent.created_at.desc(), SwarmEvent.id.desc())
                )
            )[:3]
            if swarm_plan
            else []
        )
        swarm_next = [
            self._serialize_queue_item(
                item_id=f"swarm-spec-{spec.id}",
                item_type="swarm",
                title=f"Spawn {spec.name}",
                status=spec.status,
                created_at=swarm_plan.created_at if swarm_plan else utc_now(),
            )
            for spec in swarm_specs
            if spec.status == "planned"
        ][:2]
        if swarm_plan and swarm_plan.expected_bottlenecks_json:
            swarm_next.append(
                self._serialize_queue_item(
                    item_id=f"swarm-bottleneck-{swarm_plan.id}",
                    item_type="swarm",
                    title=f"Watch bottleneck: {swarm_plan.expected_bottlenecks_json[0]}",
                    status=swarm_plan.coordination_risk,
                    created_at=swarm_plan.updated_at,
                )
            )
        swarm_deferred = [
            self._serialize_queue_item(
                item_id=f"swarm-spec-{spec.id}",
                item_type="swarm",
                title=(
                    f"Retire {spec.name} when {spec.retire_when}"
                    if spec.status == "retire_pending"
                    else f"Spawn {spec.name} after {spec.spawn_phase.replace('_', ' ')}"
                ),
                status=spec.status,
                created_at=swarm_plan.created_at if swarm_plan else utc_now(),
            )
            for spec in swarm_specs
            if spec.status in {"deferred", "retire_pending"}
        ][:3]
        return {
            "next_up": [
                self._serialize_queue_item(
                    item_id=f"task-{task.id}",
                    item_type="task",
                    title=task.title,
                    status=task.status,
                    created_at=task.created_at,
                    related_task_id=task.id,
                    related_agent_id=task.assigned_agent_id,
                )
                for task in next_up_tasks
            ]
            + swarm_next,
            "waiting_on_user": [
                *[
                    self._serialize_queue_item(
                        item_id=f"question-{question.id}",
                        item_type="question",
                        title=question.question,
                        status=question.status,
                        created_at=question.created_at,
                        related_task_id=question.related_task_id,
                        related_agent_id=question.related_agent_id,
                    )
                    for question in pending_questions
                ],
                *[
                    self._serialize_queue_item(
                        item_id=f"approval-{approval.id}",
                        item_type=approval.request_type,
                        title=approval.title,
                        status=approval.status,
                        created_at=approval.created_at,
                        related_task_id=approval.task_id,
                        related_agent_id=approval.requesting_agent_id,
                    )
                    for approval in pending_approvals
                ],
            ],
            "recently_decided": [
                *[
                    self._serialize_queue_item(
                        item_id=f"question-{question.id}",
                        item_type="question",
                        title=question.selected_text or question.question,
                        status=question.status,
                        created_at=question.resolved_at or question.created_at,
                        related_task_id=question.related_task_id,
                        related_agent_id=question.related_agent_id,
                    )
                    for question in resolved_questions
                ],
                *[
                    self._serialize_queue_item(
                        item_id=f"approval-{approval.id}",
                        item_type=approval.request_type,
                        title=approval.title,
                        status=approval.status,
                        created_at=approval.resolved_at or approval.created_at,
                        related_task_id=approval.task_id,
                        related_agent_id=approval.requesting_agent_id,
                    )
                    for approval in resolved_approvals
                ],
                *[
                    self._serialize_queue_item(
                        item_id=f"swarm-event-{event.id}",
                        item_type="swarm",
                        title=event.message,
                        status=event.event_type,
                        created_at=event.created_at,
                        related_agent_id=event.agent_id,
                    )
                    for event in recent_swarm_events
                ],
            ][:6],
            "deferred": [
                self._serialize_queue_item(
                    item_id=f"task-{task.id}",
                    item_type="task",
                    title=task.title,
                    status=task.status,
                    created_at=task.updated_at,
                    related_task_id=task.id,
                    related_agent_id=task.assigned_agent_id,
                )
                for task in deferred_tasks
            ]
            + swarm_deferred,
        }

    def _task_summary(self, db: Session, project: Project) -> dict[str, Any]:
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id)))
        by_status: dict[str, int] = {}
        for task in tasks:
            by_status[task.status] = by_status.get(task.status, 0) + 1
        return {"total": len(tasks), "by_status": by_status}

    def _milestone_summary(self, db: Session, project: Project) -> dict[str, Any]:
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        milestones: dict[str, dict[str, int | str]] = {}
        for task in tasks:
            key = task.milestone or "Unassigned milestone"
            milestone = milestones.setdefault(key, {"title": key, "total": 0, "done": 0})
            milestone["total"] = int(milestone["total"]) + 1
            if task.status == "done":
                milestone["done"] = int(milestone["done"]) + 1
        return {"items": list(milestones.values())}

    def _workflow_summary(self, db: Session, project: Project, tasks: list[Task]) -> dict[str, Any]:
        latest_session = self._latest_session(db, project.id)
        latest_plan = self._latest_plan(db, project.id)
        current_phase = "intake"
        if project.final_report_json or project.status == "handoff_ready":
            current_phase = "handoff"
        elif any(task.status == "needs_review" for task in tasks):
            current_phase = "validation"
        elif tasks or project.status in {"building", "blocked", "paused"}:
            current_phase = "build"
        elif latest_plan or project.status in {"plan_ready", "pending_approval"}:
            current_phase = "plan_review"
        elif latest_session or project.status in {"interview_in_progress", "interview_complete"}:
            current_phase = "interview"

        if project.status == "paused" and current_phase not in {"handoff", "validation"}:
            current_phase = "build"

        steps: list[dict[str, Any]] = []
        current_index = next((index for index, (phase_id, _) in enumerate(WORKFLOW_PHASES) if phase_id == current_phase), 0)
        for index, (phase_id, label) in enumerate(WORKFLOW_PHASES):
            state = "upcoming"
            if index < current_index:
                state = "complete"
            elif index == current_index:
                state = "current"
            steps.append({"id": phase_id, "label": label, "state": state, "ordinal": index + 1})
        current_label = next((label for phase_id, label in WORKFLOW_PHASES if phase_id == current_phase), "Intake")
        return {"current_phase": current_phase, "current_label": current_label, "steps": steps}

    def _tasks_for_category(self, tasks: list[Task], category_id: str) -> list[Task]:
        keyword_sets = {
            "frontend": ["frontend", "ui", "react", "component", "layout", "dashboard", "css", "screen", "view"],
            "backend": ["backend", "api", "service", "server", "database", "middleware", "route", "schema", "fastapi"],
            "auth_security": ["auth", "security", "token", "permission", "sandbox", "approval", "credential", "oauth", "login"],
            "testing": ["test", "testing", "validate", "validation", "qa", "review", "smoke", "check"],
            "documentation": ["doc", "docs", "readme", "handoff", "guide", "instruction", "changelog", "note"],
        }
        if category_id == "architecture":
            return [task for task in tasks if (task.milestone or "").lower().startswith("milestone")]
        keywords = keyword_sets.get(category_id, [])
        matched: list[Task] = []
        for task in tasks:
            haystack = " ".join(
                filter(
                    None,
                    [
                        task.title,
                        task.goal,
                        task.scope,
                        task.agent_role or "",
                        task.milestone or "",
                    ],
                )
            ).lower()
            if any(keyword in haystack for keyword in keywords):
                matched.append(task)
        return matched

    @staticmethod
    def _overview_status(tasks: list[Task]) -> str:
        if not tasks:
            return "planned"
        statuses = {task.status for task in tasks}
        if statuses == {"done"}:
            return "complete"
        if "blocked" in statuses:
            return "blocked"
        return "in_progress"

    def _project_overview(self, db: Session, project: Project, tasks: list[Task], current_action: dict[str, Any]) -> dict[str, Any]:
        latest_plan = self._latest_plan(db, project.id)
        checklist: list[dict[str, Any]] = []
        for category_id, label in OVERVIEW_SECTIONS:
            category_tasks = self._tasks_for_category(tasks, category_id)
            if category_id == "architecture" and latest_plan and not category_tasks:
                status = "complete"
                detail = "Plan approved and architecture direction captured."
            else:
                status = self._overview_status(category_tasks)
                if not category_tasks:
                    detail = "Not explicitly tracked yet."
                elif status == "complete":
                    detail = f"{len(category_tasks)} tracked task{'s' if len(category_tasks) != 1 else ''} complete."
                elif status == "blocked":
                    detail = f"{len(category_tasks)} tracked task{'s' if len(category_tasks) != 1 else ''} blocked or waiting."
                else:
                    done_count = len([task for task in category_tasks if task.status == "done"])
                    detail = f"{done_count} of {len(category_tasks)} tracked task{'s' if len(category_tasks) != 1 else ''} complete."
            checklist.append({"id": category_id, "label": label, "status": status, "detail": detail})

        score = 0.0
        for item in checklist:
            if item["status"] == "complete":
                score += 1.0
            elif item["status"] == "in_progress":
                score += 0.5
        handoff_progress = int(round((score / max(len(checklist), 1)) * 100))

        readiness_label = "Not Ready"
        readiness_tone = "neutral"
        if current_action["type"] in {"blocker", "error"}:
            readiness_label = "Blocked"
            readiness_tone = "danger"
        elif current_action["type"] in {"command_approval", "tool_approval", "manager_question", "paused"}:
            readiness_label = "Needs Review"
            readiness_tone = "warning"
        elif project.final_report_json or project.status == "handoff_ready":
            readiness_label = "Ready"
            readiness_tone = "good"
        elif handoff_progress >= 70:
            readiness_label = "Good"
            readiness_tone = "good"
        elif handoff_progress >= 35:
            readiness_label = "In Progress"
            readiness_tone = "warning"

        return {
            "handoff_progress": handoff_progress,
            "readiness_label": readiness_label,
            "readiness_tone": readiness_tone,
            "checklist": checklist,
        }

    def _serialize_activity_log_entry(self, db: Session, project: Project, event: ProjectEvent) -> dict[str, Any]:
        payload = dict(event.payload_json or {})
        agent_id = payload.get("agent_id")
        task_id = payload.get("task_id")
        severity = "info"
        summary = event.event_type.replace(".", " ").replace("_", " ").title()
        detail: str | None = None

        agent = db.get(Agent, agent_id) if isinstance(agent_id, int) else None
        task = db.get(Task, task_id) if isinstance(task_id, int) else None

        if event.event_type == "approval_created":
            severity = "warning"
            approval = db.get(ApprovalRequest, payload.get("approval_id")) if isinstance(payload.get("approval_id"), int) else None
            summary = f"Approval requested: {approval.title if approval else 'pending request'}"
            detail = approval.reason_short if approval else None
            if approval and approval.requesting_agent_id and not agent:
                agent = db.get(Agent, approval.requesting_agent_id)
            if approval and approval.task_id and not task:
                task = db.get(Task, approval.task_id)
        elif event.event_type == "approval_resolved":
            approval = db.get(ApprovalRequest, payload.get("approval_id")) if isinstance(payload.get("approval_id"), int) else None
            severity = "success" if payload.get("status") in {"approved_once", "allowed_for_project"} else "danger"
            status_label = str(payload.get("status") or "resolved").replace("_", " ")
            summary = f"Approval {status_label}"
            detail = approval.title if approval else None
            if approval and approval.requesting_agent_id and not agent:
                agent = db.get(Agent, approval.requesting_agent_id)
            if approval and approval.task_id and not task:
                task = db.get(Task, approval.task_id)
        elif event.event_type == "question_created":
            question = db.get(ManagerQuestion, payload.get("question_id")) if isinstance(payload.get("question_id"), int) else None
            severity = "warning" if payload.get("impact") == "high" else "info"
            summary = "Manager question queued"
            detail = question.question if question else None
            if question and question.related_agent_id and not agent:
                agent = db.get(Agent, question.related_agent_id)
            if question and question.related_task_id and not task:
                task = db.get(Task, question.related_task_id)
        elif event.event_type == "question_resolved":
            question = db.get(ManagerQuestion, payload.get("question_id")) if isinstance(payload.get("question_id"), int) else None
            severity = "success"
            summary = "Manager question resolved"
            detail = question.selected_text if question and question.selected_text else question.question if question else None
            if question and question.related_agent_id and not agent:
                agent = db.get(Agent, question.related_agent_id)
            if question and question.related_task_id and not task:
                task = db.get(Task, question.related_task_id)
        elif event.event_type == "agent_updated":
            severity = "danger" if payload.get("status") == "blocked" else "info"
            summary = f"{agent.name if agent else 'Agent'} status updated"
            next_status = payload.get("status") or (agent.status if agent else "updated")
            detail = str(next_status).replace("_", " ").title()
        elif event.event_type == "task_updated":
            severity = "danger" if payload.get("status") == "blocked" else "info"
            summary = f"Task updated: {task.title if task else 'Task'}"
            detail = str(payload.get("status") or task.status if task else "updated").replace("_", " ").title()
        elif event.event_type == "manager_queue_updated":
            summary = "Manager queue updated"
            detail = "Routing priorities changed."
        elif event.event_type == "manager_message_created":
            message = db.get(ManagerMessage, payload.get("message_id")) if isinstance(payload.get("message_id"), int) else None
            summary = f"Manager {str(payload.get('message_type') or 'message').replace('_', ' ')}"
            detail = message.content_markdown.splitlines()[0][:180] if message and message.content_markdown else None
            if message and message.related_agent_id and not agent:
                agent = db.get(Agent, message.related_agent_id)
            if message and message.related_task_id and not task:
                task = db.get(Task, message.related_task_id)
        elif event.event_type == "worker.report.received":
            severity = "danger" if payload.get("status") in {"blocked", "error"} else "success"
            summary = f"{agent.name if agent else 'Worker'} reported {str(payload.get('status') or 'status').replace('_', ' ')}"
            detail = str(payload.get("summary") or "")[:180] or None
        elif event.event_type == "project.handoff_ready":
            severity = "success"
            summary = "Project ready for handoff"
            detail = "Validation and documentation are in a handoff-ready state."
        elif event.event_type == "project.paused":
            severity = "warning"
            summary = "Project paused"
            detail = "New task assignment is paused until the project is resumed."
        elif event.event_type == "project.resumed":
            severity = "success"
            summary = "Project resumed"
            detail = "The manager can assign new work again."
        elif event.event_type == "agent.started":
            agent_label = payload.get("agent_name") or (agent.name if agent else "Agent")
            summary = f"{agent_label} started work"
            detail = str(payload.get("task_title") or (task.title if task else "Task assigned"))

        return {
            "id": event.id,
            "event_type": event.event_type,
            "created_at": event.created_at,
            "summary": summary,
            "detail": detail,
            "severity": severity,
            "agent_id": agent.id if agent else None,
            "agent_name": agent.name if agent else None,
            "task_id": task.id if task else None,
        }

    def _activity_log(self, db: Session, project: Project) -> list[dict[str, Any]]:
        events = list(
            db.scalars(
                select(ProjectEvent)
                .where(ProjectEvent.project_id == project.id)
                .order_by(ProjectEvent.id.desc())
            )
        )[:12]
        return [self._serialize_activity_log_entry(db, project, event) for event in events]

    @staticmethod
    def _runner_settings_payload(resolved: ResolvedRunSettings) -> RunnerSettings:
        return RunnerSettings(
            provider=resolved.provider,
            sandbox_mode=resolved.sandbox_mode,
            approval_policy=resolved.approval_policy,
            model=resolved.model,
            reasoning_effort=resolved.reasoning_effort,
            provider_endpoint=resolved.provider_endpoint,
            adapter_command=resolved.adapter_command,
            adapter_args=list(resolved.adapter_args),
        )

    @staticmethod
    def _cache_agent_run_profile(agent: Agent, resolved: ResolvedRunSettings, *, runner_type: str, action: str) -> None:
        agent.active_model = resolved.effective_model_label
        agent.active_reasoning_effort = resolved.effective_reasoning_label
        agent.active_runner_type = runner_type
        agent.current_action = action

    def _task_board_markdown(self, tasks: list[Task]) -> str:
        grouped: dict[str, list[str]] = {}
        for task in sorted(tasks, key=lambda item: (item.priority, item.id)):
            grouped.setdefault(task.status, []).append(f"- #{task.id} {task.title}")
        sections = ["# Task Board", ""]
        for status, items in grouped.items():
            sections.append(f"## {status.replace('_', ' ').title()}")
            sections.extend(items or ["- None"])
            sections.append("")
        return "\n".join(sections).strip() + "\n"

    def _render_docs(self, project: Project, plan: ManagerPlan | None = None, questions: list[InterviewQuestion] | None = None) -> dict[str, str]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        answers = [self._question_answer_text(question) for question in questions or [] if self._question_answer_text(question)]
        answer_preview = ", ".join(answers[:6]) or "Interview still pending."
        summary = plan.refined_summary if plan else project.idea
        scope = plan.mvp_scope if plan else ["Keep the first version local, usable, and tightly scoped."]
        milestones = plan.milestones if plan else ["Clarify the slice", "Build the vertical slice", "Validate and hand off"]
        risks = plan.risks if plan else ["Local tooling assumptions may change.", "Scope can drift if the first slice stays vague."]
        definitions = plan.definition_of_done if plan else ["The main workflow works locally.", "Known limitations are documented."]
        return {
            "PROJECT_BRIEF.md": f"# {project.name}\n\n## Idea\n{project.idea}\n\n## Created by\n{project.created_by or display_name_or_default(None)}\n\n## Refined summary\n{summary}\n\n## Generated\n{now}\n",
            "PRODUCT_VISION.md": "# Product Vision\n\n" + "\n".join(f"- {line}" for line in scope) + "\n",
            "USER_GOALS.md": f"# User Goals\n\n- Interview signals: {answer_preview}\n- Land a usable vertical slice quickly.\n- Keep the workflow trustworthy.\n",
            "MVP_SCOPE.md": "# MVP Scope\n\n" + "\n".join(f"- {line}" for line in scope) + "\n",
            "ARCHITECTURE_NOTES.md": "# Architecture Notes\n\n" + "\n".join(f"- {line}" for line in (plan.recommended_architecture if plan else ["Keep the app local-first.", "Separate manager logic from worker execution."])) + "\n",
            "RISKS_AND_UNKNOWNS.md": "# Risks and Unknowns\n\n" + "\n".join(f"- {line}" for line in risks) + "\n",
            "AGENT_PLAN.md": "# Agent Plan\n\n" + "\n".join(f"- {line}" for line in milestones) + "\n",
            "TASK_BOARD.md": "# Task Board\n\n- Task generation happens after plan approval.\n- Path ownership prevents overlapping edits.\n- Validation and handoff tasks stay explicit.\n",
        }

    def _deterministic_doc_update(self, project: Project, questions: list[InterviewQuestion], plan: ManagerPlan | None) -> ManagerDocUpdate:
        files = [
            ManagerDocFile(filename=filename, content=content)
            for filename, content in self._render_docs(project, plan=plan, questions=questions).items()
        ]
        return ManagerDocUpdate(
            summary_markdown=f"Generated {len(files)} planning docs for **{project.name}** with the latest project summary and scope.",
            files=files,
        )

    def _interview_remaining_budget(self, session: InterviewSession) -> int:
        return max(session.question_budget - session.questions_asked, 0)

    def _interview_source_for_mode(self, mode_used: str) -> str:
        return "manager_ai" if mode_used != "deterministic" else "fallback_generated"

    def _used_interview_categories(self, session: InterviewSession) -> set[str]:
        return {
            str(question.category).strip()
            for question in session.questions
            if question.category and (question.status == "pending" or question.selected_option_id or question.selected_option)
        }

    def _pending_interview_categories(self, session: InterviewSession) -> set[str]:
        return {
            str(question.category).strip()
            for question in self._pending_interview_questions(session)
            if question.category
        }

    def _default_interview_turn(self, project: Project, session: InterviewSession) -> InterviewTurnPayload:
        remaining_budget = self._interview_remaining_budget(session)
        understanding = self._default_understanding_payload(project, question_budget=session.question_budget)
        if session.question_budget == 0:
            understanding.summary = f"The manager will proceed with assumptions for {project.name} because the interview budget is zero."
            return InterviewTurnPayload(
                understanding=understanding,
                next_questions=[],
                more_questions_needed=False,
                stop_reason="Manager assumptions mode requested.",
            )

        asked_categories = self._used_interview_categories(session)
        pending_categories = self._pending_interview_categories(session)
        questions = select_fallback_questions(remaining_budget, asked_categories=asked_categories, pending_categories=pending_categories)
        understanding.summary = f"The deterministic interview fallback is collecting core project decisions for {project.name}."
        understanding.unknowns = {
            "priority": ["The manager fallback is covering generic requirement gaps until enough project signal exists."]
        }
        return InterviewTurnPayload(
            understanding=understanding,
            next_questions=[InterviewTurnQuestion(**question) for question in questions],
            more_questions_needed=remaining_budget > len(questions) and bool(questions),
            stop_reason=None if questions else "The fallback interview exhausted its generic category bank.",
        )

    def _normalize_interview_questions(self, session: InterviewSession, questions: list[InterviewTurnQuestion], *, allow_repeated_categories: bool = False) -> list[InterviewTurnQuestion]:
        normalized: list[InterviewTurnQuestion] = []
        seen_texts = {
            re.sub(r"\s+", " ", question.question.strip().lower())
            for question in session.questions
            if question.question and (question.status in {"pending", "answered"} or question.selected_option_id or question.selected_option)
        }
        used_categories = self._used_interview_categories(session)
        unused_categories_exist = len(INTERVIEW_CATEGORY_SET.difference(used_categories)) > 0

        for question in questions:
            question_text = re.sub(r"\s+", " ", question.question.strip())
            category = question.category.strip()
            if not question_text or category not in INTERVIEW_CATEGORY_SET:
                continue
            normalized_text = question_text.lower()
            if normalized_text in seen_texts:
                continue
            if question.impact not in {"low", "medium", "high"}:
                continue
            if len(question.options) < 2 or len(question.options) > 10:
                continue
            option_ids: set[str] = set()
            valid_options: list[dict[str, str]] = []
            for option in question.options:
                option_id = str(option.get("id") or "").strip()
                label = str(option.get("label") or "").strip()
                description = str(option.get("description") or "").strip()
                if not option_id or not label or option_id in option_ids:
                    continue
                option_ids.add(option_id)
                valid_options.append({"id": option_id, "label": label, "description": description})
            if len(valid_options) < 2:
                continue
            if not allow_repeated_categories and category in used_categories and unused_categories_exist:
                continue
            normalized.append(
                InterviewTurnQuestion(
                    question=question_text,
                    why=question.why.strip() or "The manager needs this answer to reduce planning uncertainty.",
                    category=category,
                    impact=question.impact,
                    options=valid_options,
                    allow_custom_answer=bool(question.allow_custom_answer),
                    affects=[item.strip() for item in question.affects if item and item.strip()],
                )
            )
            seen_texts.add(normalized_text)
            used_categories.add(category)
            if len(normalized) >= max(1, min(5, self._interview_remaining_budget(session))):
                break
        return normalized

    def _record_interview_questions(
        self,
        db: Session,
        session: InterviewSession,
        questions: list[InterviewTurnQuestion],
        *,
        question_source: str,
    ) -> int:
        next_index = (max((question.index for question in session.questions), default=-1) + 1)
        created = 0
        for offset, template in enumerate(questions):
            db.add(
                InterviewQuestion(
                    session_id=session.id,
                    project_id=session.project_id,
                    index=next_index + offset,
                    question=template.question,
                    why=template.why,
                    category=template.category,
                    impact=template.impact,
                    options_json=template.options,
                    allow_custom_answer=template.allow_custom_answer,
                    affects_json=template.affects,
                    status="pending",
                    question_source=question_source,
                )
            )
            created += 1
        session.questions_asked += created
        session.question_count = session.question_budget
        db.flush()
        db.expire(session, ["questions"])
        return created

    def _complete_interview_session(
        self,
        db: Session,
        session: InterviewSession,
        project: Project,
        *,
        stop_reason: str,
        stopped_early: bool,
    ) -> InterviewSession:
        session.status = "completed"
        session.stop_reason = stop_reason
        session.stopped_early = stopped_early
        project.status = "interview_complete"
        self.events.publish(
            db,
            project.id,
            "interview.finished",
            {
                "session_id": session.id,
                "stop_reason": stop_reason,
                "stopped_early": stopped_early,
                "questions_asked": session.questions_asked,
                "question_budget": session.question_budget,
            },
        )
        if stopped_early:
            self.events.publish(db, project.id, "interview.stopped_early", {"session_id": session.id, "stop_reason": stop_reason})
        self._resolve_interview_question_mirrors(
            db,
            project,
            session,
            reason="Interview completed and no pending intake question remains.",
        )
        return session

    def _apply_interview_turn(
        self,
        db: Session,
        project: Project,
        session: InterviewSession,
        turn: InterviewTurnPayload,
        *,
        question_source: str,
    ) -> InterviewSession:
        understanding = self._update_project_understanding(db, project, turn.understanding)
        self._mirror_session_understanding(session, understanding)
        normalized_questions = self._normalize_interview_questions(session, turn.next_questions)
        created_count = self._record_interview_questions(db, session, normalized_questions, question_source=question_source) if normalized_questions else 0
        self._refresh_interview_session_state(session, project=project)
        self._sync_interview_question_mirror(db, project, session)
        self.events.publish(
            db,
            project.id,
            "interview.batch_generated",
            {
                "session_id": session.id,
                "question_source": question_source,
                "created_count": created_count,
                "questions_asked": session.questions_asked,
                "question_budget": session.question_budget,
            },
        )
        if question_source == "fallback_generated":
            self.events.publish(
                db,
                project.id,
                "interview.fallback_used",
                {"session_id": session.id, "questions_created": created_count, "reason": "deterministic generation path used"},
            )

        remaining_budget = self._interview_remaining_budget(session)
        if session.question_budget == 0:
            return self._complete_interview_session(
                db,
                session,
                project,
                stop_reason=turn.stop_reason or "Manager assumptions mode requested.",
                stopped_early=False,
            )
        if created_count == 0 and (not turn.more_questions_needed or remaining_budget > 0):
            return self._complete_interview_session(
                db,
                session,
                project,
                stop_reason=turn.stop_reason or "The manager could not identify additional useful interview questions.",
                stopped_early=remaining_budget > 0,
            )
        if remaining_budget <= 0 and not self._pending_interview_questions(session):
            return self._complete_interview_session(
                db,
                session,
                project,
                stop_reason=turn.stop_reason or "Question budget reached.",
                stopped_early=False,
            )
        if not turn.more_questions_needed and not self._pending_interview_questions(session):
            return self._complete_interview_session(
                db,
                session,
                project,
                stop_reason=turn.stop_reason or "The manager has enough information to plan the project.",
                stopped_early=remaining_budget > 0,
            )
        session.stop_reason = turn.stop_reason
        return session

    def _deterministic_plan(
        self,
        db: Session,
        project: Project,
        questions: list[InterviewQuestion],
        understanding: ProjectUnderstanding | None,
        action_bias: str | None = None,
        note: str | None = None,
    ) -> ManagerPlan:
        content_markdown, summary_json = build_plan_markdown(project, questions, understanding=understanding, action_bias=action_bias, note=note)
        intelligence = planning_intelligence_service.build_context(db, project)
        playbook = intelligence.get("playbook") or {}
        preferences = intelligence.get("preferences") or []
        coverage = intelligence.get("validation_coverage") or []
        open_risks = intelligence.get("open_risks") or []
        coverage_gaps = [item["area"] for item in coverage if item.get("coverage_status") in {"none", "failed"}]
        if playbook.get("key"):
            content_markdown += (
                "\n## Intelligence Layer Inputs\n"
                f"- Suggested playbook: {playbook.get('key')} ({playbook.get('status')})\n"
                f"- Why: {playbook.get('why')}\n"
            )
        if preferences:
            content_markdown += "\n### Active Preferences\n" + "\n".join(
                f"- {item.get('key')}: {item.get('value_json')}" for item in preferences[:6]
            )
            content_markdown += "\n"
        if coverage_gaps:
            content_markdown += "\n### Validation Gaps\n" + "\n".join(f"- {gap}" for gap in coverage_gaps[:5]) + "\n"
        summary_json["intelligence"] = intelligence
        if coverage_gaps:
            summary_json["validation_plan"] = list(summary_json["validation_plan"]) + [f"Close validation gap for {gap}." for gap in coverage_gaps[:3]]
        if open_risks:
            summary_json["risks"] = list(dict.fromkeys(list(summary_json["risks"]) + [item["title"] for item in open_risks[:3]]))
        return ManagerPlan(
            refined_summary=summary_json["refined_summary"],
            mvp_scope=summary_json["mvp_scope"],
            milestones=summary_json["milestones"],
            recommended_architecture=summary_json["recommended_architecture"],
            agent_roster=summary_json["agent_roster"],
            task_breakdown=summary_json["task_breakdown"],
            validation_plan=summary_json["validation_plan"],
            risks=summary_json["risks"],
            definition_of_done=summary_json["definition_of_done"],
            content_markdown=content_markdown,
            summary_json=summary_json,
        )

    def _default_swarm_paths_for_archetype(self, archetype: str, buckets: dict[str, list[str]]) -> tuple[list[str], list[str]]:
        if archetype == "docs" or archetype == "release_handoff":
            return buckets["docs"], buckets["frontend"] + buckets["backend"]
        if archetype == "frontend" or archetype == "ui_polish":
            return buckets["frontend"] or ["src"], buckets["backend"]
        if archetype == "backend":
            return buckets["backend"] or ["server"], buckets["frontend"]
        if archetype == "test":
            return buckets["tests"] + buckets["backend"], []
        if archetype == "security":
            return buckets["backend"] + buckets["data"], []
        if archetype == "research" or archetype == "planner" or archetype == "architect":
            return buckets["docs"] + buckets["subsystems"][:2], []
        if archetype == "ops":
            return buckets["ops"] + buckets["docs"], buckets["frontend"]
        if archetype == "data":
            return buckets["data"] or buckets["backend"], []
        if archetype == "integration":
            return buckets["frontend"] + buckets["backend"], buckets["docs"]
        return (buckets["frontend"] + buckets["backend"]) or buckets["subsystems"], buckets["docs"]

    def _sanitize_swarm_plan_payload(
        self,
        project: Project,
        preferences: SwarmPreferences,
        manifest: dict[str, Any],
        payload: ManagerSwarmPlanPayload,
        fallback_payload: ManagerSwarmPlanPayload,
    ) -> ManagerSwarmPlanPayload:
        buckets = self._repo_path_buckets(manifest)
        valid_archetypes = {item["name"] for item in AGENT_ARCHETYPE_CATALOG}
        mode = payload.mode if payload.mode in {
            "fastest_build",
            "balanced",
            "high_quality",
            "documentation_heavy",
            "research_planning",
            "massive_codebase",
            "manager_decides",
        } else fallback_payload.mode
        coordination_risk = payload.coordination_risk if payload.coordination_risk in SWARM_RISK_LEVELS else fallback_payload.coordination_risk
        path_conflict_risk = payload.path_conflict_risk if payload.path_conflict_risk in SWARM_RISK_LEVELS else fallback_payload.path_conflict_risk
        capacity = self._swarm_capacity_limit(preferences)
        seen_names: set[str] = set()
        specs: list[ManagerSwarmSpecPayload] = []
        raw_specs = payload.specs or fallback_payload.specs
        for index, spec in enumerate(raw_specs, start=1):
            archetype = spec.archetype if spec.archetype in valid_archetypes else "feature"
            name = spec.name.strip() if spec.name.strip() else f"{self._titleize_path_label(archetype)} Agent"
            unique_name = name
            suffix = 2
            while unique_name.lower() in seen_names:
                unique_name = f"{name} {suffix}"
                suffix += 1
            seen_names.add(unique_name.lower())
            allowed_paths = self._normalize_string_list(spec.allowed_paths) or self._default_swarm_paths_for_archetype(archetype, buckets)[0]
            forbidden_paths = self._normalize_string_list(spec.forbidden_paths) or self._default_swarm_paths_for_archetype(archetype, buckets)[1]
            specs.append(
                self._make_swarm_spec(
                    archetype=archetype,
                    name=unique_name,
                    mission=spec.mission.strip() if spec.mission.strip() else f"Own the {archetype} slice for {project.name}.",
                    model_policy=spec.model_policy.strip() if spec.model_policy.strip() else "Prefer the default worker model.",
                    allowed_paths=allowed_paths,
                    forbidden_paths=forbidden_paths,
                    spawn_phase=spec.spawn_phase.strip() if spec.spawn_phase.strip() else "build_start",
                    retire_when=spec.retire_when.strip() if spec.retire_when.strip() else "Retire when the assigned slice is complete.",
                    priority=max(1, min(100, int(spec.priority or index * 10))),
                    toolset=self._normalize_string_list(spec.toolset),
                )
            )
            if len(specs) >= capacity:
                break
        if not specs:
            specs = fallback_payload.specs[:capacity]
        recommended = max(1, min(capacity, payload.recommended_agent_count if payload.recommended_agent_count else len(specs)))
        return ManagerSwarmPlanPayload(
            mode=mode,
            goal=payload.goal.strip() if payload.goal.strip() else fallback_payload.goal,
            recommended_agent_count=recommended,
            coordination_risk=coordination_risk,
            path_conflict_risk=path_conflict_risk,
            expected_bottlenecks=self._normalize_string_list(payload.expected_bottlenecks) or fallback_payload.expected_bottlenecks,
            strategy_summary=payload.strategy_summary.strip() if payload.strategy_summary.strip() else fallback_payload.strategy_summary,
            validation_strategy=self._normalize_string_list(payload.validation_strategy) or fallback_payload.validation_strategy,
            specs=sorted(specs[:capacity], key=lambda item: item.priority),
        )

    def _persist_swarm_plan_payload(
        self,
        db: Session,
        project: Project,
        preferences: SwarmPreferences,
        payload: ManagerSwarmPlanPayload,
        *,
        milestone_id: int | None = None,
        approved_by_user: bool = False,
        status: str = "pending_approval",
    ) -> SwarmPlan:
        current = self._current_swarm_plan_record(db, project.id)
        if current is not None:
            current.status = "superseded"
        plan = SwarmPlan(
            project_id=project.id,
            milestone_id=milestone_id,
            mode=payload.mode,
            goal=payload.goal,
            recommended_agent_count=min(self._swarm_capacity_limit(preferences), payload.recommended_agent_count),
            max_agent_count=preferences.max_agents,
            coordination_risk=payload.coordination_risk,
            path_conflict_risk=payload.path_conflict_risk,
            expected_bottlenecks_json=list(payload.expected_bottlenecks),
            validation_strategy_json=list(payload.validation_strategy),
            strategy_summary=payload.strategy_summary,
            approved_by_user=approved_by_user,
            status=status,
        )
        db.add(plan)
        db.flush()
        self._record_swarm_event(
            db,
            project,
            event_type="swarm_plan_created",
            message=f"Swarm plan created in {payload.mode} mode with {plan.recommended_agent_count} recommended worker agents.",
            swarm_plan_id=plan.id,
            metadata_json={"mode": payload.mode, "recommended_agent_count": plan.recommended_agent_count},
        )
        for spec in payload.specs[: preferences.max_agents]:
            spec_status = "deferred" if "after_" in spec.spawn_phase else "planned"
            record = SwarmAgentSpec(
                swarm_plan_id=plan.id,
                project_id=project.id,
                archetype=spec.archetype,
                name=spec.name,
                mission=spec.mission,
                model_policy=spec.model_policy,
                toolset_json=list(spec.toolset),
                allowed_paths_json=list(spec.allowed_paths),
                forbidden_paths_json=list(spec.forbidden_paths),
                spawn_phase=spec.spawn_phase,
                retire_when=spec.retire_when,
                priority=spec.priority,
                status=spec_status,
            )
            db.add(record)
            db.flush()
            self._record_swarm_event(
                db,
                project,
                event_type="agent_spec_created",
                message=f"{record.name} planned as a {record.archetype} specialist.",
                swarm_plan_id=plan.id,
                metadata_json={"spec_id": record.id, "archetype": record.archetype, "spawn_phase": record.spawn_phase},
            )
        db.flush()
        return plan

    async def create_swarm_plan(
        self,
        db: Session,
        project: Project,
        *,
        goal: str | None = None,
        milestone_id: int | None = None,
        revision_note: str | None = None,
        scale_hint: str | None = None,
    ) -> dict[str, Any]:
        preferences = self._ensure_swarm_preferences(db, project)
        self._ensure_agent_archetypes(db)
        latest_plan = self._latest_plan(db, project.id)
        understanding = self._project_understanding(project)
        manifest = self._workspace_manifest_summary(project)
        intelligence_context = planning_intelligence_service.build_context(db, project)
        intelligence_context["model_policy_hints"] = {
            category: planning_intelligence_service.recommend_model_policy(db, category)
            for category in CAPABILITY_CATEGORIES
        }
        fallback_payload = self._deterministic_swarm_plan(
            project,
            preferences,
            manifest,
            understanding,
            latest_plan,
            intelligence_context=intelligence_context,
            goal_override=goal,
            scale_hint=scale_hint,
        )
        context = await self._swarm_context_payload(db, project, preferences)
        context["intelligence_layer"] = intelligence_context
        if revision_note:
            context["revision_note"] = revision_note
        if scale_hint:
            context["scale_hint"] = scale_hint
        swarm_settings = resolve_manager_settings(project, self._project_settings(db, project))
        payload, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="swarm.plan",
            objective="Design an adaptive swarm plan that fits the project instead of copying a fixed worker roster.",
            response_schema=MANAGER_SWARM_PLAN_SCHEMA,
            payload=context,
            model_schema=ManagerSwarmPlanPayload,
            fallback_factory=lambda: fallback_payload,
            prompt_override=manager_swarm_prompt(
                project,
                payload=context,
                response_schema=MANAGER_SWARM_PLAN_SCHEMA,
                user_name=self._preferred_user_name(db, project),
                provider=swarm_settings.provider,
                model=swarm_settings.effective_model_label,
                reasoning_effort=swarm_settings.effective_reasoning_label,
            ),
        )
        sanitized = self._sanitize_swarm_plan_payload(project, preferences, manifest, payload, fallback_payload)
        approval_required = sanitized.recommended_agent_count > preferences.require_approval_above_agent_count
        plan = self._persist_swarm_plan_payload(
            db,
            project,
            preferences,
            sanitized,
            milestone_id=milestone_id,
            approved_by_user=False,
            status="pending_approval" if approval_required else "approved",
        )
        if not approval_required:
            plan.approved_by_user = True
        self._record_swarm_event(
            db,
            project,
            event_type="strategy_changed" if revision_note or scale_hint else "swarm_plan_created",
            message=sanitized.strategy_summary,
            swarm_plan_id=plan.id,
            metadata_json={"manager_mode_used": manager_mode_used, "revision_note": revision_note, "scale_hint": scale_hint},
        )
        simulation = simulation_service.simulate_launch(db, project, plan)
        if simulation.conflict_warnings_json or simulation.bottlenecks_json:
            risk_service.create_risk(
                db,
                project,
                {
                    "title": "Swarm launch coordination risk",
                    "description": "Launch simulation found conflicts or bottlenecks that could waste swarm effort.",
                    "severity": "high" if simulation.should_wait_count or simulation.conflict_warnings_json else "medium",
                    "likelihood": "medium",
                    "mitigation": "Review the Agent Launch Simulation widget before broad spawn.",
                    "status": "monitoring",
                    "created_by": "system",
                },
            )
        if simulation.should_wait_count > 0 or simulation.needs_user_approval_count > 0:
            existing_launch_question = db.scalar(
                select(ManagerQuestion)
                .where(ManagerQuestion.project_id == project.id, ManagerQuestion.status == "pending")
                .order_by(ManagerQuestion.id.desc())
            )
            if existing_launch_question is None or not (
                existing_launch_question.metadata_json
                and existing_launch_question.metadata_json.get("question_type") == "launch_simulation"
                and existing_launch_question.metadata_json.get("swarm_plan_id") == plan.id
            ):
                self._create_question(
                    db,
                    project,
                    question="Launch simulation found concerns. Revise swarm, wait, or launch anyway?",
                    options_json=[
                        {"id": "revise", "label": "Revise swarm"},
                        {"id": "wait", "label": "Wait"},
                        {"id": "launch_anyway", "label": "Launch anyway"},
                    ],
                    impact="high",
                    manager_recommendation="revise",
                    metadata_json={"question_type": "launch_simulation", "swarm_plan_id": plan.id},
                )
        return self._serialize_swarm_plan(db, project, plan) or {}

    def approve_swarm_plan(self, db: Session, project: Project, swarm_plan_id: int) -> dict[str, Any]:
        plan = db.get(SwarmPlan, swarm_plan_id)
        if not plan or plan.project_id != project.id:
            raise ValueError("Swarm plan not found in this project")
        plan.approved_by_user = True
        plan.status = "approved"
        self._record_swarm_event(
            db,
            project,
            event_type="swarm_plan_approved",
            message=f"Swarm plan approved with {plan.recommended_agent_count} worker agent slots.",
            swarm_plan_id=plan.id,
        )
        return self._serialize_swarm_plan(db, project, plan) or {}

    async def revise_swarm_plan(self, db: Session, project: Project, swarm_plan_id: int, note: str | None = None) -> dict[str, Any]:
        plan = db.get(SwarmPlan, swarm_plan_id)
        if not plan or plan.project_id != project.id:
            raise ValueError("Swarm plan not found in this project")
        return await self.create_swarm_plan(
            db,
            project,
            goal=plan.goal,
            milestone_id=plan.milestone_id,
            revision_note=note or "Revise the swarm strategy based on current project state.",
        )

    def _sync_agents_to_swarm_plan(self, db: Session, project: Project, plan: SwarmPlan, *, activate_deferred: bool = False) -> tuple[int, int]:
        preferences = self._swarm_preferences(project)
        project_root_name = Path(project.workspace_path).name or f"project-{project.id}"
        worktree_base = WORKTREE_ROOT / f"{project.id}-{project_root_name}"
        worktree_base.mkdir(parents=True, exist_ok=True)
        existing_agents = {
            agent.name: agent
            for agent in db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker").order_by(Agent.id.asc()))
        }
        specs = self._swarm_specs_for_plan(db, plan.id)
        target_specs = self._swarm_target_specs(
            specs,
            recommended_agent_count=plan.recommended_agent_count,
            activate_deferred=activate_deferred,
        )
        spawned = 0
        retired = 0
        target_names = {spec.name for spec in target_specs}
        for index, spec in enumerate(target_specs, start=1):
            agent = existing_agents.get(spec.name)
            if agent is None:
                workspace = worktree_base / f"agent-{index}-{self._slugify(spec.name)[:32]}"
                workspace.mkdir(parents=True, exist_ok=True)
                agent = Agent(
                    project_id=project.id,
                    name=spec.name,
                    role=f"{self._titleize_path_label(spec.archetype)} specialist",
                    kind="worker",
                    status="idle",
                    workspace_path=str(workspace),
                    swarm_plan_id=plan.id,
                    archetype=spec.archetype,
                    mission=spec.mission,
                    retire_when=spec.retire_when,
                    locked_paths_json=[],
                    failure_count=0,
                )
                db.add(agent)
                db.flush()
                spawned += 1
                spec.status = "spawned"
                self._record_swarm_event(
                    db,
                    project,
                    event_type="agent_spawned",
                    message=f"{agent.name} spawned for {spec.archetype} work.",
                    swarm_plan_id=plan.id,
                    agent_id=agent.id,
                    metadata_json={"spec_id": spec.id},
                )
            else:
                agent.swarm_plan_id = plan.id
                agent.archetype = spec.archetype
                agent.mission = spec.mission
                agent.retire_when = spec.retire_when
                spec.status = "spawned"
        if preferences.allow_dynamic_retirement:
            for agent_name, agent in existing_agents.items():
                if agent_name in target_names or agent.kind != "worker":
                    continue
                if agent.status in {"idle", "waiting", "done", "stopped"} or project.runner_mode == "dry_run":
                    agent.status = "done"
                    agent.current_task_id = None
                    agent.current_action = "Retired by the latest swarm strategy."
                    retired += 1
                    self._record_swarm_event(
                        db,
                        project,
                        event_type="agent_retired",
                        message=f"{agent.name} retired from the current swarm strategy.",
                        swarm_plan_id=plan.id,
                        agent_id=agent.id,
                    )
                else:
                    agent.current_action = "Retire after the current task completes."
        db.flush()
        return spawned, retired

    def spawn_swarm_agents(self, db: Session, project: Project) -> dict[str, Any]:
        preferences = self._ensure_swarm_preferences(db, project)
        plan = self._current_swarm_plan_record(db, project.id)
        if plan is None:
            raise ValueError("Swarm plan not found")
        if self._swarm_approval_required(plan, preferences) and not plan.approved_by_user:
            raise ValueError("Swarm plan requires user approval before spawning this many agents.")
        if not plan.approved_by_user:
            plan.approved_by_user = True
            plan.status = "approved"
        spawned, retired = self._sync_agents_to_swarm_plan(db, project, plan, activate_deferred=project.runner_mode == "dry_run")
        plan.status = "active"
        message = f"Swarm sync complete: {spawned} agent(s) spawned, {retired} retired."
        return {
            "ok": True,
            "message": message,
            "swarm_plan": self._serialize_swarm_plan(db, project, plan),
            "agents_spawned": spawned,
            "agents_retired": retired,
        }

    async def scale_swarm(self, db: Session, project: Project, *, direction: str, reason: str | None = None, count: int = 1) -> dict[str, Any]:
        current_plan = self._current_swarm_plan_record(db, project.id)
        active_agent_count = 0
        if current_plan is not None:
            active_agent_count = db.scalar(
                select(func.count(Agent.id)).where(
                    Agent.project_id == project.id,
                    Agent.kind == "worker",
                    Agent.swarm_plan_id == current_plan.id,
                    ~Agent.status.in_(["done", "stopped"]),
                )
            ) or 0
        baseline_count = active_agent_count or (current_plan.recommended_agent_count if current_plan is not None else 0) or 1
        desired_count = baseline_count + count if direction == "up" else baseline_count - count
        scale_hint = "up" if direction == "up" else "down"
        plan_payload = await self.create_swarm_plan(
            db,
            project,
            goal=f"Scale the swarm {scale_hint} for {project.name}.",
            revision_note=reason or f"Scale {scale_hint} by {count}.",
            scale_hint=scale_hint,
        )
        plan = self._current_swarm_plan_record(db, project.id)
        if plan is None:
            raise ValueError("Swarm plan not found")
        preferences = self._ensure_swarm_preferences(db, project)
        plan.recommended_agent_count = max(1, min(preferences.max_agents, desired_count))
        plan.updated_at = utc_now()
        db.flush()
        if direction == "down" or not self._swarm_approval_required(plan, preferences):
            plan.approved_by_user = True
            plan.status = "approved"
            sync = self.spawn_swarm_agents(db, project)
        else:
            sync = {
                "ok": True,
                "message": "Swarm scale-up created a revised plan that still needs approval before spawning more agents.",
                "swarm_plan": plan_payload,
                "agents_spawned": 0,
                "agents_retired": 0,
            }
        self._record_swarm_event(
            db,
            project,
            event_type="swarm_scaled_up" if direction == "up" else "swarm_scaled_down",
            message=sync["message"],
            swarm_plan_id=plan.id,
            metadata_json={"direction": direction, "count": count, "reason": reason, "baseline_count": baseline_count, "desired_count": plan.recommended_agent_count},
        )
        return sync

    def _deterministic_task_decomposition(self, db: Session, project: Project, plan: Plan | None) -> ManagerTaskDecomposition:
        intelligence = planning_intelligence_service.build_context(db, project)
        validation_gaps = [
            str(item.get("area"))
            for item in (intelligence.get("validation_coverage") or [])
            if item.get("coverage_status") in {"none", "failed"}
        ]
        swarm_plan = self._current_swarm_plan_record(db, project.id)
        if swarm_plan is not None:
            specs = self._swarm_specs_for_plan(db, swarm_plan.id)
            if specs:
                tasks = [
                    ManagerTaskItem(
                        title=spec.name,
                        goal=spec.mission,
                        scope=f"Execute the {spec.archetype} mission with explicit path ownership.",
                        agent_role=spec.name,
                        milestone=spec.spawn_phase.replace("_", " ").title(),
                        priority=spec.priority,
                        allowed_paths=spec.allowed_paths_json or ["src"],
                        forbidden_paths=spec.forbidden_paths_json or [],
                        validation_steps=list(swarm_plan.validation_strategy_json or ["Record what was tested or reviewed."])
                        + [f"Close validation gap for {gap}." for gap in validation_gaps[:2]],
                        success_criteria=[spec.retire_when or "Assigned mission is complete."],
                        estimated_complexity="medium",
                        dependencies=[],
                        status="backlog" if spec.status in {"planned", "spawned"} else "assigned",
                    )
                    for spec in specs[: max(3, min(8, swarm_plan.recommended_agent_count))]
                ]
                return ManagerTaskDecomposition(
                    summary_markdown=f"Generated swarm-aligned tasks for {swarm_plan.mode} mode with explicit agent ownership.",
                    milestones=[
                        "Milestone 1 - Path ownership and first useful slice",
                        "Milestone 2 - Validation, review, and handoff readiness",
                    ],
                    tasks=tasks,
                )
        if project.source_type != "idea":
            root = Path(project.source_path or project.workspace_path)
            top_level_names = {item.name.lower() for item in root.iterdir()} if root.exists() else set()
            has_tests = any(name in {"tests", "test"} for name in top_level_names)
            primary_code_path = next((name for name in ["src", "app", "lib", "package", "server"] if name in top_level_names), "src")
            docs_path = "mission-control"
            request_text = " ".join(filter(None, [project.idea, project.latest_activity or ""])).lower()
            focused_on_tests = has_tests or "test" in request_text or "failing" in request_text or "fix" in request_text
            tasks = (
                [
                    ManagerTaskItem(
                        title="Reproduce the failing behavior and isolate the smallest broken path",
                        goal="Confirm the current failure locally and identify the narrowest code path that needs a fix.",
                        scope="Inspect the existing repo, run focused validation, and capture the failure without widening scope.",
                        agent_role="Validation Specialist",
                        milestone="Milestone 1 - Reproduce the problem",
                        priority=10,
                        allowed_paths=["tests", primary_code_path],
                        forbidden_paths=[],
                        validation_steps=["Run the narrowest relevant test command", "Record the observed failure honestly"],
                        success_criteria=["The current failure is reproduced or clearly explained", "The suspected failing path is narrowed down"],
                        estimated_complexity="small",
                        dependencies=[],
                        status="backlog",
                    ),
                    ManagerTaskItem(
                        title="Implement the smallest safe code fix",
                        goal="Correct the confirmed failing behavior with the least invasive code change.",
                        scope="Update only the implementation paths needed for the validated failure and avoid opportunistic refactors.",
                        agent_role="Service Flow Builder",
                        milestone="Milestone 2 - Fix the code",
                        priority=20,
                        allowed_paths=[primary_code_path],
                        forbidden_paths=["docs", docs_path],
                        validation_steps=["Keep the change scoped to the validated failure", "Note any assumptions that remain"],
                        success_criteria=["The implementation matches the expected behavior", "The diff stays narrowly scoped"],
                        estimated_complexity="small",
                        dependencies=[1],
                        status="backlog",
                    ),
                    ManagerTaskItem(
                        title="Re-run focused validation and prepare an honest handoff",
                        goal="Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
                        scope="Run the relevant checks again, update project notes if needed, and prepare the handoff evidence.",
                        agent_role="Validation Specialist",
                        milestone="Milestone 3 - Validate and hand off",
                        priority=30,
                        allowed_paths=["tests", primary_code_path, "docs", docs_path],
                        forbidden_paths=[],
                        validation_steps=["Re-run the focused validation command", "Record pass/fail results and remaining limitations"],
                        success_criteria=["Validation evidence is recorded truthfully", "The handoff explains exactly what changed and how to verify it"],
                        estimated_complexity="small",
                        dependencies=[2],
                        status="backlog",
                    ),
                ]
                if focused_on_tests
                else [
                    ManagerTaskItem(
                        title="Map the current codebase and confirm the first useful implementation slice",
                        goal="Understand the repo shape well enough to choose the smallest safe improvement slice.",
                        scope="Inspect the codebase, identify the main execution path, and define the first concrete build task.",
                        agent_role="Execution Planner",
                        milestone="Milestone 1 - Map the codebase",
                        priority=10,
                        allowed_paths=[primary_code_path, "tests", "docs"],
                        forbidden_paths=[],
                        validation_steps=["Identify the main entry path", "List the first safe implementation slice"],
                        success_criteria=["The next implementation step is explicit", "Repo ownership is clear enough to proceed"],
                        estimated_complexity="small",
                        dependencies=[],
                        status="backlog",
                    ),
                    ManagerTaskItem(
                        title="Implement the first safe code improvement",
                        goal="Complete the smallest useful implementation slice for the current codebase.",
                        scope="Edit only the paths needed for the chosen slice and avoid broad cleanup.",
                        agent_role="Service Flow Builder",
                        milestone="Milestone 2 - Implement the slice",
                        priority=20,
                        allowed_paths=[primary_code_path],
                        forbidden_paths=["docs", docs_path],
                        validation_steps=["Keep the implementation scoped", "Record what still needs validation"],
                        success_criteria=["The chosen slice is implemented", "Scope creep stays contained"],
                        estimated_complexity="medium",
                        dependencies=[1],
                        status="backlog",
                    ),
                    ManagerTaskItem(
                        title="Validate the slice and prepare handoff notes",
                        goal="Confirm the outcome and document what to run, what changed, and what remains.",
                        scope="Run focused validation, capture evidence, and prepare the operator handoff.",
                        agent_role="Validation Specialist",
                        milestone="Milestone 3 - Validate and hand off",
                        priority=30,
                        allowed_paths=["tests", primary_code_path, "docs", docs_path],
                        forbidden_paths=[],
                        validation_steps=["Run the most relevant validation step", "Record limitations and next steps"],
                        success_criteria=["Validation evidence is available", "The handoff is actionable"],
                        estimated_complexity="small",
                        dependencies=[2],
                        status="backlog",
                    ),
                ]
            )
            return ManagerTaskDecomposition(
                summary_markdown="Generated a codebase-aware task breakdown that starts from the current repo instead of inventing a generic product roadmap.",
                milestones=[
                    "Milestone 1 - Reproduce or map the current behavior",
                    "Milestone 2 - Implement the smallest safe fix or slice",
                    "Milestone 3 - Validate and hand off",
                ],
                tasks=tasks,
            )
        items = []
        for payload in build_initial_tasks(project):
            items.append(
                ManagerTaskItem(
                    title=payload["title"],
                    goal=payload["goal"],
                    scope=payload["scope"],
                    agent_role=payload.get("agent_role") or "Primary implementation",
                    milestone=payload.get("milestone") or "Milestone 1 - Runnable vertical slice",
                    priority=payload["priority"],
                    allowed_paths=payload["allowed_paths_json"],
                    forbidden_paths=payload["forbidden_paths_json"],
                    validation_steps=payload["validation_steps_json"],
                    success_criteria=payload.get("success_criteria_json", []),
                    estimated_complexity=payload.get("estimated_complexity", "medium"),
                    dependencies=payload.get("dependencies_json", []),
                    status="backlog",
                )
            )
        return ManagerTaskDecomposition(
            summary_markdown="Generated a milestone-based task breakdown with a runnable vertical slice first and explicit validation work last.",
            milestones=[
                "Milestone 1 - Runnable vertical slice",
                "Milestone 2 - Validation and handoff",
            ],
            tasks=items,
        )

    def _build_synthetic_worker_report(self, agent: Agent, task: Task | None, status: str, raw_payload: dict[str, Any] | None) -> WorkerReport:
        raw_payload = raw_payload or {}
        task_id = str(task.id if task else raw_payload.get("task_id") or "unknown")
        summary = raw_payload.get("summary") or f"Run finished with status {status}."
        report_status = raw_payload.get("status") or ("error" if status == "error" else "done")
        try:
            return _validate_model(
                WorkerReport,
                {
                    "agent": raw_payload.get("agent") or agent.name,
                    "task_id": task_id,
                    "status": report_status,
                    "summary": summary,
                    "files_changed": raw_payload.get("files_changed") or [],
                    "tests_run": raw_payload.get("tests_run") or [],
                    "blockers": raw_payload.get("blockers") or [],
                    "risks": raw_payload.get("risks") or [],
                    "recommended_next_task": raw_payload.get("recommended_next_task") or "",
                },
            )
        except ValidationError:
            return WorkerReport(
                agent=agent.name,
                task_id=task_id,
                status="error" if status == "error" else "done",
                summary=summary,
                files_changed=[],
                tests_run=[],
                blockers=[],
                risks=["Report payload could not be validated."],
                recommended_next_task="",
            )

    def _deterministic_worker_decision(
        self,
        db: Session,
        project: Project,
        agent: Agent,
        task: Task | None,
        report: WorkerReport,
    ) -> ManagerWorkerDecision:
        if not task:
            return ManagerWorkerDecision(decision_type="wait", summary_markdown="No follow-up task was attached to this run.")
        if report.status == "needs_review":
            return ManagerWorkerDecision(
                decision_type="escalate_to_user",
                summary_markdown=f"Task **{task.title}** needs review before more work is routed.",
                escalation_message=report.summary,
            )
        if report.status == "error":
            if task.failure_count < 2 and agent.failure_count < 3:
                return ManagerWorkerDecision(
                    decision_type="request_fix",
                    summary_markdown=f"Retry **{task.title}** once with a tighter fix pass.",
                    task_id=task.id,
                    assign_to_agent_id=agent.id,
                )
            return ManagerWorkerDecision(
                decision_type="escalate_to_user",
                summary_markdown=f"Repeated errors on **{task.title}** require user attention.",
                escalation_message=report.summary,
            )
        if report.status == "blocked":
            validation_agent = db.scalar(
                select(Agent)
                .where(Agent.project_id == project.id, Agent.kind == "worker")
                .order_by(Agent.id.asc())
            )
            if validation_agent and task.failure_count < 2:
                return ManagerWorkerDecision(
                    decision_type="request_fix",
                    summary_markdown=f"Create a follow-up unblock task for **{task.title}**.",
                    assign_to_agent_id=validation_agent.id,
                    follow_up_title=f"Unblock: {task.title}",
                    follow_up_goal=report.blockers[0] if report.blockers else f"Resolve the blocker reported by {agent.name}.",
                )
            return ManagerWorkerDecision(
                decision_type="escalate_to_user",
                summary_markdown=f"Task **{task.title}** is blocked and needs user input.",
                escalation_message=report.blockers[0] if report.blockers else report.summary,
            )
        next_task = self._find_next_safe_task(db, project, agent)
        if next_task:
            return ManagerWorkerDecision(
                decision_type="assign_next_task",
                summary_markdown=f"Route **{next_task.title}** to {agent.name}.",
                task_id=next_task.id,
                assign_to_agent_id=agent.id,
            )
        return ManagerWorkerDecision(
            decision_type="wait",
            summary_markdown=f"No safe backlog task is ready after **{task.title}**. Hold {agent.name} in waiting state.",
        )

    def _deterministic_handoff(self, project: Project, tasks: list[Task], runs: list[AgentRun]) -> ManagerHandoff:
        tests_run = sorted({entry for run in runs for entry in (run.report_json or {}).get("tests_run", [])})
        done_titles = [task.title for task in tasks if task.status == "done"]
        risks = sorted({entry for run in runs for entry in (run.report_json or {}).get("risks", []) if entry})
        return ManagerHandoff(
            summary_markdown=f"{project.name} reached handoff readiness with all tracked tasks in a terminal done state.",
            what_was_built=done_titles or ["Completed the tracked MVP task set."],
            how_to_run=[
                "Backend: cd apps/server && python -m uvicorn main:app --app-dir src --reload",
                "Frontend: cd apps/dashboard && npm run dev",
                "Use dry_run mode for offline orchestration testing.",
            ],
            how_to_use=[
                "Open Project Intake and create or resume a project.",
                "Run the interview, approve the plan, then monitor workers in Build Monitor.",
                "Use the manager chat or next-step controls for follow-up changes.",
            ],
            tests_builds_run=tests_run or ["No automated tests were recorded by the backend."],
            known_limitations=[
                "App-server integration remains experimental.",
                "Live manager turns depend on the selected local provider environment and may fall back deterministically.",
            ],
            remaining_risks=risks or ["Validation depth depends on the selected workspace tooling."],
            suggested_next_improvements=[
                "Deepen manager task decomposition for larger projects.",
                "Strengthen app-server parity with the CLI runner.",
                "Add richer review workflows for needs-review tasks.",
            ],
        )

    async def _resolve_manager_model(
        self,
        db: Session,
        project: Project,
        *,
        action_name: str,
        objective: str,
        response_schema: dict[str, Any],
        payload: dict[str, Any],
        model_schema: type[TManagerModel],
        fallback_factory: Callable[[], TManagerModel],
        prompt_override: str | None = None,
    ) -> tuple[TManagerModel, str]:
        manager_agent = self._manager_agent(db, project.id)
        settings_record = self._project_settings(db, project)
        resolved_settings = resolve_manager_settings(project, settings_record)
        latest_plan = self._latest_plan(db, project.id)
        docs_path = project.docs_path or str(self._project_docs_dir(project))
        requested_mode = project.manager_mode or DEFAULT_MANAGER_MODE

        if requested_mode == "deterministic" or resolved_settings.runner_mode == "dry_run":
            manager_agent.active_model = resolved_settings.effective_model_label
            manager_agent.active_reasoning_effort = resolved_settings.effective_reasoning_label
            manager_agent.active_runner_type = resolved_settings.runner_mode
            manager_agent.current_action = action_name
            self.events.publish(db, project.id, "manager.mode.deterministic", {"action": action_name})
            return fallback_factory(), "deterministic"

        try_live_provider = requested_mode in {"provider", "codex", "auto"}
        if try_live_provider:
            try:
                runner = await self.runners.get_runner_for_settings(resolved_settings)
                prompt = prompt_override or manager_action_prompt(
                    project,
                    docs_path,
                    action=action_name,
                    objective=objective,
                    response_schema=response_schema,
                    payload=payload,
                    plan_markdown=latest_plan.content_markdown if latest_plan else None,
                    user_name=self._preferred_user_name(db, project),
                    provider=resolved_settings.provider,
                    model=resolved_settings.effective_model_label,
                    reasoning_effort=resolved_settings.effective_reasoning_label,
                )
                manager_agent.status = "working"
                self._cache_agent_run_profile(manager_agent, resolved_settings, runner_type=runner.runner_type, action=action_name)
                handle, last_payload = await runner.run_manager_turn(
                    RunnerContext(
                        project=project,
                        agent=manager_agent,
                        task=None,
                        docs_path=docs_path,
                        plan_markdown=latest_plan.content_markdown if latest_plan else None,
                        settings=self._runner_settings_payload(resolved_settings),
                    ),
                    prompt,
                )
                manager_agent.status = "idle"
                if handle.session_ref:
                    manager_agent.session_ref = handle.session_ref
                self.events.publish(
                    db,
                    project.id,
                    "manager.mode.provider",
                    {
                        "action": action_name,
                        "provider": resolved_settings.provider,
                        "runner": handle.runner_type,
                        "logs_path": handle.logs_path,
                        "effective_settings": resolved_run_settings_payload(resolved_settings),
                    },
                )
                if resolved_settings.provider == "codex":
                    self.events.publish(
                        db,
                        project.id,
                        "manager.mode.codex",
                        {
                            "action": action_name,
                            "runner": handle.runner_type,
                            "logs_path": handle.logs_path,
                            "effective_settings": resolved_run_settings_payload(resolved_settings),
                        },
                    )
                text = ""
                if last_payload and isinstance(last_payload.get("item"), dict):
                    text = last_payload["item"].get("text", "")
                elif last_payload:
                    text = str(last_payload.get("text", ""))
                parsed, repaired = runner.try_parse_json_payload(text)
                if repaired:
                    self.events.publish(db, project.id, "manager.parse_repair_attempted", {"action": action_name})
                if parsed is not None:
                    return _validate_model(model_schema, parsed), resolved_settings.provider
                self.events.publish(db, project.id, "manager.parse_failed", {"action": action_name})
            except (ValidationError, ValueError, RuntimeError) as exc:
                self.events.publish(db, project.id, "manager.parse_failed", {"action": action_name, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                self.events.publish(db, project.id, "manager.parse_failed", {"action": action_name, "error": str(exc)})
            self.events.publish(db, project.id, "manager.mode.fallback", {"action": action_name})

        manager_agent.active_model = resolved_settings.effective_model_label
        manager_agent.active_reasoning_effort = resolved_settings.effective_reasoning_label
        manager_agent.active_runner_type = resolved_settings.runner_mode
        manager_agent.current_action = action_name
        self.events.publish(db, project.id, "manager.mode.deterministic", {"action": action_name})
        return fallback_factory(), "deterministic"

    async def get_system_status(
        self,
        db: Session,
        project: Project | None = None,
        *,
        provider_override: str | None = None,
        provider_endpoint_override: str | None = None,
        adapter_command_override: str | None = None,
        adapter_args_override: list[str] | None = None,
    ) -> dict[str, Any]:
        from system_status import assess_model_advisories, detect_system_status
        from startup import startup_service
        from runtime_paths import diagnostics_root

        project_settings = self._project_settings_preview(db, project) if project else None
        app_profile = self._app_profile_preview(db)
        selected_provider = provider_override or (project_settings.provider if project_settings else app_profile.selected_provider or "codex")
        adapter_command = (
            adapter_command_override
            if adapter_command_override is not None
            else (project_settings.adapter_command if project_settings else app_profile.adapter_command)
        )
        adapter_args = (
            list(adapter_args_override)
            if adapter_args_override is not None
            else (list(project_settings.adapter_args_json) if project_settings else list(app_profile.adapter_args_json or []))
        )
        provider_endpoint = (
            provider_endpoint_override
            if provider_endpoint_override is not None
            else (project_settings.provider_endpoint if project_settings and project_settings.provider_endpoint is not None else app_profile.provider_endpoint)
        )
        status = detect_system_status(
            selected_provider=selected_provider,
            adapter_command=adapter_command,
            ollama_endpoint=provider_endpoint,
            adapter_args=adapter_args,
        )
        status["current_auth_job"] = auth_service.job_payload(auth_service.current_job())
        if normalize_provider(selected_provider) == "codex":
            status["app_server_handshake_status"] = "available" if await self.runners.app_server_available() else "unavailable"
        else:
            status["app_server_handshake_status"] = "unsupported"
        active_runs = list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.finished_at.is_(None))
                .order_by(AgentRun.started_at.desc())
            )
        )
        status["active_runs"] = [
            {
                "run_id": run.id,
                "agent_id": run.agent_id,
                "task_id": run.task_id,
                "runner_type": run.runner_type,
                "status": run.status,
                "effective_settings": run.effective_settings_json or {},
            }
            for run in active_runs
        ]
        if project:
            settings = project_settings or self._project_settings(db, project)
            status["current_settings_summary"] = settings_summary(settings)
            status["selected_provider"] = normalize_provider(settings.provider)
            status["selected_provider_label"] = provider_label(settings.provider)
            status["selected_manager_model"] = settings.manager_model
            status["selected_default_worker_model"] = settings.default_worker_model
            status["model_advisories"] = assess_model_advisories(
                provider=settings.provider,
                manager_model=settings.manager_model,
                worker_model=settings.default_worker_model,
                available_models=list(status.get("available_models", [])),
            )
            resolved = resolve_manager_settings(project, settings)
            status["effective_runner_mode"] = await self.runners.effective_mode(resolved)
        else:
            status["effective_runner_mode"] = app_profile.default_runner_mode or DEFAULT_RUNNER_MODE
        status["app_state_summary"] = app_profile
        status["startup_summary"] = startup_service.last_status or startup_service.preview_status(db, attempt_number=1, include_optional_checks=True)
        status["diagnostics_directory"] = str(diagnostics_root())
        return status

    def auth_state(self) -> dict[str, Any]:
        from system_status import detect_codex_status, detect_provider_statuses

        status = detect_codex_status()
        return {
            "authenticated": status["authenticated"],
            "auth_mode": status["auth_mode"],
            "login_status": status["login_status"],
            "cli_detected": status["cli_detected"],
            "provider": "codex",
            "current_job": auth_service.job_payload(auth_service.current_job()),
            "chatgpt_supported": status["cli_detected"],
            "device_auth_supported": status["cli_detected"],
            "api_key_supported": status["cli_detected"],
            "provider_statuses": detect_provider_statuses(),
            "notes": [
                "ChatGPT sign-in is the recommended path and keeps usage tied to your local Codex session.",
                "API key login is optional and can use API billing depending on your account.",
                "Other providers use their own local auth or environment-based setup outside Mission Control.",
            ],
        }

    def get_app_profile(self, db: Session) -> AppProfile:
        return self._app_profile_preview(db)

    def update_app_profile(self, db: Session, payload: AppProfileUpdate) -> AppProfile:
        return update_app_profile(db, payload)

    def list_projects(self, db: Session, *, include_archived: bool = False) -> list[dict[str, Any]]:
        return [self._serialize_project_card(db, project) for project in self._ordered_projects(db, include_archived=include_archived)]

    async def _dashboard_attention_items(self, db: Session, projects: list[Project]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for project in projects:
            if project.archived_at:
                continue
            settings = self._project_settings_preview(db, project)
            degraded_notices = await self._workspace_degraded_notices(project, settings)
            action = self._derive_current_action(db, project, degraded_notices)
            if action["type"] == "no_action":
                continue
            items.append(
                {
                    "id": f"{project.id}:{action['id']}",
                    "project_id": project.id,
                    "project_name": project.name,
                    "project_slug": self._effective_project_slug(project),
                    "kind": action["type"],
                    "summary": action["title"],
                    "detail": action["message"],
                    "severity": action["severity"],
                    "target": self._project_route(project),
                    "created_at": action["created_at"],
                    "_priority": ATTENTION_PRIORITY.get(str(action["type"]), 99),
                }
            )
        items.sort(
            key=lambda item: (
                int(item["_priority"]),
                -float(item["created_at"].timestamp() if hasattr(item["created_at"], "timestamp") else 0),
            )
        )
        return [{key: value for key, value in item.items() if key != "_priority"} for item in items[:6]]

    def _dashboard_stage(self, project: Project, agent: dict[str, Any] | None, pending_action: dict[str, Any] | None) -> str:
        display_status = self._project_display_status(project)
        if pending_action and pending_action["type"] in {"command_approval", "tool_approval", "manager_question"}:
            return "Waiting on user"
        if display_status == "blocked":
            return "Blocked"
        if display_status == "interviewing":
            return "Interviewing"
        if display_status == "planning":
            return "Planning"
        if display_status == "paused":
            return "Paused"
        if display_status == "ready_for_handoff":
            return "Preparing handoff"
        if agent:
            agent_status = str(agent.get("display_status") or "")
            if agent_status in {"running", "coding", "active"}:
                return "Building"
            if agent_status in {"reviewing", "monitoring"}:
                return "Testing"
            if agent_status in {"thinking"}:
                return "Planning"
            if agent_status in {"waiting"}:
                return "Waiting"
            if agent_status in {"blocked", "error"}:
                return "Blocked"
        return self._status_label(display_status)

    async def _dashboard_active_builds(self, db: Session, projects: list[Project]) -> list[dict[str, Any]]:
        builds: list[dict[str, Any]] = []
        for project in projects:
            if project.archived_at:
                continue
            agents = self._sorted_workspace_agents(db, project.id)
            active_agent = next(
                (
                    agent
                    for agent in agents
                    if str(agent.get("display_status")) in {"blocked", "error", "running", "coding", "active", "thinking", "reviewing", "monitoring", "waiting"}
                ),
                None,
            )
            pending_action: dict[str, Any] | None = None
            if project.status not in {"handoff_ready"}:
                settings = self._project_settings_preview(db, project)
                degraded_notices = await self._workspace_degraded_notices(project, settings)
                pending_action = self._derive_current_action(db, project, degraded_notices)
            stage = self._dashboard_stage(project, active_agent, pending_action)
            if stage not in {"Planning", "Interviewing", "Building", "Testing", "Waiting", "Waiting on user", "Blocked", "Paused", "Preparing handoff"}:
                continue
            task_id = active_agent.get("current_task_id") if active_agent else None
            task_title = (
                (str(active_agent.get("current_task_title")) if active_agent and active_agent.get("current_task_title") else None)
                or project.latest_milestone
                or project.latest_activity
                or "Manager is routing the next step."
            )
            builds.append(
                {
                    "project_id": project.id,
                    "project_name": project.name,
                    "project_slug": self._effective_project_slug(project),
                    "task_id": task_id,
                    "task_title": task_title,
                    "stage": stage,
                    "agent_name": active_agent.get("name") if active_agent else None,
                    "runner_type": active_agent.get("runner_mode") if active_agent else None,
                    "updated_at": project.updated_at,
                    "_priority": {
                        "Blocked": 0,
                        "Waiting on user": 1,
                        "Building": 2,
                        "Testing": 3,
                        "Planning": 4,
                        "Interviewing": 4,
                        "Waiting": 5,
                        "Paused": 6,
                        "Preparing handoff": 7,
                    }.get(stage, 99),
                }
            )
        builds.sort(
            key=lambda item: (
                int(item["_priority"]),
                -float(item["updated_at"].timestamp() if hasattr(item["updated_at"], "timestamp") else 0),
            )
        )
        return [{key: value for key, value in item.items() if key != "_priority"} for item in builds[:6]]

    async def get_dashboard_summary(self, db: Session) -> dict[str, Any]:
        profile = self._app_profile_preview(db)
        projects = self._ordered_projects(db, include_archived=True)
        sidebar_projects = self._sidebar_projects(projects)
        recent_projects = [project for project in projects if not project.archived_at][:3]
        active_builds = await self._dashboard_active_builds(db, projects)
        attention_items = await self._dashboard_attention_items(db, projects)
        widget_summary = await self.get_dashboard_widget_summary(db)
        blocked_agents = []
        for project in projects:
            for agent_payload in self._sorted_workspace_agents(db, project.id):
                if agent_payload["display_status"] in {"blocked", "error"}:
                    blocked_agents.append(agent_payload)
        archive_count = max(0, len([project for project in projects if not project.archived_at]) - len(sidebar_projects)) + len(
            [project for project in projects if project.archived_at]
        )
        system_status = await self.get_system_status(db)
        return {
            "sidebar_projects": [self._serialize_project_card(db, project) for project in sidebar_projects],
            "recent_projects": [self._serialize_project_card(db, project) for project in recent_projects],
            "archive_count": archive_count,
            "active_builds": active_builds,
            "attention_items": attention_items,
            "blocked_agents": blocked_agents[:5],
            "recent_handoffs": self.list_handoffs(db)[:3],
            "runner_status": {
                "selected_provider": system_status["selected_provider"],
                "selected_provider_label": system_status["selected_provider_label"],
                "effective_runner_mode": system_status["effective_runner_mode"],
                "cli_detected": system_status["cli_detected"],
                "authenticated": system_status["authenticated"],
                "app_server_handshake_status": system_status["app_server_handshake_status"],
            },
            "connected_accounts": dict(profile.connected_accounts_json or {}),
            "model_defaults": {
                "manager_model": profile.manager_model,
                "default_worker_model": profile.default_worker_model,
                "manager_reasoning_effort": profile.manager_reasoning_effort,
                "default_worker_reasoning_effort": profile.default_worker_reasoning_effort,
            },
            "widgets": [item["widget_type"] for item in widget_summary["instances"]],
            "available_widgets": [item["widget_type"] for item in widget_summary["catalog"]],
            "widget_instances": widget_summary["instances"],
            "widget_data": widget_summary["data"],
            "widget_catalog": widget_summary["catalog"],
        }

    def archive_project(self, db: Session, project: Project) -> Project:
        project.archived_at = utc_now()
        project.pinned = False
        self.events.publish(db, project.id, "project.archived", {"project_id": project.id})
        return project

    def unarchive_project(self, db: Session, project: Project) -> Project:
        project.archived_at = None
        self.events.publish(db, project.id, "project.unarchived", {"project_id": project.id})
        return project

    def pin_project(self, db: Session, project: Project) -> Project:
        project.pinned = True
        return project

    def unpin_project(self, db: Session, project: Project) -> Project:
        project.pinned = False
        return project

    def pause_project(self, db: Session, project: Project) -> Project:
        if project.status == "paused":
            return project
        project.status = "paused"
        for agent in db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker")):
            if agent.status in {"idle", "waiting", "done", "stopped"}:
                agent.current_action = "Paused by user."
        self._record_manager_message(
            db,
            project,
            role="system",
            message_type="system_notice",
            content_markdown="Project paused. The manager will stop assigning new work until you resume the workspace.",
            metadata_json={"project_state": "paused"},
        )
        self.events.publish(db, project.id, "project.paused", {"project_id": project.id})
        self._publish_workspace_state(db, project.id)
        return project

    def resume_project(self, db: Session, project: Project) -> Project:
        if project.status != "paused":
            return project
        has_open_tasks = db.scalar(
            select(func.count(Task.id)).where(Task.project_id == project.id, Task.status != "done")
        ) or 0
        project.status = "building" if has_open_tasks else "draft"
        for agent in db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker")):
            if agent.status in {"idle", "waiting", "done", "stopped"}:
                agent.current_action = "Awaiting reassignment."
        self._record_manager_message(
            db,
            project,
            role="system",
            message_type="system_notice",
            content_markdown="Project resumed. The manager can start routing work again.",
            metadata_json={"project_state": "resumed"},
        )
        self.events.publish(db, project.id, "project.resumed", {"project_id": project.id})
        self._publish_workspace_state(db, project.id)
        return project

    def list_handoffs(self, db: Session) -> list[dict[str, Any]]:
        handoffs: list[dict[str, Any]] = []
        projects = self._ordered_projects(db, include_archived=True)
        for project in projects:
            latest_handoff = self._latest_evidence_handoff(db, project.id)
            if latest_handoff is None and not project.final_report_json:
                continue
            handoffs.append(self._serialize_handoff_record(db, project, latest_handoff))
        return sorted(handoffs, key=lambda item: item["created_at"], reverse=True)

    def get_project_handoff_summary(self, db: Session, project: Project) -> dict[str, Any]:
        return self._serialize_handoff_record(db, project, self._latest_evidence_handoff(db, project.id))

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            ordered.append(text)
        return ordered

    def _latest_project_orchestration(self, db: Session, project: Project) -> OrchestrationSession | None:
        return db.scalar(
            select(OrchestrationSession)
            .where(OrchestrationSession.project_id == project.id)
            .order_by(OrchestrationSession.updated_at.desc(), OrchestrationSession.id.desc())
        )

    def build_operator_snapshot(self, db: Session, project: Project) -> dict[str, Any]:
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        current_action = self._derive_current_action_preview(db, project, [])
        health = self.get_project_health_preview(db, project)
        handoff = self.get_project_handoff_summary(db, project)
        pending_approvals = self.list_pending_approvals(db, project)
        pending_questions = self.list_pending_questions(db, project, mutate=False)
        coverage = validation_coverage_service.coverage_summary(db, project)
        latest_report = next(iter(self.recent_diagnostic_reports()), None)
        latest_orchestration = self._latest_project_orchestration(db, project)
        active_agents = [
            {
                "id": int(agent["id"]),
                "name": str(agent["name"]),
                "role": str(agent.get("role") or "worker"),
                "display_status": str(agent.get("display_status") or "unknown"),
                "current_action": agent.get("current_action"),
            }
            for agent in self._sorted_workspace_agents(db, project.id)
            if str(agent.get("display_status") or "") in {"working", "blocked", "waiting", "error"}
        ]
        timeline = self.list_timeline_events(db, project)[:6]
        swarm_plan = self.get_swarm_plan(db, project)
        current_focus = self._dedupe_strings(
            [
                *(f"{agent['name']}: {agent.get('current_action') or agent['display_status']}" for agent in active_agents[:4]),
                str(current_action.get("title") or ""),
                str(current_action.get("message") or ""),
            ]
        )[:6]
        top_risks = self._dedupe_strings(
            [*list(health.get("top_risks") or []), *list(health.get("reasons") or [])]
        )[:6]
        recent_events = self._dedupe_strings(
            [f"{event.title}: {event.summary}" for event in timeline]
        )[:6]
        diagnostics_summary = str(latest_report.get("summary") or "").strip() if isinstance(latest_report, dict) else None
        diagnostics_bundle_path = str(latest_report.get("bundle_path") or "").strip() or None if isinstance(latest_report, dict) else None
        performance_profile = latest_report.get("performance_profile") if isinstance(latest_report, dict) else {}
        performance_note = None
        if isinstance(performance_profile, dict) and performance_profile:
            lag_risk = str(performance_profile.get("lag_risk") or "unknown")
            max_agents = performance_profile.get("recommended_swarm_max_agents")
            performance_note = f"Device lag risk is {lag_risk}; recommended swarm max agents: {max_agents}."
        snapshot_markdown = "\n".join(
            [
                "## Mission Control Operator Snapshot",
                "",
                f"- Project: **{project.name}**",
                f"- Project status: `{project.status}`",
                f"- Overall health: `{health.get('state')}`",
                f"- Handoff status: `{handoff.get('status') or 'not_ready'}`",
                f"- Pending approvals: `{len(pending_approvals)}`",
                f"- Pending questions: `{len(pending_questions)}`",
                f"- Validation gap count: `{len(list(coverage.get('gaps') or []))}`",
                f"- Recommended next action: {health.get('next_action') or current_action.get('title') or 'Review the latest project state.'}",
                "",
                "### Current focus",
                self._markdown_list(current_focus or ["No active focus items are recorded right now."]),
                "",
                "### Top risks",
                self._markdown_list(top_risks or ["No major risk signals are recorded right now."]),
                "",
                "### Recent events",
                self._markdown_list(recent_events or ["No recent timeline events are recorded yet."]),
            ]
        )
        return {
            "project_id": project.id,
            "project_name": project.name,
            "project_status": project.status,
            "overall_status": str(health.get("state") or "unknown"),
            "orchestration_status": latest_orchestration.status if latest_orchestration is not None else None,
            "handoff_status": str(handoff.get("status") or "not_ready"),
            "current_action": str(current_action.get("title") or current_action.get("message") or "Monitoring project state."),
            "pending_approvals_count": len(pending_approvals),
            "pending_questions_count": len(pending_questions),
            "active_agent_count": len(active_agents),
            "active_agents": active_agents[:6],
            "current_focus": current_focus,
            "top_risks": top_risks,
            "recent_events": recent_events,
            "validation_gap_count": len(list(coverage.get("gaps") or [])),
            "swarm_mode": str(swarm_plan.get("mode") or "") if isinstance(swarm_plan, dict) and swarm_plan.get("mode") else None,
            "recommended_next_action": str(health.get("next_action") or current_action.get("title") or "Review the latest project state."),
            "diagnostics_summary": diagnostics_summary,
            "diagnostics_bundle_path": diagnostics_bundle_path,
            "performance_note": performance_note,
            "snapshot_markdown": snapshot_markdown,
            "generated_at": utc_now(),
        }

    def preview_operational_instincts(self, db: Session, project: Project) -> dict[str, Any]:
        snapshot = self.build_operator_snapshot(db, project)
        handoff = self.get_project_handoff_summary(db, project)
        coverage = validation_coverage_service.coverage_summary(db, project)
        persisted_locks = list(project.path_locks or [])
        preview_locks = persisted_locks or self._preview_path_locks(db, project)
        recent_decisions = list(project.decision_records or []) or self._preview_decision_records(db, project)
        latest_report = next(iter(self.recent_diagnostic_reports()), None)
        performance_profile = latest_report.get("performance_profile") if isinstance(latest_report, dict) else {}
        instincts: list[dict[str, Any]] = []

        if snapshot["active_agent_count"] > 1 or preview_locks:
            instincts.append(
                {
                    "key": "path-lock-before-parallel-edit",
                    "title": "Lock paths before parallel edits",
                    "trigger": "Multiple active agents or live path ownership signals exist.",
                    "rule": "Treat parallel work as a path-ownership problem first, not a staffing problem.",
                    "rationale": "ECC leans hard on parallelism discipline. Mission Control already has path locks and conflict tracking, so the useful move is to surface that instinct explicitly.",
                    "evidence": self._dedupe_strings(
                        [
                            f"Active agent count: {snapshot['active_agent_count']}",
                            f"Tracked path locks: {len(preview_locks)}",
                            *(snapshot["current_focus"][:2]),
                        ]
                    ),
                    "confidence": "high",
                    "tags": ["parallelism", "coordination", "path-locks"],
                }
            )
        if str(handoff.get("status") or "") in {"ready", "needs_review"} or str(handoff.get("evidence_status") or "") != "missing":
            instincts.append(
                {
                    "key": "ship-with-evidence",
                    "title": "Ship with evidence, not vibes",
                    "trigger": "A handoff exists or validation evidence is already in play.",
                    "rule": "Close work with explicit evidence, known limitations, and runnable next steps.",
                    "rationale": "ECC is obsessive about operational closure. Mission Control already tracks evidence-backed handoffs, so this turns that behavior into a reusable operator instinct.",
                    "evidence": self._dedupe_strings(
                        [
                            f"Handoff status: {handoff.get('status') or 'not_ready'}",
                            f"Evidence status: {handoff.get('evidence_status') or 'missing'}",
                            *list(handoff.get("known_limitations") or [])[:2],
                        ]
                    ),
                    "confidence": "high",
                    "tags": ["handoff", "evidence", "release"],
                }
            )
        if list(coverage.get("gaps") or []):
            instincts.append(
                {
                    "key": "turn-gaps-into-checks",
                    "title": "Turn validation gaps into named checks",
                    "trigger": "Coverage gaps are still open.",
                    "rule": "Translate missing coverage into explicit checks before calling the task done.",
                    "rationale": "This mirrors ECC's verification-loop bias without pretending every repo wants the same ceremony forever.",
                    "evidence": self._dedupe_strings(
                        [f"Validation gap: {gap}" for gap in list(coverage.get("gaps") or [])[:4]]
                    ),
                    "confidence": "high",
                    "tags": ["verification", "coverage", "quality"],
                }
            )
        if recent_decisions:
            instincts.append(
                {
                    "key": "write-the-decision-down",
                    "title": "Write the decision down when it changes execution",
                    "trigger": "Recent decision records exist.",
                    "rule": "If scope, model, tool, or recovery strategy changes, persist the decision so the next agent does not rediscover it expensively.",
                    "rationale": "ECC treats memory and operator state as first-class. Mission Control already has a decision ledger, so this is the useful non-hand-wavy version.",
                    "evidence": self._dedupe_strings(
                        [f"{entry.title}: {entry.decision}" for entry in recent_decisions[:3]]
                    ),
                    "confidence": "medium",
                    "tags": ["memory", "decisions", "handoff"],
                }
            )
        if isinstance(performance_profile, dict) and performance_profile:
            instincts.append(
                {
                    "key": "respect-device-budget",
                    "title": "Respect the device budget",
                    "trigger": "Diagnostic reports include a performance profile.",
                    "rule": "Scale swarm intensity to the host's lag risk instead of assuming every machine wants maximum concurrency.",
                    "rationale": "ECC talks a lot about harness performance. Mission Control should operationalize that as a guardrail, not a slogan.",
                    "evidence": self._dedupe_strings(
                        [
                            f"Lag risk: {performance_profile.get('lag_risk')}",
                            f"Recommended swarm max agents: {performance_profile.get('recommended_swarm_max_agents')}",
                            str(snapshot.get('performance_note') or ""),
                        ]
                    ),
                    "confidence": "medium",
                    "tags": ["performance", "swarm", "local-first"],
                }
            )
        instincts = instincts[:5]
        return {
            "project_id": project.id,
            "instinct_count": len(instincts),
            "instincts": instincts,
            "generated_at": utc_now(),
        }

    def build_verification_brief(self, db: Session, project: Project) -> dict[str, Any]:
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        overview = self._project_overview(db, project, tasks, self._derive_current_action_preview(db, project, []))
        preferences = project.swarm_preferences or self._swarm_preferences(project)
        conflicts = self._preview_conflicts(db, project)
        review_gates = list(project.review_gates or []) or self._preview_review_gates(
            db,
            project,
            tasks=tasks,
            overview=overview,
            testing_depth=preferences.testing_depth,
            conflicts=conflicts,
        )
        recipe = next(iter(project.validation_recipes or []), None) or self._preview_validation_recipe(db, project)
        coverage = validation_coverage_service.coverage_summary(db, project)
        handoff = self.get_project_handoff_summary(db, project)
        pending_approvals = self.list_pending_approvals(db, project)
        required_checks = self._dedupe_strings(
            [
                *[
                    str(step.get("command") or step.get("title") or "").strip()
                    for step in list(recipe.steps_json or [])
                ],
                *[
                    f"{gate.title}: {', '.join(str(item) for item in list(gate.required_checks_json or []))}".rstrip(": ")
                    for gate in review_gates
                    if gate.required
                ],
            ]
        )
        recommended_checks = self._dedupe_strings(
            [
                *[
                    str(step.get("title") or step.get("command") or "").strip()
                    for step in list(recipe.steps_json or [])
                ],
                "Review the latest handoff and known limitations before release.",
                "Confirm pending approvals are resolved before promoting the result.",
            ]
        )
        release_blockers = self._dedupe_strings(
            [
                *[f"Required review gate not passed: {gate.title} [{gate.status}]" for gate in review_gates if gate.required and gate.status != "passed"],
                *[f"Pending approval: {item['title']}" for item in pending_approvals[:4]],
            ]
        )
        handoff_warnings = self._dedupe_strings(
            [
                f"Handoff status is {handoff.get('status') or 'not_ready'}." if str(handoff.get("status") or "") != "ready" else "",
                "Handoff evidence is still missing." if str(handoff.get("evidence_status") or "") == "missing" else "",
                *list(handoff.get("known_limitations") or [])[:3],
            ]
        )
        evidence_gaps = self._dedupe_strings(
            [
                *[f"Validation gap: {gap}" for gap in list(coverage.get("gaps") or [])],
                *["No validated handoff evidence has been recorded yet." if str(handoff.get("evidence_status") or "") == "missing" else ""],
            ]
        )
        if release_blockers:
            readiness = "blocked"
        elif evidence_gaps or handoff_warnings:
            readiness = "needs_review"
        else:
            readiness = "ready"
        loop_strategy = [
            "Run the required automated checks first and capture the results as evidence.",
            "If a required gate fails, record the blocker explicitly instead of claiming soft success.",
            "Review docs, handoff notes, and known limitations before calling the work release-ready.",
            "After fixes, rerun the smallest meaningful validation loop before widening scope again.",
        ]
        brief_markdown = "\n".join(
            [
                "## Mission Control Verification Brief",
                "",
                f"- Readiness: `{readiness}`",
                f"- Required checks: `{len(required_checks)}`",
                f"- Evidence gaps: `{len(evidence_gaps)}`",
                f"- Release blockers: `{len(release_blockers)}`",
                "",
                "### Required checks",
                self._markdown_list(required_checks or ["No explicit required checks are recorded yet."]),
                "",
                "### Evidence gaps",
                self._markdown_list(evidence_gaps or ["No obvious evidence gaps are recorded right now."]),
                "",
                "### Loop strategy",
                self._markdown_list(loop_strategy),
            ]
        )
        return {
            "project_id": project.id,
            "readiness": readiness,
            "required_checks": required_checks,
            "recommended_checks": recommended_checks[:8],
            "evidence_gaps": evidence_gaps[:8],
            "release_blockers": release_blockers[:8],
            "handoff_warnings": handoff_warnings[:8],
            "loop_strategy": loop_strategy,
            "brief_markdown": brief_markdown,
            "generated_at": utc_now(),
        }

    def get_tool_catalog(self, db: Session) -> list[dict[str, Any]]:
        profile = self._app_profile_preview(db)
        return catalog_with_permissions(
            provider=normalize_provider(profile.selected_provider),
            connected_accounts=dict(profile.connected_accounts_json or {}),
            permission_overrides=dict(profile.tool_permission_overrides_json or {}),
        )

    def update_tool_permission(self, db: Session, tool_id: str, permission_policy: str) -> dict[str, Any]:
        if tool_id not in {item["id"] for item in TOOL_CATALOG}:
            raise ValueError("Unknown tool")
        profile = self._app_profile(db)
        overrides = dict(profile.tool_permission_overrides_json or {})
        overrides[tool_id] = permission_policy
        profile.tool_permission_overrides_json = overrides
        profile.last_opened_at = utc_now()
        db.flush()
        return {"tool_id": tool_id, "permission_policy": permission_policy}

    async def list_skills(self, db: Session) -> list[dict[str, Any]]:
        status = await self.get_system_status(db)
        return [
            {
                "name": skill,
                "source": "local_codex",
                "available": True,
                "summary": "Available through the local Codex skill configuration.",
            }
            for skill in status["local_skills"]
        ]

    def _workspace_has_user_files(self, workspace_path: str) -> bool:
        root = Path(workspace_path)
        try:
            entries = list(root.iterdir())
        except OSError:
            return False
        ignored = {
            ".git",
            ".hg",
            ".svn",
            ".DS_Store",
            "Thumbs.db",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            "mission-control",
        }
        return any(entry.name not in ignored for entry in entries)

    def _prime_workspace_context(self, db: Session, project: Project) -> None:
        if project.source_type == "idea":
            return
        if project.scan_status == "completed" and project.codebase_map and project.codebase_understanding:
            return
        try:
            codebase_map, understanding, agents_status, safety = import_service.initial_scan(db, project)
        except ValueError:
            project.scan_status = "failed"
            return
        self.events.publish(
            db,
            project.id,
            "codebase_scan_completed",
            {"project_id": project.id, "scan_depth": codebase_map.scan_depth, "codebase_size": codebase_map.codebase_size},
        )
        self.events.publish(
            db,
            project.id,
            "codebase_understanding_created",
            {
                "project_id": project.id,
                "generation_mode": understanding.generation_mode,
                "recommended_interview_mode": understanding.recommended_interview_mode,
            },
        )
        self.events.publish(
            db,
            project.id,
            "agents_md_detected",
            {"project_id": project.id, "has_agents_md": agents_status.has_agents_md, "recommended_action": agents_status.recommended_action},
        )
        self.events.publish(
            db,
            project.id,
            "import_safety_updated",
            {"project_id": project.id, "write_permission_status": safety.write_permission_status},
        )

    def recent_diagnostic_reports(self) -> list[dict[str, Any]]:
        return list_diagnostic_reports()

    def create_project(self, db: Session, *, name: str, idea: str, workspace_path: str, provider: str, runner_mode: str, manager_mode: str) -> Project:
        profile = self._app_profile(db)
        selected_provider = normalize_provider(provider or profile.selected_provider)
        normalized_workspace = resolve_local_path(workspace_path).as_posix()
        has_existing_files = self._workspace_has_user_files(normalized_workspace)
        project = Project(
            name=name,
            slug=self._slugify(name),
            idea=idea,
            workspace_path=normalized_workspace,
            status="draft",
            runner_mode=runner_mode or profile.default_runner_mode or DEFAULT_RUNNER_MODE,
            manager_mode=manager_mode or DEFAULT_MANAGER_MODE,
            created_by=display_name_or_default(profile.display_name),
            pinned=False,
            last_opened_at=utc_now(),
            latest_activity=idea.strip().splitlines()[0][:180] if idea.strip() else None,
            handoff_status="not_ready",
            source_type="existing_folder" if has_existing_files else "idea",
            source_path=normalized_workspace if has_existing_files else None,
        )
        db.add(project)
        db.flush()
        settings = self._project_settings(db, project)
        settings.provider = selected_provider
        settings.manager_model = profile.manager_model
        settings.default_worker_model = profile.default_worker_model
        settings.manager_reasoning_effort = profile.manager_reasoning_effort
        settings.default_worker_reasoning_effort = profile.default_worker_reasoning_effort
        settings.runner_mode = runner_mode or profile.default_runner_mode or DEFAULT_RUNNER_MODE
        settings.sandbox_mode = profile.sandbox_mode
        settings.approval_policy = profile.approval_policy
        settings.provider_endpoint = normalize_provider_endpoint(selected_provider, profile.provider_endpoint)
        settings.adapter_command, settings.adapter_args_json = normalize_provider_adapter_settings(
            selected_provider,
            profile.adapter_command,
            list(profile.adapter_args_json or []),
        )
        settings.workspace_widgets_json = []
        settings.approval_overrides_json = {}
        self._ensure_swarm_preferences(db, project)
        self._ensure_agent_archetypes(db)
        manager_agent = Agent(
            project_id=project.id,
            name="Manager AI",
            role="Project orchestration, planning, routing, and final handoff",
            kind="manager",
            status="idle",
            workspace_path=normalized_workspace,
            archetype="manager",
            mission="Coordinate the adaptive swarm and act as the single user-facing manager.",
            retire_when="Retire only when the project is archived or deleted.",
            failure_count=0,
            locked_paths_json=[],
        )
        db.add(manager_agent)
        db.flush()
        self._prime_workspace_context(db, project)
        playbook_service.suggest_playbook(db, project, persist=True)
        validation_coverage_service.recompute(db, project)
        self.events.publish(db, project.id, "project.created", {"project_id": project.id, "name": project.name})
        return project

    def update_settings(self, db: Session, project: Project, payload: ProjectSettingsUpdate) -> ProjectSettings:
        settings = self._ensure_project_settings(db, project)
        updates = payload.model_dump(exclude_unset=True)
        fields_set = set(getattr(payload, "model_fields_set", set(updates.keys())))

        provider_changed = "provider" in fields_set and payload.provider is not None
        if provider_changed:
            settings.provider = normalize_provider(payload.provider)
        if "manager_model" in fields_set:
            settings.manager_model = payload.manager_model.strip() if payload.manager_model and payload.manager_model.strip() else None
        if "default_worker_model" in fields_set:
            settings.default_worker_model = payload.default_worker_model.strip() if payload.default_worker_model and payload.default_worker_model.strip() else None
        if "manager_reasoning_effort" in fields_set:
            settings.manager_reasoning_effort = payload.manager_reasoning_effort
        if "default_worker_reasoning_effort" in fields_set:
            settings.default_worker_reasoning_effort = payload.default_worker_reasoning_effort
        if "per_role_model_overrides_json" in fields_set and payload.per_role_model_overrides_json is not None:
            settings.per_role_model_overrides_json = {
                key: value.strip()
                for key, value in payload.per_role_model_overrides_json.items()
                if key.strip() and value.strip()
            }
        if "per_role_reasoning_overrides_json" in fields_set and payload.per_role_reasoning_overrides_json is not None:
            settings.per_role_reasoning_overrides_json = {
                key: value
                for key, value in payload.per_role_reasoning_overrides_json.items()
                if key.strip() and value
            }
        if provider_changed or "provider_endpoint" in fields_set:
            endpoint_source = payload.provider_endpoint if "provider_endpoint" in fields_set else settings.provider_endpoint
            settings.provider_endpoint = normalize_provider_endpoint(settings.provider, endpoint_source)
        if provider_changed or "adapter_command" in fields_set or "adapter_args_json" in fields_set:
            command_source = payload.adapter_command if "adapter_command" in fields_set else settings.adapter_command
            args_source = payload.adapter_args_json if "adapter_args_json" in fields_set else list(settings.adapter_args_json or [])
            settings.adapter_command, settings.adapter_args_json = normalize_provider_adapter_settings(
                settings.provider,
                command_source,
                args_source,
            )
        if "runner_mode" in fields_set and payload.runner_mode is not None:
            settings.runner_mode = payload.runner_mode
            project.runner_mode = payload.runner_mode
        if "sandbox_mode" in fields_set and payload.sandbox_mode is not None:
            settings.sandbox_mode = payload.sandbox_mode
        if "approval_policy" in fields_set and payload.approval_policy is not None:
            settings.approval_policy = payload.approval_policy
        if "workspace_widgets_json" in fields_set and payload.workspace_widgets_json is not None:
            settings.workspace_widgets_json = validate_widget_types(
                payload.workspace_widgets_json,
                scope="project",
                field_name="workspace widgets",
            )
        if "approval_overrides_json" in fields_set and payload.approval_overrides_json is not None:
            settings.approval_overrides_json = dict(payload.approval_overrides_json or {})
        self.events.publish(
            db,
            project.id,
            "settings.updated",
            {
                "project_id": project.id,
                "provider": settings.provider,
                "runner_mode": settings.runner_mode,
                "manager_model": settings.manager_model or resolve_manager_settings(project, settings).effective_model_label,
                "default_worker_model": settings.default_worker_model or default_label(settings.provider),
            },
        )
        db.flush()
        return settings

    def open_project(self, db: Session, project: Project) -> Project:
        profile = self._app_profile(db)
        project.last_opened_at = utc_now()
        self._ensure_project_slug(project)
        profile.last_opened_at = utc_now()
        self._ensure_project_workspace(project)
        self._ensure_dry_run_workspace_seed(db, project)
        return project

    def update_project(self, db: Session, project: Project, *, name: str | None = None, idea: str | None = None) -> Project:
        changed = False
        if name is not None:
            cleaned_name = name.strip()
            if cleaned_name and cleaned_name != project.name:
                project.name = cleaned_name
                project.slug = self._slugify(cleaned_name)
                changed = True
        if idea is not None:
            cleaned_idea = idea.strip()
            if cleaned_idea and cleaned_idea != project.idea:
                project.idea = cleaned_idea
                changed = True
        if changed:
            project.latest_activity = self._project_latest_activity(db, project) or (project.idea.strip().splitlines()[0][:180] if project.idea.strip() else None)
            project.updated_at = utc_now()
            self.events.publish(
                db,
                project.id,
                "project.updated",
                {
                    "project_id": project.id,
                    "name": project.name,
                    "slug": project.slug,
                },
            )
        return project

    def list_manager_messages(self, db: Session, project: Project) -> list[dict[str, Any]]:
        messages = list(
            db.scalars(
                select(ManagerMessage)
                .where(ManagerMessage.project_id == project.id)
                .order_by(ManagerMessage.created_at.asc(), ManagerMessage.id.asc())
            )
        )
        return [self._serialize_manager_message(message) for message in messages]

    def list_pending_questions(self, db: Session, project: Project, *, mutate: bool = True) -> list[dict[str, Any]]:
        if mutate:
            self._auto_decide_due_questions(db, project)
        session = self._latest_session(db, project.id)
        if mutate and session is not None and session.status == "in_progress":
            self._sync_interview_question_mirror(db, project, session)
        questions = list(
            db.scalars(
                select(ManagerQuestion)
                .where(ManagerQuestion.project_id == project.id, ManagerQuestion.status == "pending")
                .order_by(ManagerQuestion.created_at.asc())
            )
        )
        return [self._serialize_question(question) for question in questions]

    def list_pending_approvals(self, db: Session, project: Project) -> list[dict[str, Any]]:
        approvals = list(
            db.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.project_id == project.id, ApprovalRequest.status == "pending")
                .order_by(ApprovalRequest.created_at.asc())
            )
        )
        return [self._serialize_approval(approval) for approval in approvals]

    def get_manager_queue(self, db: Session, project: Project, *, mutate: bool = True) -> dict[str, Any]:
        if mutate:
            self._auto_decide_due_questions(db, project)
        return self._manager_queue(db, project)

    async def get_project_action(self, db: Session, project: Project, *, mutate: bool = True) -> dict[str, Any]:
        settings = self._project_settings_preview(db, project)
        degraded_notices = await self._workspace_degraded_notices(project, settings)
        return self._derive_current_action(db, project, degraded_notices, mutate=mutate)

    async def list_project_actions(self, db: Session, project: Project, *, mutate: bool = True) -> list[dict[str, Any]]:
        settings = self._project_settings_preview(db, project)
        degraded_notices = await self._workspace_degraded_notices(project, settings)
        current = self._derive_current_action(db, project, degraded_notices, mutate=mutate)
        history = self._derive_action_history(db, project)
        return [current, *history]

    def resolve_project_action(
        self,
        db: Session,
        project: Project,
        action_id: str,
        *,
        decision: str,
        option_id: str | None = None,
        selected_text: str | None = None,
    ) -> dict[str, Any]:
        if action_id.startswith("question-"):
            question_id = int(action_id.split("-", 1)[1])
            if decision == "dismiss":
                question = db.get(ManagerQuestion, question_id)
                if not question or question.project_id != project.id:
                    raise ValueError("Question not found in this project")
                question.status = "cancelled"
                question.resolved_at = utc_now()
                self._record_manager_message(
                    db,
                    project,
                    role="system",
                    message_type="system_notice",
                    content_markdown="A manager question was dismissed by the user.",
                    related_agent_id=question.related_agent_id,
                    related_task_id=question.related_task_id,
                )
                self._publish_workspace_state(db, project.id)
                return self._serialize_question(question)
            if decision != "choose_option":
                raise ValueError("Questions can only be resolved with choose_option or dismiss.")
            question = self.answer_question(
                db,
                question_id,
                option_id=option_id or "",
                selected_text=selected_text or option_id or "",
                project_id=project.id,
            )
            return self._serialize_question(question)
        if action_id.startswith("approval-"):
            approval_id = int(action_id.split("-", 1)[1])
            if decision == "approve_once":
                return self._serialize_approval(self.approve_once(db, approval_id, project_id=project.id))
            if decision == "deny":
                return self._serialize_approval(self.deny_approval(db, approval_id, project_id=project.id))
            if decision == "allow_for_project":
                return self._serialize_approval(self.allow_approval_for_project(db, approval_id, project_id=project.id))
            raise ValueError("Approvals can only be approved, denied, or allowed for a project.")
        raise ValueError("Action not found")

    @staticmethod
    def _normalize_option_answer(
        options_json: list[dict[str, Any]] | None,
        option_id: str,
        selected_text: str | None,
    ) -> tuple[str, str]:
        normalized_option_id = (option_id or "").strip()
        if not normalized_option_id:
            raise ValueError("Option id is required")
        options = [item for item in list(options_json or []) if isinstance(item, dict)]
        option_label = next(
            (
                str(item.get("label")).strip()
                for item in options
                if str(item.get("id") or "").strip() == normalized_option_id and str(item.get("label") or "").strip()
            ),
            None,
        )
        if options:
            if option_label is None:
                raise ValueError("Option id is not valid for this question")
            return normalized_option_id, option_label
        normalized_selected_text = (selected_text or "").strip()
        if not normalized_selected_text:
            raise ValueError("Selected text is required")
        return normalized_option_id, normalized_selected_text

    async def get_project_workspace(self, db: Session, project: Project) -> dict[str, Any]:
        settings = self._project_settings_preview(db, project)
        swarm_preferences = self._swarm_preferences(project)
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        degraded_notices = await self._workspace_degraded_notices(project, settings)
        current_action = self._derive_current_action(db, project, degraded_notices, mutate=False)
        queue = self.get_manager_queue(db, project, mutate=False)
        reservations = self.list_reservations(db, project.id)
        swarm_plan = self._current_swarm_plan_record(db, project.id)
        widget_summary = await self.get_project_widget_summary(db, project)
        return {
            "project": self._serialize_project_card(db, project),
            "current_action": current_action,
            "action_history": self._derive_action_history(db, project),
            "manager_messages": self.list_manager_messages(db, project),
            "pending_question": next(iter(self.list_pending_questions(db, project, mutate=False)), None),
            "pending_approvals": self.list_pending_approvals(db, project),
            "agents": self._sorted_workspace_agents(db, project.id),
            "manager_queue": queue,
            "widgets": [item["widget_type"] for item in widget_summary["instances"]],
            "available_widgets": [item["widget_type"] for item in widget_summary["catalog"]],
            "widget_instances": widget_summary["instances"],
            "widget_data": widget_summary["data"],
            "widget_catalog": widget_summary["catalog"],
            "reservations": reservations,
            "task_summary": self._task_summary(db, project),
            "milestone_summary": self._milestone_summary(db, project),
            "workflow": self._workflow_summary(db, project, tasks),
            "overview": self._project_overview(db, project, tasks, current_action),
            "tasks": tasks,
            "activity_log": self._activity_log(db, project),
            "degraded_notices": degraded_notices,
            "swarm_preferences": self._serialize_swarm_preferences(swarm_preferences),
            "swarm_plan": self._serialize_swarm_plan(db, project, swarm_plan),
            "swarm_events": self.list_swarm_events(db, project)[:8],
        }

    def answer_question(self, db: Session, question_id: int, *, option_id: str, selected_text: str, project_id: int | None = None) -> ManagerQuestion:
        question = db.get(ManagerQuestion, question_id)
        if not question:
            raise ValueError("Question not found")
        if project_id is not None and question.project_id != project_id:
            raise ValueError("Question not found in this project")
        if question.status != "pending":
            return question
        normalized_option_id, normalized_selected_text = self._normalize_option_answer(question.options_json, option_id, selected_text)
        metadata = question.metadata_json if isinstance(question.metadata_json, dict) else {}
        if metadata.get("question_type") == "interview":
            session_id = int(metadata.get("interview_session_id") or 0)
            interview_question_id = int(metadata.get("interview_question_id") or 0)
            session = db.get(InterviewSession, session_id) if session_id else None
            if session is not None and interview_question_id:
                self.answer_interview(
                    db,
                    session,
                    interview_question_id,
                    normalized_option_id,
                    normalized_selected_text,
                    project_id=question.project_id,
                    sync_question_mirrors=False,
                )
                project = db.get(Project, question.project_id)
                interview_question = db.get(InterviewQuestion, interview_question_id)
                resolved = self._resolve_question(
                    db,
                    question,
                    option_id=interview_question.selected_option_id if interview_question is not None and interview_question.selected_option_id else normalized_option_id,
                    selected_text=interview_question.selected_text if interview_question is not None and interview_question.selected_text else normalized_selected_text,
                    status="answered",
                )
                if project is not None:
                    refreshed_session = db.get(InterviewSession, session_id)
                    if refreshed_session is not None and refreshed_session.status == "in_progress":
                        self._sync_interview_question_mirror(db, project, refreshed_session)
                return resolved
        return self._resolve_question(
            db,
            question,
            option_id=normalized_option_id,
            selected_text=normalized_selected_text,
            status="answered",
        )

    def auto_decide_question(self, db: Session, question_id: int, *, project_id: int | None = None) -> ManagerQuestion:
        question = db.get(ManagerQuestion, question_id)
        if not question:
            raise ValueError("Question not found")
        if project_id is not None and question.project_id != project_id:
            raise ValueError("Question not found in this project")
        if question.status != "pending":
            return question
        if question.impact == "high":
            raise ValueError("High-impact questions cannot auto-decide.")
        option = next(
            (
                item
                for item in (question.options_json or [])
                if item.get("label") == question.manager_recommendation or item.get("id") == question.manager_recommendation
            ),
            None,
        )
        if option is None and question.options_json:
            option = question.options_json[0]
        if option is None:
            raise ValueError("Question has no selectable options.")
        return self._resolve_question(
            db,
            question,
            option_id=str(option.get("id") or "auto"),
            selected_text=str(option.get("label") or question.manager_recommendation or "Manager default"),
            status="auto_decided",
        )

    def _resolve_approval(self, db: Session, approval: ApprovalRequest, *, status: str) -> ApprovalRequest:
        if approval.status != "pending":
            return approval
        approval.status = status
        approval.resolved_at = utc_now()
        approval.resolved_by = "user"
        project = db.get(Project, approval.project_id)
        if not project:
            raise ValueError("Project not found")
        if status == "allowed_for_project":
            if not security_service.may_allow_for_project(approval.risk_level):
                raise ValueError("High-risk approvals cannot be allowed for the whole project.")
            settings = self._ensure_project_settings(db, project)
            overrides = dict(settings.approval_overrides_json or {})
            overrides[self._approval_signature(approval)] = {
                "status": status,
                "title": approval.title,
                "request_type": approval.request_type,
                "cwd": approval.cwd,
            }
            settings.approval_overrides_json = overrides
        audit_decision = "approved" if status == "approved_once" else status
        security_service.log_audit(
            db,
            project=project,
            action_type=approval.request_type,
            action_summary=approval.title,
            risk_level=approval.risk_level,
            decision=audit_decision,
            decided_by="user",
            reason=approval.reason_short,
            metadata_json={"approval_id": approval.id, "cwd": approval.cwd, "request_type": approval.request_type},
        )
        self._record_approval_resolution_message(db, project, approval)
        self.events.publish(db, project.id, "approval_resolved", {"approval_id": approval.id, "status": approval.status})
        self._advance_dry_run_after_approval(db, project, approval)
        self._publish_workspace_state(db, project.id)
        return approval

    def approve_once(self, db: Session, approval_id: int, *, project_id: int | None = None) -> ApprovalRequest:
        approval = db.get(ApprovalRequest, approval_id)
        if not approval:
            raise ValueError("Approval not found")
        if project_id is not None and approval.project_id != project_id:
            raise ValueError("Approval not found in this project")
        return self._resolve_approval(db, approval, status="approved_once")

    def deny_approval(self, db: Session, approval_id: int, *, project_id: int | None = None) -> ApprovalRequest:
        approval = db.get(ApprovalRequest, approval_id)
        if not approval:
            raise ValueError("Approval not found")
        if project_id is not None and approval.project_id != project_id:
            raise ValueError("Approval not found in this project")
        return self._resolve_approval(db, approval, status="denied")

    def allow_approval_for_project(self, db: Session, approval_id: int, *, project_id: int | None = None) -> ApprovalRequest:
        approval = db.get(ApprovalRequest, approval_id)
        if not approval:
            raise ValueError("Approval not found")
        if project_id is not None and approval.project_id != project_id:
            raise ValueError("Approval not found in this project")
        return self._resolve_approval(db, approval, status="allowed_for_project")

    def update_workspace_widgets(self, db: Session, project: Project, widgets: list[str]) -> ProjectSettings:
        settings = self._ensure_project_settings(db, project)
        requested = validate_widget_types(
            widgets,
            scope="project",
            field_name="project widgets",
        )
        instances = {item.widget_type: item for item in self._project_widget_instances(db, project, settings)}
        for order_index, widget_type in enumerate(requested):
            instance = instances.get(widget_type)
            if instance is None:
                self.create_widget_instance(
                    db,
                    scope="project",
                    project=project,
                    widget_type=widget_type,
                    order_index=order_index,
                )
                instances = {item.widget_type: item for item in self._widget_instances_query(db, scope="project", project_id=project.id)}
                instance = instances[widget_type]
            instance.enabled = True
            instance.order_index = order_index
            instance.area = instance.area or str(WIDGET_CATALOG_BY_TYPE[widget_type]["default_area"])
        for widget_type, instance in instances.items():
            if widget_type not in requested:
                instance.enabled = False
        self._normalize_widget_order(db, scope="project", project_id=project.id)
        self._mirror_project_widget_legacy(settings, self._widget_instances_query(db, scope="project", project_id=project.id))
        self.events.publish(db, project.id, "widget_instances_updated", {"project_id": project.id, "widgets_updated": True})
        return settings

    async def generate_project_docs(self, db: Session, project: Project) -> dict[str, Any]:
        docs_dir = self._ensure_project_workspace(project)
        latest_plan_record = self._latest_plan(db, project.id)
        latest_session = self._latest_session(db, project.id)
        deterministic_plan = None
        if latest_plan_record and latest_plan_record.summary_json:
            deterministic_plan = ManagerPlan(
                refined_summary=latest_plan_record.summary_json.get("refined_summary", project.idea),
                mvp_scope=latest_plan_record.summary_json.get("mvp_scope", []),
                milestones=latest_plan_record.summary_json.get("milestones", []),
                recommended_architecture=latest_plan_record.summary_json.get("recommended_architecture", []),
                agent_roster=latest_plan_record.summary_json.get("agent_roster", []),
                task_breakdown=latest_plan_record.summary_json.get("task_breakdown", []),
                validation_plan=latest_plan_record.summary_json.get("validation_plan", []),
                risks=latest_plan_record.summary_json.get("risks", []),
                definition_of_done=latest_plan_record.summary_json.get("definition_of_done", []),
                content_markdown=latest_plan_record.content_markdown,
                summary_json=latest_plan_record.summary_json,
            )
        questions = list(sorted(latest_session.questions, key=lambda item: item.index)) if latest_session else []
        doc_update, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="docs.generate",
            objective="Generate or rewrite the local planning docs for the current project state.",
            response_schema=MANAGER_DOC_UPDATE_SCHEMA,
            payload={
                "project_name": project.name,
                "project_idea": project.idea,
                "interview_answers": [self._question_answer_text(question) for question in questions if self._question_answer_text(question)],
            },
            model_schema=ManagerDocUpdate,
            fallback_factory=lambda: self._deterministic_doc_update(project, questions, deterministic_plan),
        )
        files_written: list[str] = []
        for item in doc_update.files:
            target = resolve_relative_to_root(docs_dir, item.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item.content, encoding="utf-8")
            files_written.append(str(target.relative_to(docs_dir).as_posix()))
        docs_manifest_path(project).write_text(
            json.dumps(
                {
                    "generated_at": utc_now().isoformat(),
                    "files": sorted(files_written),
                    "manager_mode_used": manager_mode_used,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        project.status = "docs_ready"
        project.updated_at = utc_now()
        self.events.publish(
            db,
            project.id,
            "docs.generated",
            {"docs_path": str(docs_dir), "files": sorted(files_written), "manager_mode_used": manager_mode_used},
        )
        return {
            "docs_path": str(docs_dir),
            "files": sorted(files_written),
            "used_live_manager": manager_mode_used != "deterministic",
            "manager_mode_used": manager_mode_used,
        }

    async def _resolve_interview_turn(
        self,
        db: Session,
        project: Project,
        session: InterviewSession,
        *,
        action_name: str,
        objective: str,
    ) -> tuple[InterviewTurnPayload, str]:
        prompt_payload = await self._interview_context_payload(db, project, session)
        prompt_payload.update(
            {
                "question_budget": session.question_budget,
                "questions_asked": session.questions_asked,
                "questions_remaining": self._interview_remaining_budget(session),
                "batch_target": 0 if session.question_budget == 0 else min(5, max(self._interview_remaining_budget(session), 3)),
                "pending_categories": sorted(self._pending_interview_categories(session)),
                "used_categories": sorted(self._used_interview_categories(session)),
            }
        )
        interview_settings = resolve_manager_settings(project, self._project_settings(db, project))
        prompt_override = manager_interview_prompt(
            project,
            action=action_name,
            objective=objective,
            payload=prompt_payload,
            response_schema=MANAGER_INTERVIEW_SCHEMA,
            user_name=self._preferred_user_name(db, project),
            provider=interview_settings.provider,
            model=interview_settings.effective_model_label,
            reasoning_effort=interview_settings.effective_reasoning_label,
        )
        turn, mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name=action_name,
            objective=objective,
            response_schema=MANAGER_INTERVIEW_SCHEMA,
            payload=prompt_payload,
            model_schema=InterviewTurnPayload,
            fallback_factory=lambda: self._default_interview_turn(project, session),
            prompt_override=prompt_override,
        )
        return turn, self._interview_source_for_mode(mode_used)

    def _supersede_interview_sessions(self, db: Session, project: Project) -> None:
        previous_sessions = list(db.scalars(select(InterviewSession).where(InterviewSession.project_id == project.id)))
        for previous in previous_sessions:
            previous.status = "superseded"
            previous.stop_reason = previous.stop_reason or "Superseded by a newer interview session."
            for question in previous.questions:
                if question.status == "pending":
                    question.status = "superseded"
        db.flush()

    async def start_interview(self, db: Session, project: Project, question_budget: int | None, legacy_question_count: int | None = None) -> InterviewSession:
        budget = self._normalize_interview_budget(question_budget, legacy_question_count)
        self._supersede_interview_sessions(db, project)

        session = InterviewSession(
            project_id=project.id,
            question_count=budget,
            question_budget=budget,
            questions_asked=0,
            current_index=0,
            status="in_progress",
            manager_mode=project.manager_mode or DEFAULT_MANAGER_MODE,
            stopped_early=False,
            stop_reason=None,
            confidence_json={},
            known_facts_json={},
            unknowns_json={},
        )
        db.add(session)
        db.flush()

        project.status = "interview_in_progress"
        self.events.publish(
            db,
            project.id,
            "interview.started",
            {"session_id": session.id, "question_budget": budget, "manager_mode": session.manager_mode},
        )
        turn, question_source = await self._resolve_interview_turn(
            db,
            project,
            session,
            action_name="interview.strategy",
            objective="Analyze the project and generate the first adaptive interview batch only if more information is still needed.",
        )
        return self._apply_interview_turn(db, project, session, turn, question_source=question_source)

    async def generate_next_interview(self, db: Session, project: Project) -> InterviewSession:
        session = self._latest_session(db, project.id)
        if not session:
            raise ValueError("Interview session required before generating the next batch")
        if session.status in {"completed", "superseded"}:
            return session
        if self._pending_interview_questions(session):
            return self._refresh_interview_session_state(session, project=project)
        if self._interview_remaining_budget(session) <= 0:
            return self._complete_interview_session(
                db,
                session,
                project,
                stop_reason=session.stop_reason or "Question budget reached.",
                stopped_early=False,
            )
        turn, question_source = await self._resolve_interview_turn(
            db,
            project,
            session,
            action_name="interview.next_batch",
            objective="Update the project understanding from prior answers and decide whether another small question batch is still necessary.",
        )
        return self._apply_interview_turn(db, project, session, turn, question_source=question_source)

    def answer_interview(
        self,
        db: Session,
        session: InterviewSession,
        question_id: int,
        option_id: str,
        selected_text: str,
        *,
        custom_answer: str | None = None,
        project_id: int | None = None,
        sync_question_mirrors: bool = True,
    ) -> InterviewSession:
        question = db.get(InterviewQuestion, question_id)
        if not question or question.session_id != session.id:
            raise ValueError("Question not found")
        canonical_project_id = question.project_id or session.project_id
        if project_id is not None and canonical_project_id != project_id:
            raise ValueError("Question not found in this project")
        if question.status == "answered":
            raise ValueError("Question was already answered")

        normalized_option_id, normalized_selected_text = self._normalize_option_answer(question.options_json, option_id, selected_text)

        project = db.get(Project, session.project_id)
        if not project:
            raise ValueError("Project not found")
        understanding = self._ensure_project_understanding(db, project)

        question.project_id = canonical_project_id
        question.selected_option = normalized_option_id
        question.selected_option_id = normalized_option_id
        question.selected_text = normalized_selected_text
        question.custom_answer = custom_answer.strip() if custom_answer and custom_answer.strip() else None
        question.status = "answered"
        question.answered_at = utc_now()
        question.rationale = f"Answered during adaptive interview: {self._question_answer_text(question) or normalized_selected_text}"

        self._append_local_answer_to_understanding(understanding, question)
        self._mirror_session_understanding(session, understanding)
        self._refresh_interview_session_state(session, project=project)
        db.flush()

        if not self._pending_interview_questions(session) and session.stop_reason and self._interview_remaining_budget(session) > 0:
            self._complete_interview_session(
                db,
                session,
                project,
                stop_reason=session.stop_reason,
                stopped_early=True,
            )

        if self._interview_remaining_budget(session) <= 0 and not self._pending_interview_questions(session):
            self._complete_interview_session(
                db,
                session,
                project,
                stop_reason=session.stop_reason or "Question budget reached.",
                stopped_early=False,
            )
        elif sync_question_mirrors:
            self._sync_interview_question_mirror(db, project, session)

        self.events.publish(
            db,
            session.project_id,
            "interview.answered",
            {
                "session_id": session.id,
                "question_id": question_id,
                "option_id": option_id,
                "category": question.category,
                "custom_answer": question.custom_answer,
            },
        )
        return session

    def finish_interview(self, db: Session, project: Project) -> InterviewSession:
        session = self._latest_session(db, project.id)
        if not session:
            raise ValueError("Interview session not found")
        if session.status == "completed":
            return session
        return self._complete_interview_session(
            db,
            session,
            project,
            stop_reason=session.stop_reason or "Interview finished with the current project understanding.",
            stopped_early=self._interview_remaining_budget(session) > 0,
        )

    def get_project_understanding(self, project: Project) -> dict[str, Any]:
        understanding = self._project_understanding(project)
        return self._serialize_understanding_record(project, understanding)

    async def generate_plan(self, db: Session, project: Project, action_bias: str | None = None, note: str | None = None) -> Plan:
        latest_session = self._latest_session(db, project.id)
        if not latest_session:
            raise ValueError("Interview session required before plan generation")
        questions = list(sorted(latest_session.questions, key=lambda item: item.index))
        understanding = self._project_understanding(project)
        manager_plan, _ = await self._resolve_manager_model(
            db,
            project,
            action_name="plan.generate",
            objective="Synthesize the interview into a practical MVP plan.",
            response_schema=MANAGER_PLAN_SCHEMA,
            payload={
                "project_name": project.name,
                "project_idea": project.idea,
                "answers": [self._question_answer_text(question) for question in questions if self._question_answer_text(question)],
                "understanding_summary": self._build_interview_summary(project, understanding),
                "known_facts": dict(understanding.known_facts_json or {}),
                "unknowns": dict(understanding.unknowns_json or {}),
                "assumptions": list(understanding.assumptions_json or []),
                "constraints": list(understanding.constraints_json or []),
                "confidence_by_category": dict(understanding.confidence_by_category_json or {}),
                "intelligence_layer": planning_intelligence_service.build_context(db, project),
                "action_bias": action_bias,
                "note": note,
            },
            model_schema=ManagerPlan,
            fallback_factory=lambda: self._deterministic_plan(db, project, questions, understanding, action_bias=action_bias, note=note),
        )
        next_version = (db.scalar(select(func.max(Plan.version)).where(Plan.project_id == project.id)) or 0) + 1
        for old_plan in db.scalars(select(Plan).where(Plan.project_id == project.id)):
            old_plan.status = "superseded"
        plan = Plan(
            project_id=project.id,
            version=next_version,
            content_markdown=manager_plan.content_markdown,
            status="pending_approval",
            summary_json=manager_plan.summary_json,
        )
        db.add(plan)
        project.status = "plan_ready"
        risk_service.register_plan_risks(db, project, manager_plan.risks)
        validation_coverage_service.recompute(db, project)
        self.events.publish(db, project.id, "plan.generated", {"plan_id": plan.id, "version": next_version})
        return plan

    def initialize_build_roster(self, db: Session, project: Project) -> list[Agent]:
        existing_workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker")))
        if existing_workers:
            return existing_workers
        preferences = self._ensure_swarm_preferences(db, project)
        current_plan = self._current_swarm_plan_record(db, project.id)
        if current_plan is None:
            payload = self._deterministic_swarm_plan(
                project,
                preferences,
                self._workspace_manifest_summary(project),
                self._project_understanding(project),
                self._latest_plan(db, project.id),
            )
            approval_required = payload.recommended_agent_count > preferences.require_approval_above_agent_count
            current_plan = self._persist_swarm_plan_payload(
                db,
                project,
                preferences,
                payload,
                approved_by_user=not approval_required,
                status="pending_approval" if approval_required else "approved",
            )
            if not approval_required:
                current_plan.approved_by_user = True
        if self._swarm_approval_required(current_plan, preferences) and not current_plan.approved_by_user and project.runner_mode != "dry_run":
            return []
        self._sync_agents_to_swarm_plan(db, project, current_plan, activate_deferred=project.runner_mode == "dry_run")
        return list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker").order_by(Agent.id.asc())))

    async def generate_tasks(self, db: Session, project: Project) -> tuple[list[Task], str]:
        latest_plan = self._latest_plan(db, project.id)
        if latest_plan is None and project.source_type != "idea":
            self._prime_workspace_context(db, project)
            decomposition = self._deterministic_task_decomposition(db, project, latest_plan)
            tasks = self._upsert_tasks_from_decomposition(db, project, decomposition)
            self.events.publish(db, project.id, "tasks.generated", {"count": len(tasks), "manager_mode_used": "deterministic"})
            self._write_task_board_doc(db, project)
            return tasks, "deterministic"
        decomposition, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="tasks.decompose",
            objective="Break the approved plan into milestone-based worker tasks with non-overlapping path hints.",
            response_schema=MANAGER_TASK_DECOMPOSITION_SCHEMA,
            payload={
                "plan_summary": latest_plan.summary_json if latest_plan else {},
                "plan_markdown": latest_plan.content_markdown if latest_plan else "",
                "intelligence_layer": planning_intelligence_service.build_context(db, project),
            },
            model_schema=ManagerTaskDecomposition,
            fallback_factory=lambda: self._deterministic_task_decomposition(db, project, latest_plan),
        )
        tasks = self._upsert_tasks_from_decomposition(db, project, decomposition)
        self.events.publish(db, project.id, "tasks.generated", {"count": len(tasks), "manager_mode_used": manager_mode_used})
        self._write_task_board_doc(db, project)
        return tasks, manager_mode_used

    def _upsert_tasks_from_decomposition(self, db: Session, project: Project, decomposition: ManagerTaskDecomposition) -> list[Task]:
        existing = {task.title: task for task in db.scalars(select(Task).where(Task.project_id == project.id))}
        ordered: list[Task] = []
        index_map: dict[int, Task] = {}
        for index, item in enumerate(decomposition.tasks, start=1):
            task = existing.get(item.title)
            created = task is None
            if task is None:
                task = Task(project_id=project.id, title=item.title, goal=item.goal, scope=item.scope)
                db.add(task)
            if created or task.status in {"backlog", "assigned", "waiting_on_paths"}:
                task.goal = item.goal
                task.scope = item.scope
                task.agent_role = item.agent_role
                task.milestone = item.milestone
                task.allowed_paths_json = item.allowed_paths
                task.forbidden_paths_json = item.forbidden_paths
                task.validation_steps_json = item.validation_steps
                task.success_criteria_json = item.success_criteria
                task.estimated_complexity = item.estimated_complexity
                task.priority = item.priority
                task.status = item.status
                task.waiting_reason = None
            ordered.append(task)
            index_map[index] = task
        db.flush()
        for index, item in enumerate(decomposition.tasks, start=1):
            resolved = [index_map[dependency].id for dependency in item.dependencies if dependency in index_map]
            index_map[index].dependencies_json = resolved
        db.flush()
        return ordered

    async def approve_plan(self, db: Session, project: Project, action: str, note: str | None) -> Plan:
        latest_plan = self._latest_plan(db, project.id)
        if not latest_plan:
            raise ValueError("Plan not found")
        if action != "approve_build":
            return await self.generate_plan(db, project, action_bias=action, note=note)

        latest_plan.status = "approved"
        project.status = "building"
        if self._current_swarm_plan_record(db, project.id) is None:
            await self.create_swarm_plan(
                db,
                project,
                goal=f"Prepare the worker swarm for the approved build plan for {project.name}.",
                milestone_id=latest_plan.id,
            )
        current_swarm_plan = self._current_swarm_plan_record(db, project.id)
        preferences = self._ensure_swarm_preferences(db, project)
        if current_swarm_plan is not None and not self._swarm_approval_required(current_swarm_plan, preferences):
            self.initialize_build_roster(db, project)
        await self.generate_tasks(db, project)
        self.events.publish(db, project.id, "plan.approved", {"plan_id": latest_plan.id, "action": action})
        try:
            self.spawn_swarm_agents(db, project)
            await self.start_idle_agents(db, project)
        except ValueError:
            self._record_manager_message(
                db,
                project,
                role="manager",
                message_type="system_notice",
                content_markdown="Build plan approved, but the current swarm strategy still needs explicit approval before Mission Control spawns the full worker set.",
                metadata_json={"source": "swarm_plan", "needs_approval": True},
            )
        return latest_plan

    def _agent_task_match_score(self, agent: Agent, task: Task) -> int:
        if agent.kind != "worker":
            return 0
        if not task.agent_role:
            return 50
        agent_name = agent.name.lower()
        agent_role = agent.role.lower()
        agent_archetype = (agent.archetype or "").lower()
        task_role = task.agent_role.lower()
        allowed_paths = {path.lower() for path in (task.allowed_paths_json or [])}
        if task_role in agent_name or task_role in agent_role or task_role in agent_archetype:
            return 100
        if "validation" in task_role:
            if "validation" in agent_role or agent_archetype in {"test", "reviewer", "release_handoff"}:
                return 95
            if agent_archetype in {"backend", "feature"} or "backend" in agent_role:
                return 75
            if agent_archetype == "planner":
                return 65
        if "docs" in task_role or "handoff" in task_role:
            if agent_archetype in {"docs", "release_handoff", "reviewer"} or "docs" in agent_role:
                return 90
            if agent_archetype == "planner":
                return 55
        if "security" in task_role:
            return 90 if agent_archetype == "security" else 0
        if "review" in task_role:
            return 90 if agent_archetype == "reviewer" or "review" in agent_role else 0
        if "secondary" in task_role:
            return 80 if "secondary" in agent_role or "agent b" in agent_name else 0
        if "primary" in task_role:
            return 80 if "primary" in agent_role or "agent a" in agent_name else 0
        if task_role in agent_role or task_role in agent_name:
            return 85
        if allowed_paths & {"src", "app", "lib", "server", "package"}:
            if agent_archetype in {"backend", "feature"} or "backend" in agent_role:
                return 70
            if agent_archetype == "planner":
                return 55
        if allowed_paths & {"tests", "test"}:
            if agent_archetype in {"test", "reviewer"}:
                return 80
            if agent_archetype in {"backend", "planner"}:
                return 60
        if allowed_paths & {"docs", "mission-control"} and (agent_archetype in {"docs", "release_handoff"} or "docs" in agent_role):
            return 70
        if allowed_paths & {"ui", "frontend"} and (agent_archetype == "frontend" or "frontend" in agent_role):
            return 70
        return 0

    def _agent_matches_task(self, agent: Agent, task: Task) -> bool:
        return self._agent_task_match_score(agent, task) > 0

    def _dependencies_met(self, db: Session, task: Task) -> bool:
        if not task.dependencies_json:
            return True
        dependency_tasks = list(db.scalars(select(Task).where(Task.id.in_(task.dependencies_json))))
        return len(dependency_tasks) == len(task.dependencies_json) and all(item.status == "done" for item in dependency_tasks)

    def _is_git_workspace(self, project: Project) -> bool:
        return (Path(project.workspace_path) / ".git").exists()

    def _active_reservations(self, db: Session, project_id: int) -> list[PathReservation]:
        return list(
            db.scalars(
                select(PathReservation)
                .where(PathReservation.project_id == project_id, PathReservation.released_at.is_(None))
                .order_by(PathReservation.id.asc())
            )
        )

    def _refresh_agent_locks(self, db: Session, project_id: int) -> None:
        reservations = self._active_reservations(db, project_id)
        reserved_by_agent: dict[int, list[str]] = {}
        for reservation in reservations:
            reserved_by_agent.setdefault(reservation.agent_id, []).append(reservation.path)
        for agent in db.scalars(select(Agent).where(Agent.project_id == project_id, Agent.kind == "worker")):
            agent.locked_paths_json = reserved_by_agent.get(agent.id, [])

    def _reserve_task_paths(self, db: Session, project: Project, agent: Agent, task: Task) -> None:
        self._release_reservations(db, project.id, task_id=task.id, agent_id=agent.id, publish=False)
        for path in task.allowed_paths_json:
            db.add(PathReservation(project_id=project.id, task_id=task.id, agent_id=agent.id, path=path))
        db.flush()
        self._refresh_agent_locks(db, project.id)
        self.events.publish(db, project.id, "paths.reserved", {"agent_id": agent.id, "task_id": task.id, "paths": task.allowed_paths_json})

    def _release_reservations(
        self,
        db: Session,
        project_id: int,
        *,
        task_id: int | None = None,
        agent_id: int | None = None,
        publish: bool = True,
    ) -> None:
        query = select(PathReservation).where(PathReservation.project_id == project_id, PathReservation.released_at.is_(None))
        if task_id is not None:
            query = query.where(PathReservation.task_id == task_id)
        if agent_id is not None:
            query = query.where(PathReservation.agent_id == agent_id)
        released = list(db.scalars(query))
        if not released:
            return
        now = utc_now()
        for reservation in released:
            reservation.released_at = now
        self._refresh_agent_locks(db, project_id)
        if publish:
            self.events.publish(
                db,
                project_id,
                "paths.released",
                {"task_id": task_id, "agent_id": agent_id, "paths": [reservation.path for reservation in released]},
            )

    def list_reservations(self, db: Session, project_id: int) -> list[PathReservation]:
        return self._active_reservations(db, project_id)

    def _set_waiting_on_paths(self, db: Session, project: Project, task: Task, workers: list[Agent]) -> None:
        blockers = conflicting_agents(task, workers)
        if not blockers:
            task.waiting_reason = None
            if task.status == "waiting_on_paths":
                task.status = "backlog"
            return
        task.status = "waiting_on_paths"
        task.waiting_reason = "; ".join(
            f"{other.name} owns {', '.join(other.locked_paths_json or [])}" for other in blockers
        )
        self.events.publish(
            db,
            project.id,
            "task.waiting_on_paths",
            {"task_id": task.id, "blocking_agents": [other.id for other in blockers], "reason": task.waiting_reason},
        )

    def _candidate_task_score(self, db: Session, project: Project, agent: Agent, task: Task) -> tuple[int, int, int, int]:
        role_match = 1 if self._agent_matches_task(agent, task) else 0
        dependency_ready = 1 if self._dependencies_met(db, task) else 0
        path_overlap = 0
        if task.allowed_paths_json and agent.locked_paths_json:
            path_overlap = 1 if paths_conflict(agent.locked_paths_json, task.allowed_paths_json) else 0
        review_bias = 1 if agent.archetype in {"reviewer", "test", "security"} and task.status == "needs_review" else 0
        waiting_penalty = 1 if task.status == "waiting_on_paths" else 0
        return (
            role_match,
            dependency_ready,
            review_bias - waiting_penalty,
            -int(task.priority or 0) + path_overlap,
        )

    def _find_next_safe_task(self, db: Session, project: Project, agent: Agent) -> Task | None:
        workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker").order_by(Agent.id.asc())))
        candidates: list[tuple[tuple[int, int, int, int], Task]] = []
        blocked_by_paths: list[Task] = []
        for task in db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())):
            if task.id == agent.current_task_id:
                continue
            if task.status not in TASK_STARTABLE_STATUSES:
                continue
            if not self._agent_matches_task(agent, task):
                continue
            if not self._dependencies_met(db, task):
                continue
            if can_assign_task(agent, task, workers, self._is_git_workspace(project)):
                candidates.append((self._candidate_task_score(db, project, agent, task), task))
            else:
                blocked_by_paths.append(task)
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]
        for task in blocked_by_paths:
            self._set_waiting_on_paths(db, project, task, workers)
        return None

    def _activate_ready_deferred_specs(self, db: Session, project: Project) -> int:
        plan = self._current_swarm_plan_record(db, project.id)
        if plan is None or plan.status not in {"approved", "active"}:
            return 0
        specs = self._swarm_specs_for_plan(db, plan.id)
        completed_task_count = int(
            db.scalar(select(func.count(Task.id)).where(Task.project_id == project.id, Task.status == "done"))
            or 0
        )
        changed = 0
        for spec in specs:
            if spec.status != "deferred":
                continue
            phase = str(spec.spawn_phase or "")
            if phase in {"after_architecture", "after_path_mapping"} and completed_task_count >= 1:
                spec.status = "planned"
                changed += 1
            elif phase in {"after_first_slice", "after_backend_stabilizes", "after_subsystem_progress"} and completed_task_count >= 2:
                spec.status = "planned"
                changed += 1
            elif phase == "validation" and completed_task_count >= 3:
                spec.status = "planned"
                changed += 1
        if changed:
            self._record_swarm_event(
                db,
                project,
                event_type="strategy_changed",
                message=f"Mission Control activated {changed} deferred swarm spec(s) after upstream progress unblocked them.",
                swarm_plan_id=plan.id,
                metadata_json={"activated_deferred_specs": changed},
            )
        return changed

    async def start_idle_agents(self, db: Session, project: Project) -> None:
        if project.status == "paused":
            return
        workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker").order_by(Agent.id.asc())))
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        is_git_workspace = self._is_git_workspace(project)
        self._activate_ready_deferred_specs(db, project)
        for task in tasks:
            if task.status in TASK_STARTABLE_STATUSES and not self._dependencies_met(db, task):
                if task.assigned_agent_id is None:
                    task.status = "backlog"
                task.waiting_reason = "Waiting for task dependencies to finish."
        for agent in workers:
            if agent.status not in {"idle", "waiting", "done", "stopped"}:
                continue
            candidate = self._find_next_safe_task(db, project, agent)
            if candidate is not None:
                await self.start_agent_task(db, project, agent, candidate)
                continue
            for task in tasks:
                if task.status in TASK_STARTABLE_STATUSES and self._agent_matches_task(agent, task) and self._dependencies_met(db, task) and not can_assign_task(agent, task, workers, is_git_workspace):
                    self._set_waiting_on_paths(db, project, task, workers)
                    agent.status = "waiting"
                    agent.current_action = "Waiting for another worker to release overlapping path ownership."
                    break

    async def start_agent_task(self, db: Session, project: Project, agent: Agent, task: Task) -> AgentRun:
        settings_record = self._project_settings(db, project)
        resolved_settings = resolve_worker_settings(project, settings_record, agent)
        latest_plan = self._latest_plan(db, project.id)
        context_pack_payload = context_pack_service.build_context_pack(db, project, agent_id=agent.id, task_id=task.id)
        runner = await self.runners.get_runner_for_settings(resolved_settings)
        context = RunnerContext(
            project=project,
            agent=agent,
            task=task,
            docs_path=project.docs_path or str(self._project_docs_dir(project)),
            plan_markdown=latest_plan.content_markdown if latest_plan else None,
            context_pack_markdown=context_pack_service.render_markdown(context_pack_payload),
            settings=self._runner_settings_payload(resolved_settings),
        )
        handle = await runner.start_task(context)
        agent.status = "starting"
        agent.current_task_id = task.id
        self._cache_agent_run_profile(agent, resolved_settings, runner_type=handle.runner_type, action=task.title)
        task.status = "working"
        task.assigned_agent_id = agent.id
        task.waiting_reason = None
        self._reserve_task_paths(db, project, agent, task)
        run = AgentRun(
            agent_id=agent.id,
            task_id=task.id,
            runner_type=handle.runner_type,
            process_ref=handle.id,
            status="starting",
            logs_path=handle.logs_path,
            stdout_path=handle.stdout_path,
            stderr_path=handle.stderr_path,
            event_log_path=handle.event_log_path,
            manager_action="worker_task",
            effective_settings_json=resolved_run_settings_payload(resolved_settings),
        )
        db.add(run)
        db.flush()
        self.events.publish(
            db,
            project.id,
            "agent.started",
            {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "task_id": task.id,
                "task_title": task.title,
                "runner": handle.runner_type,
                "reserved_paths": task.allowed_paths_json,
                "effective_settings": resolved_run_settings_payload(resolved_settings),
            },
        )
        self.run_input_snapshots[run.id] = self._task_workspace_snapshot(project, task)
        self.active_monitors[run.id] = asyncio.create_task(self._monitor_run(run.id))
        return run

    async def _monitor_run(self, run_id: int) -> None:
        from db import session_scope

        try:
            while True:
                await asyncio.sleep(0.6)
                with session_scope() as db:
                    run = db.get(AgentRun, run_id)
                    if not run:
                        return
                    agent = db.get(Agent, run.agent_id)
                    if not agent:
                        return
                    project = db.get(Project, agent.project_id)
                    if not project:
                        return
                    runner = await self.runners.get_runner(run.runner_type)
                    events = await runner.read_events(run.process_ref or "")
                    for event in events:
                        self.events.publish_isolated(
                            project.id,
                            f"runner.{event.get('type', 'unknown')}",
                            {"agent_id": agent.id, "task_id": run.task_id, "event": event},
                        )
                        if event.get("type") == "thread.started":
                            agent.session_ref = event.get("thread_id")
                        if event.get("type") == "turn.started":
                            agent.status = "working"
                            run.status = "working"
                        effective_settings = event.get("effective_settings")
                        if isinstance(effective_settings, dict):
                            run.effective_settings_json = effective_settings
                            provider_name = str(effective_settings.get("provider") or settings_summary(self._project_settings(db, project)).get("provider") or "codex")
                            agent.active_model = str(effective_settings.get("model") or agent.active_model or default_label(provider_name))
                            agent.active_reasoning_effort = str(effective_settings.get("reasoning_effort") or agent.active_reasoning_effort or default_label(provider_name))
                            agent.active_runner_type = run.runner_type
                        item = event.get("item")
                        if isinstance(item, dict) and item.get("type") == "agent_message":
                            report = runner.try_parse_report(item.get("text"))
                            if report:
                                run.report_json = report
                        if event.get("type") in {"turn.completed", "turn.failed", "error"}:
                            run.status = await runner.get_status(run.process_ref or "")
                    status = await runner.get_status(run.process_ref or "")
                    if hasattr(runner, "runs") and run.process_ref in getattr(runner, "runs"):
                        state = getattr(runner, "runs")[run.process_ref]
                        run.exit_code = getattr(state, "exit_code", None)
                        if getattr(state, "session_ref", None) and not agent.session_ref:
                            agent.session_ref = state.session_ref
                    if status in {"done", "error", "blocked", "needs_review", "stopped"}:
                        await self._finalize_run(db, project, agent, run, status)
                        return
        finally:
            self.active_monitors.pop(run_id, None)

    async def _finalize_run(self, db: Session, project: Project, agent: Agent, run: AgentRun, status: str) -> None:
        task = db.get(Task, run.task_id) if run.task_id else None
        if task:
            report = self._build_synthetic_worker_report(agent, task, status, run.report_json)
            report = self._verify_worker_report_evidence(project, task, report, self.run_input_snapshots.pop(run.id, None))
            await self.ingest_worker_report(db, run, report)
            return
        self.run_input_snapshots.pop(run.id, None)
        agent.status = "waiting"
        agent.current_action = None
        run.status = status
        self.events.publish(db, project.id, "agent.finished", {"agent_id": agent.id, "task_id": run.task_id, "status": status})

    async def ingest_worker_report(self, db: Session, run: AgentRun, report: WorkerReport) -> ManagerWorkerDecision:
        if run.finished_at is not None and run.report_json:
            raise ValueError("Worker report already recorded for this run.")
        agent = db.get(Agent, run.agent_id)
        if not agent:
            raise ValueError("Agent not found")
        project = db.get(Project, agent.project_id)
        if not project:
            raise ValueError("Project not found")
        task = db.get(Task, run.task_id) if run.task_id else None
        run.report_json = _dump_model(report)
        run.status = report.status
        run.finished_at = run.finished_at or utc_now()
        agent.current_task_id = None
        agent.last_report_summary = report.summary
        agent.current_action = None
        if report.status == "done":
            agent.failure_count = 0
            if task:
                task.failure_count = 0
                task.status = "done"
        elif report.status == "needs_review":
            agent.failure_count = 0
            if task:
                task.status = "needs_review"
        else:
            agent.failure_count += 1
            if task:
                task.failure_count += 1
                task.status = "blocked" if report.status == "blocked" else "assigned"
        self._release_reservations(db, project.id, task_id=task.id if task else None, agent_id=agent.id)
        agent.status = "waiting"
        duration_seconds = None
        started_at = self._normalize_report_datetime(run.started_at)
        finished_at = self._normalize_report_datetime(run.finished_at)
        if started_at and finished_at:
            duration_seconds = max(0, int((finished_at - started_at).total_seconds()))
        outcome = {
            "done": "success",
            "needs_review": "needs_review",
            "blocked": "blocked",
            "error": "failed",
        }.get(report.status, "unknown")
        failure_summary = None
        if report.blockers:
            failure_summary = report.blockers[0]
        elif report.risks and report.status != "done":
            failure_summary = report.risks[0]
        reputation_service.record(
            db,
            {
                "project_id": project.id,
                "agent_archetype": agent.archetype or (task.agent_role if task else None) or "generalist",
                "agent_name": agent.name,
                "provider": (run.effective_settings_json or {}).get("provider") if isinstance(run.effective_settings_json, dict) else None,
                "model": (run.effective_settings_json or {}).get("model") if isinstance(run.effective_settings_json, dict) else agent.active_model,
                "runner_mode": run.runner_type or project.runner_mode,
                "task_category": (task.agent_role or task.title) if task else "general",
                "task_id": task.id if task else None,
                "outcome": outcome,
                "duration_seconds": duration_seconds,
                "review_passed": True if report.status == "done" else False if report.status == "needs_review" else None,
                "tests_passed": True if report.tests_run and report.status == "done" else False if report.tests_run else None,
                "failure_summary": failure_summary,
            },
        )
        if report.status in {"blocked", "error"} and task is not None:
            risk_service.create_risk(
                db,
                project,
                {
                    "title": f"{task.title} stalled",
                    "description": report.summary,
                    "severity": "high" if report.status == "error" else "medium",
                    "likelihood": "medium",
                    "mitigation": failure_summary or "Manager should route a fix or de-scope the blocker.",
                    "status": "open",
                    "related_task_id": task.id,
                    "owner_agent_id": agent.id,
                    "created_by": "agent",
                },
            )
        validation_coverage_service.recompute(db, project)
        self.events.publish(db, project.id, "worker.report.received", {"run_id": run.id, "task_id": run.task_id, "status": report.status, "summary": report.summary})
        decision, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="worker.decide_next",
            objective="Decide the next action after a worker completion report.",
            response_schema=MANAGER_WORKER_DECISION_SCHEMA,
            payload={
                "agent": agent.name,
                "task": {"id": task.id if task else None, "title": task.title if task else None},
                "report": _dump_model(report),
                "open_tasks": [
                    {"id": item.id, "title": item.title, "status": item.status}
                    for item in db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc()))
                ],
                "intelligence_layer": planning_intelligence_service.build_context(db, project),
            },
            model_schema=ManagerWorkerDecision,
            fallback_factory=lambda: self._deterministic_worker_decision(db, project, agent, task, report),
        )
        await self._apply_worker_decision(db, project, agent, task, decision)
        self.events.publish(
            db,
            project.id,
            "manager.worker_decision",
            {"run_id": run.id, "decision": _dump_model(decision), "manager_mode_used": manager_mode_used},
        )
        await self._maybe_finalize_handoff(db, project)
        if project.status != "handoff_ready":
            await self.start_idle_agents(db, project)
        self._write_task_board_doc(db, project)
        return decision

    async def _apply_worker_decision(self, db: Session, project: Project, agent: Agent, task: Task | None, decision: ManagerWorkerDecision) -> None:
        immediate_task: Task | None = None
        agent.current_action = decision.summary_markdown
        if decision.decision_type == "assign_next_task" and decision.task_id:
            immediate_task = db.get(Task, decision.task_id)
            if immediate_task:
                immediate_task.status = "assigned"
                immediate_task.assigned_agent_id = decision.assign_to_agent_id or agent.id
        elif decision.decision_type == "request_fix":
            if decision.follow_up_title and decision.follow_up_goal:
                fix_task = Task(
                    project_id=project.id,
                    assigned_agent_id=decision.assign_to_agent_id,
                    title=decision.follow_up_title,
                    goal=decision.follow_up_goal,
                    scope="Resolve a blocker or error before the main flow can continue.",
                    agent_role="Validation, docs, and handoff" if decision.assign_to_agent_id else "Primary implementation",
                    milestone=(task.milestone if task else "Milestone 2 - Validation and handoff") if task else "Milestone 2 - Validation and handoff",
                    allowed_paths_json=task.allowed_paths_json[:] if task else ["docs", "tests"],
                    forbidden_paths_json=task.forbidden_paths_json[:] if task else [],
                    validation_steps_json=["Confirm the blocker is removed", "Record what changed"],
                    success_criteria_json=["The blocking issue is resolved or clearly isolated."],
                    estimated_complexity="small",
                    dependencies_json=[],
                    status="backlog",
                    priority=(task.priority + 1 if task else 50),
                )
                db.add(fix_task)
            elif task and task.failure_count < 2:
                task.status = "assigned"
                task.waiting_reason = "Manager requested one fix retry."
                immediate_task = task
            elif task:
                task.status = "blocked"
        elif decision.decision_type == "mark_blocked" and task:
            task.status = "blocked"
        elif decision.decision_type == "mark_done" and task:
            task.status = "done"
        elif decision.decision_type == "retire_agent":
            agent.status = "done"
        elif decision.decision_type == "escalate_to_user":
            agent.status = "waiting"
            self.events.publish(db, project.id, "manager.escalation", {"agent_id": agent.id, "task_id": task.id if task else None, "message": decision.escalation_message or decision.summary_markdown})
        else:
            agent.status = "waiting"

        if immediate_task and agent.status in {"idle", "waiting", "done", "stopped"}:
            workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker")))
            if can_assign_task(agent, immediate_task, workers, self._is_git_workspace(project)) and self._dependencies_met(db, immediate_task):
                await self.start_agent_task(db, project, agent, immediate_task)

    async def _maybe_finalize_handoff(self, db: Session, project: Project) -> None:
        open_tasks = list(db.scalars(select(Task).where(Task.project_id == project.id, Task.status.in_(list(TASK_OPEN_STATUSES)))))
        if open_tasks:
            return
        settings_record = self._project_settings(db, project)
        project_agent_ids = [project_agent.id for project_agent in db.scalars(select(Agent).where(Agent.project_id == project.id))]
        completed_runs = list(db.scalars(select(AgentRun).where(AgentRun.agent_id.in_(project_agent_ids))))
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        handoff, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="handoff.generate",
            objective="Generate the final handoff summary, run instructions, and known limitations.",
            response_schema=MANAGER_HANDOFF_SCHEMA,
            payload={
                "tasks": [{"title": task.title, "status": task.status} for task in tasks],
                "runs": [run.report_json or {} for run in completed_runs],
            },
            model_schema=ManagerHandoff,
            fallback_factory=lambda: self._deterministic_handoff(project, tasks, completed_runs),
        )
        project.status = "handoff_ready"
        project.final_report_json = _dump_model(handoff) | {
            "manager_mode_used": manager_mode_used,
            "models_used": {
                "provider": settings_record.provider,
                "manager_model": settings_record.manager_model or default_label(settings_record.provider),
                "default_worker_model": settings_record.default_worker_model or default_label(settings_record.provider),
                "manager_reasoning_effort": settings_record.manager_reasoning_effort or default_label(settings_record.provider),
                "default_worker_reasoning_effort": settings_record.default_worker_reasoning_effort or default_label(settings_record.provider),
                "role_model_overrides": settings_record.per_role_model_overrides_json or {},
                "role_reasoning_overrides": settings_record.per_role_reasoning_overrides_json or {},
                "effective_runs": [run.effective_settings_json or {} for run in completed_runs if run.effective_settings_json],
            },
        }
        self.events.publish(db, project.id, "project.handoff_ready", {"project_id": project.id})

    async def stop_agent(self, db: Session, agent: Agent) -> None:
        run = db.scalar(
            select(AgentRun)
            .where(AgentRun.agent_id == agent.id, AgentRun.finished_at.is_(None))
            .order_by(AgentRun.id.desc())
        )
        if not run:
            agent.status = "stopped"
            task = db.get(Task, agent.current_task_id) if agent.current_task_id else None
            if task is not None and task.status == "working":
                task.status = "assigned"
                task.assigned_agent_id = None
                task.waiting_reason = "Agent was stopped before completing the task."
            agent.current_task_id = None
            agent.current_action = None
            self._release_reservations(db, agent.project_id, agent_id=agent.id)
            return
        runner = await self.runners.get_runner(run.runner_type)
        await runner.stop_run(run.process_ref or "")
        task = db.get(Task, run.task_id) if run.task_id else None
        agent.status = "stopped"
        agent.current_task_id = None
        agent.current_action = None
        run.status = "stopped"
        run.finished_at = utc_now()
        if task is not None and task.status == "working":
            task.status = "assigned"
            task.assigned_agent_id = None
            task.waiting_reason = "Agent was stopped before completing the task."
        self._release_reservations(db, agent.project_id, task_id=run.task_id, agent_id=agent.id)
        self.events.publish(db, agent.project_id, "agent.stopped", {"agent_id": agent.id})

    async def complete_task_by_user(self, db: Session, task: Task) -> None:
        project = db.get(Project, task.project_id)
        if project is None:
            raise ValueError("Project not found")
        run = db.scalar(
            select(AgentRun)
            .where(AgentRun.task_id == task.id, AgentRun.finished_at.is_(None))
            .order_by(AgentRun.id.desc())
        )
        agent = db.get(Agent, task.assigned_agent_id) if task.assigned_agent_id else None
        if run is not None:
            run.status = "stopped"
            run.finished_at = utc_now()
        if agent is not None:
            agent.current_task_id = None
            agent.current_action = None
            if agent.status not in {"done", "retired"}:
                agent.status = "waiting"
        task.status = "done"
        task.assigned_agent_id = None
        task.waiting_reason = None
        self._release_reservations(db, project.id, task_id=task.id, agent_id=agent.id if agent is not None else None)
        self.events.publish(db, project.id, "task.completed_by_user", {"task_id": task.id, "run_id": run.id if run is not None else None})
        await self._maybe_finalize_handoff(db, project)

    async def pause_agent(self, db: Session, agent: Agent) -> None:
        await self.stop_agent(db, agent)
        agent.status = "waiting"
        self.events.publish(db, agent.project_id, "agent.paused", {"agent_id": agent.id})

    def read_logs(self, db: Session, agent: Agent) -> tuple[str | None, str]:
        run = db.scalar(select(AgentRun).where(AgentRun.agent_id == agent.id).order_by(AgentRun.id.desc()))
        if not run or not run.logs_path:
            return None, ""
        path = Path(run.logs_path)
        if not path.exists():
            return str(path), ""
        return str(path), path.read_text(encoding="utf-8", errors="ignore")

    async def manager_message(self, db: Session, project: Project, message: str) -> dict[str, Any]:
        manager_agent = self._manager_agent(db, project.id)
        settings_record = self._project_settings(db, project)
        resolved_settings = resolve_manager_settings(project, settings_record)
        latest_plan = self._latest_plan(db, project.id)
        user_record = self._record_manager_message(
            db,
            project,
            role="user",
            message_type="user_message",
            content_markdown=message,
            metadata_json={"source": "workspace_chat"},
        )
        if project.manager_mode == "deterministic" or resolved_settings.runner_mode == "dry_run":
            reply = f"Manager summary: project is **{project.status}**. Open tasks: {db.scalar(select(func.count(Task.id)).where(Task.project_id == project.id, Task.status.in_(list(TASK_OPEN_STATUSES))))}."
            manager_agent.active_model = resolved_settings.effective_model_label
            manager_agent.active_reasoning_effort = resolved_settings.effective_reasoning_label
            manager_agent.active_runner_type = resolved_settings.runner_mode
            manager_agent.current_action = "message"
            self.events.publish(db, project.id, "manager.mode.deterministic", {"action": "message"})
            manager_record = self._record_manager_message(
                db,
                project,
                role="manager",
                message_type="normal_update",
                content_markdown=reply,
                metadata_json={"response_mode": "deterministic" if project.manager_mode == "deterministic" else "dry_run", "source_message_id": user_record.id},
            )
            self.events.publish(db, project.id, "manager.message", {"message": message, "reply": reply})
            return {"reply": reply, "message": self._serialize_manager_message(manager_record)}
        try:
            runner = await self.runners.get_runner_for_settings(resolved_settings)
            manager_agent.status = "working"
            self._cache_agent_run_profile(manager_agent, resolved_settings, runner_type=runner.runner_type, action="message")
            handle, last_payload = await runner.run_manager_turn(
                RunnerContext(
                    project=project,
                    agent=manager_agent,
                    task=None,
                    docs_path=project.docs_path or str(self._project_docs_dir(project)),
                    plan_markdown=latest_plan.content_markdown if latest_plan else None,
                    settings=self._runner_settings_payload(resolved_settings),
                ),
                manager_message_prompt(
                    project,
                    project.docs_path or str(self._project_docs_dir(project)),
                    message,
                    user_name=self._preferred_user_name(db, project),
                    provider=resolved_settings.provider,
                    model=resolved_settings.effective_model_label,
                    reasoning_effort=resolved_settings.effective_reasoning_label,
                ),
            )
            manager_agent.status = "idle"
            manager_agent.current_action = None
            if handle.session_ref:
                manager_agent.session_ref = handle.session_ref
            reply = ""
            if last_payload and isinstance(last_payload.get("item"), dict):
                reply = last_payload["item"].get("text", "")
            elif last_payload:
                reply = str(last_payload.get("text", ""))
            if reply:
                reply = self._format_provider_manager_reply(reply)
                self.events.publish(
                    db,
                    project.id,
                    "manager.mode.provider",
                    {
                        "action": "message",
                        "provider": resolved_settings.provider,
                        "runner": handle.runner_type,
                        "effective_settings": resolved_run_settings_payload(resolved_settings),
                    },
                )
                if resolved_settings.provider == "codex":
                    self.events.publish(
                        db,
                        project.id,
                        "manager.mode.codex",
                        {
                            "action": "message",
                            "runner": handle.runner_type,
                            "effective_settings": resolved_run_settings_payload(resolved_settings),
                        },
                    )
                manager_record = self._record_manager_message(
                    db,
                    project,
                    role="manager",
                    message_type="normal_update",
                    content_markdown=reply,
                    metadata_json={
                        "response_mode": "provider",
                        "provider": resolved_settings.provider,
                        "runner": handle.runner_type,
                        "logs_path": handle.logs_path,
                        "source_message_id": user_record.id,
                    },
                )
                self.events.publish(db, project.id, "manager.message", {"message": message, "reply": reply, "logs_path": handle.logs_path})
                return {"reply": reply, "message": self._serialize_manager_message(manager_record)}
        except Exception as exc:  # noqa: BLE001
            self.events.publish(db, project.id, "manager.mode.fallback", {"action": "message", "error": str(exc)})
        manager_agent.status = "idle"
        manager_agent.active_model = resolved_settings.effective_model_label
        manager_agent.active_reasoning_effort = resolved_settings.effective_reasoning_label
        manager_agent.active_runner_type = resolved_settings.runner_mode
        manager_agent.current_action = "message"
        intake_decision = await self._greenfield_intake_decision(db, project)
        reply = (
            intake_decision.summary_markdown
            if intake_decision is not None
            else f"Manager fallback: project is **{project.status}**. Ask for next tasks or start idle agents to continue the build."
        )
        self.events.publish(db, project.id, "manager.mode.deterministic", {"action": "message"})
        manager_record = self._record_manager_message(
            db,
            project,
            role="manager",
            message_type="system_notice",
            content_markdown=reply,
            metadata_json={"response_mode": "fallback", "source_message_id": user_record.id},
        )
        self.events.publish(db, project.id, "manager.message", {"message": message, "reply": reply})
        return {"reply": reply, "message": self._serialize_manager_message(manager_record)}

    async def manager_generate_update(self, db: Session, project: Project) -> dict[str, Any]:
        queue = self._manager_queue(db, project)
        working_agents = len([agent for agent in self._sorted_workspace_agents(db, project.id) if agent["display_status"] in {"active", "running", "coding", "thinking"}])
        update = (
            f"Workspace update: **{working_agents}** active agents, "
            f"**{len(queue['waiting_on_user'])}** items waiting on the user, "
            f"and **{len(queue['deferred'])}** deferred items."
        )
        message = self._record_manager_message(
            db,
            project,
            role="manager",
            message_type="normal_update",
            content_markdown=update,
            metadata_json={"response_mode": "deterministic"},
        )
        return self._serialize_manager_message(message)

    async def manager_ask_next(self, db: Session, project: Project) -> dict[str, Any]:
        decision = await self.manager_next_step(db, project)
        message = self._record_manager_message(
            db,
            project,
            role="manager",
            message_type="normal_update",
            content_markdown=decision.summary_markdown,
            related_agent_id=decision.assign_to_agent_id,
            related_task_id=decision.task_id,
            metadata_json={"response_mode": "deterministic", "decision_type": decision.decision_type},
        )
        return self._serialize_manager_message(message)

    def _greenfield_intake_candidate(self, db: Session, project: Project) -> bool:
        if project.source_type != "idea":
            return False
        if project.status not in {"draft", "interview_in_progress", "interview_complete", "plan_ready"}:
            return False
        has_tasks = db.scalar(select(Task.id).where(Task.project_id == project.id).limit(1)) is not None
        return not has_tasks

    def _manager_interview_prompt_markdown(self, project: Project, session: InterviewSession, question: InterviewQuestion) -> str:
        options = []
        for option in question.options_json or []:
            if not isinstance(option, dict):
                continue
            option_id = str(option.get("id") or "").strip()
            label = str(option.get("label") or "").strip()
            description = str(option.get("description") or "").strip()
            if not option_id or not label:
                continue
            suffix = f" - {description}" if description else ""
            options.append(f"- `{option_id}`: {label}{suffix}")
        generated = session.questions_asked
        answered = sum(1 for item in session.questions if item.status in {"answered", "auto_decided"} or item.answered_at is not None)
        remaining = max(session.question_budget - generated, 0)
        lines = [
            f"Mission Control started intake for **{project.name}**.",
            "",
            f"**First question:** {question.question}",
            f"**Why this matters:** {question.why or 'The manager needs this answer to reduce planning uncertainty.'}",
        ]
        if options:
            lines.extend(["", "### Answer options", *options])
        lines.extend(
            [
                "",
                f"**Interview progress:** {generated} generated, {answered} answered, up to {remaining} more useful questions if needed.",
                "Reply with the option id or the matching answer text so the manager can move into planning instead of guessing.",
            ]
        )
        return "\n".join(lines)

    async def _greenfield_intake_decision(self, db: Session, project: Project) -> ManagerWorkerDecision | None:
        if not self._greenfield_intake_candidate(db, project):
            return None

        session = self._latest_session(db, project.id)
        if session is None or session.status == "superseded":
            session = await self.start_interview(db, project, question_budget=6)
        elif session.status == "in_progress" and not self._pending_interview_questions(session):
            session = await self.generate_next_interview(db, project)
        elif session.status == "completed":
            return ManagerWorkerDecision(
                decision_type="wait",
                summary_markdown="The greenfield intake interview is complete. Generate the initial project plan next from the captured answers.",
            )

        pending_questions = self._pending_interview_questions(session)
        if not pending_questions and session.status == "in_progress":
            turn = self._default_interview_turn(project, session)
            session = self._apply_interview_turn(db, project, session, turn, question_source="fallback_generated")
            pending_questions = self._pending_interview_questions(session)
        if not pending_questions and session.status == "in_progress":
            emergency_questions = [
                InterviewTurnQuestion(**question)
                for question in select_fallback_questions(1, asked_categories=set(), pending_categories=set())
            ]
            normalized_questions = self._normalize_interview_questions(session, emergency_questions, allow_repeated_categories=True)
            if normalized_questions:
                self._record_interview_questions(db, session, normalized_questions, question_source="fallback_generated")
                self._refresh_interview_session_state(session, project=project)
                pending_questions = self._pending_interview_questions(session)
        if not pending_questions and session.status == "in_progress":
            explicit_question = InterviewTurnQuestion(
                question="What is the first usable outcome you want this project to deliver?",
                why="The manager needs a concrete first slice before it can plan tasks or route agents.",
                category="product goal",
                impact="high",
                options=[
                    {"id": "local_prototype", "label": "A local prototype", "description": "Prove the core workflow locally before widening scope."},
                    {"id": "working_bug_fix", "label": "A working bug fix", "description": "Target one clearly broken behavior and make it reliable first."},
                    {"id": "usable_cli_command", "label": "A usable CLI command", "description": "Ship one command that already feels worth using."},
                    {"id": "small_web_flow", "label": "A small web flow", "description": "Deliver one narrow browser flow that actually works end to end."},
                ],
                allow_custom_answer=True,
                affects=["success criteria", "MVP definition", "validation priorities"],
            )
            normalized_questions = self._normalize_interview_questions(session, [explicit_question], allow_repeated_categories=True)
            if normalized_questions:
                self._record_interview_questions(db, session, normalized_questions, question_source="fallback_generated")
                self._refresh_interview_session_state(session, project=project)
                pending_questions = self._pending_interview_questions(session)
        if not pending_questions:
            db.expire(session, ["questions"])
            pending_questions = self._pending_interview_questions(session)
        if not pending_questions:
            project.status = "interview_in_progress"
            return ManagerWorkerDecision(
                decision_type="escalate_to_user",
                summary_markdown=(
                    f"Mission Control started intake for **{project.name}**.\n\n"
                    "**First question:** What is the first usable outcome you want this project to deliver?\n"
                    "**Why this matters:** The manager needs a concrete first slice before it can plan tasks or route agents.\n\n"
                    "Reply with a short answer such as:\n"
                    "- a local prototype\n"
                    "- a working bug fix\n"
                    "- a usable CLI command\n"
                    "- a small web flow\n\n"
                    "Mission Control will keep the project in interview mode until it gets enough signal to plan safely."
                ),
                escalation_message="What is the first usable outcome you want this project to deliver?",
            )

        first_question = pending_questions[0]
        self._sync_interview_question_mirror(db, project, session)
        return ManagerWorkerDecision(
            decision_type="escalate_to_user",
            summary_markdown=self._manager_interview_prompt_markdown(project, session, first_question),
            escalation_message=first_question.question,
        )

    async def manager_next_step(self, db: Session, project: Project) -> ManagerWorkerDecision:
        intake_decision = await self._greenfield_intake_decision(db, project)
        if intake_decision is not None:
            self.events.publish(
                db,
                project.id,
                "manager.worker_decision",
                {"decision": _dump_model(intake_decision), "manager_mode_used": "deterministic_greenfield_intake"},
            )
            return intake_decision
        workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker").order_by(Agent.id.asc())))
        fallback_decision = ManagerWorkerDecision(decision_type="wait", summary_markdown="No safe backlog task is ready.")
        for agent in workers:
            if agent.status not in {"idle", "waiting", "done", "stopped"}:
                continue
            task = self._find_next_safe_task(db, project, agent)
            if task:
                fallback_decision = ManagerWorkerDecision(
                    decision_type="assign_next_task",
                    summary_markdown=f"Route **{task.title}** to {agent.name}.",
                    task_id=task.id,
                    assign_to_agent_id=agent.id,
                )
                break
        decision, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="manager.next_step",
            objective="Re-evaluate the backlog and choose the next safe task assignment.",
            response_schema=MANAGER_WORKER_DECISION_SCHEMA,
            payload={
                "workers": [{"id": agent.id, "name": agent.name, "status": agent.status} for agent in workers],
                "tasks": [
                    {"id": task.id, "title": task.title, "status": task.status, "waiting_reason": task.waiting_reason}
                    for task in db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc()))
                ],
            },
            model_schema=ManagerWorkerDecision,
            fallback_factory=lambda: fallback_decision,
        )
        self.events.publish(db, project.id, "manager.worker_decision", {"decision": _dump_model(decision), "manager_mode_used": manager_mode_used})
        await self.start_idle_agents(db, project)
        return decision

    def _write_task_board_doc(self, db: Session, project: Project) -> None:
        docs_dir = self._ensure_project_workspace(project)
        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.priority.asc(), Task.id.asc())))
        (docs_dir / "TASK_BOARD.md").write_text(self._task_board_markdown(tasks), encoding="utf-8")


service = MissionControlService()
