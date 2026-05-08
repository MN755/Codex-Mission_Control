from __future__ import annotations

from datetime import datetime, timezone

from codex_auth import auth_service
from manager import service


def _job_payload(method: str = "chatgpt") -> dict:
    return {
        "id": "auth-test",
        "method": method,
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "finished_at": None,
        "exit_code": None,
        "message": "Waiting for auth",
        "auth_mode_after": None,
        "log_path": "C:/tmp/auth.log",
        "output_lines": ["Waiting for auth"],
    }


def test_auth_state_endpoint_uses_service_payload(monkeypatch, client) -> None:
    monkeypatch.setattr(
        service,
        "auth_state",
        lambda: {
            "authenticated": False,
            "auth_mode": None,
            "login_status": "Not logged in",
            "cli_detected": True,
            "provider": "codex",
            "current_job": None,
            "chatgpt_supported": True,
            "device_auth_supported": True,
            "api_key_supported": True,
            "provider_statuses": [],
            "notes": ["Test note"],
        },
    )
    response = client.get("/api/system/auth-state")
    assert response.status_code == 200
    assert response.json()["notes"] == ["Test note"]


def test_chatgpt_login_endpoint_starts_auth_job(monkeypatch, client) -> None:
    class DummyJob:
        pass

    async def fake_start_chatgpt_login(*, device_auth: bool = False):
        assert device_auth is False
        return DummyJob()

    monkeypatch.setattr(auth_service, "start_chatgpt_login", fake_start_chatgpt_login)
    monkeypatch.setattr(auth_service, "job_payload", lambda _job: _job_payload("chatgpt"))
    response = client.post("/api/system/auth/login/chatgpt", json={"device_auth": False})
    assert response.status_code == 200
    assert response.json()["method"] == "chatgpt"


def test_api_key_login_endpoint_starts_auth_job(monkeypatch, client) -> None:
    class DummyJob:
        pass

    async def fake_start_api_key_login(api_key: str):
        assert api_key == "sk-test"
        return DummyJob()

    monkeypatch.setattr(auth_service, "start_api_key_login", fake_start_api_key_login)
    monkeypatch.setattr(auth_service, "job_payload", lambda _job: _job_payload("api_key"))
    response = client.post("/api/system/auth/login/api-key", json={"api_key": "sk-test"})
    assert response.status_code == 200
    assert response.json()["method"] == "api_key"
