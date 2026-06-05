from __future__ import annotations

import atexit
import gc
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

TEST_ROOT = (Path(__file__).resolve().parents[1] / ".runtime-test-runs" / uuid.uuid4().hex).resolve()
os.environ["MISSION_CONTROL_APP_HOME"] = str(TEST_ROOT / "app-home")
os.environ["MISSION_CONTROL_RUNTIME_ROOT"] = str(TEST_ROOT)
os.environ["MISSION_CONTROL_LAUNCHER_DIR"] = str(TEST_ROOT / "launcher")


def _cleanup_test_root() -> None:
    gc.collect()
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


atexit.register(_cleanup_test_root)

_DB_STATE: tuple[Path, Any, Any, Any] | None = None
_APP: Any | None = None
_DB_TEMPLATE: Path | None = None


def _db_state() -> tuple[Path, Any, Any, Any]:
    global _DB_STATE
    if _DB_STATE is None:
        from config import DB_PATH
        from db import engine, init_db
        from startup import startup_service

        _DB_STATE = (DB_PATH, engine, init_db, startup_service)
    return _DB_STATE


def _app() -> Any:
    global _APP
    if _APP is None:
        from main import app

        _APP = app
    return _APP


def _blank_db_template() -> Path:
    global _DB_TEMPLATE
    if _DB_TEMPLATE is None:
        db_path, engine, init_db, _startup_service = _db_state()
        engine.dispose()
        if db_path.exists():
            db_path.unlink()
        init_db()
        engine.dispose()
        _DB_TEMPLATE = TEST_ROOT / "blank-test-db.sqlite3"
        shutil.copy2(db_path, _DB_TEMPLATE)
    return _DB_TEMPLATE


def _daemon_token() -> str:
    from daemon_state import ensure_daemon_token

    return ensure_daemon_token()


