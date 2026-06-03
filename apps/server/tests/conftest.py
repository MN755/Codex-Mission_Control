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

