from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import DEFAULT_DB_URL, ensure_runtime_dirs


ensure_runtime_dirs()

Base = declarative_base()
engine = create_engine(
    DEFAULT_DB_URL,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


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
    if "projects" in tables:
        _ensure_column("projects", "manager_mode", "manager_mode VARCHAR(30) NOT NULL DEFAULT 'auto'")
        _ensure_column("projects", "docs_path", "docs_path TEXT")
        _ensure_column("projects", "final_report_json", "final_report_json JSON")
    if "agents" in tables:
        _ensure_column("agents", "kind", "kind VARCHAR(30) NOT NULL DEFAULT 'worker'")
        _ensure_column("agents", "session_ref", "session_ref VARCHAR(120)")
        _ensure_column("agents", "locked_paths_json", "locked_paths_json JSON")
        _ensure_column("agents", "failure_count", "failure_count INTEGER NOT NULL DEFAULT 0")
        _ensure_column("agents", "last_report_summary", "last_report_summary TEXT")
        _ensure_column("agents", "active_model", "active_model VARCHAR(120)")
        _ensure_column("agents", "active_reasoning_effort", "active_reasoning_effort VARCHAR(30)")
        _ensure_column("agents", "active_runner_type", "active_runner_type VARCHAR(50)")
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