@pytest.fixture(autouse=True)
def reset_db(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("no_db_reset") is not None:
        return None
    db_path, engine, init_db, startup_service = _db_state()
    template_path = _blank_db_template()
    engine.dispose()
    if db_path.exists():
        last_error: Exception | None = None
        for _ in range(30):
            try:
                db_path.unlink()
                last_error = None
                break
            except FileNotFoundError:
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                gc.collect()
                engine.dispose()
                time.sleep(0.1)
        if last_error is not None:
            raise last_error
    shutil.copy2(template_path, db_path)
    startup_service.last_status = None
    engine.dispose()


@pytest.fixture
def client() -> TestClient:
    with TestClient(_app()) as test_client:
        test_client.headers.update({"X-Mission-Control-Token": _daemon_token()})
        yield test_client


@pytest.fixture
def bridge_headers() -> dict[str, str]:
    return {"X-Mission-Control-Token": _daemon_token()}


def pytest_sessionfinish(session, exitstatus) -> None:  # type: ignore[no-untyped-def]
    if _DB_STATE is not None:
        _db_state()[1].dispose()
    gc.collect()
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


def wait_for(condition, timeout: float = 6.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        if condition():
            return
        time.sleep(0.2)
    raise AssertionError("Condition was not satisfied before timeout.")


def sample_workspace(name: str) -> str:
    return (TEST_ROOT / "workspaces" / name).as_posix()


def seed_imported_codebase_records(
    db,
    project,
    *,
    indexed_areas: list[str] | None = None,
    unindexed_areas: list[str] | None = None,
    scan_depth: str = "standard",
):
    from models import AgentInstructionsStatus, CodebaseMap, CodebaseUnderstanding, ImportedCodebaseSafety, utc_now

    source_path = project.source_path or project.workspace_path
    important_folders = sorted({item for item in (indexed_areas or ["src", "tests"]) if item})
    codebase_map = db.get(CodebaseMap, project.id)
    if codebase_map is None:
        codebase_map = CodebaseMap(
            project_id=project.id,
            source_path=source_path,
        )
        db.add(codebase_map)
    codebase_map.source_path = source_path
    codebase_map.languages_json = ["python"]
    codebase_map.frameworks_json = ["fastapi"] if (Path(source_path) / "apps").exists() else []
    codebase_map.package_managers_json = ["pip"]
    codebase_map.build_tools_json = []
    codebase_map.test_frameworks_json = ["pytest"]
    codebase_map.entry_points_json = ["src/main.py"] if "src" in important_folders else []
    codebase_map.build_commands_json = []
    codebase_map.test_commands_json = ["python -m pytest"]
    codebase_map.important_folders_json = important_folders
    codebase_map.docs_json = ["README.md"] if (Path(source_path) / "README.md").exists() else []
    codebase_map.agent_instructions_json = []
    codebase_map.config_files_json = []
    codebase_map.ci_config_json = []
    codebase_map.deployment_config_json = []
    codebase_map.git_status_json = {
        "is_git_repo": False,
        "dirty_working_tree": False,
        "dirty_working_tree_known": True,
        "command_required_for_dirty_check": False,
    }
    codebase_map.risk_flags_json = []
    codebase_map.scan_depth = scan_depth
    codebase_map.codebase_size = "small"
    codebase_map.recommended_scan_strategy = "standard_complete"
    codebase_map.indexed_areas_json = list(indexed_areas or important_folders)
    codebase_map.unindexed_areas_json = list(unindexed_areas or [])
    codebase_map.updated_at = utc_now()

    understanding = db.get(CodebaseUnderstanding, project.id)
    if understanding is None:
        understanding = CodebaseUnderstanding(project_id=project.id)
        db.add(understanding)
    understanding.summary = f"Imported codebase at {source_path}."
    understanding.architecture_summary = "Fast test stub for imported codebase understanding."
    understanding.detected_stack_json = ["python"]
    understanding.likely_run_instructions_json = []
    understanding.likely_test_instructions_json = ["python -m pytest"]
    understanding.risk_summary = "No major risks detected by the fast test stub."
    understanding.missing_context_json = []
    understanding.suggested_next_steps_json = ["Inspect the failing tests before editing code."]
    understanding.recommended_interview_mode = "skip"
    understanding.confidence_by_area_json = {"repo_map": 0.75}
    understanding.generation_mode = "deterministic_scanner"
    understanding.updated_at = utc_now()

    agents_status = db.get(AgentInstructionsStatus, project.id)
    if agents_status is None:
        agents_status = AgentInstructionsStatus(project_id=project.id)
        db.add(agents_status)
    agents_status.has_agents_md = False
    agents_status.agents_md_path = None
    agents_status.summary = "No AGENTS.md file detected."
    agents_status.recommended_action = "none"
    agents_status.updated_at = utc_now()

    safety = db.get(ImportedCodebaseSafety, project.id)
    if safety is None:
        safety = ImportedCodebaseSafety(project_id=project.id)
        db.add(safety)
    safety.read_only_scan_completed = True
    safety.write_permission_status = "read_only"
    safety.updated_at = utc_now()

    project.scan_status = "completed"
    project.status = "import_review"
    project.last_indexed_at = utc_now()
    project.write_permission_status = "read_only"
    db.flush()
    return codebase_map, understanding, agents_status, safety


def seed_waiting_dry_run_approval(orchestration_id: int, *, command: str = "python -m pytest") -> None:
    from db import SessionLocal
    from manager import service as manager_service
    from models import Project
    from orchestration import coordinator

    db = SessionLocal()
    try:
        session = coordinator.get_session(db, orchestration_id)
        project = db.get(Project, session.project_id)
        assert project is not None
        manager_service._create_approval(
            db,
            project,
            request_type="command",
            title="Approve simulated dry-run test command",
            reason_short="Run a simulated local test command so Mission Control can continue the bridge flow safely.",
            risk_level="medium",
            cwd=project.workspace_path,
            request_payload_json={"command": command, "scope": ["tests/"], "simulated": True},
        )
        coordinator.sync_pending_decisions(db, session)
        coordinator._update_session_status(
            db,
            session,
            status="waiting_for_user",
            manager_status="Waiting for dry-run command approval.",
        )
        coordinator._record_event(db, session, "background_turn_waiting_for_user", {"reason": "fast_test_stub"})
        db.commit()
    finally:
        db.close()

