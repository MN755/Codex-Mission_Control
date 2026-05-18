from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    idea: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    runner_mode: Mapped[str] = mapped_column(String(30), default="auto", nullable=False)
    manager_mode: Mapped[str] = mapped_column(String(30), default="auto", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    docs_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_milestone: Mapped[str | None] = mapped_column(String(160), nullable=True)
    latest_activity: Mapped[str | None] = mapped_column(Text, nullable=True)
    handoff_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    interview_sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="project")
    plans: Mapped[list["Plan"]] = relationship(back_populates="project")
    agents: Mapped[list["Agent"]] = relationship(back_populates="project")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")
    events: Mapped[list["ProjectEvent"]] = relationship(back_populates="project")
    reservations: Mapped[list["PathReservation"]] = relationship(back_populates="project")
    settings: Mapped["ProjectSettings | None"] = relationship(back_populates="project", uselist=False)
    swarm_preferences: Mapped["SwarmPreferences | None"] = relationship(back_populates="project", uselist=False)
    understanding: Mapped["ProjectUnderstanding | None"] = relationship(back_populates="project", uselist=False)
    swarm_plans: Mapped[list["SwarmPlan"]] = relationship(back_populates="project")
    swarm_events: Mapped[list["SwarmEvent"]] = relationship(back_populates="project")
    manager_messages: Mapped[list["ManagerMessage"]] = relationship(back_populates="project")
    manager_questions: Mapped[list["ManagerQuestion"]] = relationship(back_populates="project")
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(back_populates="project")
    widget_instances: Mapped[list["WidgetInstance"]] = relationship(back_populates="project")
    swarm_budget: Mapped["SwarmBudget | None"] = relationship(back_populates="project", uselist=False)
    agent_contracts: Mapped[list["AgentContract"]] = relationship(back_populates="project")
    path_locks: Mapped[list["PathLock"]] = relationship(back_populates="project")
    decision_records: Mapped[list["DecisionRecord"]] = relationship(back_populates="project")
    project_confidence: Mapped[list["ProjectConfidence"]] = relationship(back_populates="project")
    recovery_plans: Mapped[list["RecoveryPlan"]] = relationship(back_populates="project")
    stuck_signals: Mapped[list["AgentStuckSignal"]] = relationship(back_populates="project")
    review_gates: Mapped[list["ReviewGate"]] = relationship(back_populates="project")
    model_policies: Mapped[list["ModelPolicy"]] = relationship(back_populates="project")
    tool_routing_policies: Mapped[list["ToolRoutingPolicy"]] = relationship(back_populates="project")
    manager_assumptions: Mapped[list["ManagerAssumption"]] = relationship(back_populates="project")
    repo_intelligence: Mapped["RepoIntelligenceSummary | None"] = relationship(back_populates="project", uselist=False)
    validation_recipes: Mapped[list["ValidationRecipe"]] = relationship(back_populates="project")
    handoff_quality_preference: Mapped["HandoffQualityPreference | None"] = relationship(back_populates="project", uselist=False)
    change_requests: Mapped[list["ChangeRequest"]] = relationship(back_populates="project")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    question_budget: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    questions_asked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="in_progress", nullable=False)
    manager_mode: Mapped[str] = mapped_column(String(30), default="auto", nullable=False)
    stopped_early: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    known_facts_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    unknowns_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="interview_sessions")
    questions: Mapped[list["InterviewQuestion"]] = relationship(back_populates="session")


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    impact: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    options_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    allow_custom_answer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    selected_option: Mapped[str | None] = mapped_column(String(200), nullable=True)
    selected_option_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    selected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    affects_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    question_source: Mapped[str] = mapped_column(String(40), default="fallback_generated", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[InterviewSession] = relationship(back_populates="questions")


class ProjectUnderstanding(Base):
    __tablename__ = "project_understanding"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    known_facts_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    unknowns_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    assumptions_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    constraints_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence_by_category_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="understanding")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="plans")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), default="worker", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="idle", nullable=False)
    current_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", use_alter=True, name="fk_agents_current_task_id"),
        nullable=True,
    )
    swarm_plan_id: Mapped[int | None] = mapped_column(ForeignKey("swarm_plans.id"), nullable=True)
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    archetype: Mapped[str | None] = mapped_column(String(80), nullable=True)
    mission: Mapped[str | None] = mapped_column(Text, nullable=True)
    retire_when: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    locked_paths_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_report_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active_reasoning_effort: Mapped[str | None] = mapped_column(String(30), nullable=True)
    active_runner_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="agents")
    current_task: Mapped["Task | None"] = relationship(foreign_keys=[current_task_id], post_update=True)
    runs: Mapped[list["AgentRun"]] = relationship(back_populates="agent")
    reservations: Mapped[list["PathReservation"]] = relationship(back_populates="agent")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    assigned_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", use_alter=True, name="fk_tasks_assigned_agent_id"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    agent_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    milestone: Mapped[str | None] = mapped_column(String(120), nullable=True)
    allowed_paths_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    forbidden_paths_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    validation_steps_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    success_criteria_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    estimated_complexity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    dependencies_json: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="backlog", nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    waiting_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="tasks")
    reservations: Mapped[list["PathReservation"]] = relationship(back_populates="task")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    runner_type: Mapped[str] = mapped_column(String(50), nullable=False)
    process_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="starting", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    logs_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_log_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manager_action: Mapped[str | None] = mapped_column(String(80), nullable=True)
    effective_settings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    agent: Mapped[Agent] = relationship(back_populates="runs")


