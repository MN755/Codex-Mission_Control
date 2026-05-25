from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ProviderId = Literal["codex", "ollama", "openai_api", "anthropic_api", "xai_api", "claude_code", "custom"]
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
SwarmOptimizationMode = Literal["fastest_build", "balanced", "high_quality", "documentation_heavy", "research_planning", "massive_codebase", "manager_decides"]
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
    provider: ProviderId = "codex"
    manager_model: str | None = None
    default_worker_model: str | None = None
    manager_reasoning_effort: ReasoningEffort | None = None
    default_worker_reasoning_effort: ReasoningEffort | None = None
    per_role_model_overrides_json: dict[str, str] = Field(default_factory=dict)
    per_role_reasoning_overrides_json: dict[str, str] = Field(default_factory=dict)
    provider_endpoint: str | None = None
    adapter_command: str | None = None
    adapter_args_json: list[str] = Field(default_factory=list)
    runner_mode: RunnerMode = "auto"
    sandbox_mode: SandboxMode = "workspace-write"
    approval_policy: ApprovalPolicy = "on-request"
    workspace_widgets_json: list[str] = Field(default_factory=list)
    approval_overrides_json: dict[str, Any] = Field(default_factory=dict)


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
    optimization_mode: SwarmOptimizationMode = "balanced"
    swarm_aggressiveness: SwarmAggressiveness = "medium"
    max_agents: int = Field(default=8, ge=1, le=50)
    require_approval_above_agent_count: int = Field(default=10, ge=1, le=50)
    allow_dynamic_spawning: bool = True
    allow_dynamic_retirement: bool = True
    docs_depth: DocsDepth = "standard"
    testing_depth: TestingDepth = "standard"


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
    default_command_policy: DefaultExecutionPolicy = "ask"
    default_tool_policy: DefaultExecutionPolicy = "ask"
    network_access_policy: NetworkAccessPolicy = "ask"
    write_access_policy: WriteAccessPolicy = "workspace_write"
    external_account_policy: ExternalAccountPolicy = "ask"
    deployment_policy: DeploymentPolicy = "deny"
    destructive_action_policy: DestructiveActionPolicy = "critical_approval"
    auto_approve_low_risk: bool = False
    auto_approve_medium_risk: bool = False
    high_risk_requires_user: bool = True


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
    prompt_summary: str
    prompt_path: str | None = None
    response_summary: str
    report_json: dict[str, Any] = Field(default_factory=dict)
    files_changed_json: list[str] = Field(default_factory=list)
    approvals_requested_json: list[dict[str, Any]] = Field(default_factory=list)
    commands_attempted_json: list[str] = Field(default_factory=list)
    manager_decision_after: str | None = None
    redaction_status: str
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
    included_files_json: list[str] = Field(default_factory=list)
    excluded_files_json: list[str] = Field(default_factory=list)
    known_decisions_json: list[str] = Field(default_factory=list)
    relevant_assumptions_json: list[str] = Field(default_factory=list)
    validation_steps_json: list[str] = Field(default_factory=list)
    token_budget_hint: int | None = None
    warnings_json: list[str] = Field(default_factory=list)
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


class ValidationCoverageAreaRead(BaseModel):
    id: int
    project_id: int
    area: str
    coverage_status: Literal["none", "planned", "partial", "validated", "failed", "skipped"]
    evidence_summary: str | None = None
    related_validation_step_id: int | None = None
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


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
    startup_started_at: datetime
    last_completed_at: datetime | None = None


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
    tests_count: int = 0
    run_instructions: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    confidence_level: str | None = None
    evidence_status: str | None = None
    missing_evidence: list[str] = Field(default_factory=list)
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
    platform_profile: dict[str, Any] = Field(default_factory=dict)
    performance_profile: dict[str, Any] = Field(default_factory=dict)
    safe_debug_commands: list[str] = Field(default_factory=list)


ToolAvailability = Literal["available", "needs_setup", "experimental", "unsupported_on_device", "coming_soon"]
ToolPermissionPolicy = Literal["ask_every_time", "ask_once_per_project", "allow_for_project", "never_allow"]


class ToolCatalogItemRead(BaseModel):
    id: str
    name: str
    category: str
    summary: str
    availability: ToolAvailability
    permission_policy: ToolPermissionPolicy
    risk_level: RiskLevel
    notes: list[str] = Field(default_factory=list)


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
