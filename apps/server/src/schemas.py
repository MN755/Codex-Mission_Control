from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from capabilities import CAPABILITY_CATEGORIES


ProviderId = Literal["codex", "ollama", "openai_api", "anthropic_api", "xai_api", "nvidia_dynamo", "nvidia_nim", "claude_code", "custom"]
StartupProviderChoice = ProviderId
StartupStartMode = Literal["new_project", "guided_walkthrough"]
RunnerMode = Literal["auto", "cli", "app_server", "dry_run"]
ManagerMode = Literal["auto", "provider", "codex", "deterministic"]
ProjectSourceType = Literal["idea", "existing_folder", "cloned_repo", "docs_import"]
ImportMode = Literal["linked", "copied", "cloned"]
ScanStatus = Literal["not_started", "in_progress", "completed", "failed"]
WritePermissionStatus = Literal["read_only", "write_allowed", "limited_write"]
ScanDepth = Literal["shallow", "standard", "targeted", "deep"]
CodebaseSize = Literal["small", "medium", "large", "huge"]
InterviewChoice = Literal["skip", "quick", "full", "manager_decides"]
AgentStatus = Literal["idle", "starting", "working", "waiting", "needs_review", "blocked", "done", "stopped", "error"]
TaskStatus = Literal["backlog", "assigned", "working", "waiting_on_paths", "needs_review", "done", "blocked"]
PlanAction = Literal["approve_build", "simplify", "ambitious", "usability", "quality", "rewrite", "feature_delta"]
TaskComplexity = Literal["small", "medium", "large"]
WorkerReportStatus = Literal["done", "blocked", "needs_review", "error"]
FailureClassification = Literal["transient", "user_action_required", "input_error", "runner_bug", "infra_blocker", "approval_denied"]
RunnerResultStatus = Literal["completed", "blocked", "needs_review", "failed"]
RunnerLaneType = Literal["implementation", "browser_automation", "test_execution", "repo_analysis", "manager_turn"]
WorkerDecisionType = Literal["assign_next_task", "request_fix", "mark_done", "mark_blocked", "retire_agent", "escalate_to_user", "wait"]
ReasoningEffort = Literal["minimal", "low", "medium", "high"]
SandboxMode = Literal["workspace-write", "read-only"]
ApprovalPolicy = Literal["on-request", "untrusted", "never"]
ThemeMode = Literal["system", "dark", "light"]
StartupBehavior = Literal["dashboard", "last_project", "restore_previous_page"]
AuthJobMethod = Literal["chatgpt", "device_auth", "api_key", "logout"]
AuthJobStatus = Literal["queued", "running", "succeeded", "failed"]
StartupMode = Literal["first_time", "regular", "error", "degraded"]
StartupOverallStatus = Literal["starting", "ready", "retrying", "error", "degraded"]
StartupCheckStatus = Literal["passed", "failed", "warning", "skipped"]
StartupRetryMode = Literal["targeted", "full"]
ManagerMessageType = Literal[
    "normal_update",
    "user_message",
    "manager_question",
    "command_approval",
    "tool_approval",
    "milestone_report",
    "blocker_report",
    "handoff_report",
    "system_notice",
]
QuestionImpact = Literal["low", "medium", "high"]
QuestionStatus = Literal["pending", "answered", "auto_decided", "cancelled"]
ApprovalRequestType = Literal["command", "tool", "plugin", "connected_app"]
ApprovalRequestStatus = Literal["pending", "approved_once", "denied", "allowed_for_project", "expired"]
RiskLevel = Literal["low", "medium", "high", "critical"]
SecurityScope = Literal["global", "project"]
DefaultExecutionPolicy = Literal["ask", "allow_low_risk", "deny"]
NetworkAccessPolicy = Literal["ask", "allow", "deny"]
WriteAccessPolicy = Literal["read_only", "workspace_write", "limited_paths"]
ExternalAccountPolicy = Literal["ask", "deny"]
DeploymentPolicy = Literal["ask", "deny"]
DestructiveActionPolicy = Literal["deny", "critical_approval"]
ApprovalAuditDecision = Literal["approved", "denied", "allowed_for_project", "expired", "auto_approved", "blocked"]
ApprovalAuditActor = Literal["user", "manager", "policy", "system"]
OrchestrationSource = Literal["codex_plugin", "dashboard", "cli", "desktop", "test"]
OrchestrationStatus = Literal["initializing", "planning", "waiting_for_user", "running", "paused", "completed", "failed"]
OrchestrationMode = Literal["dry_run", "codex_cli", "mixed", "unknown"]
AttachMode = Literal["auto", "new_project", "existing_codebase"]
AttachPolicy = Literal["reuse_existing", "create_new", "ask"]
HeadlessTaskMode = Literal["dry_run", "auto", "codex_cli"]
HeadlessTaskStrategy = Literal["manager_decides", "fastest_build", "balanced", "high_quality", "documentation_heavy", "safe_mode"]
PendingDecisionType = Literal[
    "manager_question",
    "command_approval",
    "tool_approval",
    "write_permission",
    "swarm_approval",
    "subagent_burst_approval",
    "snapshot_approval",
    "recovery_decision",
    "handoff_review",
    "scope_change_decision",
    "safe_mode_confirmation",
]
PendingDecisionStatus = Literal["pending", "answered", "expired", "cancelled"]
BridgeMessageSourceType = Literal["manager", "system", "agent", "security", "diagnostics", "handoff"]
BridgeMessageType = Literal[
    "status_update",
    "approval_request",
    "manager_question",
    "warning",
    "blocked",
    "handoff_ready",
    "failed",
    "recovery_options",
    "swarm_update",
    "subagent_burst_recommendation",
    "diagnostic_summary",
    "event_digest",
    "safe_mode_update",
]
BridgeRedactionStatus = Literal["clean", "redacted"]
ErrorSeverity = Literal["debug", "info", "warning", "error", "fatal"]
EventDigestWindow = Literal["last_5_minutes", "last_15_minutes", "since_last_user_interaction", "since_orchestration_start"]
ProjectActionType = Literal["no_action", "manager_question", "command_approval", "tool_approval", "blocker", "handoff_ready", "degraded", "paused", "error"]
ProjectActionSeverity = Literal["info", "warning", "danger", "success"]
AgentDisplayStatus = Literal["active", "thinking", "coding", "running", "reviewing", "monitoring", "waiting", "idle", "blocked", "error", "retired"]
InterviewCategory = Literal[
    "product goal",
    "target users",
    "MVP scope",
    "core features",
    "nice-to-have features",
    "platform/runtime",
    "UI/UX style",
    "data/storage",
    "authentication/security",
    "integrations/connectors",
    "agent/tool behavior",
    "approvals/sandboxing",
    "testing/validation",
    "deployment/distribution",
    "performance constraints",
    "privacy/local-first constraints",
    "future expansion",
    "handoff format",
]
InterviewQuestionState = Literal["pending", "answered", "superseded", "cancelled"]
InterviewQuestionSource = Literal["manager_ai", "fallback_generated"]
SwarmOptimizationMode = Literal["fastest_build", "balanced", "high_quality", "documentation_heavy", "research_planning", "massive_codebase", "gpu_programming", "manager_decides"]
SwarmAggressiveness = Literal["small", "medium", "large", "maximum", "manager_decides"]
DocsDepth = Literal["minimal", "standard", "detailed", "publishable"]
TestingDepth = Literal["minimal", "standard", "extensive", "release_grade"]
SwarmRisk = Literal["low", "medium", "high"]
SwarmPlanStatus = Literal["pending_approval", "approved", "active", "spawned", "superseded", "rejected"]
SwarmAgentSpecStatus = Literal["planned", "spawned", "deferred", "retire_pending", "retired", "cancelled"]
SwarmEventType = Literal[
    "swarm_plan_created",
    "swarm_plan_approved",
    "agent_spec_created",
    "agent_spawned",
    "agent_retired",
    "agent_reassigned",
    "swarm_scaled_up",
    "swarm_scaled_down",
    "path_conflict_detected",
    "bottleneck_detected",
    "strategy_changed",
]
WidgetScope = Literal["dashboard", "project"]
WidgetArea = Literal[
    "dashboard_main",
    "dashboard_right",
    "dashboard_bottom",
    "dashboard_custom",
    "project_right_sidebar",
    "project_bottom",
    "project_overview",
    "project_custom",
]
WidgetSize = Literal["small", "medium", "large", "full"]
WidgetDataStatus = Literal["ready", "warning", "empty", "coming_soon", "needs_setup", "unsupported"]
WidgetCategory = Literal["Attention", "Swarm", "Agents", "Safety", "Quality", "Docs", "Models", "Tools", "Diagnostics", "Handoff", "Change Management"]
ConflictType = Literal["path_overlap", "file_edit_collision", "task_dependency", "review_disagreement", "merge_conflict", "unknown"]
ConflictStatus = Literal["detected", "manager_review", "resolving", "resolved", "dismissed"]
ConflictResolution = Literal["serialize_tasks", "choose_agent_a", "choose_agent_b", "merge_changes", "split_file_ownership", "ask_user", "spawn_conflict_resolver_agent", "rollback_one_side"]
EvidenceType = Literal["command_output", "test_result", "build_result", "file_change", "artifact", "screenshot", "report", "manual_note"]
EvidenceStatus = Literal["passed", "failed", "not_run", "unknown"]
SnapshotType = Literal["git_commit", "git_branch", "filesystem_marker", "manual"]
SnapshotStatus = Literal["available", "failed", "unsupported"]
RecoveryStatus = Literal["proposed", "accepted", "rejected", "completed"]
AgentLoadLevel = Literal["idle", "light", "normal", "heavy", "blocked"]
ProjectHealthState = Literal["healthy", "needs_review", "blocked", "ready_for_handoff", "unstable", "unknown"]
SwarmIntensity = Literal["low", "medium", "high", "extreme"]
SubagentDefaultMode = Literal["read_only", "limited_write", "disabled"]
SubagentSpawnMethod = Literal["codex_chat_bridge", "codex_cli", "manual_prompt"]
SubagentTaskType = Literal["codebase_exploration", "review", "planning", "handoff_audit", "failure_diagnosis"]
SubagentBatchStatus = Literal["proposed", "approved", "running", "completed", "failed", "cancelled"]
SubagentEstimatedIntensity = Literal["low", "medium", "high"]
TraceSpanKind = Literal[
    "run",
    "manager_planning",
    "worker_assignment",
    "runner_attempt",
    "validation",
    "approval",
    "handoff",
    "browser_automation",
    "test_execution",
    "repo_analysis",
]


class ProjectCreate(BaseModel):
    name: str
    idea: str
    workspace_path: str
    provider: ProviderId = "codex"
    runner_mode: RunnerMode = "auto"
    manager_mode: ManagerMode = "auto"
    source_type: ProjectSourceType = "idea"
    source_path: str | None = None
    import_mode: ImportMode | None = None
    scan_status: ScanStatus = "not_started"
    write_permission_status: WritePermissionStatus = "write_allowed"


class ProjectRead(BaseModel):
    id: int
    name: str
    slug: str | None
    idea: str
    workspace_path: str
    status: str
    runner_mode: RunnerMode
    manager_mode: ManagerMode
    created_by: str | None
    docs_path: str | None
    final_report_json: dict[str, Any] | None
    pinned: bool = False
    archived_at: datetime | None = None
    last_opened_at: datetime | None
    latest_milestone: str | None = None
    latest_activity: str | None = None
    handoff_status: str | None = None
    source_type: ProjectSourceType = "idea"
    source_path: str | None = None
    import_mode: ImportMode | None = None
    imported_at: datetime | None = None
    scan_status: ScanStatus = "not_started"
    last_indexed_at: datetime | None = None
    write_permission_status: WritePermissionStatus = "write_allowed"
    display_status: str = "planning"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    idea: str | None = Field(default=None, min_length=1)


class DocGenerationResponse(BaseModel):
    docs_path: str
    files: list[str]
    used_live_manager: bool = False
    manager_mode_used: str = "deterministic"


class InterviewStartRequest(BaseModel):
    question_budget: int | None = Field(default=None, ge=0, le=500)
    question_count: int | None = Field(default=None, ge=0, le=500)


class InterviewOption(BaseModel):
    id: str
    label: str
    description: str


class InterviewQuestionRead(BaseModel):
    id: int
    project_id: int
    index: int
    question: str
    why: str | None = None
    category: InterviewCategory | None = None
    impact: QuestionImpact = "medium"
    options: list[InterviewOption]
    allow_custom_answer: bool = False
    selected_option_id: str | None = None
    selected_text: str | None
    custom_answer: str | None = None
    affects: list[str] = Field(default_factory=list)
    status: InterviewQuestionState = "pending"
    question_source: InterviewQuestionSource = "fallback_generated"
    answered_at: datetime | None = None
    rationale: str | None = None
    selected_option: str | None = None


class InterviewSessionRead(BaseModel):
    id: int
    project_id: int
    question_budget: int
    questions_asked: int
    questions_remaining: int
    questions_generated: int = 0
    questions_answered: int = 0
    pending_questions: int = 0
    generation_budget_remaining: int = 0
    manager_mode: ManagerMode
    stopped_early: bool = False
    stop_reason: str | None = None
    confidence: dict[str, float] = Field(default_factory=dict)
    understanding_summary: str | None = None
    known_facts: dict[str, Any] = Field(default_factory=dict)
    unknowns: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    generation_sources: list[InterviewQuestionSource] = Field(default_factory=list)
    question_count: int
    current_index: int
    status: str
    questions: list[InterviewQuestionRead]


class ProjectUnderstandingRead(BaseModel):
    project_id: int
    summary: str
    known_facts_json: dict[str, Any] = Field(default_factory=dict)
    unknowns_json: dict[str, Any] = Field(default_factory=dict)
    assumptions_json: list[str] = Field(default_factory=list)
    constraints_json: list[str] = Field(default_factory=list)
    confidence_by_category_json: dict[str, float] = Field(default_factory=dict)
    updated_at: datetime


class InterviewQuestionAnswerRequest(BaseModel):
    project_id: int
    option_id: str
    selected_text: str
    custom_answer: str | None = None


class InterviewAnswerRequest(BaseModel):
    question_id: int
    option_id: str
    selected_text: str
    custom_answer: str | None = None


class PlanGenerateRequest(BaseModel):
    force_rebuild: bool = False


class PlanRead(BaseModel):
    id: int
    project_id: int
    version: int
    content_markdown: str
    status: str
    summary_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlanApproveRequest(BaseModel):
    action: PlanAction
    note: str | None = None


class ManagerDocFile(BaseModel):
    filename: str
    content: str


class ManagerDocUpdate(BaseModel):
    summary_markdown: str
    files: list[ManagerDocFile]


class ManagerPlan(BaseModel):
    refined_summary: str
    mvp_scope: list[str]
    milestones: list[str]
    recommended_architecture: list[str]
    agent_roster: list[dict[str, str]]
    task_breakdown: list[str]
    validation_plan: list[str]
    risks: list[str]
    definition_of_done: list[str]
    content_markdown: str
    summary_json: dict[str, Any]


class ManagerTaskItem(BaseModel):
    title: str
    goal: str
    scope: str
    agent_role: str
    milestone: str
    priority: int
    allowed_paths: list[str]
    forbidden_paths: list[str]
    validation_steps: list[str]
    success_criteria: list[str]
    estimated_complexity: TaskComplexity
    dependencies: list[int] = Field(default_factory=list)
    status: TaskStatus = "backlog"


class ManagerTaskDecomposition(BaseModel):
    summary_markdown: str
    milestones: list[str]
    tasks: list[ManagerTaskItem]


class ManagerWorkerDecision(BaseModel):
    decision_type: WorkerDecisionType
    summary_markdown: str
    task_id: int | None = None
    assign_to_agent_id: int | None = None
    follow_up_title: str | None = None
    follow_up_goal: str | None = None
    escalation_message: str | None = None


class ManagerHandoff(BaseModel):
    summary_markdown: str
    what_was_built: list[str]
    how_to_run: list[str]
    how_to_use: list[str]
    tests_builds_run: list[str]
    known_limitations: list[str]
    remaining_risks: list[str]
    suggested_next_improvements: list[str]


class WorkerReport(BaseModel):
    agent: str
    task_id: str
    status: WorkerReportStatus
    summary: str
    files_changed: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_next_task: str = ""


class RunnerResultEdit(BaseModel):
    path: str
    content: str | None = None
    summary: str | None = None


class RunnerResultEvidence(BaseModel):
    kind: EvidenceType | str
    summary: str
    status: EvidenceStatus | str = "unknown"
    source_path: str | None = None
    command: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RunnerResultEnvelope(BaseModel):
    status: RunnerResultStatus
    runner_type: str
    lane: RunnerLaneType = "implementation"
    summary: str
    report: WorkerReport
    files_changed: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    commands_attempted: list[str] = Field(default_factory=list)
    evidence: list[RunnerResultEvidence] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    approvals_requested: list[dict[str, Any]] = Field(default_factory=list)
    recovery_plan: list[str] = Field(default_factory=list)
    edits: list[RunnerResultEdit] = Field(default_factory=list)
    failure_classification: FailureClassification | None = None
    needs_approval: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AgentRead(BaseModel):
    id: int
    project_id: int
    name: str
    role: str
    kind: str
    status: str
    current_task_id: int | None
    swarm_plan_id: int | None = None
    workspace_path: str
    archetype: str | None = None
    mission: str | None = None
    retire_when: str | None = None
    session_ref: str | None
    locked_paths_json: list[str] | None
    failure_count: int
    last_report_summary: str | None
    active_model: str | None
    active_reasoning_effort: str | None
    active_runner_type: str | None
    current_action: str | None
    current_task_title: str | None = None
    display_status: AgentDisplayStatus | str = "idle"
    runner_mode: str | None = None
    needs_approval: bool = False
    last_update: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskRead(BaseModel):
    id: int
    project_id: int
    assigned_agent_id: int | None
    title: str
    goal: str
    scope: str
    agent_role: str | None
    milestone: str | None
    allowed_paths_json: list[str]
    forbidden_paths_json: list[str]
    validation_steps_json: list[str]
    success_criteria_json: list[str]
    estimated_complexity: TaskComplexity
    dependencies_json: list[int]
    status: str
    failure_count: int
    waiting_reason: str | None
    priority: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentActionResponse(BaseModel):
    ok: bool
    message: str
    run_id: int | None = None


class TaskGenerationResponse(BaseModel):
    count: int
    manager_mode_used: str


class ReservationRead(BaseModel):
    id: int
    project_id: int
    task_id: int
    agent_id: int
    path: str
    created_at: datetime
    released_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class RunReportRequest(WorkerReport):
    pass


class EventRead(BaseModel):
    id: int
    project_id: int
    event_type: str
    payload_json: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ManagerMessageRequest(BaseModel):
    message: str = Field(min_length=1)


class LogRead(BaseModel):
    agent_id: int
    logs_path: str | None
    content: str


class ProjectSettingsRead(BaseModel):
    project_id: int
    provider: ProviderId = "codex"
    manager_model: str | None
    default_worker_model: str | None
    manager_reasoning_effort: ReasoningEffort | None
    default_worker_reasoning_effort: ReasoningEffort | None
    per_role_model_overrides_json: dict[str, str]
    per_role_reasoning_overrides_json: dict[str, str]
    provider_endpoint: str | None = None
    adapter_command: str | None = None
    adapter_args_json: list[str] = Field(default_factory=list)
    runner_mode: RunnerMode
    sandbox_mode: SandboxMode
    approval_policy: ApprovalPolicy
    workspace_widgets_json: list[str] = Field(default_factory=list)
    approval_overrides_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectSettingsUpdate(BaseModel):
    provider: ProviderId | None = None
    manager_model: str | None = None
    default_worker_model: str | None = None
    manager_reasoning_effort: ReasoningEffort | None = None
    default_worker_reasoning_effort: ReasoningEffort | None = None
    per_role_model_overrides_json: dict[str, str] | None = None
    per_role_reasoning_overrides_json: dict[str, str] | None = None
    provider_endpoint: str | None = None
    adapter_command: str | None = None
    adapter_args_json: list[str] | None = None
    runner_mode: RunnerMode | None = None
    sandbox_mode: SandboxMode | None = None
    approval_policy: ApprovalPolicy | None = None
    workspace_widgets_json: list[str] | None = None
    approval_overrides_json: dict[str, Any] | None = None


class SwarmPreferencesRead(BaseModel):
    project_id: int
    optimization_mode: SwarmOptimizationMode = "balanced"
    swarm_aggressiveness: SwarmAggressiveness = "medium"
    max_agents: int = 8
    require_approval_above_agent_count: int = 10
    allow_dynamic_spawning: bool = True
    allow_dynamic_retirement: bool = True
    docs_depth: DocsDepth = "standard"
    testing_depth: TestingDepth = "standard"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SwarmPreferencesUpdate(BaseModel):
    optimization_mode: SwarmOptimizationMode | None = None
    swarm_aggressiveness: SwarmAggressiveness | None = None
    max_agents: int | None = Field(default=None, ge=1, le=50)
    require_approval_above_agent_count: int | None = Field(default=None, ge=1, le=50)
    allow_dynamic_spawning: bool | None = None
    allow_dynamic_retirement: bool | None = None
    docs_depth: DocsDepth | None = None
    testing_depth: TestingDepth | None = None


class AgentArchetypeRead(BaseModel):
    id: int
    name: str
    purpose: str
    default_guidelines: str
    default_tools_json: list[str] = Field(default_factory=list)
    default_permissions_json: dict[str, Any] = Field(default_factory=dict)
    spawn_triggers_json: list[str] = Field(default_factory=list)
    retirement_triggers_json: list[str] = Field(default_factory=list)
    risk_profile: SwarmRisk

    model_config = ConfigDict(from_attributes=True)