class PathReservation(Base):
    __tablename__ = "path_reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="reservations")
    task: Mapped[Task] = relationship(back_populates="reservations")
    agent: Mapped[Agent] = relationship(back_populates="reservations")


class ProjectSettings(Base):
    __tablename__ = "project_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="codex", nullable=False)
    manager_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_worker_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manager_reasoning_effort: Mapped[str | None] = mapped_column(String(30), nullable=True)
    default_worker_reasoning_effort: Mapped[str | None] = mapped_column(String(30), nullable=True)
    per_role_model_overrides_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    per_role_reasoning_overrides_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    adapter_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    adapter_args_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    runner_mode: Mapped[str] = mapped_column(String(30), default="auto", nullable=False)
    sandbox_mode: Mapped[str] = mapped_column(String(30), default="workspace-write", nullable=False)
    approval_policy: Mapped[str] = mapped_column(String(30), default="on-request", nullable=False)
    workspace_widgets_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    approval_overrides_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="settings")


class SwarmPreferences(Base):
    __tablename__ = "swarm_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, unique=True, index=True)
    optimization_mode: Mapped[str] = mapped_column(String(40), default="balanced", nullable=False)
    swarm_aggressiveness: Mapped[str] = mapped_column(String(30), default="medium", nullable=False)
    max_agents: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    require_approval_above_agent_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    allow_dynamic_spawning: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_dynamic_retirement: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    docs_depth: Mapped[str] = mapped_column(String(30), default="standard", nullable=False)
    testing_depth: Mapped[str] = mapped_column(String(30), default="standard", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="swarm_preferences")


class SwarmPlan(Base):
    __tablename__ = "swarm_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    milestone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_agent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_agent_count: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    coordination_risk: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    path_conflict_risk: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    expected_bottlenecks_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    validation_strategy_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    strategy_summary: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="swarm_plans")
    agent_specs: Mapped[list["SwarmAgentSpec"]] = relationship(back_populates="swarm_plan")


class SwarmAgentSpec(Base):
    __tablename__ = "swarm_agent_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    swarm_plan_id: Mapped[int] = mapped_column(ForeignKey("swarm_plans.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    archetype: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mission: Mapped[str] = mapped_column(Text, nullable=False)
    model_policy: Mapped[str] = mapped_column(Text, nullable=False)
    toolset_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_paths_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    forbidden_paths_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    spawn_phase: Mapped[str] = mapped_column(String(80), default="build_start", nullable=False)
    retire_when: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="planned", nullable=False)

    swarm_plan: Mapped[SwarmPlan] = relationship(back_populates="agent_specs")


class AgentArchetype(Base):
    __tablename__ = "agent_archetypes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    default_guidelines: Mapped[str] = mapped_column(Text, nullable=False)
    default_tools_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    default_permissions_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    spawn_triggers_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    retirement_triggers_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risk_profile: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)


class SwarmEvent(Base):
    __tablename__ = "swarm_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    swarm_plan_id: Mapped[int | None] = mapped_column(ForeignKey("swarm_plans.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    project: Mapped[Project] = relationship(back_populates="swarm_events")


class WidgetDefinition(Base):
    __tablename__ = "widget_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    widget_type: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(30), nullable=False)
    default_area: Mapped[str] = mapped_column(String(60), nullable=False)
    default_size: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    requires_project: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_tool: Mapped[str | None] = mapped_column(String(120), nullable=True)
    coming_soon: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)


class WidgetInstance(Base):
    __tablename__ = "widget_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    widget_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    area: Mapped[str] = mapped_column(String(60), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    size: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    collapsed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project | None] = relationship(back_populates="widget_instances")


class SwarmBudget(Base):
    __tablename__ = "swarm_budgets"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    max_agents: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    require_approval_above_agent_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    prefer_local_models: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    premium_models_only_for: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    current_active_agents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_intensity: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    dynamic_spawning_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="swarm_budget")


class AgentContract(Base):
    __tablename__ = "agent_contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(200), nullable=False)
    archetype: Mapped[str] = mapped_column(String(80), nullable=False)
    mission: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_paths_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    forbidden_paths_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_tools_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    validation_required_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    stop_conditions_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    escalation_conditions_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    completion_report_schema_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="agent_contracts")


