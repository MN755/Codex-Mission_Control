from __future__ import annotations

import atexit
import gc
import os
import shutil
import time
import uuid
from pathlib import Path

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

from config import DB_PATH
from daemon_state import ensure_daemon_token
from db import Base, engine, init_db
from main import app
from startup import startup_service


@pytest.fixture(autouse=True)
def reset_db() -> None:
    engine.dispose()
    if DB_PATH.exists():
        last_error: Exception | None = None
        for _ in range(30):
            try:
                DB_PATH.unlink()
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
    init_db()
    startup_service.last_status = None
    engine.dispose()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def bridge_headers() -> dict[str, str]:
    return {"X-Mission-Control-Token": ensure_daemon_token()}


def pytest_sessionfinish(session, exitstatus) -> None:  # type: ignore[no-untyped-def]
    engine.dispose()
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