class SwarmAgentSpecRead(BaseModel):
    id: int
    swarm_plan_id: int
    project_id: int
    archetype: str
    name: str
    mission: str
    model_policy: str
    toolset_json: list[str] = Field(default_factory=list)
    allowed_paths_json: list[str] = Field(default_factory=list)
    forbidden_paths_json: list[str] = Field(default_factory=list)
    spawn_phase: str
    retire_when: str
    priority: int
    iteration_budget: int = 1
    status: SwarmAgentSpecStatus

    model_config = ConfigDict(from_attributes=True)


class SwarmPlanRequest(BaseModel):
    goal: str | None = None
    milestone_id: int | None = None


class SwarmPlanReviseRequest(BaseModel):
    note: str | None = None


class SwarmScaleRequest(BaseModel):
    direction: Literal["up", "down"]
    reason: str | None = None
    count: int = Field(default=1, ge=1, le=10)


class SwarmPlanRead(BaseModel):
    id: int
    project_id: int
    milestone_id: int | None = None
    mode: SwarmOptimizationMode | str
    goal: str
    recommended_agent_count: int
    max_agent_count: int
    coordination_risk: SwarmRisk | str
    path_conflict_risk: SwarmRisk | str
    expected_bottlenecks_json: list[str] = Field(default_factory=list)
    validation_strategy_json: list[str] = Field(default_factory=list)
    strategy_summary: str
    approved_by_user: bool = False
    status: SwarmPlanStatus | str
    created_at: datetime
    updated_at: datetime
    approval_required: bool = False
    usage_warning: str | None = None
    active_agent_count: int = 0
    current_bottleneck: str | None = None
    dynamic_spawning_enabled: bool = True
    dynamic_retirement_enabled: bool = True
    spec_status_summary: dict[str, int] = Field(default_factory=dict)
    launch_readiness: dict[str, Any] = Field(default_factory=dict)
    recommended_wave_label: str | None = None
    recommended_next_step: str | None = None
    specs: list[SwarmAgentSpecRead] = Field(default_factory=list)


class SwarmEventRead(BaseModel):
    id: int
    project_id: int
    swarm_plan_id: int | None = None
    event_type: SwarmEventType | str
    message: str
    agent_id: int | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class SwarmSpawnResponse(BaseModel):
    ok: bool = True
    message: str
    swarm_plan: SwarmPlanRead
    agents_spawned: int = 0
    agents_retired: int = 0


class ManagerMessageRead(BaseModel):
    id: int
    project_id: int
    role: Literal["user", "manager", "system", "agent"]
    message_type: ManagerMessageType
    content_markdown: str
    created_at: datetime
    related_agent_id: int | None = None
    related_task_id: int | None = None
    actions_json: list[dict[str, Any]] | None = None
    resolved_at: datetime | None = None
    metadata_json: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class ManagerMessageCreate(BaseModel):
    message: str = Field(min_length=1)


class ManagerQuestionRead(BaseModel):
    id: int
    project_id: int
    question: str
    question_markdown: str | None = None
    options_json: list[dict[str, Any]] = Field(default_factory=list)
    impact: QuestionImpact
    status: QuestionStatus
    selected_option_id: str | None = None
    selected_text: str | None = None
    manager_recommendation: str | None = None
    auto_decide_at: datetime | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    related_task_id: int | None = None
    related_agent_id: int | None = None
    metadata_json: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class ManagerQuestionAnswer(BaseModel):
    project_id: int | None = None
    option_id: str
    selected_text: str


class ApprovalResolveRequest(BaseModel):
    project_id: int


class ApprovalRequestRead(BaseModel):
    id: int
    project_id: int
    request_type: ApprovalRequestType
    requesting_agent_id: int | None = None
    task_id: int | None = None
    title: str
    reason_short: str
    risk_level: RiskLevel
    status: ApprovalRequestStatus
    cwd: str | None = None
    request_payload_json: dict[str, Any] = Field(default_factory=dict)
    runner_ref: str | None = None
    resolved_by: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SecurityPolicyRead(BaseModel):
    id: int
    scope: SecurityScope
    project_id: int | None = None
    default_command_policy: DefaultExecutionPolicy
    default_tool_policy: DefaultExecutionPolicy
    network_access_policy: NetworkAccessPolicy
    write_access_policy: WriteAccessPolicy
    external_account_policy: ExternalAccountPolicy
    deployment_policy: DeploymentPolicy
    destructive_action_policy: DestructiveActionPolicy
    auto_approve_low_risk: bool
    auto_approve_medium_risk: bool
    high_risk_requires_user: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SecurityPolicyUpdate(BaseModel):
    default_command_policy: DefaultExecutionPolicy | None = None
    default_tool_policy: DefaultExecutionPolicy | None = None
    network_access_policy: NetworkAccessPolicy | None = None
    write_access_policy: WriteAccessPolicy | None = None
    external_account_policy: ExternalAccountPolicy | None = None
    deployment_policy: DeploymentPolicy | None = None
    destructive_action_policy: DestructiveActionPolicy | None = None
    auto_approve_low_risk: bool | None = None
    auto_approve_medium_risk: bool | None = None
    high_risk_requires_user: bool | None = None


class RiskAssessRequest(BaseModel):
    project_id: int | None = None
    action_type: str
    title: str | None = None
    summary: str | None = None
    command: str | None = None
    tool_name: str | None = None
    cwd: str | None = None
    affected_paths_json: list[str] = Field(default_factory=list)
    external_access_requested: bool = False
    modifies_files: bool = False
    modifies_package_files: bool = False
    deletes_files: bool = False
    deploys: bool = False
    accesses_network: bool = False
    accesses_credentials: bool = False
    writes_outside_workspace: bool = False


class RiskAssessmentRead(BaseModel):
    id: int
    project_id: int | None = None
    action_type: str
    title: str
    summary: str
    risk_level: RiskLevel
    reasons_json: list[str] = Field(default_factory=list)
    affected_paths_json: list[str] = Field(default_factory=list)
    external_access_json: dict[str, Any] = Field(default_factory=dict)
    recommended_policy: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalAuditLogRead(BaseModel):
    id: int
    project_id: int | None = None
    orchestration_id: int | None = None
    decision_id: int | None = None
    action_type: str
    action_summary: str
    risk_level: RiskLevel
    decision: ApprovalAuditDecision
    decided_by: ApprovalAuditActor
    reason: str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class OrchestrationAttachRequest(BaseModel):
    workspace_path: str
    project_name: str | None = None
    mode: AttachMode = "auto"
    read_only_first: bool = True
    attach_policy: AttachPolicy = "reuse_existing"


class RunnerAvailabilityRead(BaseModel):
    runner_type: str
    availability: bool
    config_status: str
    supports_background: bool
    supports_streaming: bool
    supports_approvals: bool
    notes: list[str] = Field(default_factory=list)


class OrchestrationSessionRead(BaseModel):
    id: int
    project_id: int
    workspace_path: str
    source: OrchestrationSource
    user_request: str
    status: OrchestrationStatus
    manager_status: str
    mode: OrchestrationMode = "unknown"
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class OrchestrationAttachRead(BaseModel):
    project: ProjectRead
    project_id: int | None = None
    project_name: str | None = None
    source_type: ProjectSourceType | None = None
    workspace_path: str | None = None
    orchestration: OrchestrationSessionRead | None = None
    attach_outcome: str
    next_action: str | None = None
    reused_existing_project: bool = False
    reused_existing_orchestration: bool = False
    user_action_required: bool = False
    pending_decision_id: int | None = None
    message: str
    status_summary_markdown: str | None = None


class OrchestrationCreateRequest(BaseModel):
    project_id: int
    user_request: str = Field(min_length=1)
    source: OrchestrationSource = "codex_plugin"
    orchestration_id: int | None = None
    mode: OrchestrationMode | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OrchestrationEventRead(BaseModel):
    id: int
    orchestration_id: int
    project_id: int
    event_type: str
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PendingDecisionRead(BaseModel):
    id: int
    project_id: int | None = None
    orchestration_id: int | None = None
    decision_type: PendingDecisionType
    title: str
    message: str
    requesting_agent_id: int | None = None
    related_task_id: int | None = None
    risk_level: RiskLevel
    options: list[dict[str, Any]] = Field(default_factory=list)
    options_json: list[dict[str, Any]] = Field(default_factory=list)
    recommended_option: str | None = None
    status: PendingDecisionStatus
    created_at: datetime
    presentation: dict[str, Any] | None = None
    presentation_json: dict[str, Any] | None = None
    answered_at: datetime | None = None
    answer_json: dict[str, Any] | None = None
    related_agent_id: int | None = None


class PendingDecisionAnswerRequest(BaseModel):
    option_id: str
    selected_text: str
    free_text: str | None = None


class ProblemDetailsRead(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    family: str
    severity: ErrorSeverity
    breakpoint: str
    retryable: bool
    user_action_required: bool
    recommended_fix: str
    correlation_id: str
    orchestration_id: int | None = None
    project_id: int | None = None
    runner: str | None = None
    redaction_status: BridgeRedactionStatus = "clean"
    safe_details: dict[str, Any] = Field(default_factory=dict)


class BridgeMessageRead(BaseModel):
    id: str
    project_id: int | None = None
    orchestration_id: int | None = None
    source_type: BridgeMessageSourceType
    message_type: BridgeMessageType
    title: str
    summary: str
    user_action_required: bool = False
    risk_level: RiskLevel | None = None
    options_json: list[dict[str, Any]] | None = None
    machine_payload_json: dict[str, Any] | None = None
    fallback_markdown: str
    redaction_status: BridgeRedactionStatus = "clean"
    created_at: datetime
    expires_at: datetime | None = None
    resolved_at: datetime | None = None


class PendingDecisionAnswerResultRead(BaseModel):
    decision: PendingDecisionRead
    next_status_summary: BridgeMessageRead | None = None


class HeadlessHappyPathDemoRequest(BaseModel):
    workspace_path: str
    project_name: str | None = None
    user_request: str = Field(default="Use Mission Control for this repo and fix the failing tests.", min_length=1)
    mode: AttachMode = "existing_codebase"
    read_only_first: bool = True
    attach_policy: AttachPolicy = "reuse_existing"
    create_pending_decision: bool = True


class HeadlessHappyPathDemoRead(BaseModel):
    attach: OrchestrationAttachRead
    orchestration: OrchestrationSessionRead
    initial_status_summary: BridgeMessageRead
    pending_decision: PendingDecisionRead | None = None
    decision_bridge_message: BridgeMessageRead | None = None
    answer_result: PendingDecisionAnswerResultRead | None = None
    event_digest: BridgeMessageRead | None = None
    handoff_summary: BridgeMessageRead | None = None
    dry_run: bool = True


class HeadlessStartTaskRequest(BaseModel):
    workspace_path: str | None = None
    project_id: int | None = None
    user_request: str = Field(min_length=1)
    strategy: HeadlessTaskStrategy = "manager_decides"
    mode: HeadlessTaskMode = "auto"
    interview_mode: InterviewChoice = "manager_decides"
    attach_policy: AttachPolicy = "reuse_existing"


class HeadlessStartTaskRead(BaseModel):
    project: ProjectRead
    orchestration: OrchestrationSessionRead | None = None
    attach: OrchestrationAttachRead | None = None
    status_summary: BridgeMessageRead | None = None
    pending_decisions: list[PendingDecisionRead] = Field(default_factory=list)
    next_action: str | None = None
    user_action_required: bool = False
    mode_used: OrchestrationMode = "unknown"


class SafeModeStatusRead(BaseModel):
    project_id: int
    enabled: bool
    require_all_command_approvals: bool
    destructive_actions_blocked: bool
    deployment_tools_blocked: bool
    external_account_tools_require_approval: bool
    dynamic_spawning_paused: bool
    require_read_only_scan_for_imported_codebases: bool
    bridge_message: BridgeMessageRead


class SubagentPolicyRead(BaseModel):
    id: int = 1
    enabled: bool = True
    default_mode: SubagentDefaultMode = "read_only"
    max_subagents_per_burst: int = 6
    max_runtime_seconds: int = 600
    allow_file_edits: bool = False
    allow_commands: bool = False
    require_user_approval_above_count: int = 3
    allowed_task_types_json: list[SubagentTaskType | str] = Field(default_factory=list)
    default_spawn_method: SubagentSpawnMethod = "codex_chat_bridge"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubagentPolicyUpdate(BaseModel):
    enabled: bool | None = None
    default_mode: SubagentDefaultMode | None = None
    max_subagents_per_burst: int | None = Field(default=None, ge=1, le=12)
    max_runtime_seconds: int | None = Field(default=None, ge=60, le=3600)
    allow_file_edits: bool | None = None
    allow_commands: bool | None = None
    require_user_approval_above_count: int | None = Field(default=None, ge=1, le=12)
    allowed_task_types_json: list[SubagentTaskType | str] | None = None
    default_spawn_method: SubagentSpawnMethod | None = None


class SubagentPolicySummaryRead(BaseModel):
    enabled: bool
    default_mode: SubagentDefaultMode
    sandbox_mode: Literal["workspace-write", "read-only"]
    max_subagents_per_burst: int
    max_runtime_seconds: int
    allow_file_edits: bool
    allow_commands: bool
    require_user_approval_above_count: int
    allowed_task_types_json: list[SubagentTaskType | str] = Field(default_factory=list)
    default_spawn_method: SubagentSpawnMethod
    writes_allowed: bool
    read_only_default: bool
    command_capable: bool


class SubagentSpecRead(BaseModel):
    id: int
    batch_id: int
    name: str
    display_name: str
    custom_agent_name: str | None = None
    mission: str
    sandbox_mode: str
    allowed_paths_json: list[str] = Field(default_factory=list)
    forbidden_paths_json: list[str] = Field(default_factory=list)
    expected_output: str
    timeout_seconds: int
    status: str
    result_summary: str | None = None
    evidence_json: list[str] = Field(default_factory=list)
    risks_found_json: list[str] = Field(default_factory=list)
    recommendations_json: list[str] = Field(default_factory=list)
    confidence: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SubagentBatchRead(BaseModel):
    id: int
    project_id: int
    orchestration_id: int | None = None
    purpose: str
    task_type: SubagentTaskType | str
    status: SubagentBatchStatus | str
    spawn_method: SubagentSpawnMethod | str
    risk_level: RiskLevel | str
    estimated_intensity: SubagentEstimatedIntensity | str
    reason: str
    summary: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    specs: list[SubagentSpecRead] = Field(default_factory=list)
    bridge_message: BridgeMessageRead | None = None
    spawn_instructions_markdown: str | None = None
    manual_prompt_text: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SubagentBurstRecommendRequest(BaseModel):
    purpose: str = Field(min_length=1)
    task_type: SubagentTaskType
    template_name: str | None = None
    codebase_size: CodebaseSize | str | None = None
    task_complexity: TaskComplexity = "medium"
    user_priority: Literal["low", "normal", "high", "urgent"] = "normal"
    current_phase: str | None = None
    expected_parallelism: int | None = Field(default=None, ge=1, le=12)
    risk_level: RiskLevel = "low"
    bounded_scope: bool = True
    requires_file_edits: bool = False
    requires_commands: bool = False
    allowed_paths_json: list[str] = Field(default_factory=list)
    forbidden_paths_json: list[str] = Field(default_factory=list)
    spawn_method: SubagentSpawnMethod = "codex_chat_bridge"


class SubagentBurstRecommendationRead(BaseModel):
    recommended: bool
    suggested_burst_template: str | None = None
    number_of_subagents: int = 0
    reason: str
    risks: list[str] = Field(default_factory=list)
    pending_decision_required: bool = False
    batch: SubagentBatchRead | None = None
    policy: SubagentPolicyRead


class SubagentResultItem(BaseModel):
    subagent_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    risks_found: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] | str = "medium"


class SubagentBatchResultsIngestRequest(BaseModel):
    results: list[SubagentResultItem] = Field(default_factory=list)


class CustomCodexAgentsGenerateRequest(BaseModel):
    overwrite_existing: bool = False
    template_names: list[str] = Field(default_factory=list)


class CustomCodexAgentsGenerateRead(BaseModel):
    agents_dir: str
    generated_files: list[str] = Field(default_factory=list)
    skipped_existing_files: list[str] = Field(default_factory=list)
    backup_files: list[str] = Field(default_factory=list)
    generated_count: int = 0


class ResumeWorkspaceRequest(BaseModel):
    workspace_path: str
    attach_policy: AttachPolicy = "reuse_existing"


class ResumeWorkspaceRead(BaseModel):
    workspace_path: str
    status: Literal["found_active", "found_recent", "found_project_only", "needs_selection", "not_found"]
    message: str
    project: ProjectRead | None = None
    orchestration: OrchestrationSessionRead | None = None
    status_summary: BridgeMessageRead | None = None
    pending_decisions: list[PendingDecisionRead] = Field(default_factory=list)
    user_action_required: bool = False


class OrchestrationStatusRead(BaseModel):
    orchestration_id: int
    project_id: int
    project_name: str
    orchestration_status: OrchestrationStatus
    manager_status: str
    current_phase: str
    active_agents: list[dict[str, Any]] = Field(default_factory=list)
    pending_decisions_count: int = 0
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    current_blockers: list[str] = Field(default_factory=list)
    next_expected_action: str
    user_action_required: bool = False
    handoff_readiness: str = "not_ready"
    runner_inventory: list[RunnerAvailabilityRead] = Field(default_factory=list)
    background_runtime: dict[str, Any] = Field(default_factory=dict)


class DaemonStatusRead(BaseModel):
    status: str
    metadata_status: str | None = None
    mode: str
    host: str
    port: int
    pid: int
    started_at: datetime
    token_configured: bool = False
    active_orchestrations: int = 0
    runner_inventory: list[RunnerAvailabilityRead] = Field(default_factory=list)
    background_runtime: list[dict[str, Any]] = Field(default_factory=list)
    retrying_orchestrations: int = 0
    active_background_turns: int = 0
    dashboard_url: str
    repo_root: str | None = None
    runtime_root: str | None = None
    launcher_root: str | None = None
    notes: list[str] = Field(default_factory=list)


class ProjectActionRead(BaseModel):
    id: str
    project_id: int
    type: ProjectActionType
    severity: ProjectActionSeverity
    title: str
    message: str
    requesting_agent_id: int | None = None
    related_task_id: int | None = None
    command_id: int | None = None
    tool_request_id: int | None = None
    question_id: int | None = None
    created_at: datetime
    expires_at: datetime | None = None
    auto_decide_at: datetime | None = None
    resolved_at: datetime | None = None
    actions_json: list[dict[str, Any]] = Field(default_factory=list)


class ManagerQueueItemRead(BaseModel):
    id: str
    type: str
    title: str
    status: str
    related_task_id: int | None = None
    related_agent_id: int | None = None
    created_at: datetime


class ManagerQueueRead(BaseModel):
    next_up: list[ManagerQueueItemRead] = Field(default_factory=list)
    waiting_on_user: list[ManagerQueueItemRead] = Field(default_factory=list)
    recently_decided: list[ManagerQueueItemRead] = Field(default_factory=list)
    deferred: list[ManagerQueueItemRead] = Field(default_factory=list)


class WorkspaceWidgetsUpdate(BaseModel):
    widgets: list[str] = Field(default_factory=list)


class WidgetDefinitionRead(BaseModel):
    id: int
    widget_type: str
    title: str
    description: str
    scope: WidgetScope
    default_area: WidgetArea
    default_size: WidgetSize
    category: WidgetCategory | str
    requires_project: bool = False
    requires_tool: str | None = None
    coming_soon: bool = False
    risk_level: RiskLevel | None = None

    model_config = ConfigDict(from_attributes=True)


class WidgetInstanceRead(BaseModel):
    id: int
    scope: WidgetScope
    project_id: int | None = None
    widget_type: str
    area: WidgetArea
    order_index: int
    size: WidgetSize
    collapsed: bool = False
    enabled: bool = True
    config_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WidgetInstanceCreate(BaseModel):
    scope: WidgetScope
    project_id: int | None = None
    widget_type: str
    area: WidgetArea | None = None
    order_index: int | None = Field(default=None, ge=0)
    size: WidgetSize | None = None
    collapsed: bool = False
    enabled: bool = True
    config_json: dict[str, Any] = Field(default_factory=dict)


class WidgetInstanceUpdate(BaseModel):
    area: WidgetArea | None = None
    order_index: int | None = Field(default=None, ge=0)
    size: WidgetSize | None = None
    collapsed: bool | None = None
    enabled: bool | None = None
    config_json: dict[str, Any] | None = None


class WidgetDataResponseRead(BaseModel):
    widget_instance_id: int
    widget_type: str
    title: str
    status: WidgetDataStatus
    data_json: dict[str, Any] = Field(default_factory=dict)
    empty_state: str | None = None
    warnings_json: list[str] = Field(default_factory=list)
    updated_at: datetime


class WidgetSummaryRead(BaseModel):
    scope: WidgetScope
    project_id: int | None = None
    instances: list[WidgetInstanceRead] = Field(default_factory=list)
    data: list[WidgetDataResponseRead] = Field(default_factory=list)
    catalog: list[WidgetDefinitionRead] = Field(default_factory=list)


class WidgetAddRequest(BaseModel):
    widget_type: str
    area: WidgetArea | None = None
    size: WidgetSize | None = None


