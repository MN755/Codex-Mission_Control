from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import DEFAULT_DB_URL, ensure_runtime_dirs


ensure_runtime_dirs()

Base = declarative_base()
SQLITE_DEFAULT_BUSY_TIMEOUT_MS = 5_000
engine = create_engine(
    DEFAULT_DB_URL,
    connect_args={"check_same_thread": False, "timeout": SQLITE_DEFAULT_BUSY_TIMEOUT_MS / 1000},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_DEFAULT_BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _ensure_column(table_name: str, column_name: str, sql: str) -> None:
    inspector = inspect(engine)
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in existing:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {sql}"))


def _apply_sqlite_migrations() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "interview_questions" in tables and "interview_sessions" in tables:
            columns = {column["name"] for column in inspector.get_columns("interview_questions")}
            if "project_id" in columns:
                connection.execute(
                    text(
                        """
                        UPDATE interview_questions
                        SET project_id = (
                            SELECT interview_sessions.project_id
                            FROM interview_sessions
                            WHERE interview_sessions.id = interview_questions.session_id
                        )
                        WHERE project_id IS NULL
                        """
                    )
                )
    if "projects" in tables:
        _ensure_column("projects", "slug", "slug VARCHAR(220)")
        _ensure_column("projects", "manager_mode", "manager_mode VARCHAR(30) NOT NULL DEFAULT 'auto'")
        _ensure_column("projects", "created_by", "created_by VARCHAR(50)")
        _ensure_column("projects", "docs_path", "docs_path TEXT")
        _ensure_column("projects", "final_report_json", "final_report_json JSON")
        _ensure_column("projects", "pinned", "pinned BOOLEAN NOT NULL DEFAULT 0")
        _ensure_column("projects", "archived_at", "archived_at DATETIME")
        _ensure_column("projects", "last_opened_at", "last_opened_at DATETIME")
        _ensure_column("projects", "latest_milestone", "latest_milestone VARCHAR(160)")
        _ensure_column("projects", "latest_activity", "latest_activity TEXT")
        _ensure_column("projects", "handoff_status", "handoff_status VARCHAR(60)")
        _ensure_column("projects", "source_type", "source_type VARCHAR(40) NOT NULL DEFAULT 'idea'")
        _ensure_column("projects", "source_path", "source_path TEXT")
        _ensure_column("projects", "import_mode", "import_mode VARCHAR(30)")
        _ensure_column("projects", "imported_at", "imported_at DATETIME")
        _ensure_column("projects", "scan_status", "scan_status VARCHAR(30) NOT NULL DEFAULT 'not_started'")
        _ensure_column("projects", "last_indexed_at", "last_indexed_at DATETIME")
        _ensure_column("projects", "write_permission_status", "write_permission_status VARCHAR(30) NOT NULL DEFAULT 'write_allowed'")
    if "agents" in tables:
        _ensure_column("agents", "kind", "kind VARCHAR(30) NOT NULL DEFAULT 'worker'")
        _ensure_column("agents", "session_ref", "session_ref VARCHAR(120)")
        _ensure_column("agents", "swarm_plan_id", "swarm_plan_id INTEGER")
        _ensure_column("agents", "archetype", "archetype VARCHAR(80)")
        _ensure_column("agents", "mission", "mission TEXT")
        _ensure_column("agents", "retire_when", "retire_when TEXT")
        _ensure_column("agents", "locked_paths_json", "locked_paths_json JSON")
        _ensure_column("agents", "failure_count", "failure_count INTEGER NOT NULL DEFAULT 0")
        _ensure_column("agents", "last_report_summary", "last_report_summary TEXT")
        _ensure_column("agents", "active_model", "active_model VARCHAR(120)")
        _ensure_column("agents", "active_reasoning_effort", "active_reasoning_effort VARCHAR(30)")
        _ensure_column("agents", "active_runner_type", "active_runner_type VARCHAR(50)")
        _ensure_column("agents", "active_usage_json", "active_usage_json JSON")
        _ensure_column("agents", "current_action", "current_action TEXT")
    if "tasks" in tables:
        _ensure_column("tasks", "agent_role", "agent_role VARCHAR(120)")
        _ensure_column("tasks", "milestone", "milestone VARCHAR(120)")
        _ensure_column("tasks", "success_criteria_json", "success_criteria_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("tasks", "estimated_complexity", "estimated_complexity VARCHAR(20) NOT NULL DEFAULT 'medium'")
        _ensure_column("tasks", "dependencies_json", "dependencies_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("tasks", "failure_count", "failure_count INTEGER NOT NULL DEFAULT 0")
        _ensure_column("tasks", "waiting_reason", "waiting_reason TEXT")
    if "agent_runs" in tables:
        _ensure_column("agent_runs", "stdout_path", "stdout_path TEXT")
        _ensure_column("agent_runs", "stderr_path", "stderr_path TEXT")
        _ensure_column("agent_runs", "event_log_path", "event_log_path TEXT")
        _ensure_column("agent_runs", "exit_code", "exit_code INTEGER")
        _ensure_column("agent_runs", "manager_action", "manager_action VARCHAR(80)")
        _ensure_column("agent_runs", "effective_settings_json", "effective_settings_json JSON")
        _ensure_column("agent_runs", "usage_json", "usage_json JSON")
        _ensure_column("agent_runs", "result_envelope_json", "result_envelope_json JSON")
        _ensure_column("agent_runs", "failure_classification", "failure_classification VARCHAR(40)")
    if "project_settings" in tables:
        _ensure_column("project_settings", "provider", "provider VARCHAR(40) NOT NULL DEFAULT 'codex'")
        _ensure_column("project_settings", "provider_endpoint", "provider_endpoint TEXT")
        _ensure_column("project_settings", "adapter_command", "adapter_command TEXT")
        _ensure_column("project_settings", "adapter_args_json", "adapter_args_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("project_settings", "remote_execution_policy_json", "remote_execution_policy_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("project_settings", "launch_guard_enabled", "launch_guard_enabled BOOLEAN NOT NULL DEFAULT 1")
        _ensure_column("project_settings", "hard_total_token_budget", "hard_total_token_budget INTEGER NOT NULL DEFAULT 2500000")
        _ensure_column("project_settings", "hard_total_worker_launch_budget", "hard_total_worker_launch_budget INTEGER NOT NULL DEFAULT 120")
        _ensure_column("project_settings", "hard_peak_context_budget", "hard_peak_context_budget INTEGER NOT NULL DEFAULT 400000")
        _ensure_column("project_settings", "quota_backoff_cooldown_minutes", "quota_backoff_cooldown_minutes INTEGER NOT NULL DEFAULT 60")
        _ensure_column("project_settings", "workspace_widgets_json", "workspace_widgets_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("project_settings", "approval_overrides_json", "approval_overrides_json JSON NOT NULL DEFAULT '{}'")
    if "swarm_preferences" in tables:
        _ensure_column("swarm_preferences", "optimization_mode", "optimization_mode VARCHAR(40) NOT NULL DEFAULT 'balanced'")
        _ensure_column("swarm_preferences", "swarm_aggressiveness", "swarm_aggressiveness VARCHAR(30) NOT NULL DEFAULT 'medium'")
        _ensure_column("swarm_preferences", "max_agents", "max_agents INTEGER NOT NULL DEFAULT 8")
        _ensure_column("swarm_preferences", "require_approval_above_agent_count", "require_approval_above_agent_count INTEGER NOT NULL DEFAULT 10")
        _ensure_column("swarm_preferences", "allow_dynamic_spawning", "allow_dynamic_spawning BOOLEAN NOT NULL DEFAULT 1")
        _ensure_column("swarm_preferences", "allow_dynamic_retirement", "allow_dynamic_retirement BOOLEAN NOT NULL DEFAULT 1")
        _ensure_column("swarm_preferences", "docs_depth", "docs_depth VARCHAR(30) NOT NULL DEFAULT 'standard'")
        _ensure_column("swarm_preferences", "testing_depth", "testing_depth VARCHAR(30) NOT NULL DEFAULT 'standard'")
    if "swarm_plans" in tables:
        _ensure_column("swarm_plans", "milestone_id", "milestone_id INTEGER")
        _ensure_column("swarm_plans", "mode", "mode VARCHAR(40) NOT NULL DEFAULT 'balanced'")
        _ensure_column("swarm_plans", "goal", "goal TEXT NOT NULL DEFAULT ''")
        _ensure_column("swarm_plans", "recommended_agent_count", "recommended_agent_count INTEGER NOT NULL DEFAULT 0")
        _ensure_column("swarm_plans", "max_agent_count", "max_agent_count INTEGER NOT NULL DEFAULT 8")
        _ensure_column("swarm_plans", "coordination_risk", "coordination_risk VARCHAR(20) NOT NULL DEFAULT 'medium'")
        _ensure_column("swarm_plans", "path_conflict_risk", "path_conflict_risk VARCHAR(20) NOT NULL DEFAULT 'medium'")
        _ensure_column("swarm_plans", "expected_bottlenecks_json", "expected_bottlenecks_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("swarm_plans", "validation_strategy_json", "validation_strategy_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("swarm_plans", "strategy_summary", "strategy_summary TEXT NOT NULL DEFAULT ''")
        _ensure_column("swarm_plans", "approved_by_user", "approved_by_user BOOLEAN NOT NULL DEFAULT 0")
        _ensure_column("swarm_plans", "status", "status VARCHAR(30) NOT NULL DEFAULT 'pending_approval'")
    if "swarm_agent_specs" in tables:
        _ensure_column("swarm_agent_specs", "project_id", "project_id INTEGER")
        _ensure_column("swarm_agent_specs", "archetype", "archetype VARCHAR(80) NOT NULL DEFAULT 'feature'")
        _ensure_column("swarm_agent_specs", "name", "name VARCHAR(200) NOT NULL DEFAULT 'Worker Agent'")
        _ensure_column("swarm_agent_specs", "mission", "mission TEXT NOT NULL DEFAULT ''")
        _ensure_column("swarm_agent_specs", "model_policy", "model_policy TEXT NOT NULL DEFAULT ''")
        _ensure_column("swarm_agent_specs", "toolset_json", "toolset_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("swarm_agent_specs", "allowed_paths_json", "allowed_paths_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("swarm_agent_specs", "forbidden_paths_json", "forbidden_paths_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("swarm_agent_specs", "spawn_phase", "spawn_phase VARCHAR(80) NOT NULL DEFAULT 'build_start'")
        _ensure_column("swarm_agent_specs", "retire_when", "retire_when TEXT NOT NULL DEFAULT ''")
        _ensure_column("swarm_agent_specs", "priority", "priority INTEGER NOT NULL DEFAULT 50")
        _ensure_column("swarm_agent_specs", "iteration_budget", "iteration_budget INTEGER NOT NULL DEFAULT 1")
        _ensure_column("swarm_agent_specs", "status", "status VARCHAR(30) NOT NULL DEFAULT 'planned'")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE swarm_agent_specs
                    SET project_id = (
                        SELECT swarm_plans.project_id
                        FROM swarm_plans
                        WHERE swarm_plans.id = swarm_agent_specs.swarm_plan_id
                    )
                    WHERE project_id IS NULL
                    """
                )
            )
    if "agent_archetypes" in tables:
        _ensure_column("agent_archetypes", "purpose", "purpose TEXT NOT NULL DEFAULT ''")
        _ensure_column("agent_archetypes", "default_guidelines", "default_guidelines TEXT NOT NULL DEFAULT ''")
        _ensure_column("agent_archetypes", "default_tools_json", "default_tools_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("agent_archetypes", "default_permissions_json", "default_permissions_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("agent_archetypes", "spawn_triggers_json", "spawn_triggers_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("agent_archetypes", "retirement_triggers_json", "retirement_triggers_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("agent_archetypes", "risk_profile", "risk_profile VARCHAR(20) NOT NULL DEFAULT 'medium'")
    if "swarm_events" in tables:
        _ensure_column("swarm_events", "swarm_plan_id", "swarm_plan_id INTEGER")
        _ensure_column("swarm_events", "message", "message TEXT NOT NULL DEFAULT ''")
        _ensure_column("swarm_events", "agent_id", "agent_id INTEGER")
        _ensure_column("swarm_events", "metadata_json", "metadata_json JSON NOT NULL DEFAULT '{}'")
    if "swarm_budgets" in tables:
        _ensure_column("swarm_budgets", "launch_guard_enabled", "launch_guard_enabled BOOLEAN NOT NULL DEFAULT 1")
        _ensure_column("swarm_budgets", "launch_guard_status", "launch_guard_status VARCHAR(40) NOT NULL DEFAULT 'ok'")
        _ensure_column("swarm_budgets", "launch_guard_reason", "launch_guard_reason TEXT")
        _ensure_column("swarm_budgets", "hard_total_token_budget", "hard_total_token_budget INTEGER NOT NULL DEFAULT 2500000")
        _ensure_column("swarm_budgets", "observed_total_tokens", "observed_total_tokens INTEGER NOT NULL DEFAULT 0")
        _ensure_column("swarm_budgets", "hard_total_worker_launch_budget", "hard_total_worker_launch_budget INTEGER NOT NULL DEFAULT 120")
        _ensure_column("swarm_budgets", "launches_started", "launches_started INTEGER NOT NULL DEFAULT 0")
        _ensure_column("swarm_budgets", "hard_peak_context_budget", "hard_peak_context_budget INTEGER NOT NULL DEFAULT 400000")
        _ensure_column("swarm_budgets", "observed_peak_context_tokens", "observed_peak_context_tokens INTEGER NOT NULL DEFAULT 0")
        _ensure_column("swarm_budgets", "quota_backoff_active", "quota_backoff_active BOOLEAN NOT NULL DEFAULT 0")
    if "interview_sessions" in tables:
        _ensure_column("interview_sessions", "question_budget", "question_budget INTEGER NOT NULL DEFAULT 20")
        _ensure_column("interview_sessions", "questions_asked", "questions_asked INTEGER NOT NULL DEFAULT 0")
        _ensure_column("interview_sessions", "manager_mode", "manager_mode VARCHAR(30) NOT NULL DEFAULT 'auto'")
        _ensure_column("interview_sessions", "stopped_early", "stopped_early BOOLEAN NOT NULL DEFAULT 0")
        _ensure_column("interview_sessions", "stop_reason", "stop_reason TEXT")
        _ensure_column("interview_sessions", "confidence_json", "confidence_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("interview_sessions", "known_facts_json", "known_facts_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("interview_sessions", "unknowns_json", "unknowns_json JSON NOT NULL DEFAULT '{}'")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE interview_sessions
                    SET question_budget = COALESCE(question_budget, question_count, 20),
                        questions_asked = COALESCE(questions_asked, 0),
                        manager_mode = COALESCE(manager_mode, 'auto'),
                        stopped_early = COALESCE(stopped_early, 0),
                        confidence_json = COALESCE(confidence_json, '{}'),
                        known_facts_json = COALESCE(known_facts_json, '{}'),
                        unknowns_json = COALESCE(unknowns_json, '{}')
                    """
                )
            )
    if "interview_questions" in tables:
        _ensure_column("interview_questions", "project_id", "project_id INTEGER")
        _ensure_column("interview_questions", "why", "why TEXT")
        _ensure_column("interview_questions", "category", "category VARCHAR(80)")
        _ensure_column("interview_questions", "impact", "impact VARCHAR(20) NOT NULL DEFAULT 'medium'")
        _ensure_column("interview_questions", "allow_custom_answer", "allow_custom_answer BOOLEAN NOT NULL DEFAULT 0")
        _ensure_column("interview_questions", "selected_option_id", "selected_option_id VARCHAR(200)")
        _ensure_column("interview_questions", "custom_answer", "custom_answer TEXT")
        _ensure_column("interview_questions", "affects_json", "affects_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("interview_questions", "status", "status VARCHAR(20) NOT NULL DEFAULT 'pending'")
        _ensure_column("interview_questions", "question_source", "question_source VARCHAR(40) NOT NULL DEFAULT 'fallback_generated'")
        _ensure_column("interview_questions", "created_at", "created_at DATETIME")
        _ensure_column("interview_questions", "answered_at", "answered_at DATETIME")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE interview_questions
                    SET project_id = (
                            SELECT interview_sessions.project_id
                            FROM interview_sessions
                            WHERE interview_sessions.id = interview_questions.session_id
                        )
                    WHERE project_id IS NULL
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE interview_questions
                    SET selected_option_id = COALESCE(selected_option_id, selected_option),
                        impact = COALESCE(impact, 'medium'),
                        allow_custom_answer = COALESCE(allow_custom_answer, 0),
                        affects_json = COALESCE(affects_json, '[]'),
                        status = CASE
                            WHEN COALESCE(selected_option_id, selected_option) IS NOT NULL THEN 'answered'
                            ELSE COALESCE(status, 'pending')
                        END,
                        question_source = COALESCE(question_source, 'fallback_generated')
                    """
                )
            )
    if "recovery_plans" in tables:
        _ensure_column("recovery_plans", "related_agent_id", "related_agent_id INTEGER")
        _ensure_column("recovery_plans", "related_task_id", "related_task_id INTEGER")
    if "review_gates" in tables:
        _ensure_column("review_gates", "related_agent_id", "related_agent_id INTEGER")
        _ensure_column("review_gates", "evidence_ids_json", "evidence_ids_json JSON NOT NULL DEFAULT '[]'")
    if "change_requests" in tables:
        _ensure_column("change_requests", "related_handoff_id", "related_handoff_id INTEGER")
    if "app_profile" in tables:
        _ensure_column("app_profile", "install_id", "install_id VARCHAR(64)")
        _ensure_column("app_profile", "display_name", "display_name VARCHAR(50)")
        _ensure_column("app_profile", "preferred_provider_choice", "preferred_provider_choice VARCHAR(40) NOT NULL DEFAULT 'codex'")
        _ensure_column("app_profile", "preferred_start_mode", "preferred_start_mode VARCHAR(40) NOT NULL DEFAULT 'new_project'")
        _ensure_column("app_profile", "selected_provider", "selected_provider VARCHAR(40) NOT NULL DEFAULT 'codex'")
        _ensure_column("app_profile", "auth_mode", "auth_mode VARCHAR(40)")
        _ensure_column("app_profile", "connected_accounts_json", "connected_accounts_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("app_profile", "integration_registry_json", "integration_registry_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("app_profile", "first_run_completed", "first_run_completed BOOLEAN NOT NULL DEFAULT 0")
        _ensure_column("app_profile", "setup_version_completed", "setup_version_completed VARCHAR(40)")
        _ensure_column("app_profile", "onboarding_completed", "onboarding_completed BOOLEAN NOT NULL DEFAULT 0")
        _ensure_column("app_profile", "default_runner_mode", "default_runner_mode VARCHAR(30) NOT NULL DEFAULT 'auto'")
        _ensure_column("app_profile", "manager_model", "manager_model VARCHAR(120)")
        _ensure_column("app_profile", "default_worker_model", "default_worker_model VARCHAR(120)")
        _ensure_column("app_profile", "manager_reasoning_effort", "manager_reasoning_effort VARCHAR(30)")
        _ensure_column("app_profile", "default_worker_reasoning_effort", "default_worker_reasoning_effort VARCHAR(30)")
        _ensure_column("app_profile", "sandbox_mode", "sandbox_mode VARCHAR(30) NOT NULL DEFAULT 'workspace-write'")
        _ensure_column("app_profile", "approval_policy", "approval_policy VARCHAR(30) NOT NULL DEFAULT 'on-request'")
        _ensure_column("app_profile", "theme", "theme VARCHAR(20) NOT NULL DEFAULT 'system'")
        _ensure_column("app_profile", "startup_behavior", "startup_behavior VARCHAR(40) NOT NULL DEFAULT 'dashboard'")
        _ensure_column("app_profile", "notification_preferences_json", "notification_preferences_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("app_profile", "dashboard_widgets_json", "dashboard_widgets_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("app_profile", "dashboard_widget_preferences_json", "dashboard_widget_preferences_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("app_profile", "tool_permission_overrides_json", "tool_permission_overrides_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("app_profile", "provider_endpoint", "provider_endpoint TEXT")
        _ensure_column("app_profile", "adapter_command", "adapter_command TEXT")
        _ensure_column("app_profile", "adapter_args_json", "adapter_args_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("app_profile", "remote_execution_registry_json", "remote_execution_registry_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("app_profile", "recent_startup_error_json", "recent_startup_error_json JSON")
        _ensure_column("app_profile", "last_opened_at", "last_opened_at DATETIME")
    if "orchestration_sessions" in tables:
        _ensure_column("orchestration_sessions", "mode", "mode VARCHAR(30) NOT NULL DEFAULT 'unknown'")
    if "agent_execution_traces" in tables:
        _ensure_column("agent_execution_traces", "trace_id", "trace_id VARCHAR(120) NOT NULL DEFAULT ''")
        _ensure_column("agent_execution_traces", "span_id", "span_id VARCHAR(120) NOT NULL DEFAULT ''")
        _ensure_column("agent_execution_traces", "parent_span_id", "parent_span_id VARCHAR(120)")
        _ensure_column("agent_execution_traces", "span_kind", "span_kind VARCHAR(60) NOT NULL DEFAULT 'run'")
        _ensure_column("agent_execution_traces", "attempt_number", "attempt_number INTEGER NOT NULL DEFAULT 1")
        _ensure_column("agent_execution_traces", "outcome", "outcome VARCHAR(40) NOT NULL DEFAULT 'unknown'")
        _ensure_column("agent_execution_traces", "failure_classification", "failure_classification VARCHAR(40)")
        _ensure_column("agent_execution_traces", "evidence_ids_json", "evidence_ids_json JSON NOT NULL DEFAULT '[]'")
        _ensure_column("agent_execution_traces", "metadata_json", "metadata_json JSON NOT NULL DEFAULT '{}'")
        _ensure_column("agent_execution_traces", "started_at", "started_at DATETIME")
        _ensure_column("agent_execution_traces", "finished_at", "finished_at DATETIME")


def init_db() -> None:
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_sqlite_migrations()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    with session_scope() as session:
        yield session
