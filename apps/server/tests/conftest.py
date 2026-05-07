from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from db import Base, engine, init_db
from main import app


@pytest.fixture(autouse=True)
def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()


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

