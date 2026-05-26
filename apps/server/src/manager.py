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
        if self._task_expects_file_changes(task) and not verified_claims:
            report = report.model_copy(update={"status": "needs_review"})
        return report

    def _cache_agent_run_profile(self, agent: Agent, resolved_settings: ResolvedRunSettings, *, runner_type: str, action: str) -> None:
        agent.active_model = resolved_settings.effective_model_label
        agent.active_reasoning_effort = resolved_settings.effective_reasoning_label
        agent.active_runner_type = runner_type
        agent.current_action = action

    def _runner_settings_payload(self, resolved_settings: ResolvedRunSettings) -> dict[str, Any]:
        return {
            "provider": resolved_settings.provider,
            "model": resolved_settings.effective_model_label,
            "reasoning_effort": resolved_settings.effective_reasoning_label,
            "runner_mode": resolved_settings.runner_mode,
            "sandbox_mode": resolved_settings.sandbox_mode,
            "approval_policy": resolved_settings.approval_policy,
            "provider_endpoint": resolved_settings.provider_endpoint,
            "adapter_command": resolved_settings.adapter_command,
            "adapter_args": list(resolved_settings.adapter_args),
        }

    def _manager_docs_dir(self, project: Project) -> Path:
        return self._project_docs_dir(project)

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

    def _agent_archetypes_preview(self) -> list[AgentArchetype]:
        return [
            AgentArchetype(
                name=entry["name"],
                label=entry["label"],
                purpose=entry["purpose"],
                default_guidelines=entry["default_guidelines"],
                default_tools_json=list(entry["default_tools"]),
                default_permissions_json=dict(entry["default_permissions"]),
                spawn_triggers_json=list(entry["spawn_triggers"]),
                retirement_triggers_json=list(entry["retirement_triggers"]),
                risk_profile=entry.get("risk_profile", "medium"),
            )
            for entry in AGENT_ARCHETYPE_CATALOG
        ]

    def _ensure_agent_archetypes(self, db: Session) -> list[AgentArchetype]:
        existing = {entry.name: entry for entry in db.scalars(select(AgentArchetype).order_by(AgentArchetype.name.asc()))}
        for spec in AGENT_ARCHETYPE_CATALOG:
            entry = existing.get(spec["name"])
            if entry is None:
                entry = AgentArchetype(name=spec["name"])
                db.add(entry)
                existing[spec["name"]] = entry
            entry.label = spec["label"]
            entry.purpose = spec["purpose"]
            entry.default_guidelines = spec["default_guidelines"]
            entry.default_tools_json = list(spec["default_tools"])
            entry.default_permissions_json = dict(spec["default_permissions"])
            entry.spawn_triggers_json = list(spec["spawn_triggers"])
            entry.retirement_triggers_json = list(spec["retirement_triggers"])
            entry.risk_profile = spec.get("risk_profile", "medium")
        db.flush()
        return list(db.scalars(select(AgentArchetype).order_by(AgentArchetype.name.asc())))

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
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "project"

    def _effective_project_slug(self, project: Project) -> str:
        return project.slug or self._slugify(project.name)

    def _project_route(self, project: Project) -> str:
        return f"/project/{project.id}-{self._effective_project_slug(project)}"

    def _workspace_route(self, project: Project) -> str:
        return f"/workspace/{project.id}-{self._effective_project_slug(project)}"

    def _project_display_status(self, project: Project) -> str:
        if project.archived_at:
            return "archived"
        if project.status in {"import_scanning"}:
            return "import_scanning"
        if project.status in {"import_review"}:
            return "import_review"
        if project.status in {"handoff_ready"}:
            return "ready_for_handoff"
        if project.status in {"planning", "plan_ready"}:
            return "planning"
        if project.status in {"paused"}:
            return "paused"
        if project.status in {"blocked"}:
            return "blocked"
        if project.status in {"interview_in_progress", "interview_complete"}:
            return "interviewing"
        if project.status in {"building", "active"}:
            return "building"
        return project.status or "draft"

    def _status_label(self, value: str) -> str:
        return {
            "draft": "Draft",
            "planning": "Planning",
            "building": "Building",
            "blocked": "Blocked",
            "paused": "Paused",
            "ready_for_handoff": "Preparing handoff",
            "interviewing": "Interviewing",
            "archived": "Archived",
            "import_scanning": "Import scanning",
            "import_review": "Import review",
        }.get(value, value.replace("_", " ").title())

    def _workspace_summary(self, project: Project) -> dict[str, Any]:
        return {
            "name": project.name,
            "slug": self._effective_project_slug(project),
            "route": self._project_route(project),
            "status": self._project_display_status(project),
            "status_label": self._status_label(self._project_display_status(project)),
            "workspace_path": project.workspace_path,
            "docs_path": project.docs_path,
        }

    def _ordered_projects(self, db: Session, *, include_archived: bool = False) -> list[Project]:
        query = select(Project).order_by(Project.pinned.desc(), Project.last_opened_at.desc(), Project.updated_at.desc(), Project.id.desc())
        if not include_archived:
            query = query.where(Project.archived_at.is_(None))
        return list(db.scalars(query))

    def _sidebar_projects(self, projects: list[Project]) -> list[Project]:
        active = [project for project in projects if project.archived_at is None]
        pinned = [project for project in active if project.pinned]
        recent = [project for project in active if not project.pinned]
        return [*pinned[:4], *recent[: max(0, 6 - len(pinned[:4]))]]

    def _ordered_worker_agents(self, db: Session, project_id: int) -> list[Agent]:
        return list(
            db.scalars(select(Agent).where(Agent.project_id == project_id, Agent.kind == "worker").order_by(Agent.id.asc()))
        )

    def _manager_queue(self, db: Session, project: Project) -> dict[str, Any]:
        waiting_on_user = []
        deferred = []
        approvals = list(
            db.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.project_id == project.id, ApprovalRequest.status == "pending")
                .order_by(ApprovalRequest.created_at.asc(), ApprovalRequest.id.asc())
            )
        )
        for approval in approvals:
            waiting_on_user.append(
                {
                    "id": f"approval-{approval.id}",
                    "type": "command_approval" if approval.request_type == "command" else "tool_approval",
                    "title": approval.title,
                    "message": approval.reason_short,
                    "risk_level": approval.risk_level,
                    "created_at": approval.created_at,
                }
            )
        pending_questions = list(
            db.scalars(
                select(ManagerQuestion)
                .where(ManagerQuestion.project_id == project.id, ManagerQuestion.status == "pending")
                .order_by(ManagerQuestion.created_at.asc(), ManagerQuestion.id.asc())
            )
        )
        for question in pending_questions:
            waiting_on_user.append(
                {
                    "id": f"question-{question.id}",
                    "type": "manager_question",
                    "title": question.question,
                    "message": question.question,
                    "risk_level": "high" if question.impact == "high" else "medium",
                    "created_at": question.created_at,
                }
            )
        for task in db.scalars(select(Task).where(Task.project_id == project.id, Task.status == "blocked").order_by(Task.priority.asc(), Task.id.asc())):
            deferred.append(
                {
                    "id": f"task-{task.id}",
                    "type": "blocked_task",
                    "title": task.title,
                    "message": task.waiting_reason or "Task is blocked.",
                    "created_at": task.updated_at,
                }
            )
        return {"waiting_on_user": waiting_on_user, "deferred": deferred}

    def _normalize_confidence_map(self, raw: dict[str, Any]) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for key, value in raw.items():
            if not isinstance(key, str):
                continue
            try:
                normalized[key.strip().lower()] = max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                continue
        return normalized

    def _project_understanding(self, project: Project) -> ProjectUnderstanding:
        understanding = next(iter(project.understanding or []), None)
        if understanding is not None:
            return understanding
        timestamp = utc_now()
        return ProjectUnderstanding(
            project_id=project.id,
            summary="Project understanding has not been captured yet.",
            known_facts_json={},
            unknowns_json={},
            assumptions_json=[],
            constraints_json=[],
            confidence_by_category_json={},
            generation_mode="preview",
            recommended_interview_mode="skip",
            created_at=timestamp,
            updated_at=timestamp,
        )

    def _ensure_project_understanding(self, db: Session, project: Project) -> ProjectUnderstanding:
        understanding = db.scalar(select(ProjectUnderstanding).where(ProjectUnderstanding.project_id == project.id).order_by(ProjectUnderstanding.id.asc()))
        if understanding is not None:
            return understanding
        understanding = ProjectUnderstanding(
            project_id=project.id,
            summary="Project understanding has not been captured yet.",
            known_facts_json={},
            unknowns_json={},
            assumptions_json=[],
            constraints_json=[],
            confidence_by_category_json={},
            generation_mode="manual",
            recommended_interview_mode="skip",
        )
        db.add(understanding)
        db.flush()
        return understanding

    def _refresh_understanding_from_interview(self, project: Project, session: InterviewSession) -> None:
        understanding = self._ensure_project_understanding(Session.object_session(session), project)  # type: ignore[arg-type]
        understanding.summary = session.summary or understanding.summary
        understanding.known_facts_json = dict(session.known_facts_json or {})
        understanding.unknowns_json = dict(session.unknowns_json or {})
        understanding.assumptions_json = list(session.assumptions_json or [])
        understanding.constraints_json = list(session.constraints_json or [])
        understanding.confidence_by_category_json = dict(session.confidence_json or {})
        understanding.generation_mode = "interview"
        understanding.recommended_interview_mode = "skip"
        understanding.updated_at = utc_now()

    def _serialize_agent(self, db: Session, agent: Agent) -> dict[str, Any]:
        current_task = db.get(Task, agent.current_task_id) if agent.current_task_id else None
        display_status = agent.status
        if agent.status in {"working", "starting"}:
            display_status = "running"
        elif agent.status == "needs_review":
            display_status = "reviewing"
        return {
            "id": agent.id,
            "project_id": agent.project_id,
            "name": agent.name,
            "role": agent.role,
            "kind": agent.kind,
            "status": agent.status,
            "display_status": display_status,
            "workspace_path": agent.workspace_path,
            "current_task_id": current_task.id if current_task else None,
            "current_task_title": current_task.title if current_task else None,
            "last_report_summary": agent.last_report_summary,
            "failure_count": agent.failure_count,
            "current_action": agent.current_action,
            "runner_mode": agent.active_runner_type,
            "updated_at": agent.last_update,
        }

    def _sorted_workspace_agents(self, db: Session, project_id: int) -> list[dict[str, Any]]:
        agents = [self._serialize_agent(db, agent) for agent in self._ordered_worker_agents(db, project_id)]
        return sorted(
            agents,
            key=lambda item: (
                DISPLAY_STATUS_PRIORITY.get(str(item.get("display_status")), 99),
                -float(item.get("failure_count") or 0),
                str(item.get("name") or "").lower(),
            ),
        )

    def list_workspace_agents(self, db: Session, project_id: int) -> list[dict[str, Any]]:
        return self._sorted_workspace_agents(db, project_id)

    def list_tasks(self, db: Session, project_id: int) -> list[Task]:
        return list(
            db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.priority.asc(), Task.id.asc()))
        )

    def _task_status_counts(self, tasks: list[Task]) -> Counter[str]:
        return Counter(task.status for task in tasks)

    def _project_progress(self, tasks: list[Task]) -> int:
        if not tasks:
            return 0
        done = len([task for task in tasks if task.status == "done"])
        return int(round((done / len(tasks)) * 100))

    def _project_overview(self, db: Session, project: Project, tasks: list[Task], current_action: dict[str, Any]) -> dict[str, Any]:
        counts = self._task_status_counts(tasks)
        progress = self._project_progress(tasks)
        completed = counts.get("done", 0)
        total = len(tasks)
        active = counts.get("working", 0) + counts.get("needs_review", 0)
        blocked = counts.get("blocked", 0) + counts.get("waiting_on_paths", 0)
        checklist = [
            {
                "title": "Clarify architecture",
                "status": "complete" if total else "pending",
                "detail": "Initial task map exists." if total else "Architecture still needs task structure.",
            },
            {
                "title": "Implement MVP slice",
                "status": "complete" if completed and total else ("pending" if total else "missing"),
                "detail": f"{completed}/{total} tasks completed.",
            },
            {
                "title": "Unblock active work",
                "status": "complete" if blocked == 0 else "failed",
                "detail": "No active blockers." if blocked == 0 else f"{blocked} blocking task(s) remain.",
            },
            {
                "title": "Security review",
                "status": "complete" if progress >= 75 else "pending",
                "detail": "Security-sensitive changes are reviewed late in the build." if progress >= 75 else "Security review is still ahead.",
            },
            {
                "title": "Validation plan",
                "status": "complete" if total else "pending",
                "detail": "Validation coverage is mapped from the active task board." if total else "Validation planning is incomplete.",
            },
            {
                "title": "Prepare handoff",
                "status": "complete" if project.status == "handoff_ready" else "pending",
                "detail": "Handoff is ready." if project.status == "handoff_ready" else "Handoff prep is still in progress.",
            },
        ]
        return {
            "progress": progress,
            "completed_tasks": completed,
            "total_tasks": total,
            "active_tasks": active,
            "blocked_tasks": blocked,
            "current_action": current_action,
            "checklist": checklist,
            "handoff_progress": progress,
        }

    def _record_interview_questions(self, db: Session, session: InterviewSession, questions: list[InterviewTurnQuestion], *, question_source: str) -> None:
        asked_categories = {str(existing.category or "").strip().lower() for existing in session.questions}
        next_index = max([item.index for item in session.questions], default=0) + 1
        created = False
        for question in questions:
            category = str(question.category or "").strip().lower()
            if category in asked_categories and not question.allow_custom_answer:
                continue
            record = InterviewQuestion(
                session_id=session.id,
                project_id=session.project_id,
                index=next_index,
                question=question.question,
                why=question.why,
                category=question.category,
                impact=question.impact,
                options_json=[dict(item) for item in question.options],
                allow_custom_answer=question.allow_custom_answer,
                affects_json=[str(item) for item in question.affects],
                status="pending",
                question_source=question_source,
                created_at=utc_now(),
            )
            db.add(record)
            next_index += 1
            asked_categories.add(category)
            created = True
        if created:
            db.flush()
            self._refresh_interview_session_state(session)

    def _pending_interview_questions(self, session: InterviewSession) -> list[InterviewQuestion]:
        questions = [item for item in list(session.questions or []) if item.status == "pending"]
        return sorted(questions, key=lambda item: (item.index, item.id or 0))

    def _refresh_interview_session_state(self, session: InterviewSession, *, project: Project | None = None) -> None:
        session.questions_asked = len(list(session.questions or []))
        if session.status == "completed":
            return
        pending = self._pending_interview_questions(session)
        if pending:
            session.status = "in_progress"
            if project is not None:
                project.status = "interview_in_progress"
            return
        if session.questions_asked >= session.question_budget or session.stopped_early:
            session.status = "completed"
            session.completed_at = utc_now()
            if project is not None:
                project.status = "interview_complete"

    def _default_interview_turn(self, project: Project, session: InterviewSession) -> InterviewTurnPayload:
        answered = {
            str(item.category or "").strip().lower()
            for item in list(session.questions or [])
            if item.status in {"answered", "auto_decided"}
        }
        pending_categories = {
            str(item.category or "").strip().lower()
            for item in list(session.questions or [])
            if item.status == "pending"
        }
        budget_remaining = max(session.question_budget - session.questions_asked, 0)
        if budget_remaining <= 0:
            return InterviewTurnPayload(
                understanding=InterviewUnderstandingPayload(summary="Interview budget exhausted."),
                next_questions=[],
                more_questions_needed=False,
                stop_reason="budget_exhausted",
            )
        fallback_questions = select_fallback_questions(min(3, budget_remaining), asked_categories=answered, pending_categories=pending_categories)
        return InterviewTurnPayload(
            understanding=InterviewUnderstandingPayload(summary=project.idea or "Project intake is in progress."),
            next_questions=[InterviewTurnQuestion(**item) for item in fallback_questions],
            more_questions_needed=budget_remaining > len(fallback_questions),
        )

    def _normalize_interview_questions(
        self,
        session: InterviewSession,
        questions: list[InterviewTurnQuestion],
        *,
        allow_repeated_categories: bool = False,
    ) -> list[InterviewTurnQuestion]:
        existing_categories = {
            str(item.category or "").strip().lower()
            for item in list(session.questions or [])
            if item.status != "superseded"
        }
        normalized: list[InterviewTurnQuestion] = []
        seen_in_batch: set[str] = set()
        for question in questions:
            category = str(question.category or "").strip().lower()
            if not allow_repeated_categories and category in existing_categories:
                continue
            if category in seen_in_batch:
                continue
            seen_in_batch.add(category)
            normalized.append(question)
        return normalized

    async def start_interview(self, db: Session, project: Project, *, question_budget: int = 20) -> InterviewSession:
        previous_sessions = list(db.scalars(select(InterviewSession).where(InterviewSession.project_id == project.id)))
        for old_session in previous_sessions:
            old_session.status = "superseded"
        session = InterviewSession(
            project_id=project.id,
            question_budget=max(1, question_budget),
            questions_asked=0,
            manager_mode=project.manager_mode,
            stopped_early=False,
            stop_reason=None,
            confidence_json={},
            known_facts_json={},
            unknowns_json={},
            assumptions_json=[],
            constraints_json=[],
            summary=None,
            status="in_progress",
            created_at=utc_now(),
        )
        db.add(session)
        db.flush()
        project.status = "interview_in_progress"
        self.events.publish(db, project.id, "interview.started", {"project_id": project.id, "session_id": session.id})
        turn = self._default_interview_turn(project, session)
        normalized_questions = self._normalize_interview_questions(session, turn.next_questions)
        if normalized_questions:
            self._record_interview_questions(db, session, normalized_questions, question_source="fallback_generated")
        else:
            self._refresh_interview_session_state(session, project=project)
        return session

    async def generate_next_interview(self, db: Session, project: Project) -> InterviewSession:
        session = self._latest_session(db, project.id)
        if session is None or session.status == "superseded":
            return await self.start_interview(db, project)
        if session.status == "completed":
            return session
        pending = self._pending_interview_questions(session)
        if pending:
            return session
        turn = self._default_interview_turn(project, session)
        normalized_questions = self._normalize_interview_questions(session, turn.next_questions)
        if normalized_questions:
            self._record_interview_questions(db, session, normalized_questions, question_source="fallback_generated")
        else:
            session.status = "completed"
            session.completed_at = utc_now()
            if project.status == "interview_in_progress":
                project.status = "interview_complete"
        return session

    def _serialize_interview_question(self, project: Project, question: InterviewQuestion) -> dict[str, Any]:
        return {
            "id": question.id,
            "project_id": question.project_id or project.id,
            "index": question.index,
            "question": question.question,
            "why": question.why,
            "category": question.category,
            "impact": question.impact,
            "options": list(question.options_json or []),
            "allow_custom_answer": question.allow_custom_answer,
            "selected_option_id": question.selected_option_id or question.selected_option,
            "selected_text": question.selected_text,
            "custom_answer": question.custom_answer,
            "affects": list(question.affects_json or []),
            "status": question.status,
            "question_source": question.question_source,
            "answered_at": question.answered_at,
            "rationale": question.rationale,
            "selected_option": question.selected_option_id or question.selected_option,
        }

    def _serialize_interview_session(self, project: Project, session: InterviewSession) -> dict[str, Any]:
        questions = [self._serialize_interview_question(project, question) for question in sorted(list(session.questions or []), key=lambda item: (item.index, item.id or 0))]
        return {
            "id": session.id,
            "project_id": session.project_id,
            "status": session.status,
            "question_budget": session.question_budget,
            "questions_asked": session.questions_asked,
            "manager_mode": session.manager_mode,
            "stopped_early": session.stopped_early,
            "stop_reason": session.stop_reason,
            "confidence": dict(session.confidence_json or {}),
            "known_facts": dict(session.known_facts_json or {}),
            "unknowns": dict(session.unknowns_json or {}),
            "assumptions": list(session.assumptions_json or []),
            "constraints": list(session.constraints_json or []),
            "summary": session.summary,
            "questions": questions,
            "created_at": session.created_at,
            "completed_at": session.completed_at,
        }

    def _refresh_understanding(self, db: Session, project: Project, session: InterviewSession) -> None:
        understanding = self._ensure_project_understanding(db, project)
        understanding.summary = session.summary or understanding.summary
        understanding.known_facts_json = dict(session.known_facts_json or {})
        understanding.unknowns_json = dict(session.unknowns_json or {})
        understanding.assumptions_json = list(session.assumptions_json or [])
        understanding.constraints_json = list(session.constraints_json or [])
        understanding.confidence_by_category_json = dict(session.confidence_json or {})
        understanding.generation_mode = "interview"
        understanding.recommended_interview_mode = "skip"
        understanding.updated_at = utc_now()
        db.flush()

    def _sync_interview_question_mirror(self, db: Session, project: Project, session: InterviewSession) -> None:
        pending = self._pending_interview_questions(session)
        if not pending:
            return
        latest = pending[0]
        existing = db.scalar(
            select(ManagerQuestion)
            .where(
                ManagerQuestion.project_id == project.id,
                ManagerQuestion.status == "pending",
                ManagerQuestion.metadata_json["interview_question_id"].as_integer() == latest.id,
            )
            .order_by(ManagerQuestion.id.desc())
        )
        if existing is not None:
            existing.question = latest.question
            existing.options_json = list(latest.options_json or [])
            existing.manager_recommendation = None
            existing.impact = latest.impact
            existing.metadata_json = {"interview_question_id": latest.id, "session_id": session.id}
            db.flush()
            return
        self._create_question(
            db,
            project,
            question=latest.question,
            options_json=list(latest.options_json or []),
            impact=latest.impact,
            manager_recommendation=None,
            metadata_json={"interview_question_id": latest.id, "session_id": session.id},
        )

    def _serialize_plan(self, plan: Plan) -> dict[str, Any]:
        return {
            "id": plan.id,
            "project_id": plan.project_id,
            "version": plan.version,
            "status": plan.status,
            "content_markdown": plan.content_markdown,
            "summary": plan.summary,
            "milestone": plan.milestone,
            "constraints_json": list(plan.constraints_json or []),
            "risks_json": list(plan.risks_json or []),
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
        }

    async def generate_plan(self, db: Session, project: Project, action_bias: str | None = None, note: str | None = None) -> Plan:
        latest_understanding = self._project_understanding(project)
        previous_plan = self._latest_plan(db, project.id)
        tasks = self.list_tasks(db, project.id)
        previous_risks = [
            {
                "title": risk.title,
                "severity": risk.severity,
                "likelihood": risk.likelihood,
                "status": risk.status,
                "mitigation": risk.mitigation,
            }
            for risk in risk_service.list_risks(db, project)
        ]
        if previous_risks:
            previous_risks = previous_risks[:12]
        runner_prompt = manager_action_prompt(
            project,
            docs_path=project.docs_path or str(self._manager_docs_dir(project)),
            action="generate_plan",
            user_name=self._preferred_user_name(db, project),
            provider=resolve_manager_settings(project, self._project_settings(db, project)).provider,
            model=resolve_manager_settings(project, self._project_settings(db, project)).effective_model_label,
            reasoning_effort=resolve_manager_settings(project, self._project_settings(db, project)).effective_reasoning_label,
            previous_plan=previous_plan.content_markdown if previous_plan else None,
            previous_risks=previous_risks,
            action_bias=action_bias,
            note=note,
            understanding_summary=latest_understanding.summary,
            constraints=list(latest_understanding.constraints_json or []),
            assumptions=list(latest_understanding.assumptions_json or []),
            unknowns=dict(latest_understanding.unknowns_json or {}),
            confidence=dict(latest_understanding.confidence_by_category_json or {}),
            tasks=[{"title": task.title, "status": task.status, "goal": task.goal} for task in tasks],
        )
        decision_payload, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="manager.generate_plan",
            objective="Create or refresh the project execution plan.",
            response_schema=MANAGER_PLAN_SCHEMA,
            payload={
                "project_idea": project.idea,
                "understanding": latest_understanding.summary,
                "constraints": list(latest_understanding.constraints_json or []),
                "assumptions": list(latest_understanding.assumptions_json or []),
                "unknowns": dict(latest_understanding.unknowns_json or {}),
                "confidence": dict(latest_understanding.confidence_by_category_json or {}),
                "existing_tasks": [{"title": task.title, "status": task.status, "goal": task.goal} for task in tasks],
                "previous_plan": previous_plan.content_markdown if previous_plan else None,
                "action_bias": action_bias,
                "note": note,
            },
            model_schema=ManagerPlan,
            fallback_factory=lambda: ManagerPlan(
                milestone="MVP",
                summary="Draft a narrow MVP plan grounded in the current interview answers.",
                content_markdown=build_plan_markdown(
                    milestone="MVP",
                    objectives=[
                        "Clarify the highest-confidence workflow.",
                        "Build the smallest usable vertical slice.",
                        "Validate it before broadening scope.",
                    ],
                    risks=[
                        "Requirements are still fuzzy in at least one category.",
                        "Validation needs to stay lightweight until the first slice works.",
                    ],
                    constraints=list(latest_understanding.constraints_json or []),
                ),
                constraints_json=list(latest_understanding.constraints_json or []),
                risks_json=["Requirements are still fuzzy."],
            ),
        )
        next_version = (db.scalar(select(func.max(Plan.version)).where(Plan.project_id == project.id)) or 0) + 1
        for old_plan in db.scalars(select(Plan).where(Plan.project_id == project.id)):
            old_plan.status = "superseded"
        plan = Plan(
            project_id=project.id,
            version=next_version,
            status="ready",
            content_markdown=decision_payload.content_markdown,
            summary=decision_payload.summary,
            milestone=decision_payload.milestone,
            constraints_json=list(decision_payload.constraints_json or []),
            risks_json=list(decision_payload.risks_json or []),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(plan)
        db.flush()
        project.status = "plan_ready"
        self.events.publish(
            db,
            project.id,
            "plan.generated",
            {
                "project_id": project.id,
                "plan_id": plan.id,
                "version": plan.version,
                "manager_mode_used": manager_mode_used,
            },
        )
        self._record_manager_message(
            db,
            project,
            role="system",
            message_type="normal_update",
            content_markdown=f"Plan v{plan.version} generated for **{project.name}**.",
            metadata_json={"plan_id": plan.id, "response_mode": manager_mode_used},
        )
        return plan

    def get_plan(self, db: Session, project: Project) -> dict[str, Any] | None:
        plan = self._latest_plan(db, project.id)
        return self._serialize_plan(plan) if plan else None

    async def approve_plan(self, db: Session, project: Project, action: str, note: str | None) -> Plan:
        latest = self._latest_plan(db, project.id)
        if latest is None:
            raise ValueError("Plan not found")
        if action == "approve":
            latest.status = "approved"
            project.status = "planning"
        elif action == "revise":
            latest.status = "superseded"
            return await self.generate_plan(db, project, action_bias="revise", note=note)
        else:
            raise ValueError("Unknown plan action")
        latest.updated_at = utc_now()
        db.flush()
        self.events.publish(db, project.id, "plan.updated", {"project_id": project.id, "plan_id": latest.id, "status": latest.status})
        return latest

    async def generate_tasks(self, db: Session, project: Project) -> tuple[list[Task], str]:
        latest_plan = self._latest_plan(db, project.id)
        if latest_plan is None:
            raise ValueError("Plan not found")
        manager_agent = self._manager_agent(db, project.id)
        settings_record = self._project_settings(db, project)
        resolved_settings = resolve_manager_settings(project, settings_record)
        self._cache_agent_run_profile(manager_agent, resolved_settings, runner_type=resolved_settings.runner_mode, action="generate_tasks")
        decomposition_payload, manager_mode_used = await self._resolve_manager_model(
            db,
            project,
            action_name="manager.generate_tasks",
            objective="Break the approved plan into concrete implementation tasks.",
            response_schema=MANAGER_TASK_DECOMPOSITION_SCHEMA,
            payload={"plan_markdown": latest_plan.content_markdown, "milestone": latest_plan.milestone, "summary": latest_plan.summary},
            model_schema=ManagerTaskDecomposition,
            fallback_factory=lambda: ManagerTaskDecomposition(tasks=build_initial_tasks(latest_plan.milestone, latest_plan.summary)),
        )
        existing = {task.title: task for task in db.scalars(select(Task).where(Task.project_id == project.id))}
        created_tasks: list[Task] = []
        for item in decomposition_payload.tasks:
            task = existing.get(item.title)
            if task is None:
                task = Task(project_id=project.id, title=item.title, goal=item.goal, scope=item.scope)
                db.add(task)
                created_tasks.append(task)
            task.agent_role = item.agent_role
            task.milestone = item.milestone or latest_plan.milestone
            task.allowed_paths_json = list(item.allowed_paths_json or [])
            task.forbidden_paths_json = list(item.forbidden_paths_json or [])
            task.validation_steps_json = list(item.validation_steps_json or [])
            task.success_criteria_json = list(item.success_criteria_json or [])
            task.estimated_complexity = item.estimated_complexity
            task.dependencies_json = list(item.dependencies_json or [])
            if task.status == "draft":
                task.status = "backlog"
        db.flush()
        project.status = "planning"
        self.events.publish(db, project.id, "tasks.generated", {"project_id": project.id, "count": len(created_tasks), "manager_mode_used": manager_mode_used})
        self._write_task_board_doc(db, project)
        return self.list_tasks(db, project.id), manager_mode_used

    def _release_reservations(self, db: Session, project_id: int, *, task_id: int | None = None, agent_id: int | None = None, publish: bool = True) -> list[PathReservation]:
        query = select(PathReservation).where(PathReservation.project_id == project_id, PathReservation.released_at.is_(None))
        if task_id is not None:
            query = query.where(PathReservation.task_id == task_id)
        if agent_id is not None:
            query = query.where(PathReservation.agent_id == agent_id)
        released: list[PathReservation] = []
        for reservation in db.scalars(query):
            reservation.released_at = utc_now()
            released.append(reservation)
        if released:
            self._refresh_agent_locks(db, project_id)
            if publish:
                self.events.publish(
                    db,
                    project_id,
                    "paths.released",
                    {"task_id": task_id, "agent_id": agent_id, "paths": [reservation.path for reservation in released]},
                )
        return released

    def _refresh_agent_locks(self, db: Session, project_id: int) -> None:
        reservations = self._active_reservations(db, project_id)
        reserved_by_agent: dict[int, list[str]] = {}
        for reservation in reservations:
            reserved_by_agent.setdefault(reservation.agent_id, []).append(reservation.path)
        for agent in db.scalars(select(Agent).where(Agent.project_id == project_id, Agent.kind == "worker")):
            agent.locked_paths_json = sorted(reserved_by_agent.get(agent.id, []))
        db.flush()

    def _active_reservations(self, db: Session, project_id: int) -> list[PathReservation]:
        return list(
            db.scalars(
                select(PathReservation)
                .where(PathReservation.project_id == project_id, PathReservation.released_at.is_(None))
                .order_by(PathReservation.id.asc())
            )
        )

    def list_reservations(self, db: Session, project_id: int) -> list[PathReservation]:
        return self._active_reservations(db, project_id)

    def _reserve_paths(self, db: Session, project: Project, task: Task, agent: Agent) -> None:
        self._release_reservations(db, project.id, task_id=task.id, agent_id=agent.id, publish=False)
        for path in list(task.allowed_paths_json or []):
            db.add(PathReservation(project_id=project.id, task_id=task.id, agent_id=agent.id, path=path))
        db.flush()
        self._refresh_agent_locks(db, project.id)
        self.events.publish(db, project.id, "paths.reserved", {"agent_id": agent.id, "task_id": task.id, "paths": task.allowed_paths_json})

    def _find_path_conflicts(self, db: Session, project: Project, task: Task, agent: Agent) -> list[Agent]:
        blockers: list[Agent] = []
        for reservation in self._active_reservations(db, project.id):
            if reservation.agent_id == agent.id:
                continue
            if reservation.path in list(task.allowed_paths_json or []):
                other = db.get(Agent, reservation.agent_id)
                if other is not None:
                    blockers.append(other)
        return blockers

    def _mark_task_waiting(self, db: Session, project: Project, task: Task, blockers: list[Agent]) -> None:
        task.status = "waiting_on_paths"
        task.waiting_reason = f"Waiting on path ownership from {', '.join(agent.name for agent in blockers)}."
        self.events.publish(
            db,
            project.id,
            "task.waiting_on_paths",
            {"task_id": task.id, "blocking_agents": [other.id for other in blockers], "reason": task.waiting_reason},
        )

    def _find_next_safe_task(self, db: Session, project: Project, agent: Agent) -> Task | None:
        workers = self._ordered_worker_agents(db, project.id)
        active_task_ids = {other.current_task_id for other in workers if other.current_task_id}
        for task in self.list_tasks(db, project.id):
            if task.id in active_task_ids:
                continue
            if not can_assign_task(task):
                continue
            if task.assigned_agent_id and task.assigned_agent_id != agent.id:
                continue
            if not task.allowed_paths_json:
                return task
            blockers = self._find_path_conflicts(db, project, task, agent)
            if blockers:
                self._mark_task_waiting(db, project, task, blockers)
                continue
            return task
        return None

    async def start_idle_agents(self, db: Session, project: Project) -> list[dict[str, Any]]:
        started: list[dict[str, Any]] = []
        workers = self._ordered_worker_agents(db, project.id)
        tasks = self.list_tasks(db, project.id)
        for agent in workers:
            if agent.status not in {"idle", "waiting", "done", "stopped"}:
                continue
            task = self._find_next_safe_task(db, project, agent)
            if task is None:
                continue
            await self._start_agent_on_task(db, project, agent, task)
            started.append(self._serialize_agent(db, agent))
        return started

    async def _start_agent_on_task(self, db: Session, project: Project, agent: Agent, task: Task) -> None:
        if task.status == "waiting_on_paths":
            task.status = "assigned"
            task.waiting_reason = None
        task.assigned_agent_id = agent.id
        task.status = "working"
        self._reserve_paths(db, project, task, agent)
        agent.current_task_id = task.id
        agent.status = "working"
        agent.current_action = task.title
        settings = resolve_worker_settings(project, self._project_settings(db, project))
        runner = await self.runners.get_runner_for_settings(settings)
        self._cache_agent_run_profile(agent, settings, runner_type=runner.runner_type, action=task.title)
        context_pack_payload = context_pack_service.build_context_pack(db, project, agent_id=agent.id, task_id=task.id)
        run = AgentRun(
            agent_id=agent.id,
            task_id=task.id,
            runner_type=runner.runner_type,
            process_ref=f"task-{task.id}-{agent.id}",
            status="running",
            context_pack_json=context_pack_payload,
            effective_settings_json=self._runner_settings_payload(settings),
            started_at=utc_now(),
        )
        db.add(run)
        db.flush()
        self.events.publish(db, project.id, "agent.started", {"agent_id": agent.id, "task_id": task.id, "runner": runner.runner_type})

    async def _maybe_finalize_handoff(self, db: Session, project: Project) -> None:
        open_tasks = [task for task in self.list_tasks(db, project.id) if task.status != "done"]
        if open_tasks:
            return
        workers = self._ordered_worker_agents(db, project.id)
        if any(agent.status not in {"idle", "done", "stopped", "retired"} for agent in workers):
            return
        project.status = "handoff_ready"
        self.events.publish(db, project.id, "project.handoff_ready", {"project_id": project.id})

    def _latest_unfinished_run(self, db: Session, agent_id: int) -> AgentRun | None:
        return db.scalar(select(AgentRun).where(AgentRun.agent_id == agent_id, AgentRun.finished_at.is_(None)).order_by(AgentRun.id.desc()))

    async def ingest_worker_report(self, db: Session, run: AgentRun, payload: dict[str, Any]) -> ManagerWorkerDecision:
        report = WorkerReport.model_validate(payload)
        if run.finished_at is not None:
            raise ValueError("Worker report already recorded")
        agent = db.get(Agent, run.agent_id)
        if agent is None:
            raise ValueError("Agent not found")
        project = db.get(Project, agent.project_id)
        if project is None:
            raise ValueError("Project not found")
        task = db.get(Task, run.task_id) if run.task_id else None
        if task is not None and report.task_id and report.task_id != task.id:
            raise ValueError("Worker report task_id does not match the run task")
        if report.agent_id and report.agent_id != agent.id:
            raise ValueError("Worker report agent_id does not match the run agent")
        report = self._verify_worker_report_evidence(project, task, report, self.run_input_snapshots.get(run.id))
        run.report_json = _dump_model(report)
        run.status = report.status
        run.finished_at = utc_now()
        agent.last_report_summary = report.summary
        agent.failure_count = report.failure_count or agent.failure_count
        if report.status in {"error", "blocked"}:
            agent.status = "blocked"
        elif report.status == "needs_review":
            agent.status = "needs_review"
        else:
            agent.status = "idle"
        if task is not None:
            if report.status == "done":
                task.status = "done"
                task.assigned_agent_id = None
            elif report.status == "needs_review":
                task.status = "needs_review"
            elif report.status == "blocked":
                task.status = "blocked"
                task.waiting_reason = report.summary
            elif report.status == "error":
                task.status = "blocked"
                task.waiting_reason = report.summary
        agent.current_task_id = None
        agent.current_action = None
        self._release_reservations(db, project.id, task_id=task.id if task else None, agent_id=agent.id)
        self.events.publish(db, project.id, "worker.report.received", {"run_id": run.id, "task_id": run.task_id, "status": report.status, "summary": report.summary})
        self.run_input_snapshots.pop(run.id, None)
        if report.status == "blocked" and task is not None:
            self._create_question(
                db,
                project,
                question=f"{agent.name} is blocked on {task.title}. Reassign, reduce scope, or ask the user?",
                options_json=[
                    {"id": "reassign", "label": "Reassign"},
                    {"id": "reduce_scope", "label": "Reduce scope"},
                    {"id": "ask_user", "label": "Ask user"},
                ],
                impact="high",
                manager_recommendation="ask_user",
                metadata_json={"related_task_id": task.id, "owner_agent_id": agent.id},
            )
        await self._maybe_finalize_handoff(db, project)
        if report.status == "blocked":
            return ManagerWorkerDecision(
                decision_type="escalate_to_user",
                summary_markdown=f"{agent.name} is blocked: {report.summary}",
                escalation_message=report.summary,
                task_id=task.id if task else None,
                assign_to_agent_id=agent.id,
            )
        if report.status == "needs_review":
            return ManagerWorkerDecision(
                decision_type="assign_next_task",
                summary_markdown=f"{agent.name} finished implementation for **{task.title if task else 'the task'}** and it needs review.",
                task_id=task.id if task else None,
                assign_to_agent_id=agent.id,
            )
        return await self.manager_next_step(db, project)

    async def start_project_agents(self, db: Session, project: Project) -> dict[str, Any]:
        manager = self._manager_agent(db, project.id)
        try:
            started = await self.start_idle_agents(db, project)
            if not started and manager.status == "idle":
                manager.status = "blocked"
                manager.current_action = "No safe backlog task is ready."
                self.events.publish(db, project.id, "manager.blocked", {"project_id": project.id, "reason": manager.current_action})
                return {"status": "blocked", "message": manager.current_action, "agents": []}
            project.status = "building"
            manager.status = "working"
            manager.current_action = "Routing active work."
            self.events.publish(db, project.id, "project.started", {"project_id": project.id, "count": len(started)})
            return {"status": "started", "message": f"Started {len(started)} worker(s).", "agents": started}
        except Exception as exc:  # noqa: BLE001
            manager.status = "blocked"
            manager.current_action = f"Failed to start workers: {exc}"
            self.events.publish(db, project.id, "manager.blocked", {"project_id": project.id, "reason": str(exc)})
            raise

    async def start_agent(self, db: Session, agent: Agent) -> None:
        project = db.get(Project, agent.project_id)
        if project is None:
            raise ValueError("Project not found")
        task = self._find_next_safe_task(db, project, agent)
        if task is None:
            raise ValueError("No safe task is ready for this agent")
        await self._start_agent_on_task(db, project, agent, task)

    async def stop_agent(self, db: Session, agent: Agent) -> None:
        run = self._latest_unfinished_run(db, agent.id)
        task = db.get(Task, run.task_id) if run and run.task_id else None
        if run is not None:
            run.finished_at = utc_now()
            run.status = "stopped"
        if task is not None:
            task.status = "assigned"
            task.assigned_agent_id = None
        agent.current_task_id = None
        agent.current_action = None
        agent.status = "stopped"
        self._release_reservations(db, agent.project_id, task_id=task.id if task else None, agent_id=agent.id)
        self.events.publish(db, agent.project_id, "agent.stopped", {"agent_id": agent.id})

    async def complete_task(self, db: Session, task: Task) -> None:
        project = db.get(Project, task.project_id)
        if project is None:
            raise ValueError("Project not found")
        run = db.scalar(select(AgentRun).where(AgentRun.task_id == task.id, AgentRun.finished_at.is_(None)).order_by(AgentRun.id.desc()))
        agent = db.get(Agent, task.assigned_agent_id) if task.assigned_agent_id else None
        if run is not None:
            run.finished_at = utc_now()
            run.status = "done"
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
