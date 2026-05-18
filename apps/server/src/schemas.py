from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ProviderId = Literal["codex", "ollama", "openai_api", "anthropic_api", "xai_api", "claude_code", "custom"]
StartupProviderChoice = ProviderId
StartupStartMode = Literal["new_project", "guided_walkthrough"]
RunnerMode = Literal["auto", "cli", "app_server", "dry_run"]
ManagerMode = Literal["auto", "provider", "codex", "deterministic"]
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
SwarmIntensity = Literal["low", "medium", "high", "extreme"]


class ProjectCreate(BaseModel):
    name: str
    idea: str
    workspace_path: str
    provider: ProviderId = "codex"
    runner_mode: RunnerMode = "auto"
    manager_mode: ManagerMode = "auto"


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
    required_checks_json: list[str] = Field(default_factory=list)
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
    details: dict[str, Any] = Field(default_factory=dict)


class StartupStatusRead(BaseModel):
    mode: StartupMode
    first_run_completed: bool
    setup_version_completed: str | None = None
    current_setup_version: str
    install_id: str
    startup_attempt: int
    max_startup_attempts: int
    overall_status: StartupOverallStatus
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
    summary: str
    error_code: str | None = None
    recommended_fixes: list[str] = Field(default_factory=list)


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


class DiagnosticReportListItemRead(BaseModel):
    path: str
    json_path: str | None = None
    created_at: datetime
    error_code: str | None = None
    summary: str


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
    cli_version: str | None
    authenticated: bool
    auth_mode: str | None
    auth_status_detectable: bool = True
    login_status: str
    supports_model_override: bool
    supports_reasoning_effort: bool
    supports_app_server: bool
    supports_builtin_auth: bool
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
    cli_version: str | None
    login_status: str
    auth_mode: str | None
    authenticated: bool = False
    app_server_supported: bool
    app_server_handshake_status: str
    app_server_transport: str
    effective_runner_mode: str
    dry_run_available: bool
    runtime_directory: str
    diagnostics_directory: str | None = None
    backend_port: int
    frontend_port: int | None
    active_runs: list[dict[str, Any]]
    current_settings_summary: ProjectSettingsRead | None = None
    selected_manager_model: str | None = None
    selected_default_worker_model: str | None = None
    available_models: list[str] = Field(default_factory=list)
    provider_statuses: list[ProviderStatusRead] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]]
    configured_plugins: list[str]
    local_skills: list[str]
    current_auth_job: AuthJobRead | None = None
    notes: list[str]
    startup_summary: StartupStatusRead | None = None
    app_state_summary: AppStateRead | None = None


class CodexStatusRead(SystemStatusRead):
    pass
