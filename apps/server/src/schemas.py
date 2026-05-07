from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


RunnerMode = Literal["auto", "cli", "app_server", "dry_run"]
ManagerMode = Literal["auto", "codex", "deterministic"]
AgentStatus = Literal["idle", "starting", "working", "waiting", "needs_review", "blocked", "done", "stopped", "error"]
TaskStatus = Literal["backlog", "assigned", "working", "waiting_on_paths", "needs_review", "done", "blocked"]
PlanAction = Literal["approve_build", "simplify", "ambitious", "usability", "quality", "rewrite", "feature_delta"]
TaskComplexity = Literal["small", "medium", "large"]
WorkerReportStatus = Literal["done", "blocked", "needs_review", "error"]
WorkerDecisionType = Literal["assign_next_task", "request_fix", "mark_done", "mark_blocked", "retire_agent", "escalate_to_user", "wait"]
ReasoningEffort = Literal["minimal", "low", "medium", "high"]
SandboxMode = Literal["workspace-write", "read-only"]
ApprovalPolicy = Literal["on-request", "untrusted", "never"]


class ProjectCreate(BaseModel):
    name: str
    idea: str
    workspace_path: str
    runner_mode: RunnerMode = "auto"
    manager_mode: ManagerMode = "auto"


class ProjectRead(BaseModel):
    id: int
    name: str
    idea: str
    workspace_path: str
    status: str
    runner_mode: RunnerMode
    manager_mode: ManagerMode
    docs_path: str | None
    final_report_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocGenerationResponse(BaseModel):
    docs_path: str
    files: list[str]
    used_live_manager: bool = False
    manager_mode_used: str = "deterministic"


class InterviewStartRequest(BaseModel):
    question_count: Literal[6, 20, 50]


class InterviewOption(BaseModel):
    id: str
    label: str
    description: str


class InterviewQuestionRead(BaseModel):
    id: int
    index: int
    question: str
    options: list[InterviewOption]
    selected_option: str | None
    selected_text: str | None
    rationale: str | None


class InterviewSessionRead(BaseModel):
    id: int
    project_id: int
    question_count: int
    current_index: int
    status: str
    questions: list[InterviewQuestionRead]


class InterviewAnswerRequest(BaseModel):
    question_id: int
    option_id: str
    selected_text: str


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

    class Config:
        from_attributes = True


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
    workspace_path: str
    session_ref: str | None
    locked_paths_json: list[str] | None
    failure_count: int
    last_report_summary: str | None
    active_model: str | None
    active_reasoning_effort: str | None
    active_runner_type: str | None
    current_action: str | None
    last_update: datetime

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class RunReportRequest(WorkerReport):
    pass


class EventRead(BaseModel):
    id: int
    project_id: int
    event_type: str
    payload_json: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class ManagerMessageRequest(BaseModel):
    message: str = Field(min_length=1)


class LogRead(BaseModel):
    agent_id: int
    logs_path: str | None
    content: str


class ProjectSettingsRead(BaseModel):
    project_id: int
    manager_model: str | None
    default_worker_model: str | None
    manager_reasoning_effort: ReasoningEffort | None
    default_worker_reasoning_effort: ReasoningEffort | None
    per_role_model_overrides_json: dict[str, str]
    per_role_reasoning_overrides_json: dict[str, str]
    runner_mode: RunnerMode
    sandbox_mode: SandboxMode
    approval_policy: ApprovalPolicy
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectSettingsUpdate(BaseModel):
    manager_model: str | None = None
    default_worker_model: str | None = None
    manager_reasoning_effort: ReasoningEffort | None = None
    default_worker_reasoning_effort: ReasoningEffort | None = None
    per_role_model_overrides_json: dict[str, str] = Field(default_factory=dict)
    per_role_reasoning_overrides_json: dict[str, str] = Field(default_factory=dict)
    runner_mode: RunnerMode = "auto"
    sandbox_mode: SandboxMode = "workspace-write"
    approval_policy: ApprovalPolicy = "on-request"


class SystemStatusRead(BaseModel):
    cli_detected: bool
    cli_version: str | None
    login_status: str
    auth_mode: str | None
    app_server_supported: bool
    app_server_handshake_status: str
    app_server_transport: str
    effective_runner_mode: str
    dry_run_available: bool
    runtime_directory: str
    backend_port: int
    frontend_port: int | None
    active_runs: list[dict[str, Any]]
    current_settings_summary: ProjectSettingsRead | None = None
    selected_manager_model: str | None = None
    selected_default_worker_model: str | None = None
    available_models: list[str] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]]
    configured_plugins: list[str]
    local_skills: list[str]
    notes: list[str]


class CodexStatusRead(BaseModel):
    cli_detected: bool
    cli_version: str | None
    login_status: str
    auth_mode: str | None
    app_server_supported: bool
    app_server_handshake_status: str
    app_server_transport: str
    effective_runner_mode: str
    dry_run_available: bool
    runtime_directory: str
    backend_port: int
    frontend_port: int | None
    active_runs: list[dict[str, Any]]
    current_settings_summary: ProjectSettingsRead | None = None
    selected_manager_model: str | None = None
    selected_default_worker_model: str | None = None
    available_models: list[str] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]]
    configured_plugins: list[str]
    local_skills: list[str]
    notes: list[str]