class SwarmBudgetRead(BaseModel):
    project_id: int
    max_agents: int
    require_approval_above_agent_count: int
    prefer_local_models: bool = False
    premium_models_only_for: list[str] = Field(default_factory=list)
    current_active_agents: int = 0
    current_intensity: SwarmIntensity | str = "low"
    dynamic_spawning_paused: bool = False
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentContractRead(BaseModel):
    id: int
    project_id: int
    agent_id: int | None = None
    agent_name: str
    archetype: str
    mission: str
    allowed_paths_json: list[str] = Field(default_factory=list)
    forbidden_paths_json: list[str] = Field(default_factory=list)
    allowed_tools_json: list[str] = Field(default_factory=list)
    expected_output: str
    validation_required_json: list[str] = Field(default_factory=list)
    stop_conditions_json: list[str] = Field(default_factory=list)
    escalation_conditions_json: list[str] = Field(default_factory=list)
    completion_report_schema_json: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PathLockRead(BaseModel):
    id: int
    project_id: int
    path_pattern: str
    owner_agent_id: int | None = None
    owner_task_id: int | None = None
    reason: str
    status: str
    created_at: datetime
    released_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DecisionRecordRead(BaseModel):
    id: int
    project_id: int
    decision_type: str
    title: str
    decision: str
    reason: str
    made_by: str
    impact_area_json: list[str] = Field(default_factory=list)
    related_task_id: int | None = None
    related_agent_id: int | None = None
    created_at: datetime
    reversible: bool = False
    superseded_by: int | None = None

    model_config = ConfigDict(from_attributes=True)


class OperatorSnapshotAgentRead(BaseModel):
    id: int
    name: str
    role: str
    display_status: str
    current_action: str | None = None


class OperatorSnapshotTraceRead(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    span_kind: TraceSpanKind | str
    outcome: str
    summary: str
    failure_classification: FailureClassification | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class OperatorSnapshotEvidenceRead(BaseModel):
    id: int
    evidence_type: str
    status: str
    summary: str
    source_path: str | None = None
    command: str | None = None


class OperatorSnapshotRead(BaseModel):
    project_id: int
    project_name: str
    project_status: str
    overall_status: str
    orchestration_status: str | None = None
    handoff_status: str = "not_ready"
    current_action: str
    pending_approvals_count: int = 0
    pending_questions_count: int = 0
    active_agent_count: int = 0
    active_agents: list[OperatorSnapshotAgentRead] = Field(default_factory=list)
    trace_span_count: int = 0
    trace_spans: list[OperatorSnapshotTraceRead] = Field(default_factory=list)
    trace_outcome_counts: dict[str, int] = Field(default_factory=dict)
    trace_outcome_group_count: int = 0
    trace_span_kind_counts: dict[str, int] = Field(default_factory=dict)
    trace_span_kind_group_count: int = 0
    trace_failure_classifications: list[str] = Field(default_factory=list)
    trace_failure_classification_counts: dict[str, int] = Field(default_factory=dict)
    trace_failure_classification_group_count: int = 0
    evidence_item_count: int = 0
    evidence_items: list[OperatorSnapshotEvidenceRead] = Field(default_factory=list)
    evidence_status_counts: dict[str, int] = Field(default_factory=dict)
    evidence_status_group_count: int = 0
    current_focus_count: int = 0
    current_focus: list[str] = Field(default_factory=list)
    top_risk_count: int = 0
    top_risks: list[str] = Field(default_factory=list)
    recent_event_count: int = 0
    recent_events: list[str] = Field(default_factory=list)
    validation_gap_count: int = 0
    swarm_mode: str | None = None
    recommended_next_action: str
    diagnostics_summary: str | None = None
    diagnostics_bundle_path: str | None = None
    performance_note: str | None = None
    snapshot_markdown: str
    generated_at: datetime


class OperationalInstinctRead(BaseModel):
    key: str
    title: str
    trigger: str
    rule: str
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    confidence: str
    tags: list[str] = Field(default_factory=list)


class OperationalInstinctPreviewRead(BaseModel):
    project_id: int
    instinct_count: int = 0
    instinct_keys: list[str] = Field(default_factory=list)
    confidence_levels: list[str] = Field(default_factory=list)
    confidence_counts: dict[str, int] = Field(default_factory=dict)
    confidence_group_count: int = 0
    tags: list[str] = Field(default_factory=list)
    tag_counts: dict[str, int] = Field(default_factory=dict)
    tag_group_count: int = 0
    evidence_item_count: int = 0
    evidenceful_instinct_count: int = 0
    instincts: list[OperationalInstinctRead] = Field(default_factory=list)
    generated_at: datetime


class VerificationBriefRead(BaseModel):
    project_id: int
    readiness: str
    required_checks: list[str] = Field(default_factory=list)
    required_check_count: int = 0
    recommended_checks: list[str] = Field(default_factory=list)
    recommended_check_count: int = 0
    evidence_gaps: list[str] = Field(default_factory=list)
    evidence_gap_count: int = 0
    release_blockers: list[str] = Field(default_factory=list)
    release_blocker_count: int = 0
    handoff_warnings: list[str] = Field(default_factory=list)
    handoff_warning_count: int = 0
    loop_strategy: list[str] = Field(default_factory=list)
    loop_strategy_count: int = 0
    brief_markdown: str
    generated_at: datetime


class CapabilitySectionRead(BaseModel):
    key: str
    title: str
    status: str
    summary: str
    details: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ProjectCapabilityReportRead(BaseModel):
    project_id: int
    project_name: str
    section_count: int = 0
    section_keys: list[str] = Field(default_factory=list)
    section_statuses: list[str] = Field(default_factory=list)
    section_status_counts: dict[str, int] = Field(default_factory=dict)
    section_status_group_count: int = 0
    ready_section_count: int = 0
    needs_setup_section_count: int = 0
    warning_section_count: int = 0
    gathering_section_count: int = 0
    awaiting_second_pack_section_count: int = 0
    command_count: int = 0
    commands: list[str] = Field(default_factory=list)
    artifact_count: int = 0
    artifacts: list[str] = Field(default_factory=list)
    detail_count: int = 0
    metadata_section_count: int = 0
    sections: list[CapabilitySectionRead] = Field(default_factory=list)
    report_markdown: str
    generated_at: datetime


class WorkspaceToolingItemRead(BaseModel):
    id: str
    label: str
    category: str
    installed: bool = False
    binary_path: str | None = None
    configured: bool = False
    config_files: list[str] = Field(default_factory=list)
    config_sections: list[str] = Field(default_factory=list)
    status: str
    recommended_commands: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WorkspaceToolingPackRead(BaseModel):
    id: str
    title: str
    status: str
    summary: str
    tool_ids: list[str] = Field(default_factory=list)
    installed_tool_ids: list[str] = Field(default_factory=list)
    missing_tool_ids: list[str] = Field(default_factory=list)


class WorkspaceToolingStatusRead(BaseModel):
    project_id: int
    project_name: str
    workspace_path: str | None = None
    available: bool = False
    summary: str
    repo_profile: dict[str, Any] = Field(default_factory=dict)
    tool_count: int = 0
    tool_ids: list[str] = Field(default_factory=list)
    installed_tool_count: int = 0
    installed_tool_ids: list[str] = Field(default_factory=list)
    configured_tool_count: int = 0
    configured_tool_ids: list[str] = Field(default_factory=list)
    missing_tool_count: int = 0
    missing_tool_ids: list[str] = Field(default_factory=list)
    tool_statuses: list[str] = Field(default_factory=list)
    tool_status_counts: dict[str, int] = Field(default_factory=dict)
    tool_status_group_count: int = 0
    tool_categories: list[str] = Field(default_factory=list)
    tool_category_counts: dict[str, int] = Field(default_factory=dict)
    tool_category_group_count: int = 0
    tools: list[WorkspaceToolingItemRead] = Field(default_factory=list)
    pack_count: int = 0
    pack_ids: list[str] = Field(default_factory=list)
    pack_statuses: list[str] = Field(default_factory=list)
    pack_status_counts: dict[str, int] = Field(default_factory=dict)
    pack_status_group_count: int = 0
    packs: list[WorkspaceToolingPackRead] = Field(default_factory=list)
    recommended_next_step_count: int = 0
    recommended_next_steps: list[str] = Field(default_factory=list)
    repo_mode_summary_count: int = 0
    repo_mode_summaries: list[str] = Field(default_factory=list)
    important_path_count: int = 0
    important_paths: list[str] = Field(default_factory=list)
    execution_entrypoint_count: int = 0
    execution_entrypoints: list[str] = Field(default_factory=list)
    runtime_blocker_count: int = 0
    runtime_blockers: list[str] = Field(default_factory=list)
    validation_evidence_target_count: int = 0
    validation_evidence_targets: list[str] = Field(default_factory=list)
    product_lane_status_count: int = 0
    product_lane_statuses: list[str] = Field(default_factory=list)
    execution_lane_summary_count: int = 0
    execution_lane_summaries: list[str] = Field(default_factory=list)
    artifact_kind_summary_count: int = 0
    artifact_kind_summaries: list[str] = Field(default_factory=list)
    command_count: int = 0
    commands: list[str] = Field(default_factory=list)
    intake_commands: list[str] = Field(default_factory=list)
    notebook_paths: list[str] = Field(default_factory=list)
    notebook_commands: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    observability_commands: list[str] = Field(default_factory=list)
    security_commands: list[str] = Field(default_factory=list)
    deployment_commands: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    artifact_inspection_commands: list[str] = Field(default_factory=list)
    checkpoint_commands: list[str] = Field(default_factory=list)
    distributed_launcher_commands: list[str] = Field(default_factory=list)
    config_review_paths: list[str] = Field(default_factory=list)
    config_review_commands: list[str] = Field(default_factory=list)
    tensorflow_repo: dict[str, Any] = Field(default_factory=dict)
    tensorflow_validation_plan: dict[str, Any] = Field(default_factory=dict)
    pytorch_repo: dict[str, Any] = Field(default_factory=dict)
    pytorch_runtime_status: dict[str, Any] = Field(default_factory=dict)
    pytorch_validation_plan: dict[str, Any] = Field(default_factory=dict)
    spatial3d_repo: dict[str, Any] = Field(default_factory=dict)
    spatial3d_validation_plan: dict[str, Any] = Field(default_factory=dict)


class ExecutionPolicySummaryRead(BaseModel):
    project_id: int
    project_name: str
    provider: ProviderId = "codex"
    runner_mode: RunnerMode = "auto"
    sandbox_mode: SandboxMode = "workspace-write"
    approval_policy: ApprovalPolicy = "on-request"
    model_policy_name: str
    manager_model: str | None = None
    worker_model_count: int = 0
    tool_routing_count: int = 0
    approval_required_tool_count: int = 0
    approval_required_tools: list[str] = Field(default_factory=list)
    blocked_tool_count: int = 0
    blocked_tools: list[str] = Field(default_factory=list)
    sandbox_profile_count: int = 0
    default_sandbox_profile: str | None = None
    current_sandbox_profile: str | None = None
    validation_step_count: int = 0
    validation_command_count: int = 0
    validation_commands: list[str] = Field(default_factory=list)
    validation_status: str


class CoordinationSummaryRead(BaseModel):
    project_id: int
    project_name: str
    current_action_type: str
    contract_count: int = 0
    active_contract_count: int = 0
    waiting_lock_count: int = 0
    active_lock_count: int = 0
    unresolved_conflict_count: int = 0
    decision_count: int = 0
    decision_types: list[str] = Field(default_factory=list)
    low_confidence_count: int = 0
    low_confidence_categories: list[str] = Field(default_factory=list)
    failed_gate_count: int = 0
    pending_gate_count: int = 0
    review_gate_count: int = 0


class TensorFlowFeatureCatalogEntryRead(BaseModel):
    feature_id: str
    title: str
    variants: list[str] = Field(default_factory=list)
    summary: str


class TensorFlowFeatureBundleRead(BaseModel):
    feature_id: str
    variant: str
    title: str
    summary: str
    dependencies: list[str] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)
    validation_steps: list[str] = Field(default_factory=list)
    evidence_targets: list[str] = Field(default_factory=list)


class PyTorchFeatureCatalogEntryRead(BaseModel):
    feature_id: str
    title: str
    variants: list[str] = Field(default_factory=list)
    summary: str


class PyTorchFeatureBundleRead(BaseModel):
    feature_id: str
    variant: str
    title: str
    summary: str
    dependencies: list[str] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)
    validation_steps: list[str] = Field(default_factory=list)
    evidence_targets: list[str] = Field(default_factory=list)


class Spatial3DFeatureCatalogEntryRead(BaseModel):
    feature_id: str
    title: str
    variants: list[str] = Field(default_factory=list)
    summary: str


class Spatial3DFeatureBundleRead(BaseModel):
    feature_id: str
    variant: str
    title: str
    summary: str
    dependencies: list[str] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)
    validation_steps: list[str] = Field(default_factory=list)
    evidence_targets: list[str] = Field(default_factory=list)


class CodebaseSearchMatchRead(BaseModel):
    path: str
    line_number: int
    line_text: str


class CodebaseSearchRequest(BaseModel):
    pattern: str = Field(min_length=1)
    glob: str | None = None
    max_matches: int = Field(default=40, ge=1, le=200)


class CodebaseSearchRead(BaseModel):
    project_id: int
    project_name: str
    workspace_path: str
    pattern: str
    glob: str | None = None
    match_count: int = 0
    truncated: bool = False
    search_backend: str
    command: str
    matches: list[CodebaseSearchMatchRead] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WebwrightStatusRead(BaseModel):
    project_id: int
    project_name: str
    workspace_path: str | None = None
    available: bool = False
    install_status: Literal["ready", "partial", "missing"]
    cli_detected: bool = False
    cli_path: str | None = None
    python_package_detected: bool = False
    playwright_package_detected: bool = False
    playwright_cli_detected: bool = False
    version: str | None = None
    launch_command: str | None = None
    workspace_signals: list[str] = Field(default_factory=list)
    summary: str
    recommended_fix: str | None = None
    recommended_install_commands: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    bridge_markdown: str
    details: dict[str, Any] = Field(default_factory=dict)


class NvidiaDynamoStatusRead(BaseModel):
    project_id: int
    project_name: str
    provider: str = "nvidia_dynamo"
    label: str = "NVIDIA Dynamo"
    available: bool = False
    reachable: bool = False
    endpoint: str
    endpoint_configured: bool = False
    api_key_configured: bool = False
    auth_required: bool = False
    authenticated: bool = False
    available_models: list[str] = Field(default_factory=list)
    runtime_ready: bool = False
    runtime_status: str = "blocked"
    runtime_summary: str = ""
    runtime_blockers: list[str] = Field(default_factory=list)
    adapter_command_configured: bool = False
    adapter_command_detected: bool = False
    adapter_command_path: str | None = None
    adapter_args: list[str] = Field(default_factory=list)
    adapter_recipe_source: str | None = None
    summary: str
    notes: list[str] = Field(default_factory=list)


class NvidiaNimStatusRead(BaseModel):
    project_id: int
    project_name: str
    provider: str = "nvidia_nim"
    label: str = "NVIDIA NIM"
    available: bool = False
    reachable: bool = False
    endpoint: str
    endpoint_configured: bool = False
    api_key_configured: bool = False
    auth_required: bool = False
    authenticated: bool = False
    available_models: list[str] = Field(default_factory=list)
    runtime_ready: bool = False
    runtime_status: str = "blocked"
    runtime_summary: str = ""
    runtime_blockers: list[str] = Field(default_factory=list)
    adapter_command_configured: bool = False
    adapter_command_detected: bool = False
    adapter_command_path: str | None = None
    adapter_args: list[str] = Field(default_factory=list)
    adapter_recipe_source: str | None = None
    summary: str
    notes: list[str] = Field(default_factory=list)


class NvidiaAiqStatusRead(BaseModel):
    project_id: int
    project_name: str
    available: bool = False
    install_status: Literal["ready", "partial", "missing"]
    summary: str
    endpoint: str
    endpoint_configured: bool = False
    api_key_configured: bool = False
    auth_required: bool = False
    dask_available: bool | None = None
    agent_types: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    recommended_fix: str | None = None
    notes: list[str] = Field(default_factory=list)


class NvidiaAiqResearchRequest(BaseModel):
    query: str = Field(min_length=1)
    agent_type: str = Field(default="deep_researcher", min_length=1)
    timeout_seconds: int = 90
    poll_interval_seconds: float = 2.0
    expiry_seconds: int = 3600
    endpoint_override: str | None = None


class NvidiaAiqToolInvocationRead(BaseModel):
    name: str | None = None
    status: str | None = None
    workflow: str | None = None


class NvidiaAiqResearchRead(BaseModel):
    project_id: int
    project_name: str
    endpoint: str
    agent_type: str
    job_id: str
    status: str
    timed_out: bool = False
    poll_count: int = 0
    summary: str
    report: str = ""
    source_summary: dict[str, Any] = Field(default_factory=dict)
    tool_count: int = 0
    tools: list[NvidiaAiqToolInvocationRead] = Field(default_factory=list)
    status_payload: dict[str, Any] = Field(default_factory=dict)


class NvidiaGpuDiagnosticsRead(BaseModel):
    project_id: int
    project_name: str
    available: bool = False
    status: str
    summary: str
    prometheus_url: str | None = None
    workspace_relevant: bool = False
    telemetry_status: str = "missing"
    workspace_summary_status: str = "missing"
    repo_mode_enabled: bool = False
    repo_mode: str | None = None
    cluster_usable: bool | None = None
    pending_pod_count: int | None = None
    gpu_memory_saturation_pct: float | None = None
    gpu_memory_saturated: bool = False
    likely_failure_source: str = "unknown"
    blocking_reasons: list[str] = Field(default_factory=list)
    detected_signals: list[str] = Field(default_factory=list)
    observability_sources: list[str] = Field(default_factory=list)
    summary_files: list[str] = Field(default_factory=list)
    safe_commands: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    alerts: list[str] = Field(default_factory=list)
    recommended_fixes: list[str] = Field(default_factory=list)
    queries: dict[str, str] = Field(default_factory=dict)


class NvidiaLocalRuntimeStatusRead(BaseModel):
    project_id: int
    project_name: str
    available: bool = False
    status: str
    summary: str
    repo_mode_enabled: bool = False
    repo_mode: str | None = None
    detected_tools: list[str] = Field(default_factory=list)
    missing_required_tools: list[str] = Field(default_factory=list)
    missing_optional_tools: list[str] = Field(default_factory=list)
    tool_paths: dict[str, str] = Field(default_factory=dict)
    gpu_names: list[str] = Field(default_factory=list)
    driver_version: str | None = None
    nvcc_version: str | None = None
    cuda_release: str | None = None
    cuda_home: str | None = None
    compute_sanitizer_available: bool = False
    nsight_systems_available: bool = False
    nsight_compute_available: bool = False
    cuda_gdb_available: bool = False
    container_toolkit_available: bool = False
    ngc_cli_available: bool = False
    container_runtime_ready: bool = False
    docker_available: bool = False
    recommended_fixes: list[str] = Field(default_factory=list)
    validation_hints: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class NvidiaValidationPlanStepRead(BaseModel):
    title: str
    command: str | None = None
    type: str
    source: str
    status: str


class NvidiaValidationPlanRead(BaseModel):
    project_id: int
    project_name: str
    available: bool = False
    status: str
    summary: str
    repo_mode_enabled: bool = False
    repo_mode: str | None = None
    local_runtime_status: str | None = None
    gpu_diagnostics_status: str | None = None
    sanitizer_ready: bool = False
    profiler_ready: bool = False
    container_smoke_ready: bool = False
    ngc_smoke_image: str | None = None
    steps: list[NvidiaValidationPlanStepRead] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    recommended_fixes: list[str] = Field(default_factory=list)
    evidence_targets: list[str] = Field(default_factory=list)


class ProjectConfidenceRead(BaseModel):
    id: int
    project_id: int
    category: str
    confidence_score: int
    reason: str
    unknowns_json: list[str] = Field(default_factory=list)
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


class RecoveryPlanRead(BaseModel):
    id: int
    project_id: int
    trigger_type: str
    trigger_summary: str
    related_agent_id: int | None = None
    related_task_id: int | None = None
    suggested_actions_json: list[str] = Field(default_factory=list)
    selected_action: str | None = None
    status: str
    created_at: datetime
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentStuckSignalRead(BaseModel):
    id: int
    project_id: int
    agent_id: int
    signal_type: str
    message: str
    severity: str
    detected_at: datetime
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RecoveryPlanPreviewItemRead(BaseModel):
    project_id: int
    trigger_type: str
    trigger_summary: str
    related_agent_id: int | None = None
    related_task_id: int | None = None
    suggested_actions_json: list[str] = Field(default_factory=list)
    status: str = "proposed"
    source: Literal["computed"] = "computed"


class RecoveryPlanPreviewSummaryRead(BaseModel):
    project_id: int
    current_action: dict[str, Any] = Field(default_factory=dict)
    blocked_task_count: int = 0
    stuck_signal_count: int = 0
    persisted_statuses: list[str] = Field(default_factory=list)
    persisted_status_counts: dict[str, int] = Field(default_factory=dict)
    persisted_status_group_count: int = 0
    persisted: list[RecoveryPlanRead] = Field(default_factory=list)
    derived_trigger_types: list[str] = Field(default_factory=list)
    derived_trigger_type_counts: dict[str, int] = Field(default_factory=dict)
    derived_trigger_type_group_count: int = 0
    suggested_action_count: int = 0
    suggested_action_values: list[str] = Field(default_factory=list)
    suggested_action_counts: dict[str, int] = Field(default_factory=dict)
    suggested_action_group_count: int = 0
    derived_candidates: list[RecoveryPlanPreviewItemRead] = Field(default_factory=list)
    stored_count: int = 0
    derived_candidate_count: int = 0
    generated_at: datetime