class PathLock(Base):
    __tablename__ = "path_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    path_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    owner_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    owner_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="path_locks")


class DecisionRecord(Base):
    __tablename__ = "decision_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    decision_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    made_by: Mapped[str] = mapped_column(String(20), nullable=False)
    impact_area_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    related_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reversible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    superseded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    project: Mapped[Project] = relationship(back_populates="decision_records")


class ProjectConfidence(Base):
    __tablename__ = "project_confidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    unknowns_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="project_confidence")


class RecoveryPlan(Base):
    __tablename__ = "recovery_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(60), nullable=False)
    trigger_summary: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_actions_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    selected_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="recovery_plans")


class AgentStuckSignal(Base):
    __tablename__ = "agent_stuck_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(60), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="stuck_signals")


class ReviewGate(Base):
    __tablename__ = "review_gates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    gate_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    required_checks_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="review_gates")


class ModelPolicy(Base):
    __tablename__ = "model_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    policy_name: Mapped[str] = mapped_column(String(40), nullable=False)
    manager_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    coding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    docs_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    test_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    research_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    security_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fallback_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project | None] = relationship(back_populates="model_policies")


class ToolRoutingPolicy(Base):
    __tablename__ = "tool_routing_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    agent_archetype: Mapped[str] = mapped_column(String(80), nullable=False)
    allowed_tools_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    requires_approval_tools_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    blocked_tools_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="tool_routing_policies")


class SandboxProfile(Base):
    __tablename__ = "sandbox_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    network_policy: Mapped[str] = mapped_column(String(60), nullable=False)
    file_write_policy: Mapped[str] = mapped_column(String(60), nullable=False)
    command_approval_policy: Mapped[str] = mapped_column(String(60), nullable=False)
    external_tool_policy: Mapped[str] = mapped_column(String(60), nullable=False)
    deployment_policy: Mapped[str] = mapped_column(String(60), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ManagerAssumption(Base):
    __tablename__ = "manager_assumptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    assumption: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    impact_area_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="manager_assumptions")


class RepoIntelligenceSummary(Base):
    __tablename__ = "repo_intelligence_summaries"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    languages_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    frameworks_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    package_managers_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    entry_points_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    build_commands_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    test_commands_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    important_folders_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risky_files_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    docs_found_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    ci_config_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    deployment_config_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="repo_intelligence")


class ValidationRecipe(Base):
    __tablename__ = "validation_recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    steps_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="validation_recipes")


class HandoffQualityPreference(Base):
    __tablename__ = "handoff_quality_preferences"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    quality_level: Mapped[str] = mapped_column(String(40), default="developer_handoff", nullable=False)
    include_run_commands: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_known_limitations: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_artifacts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_tests: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_next_steps: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    project: Mapped[Project] = relationship(back_populates="handoff_quality_preference")


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(80), nullable=False)
    impact_estimate: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    related_tasks_json: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="change_requests")


class ManagerMessage(Base):
    __tablename__ = "manager_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    message_type: Mapped[str] = mapped_column(String(40), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    related_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    actions_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="manager_messages")


class ManagerQuestion(Base):
    __tablename__ = "manager_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    impact: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    selected_option_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    selected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_decide_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    related_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    project: Mapped[Project] = relationship(back_populates="manager_questions")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    request_type: Mapped[str] = mapped_column(String(30), nullable=False)
    requesting_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    reason_short: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    cwd: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    runner_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="approval_requests")


class ProjectEvent(Base):
    __tablename__ = "project_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="events")


class AppEvent(Base):
    __tablename__ = "app_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AppProfile(Base):
    __tablename__ = "app_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    display_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    install_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_provider_choice: Mapped[str] = mapped_column(String(40), default="codex", nullable=False)
    preferred_start_mode: Mapped[str] = mapped_column(String(40), default="new_project", nullable=False)
    selected_provider: Mapped[str] = mapped_column(String(40), default="codex", nullable=False)
    auth_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    connected_accounts_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    first_run_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    setup_version_completed: Mapped[str | None] = mapped_column(String(40), nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_runner_mode: Mapped[str] = mapped_column(String(30), default="auto", nullable=False)
    manager_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_worker_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manager_reasoning_effort: Mapped[str | None] = mapped_column(String(30), nullable=True)
    default_worker_reasoning_effort: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sandbox_mode: Mapped[str] = mapped_column(String(30), default="workspace-write", nullable=False)
    approval_policy: Mapped[str] = mapped_column(String(30), default="on-request", nullable=False)
    theme: Mapped[str] = mapped_column(String(20), default="system", nullable=False)
    startup_behavior: Mapped[str] = mapped_column(String(40), default="dashboard", nullable=False)
    notification_preferences_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    dashboard_widgets_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    dashboard_widget_preferences_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    tool_permission_overrides_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    provider_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    adapter_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    adapter_args_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    recent_startup_error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
