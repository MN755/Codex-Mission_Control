from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_ROOT = (Path(__file__).resolve().parents[1] / ".runtime-test").resolve()
os.environ.setdefault("MISSION_CONTROL_APP_HOME", str(TEST_ROOT / "app-home"))
os.environ.setdefault("MISSION_CONTROL_RUNTIME_ROOT", str(TEST_ROOT))
os.environ.setdefault("MISSION_CONTROL_LAUNCHER_DIR", str(TEST_ROOT / "launcher"))

from db import Base, engine, init_db
from main import app
from startup import startup_service


@pytest.fixture(autouse=True)
def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()
    startup_service.last_status = None


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def wait_for(condition, timeout: float = 6.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        if condition():
            return
        time.sleep(0.2)
    raise AssertionError("Condition was not satisfied before timeout.")


def sample_workspace(name: str) -> str:
    return (TEST_ROOT / "workspaces" / name).as_posix()