class ReviewGateRead(BaseModel):
    id: int
    project_id: int
    gate_type: str
    title: str
    status: str
    required: bool = True
    related_task_id: int | None = None
    related_agent_id: int | None = None
    required_checks_json: list[str] = Field(default_factory=list)
    evidence_ids_json: list[int] = Field(default_factory=list)
    result_summary: str | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ModelPolicyRead(BaseModel):
    id: int
    project_id: int | None = None
    policy_name: str
    manager_model: str | None = None
    coding_model: str | None = None
    docs_model: str | None = None
    review_model: str | None = None
    test_model: str | None = None
    research_model: str | None = None
    security_model: str | None = None
    fallback_model: str | None = None
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ToolRoutingPolicyRead(BaseModel):
    id: int
    project_id: int
    agent_archetype: str
    allowed_tools_json: list[str] = Field(default_factory=list)
    requires_approval_tools_json: list[str] = Field(default_factory=list)
    blocked_tools_json: list[str] = Field(default_factory=list)
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SandboxProfileRead(BaseModel):
    id: int
    project_id: int | None = None
    name: str
    description: str
    network_policy: str
    file_write_policy: str
    command_approval_policy: str
    external_tool_policy: str
    deployment_policy: str
    is_default: bool = False

    model_config = ConfigDict(from_attributes=True)


class ManagerAssumptionRead(BaseModel):
    id: int
    project_id: int
    assumption: str
    reason: str
    impact_area_json: list[str] = Field(default_factory=list)
    confidence: int
    status: str
    created_at: datetime
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RepoIntelligenceSummaryRead(BaseModel):
    project_id: int
    languages_json: list[str] = Field(default_factory=list)
    frameworks_json: list[str] = Field(default_factory=list)
    package_managers_json: list[str] = Field(default_factory=list)
    entry_points_json: list[str] = Field(default_factory=list)
    build_commands_json: list[str] = Field(default_factory=list)
    test_commands_json: list[str] = Field(default_factory=list)
    important_folders_json: list[str] = Field(default_factory=list)
    risky_files_json: list[str] = Field(default_factory=list)
    docs_found_json: list[str] = Field(default_factory=list)
    ci_config_json: list[str] = Field(default_factory=list)
    deployment_config_json: list[str] = Field(default_factory=list)
    last_indexed_at: datetime

    @computed_field(return_type=int)
    @property
    def language_count(self) -> int:
        return len(self.languages_json)

    @computed_field(return_type=int)
    @property
    def framework_count(self) -> int:
        return len(self.frameworks_json)

    @computed_field(return_type=int)
    @property
    def package_manager_count(self) -> int:
        return len(self.package_managers_json)

    @computed_field(return_type=int)
    @property
    def entry_point_count(self) -> int:
        return len(self.entry_points_json)

    @computed_field(return_type=int)
    @property
    def build_command_count(self) -> int:
        return len(self.build_commands_json)

    @computed_field(return_type=int)
    @property
    def test_command_count(self) -> int:
        return len(self.test_commands_json)

    @computed_field(return_type=int)
    @property
    def important_folder_count(self) -> int:
        return len(self.important_folders_json)

    @computed_field(return_type=int)
    @property
    def risky_file_count(self) -> int:
        return len(self.risky_files_json)

    @computed_field(return_type=int)
    @property
    def doc_count(self) -> int:
        return len(self.docs_found_json)

    @computed_field(return_type=int)
    @property
    def ci_config_count(self) -> int:
        return len(self.ci_config_json)

    @computed_field(return_type=int)
    @property
    def deployment_config_count(self) -> int:
        return len(self.deployment_config_json)

    @computed_field(return_type=bool)
    @property
    def has_docs(self) -> bool:
        return bool(self.docs_found_json)

    @computed_field(return_type=bool)
    @property
    def has_ci_config(self) -> bool:
        return bool(self.ci_config_json)

    @computed_field(return_type=bool)
    @property
    def has_deployment_config(self) -> bool:
        return bool(self.deployment_config_json)

    @computed_field(return_type=bool)
    @property
    def has_risky_files(self) -> bool:
        return bool(self.risky_files_json)

    model_config = ConfigDict(from_attributes=True)


class ImportFolderRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    folder_path: str = Field(min_length=1)
    import_mode: ImportMode = "linked"
    start_read_only_scan: bool = True


class ImportFolderResponse(BaseModel):
    project: ProjectRead
    scan_started: bool
    warnings: list[str] = Field(default_factory=list)
    recommended_next_route: str


class CodebaseMapRead(BaseModel):
    project_id: int
    source_path: str
    languages_json: list[str] = Field(default_factory=list)
    frameworks_json: list[str] = Field(default_factory=list)
    package_managers_json: list[str] = Field(default_factory=list)
    build_tools_json: list[str] = Field(default_factory=list)
    test_frameworks_json: list[str] = Field(default_factory=list)
    entry_points_json: list[str] = Field(default_factory=list)
    build_commands_json: list[str] = Field(default_factory=list)
    test_commands_json: list[str] = Field(default_factory=list)
    important_folders_json: list[str] = Field(default_factory=list)
    docs_json: list[str] = Field(default_factory=list)
    agent_instructions_json: list[dict[str, Any]] = Field(default_factory=list)
    config_files_json: list[str] = Field(default_factory=list)
    ci_config_json: list[str] = Field(default_factory=list)
    deployment_config_json: list[str] = Field(default_factory=list)
    git_status_json: dict[str, Any] = Field(default_factory=dict)
    risk_flags_json: list[str] = Field(default_factory=list)
    scan_depth: ScanDepth | str
    codebase_size: CodebaseSize | str
    recommended_scan_strategy: str
    indexed_areas_json: list[str] = Field(default_factory=list)
    unindexed_areas_json: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @computed_field(return_type=int)
    @property
    def language_count(self) -> int:
        return len(self.languages_json)

    @computed_field(return_type=int)
    @property
    def framework_count(self) -> int:
        return len(self.frameworks_json)

    @computed_field(return_type=int)
    @property
    def package_manager_count(self) -> int:
        return len(self.package_managers_json)

    @computed_field(return_type=int)
    @property
    def build_tool_count(self) -> int:
        return len(self.build_tools_json)

    @computed_field(return_type=int)
    @property
    def test_framework_count(self) -> int:
        return len(self.test_frameworks_json)

    @computed_field(return_type=int)
    @property
    def entry_point_count(self) -> int:
        return len(self.entry_points_json)

    @computed_field(return_type=int)
    @property
    def build_command_count(self) -> int:
        return len(self.build_commands_json)

    @computed_field(return_type=int)
    @property
    def test_command_count(self) -> int:
        return len(self.test_commands_json)

    @computed_field(return_type=int)
    @property
    def important_folder_count(self) -> int:
        return len(self.important_folders_json)

    @computed_field(return_type=int)
    @property
    def doc_count(self) -> int:
        return len(self.docs_json)

    @computed_field(return_type=int)
    @property
    def agent_instruction_count(self) -> int:
        return len(self.agent_instructions_json)

    @computed_field(return_type=int)
    @property
    def config_file_count(self) -> int:
        return len(self.config_files_json)

    @computed_field(return_type=int)
    @property
    def ci_config_count(self) -> int:
        return len(self.ci_config_json)

    @computed_field(return_type=int)
    @property
    def deployment_config_count(self) -> int:
        return len(self.deployment_config_json)

    @computed_field(return_type=int)
    @property
    def risk_flag_count(self) -> int:
        return len(self.risk_flags_json)

    @computed_field(return_type=int)
    @property
    def indexed_area_count(self) -> int:
        return len(self.indexed_areas_json)

    @computed_field(return_type=int)
    @property
    def unindexed_area_count(self) -> int:
        return len(self.unindexed_areas_json)

    @computed_field(return_type=bool)
    @property
    def has_docs(self) -> bool:
        return bool(self.docs_json)

    @computed_field(return_type=bool)
    @property
    def has_agent_instructions(self) -> bool:
        return bool(self.agent_instructions_json)

    @computed_field(return_type=bool)
    @property
    def has_risk_flags(self) -> bool:
        return bool(self.risk_flags_json)

    @computed_field(return_type=bool)
    @property
    def is_git_repo(self) -> bool:
        return bool(self.git_status_json.get("is_git_repo"))

    @computed_field(return_type=str)
    @property
    def dirty_working_tree_status(self) -> str:
        status = self.git_status_json.get("dirty_working_tree")
        if isinstance(status, str) and status.strip():
            return status
        return "not_git"

    @computed_field(return_type=bool)
    @property
    def dirty_working_tree_known(self) -> bool:
        return self.dirty_working_tree_status not in {"unknown_without_command", "unknown"}

    @computed_field(return_type=bool)
    @property
    def command_required_for_dirty_check(self) -> bool:
        return bool(self.git_status_json.get("command_required_for_dirty_check"))

    @computed_field(return_type=bool)
    @property
    def is_fully_indexed(self) -> bool:
        return not self.unindexed_areas_json

    @computed_field(return_type=bool)
    @property
    def is_targeted_scan(self) -> bool:
        return self.scan_depth == "targeted"

    model_config = ConfigDict(from_attributes=True)


class CodebaseUnderstandingRead(BaseModel):
    project_id: int
    summary: str
    architecture_summary: str
    detected_stack_json: list[str] = Field(default_factory=list)
    likely_run_instructions_json: list[str] = Field(default_factory=list)
    likely_test_instructions_json: list[str] = Field(default_factory=list)
    risk_summary: str
    missing_context_json: list[str] = Field(default_factory=list)
    suggested_next_steps_json: list[str] = Field(default_factory=list)
    recommended_interview_mode: InterviewChoice
    confidence_by_area_json: dict[str, float] = Field(default_factory=dict)
    generation_mode: str
    created_at: datetime
    updated_at: datetime

    @computed_field(return_type=int)
    @property
    def detected_stack_count(self) -> int:
        return len(self.detected_stack_json)

    @computed_field(return_type=int)
    @property
    def likely_run_instruction_count(self) -> int:
        return len(self.likely_run_instructions_json)

    @computed_field(return_type=int)
    @property
    def likely_test_instruction_count(self) -> int:
        return len(self.likely_test_instructions_json)

    @computed_field(return_type=int)
    @property
    def missing_context_count(self) -> int:
        return len(self.missing_context_json)

    @computed_field(return_type=int)
    @property
    def suggested_next_step_count(self) -> int:
        return len(self.suggested_next_steps_json)

    @computed_field(return_type=int)
    @property
    def confidence_area_count(self) -> int:
        return len(self.confidence_by_area_json)

    @computed_field(return_type=float)
    @property
    def average_confidence(self) -> float:
        if not self.confidence_by_area_json:
            return 0.0
        return round(sum(float(value) for value in self.confidence_by_area_json.values()) / len(self.confidence_by_area_json), 3)

    @computed_field(return_type=list[str])
    @property
    def lowest_confidence_areas(self) -> list[str]:
        return [
            str(area)
            for area, _score in sorted(
                self.confidence_by_area_json.items(),
                key=lambda item: (float(item[1]), str(item[0])),
            )[:3]
        ]

    @computed_field(return_type=list[str])
    @property
    def highest_confidence_areas(self) -> list[str]:
        return [
            str(area)
            for area, _score in sorted(
                self.confidence_by_area_json.items(),
                key=lambda item: (-float(item[1]), str(item[0])),
            )[:3]
        ]

    @computed_field(return_type=bool)
    @property
    def has_missing_context(self) -> bool:
        return bool(self.missing_context_json)

    @computed_field(return_type=bool)
    @property
    def has_suggested_next_steps(self) -> bool:
        return bool(self.suggested_next_steps_json)

    model_config = ConfigDict(from_attributes=True)


class AgentInstructionsStatusRead(BaseModel):
    project_id: int
    has_agents_md: bool
    agents_md_path: str | None = None
    summary: str
    recommended_action: Literal["none", "create", "update", "review"]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentsMdProposalRead(BaseModel):
    project_id: int
    recommended_path: str
    summary: str
    proposal_markdown: str


class ImportedCodebaseSafetyRead(BaseModel):
    project_id: int
    read_only_scan_completed: bool
    write_permission_status: WritePermissionStatus
    require_snapshot_before_edits: bool
    require_approval_for_dependency_changes: bool
    require_approval_for_test_commands: bool
    require_approval_for_build_commands: bool
    require_approval_for_formatting: bool
    require_approval_for_package_file_changes: bool
    destructive_commands_blocked: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImportedCodebaseSafetyUpdate(BaseModel):
    write_permission_status: WritePermissionStatus | None = None
    require_snapshot_before_edits: bool | None = None
    require_approval_for_dependency_changes: bool | None = None
    require_approval_for_test_commands: bool | None = None
    require_approval_for_build_commands: bool | None = None
    require_approval_for_formatting: bool | None = None
    require_approval_for_package_file_changes: bool | None = None
    destructive_commands_blocked: bool | None = None


class WritePermissionRequest(BaseModel):
    write_permission_status: WritePermissionStatus


class ImportInterviewChoiceRequest(BaseModel):
    choice: InterviewChoice


class ImportInterviewChoiceResponse(BaseModel):
    next_route: str
    questions: list[InterviewQuestionRead] = Field(default_factory=list)
    manager_note: str


class TargetedCodebaseScanRequest(BaseModel):
    target_paths: list[str] | None = None
    request_text: str | None = None
    scan_reason: str | None = None


class ImportedCodebaseRequest(BaseModel):
    message: str = Field(min_length=1)


class ImportedCodebaseRequestRead(BaseModel):
    project_id: int
    classification: Literal["analysis", "bugfix", "feature", "refactor", "docs", "test", "security", "performance", "migration", "cleanup", "unknown"]
    decision: Literal[
        "answer_directly",
        "ask_quick_question",
        "create_task_plan",
        "run_targeted_scan",
        "request_command_approval",
        "request_write_permission",
        "recommend_snapshot_first",
    ]
    manager_note: str
    suggested_questions: list[str] = Field(default_factory=list)
    targeted_scan_targets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ValidationRecipeRead(BaseModel):
    id: int
    project_id: int
    name: str
    steps_json: list[dict[str, Any]] = Field(default_factory=list)
    status: str
    last_run_at: datetime | None = None
    last_result: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HandoffQualityPreferenceRead(BaseModel):
    project_id: int
    quality_level: str
    include_run_commands: bool = True
    include_known_limitations: bool = True
    include_artifacts: bool = True
    include_tests: bool = True
    include_next_steps: bool = True

    model_config = ConfigDict(from_attributes=True)


class ChangeRequestCreate(BaseModel):
    request_text: str = Field(min_length=1)


class ChangeRequestRead(BaseModel):
    id: int
    project_id: int
    request_text: str
    classification: str
    impact_estimate: str
    status: str
    related_tasks_json: list[int] = Field(default_factory=list)
    related_handoff_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChangeRequestUpdate(BaseModel):
    classification: str | None = None
    impact_estimate: str | None = None
    status: str | None = None
    related_tasks_json: list[int] | None = None
    related_handoff_id: int | None = None


class ChangeRequestTriageRead(BaseModel):
    id: int
    classification: str
    impact_estimate: str
    status: str
    note: str


class ConflictRecordRead(BaseModel):
    id: int
    project_id: int
    conflict_type: ConflictType
    title: str
    summary: str
    involved_agent_ids_json: list[int] = Field(default_factory=list)
    involved_task_ids_json: list[int] = Field(default_factory=list)
    affected_paths_json: list[str] = Field(default_factory=list)
    severity: RiskLevel
    status: ConflictStatus
    suggested_resolution_json: list[str] = Field(default_factory=list)
    selected_resolution: ConflictResolution | str | None = None
    created_at: datetime
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ConflictResolveRequest(BaseModel):
    resolution: ConflictResolution | str


class HandoffEvidenceCreate(BaseModel):
    evidence_type: EvidenceType
    claim: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_path: str | None = None
    command: str | None = None
    status: EvidenceStatus = "unknown"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class HandoffEvidenceRead(BaseModel):
    id: int
    project_id: int
    handoff_id: int | None = None
    evidence_type: EvidenceType | str
    claim: str
    summary: str
    source_path: str | None = None
    command: str | None = None
    status: EvidenceStatus | str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class HandoffEvidencePreviewItemRead(BaseModel):
    project_id: int
    evidence_type: str
    claim: str
    summary: str
    source_path: str | None = None
    command: str | None = None
    status: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    derived_from_run_id: int | None = None


class HandoffEvidencePreviewSummaryRead(BaseModel):
    project_id: int
    persisted: list[HandoffEvidenceRead] = Field(default_factory=list)
    derived_candidates: list[HandoffEvidencePreviewItemRead] = Field(default_factory=list)
    stored_count: int = 0
    derived_candidate_count: int = 0
    generated_at: datetime


class EvidenceBasedHandoffRead(BaseModel):
    id: int
    project_id: int
    title: str
    summary: str
    what_was_built: str
    how_to_run: str
    how_to_use: str
    tests_run_json: list[dict[str, Any]] = Field(default_factory=list)
    known_limitations_json: list[str] = Field(default_factory=list)
    suggested_next_steps_json: list[str] = Field(default_factory=list)
    evidence_ids_json: list[int] = Field(default_factory=list)
    confidence_level: str
    dry_run: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunbookRead(BaseModel):
    id: int
    project_id: int
    content_markdown: str
    generated_from_handoff_id: int | None = None
    generated_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunbookUpdate(BaseModel):
    content_markdown: str = Field(min_length=1)


class AgentExecutionTraceRead(BaseModel):
    id: int
    project_id: int
    agent_id: int | None = None
    task_id: int | None = None
    run_id: int | None = None
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    span_kind: TraceSpanKind | str
    attempt_number: int = 1
    outcome: str = "unknown"
    failure_classification: FailureClassification | None = None
    prompt_summary: str
    prompt_path: str | None = None
    response_summary: str
    report_json: dict[str, Any] = Field(default_factory=dict)
    files_changed_json: list[str] = Field(default_factory=list)
    approvals_requested_json: list[dict[str, Any]] = Field(default_factory=list)
    commands_attempted_json: list[str] = Field(default_factory=list)
    evidence_ids_json: list[int] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    manager_decision_after: str | None = None
    redaction_status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectSnapshotCreate(BaseModel):
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    created_before_task_id: int | None = None
    created_before_agent_id: int | None = None


class ProjectSnapshotRead(BaseModel):
    id: int
    project_id: int
    snapshot_type: SnapshotType | str
    label: str
    description: str
    git_ref: str | None = None
    created_before_task_id: int | None = None
    created_before_agent_id: int | None = None
    status: SnapshotStatus | str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class SnapshotRestorePlanRead(BaseModel):
    snapshot_id: int
    project_id: int
    status: SnapshotStatus | str
    summary: str
    steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RecoveryPlanCreate(BaseModel):
    trigger_type: str = Field(min_length=1)
    trigger_summary: str = Field(min_length=1)
    related_agent_id: int | None = None
    related_task_id: int | None = None
    suggested_actions_json: list[str] = Field(default_factory=list)


class RecoveryPlanSelectRequest(BaseModel):
    action: str = Field(min_length=1)


class AgentLoadSnapshotRead(BaseModel):
    id: int
    project_id: int
    agent_id: int
    active_task_count: int
    waiting_task_count: int
    blocked_task_count: int
    idle_duration_seconds: int | None = None
    load_level: AgentLoadLevel | str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentLoadRebalanceRead(BaseModel):
    overloaded_agents: list[dict[str, Any]] = Field(default_factory=list)
    idle_agents: list[dict[str, Any]] = Field(default_factory=list)
    suggested_reassignments: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class ReviewGateCreate(BaseModel):
    gate_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    required: bool = True
    related_task_id: int | None = None
    related_agent_id: int | None = None
    required_checks_json: list[str] = Field(default_factory=list)
    evidence_ids_json: list[int] = Field(default_factory=list)
    result_summary: str | None = None
    status: str = "pending"


class ReviewGateUpdate(BaseModel):
    status: str | None = None
    required: bool | None = None
    related_task_id: int | None = None
    related_agent_id: int | None = None
    required_checks_json: list[str] | None = None
    evidence_ids_json: list[int] | None = None
    result_summary: str | None = None


class ProjectHealthRead(BaseModel):
    state: ProjectHealthState | str
    score: int
    reasons: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    next_action: str


class ProjectTimelineEventCreate(BaseModel):
    event_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    related_agent_id: int | None = None
    related_task_id: int | None = None
    related_handoff_id: int | None = None
    severity: ProjectActionSeverity = "info"


