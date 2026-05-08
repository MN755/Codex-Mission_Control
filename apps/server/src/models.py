from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    idea: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    runner_mode: Mapped[str] = mapped_column(String(30), default="auto", nullable=False)
    manager_mode: Mapped[str] = mapped_column(String(30), default="auto", nullable=False)
    docs_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    interview_sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="project")
    plans: Mapped[list["Plan"]] = relationship(back_populates="project")
    agents: Mapped[list["Agent"]] = relationship(back_populates="project")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")
    events: Mapped[list["ProjectEvent"]] = relationship(back_populates="project")
    reservations: Mapped[list["PathReservation"]] = relationship(back_populates="project")
    settings: Mapped["ProjectSettings | None"] = relationship(back_populates="project", uselist=False)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    current_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="in_progress", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="interview_sessions")
    questions: Mapped[list["InterviewQuestion"]] = relationship(back_populates="session")


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    selected_option: Mapped[str | None] = mapped_column(String(200), nullable=True)
    selected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[InterviewSession] = relationship(back_populates="questions")


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
    current_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
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
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="settings")


class ProjectEvent(Base):
    __tablename__ = "project_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="events")