class ProjectTimelineEventRead(BaseModel):
    id: int
    project_id: int
    event_type: str
    title: str
    summary: str
    related_agent_id: int | None = None
    related_task_id: int | None = None
    related_handoff_id: int | None = None
    severity: ProjectActionSeverity | str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CapabilityBenchmarkCreate(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    runner_mode: RunnerMode = "auto"
    category: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    sample_size: int = Field(default=1, ge=0)
    notes: str | None = None
    last_run_at: datetime | None = None

    @field_validator("category")
    @classmethod
    def validate_capability_category(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in CAPABILITY_CATEGORIES:
            allowed = ", ".join(CAPABILITY_CATEGORIES)
            raise ValueError(f"Category must be one of: {allowed}")
        return normalized


class CapabilityBenchmarkRead(BaseModel):
    id: int
    provider: str
    model: str
    runner_mode: RunnerMode | str
    category: str
    score: int
    sample_size: int
    notes: str | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CapabilityMatrixEntryRead(BaseModel):
    provider: str
    model: str
    runner_mode: RunnerMode | str
    scores: dict[str, int | None] = Field(default_factory=dict)
    sample_size: int = 0
    notes: list[str] = Field(default_factory=list)
    recommendation_note: str


class AgentPerformanceRecordCreate(BaseModel):
    project_id: int | None = None
    agent_archetype: str = Field(min_length=1)
    agent_name: str | None = None
    provider: str | None = None
    model: str | None = None
    runner_mode: RunnerMode = "auto"
    task_category: str = Field(min_length=1)
    task_id: int | None = None
    outcome: str = "unknown"
    duration_seconds: int | None = Field(default=None, ge=0)
    review_passed: bool | None = None
    tests_passed: bool | None = None
    failure_summary: str | None = None


class AgentPerformanceRecordRead(BaseModel):
    id: int
    project_id: int | None = None
    agent_archetype: str
    agent_name: str | None = None
    provider: str | None = None
    model: str | None = None
    runner_mode: RunnerMode | str
    task_category: str
    task_id: int | None = None
    outcome: str
    duration_seconds: int | None = None
    review_passed: bool | None = None
    tests_passed: bool | None = None
    failure_summary: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentReputationSummaryRead(BaseModel):
    archetype: str
    provider: str | None = None
    model: str | None = None
    total_tasks: int
    success_rate: float
    common_failure_modes: list[str] = Field(default_factory=list)
    recommended_for: list[str] = Field(default_factory=list)
    avoid_for: list[str] = Field(default_factory=list)
    confidence: int = 0


class ProjectPlaybookRead(BaseModel):
    id: int
    key: str
    name: str
    description: str
    suggested_interview_categories_json: list[str] = Field(default_factory=list)
    suggested_swarm_mode: str | None = None
    suggested_agent_archetypes_json: list[str] = Field(default_factory=list)
    suggested_validation_recipe_json: list[dict[str, Any]] = Field(default_factory=list)
    common_risks_json: list[str] = Field(default_factory=list)
    suggested_docs_json: list[str] = Field(default_factory=list)
    typical_structure_json: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectPlaybookSuggestionRead(BaseModel):
    project_id: int
    playbook_key: str | None = None
    status: str
    why: str
    playbook: ProjectPlaybookRead | None = None


class ProjectPlaybookRecommendationRead(BaseModel):
    playbook_key: str
    score: int
    why: str
    is_current: bool = False
    status: str | None = None
    playbook: ProjectPlaybookRead


class ProjectPlaybookApplyRequest(BaseModel):
    playbook_key: str = Field(min_length=1)


class ContextPackBuildRequest(BaseModel):
    agent_id: int | None = None
    task_id: int | None = None
    title: str | None = None
    goal: str | None = None
    token_budget_hint: int | None = Field(default=None, ge=0)


class ContextPackSectionRead(BaseModel):
    id: int
    context_pack_id: int
    section_type: str
    title: str
    content_markdown: str
    source_refs_json: list[str] = Field(default_factory=list)
    source_ref_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContextPackRead(BaseModel):
    id: int
    project_id: int
    agent_id: int | None = None
    task_id: int | None = None
    title: str
    goal: str
    included_docs_json: list[str] = Field(default_factory=list)
    included_doc_count: int = 0
    included_files_json: list[str] = Field(default_factory=list)
    included_file_count: int = 0
    excluded_files_json: list[str] = Field(default_factory=list)
    excluded_file_count: int = 0
    known_decisions_json: list[str] = Field(default_factory=list)
    known_decision_count: int = 0
    relevant_assumptions_json: list[str] = Field(default_factory=list)
    relevant_assumption_count: int = 0
    validation_steps_json: list[str] = Field(default_factory=list)
    validation_step_count: int = 0
    token_budget_hint: int | None = None
    warnings_json: list[str] = Field(default_factory=list)
    warning_count: int = 0
    section_count: int = 0
    section_types: list[str] = Field(default_factory=list)
    section_type_counts: dict[str, int] = Field(default_factory=dict)
    section_type_group_count: int = 0
    section_titles: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    source_ref_count: int = 0
    sections: list[ContextPackSectionRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RiskRecordCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: RiskLevel = "medium"
    likelihood: Literal["low", "medium", "high"] = "medium"
    owner_agent_id: int | None = None
    mitigation: str | None = None
    status: Literal["open", "monitoring", "mitigated", "accepted", "closed"] = "open"
    related_task_id: int | None = None
    created_by: Literal["manager", "user", "agent", "system"] = "manager"


class RiskRecordUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    severity: RiskLevel | None = None
    likelihood: Literal["low", "medium", "high"] | None = None
    owner_agent_id: int | None = None
    mitigation: str | None = None
    status: Literal["open", "monitoring", "mitigated", "accepted", "closed"] | None = None
    related_task_id: int | None = None


class RiskRecordRead(BaseModel):
    id: int
    project_id: int
    title: str
    description: str
    severity: RiskLevel
    likelihood: Literal["low", "medium", "high"]
    owner_agent_id: int | None = None
    mitigation: str | None = None
    status: Literal["open", "monitoring", "mitigated", "accepted", "closed"]
    related_task_id: int | None = None
    created_by: Literal["manager", "user", "agent", "system"]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScopeChangeAnalyzeRequest(BaseModel):
    source: str = "manager"
    summary: str | None = None
    related_task_id: int | None = None
    related_message_id: int | None = None


class ScopeChangeResolveRequest(BaseModel):
    status: Literal["accepted", "deferred", "dismissed"]


class ScopeChangeSignalRead(BaseModel):
    id: int
    project_id: int
    source: str
    summary: str
    severity: Literal["low", "medium", "high"]
    related_task_id: int | None = None
    related_message_id: int | None = None
    suggested_action: Literal["include_now", "defer", "create_future_milestone", "ask_user"]
    status: Literal["open", "accepted", "deferred", "dismissed"]
    created_at: datetime
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SwarmLaunchSimulationRead(BaseModel):
    id: int
    project_id: int
    swarm_plan_id: int | None = None
    safe_to_launch_count: int
    should_wait_count: int
    needs_user_approval_count: int
    conflict_warnings_json: list[str] = Field(default_factory=list)
    bottlenecks_json: list[str] = Field(default_factory=list)
    recommended_launch_order_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CommonRiskRead(BaseModel):
    title: str
    detail: str
    project_id: int
    status: Literal["open", "monitoring", "mitigated", "accepted", "closed"]


class RiskSummaryRead(BaseModel):
    project_id: int | None = None
    total_count: int
    open_count: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    severity_counts: dict[str, int] = Field(default_factory=dict)
    top_risks: list[CommonRiskRead] = Field(default_factory=list)


class SwarmLaunchSimulationSnapshotRead(BaseModel):
    simulation_id: int | None = None
    project_id: int
    swarm_plan_id: int | None = None
    safe_to_launch_count: int
    should_wait_count: int
    needs_user_approval_count: int
    conflict_warnings_json: list[str] = Field(default_factory=list)
    bottlenecks_json: list[str] = Field(default_factory=list)
    recommended_launch_order_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    persisted: bool
    stale: bool = False


class ValidationCoverageAreaRead(BaseModel):
    id: int
    project_id: int
    area: str
    coverage_status: Literal["none", "planned", "partial", "validated", "failed", "skipped"]
    evidence_summary: str | None = None
    related_validation_step_id: int | None = None
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


class ValidationCoverageSummaryRead(BaseModel):
    project_id: int
    items: list[ValidationCoverageAreaRead] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    gap_count: int = 0


class UserPreferenceUpsert(BaseModel):
    value_json: Any
    source: Literal["setup", "user", "manager_observed", "imported"] = "user"
    editable: bool = True


class UserPreferenceRead(BaseModel):
    id: int
    key: str
    value_json: Any
    source: Literal["setup", "user", "manager_observed", "imported"]
    scope: Literal["global", "project"]
    project_id: int | None = None
    editable: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EffectiveUserPreferenceRead(BaseModel):
    id: int
    key: str
    value_json: Any
    source: Literal["setup", "user", "manager_observed", "imported"]
    scope: Literal["global", "project"]
    project_id: int | None = None
    editable: bool
    created_at: datetime
    updated_at: datetime
    inherited: bool = False

    model_config = ConfigDict(from_attributes=True)


class PreferenceSummaryRead(BaseModel):
    scope: Literal["global", "project"]
    project_id: int | None = None
    items: list[EffectiveUserPreferenceRead] = Field(default_factory=list)
    item_count: int = 0
    editable_count: int = 0
    inherited_count: int = 0
    project_override_count: int = 0


class ProjectWorkflowStepRead(BaseModel):
    id: str
    label: str
    state: Literal["complete", "current", "upcoming"]
    ordinal: int


class ProjectWorkflowRead(BaseModel):
    current_phase: str
    current_label: str
    steps: list[ProjectWorkflowStepRead] = Field(default_factory=list)


class ProjectOverviewChecklistItemRead(BaseModel):
    id: str
    label: str
    status: Literal["complete", "in_progress", "blocked", "planned"]
    detail: str


class ProjectOverviewRead(BaseModel):
    handoff_progress: int
    readiness_label: str
    readiness_tone: Literal["good", "warning", "danger", "neutral"]
    checklist: list[ProjectOverviewChecklistItemRead] = Field(default_factory=list)


class ActivityLogEntryRead(BaseModel):
    id: int
    event_type: str
    created_at: datetime
    summary: str
    detail: str | None = None
    severity: ProjectActionSeverity = "info"
    agent_id: int | None = None
    agent_name: str | None = None
    task_id: int | None = None


class ProjectWorkspaceRead(BaseModel):
    project: ProjectRead
    current_action: ProjectActionRead
    action_history: list[ProjectActionRead] = Field(default_factory=list)
    manager_messages: list[ManagerMessageRead] = Field(default_factory=list)
    pending_question: ManagerQuestionRead | None = None
    pending_approvals: list[ApprovalRequestRead] = Field(default_factory=list)
    agents: list[AgentRead] = Field(default_factory=list)
    manager_queue: ManagerQueueRead
    widgets: list[str] = Field(default_factory=list)
    available_widgets: list[str] = Field(default_factory=list)
    widget_instances: list[WidgetInstanceRead] = Field(default_factory=list)
    widget_data: list[WidgetDataResponseRead] = Field(default_factory=list)
    widget_catalog: list[WidgetDefinitionRead] = Field(default_factory=list)
    reservations: list[ReservationRead] = Field(default_factory=list)
    task_summary: dict[str, Any] = Field(default_factory=dict)
    milestone_summary: dict[str, Any] = Field(default_factory=dict)
    workflow: ProjectWorkflowRead
    overview: ProjectOverviewRead
    tasks: list[TaskRead] = Field(default_factory=list)
    activity_log: list[ActivityLogEntryRead] = Field(default_factory=list)
    degraded_notices: list[str] = Field(default_factory=list)
    swarm_preferences: SwarmPreferencesRead
    swarm_plan: SwarmPlanRead | None = None
    swarm_events: list[SwarmEventRead] = Field(default_factory=list)


class AppProfileRead(BaseModel):
    id: int = 1
    install_id: str | None = None
    display_name: str | None = None
    preferred_provider_choice: StartupProviderChoice = "codex"
    preferred_start_mode: StartupStartMode = "new_project"
    selected_provider: ProviderId = "codex"
    auth_mode: str | None = None
    connected_accounts_json: dict[str, Any] = Field(default_factory=dict)
    integration_registry_json: dict[str, Any] = Field(default_factory=dict)
    first_run_completed: bool = False
    setup_version_completed: str | None = None
    onboarding_completed: bool = False
    default_runner_mode: RunnerMode = "auto"
    manager_model: str | None = None
    default_worker_model: str | None = None
    manager_reasoning_effort: ReasoningEffort | None = None
    default_worker_reasoning_effort: ReasoningEffort | None = None
    sandbox_mode: SandboxMode = "workspace-write"
    approval_policy: ApprovalPolicy = "on-request"
    theme: ThemeMode = "system"
    startup_behavior: StartupBehavior = "dashboard"
    notification_preferences_json: dict[str, Any] = Field(default_factory=dict)
    dashboard_widgets_json: list[str] = Field(default_factory=list)
    dashboard_widget_preferences_json: dict[str, Any] = Field(default_factory=dict)
    tool_permission_overrides_json: dict[str, Any] = Field(default_factory=dict)
    provider_endpoint: str | None = None
    adapter_command: str | None = None
    adapter_args_json: list[str] = Field(default_factory=list)
    recent_startup_error_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    last_opened_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AppProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    preferred_provider_choice: StartupProviderChoice | None = None
    preferred_start_mode: StartupStartMode | None = None
    onboarding_completed: bool | None = None
    theme: ThemeMode | None = None
    startup_behavior: StartupBehavior | None = None
    notification_preferences_json: dict[str, Any] | None = None
    dashboard_widgets_json: list[str] | None = None
    dashboard_widget_preferences_json: dict[str, Any] | None = None


class AppProfileSummaryRead(BaseModel):
    id: int = 1
    exists: bool = False
    display_name: str
    selected_provider: ProviderId = "codex"
    first_run_completed: bool = False
    onboarding_completed: bool = False
    startup_behavior: StartupBehavior = "dashboard"
    default_runner_mode: RunnerMode = "auto"
    sandbox_mode: SandboxMode = "workspace-write"
    approval_policy: ApprovalPolicy = "on-request"
    connected_account_count: int = 0
    dashboard_widget_count: int = 0
    enabled_notification_count: int = 0
    has_provider_endpoint: bool = False
    has_adapter: bool = False
    updated_at: datetime
    last_opened_at: datetime | None = None


class StartupCheckRead(BaseModel):
    name: str
    required: bool
    status: StartupCheckStatus
    summary: str
    error_code: str | None = None
    family: str | None = None
    severity: ErrorSeverity | None = None
    breakpoint: str | None = None
    retryable: bool | None = None
    user_action_required: bool | None = None
    recommended_fix: str | None = None
    correlation_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class StartupStatusRead(BaseModel):
    mode: StartupMode
    first_run_completed: bool
    onboarding_complete: bool = False
    setup_version_completed: str | None = None
    current_setup_version: str
    install_id: str
    startup_attempt: int
    max_startup_attempts: int
    overall_status: StartupOverallStatus
    backend_ready: bool = False
    checks: list[StartupCheckRead] = Field(default_factory=list)
    recommended_route: str
    error_code: str | None = None
    error_summary: str | None = None
    diagnostic_report_path: str | None = None
    degraded_reasons: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    status_source: Literal["fresh", "cached"] = "fresh"
    startup_started_at: datetime
    last_completed_at: datetime | None = None
    checked_at: datetime | None = None


class StartupCheckRequest(BaseModel):
    attempt_number: int = Field(ge=1, default=1)
    include_optional_checks: bool = True


class StartupRetryRequest(BaseModel):
    attempt_number: int = Field(ge=1, default=1)
    failed_check: str | None = None
    retry_mode: StartupRetryMode = "targeted"


class CompleteFirstRunRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    provider: ProviderId = "codex"
    auth_mode: str | None = None
    connected_accounts_summary: dict[str, Any] | None = None
    default_runner_mode: RunnerMode | None = None
    manager_model: str | None = None
    default_worker_model: str | None = None
    manager_reasoning_effort: ReasoningEffort | None = None
    default_worker_reasoning_effort: ReasoningEffort | None = None
    sandbox_mode: SandboxMode | None = None
    approval_policy: ApprovalPolicy | None = None
    provider_endpoint: str | None = None
    adapter_command: str | None = None
    adapter_args: list[str] = Field(default_factory=list)
    start_mode: StartupStartMode | None = None


class DiagnosticReportRead(BaseModel):
    path: str
    json_path: str | None = None
    bundle_path: str | None = None
    summary: str
    error_code: str | None = None
    recommended_fixes: list[str] = Field(default_factory=list)
    project_id: int | None = None
    project_name: str | None = None
    workspace_path: str | None = None
    platform_profile: dict[str, Any] = Field(default_factory=dict)
    performance_profile: dict[str, Any] = Field(default_factory=dict)
    safe_debug_commands: list[str] = Field(default_factory=list)
    problem: ProblemDetailsRead | None = None


class AppStateRead(AppProfileRead):
    pass


class OpenPathResponse(BaseModel):
    ok: bool
    path: str
    message: str


class DashboardSummaryRead(BaseModel):
    sidebar_projects: list[ProjectRead] = Field(default_factory=list)
    recent_projects: list[ProjectRead] = Field(default_factory=list)
    archive_count: int = 0
    active_builds: list[dict[str, Any]] = Field(default_factory=list)
    attention_items: list[dict[str, Any]] = Field(default_factory=list)
    blocked_agents: list[AgentRead] = Field(default_factory=list)
    recent_handoffs: list[dict[str, Any]] = Field(default_factory=list)
    runner_status: dict[str, Any] = Field(default_factory=dict)
    connected_accounts: dict[str, Any] = Field(default_factory=dict)
    model_defaults: dict[str, Any] = Field(default_factory=dict)
    widgets: list[str] = Field(default_factory=list)
    available_widgets: list[str] = Field(default_factory=list)
    widget_instances: list[WidgetInstanceRead] = Field(default_factory=list)
    widget_data: list[WidgetDataResponseRead] = Field(default_factory=list)
    widget_catalog: list[WidgetDefinitionRead] = Field(default_factory=list)


class ProjectActionResolveRequest(BaseModel):
    decision: Literal["approve_once", "deny", "allow_for_project", "choose_option", "dismiss"]
    option_id: str | None = None
    selected_text: str | None = None


class HandoffListItemRead(BaseModel):
    project_id: int
    project_name: str
    project_slug: str | None = None
    created_at: datetime
    status: str
    summary: str
    artifacts_path: str | None = None
    has_artifacts_path: bool = False
    tests_count: int = 0
    run_instructions: list[str] = Field(default_factory=list)
    run_instruction_count: int = 0
    known_limitations: list[str] = Field(default_factory=list)
    known_limitation_count: int = 0
    confidence_level: str | None = None
    evidence_status: str | None = None
    evidence_backed: bool = False
    missing_evidence: list[str] = Field(default_factory=list)
    missing_evidence_count: int = 0
    ready_for_release: bool = False
    dry_run: bool = False


class OrchestrationHandoffRead(BaseModel):
    ready: bool = False
    status: str
    message: str
    handoff: HandoffListItemRead | None = None


class DiagnosticReportListItemRead(BaseModel):
    path: str
    json_path: str | None = None
    bundle_path: str | None = None
    created_at: datetime
    error_code: str | None = None
    summary: str
    project_id: int | None = None
    project_name: str | None = None
    workspace_path: str | None = None
    platform_profile: dict[str, Any] = Field(default_factory=dict)
    performance_profile: dict[str, Any] = Field(default_factory=dict)
    safe_debug_commands: list[str] = Field(default_factory=list)


ToolAvailability = Literal["available", "needs_setup", "experimental", "unsupported_on_device", "coming_soon"]
ToolPermissionPolicy = Literal["ask_every_time", "ask_once_per_project", "allow_for_project", "never_allow"]
IntegrationProviderResolutionState = Literal["resolved", "suppressed_cli_only", "unresolved"]
IntegrationActionSupportMode = Literal["registry_state", "provider_specific", "family_default", "guided_only", "unsupported"]
IntegrationProviderContextStatus = Literal["verified", "inferred", "missing"]
IntegrationVerificationScope = Literal["guided_remote_mutation", "local_cli_mutation"]


class ToolCatalogItemRead(BaseModel):
    id: str
    name: str
    category: str
    summary: str
    availability: ToolAvailability
    permission_policy: ToolPermissionPolicy
    risk_level: RiskLevel
    notes: list[str] = Field(default_factory=list)


class IntegrationActionRead(BaseModel):
    action_id: str
    title: str
    summary: str
    risk_level: RiskLevel = "medium"
    permission_policy: ToolPermissionPolicy = "ask_every_time"
    preview_supported: bool = True
    mutates_remote_state: bool = False
    requires_confirmation: bool = False
    required_params: list[str] = Field(default_factory=list)
    missing_params: list[str] = Field(default_factory=list)
    defaulted_params: dict[str, Any] = Field(default_factory=dict)
    params_complete: bool = True
    status: ToolAvailability = "available"
    provider: str | None = None
    provider_candidates: list[str] = Field(default_factory=list)
    provider_signal_breakdown: dict[str, Any] = Field(default_factory=dict)
    resolved_provider_evidence: dict[str, Any] = Field(default_factory=dict)
    cli_only_candidates_suppressed: list[str] = Field(default_factory=list)
    provider_resolution_state: IntegrationProviderResolutionState = "unresolved"
    command: str | None = None
    command_template: str | None = None
    command_ready: bool = False
    execution_mode: str = "unavailable"
    provider_support_mode: IntegrationActionSupportMode = "unsupported"
    supported_providers: list[str] = Field(default_factory=list)
    supported_provider_count: int = 0
    provider_lane_resolved: bool = False
    provider_context_verified: bool = False
    provider_context_source: str = "none"
    provider_context_status: IntegrationProviderContextStatus = "missing"
    context_available: bool = False
    provider_verification_required: bool = False
    provider_verification_reason: str | None = None
    verification_scope: IntegrationVerificationScope | None = None
    executable_name: str | None = None
    execution_block_reason: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    blocking_reason_count: int = 0
    preflight_ready: bool = False
    confirmation_eligible: bool = False
    ready_to_execute: bool = False
    safe_command_eligible: bool = False
    safe_command_reason: str | None = None
    context_required: bool = False
    context_requirement_reason: str | None = None
    suppressed_command_reason: str | None = None
    provider_guidance: str | None = None
    notes: list[str] = Field(default_factory=list)


class IntegrationCatalogEntryRead(BaseModel):
    family: str
    name: str
    summary: str
    category: str
    providers: list[str] = Field(default_factory=list)
    host_support: list[str] = Field(default_factory=list)
    available_action_ids: list[str] = Field(default_factory=list)
    status: str = "disconnected"
    connection_source: str = "mission_control"
    host_imported: bool = False
    notes: list[str] = Field(default_factory=list)


class IntegrationConnectionRead(BaseModel):
    family: str
    status: str = "disconnected"
    providers: list[str] = Field(default_factory=list)
    connection_source: str = "mission_control"
    host_imported: bool = False
    approval_policy: str = "ask_every_time"
    notes: list[str] = Field(default_factory=list)


class IntegrationHealthRead(BaseModel):
    version: int
    family_count: int
    connection_count: int
    authoritative_connection_count: int
    host_imported_count: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    recent_action_failures: list[dict[str, Any]] = Field(default_factory=list)
    host_import_roots: dict[str, list[str]] = Field(default_factory=dict)


class ProjectIntegrationFamilyRead(BaseModel):
    family: str
    name: str
    summary: str
    category: str
    project_name: str
    workspace_path: str | None = None
    status: str
    connection_status: str = "disconnected"
    connection_source: str = "mission_control"
    host_imported: bool = False
    providers: list[str] = Field(default_factory=list)
    provider_count: int = 0
    resolved_provider: str | None = None
    provider_candidates: list[str] = Field(default_factory=list)
    provider_candidate_count: int = 0
    resolved_cli_candidates: list[str] = Field(default_factory=list)
    resolved_cli_candidate_count: int = 0
    provider_signal_breakdown: dict[str, Any] = Field(default_factory=dict)
    resolved_provider_evidence: dict[str, Any] = Field(default_factory=dict)
    cli_only_candidates_suppressed: list[str] = Field(default_factory=list)
    cli_only_candidates_suppressed_count: int = 0
    provider_resolution_state: IntegrationProviderResolutionState = "unresolved"
    provider_context_verified: bool = False
    provider_context_source: str = "none"
    provider_context_status: IntegrationProviderContextStatus = "missing"
    workspace_signal_detected: bool = False
    host_import_detected: bool = False
    connection_detected: bool = False
    standalone_cli_detected: bool = False
    signal_sources: list[str] = Field(default_factory=list)
    signal_source_count: int = 0
    cli_detected: list[str] = Field(default_factory=list)
    cli_detected_count: int = 0
    resolved_cli_detected: list[str] = Field(default_factory=list)
    resolved_cli_detected_count: int = 0
    workspace_config_files: list[str] = Field(default_factory=list)
    workspace_config_file_count: int = 0
    workspace_token_hits: list[str] = Field(default_factory=list)
    workspace_token_hit_count: int = 0
    connection_provider_count: int = 0
    connection_without_provider_identity: bool = False
    git_remote_url: str | None = None
    required_permissions: list[str] = Field(default_factory=list)
    required_permission_count: int = 0
    permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    available_permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    blocked_permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    permission_policy_group_count: int = 0
    available_permission_policy_group_count: int = 0
    blocked_permission_policy_group_count: int = 0
    permission_policy_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_permission_policy_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_permission_policy_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    risk_level_counts: dict[str, int] = Field(default_factory=dict)
    available_risk_level_counts: dict[str, int] = Field(default_factory=dict)
    blocked_risk_level_counts: dict[str, int] = Field(default_factory=dict)
    risk_level_group_count: int = 0
    available_risk_level_group_count: int = 0
    blocked_risk_level_group_count: int = 0
    risk_level_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_risk_level_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_risk_level_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    action_status_counts: dict[str, int] = Field(default_factory=dict)
    action_status_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    action_status_group_count: int = 0
    available_action_status_counts: dict[str, int] = Field(default_factory=dict)
    available_action_status_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_action_status_group_count: int = 0
    blocked_action_status_counts: dict[str, int] = Field(default_factory=dict)
    blocked_action_status_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_action_status_group_count: int = 0
    execution_mode_counts: dict[str, int] = Field(default_factory=dict)
    execution_mode_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    execution_mode_group_count: int = 0
    provider_support_mode_counts: dict[str, int] = Field(default_factory=dict)
    provider_support_mode_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    provider_support_mode_group_count: int = 0
    available_provider_support_mode_counts: dict[str, int] = Field(default_factory=dict)
    available_provider_support_mode_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_provider_support_mode_group_count: int = 0
    blocked_provider_support_mode_counts: dict[str, int] = Field(default_factory=dict)
    blocked_provider_support_mode_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_provider_support_mode_group_count: int = 0
    provider_context_status_counts: dict[str, int] = Field(default_factory=dict)
    provider_context_status_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    provider_context_status_group_count: int = 0
    verification_scope_counts: dict[str, int] = Field(default_factory=dict)
    verification_scope_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    verification_scope_group_count: int = 0
    available_verification_scope_counts: dict[str, int] = Field(default_factory=dict)
    available_verification_scope_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_verification_scope_group_count: int = 0
    blocked_verification_scope_counts: dict[str, int] = Field(default_factory=dict)
    blocked_verification_scope_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_verification_scope_group_count: int = 0
    safe_command_reason_counts: dict[str, int] = Field(default_factory=dict)
    safe_command_reason_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    safe_command_reason_group_count: int = 0
    available_safe_command_reason_counts: dict[str, int] = Field(default_factory=dict)
    available_safe_command_reason_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_safe_command_reason_group_count: int = 0
    blocked_safe_command_reason_counts: dict[str, int] = Field(default_factory=dict)
    blocked_safe_command_reason_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_safe_command_reason_group_count: int = 0
    context_requirement_reason_counts: dict[str, int] = Field(default_factory=dict)
    context_requirement_reason_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    context_requirement_reason_group_count: int = 0
    available_context_requirement_reason_counts: dict[str, int] = Field(default_factory=dict)
    available_context_requirement_reason_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_context_requirement_reason_group_count: int = 0
    blocked_context_requirement_reason_counts: dict[str, int] = Field(default_factory=dict)
    blocked_context_requirement_reason_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_context_requirement_reason_group_count: int = 0
    action_provider_counts: dict[str, int] = Field(default_factory=dict)
    action_provider_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    action_provider_group_count: int = 0
    available_action_provider_counts: dict[str, int] = Field(default_factory=dict)
    available_action_provider_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_action_provider_group_count: int = 0
    blocked_action_provider_counts: dict[str, int] = Field(default_factory=dict)
    blocked_action_provider_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_action_provider_group_count: int = 0
    executable_name_counts: dict[str, int] = Field(default_factory=dict)
    executable_name_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    executable_name_group_count: int = 0
    available_executable_name_counts: dict[str, int] = Field(default_factory=dict)
    available_executable_name_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_executable_name_group_count: int = 0
    blocked_executable_name_counts: dict[str, int] = Field(default_factory=dict)
    blocked_executable_name_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_executable_name_group_count: int = 0
    available_execution_mode_counts: dict[str, int] = Field(default_factory=dict)
    available_execution_mode_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_execution_mode_group_count: int = 0
    blocked_execution_mode_counts: dict[str, int] = Field(default_factory=dict)
    blocked_execution_mode_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_execution_mode_group_count: int = 0
    available_provider_context_status_counts: dict[str, int] = Field(default_factory=dict)
    available_provider_context_status_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_provider_context_status_group_count: int = 0
    blocked_provider_context_status_counts: dict[str, int] = Field(default_factory=dict)
    blocked_provider_context_status_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_provider_context_status_group_count: int = 0
    action_count: int = 0
    available_action_count: int = 0
    blocked_action_count: int = 0
    available_execution_action_count: int = 0
    available_execution_action_ids: list[str] = Field(default_factory=list)
    execution_required_permissions: list[str] = Field(default_factory=list)
    execution_required_permission_count: int = 0
    execution_permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    execution_permission_policy_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    execution_permission_policy_group_count: int = 0
    available_execution_permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    available_execution_permission_policy_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_execution_permission_policy_group_count: int = 0
    blocked_execution_permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    blocked_execution_permission_policy_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_execution_permission_policy_group_count: int = 0
    execution_risk_level_counts: dict[str, int] = Field(default_factory=dict)
    execution_risk_level_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    execution_risk_level_group_count: int = 0
    available_execution_risk_level_counts: dict[str, int] = Field(default_factory=dict)
    available_execution_risk_level_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_execution_risk_level_group_count: int = 0
    blocked_execution_risk_level_counts: dict[str, int] = Field(default_factory=dict)
    blocked_execution_risk_level_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_execution_risk_level_group_count: int = 0
    local_action_count: int = 0
    available_action_ids: list[str] = Field(default_factory=list)
    blocked_action_ids: list[str] = Field(default_factory=list)
    local_action_ids: list[str] = Field(default_factory=list)
    guided_action_count: int = 0
    guided_action_ids: list[str] = Field(default_factory=list)
    registry_action_count: int = 0
    registry_action_ids: list[str] = Field(default_factory=list)
    provider_specific_action_count: int = 0
    provider_specific_action_ids: list[str] = Field(default_factory=list)
    guided_only_action_count: int = 0
    guided_only_action_ids: list[str] = Field(default_factory=list)
    available_provider_lane_count: int = 0
    available_provider_lane_action_ids: list[str] = Field(default_factory=list)
    available_mutating_action_count: int = 0
    available_mutating_action_ids: list[str] = Field(default_factory=list)
    available_non_mutating_action_count: int = 0
    available_non_mutating_action_ids: list[str] = Field(default_factory=list)
    context_blocked_action_count: int = 0
    context_blocked_action_ids: list[str] = Field(default_factory=list)
    verification_blocked_action_count: int = 0
    verification_blocked_action_ids: list[str] = Field(default_factory=list)
    verification_blocked_guided_action_count: int = 0
    verification_blocked_guided_action_ids: list[str] = Field(default_factory=list)
    verification_blocked_local_action_count: int = 0
    verification_blocked_local_action_ids: list[str] = Field(default_factory=list)
    execution_action_count: int = 0
    execution_action_ids: list[str] = Field(default_factory=list)
    mutating_execution_action_count: int = 0
    mutating_execution_action_ids: list[str] = Field(default_factory=list)
    non_mutating_execution_action_count: int = 0
    non_mutating_execution_action_ids: list[str] = Field(default_factory=list)
    confirmation_required_execution_action_count: int = 0
    confirmation_required_execution_action_ids: list[str] = Field(default_factory=list)
    preview_supported_execution_action_count: int = 0
    preview_supported_execution_action_ids: list[str] = Field(default_factory=list)
    context_available_execution_action_count: int = 0
    context_available_execution_action_ids: list[str] = Field(default_factory=list)
    provider_guidance_action_count: int = 0
    provider_guidance_action_ids: list[str] = Field(default_factory=list)
    local_execution_action_count: int = 0
    local_execution_action_ids: list[str] = Field(default_factory=list)
    guided_execution_action_count: int = 0
    guided_execution_action_ids: list[str] = Field(default_factory=list)
    provider_specific_execution_action_count: int = 0
    provider_specific_execution_action_ids: list[str] = Field(default_factory=list)
    guided_only_execution_action_count: int = 0
    guided_only_execution_action_ids: list[str] = Field(default_factory=list)
    commandful_execution_action_count: int = 0
    commandful_execution_action_ids: list[str] = Field(default_factory=list)
    blocked_execution_action_count: int = 0
    blocked_execution_action_ids: list[str] = Field(default_factory=list)
    blocked_local_execution_action_count: int = 0
    blocked_local_execution_action_ids: list[str] = Field(default_factory=list)
    blocked_guided_execution_action_count: int = 0
    blocked_guided_execution_action_ids: list[str] = Field(default_factory=list)
    blocked_provider_specific_execution_action_count: int = 0
    blocked_provider_specific_execution_action_ids: list[str] = Field(default_factory=list)
    blocked_guided_only_execution_action_count: int = 0
    blocked_guided_only_execution_action_ids: list[str] = Field(default_factory=list)
    multi_blocked_action_count: int = 0
    multi_blocked_action_ids: list[str] = Field(default_factory=list)
    preflight_ready_action_count: int = 0
    preflight_ready_action_ids: list[str] = Field(default_factory=list)
    not_preflight_ready_action_count: int = 0
    not_preflight_ready_action_ids: list[str] = Field(default_factory=list)
    confirmation_eligible_action_count: int = 0
    confirmation_eligible_action_ids: list[str] = Field(default_factory=list)
    not_confirmation_eligible_action_count: int = 0
    not_confirmation_eligible_action_ids: list[str] = Field(default_factory=list)
    ready_to_execute_action_count: int = 0
    ready_to_execute_action_ids: list[str] = Field(default_factory=list)
    not_ready_to_execute_action_count: int = 0
    not_ready_to_execute_action_ids: list[str] = Field(default_factory=list)
    safe_command_action_count: int = 0
    safe_command_action_ids: list[str] = Field(default_factory=list)
    unsafe_command_action_count: int = 0
    unsafe_command_action_ids: list[str] = Field(default_factory=list)
    command_ready_action_count: int = 0
    command_ready_action_ids: list[str] = Field(default_factory=list)
    command_not_ready_action_count: int = 0
    command_not_ready_action_ids: list[str] = Field(default_factory=list)
    parameterized_execution_action_count: int = 0
    parameterized_execution_action_ids: list[str] = Field(default_factory=list)
    non_parameterized_execution_action_count: int = 0
    non_parameterized_execution_action_ids: list[str] = Field(default_factory=list)
    params_complete_action_count: int = 0
    params_complete_action_ids: list[str] = Field(default_factory=list)
    params_incomplete_action_count: int = 0
    params_incomplete_action_ids: list[str] = Field(default_factory=list)
    defaulted_param_action_count: int = 0
    missing_params_action_count: int = 0
    missing_params_action_ids: list[str] = Field(default_factory=list)
    missing_executable_action_count: int = 0
    missing_executable_action_ids: list[str] = Field(default_factory=list)
    no_local_command_action_count: int = 0
    no_local_command_action_ids: list[str] = Field(default_factory=list)
    provider_context_blocked_action_count: int = 0
    provider_context_blocked_action_ids: list[str] = Field(default_factory=list)
    provider_context_verified_action_count: int = 0
    provider_context_verified_action_ids: list[str] = Field(default_factory=list)
    provider_context_inferred_action_count: int = 0
    provider_context_inferred_action_ids: list[str] = Field(default_factory=list)
    provider_context_missing_action_count: int = 0
    provider_context_missing_action_ids: list[str] = Field(default_factory=list)
    defaulted_param_action_ids: list[str] = Field(default_factory=list)
    commandless_execution_action_count: int = 0
    commandless_execution_action_ids: list[str] = Field(default_factory=list)
    execution_block_reason_counts: dict[str, int] = Field(default_factory=dict)
    execution_block_reason_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    execution_block_reason_group_count: int = 0
    blocking_reason_counts: dict[str, int] = Field(default_factory=dict)
    blocking_reason_action_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocking_reason_group_count: int = 0
    health: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    artifact_count: int = 0
    safe_commands: list[str] = Field(default_factory=list)
    safe_command_count: int = 0
    blockers: list[str] = Field(default_factory=list)
    blocker_count: int = 0
    recommended_fixes: list[str] = Field(default_factory=list)
    recommended_fix_count: int = 0
    available_actions: list[IntegrationActionRead] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    note_count: int = 0


class ProjectIntegrationsRead(BaseModel):
    project_id: int
    project_name: str
    workspace_path: str | None = None
    summary: str
    family_count: int = 0
    family_ids: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)
    status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    status_family_counts: dict[str, int] = Field(default_factory=dict)
    status_group_count: int = 0
    status_family_count: int = 0
    status_families: list[str] = Field(default_factory=list)
    connection_statuses: list[str] = Field(default_factory=list)
    connection_status_counts: dict[str, int] = Field(default_factory=dict)
    connection_status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    connection_status_family_counts: dict[str, int] = Field(default_factory=dict)
    connection_status_group_count: int = 0
    connection_status_family_count: int = 0
    connection_status_families: list[str] = Field(default_factory=list)
    connection_sources: list[str] = Field(default_factory=list)
    connection_source_counts: dict[str, int] = Field(default_factory=dict)
    connection_source_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    connection_source_family_counts: dict[str, int] = Field(default_factory=dict)
    connection_source_group_count: int = 0
    connection_source_family_count: int = 0
    connection_source_families: list[str] = Field(default_factory=list)
    resolved_providers: list[str] = Field(default_factory=list)
    resolved_provider_counts: dict[str, int] = Field(default_factory=dict)
    resolved_provider_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    resolved_provider_family_counts: dict[str, int] = Field(default_factory=dict)
    resolved_provider_group_count: int = 0
    resolved_provider_family_count: int = 0
    resolved_provider_families: list[str] = Field(default_factory=list)
    provider_resolution_states: list[str] = Field(default_factory=list)
    provider_resolution_state_counts: dict[str, int] = Field(default_factory=dict)
    provider_resolution_state_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    provider_resolution_state_family_counts: dict[str, int] = Field(default_factory=dict)
    provider_resolution_state_group_count: int = 0
    provider_resolution_state_family_count: int = 0
    provider_resolution_state_families: list[str] = Field(default_factory=list)
    provider_context_sources: list[str] = Field(default_factory=list)
    provider_context_source_counts: dict[str, int] = Field(default_factory=dict)
    provider_context_source_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    provider_context_source_family_counts: dict[str, int] = Field(default_factory=dict)
    provider_context_source_group_count: int = 0
    provider_context_source_family_count: int = 0
    provider_context_source_families: list[str] = Field(default_factory=list)
    provider_context_statuses: list[str] = Field(default_factory=list)
    provider_context_status_counts: dict[str, int] = Field(default_factory=dict)
    provider_context_status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    provider_context_status_family_counts: dict[str, int] = Field(default_factory=dict)
    provider_context_status_group_count: int = 0
    provider_context_status_family_count: int = 0
    provider_context_status_families: list[str] = Field(default_factory=list)
    signal_sources: list[str] = Field(default_factory=list)
    signal_source_counts: dict[str, int] = Field(default_factory=dict)
    signal_source_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    signal_source_family_counts: dict[str, int] = Field(default_factory=dict)
    signal_source_group_count: int = 0
    signal_source_family_count: int = 0
    signal_source_families: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    provider_counts: dict[str, int] = Field(default_factory=dict)
    provider_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    provider_family_counts: dict[str, int] = Field(default_factory=dict)
    provider_group_count: int = 0
    provider_family_count: int = 0
    provider_families: list[str] = Field(default_factory=list)
    provider_candidates: list[str] = Field(default_factory=list)
    provider_candidate_counts: dict[str, int] = Field(default_factory=dict)
    provider_candidate_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    provider_candidate_family_counts: dict[str, int] = Field(default_factory=dict)
    provider_candidate_group_count: int = 0
    provider_candidate_family_count: int = 0
    provider_candidate_families: list[str] = Field(default_factory=list)
    cli_detected: list[str] = Field(default_factory=list)
    cli_detected_counts: dict[str, int] = Field(default_factory=dict)
    cli_detected_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    cli_detected_family_counts: dict[str, int] = Field(default_factory=dict)
    cli_detected_group_count: int = 0
    cli_detected_family_count: int = 0
    cli_detected_families: list[str] = Field(default_factory=list)
    resolved_cli_detected: list[str] = Field(default_factory=list)
    resolved_cli_detected_counts: dict[str, int] = Field(default_factory=dict)
    resolved_cli_detected_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    resolved_cli_detected_family_counts: dict[str, int] = Field(default_factory=dict)
    resolved_cli_detected_group_count: int = 0
    resolved_cli_detected_family_count: int = 0
    resolved_cli_detected_families: list[str] = Field(default_factory=list)
    workspace_config_files: list[str] = Field(default_factory=list)
    workspace_config_file_counts: dict[str, int] = Field(default_factory=dict)
    workspace_config_file_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    workspace_config_file_family_counts: dict[str, int] = Field(default_factory=dict)
    workspace_config_file_group_count: int = 0
    workspace_config_file_family_count: int = 0
    workspace_config_file_families: list[str] = Field(default_factory=list)
    workspace_token_hits: list[str] = Field(default_factory=list)
    workspace_token_hit_counts: dict[str, int] = Field(default_factory=dict)
    workspace_token_hit_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    workspace_token_hit_family_counts: dict[str, int] = Field(default_factory=dict)
    workspace_token_hit_group_count: int = 0
    workspace_token_hit_family_count: int = 0
    workspace_token_hit_families: list[str] = Field(default_factory=list)
    ready_family_count: int = 0
    ready_family_ids: list[str] = Field(default_factory=list)
    partial_family_count: int = 0
    partial_family_ids: list[str] = Field(default_factory=list)
    needs_setup_family_count: int = 0
    needs_setup_family_ids: list[str] = Field(default_factory=list)
    connection_detected_family_count: int = 0
    connection_detected_family_ids: list[str] = Field(default_factory=list)
    workspace_signal_family_count: int = 0
    workspace_signal_family_ids: list[str] = Field(default_factory=list)
    host_import_family_count: int = 0
    host_import_family_ids: list[str] = Field(default_factory=list)
    standalone_cli_detected_family_count: int = 0
    standalone_cli_detected_family_ids: list[str] = Field(default_factory=list)
    connection_provider_count: int = 0
    connection_provider_family_count: int = 0
    connection_provider_family_ids: list[str] = Field(default_factory=list)
    connection_without_provider_identity_family_count: int = 0
    connection_without_provider_identity_family_ids: list[str] = Field(default_factory=list)
    provider_context_verified_family_count: int = 0
    provider_context_verified_family_ids: list[str] = Field(default_factory=list)
    available_action_family_count: int = 0
    available_action_family_ids: list[str] = Field(default_factory=list)
    available_action_count: int = 0
    available_action_refs: list[str] = Field(default_factory=list)
    local_action_count: int = 0
    local_action_refs: list[str] = Field(default_factory=list)
    local_action_family_count: int = 0
    local_action_family_ids: list[str] = Field(default_factory=list)
    guided_action_count: int = 0
    guided_action_refs: list[str] = Field(default_factory=list)
    guided_action_family_count: int = 0
    guided_action_family_ids: list[str] = Field(default_factory=list)
    registry_action_count: int = 0
    registry_action_refs: list[str] = Field(default_factory=list)
    registry_action_family_count: int = 0
    registry_action_family_ids: list[str] = Field(default_factory=list)
    provider_specific_action_count: int = 0
    provider_specific_action_refs: list[str] = Field(default_factory=list)
    provider_specific_action_family_count: int = 0
    provider_specific_action_family_ids: list[str] = Field(default_factory=list)
    guided_only_action_count: int = 0
    guided_only_action_refs: list[str] = Field(default_factory=list)
    guided_only_action_family_count: int = 0
    guided_only_action_family_ids: list[str] = Field(default_factory=list)
    available_mutating_action_count: int = 0
    available_mutating_action_refs: list[str] = Field(default_factory=list)
    available_mutating_action_family_count: int = 0
    available_mutating_action_family_ids: list[str] = Field(default_factory=list)
    available_non_mutating_action_count: int = 0
    available_non_mutating_action_refs: list[str] = Field(default_factory=list)
    available_non_mutating_action_family_count: int = 0
    available_non_mutating_action_family_ids: list[str] = Field(default_factory=list)
    blocked_action_family_count: int = 0
    blocked_action_family_ids: list[str] = Field(default_factory=list)
    blocked_action_count: int = 0
    blocked_action_refs: list[str] = Field(default_factory=list)
    execution_action_family_count: int = 0
    execution_action_family_ids: list[str] = Field(default_factory=list)
    execution_action_count: int = 0
    execution_action_refs: list[str] = Field(default_factory=list)
    available_execution_action_count: int = 0
    available_execution_action_refs: list[str] = Field(default_factory=list)
    available_execution_family_count: int = 0
    available_execution_family_ids: list[str] = Field(default_factory=list)
    local_execution_action_count: int = 0
    local_execution_action_refs: list[str] = Field(default_factory=list)
    local_execution_action_family_count: int = 0
    local_execution_action_family_ids: list[str] = Field(default_factory=list)
    guided_execution_action_count: int = 0
    guided_execution_action_refs: list[str] = Field(default_factory=list)
    guided_execution_action_family_count: int = 0
    guided_execution_action_family_ids: list[str] = Field(default_factory=list)
    provider_specific_execution_action_count: int = 0
    provider_specific_execution_action_refs: list[str] = Field(default_factory=list)
    provider_specific_execution_action_family_count: int = 0
    provider_specific_execution_action_family_ids: list[str] = Field(default_factory=list)
    guided_only_execution_action_count: int = 0
    guided_only_execution_action_refs: list[str] = Field(default_factory=list)
    guided_only_execution_action_family_count: int = 0
    guided_only_execution_action_family_ids: list[str] = Field(default_factory=list)
    mutating_execution_action_count: int = 0
    mutating_execution_action_refs: list[str] = Field(default_factory=list)
    mutating_execution_action_family_count: int = 0
    mutating_execution_action_family_ids: list[str] = Field(default_factory=list)
    non_mutating_execution_action_count: int = 0
    non_mutating_execution_action_refs: list[str] = Field(default_factory=list)
    non_mutating_execution_action_family_count: int = 0
    non_mutating_execution_action_family_ids: list[str] = Field(default_factory=list)
    confirmation_required_execution_action_count: int = 0
    confirmation_required_execution_action_refs: list[str] = Field(default_factory=list)
    confirmation_required_execution_action_family_count: int = 0
    confirmation_required_execution_action_family_ids: list[str] = Field(default_factory=list)
    preview_supported_execution_action_count: int = 0
    preview_supported_execution_action_refs: list[str] = Field(default_factory=list)
    preview_supported_execution_action_family_count: int = 0
    preview_supported_execution_action_family_ids: list[str] = Field(default_factory=list)
    context_available_execution_action_count: int = 0
    context_available_execution_action_refs: list[str] = Field(default_factory=list)
    context_available_execution_action_family_count: int = 0
    context_available_execution_action_family_ids: list[str] = Field(default_factory=list)
    provider_guidance_action_count: int = 0
    provider_guidance_action_refs: list[str] = Field(default_factory=list)
    provider_guidance_action_family_count: int = 0
    provider_guidance_action_family_ids: list[str] = Field(default_factory=list)
    commandful_execution_action_count: int = 0
    commandful_execution_action_refs: list[str] = Field(default_factory=list)
    commandful_execution_action_family_count: int = 0
    commandful_execution_action_family_ids: list[str] = Field(default_factory=list)
    blocked_execution_action_family_count: int = 0
    blocked_execution_action_family_ids: list[str] = Field(default_factory=list)
    blocked_execution_action_count: int = 0
    blocked_execution_action_refs: list[str] = Field(default_factory=list)
    blocked_local_execution_action_count: int = 0
    blocked_local_execution_action_refs: list[str] = Field(default_factory=list)
    blocked_local_execution_action_family_count: int = 0
    blocked_local_execution_action_family_ids: list[str] = Field(default_factory=list)
    blocked_guided_execution_action_count: int = 0
    blocked_guided_execution_action_refs: list[str] = Field(default_factory=list)
    blocked_guided_execution_action_family_count: int = 0
    blocked_guided_execution_action_family_ids: list[str] = Field(default_factory=list)
    blocked_provider_specific_execution_action_count: int = 0
    blocked_provider_specific_execution_action_refs: list[str] = Field(default_factory=list)
    blocked_provider_specific_execution_action_family_count: int = 0
    blocked_provider_specific_execution_action_family_ids: list[str] = Field(default_factory=list)
    blocked_guided_only_execution_action_count: int = 0
    blocked_guided_only_execution_action_refs: list[str] = Field(default_factory=list)
    blocked_guided_only_execution_action_family_count: int = 0
    blocked_guided_only_execution_action_family_ids: list[str] = Field(default_factory=list)
    safe_command_family_count: int = 0
    safe_command_family_ids: list[str] = Field(default_factory=list)
    safe_command_count: int = 0
    safe_command_action_refs: list[str] = Field(default_factory=list)
    available_provider_lane_family_count: int = 0
    available_provider_lane_family_ids: list[str] = Field(default_factory=list)
    available_provider_lane_count: int = 0
    available_provider_lane_action_refs: list[str] = Field(default_factory=list)
    verification_blocked_family_count: int = 0
    verification_blocked_family_ids: list[str] = Field(default_factory=list)
    verification_blocked_action_count: int = 0
    verification_blocked_action_refs: list[str] = Field(default_factory=list)
    verification_blocked_guided_action_count: int = 0
    verification_blocked_guided_action_refs: list[str] = Field(default_factory=list)
    verification_blocked_guided_action_family_count: int = 0
    verification_blocked_guided_action_family_ids: list[str] = Field(default_factory=list)
    verification_blocked_local_action_count: int = 0
    verification_blocked_local_action_refs: list[str] = Field(default_factory=list)
    verification_blocked_local_action_family_count: int = 0
    verification_blocked_local_action_family_ids: list[str] = Field(default_factory=list)
    context_blocked_family_count: int = 0
    context_blocked_family_ids: list[str] = Field(default_factory=list)
    context_blocked_action_count: int = 0
    context_blocked_action_refs: list[str] = Field(default_factory=list)
    multi_blocked_action_count: int = 0
    multi_blocked_action_refs: list[str] = Field(default_factory=list)
    multi_blocked_action_family_count: int = 0
    multi_blocked_action_family_ids: list[str] = Field(default_factory=list)
    defaulted_param_action_count: int = 0
    defaulted_param_action_refs: list[str] = Field(default_factory=list)
    defaulted_param_action_family_count: int = 0
    defaulted_param_action_family_ids: list[str] = Field(default_factory=list)
    missing_params_action_count: int = 0
    missing_params_action_refs: list[str] = Field(default_factory=list)
    missing_params_action_family_count: int = 0
    missing_params_action_family_ids: list[str] = Field(default_factory=list)
    missing_executable_action_count: int = 0
    missing_executable_action_refs: list[str] = Field(default_factory=list)
    missing_executable_action_family_count: int = 0
    missing_executable_action_family_ids: list[str] = Field(default_factory=list)
    no_local_command_action_count: int = 0
    no_local_command_action_refs: list[str] = Field(default_factory=list)
    no_local_command_action_family_count: int = 0
    no_local_command_action_family_ids: list[str] = Field(default_factory=list)
    provider_context_blocked_action_count: int = 0
    provider_context_blocked_action_refs: list[str] = Field(default_factory=list)
    provider_context_blocked_action_family_count: int = 0
    provider_context_blocked_action_family_ids: list[str] = Field(default_factory=list)
    provider_context_verified_action_count: int = 0
    provider_context_verified_action_refs: list[str] = Field(default_factory=list)
    provider_context_verified_action_family_count: int = 0
    provider_context_verified_action_family_ids: list[str] = Field(default_factory=list)
    provider_context_inferred_action_count: int = 0
    provider_context_inferred_action_refs: list[str] = Field(default_factory=list)
    provider_context_inferred_action_family_count: int = 0
    provider_context_inferred_action_family_ids: list[str] = Field(default_factory=list)
    provider_context_missing_action_count: int = 0
    provider_context_missing_action_refs: list[str] = Field(default_factory=list)
    provider_context_missing_action_family_count: int = 0
    provider_context_missing_action_family_ids: list[str] = Field(default_factory=list)
    commandless_execution_action_count: int = 0
    commandless_execution_action_refs: list[str] = Field(default_factory=list)
    commandless_execution_action_family_count: int = 0
    commandless_execution_action_family_ids: list[str] = Field(default_factory=list)
    preflight_ready_action_count: int = 0
    preflight_ready_action_refs: list[str] = Field(default_factory=list)
    preflight_ready_family_count: int = 0
    preflight_ready_family_ids: list[str] = Field(default_factory=list)
    not_preflight_ready_action_count: int = 0
    not_preflight_ready_action_refs: list[str] = Field(default_factory=list)
    not_preflight_ready_family_count: int = 0
    not_preflight_ready_family_ids: list[str] = Field(default_factory=list)
    confirmation_eligible_action_count: int = 0
    confirmation_eligible_action_refs: list[str] = Field(default_factory=list)
    confirmation_eligible_family_count: int = 0
    confirmation_eligible_family_ids: list[str] = Field(default_factory=list)
    not_confirmation_eligible_action_count: int = 0
    not_confirmation_eligible_action_refs: list[str] = Field(default_factory=list)
    not_confirmation_eligible_family_count: int = 0
    not_confirmation_eligible_family_ids: list[str] = Field(default_factory=list)
    ready_to_execute_action_count: int = 0
    ready_to_execute_action_refs: list[str] = Field(default_factory=list)
    ready_to_execute_family_count: int = 0
    ready_to_execute_family_ids: list[str] = Field(default_factory=list)
    not_ready_to_execute_action_count: int = 0
    not_ready_to_execute_action_refs: list[str] = Field(default_factory=list)
    not_ready_to_execute_family_count: int = 0
    not_ready_to_execute_family_ids: list[str] = Field(default_factory=list)
    unsafe_command_action_count: int = 0
    unsafe_command_action_refs: list[str] = Field(default_factory=list)
    unsafe_command_family_count: int = 0
    unsafe_command_family_ids: list[str] = Field(default_factory=list)
    command_ready_action_count: int = 0
    command_ready_action_refs: list[str] = Field(default_factory=list)
    command_ready_family_count: int = 0
    command_ready_family_ids: list[str] = Field(default_factory=list)
    command_not_ready_action_count: int = 0
    command_not_ready_action_refs: list[str] = Field(default_factory=list)
    command_not_ready_family_count: int = 0
    command_not_ready_family_ids: list[str] = Field(default_factory=list)
    parameterized_execution_action_count: int = 0
    parameterized_execution_action_refs: list[str] = Field(default_factory=list)
    parameterized_execution_family_count: int = 0
    parameterized_execution_family_ids: list[str] = Field(default_factory=list)
    non_parameterized_execution_action_count: int = 0
    non_parameterized_execution_action_refs: list[str] = Field(default_factory=list)
    non_parameterized_execution_family_count: int = 0
    non_parameterized_execution_family_ids: list[str] = Field(default_factory=list)
    params_complete_action_count: int = 0
    params_complete_action_refs: list[str] = Field(default_factory=list)
    params_complete_family_count: int = 0
    params_complete_family_ids: list[str] = Field(default_factory=list)
    params_incomplete_action_count: int = 0
    params_incomplete_action_refs: list[str] = Field(default_factory=list)
    params_incomplete_family_count: int = 0
    params_incomplete_family_ids: list[str] = Field(default_factory=list)
    action_count: int = 0
    action_statuses: list[str] = Field(default_factory=list)
    action_status_counts: dict[str, int] = Field(default_factory=dict)
    action_status_group_count: int = 0
    action_status_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    action_status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    action_status_family_counts: dict[str, int] = Field(default_factory=dict)
    action_status_family_count: int = 0
    action_status_families: list[str] = Field(default_factory=list)
    available_action_statuses: list[str] = Field(default_factory=list)
    available_action_status_counts: dict[str, int] = Field(default_factory=dict)
    available_action_status_group_count: int = 0
    available_action_status_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_action_status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_action_status_family_counts: dict[str, int] = Field(default_factory=dict)
    available_action_status_family_count: int = 0
    available_action_status_families: list[str] = Field(default_factory=list)
    blocked_action_statuses: list[str] = Field(default_factory=list)
    blocked_action_status_counts: dict[str, int] = Field(default_factory=dict)
    blocked_action_status_group_count: int = 0
    blocked_action_status_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_action_status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_action_status_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_action_status_family_count: int = 0
    blocked_action_status_families: list[str] = Field(default_factory=list)
    execution_modes: list[str] = Field(default_factory=list)
    execution_mode_counts: dict[str, int] = Field(default_factory=dict)
    execution_mode_group_count: int = 0
    execution_mode_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    execution_mode_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    execution_mode_family_counts: dict[str, int] = Field(default_factory=dict)
    execution_mode_family_count: int = 0
    execution_mode_families: list[str] = Field(default_factory=list)
    available_execution_modes: list[str] = Field(default_factory=list)
    available_execution_mode_counts: dict[str, int] = Field(default_factory=dict)
    available_execution_mode_group_count: int = 0
    available_execution_mode_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_execution_mode_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_execution_mode_family_counts: dict[str, int] = Field(default_factory=dict)
    available_execution_mode_family_count: int = 0
    available_execution_mode_families: list[str] = Field(default_factory=list)
    blocked_execution_modes: list[str] = Field(default_factory=list)
    blocked_execution_mode_counts: dict[str, int] = Field(default_factory=dict)
    blocked_execution_mode_group_count: int = 0
    blocked_execution_mode_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_execution_mode_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_execution_mode_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_execution_mode_family_count: int = 0
    blocked_execution_mode_families: list[str] = Field(default_factory=list)
    provider_support_modes: list[str] = Field(default_factory=list)
    provider_support_mode_counts: dict[str, int] = Field(default_factory=dict)
    provider_support_mode_group_count: int = 0
    provider_support_mode_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    provider_support_mode_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    provider_support_mode_family_counts: dict[str, int] = Field(default_factory=dict)
    provider_support_mode_family_count: int = 0
    provider_support_mode_families: list[str] = Field(default_factory=list)
    available_provider_support_modes: list[str] = Field(default_factory=list)
    available_provider_support_mode_counts: dict[str, int] = Field(default_factory=dict)
    available_provider_support_mode_group_count: int = 0
    available_provider_support_mode_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_provider_support_mode_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_provider_support_mode_family_counts: dict[str, int] = Field(default_factory=dict)
    available_provider_support_mode_family_count: int = 0
    available_provider_support_mode_families: list[str] = Field(default_factory=list)
    blocked_provider_support_modes: list[str] = Field(default_factory=list)
    blocked_provider_support_mode_counts: dict[str, int] = Field(default_factory=dict)
    blocked_provider_support_mode_group_count: int = 0
    blocked_provider_support_mode_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_provider_support_mode_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_provider_support_mode_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_provider_support_mode_family_count: int = 0
    blocked_provider_support_mode_families: list[str] = Field(default_factory=list)
    action_provider_context_statuses: list[str] = Field(default_factory=list)
    action_provider_context_status_counts: dict[str, int] = Field(default_factory=dict)
    action_provider_context_status_group_count: int = 0
    action_provider_context_status_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    action_provider_context_status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    action_provider_context_status_family_counts: dict[str, int] = Field(default_factory=dict)
    action_provider_context_status_family_count: int = 0
    action_provider_context_status_families: list[str] = Field(default_factory=list)
    available_action_provider_context_statuses: list[str] = Field(default_factory=list)
    available_action_provider_context_status_counts: dict[str, int] = Field(default_factory=dict)
    available_action_provider_context_status_group_count: int = 0
    available_action_provider_context_status_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_action_provider_context_status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_action_provider_context_status_family_counts: dict[str, int] = Field(default_factory=dict)
    available_action_provider_context_status_family_count: int = 0
    available_action_provider_context_status_families: list[str] = Field(default_factory=list)
    blocked_action_provider_context_statuses: list[str] = Field(default_factory=list)
    blocked_action_provider_context_status_counts: dict[str, int] = Field(default_factory=dict)
    blocked_action_provider_context_status_group_count: int = 0
    blocked_action_provider_context_status_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_action_provider_context_status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_action_provider_context_status_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_action_provider_context_status_family_count: int = 0
    blocked_action_provider_context_status_families: list[str] = Field(default_factory=list)
    verification_scopes: list[str] = Field(default_factory=list)
    verification_scope_counts: dict[str, int] = Field(default_factory=dict)
    verification_scope_group_count: int = 0
    verification_scope_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    verification_scope_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    verification_scope_family_counts: dict[str, int] = Field(default_factory=dict)
    verification_scope_family_count: int = 0
    verification_scope_families: list[str] = Field(default_factory=list)
    available_verification_scopes: list[str] = Field(default_factory=list)
    available_verification_scope_counts: dict[str, int] = Field(default_factory=dict)
    available_verification_scope_group_count: int = 0
    available_verification_scope_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_verification_scope_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_verification_scope_family_counts: dict[str, int] = Field(default_factory=dict)
    available_verification_scope_family_count: int = 0
    available_verification_scope_families: list[str] = Field(default_factory=list)
    blocked_verification_scopes: list[str] = Field(default_factory=list)
    blocked_verification_scope_counts: dict[str, int] = Field(default_factory=dict)
    blocked_verification_scope_group_count: int = 0
    blocked_verification_scope_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_verification_scope_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_verification_scope_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_verification_scope_family_count: int = 0
    blocked_verification_scope_families: list[str] = Field(default_factory=list)
    safe_command_reasons: list[str] = Field(default_factory=list)
    safe_command_reason_counts: dict[str, int] = Field(default_factory=dict)
    safe_command_reason_group_count: int = 0
    safe_command_reason_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    safe_command_reason_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    safe_command_reason_family_counts: dict[str, int] = Field(default_factory=dict)
    safe_command_reason_family_count: int = 0
    safe_command_reason_families: list[str] = Field(default_factory=list)
    available_safe_command_reasons: list[str] = Field(default_factory=list)
    available_safe_command_reason_counts: dict[str, int] = Field(default_factory=dict)
    available_safe_command_reason_group_count: int = 0
    available_safe_command_reason_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_safe_command_reason_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_safe_command_reason_family_counts: dict[str, int] = Field(default_factory=dict)
    available_safe_command_reason_family_count: int = 0
    available_safe_command_reason_families: list[str] = Field(default_factory=list)
    blocked_safe_command_reasons: list[str] = Field(default_factory=list)
    blocked_safe_command_reason_counts: dict[str, int] = Field(default_factory=dict)
    blocked_safe_command_reason_group_count: int = 0
    blocked_safe_command_reason_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_safe_command_reason_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_safe_command_reason_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_safe_command_reason_family_count: int = 0
    blocked_safe_command_reason_families: list[str] = Field(default_factory=list)
    context_requirement_reasons: list[str] = Field(default_factory=list)
    context_requirement_reason_counts: dict[str, int] = Field(default_factory=dict)
    context_requirement_reason_group_count: int = 0
    context_requirement_reason_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    context_requirement_reason_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    context_requirement_reason_family_counts: dict[str, int] = Field(default_factory=dict)
    context_requirement_reason_family_count: int = 0
    context_requirement_reason_families: list[str] = Field(default_factory=list)
    available_context_requirement_reasons: list[str] = Field(default_factory=list)
    available_context_requirement_reason_counts: dict[str, int] = Field(default_factory=dict)
    available_context_requirement_reason_group_count: int = 0
    available_context_requirement_reason_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_context_requirement_reason_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_context_requirement_reason_family_counts: dict[str, int] = Field(default_factory=dict)
    available_context_requirement_reason_family_count: int = 0
    available_context_requirement_reason_families: list[str] = Field(default_factory=list)
    blocked_context_requirement_reasons: list[str] = Field(default_factory=list)
    blocked_context_requirement_reason_counts: dict[str, int] = Field(default_factory=dict)
    blocked_context_requirement_reason_group_count: int = 0
    blocked_context_requirement_reason_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_context_requirement_reason_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_context_requirement_reason_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_context_requirement_reason_family_count: int = 0
    blocked_context_requirement_reason_families: list[str] = Field(default_factory=list)
    action_providers: list[str] = Field(default_factory=list)
    action_provider_counts: dict[str, int] = Field(default_factory=dict)
    action_provider_group_count: int = 0
    action_provider_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    action_provider_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    action_provider_family_counts: dict[str, int] = Field(default_factory=dict)
    action_provider_family_count: int = 0
    action_provider_families: list[str] = Field(default_factory=list)
    available_action_providers: list[str] = Field(default_factory=list)
    available_action_provider_counts: dict[str, int] = Field(default_factory=dict)
    available_action_provider_group_count: int = 0
    available_action_provider_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_action_provider_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_action_provider_family_counts: dict[str, int] = Field(default_factory=dict)
    available_action_provider_family_count: int = 0
    available_action_provider_families: list[str] = Field(default_factory=list)
    blocked_action_providers: list[str] = Field(default_factory=list)
    blocked_action_provider_counts: dict[str, int] = Field(default_factory=dict)
    blocked_action_provider_group_count: int = 0
    blocked_action_provider_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_action_provider_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_action_provider_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_action_provider_family_count: int = 0
    blocked_action_provider_families: list[str] = Field(default_factory=list)
    executable_names: list[str] = Field(default_factory=list)
    executable_name_counts: dict[str, int] = Field(default_factory=dict)
    executable_name_group_count: int = 0
    executable_name_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    executable_name_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    executable_name_family_counts: dict[str, int] = Field(default_factory=dict)
    executable_name_family_count: int = 0
    executable_name_families: list[str] = Field(default_factory=list)
    available_executable_names: list[str] = Field(default_factory=list)
    available_executable_name_counts: dict[str, int] = Field(default_factory=dict)
    available_executable_name_group_count: int = 0
    available_executable_name_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_executable_name_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_executable_name_family_counts: dict[str, int] = Field(default_factory=dict)
    available_executable_name_family_count: int = 0
    available_executable_name_families: list[str] = Field(default_factory=list)
    blocked_executable_names: list[str] = Field(default_factory=list)
    blocked_executable_name_counts: dict[str, int] = Field(default_factory=dict)
    blocked_executable_name_group_count: int = 0
    blocked_executable_name_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_executable_name_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_executable_name_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_executable_name_family_count: int = 0
    blocked_executable_name_families: list[str] = Field(default_factory=list)
    available_provider_context_statuses: list[str] = Field(default_factory=list)
    available_provider_context_status_counts: dict[str, int] = Field(default_factory=dict)
    available_provider_context_status_group_count: int = 0
    available_provider_context_status_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_provider_context_status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_provider_context_status_family_counts: dict[str, int] = Field(default_factory=dict)
    available_provider_context_status_family_count: int = 0
    available_provider_context_status_families: list[str] = Field(default_factory=list)
    blocked_provider_context_statuses: list[str] = Field(default_factory=list)
    blocked_provider_context_status_counts: dict[str, int] = Field(default_factory=dict)
    blocked_provider_context_status_group_count: int = 0
    blocked_provider_context_status_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_provider_context_status_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_provider_context_status_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_provider_context_status_family_count: int = 0
    blocked_provider_context_status_families: list[str] = Field(default_factory=list)
    execution_block_reasons: list[str] = Field(default_factory=list)
    execution_block_reason_counts: dict[str, int] = Field(default_factory=dict)
    execution_block_reason_group_count: int = 0
    execution_block_reason_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    execution_block_reason_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    execution_block_reason_family_counts: dict[str, int] = Field(default_factory=dict)
    execution_block_reason_family_count: int = 0
    execution_block_reason_families: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    blocking_reason_counts: dict[str, int] = Field(default_factory=dict)
    blocking_reason_group_count: int = 0
    blocking_reason_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocking_reason_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocking_reason_family_counts: dict[str, int] = Field(default_factory=dict)
    blocking_reason_family_count: int = 0
    blocking_reason_families: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    required_permission_count: int = 0
    required_permission_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    required_permission_family_counts: dict[str, int] = Field(default_factory=dict)
    required_permission_group_count: int = 0
    required_permission_family_count: int = 0
    required_permission_families: list[str] = Field(default_factory=list)
    permission_policies: list[str] = Field(default_factory=list)
    permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    permission_policy_group_count: int = 0
    permission_policy_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    permission_policy_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    permission_policy_family_counts: dict[str, int] = Field(default_factory=dict)
    permission_policy_family_count: int = 0
    permission_policy_families: list[str] = Field(default_factory=list)
    available_permission_policies: list[str] = Field(default_factory=list)
    available_permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    available_permission_policy_group_count: int = 0
    available_permission_policy_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_permission_policy_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_permission_policy_family_counts: dict[str, int] = Field(default_factory=dict)
    available_permission_policy_family_count: int = 0
    available_permission_policy_families: list[str] = Field(default_factory=list)
    blocked_permission_policies: list[str] = Field(default_factory=list)
    blocked_permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    blocked_permission_policy_group_count: int = 0
    blocked_permission_policy_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_permission_policy_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_permission_policy_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_permission_policy_family_count: int = 0
    blocked_permission_policy_families: list[str] = Field(default_factory=list)
    risk_levels: list[str] = Field(default_factory=list)
    risk_level_counts: dict[str, int] = Field(default_factory=dict)
    risk_level_group_count: int = 0
    risk_level_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    risk_level_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    risk_level_family_counts: dict[str, int] = Field(default_factory=dict)
    risk_level_family_count: int = 0
    risk_level_families: list[str] = Field(default_factory=list)
    available_risk_levels: list[str] = Field(default_factory=list)
    available_risk_level_counts: dict[str, int] = Field(default_factory=dict)
    available_risk_level_group_count: int = 0
    available_risk_level_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_risk_level_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_risk_level_family_counts: dict[str, int] = Field(default_factory=dict)
    available_risk_level_family_count: int = 0
    available_risk_level_families: list[str] = Field(default_factory=list)
    blocked_risk_levels: list[str] = Field(default_factory=list)
    blocked_risk_level_counts: dict[str, int] = Field(default_factory=dict)
    blocked_risk_level_group_count: int = 0
    blocked_risk_level_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_risk_level_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_risk_level_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_risk_level_family_count: int = 0
    blocked_risk_level_families: list[str] = Field(default_factory=list)
    execution_required_permissions: list[str] = Field(default_factory=list)
    execution_required_permission_count: int = 0
    execution_required_permission_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    execution_required_permission_family_counts: dict[str, int] = Field(default_factory=dict)
    execution_required_permission_group_count: int = 0
    execution_required_permission_family_count: int = 0
    execution_required_permission_families: list[str] = Field(default_factory=list)
    execution_permission_policies: list[str] = Field(default_factory=list)
    execution_permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    execution_permission_policy_group_count: int = 0
    execution_permission_policy_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    execution_permission_policy_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    execution_permission_policy_family_counts: dict[str, int] = Field(default_factory=dict)
    execution_permission_policy_family_count: int = 0
    execution_permission_policy_families: list[str] = Field(default_factory=list)
    available_execution_permission_policies: list[str] = Field(default_factory=list)
    available_execution_permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    available_execution_permission_policy_group_count: int = 0
    available_execution_permission_policy_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_execution_permission_policy_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_execution_permission_policy_family_counts: dict[str, int] = Field(default_factory=dict)
    available_execution_permission_policy_family_count: int = 0
    available_execution_permission_policy_families: list[str] = Field(default_factory=list)
    blocked_execution_permission_policies: list[str] = Field(default_factory=list)
    blocked_execution_permission_policy_counts: dict[str, int] = Field(default_factory=dict)
    blocked_execution_permission_policy_group_count: int = 0
    blocked_execution_permission_policy_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_execution_permission_policy_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_execution_permission_policy_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_execution_permission_policy_family_count: int = 0
    blocked_execution_permission_policy_families: list[str] = Field(default_factory=list)
    execution_risk_levels: list[str] = Field(default_factory=list)
    execution_risk_level_counts: dict[str, int] = Field(default_factory=dict)
    execution_risk_level_group_count: int = 0
    execution_risk_level_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    execution_risk_level_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    execution_risk_level_family_counts: dict[str, int] = Field(default_factory=dict)
    execution_risk_level_family_count: int = 0
    execution_risk_level_families: list[str] = Field(default_factory=list)
    available_execution_risk_levels: list[str] = Field(default_factory=list)
    available_execution_risk_level_counts: dict[str, int] = Field(default_factory=dict)
    available_execution_risk_level_group_count: int = 0
    available_execution_risk_level_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    available_execution_risk_level_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    available_execution_risk_level_family_counts: dict[str, int] = Field(default_factory=dict)
    available_execution_risk_level_family_count: int = 0
    available_execution_risk_level_families: list[str] = Field(default_factory=list)
    blocked_execution_risk_levels: list[str] = Field(default_factory=list)
    blocked_execution_risk_level_counts: dict[str, int] = Field(default_factory=dict)
    blocked_execution_risk_level_group_count: int = 0
    blocked_execution_risk_level_action_refs: dict[str, list[str]] = Field(default_factory=dict)
    blocked_execution_risk_level_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocked_execution_risk_level_family_counts: dict[str, int] = Field(default_factory=dict)
    blocked_execution_risk_level_family_count: int = 0
    blocked_execution_risk_level_families: list[str] = Field(default_factory=list)
    artifact_count: int = 0
    artifact_family_count: int = 0
    artifact_family_ids: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    artifact_types: list[str] = Field(default_factory=list)
    artifact_type_counts: dict[str, int] = Field(default_factory=dict)
    artifact_type_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    artifact_type_family_counts: dict[str, int] = Field(default_factory=dict)
    artifact_type_group_count: int = 0
    artifact_type_family_count: int = 0
    artifact_type_families: list[str] = Field(default_factory=list)
    safe_commands: list[str] = Field(default_factory=list)
    safe_command_values: list[str] = Field(default_factory=list)
    safe_command_value_counts: dict[str, int] = Field(default_factory=dict)
    safe_command_value_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    safe_command_value_family_counts: dict[str, int] = Field(default_factory=dict)
    safe_command_value_group_count: int = 0
    safe_command_value_family_count: int = 0
    safe_command_value_families: list[str] = Field(default_factory=list)
    blocker_count: int = 0
    blocker_family_count: int = 0
    blocker_family_ids: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    blocker_values: list[str] = Field(default_factory=list)
    blocker_value_counts: dict[str, int] = Field(default_factory=dict)
    blocker_value_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    blocker_value_family_counts: dict[str, int] = Field(default_factory=dict)
    blocker_value_group_count: int = 0
    blocker_value_family_count: int = 0
    blocker_value_families: list[str] = Field(default_factory=list)
    recommended_fix_count: int = 0
    recommended_fix_family_count: int = 0
    recommended_fix_family_ids: list[str] = Field(default_factory=list)
    recommended_fixes: list[str] = Field(default_factory=list)
    recommended_fix_values: list[str] = Field(default_factory=list)
    recommended_fix_value_counts: dict[str, int] = Field(default_factory=dict)
    recommended_fix_value_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    recommended_fix_value_family_counts: dict[str, int] = Field(default_factory=dict)
    recommended_fix_value_group_count: int = 0
    recommended_fix_value_family_count: int = 0
    recommended_fix_value_families: list[str] = Field(default_factory=list)
    note_count: int = 0
    note_family_count: int = 0
    note_family_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    note_values: list[str] = Field(default_factory=list)
    note_value_counts: dict[str, int] = Field(default_factory=dict)
    note_value_family_ids: dict[str, list[str]] = Field(default_factory=dict)
    note_value_family_counts: dict[str, int] = Field(default_factory=dict)
    note_value_group_count: int = 0
    note_value_family_count: int = 0
    note_value_families: list[str] = Field(default_factory=list)
    families: list[ProjectIntegrationFamilyRead] = Field(default_factory=list)


class IntegrationActionRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class IntegrationActionPreviewRead(BaseModel):
    family: str
    action_id: str
    title: str
    summary: str
    project_name: str
    workspace_path: str | None = None
    command: str | None = None
    risk_level: RiskLevel = "medium"
    permission_policy: ToolPermissionPolicy = "ask_every_time"
    preview_supported: bool = True
    mutates_remote_state: bool = False
    requires_confirmation: bool = False
    required_params: list[str] = Field(default_factory=list)
    missing_params: list[str] = Field(default_factory=list)
    params_complete: bool = True
    provider: str | None = None
    provider_candidates: list[str] = Field(default_factory=list)
    provider_signal_breakdown: dict[str, Any] = Field(default_factory=dict)
    resolved_provider_evidence: dict[str, Any] = Field(default_factory=dict)
    cli_only_candidates_suppressed: list[str] = Field(default_factory=list)
    provider_resolution_state: IntegrationProviderResolutionState = "unresolved"
    provider_support_mode: IntegrationActionSupportMode = "unsupported"
    supported_providers: list[str] = Field(default_factory=list)
    supported_provider_count: int = 0
    provider_lane_resolved: bool = False
    provider_context_verified: bool = False
    provider_context_source: str = "none"
    provider_context_status: IntegrationProviderContextStatus = "missing"
    provider_verification_required: bool = False
    provider_verification_reason: str | None = None
    verification_scope: IntegrationVerificationScope | None = None
    executable_name: str | None = None
    defaulted_params: dict[str, Any] = Field(default_factory=dict)
    command_ready: bool = False
    execution_mode: str = "unavailable"
    execution_block_reason: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    blocking_reason_count: int = 0
    preflight_ready: bool = False
    confirmation_eligible: bool = False
    ready_to_execute: bool = False
    safe_command_eligible: bool = False
    safe_command_reason: str | None = None
    context_required: bool = False
    context_requirement_reason: str | None = None
    context_available: bool = False
    suppressed_command_reason: str | None = None
    provider_guidance: str | None = None
    notes: list[str] = Field(default_factory=list)


class IntegrationActionExecutionRead(IntegrationActionPreviewRead):
    status: str
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    approval_required: bool = False
    updated_registry: dict[str, Any] = Field(default_factory=dict)


class ToolPermissionRead(BaseModel):
    tool_id: str
    permission_policy: ToolPermissionPolicy


class ToolPermissionUpdate(BaseModel):
    permission_policy: ToolPermissionPolicy


class SkillRead(BaseModel):
    name: str
    source: str
    available: bool = True
    summary: str | None = None


class AuthJobRead(BaseModel):
    id: str
    method: AuthJobMethod
    status: AuthJobStatus
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    message: str
    auth_mode_after: str | None = None
    log_path: str | None = None
    output_lines: list[str] = Field(default_factory=list)


class ChatGptLoginRequest(BaseModel):
    device_auth: bool = False


class ApiKeyLoginRequest(BaseModel):
    api_key: str = Field(min_length=1)


class ProviderStatusRead(BaseModel):
    provider: ProviderId
    label: str
    cli_detected: bool
    cli_path: str | None = None
    cli_path_exists: bool = False
    cli_execution_available: bool = False
    cli_version: str | None
    authenticated: bool
    auth_mode: str | None
    auth_status_detectable: bool = True
    login_status: str
    supports_model_override: bool
    supports_reasoning_effort: bool
    supports_app_server: bool
    supports_builtin_auth: bool
    runtime_ready: bool = False
    runtime_summary: str | None = None
    requires_adapter_command: bool = False
    adapter_command_configured: bool = False
    adapter_command_detected: bool = False
    adapter_command_path: str | None = None
    adapter_args: list[str] = Field(default_factory=list)
    adapter_recipe_source: Literal["explicit", "builtin", "none"] = "none"
    provider_endpoint_configured: bool = False
    available_models: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AuthStateRead(BaseModel):
    authenticated: bool
    auth_mode: str | None
    login_status: str
    cli_detected: bool
    provider: ProviderId = "codex"
    current_job: AuthJobRead | None = None
    chatgpt_supported: bool = True
    device_auth_supported: bool = True
    api_key_supported: bool = True
    provider_statuses: list[ProviderStatusRead] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SystemStatusRead(BaseModel):
    selected_provider: ProviderId = "codex"
    selected_provider_label: str
    cli_detected: bool
    cli_path: str | None = None
    cli_path_exists: bool = False
    cli_execution_available: bool = False
    cli_version: str | None
    login_status: str
    auth_mode: str | None
    authenticated: bool = False
    runtime_ready: bool = False
    runtime_summary: str | None = None
    app_server_supported: bool
    app_server_handshake_status: str
    app_server_transport: str
    effective_runner_mode: str
    dry_run_available: bool
    runtime_directory: str
    diagnostics_directory: str | None = None
    repo_root: str | None = None
    launcher_root: str | None = None
    plugin_source_root: str | None = None
    backend_host: str = "127.0.0.1"
    backend_port: int
    backend_base_url: str | None = None
    configured_backend_port: int | None = None
    backend_binding_source: str | None = None
    frontend_port: int | None
    active_runs: list[dict[str, Any]]
    current_settings_summary: ProjectSettingsRead | None = None
    selected_manager_model: str | None = None
    selected_default_worker_model: str | None = None
    available_models: list[str] = Field(default_factory=list)
    model_advisories: list[dict[str, Any]] = Field(default_factory=list)
    provider_statuses: list[ProviderStatusRead] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]]
    configured_mcp_servers: list[dict[str, Any]] = Field(default_factory=list)
    mcp_state: dict[str, Any] = Field(default_factory=dict)
    configured_plugins: list[str]
    local_skills: list[str]
    current_auth_job: AuthJobRead | None = None
    notes: list[str]
    startup_summary: StartupStatusRead | None = None
    app_state_summary: AppStateRead | None = None


class CodexStatusRead(SystemStatusRead):
    pass


PluginHealthState = Literal["ready", "degraded", "broken"]
PluginHealthCheckState = Literal["ready", "degraded", "broken", "unknown"]


class PluginHealthCheckRead(BaseModel):
    key: str
    label: str
    status: PluginHealthCheckState
    summary: str
    recommended_fix: str | None = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime
    code: str | None = None
    family: str | None = None
    severity: ErrorSeverity | None = None
    breakpoint: str | None = None
    retryable: bool | None = None
    user_action_required: bool | None = None
    correlation_id: str | None = None
    redaction_status: BridgeRedactionStatus = "clean"


class PluginHealthSummaryRead(BaseModel):
    status: PluginHealthState
    checks: list[PluginHealthCheckRead] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    safe_troubleshooting_commands: list[str] = Field(default_factory=list)
    codex_chat_markdown: str
    checked_at: datetime
    notes: list[str] = Field(default_factory=list)
    platform_profile: dict[str, Any] = Field(default_factory=dict)
    performance_profile: dict[str, Any] = Field(default_factory=dict)
    device_debug_commands: list[str] = Field(default_factory=list)


PluginHealthRead = PluginHealthSummaryRead

HeadlessSetupStatus = Literal["ready", "degraded", "failed"]
RunnerAuthStatus = Literal["authenticated", "unauthenticated", "unknown", "not_required"]
AttachPolicyRead = AttachPolicy


class RunnerProbeRead(BaseModel):
    runner_id: str
    label: str
    available: bool
    configured: bool
    auth_status: RunnerAuthStatus
    install_status: str
    command_path: str | None = None
    version: str | None = None
    safe_default: bool = False
    requires_user_action: bool = False
    recommended_fix: str | None = None
    billing_warning: str | None = None
    code: str | None = None
    severity: ErrorSeverity | None = None
    breakpoint: str | None = None
    retryable: bool | None = None
    user_action_required: bool | None = None
    models: list[str] = Field(default_factory=list)
    details_json: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime


class RunnersStatusRead(BaseModel):
    status: HeadlessSetupStatus
    runners: list[RunnerProbeRead] = Field(default_factory=list)
    enabled_runners: list[str] = Field(default_factory=list)
    safe_defaults: list[str] = Field(default_factory=list)
    checked_at: datetime


class HeadlessConfigRead(BaseModel):
    config_path: str
    install_id: str
    install_path: str
    runtime_path: str
    headless_only: bool = True
    dashboard_enabled: bool = False
    daemon_host: str
    daemon_port: int
    mcp_transport: str
    mcp_port: int | None = None
    enabled_runners: list[str] = Field(default_factory=list)
    runner_configs: dict[str, Any] = Field(default_factory=dict)
    default_runner_policy: dict[str, Any] = Field(default_factory=dict)
    default_model_policy: dict[str, Any] = Field(default_factory=dict)
    safe_mode_defaults: dict[str, Any] = Field(default_factory=dict)
    plugin_paths: list[str] = Field(default_factory=list)
    skills_paths: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    redaction_status: BridgeRedactionStatus = "clean"


class HeadlessAutowireRequest(BaseModel):
    workspace_path: str | None = None
    install_path: str | None = None
    runtime_path: str | None = None
    daemon_host: str | None = None
    daemon_port: int | None = None
    mcp_transport: str | None = None
    mcp_port: int | None = None
    headless_only: bool = True
    dry_run: bool = False


class HeadlessRepairRequest(BaseModel):
    install_path: str | None = None
    runtime_path: str | None = None
    daemon_host: str | None = None
    daemon_port: int | None = None
    mcp_transport: str | None = None
    mcp_port: int | None = None
    headless_only: bool = True
    preserve_config: bool = True


class InstallReportRead(BaseModel):
    status: HeadlessSetupStatus
    install_path: str
    runtime_path: str
    active_repo_root: str | None = None
    daemon_status: str
    mcp_status: str
    subsystem_status: dict[str, str] = Field(default_factory=dict)
    readiness_matrix: list[dict[str, Any]] = Field(default_factory=list)
    configured_runners: list[str] = Field(default_factory=list)
    unavailable_runners: list[str] = Field(default_factory=list)
    discovered_installs: list[dict[str, Any]] = Field(default_factory=list)
    user_actions_required: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_codex_prompt: str
    redaction_status: BridgeRedactionStatus = "clean"
    created_at: datetime
    codex_chat_markdown: str
    headless_config: HeadlessConfigRead | None = None
    plugin_health: PluginHealthSummaryRead | None = None
    problems: list[ProblemDetailsRead] = Field(default_factory=list)
