from __future__ import annotations

import asyncio

from daemon_state import ensure_daemon_token


def test_plugin_health_ready(monkeypatch) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Logged in using ChatGPT",
            "auth_mode": "chatgpt",
            "authenticated": True,
            "auth_status_detectable": True,
            "mcp_servers": [{"name": "mission-control", "status": "connected"}],
            "local_skills": [
                "mission-control-orchestrate",
                "mission-control-import-codebase",
                "mission-control-review-handoff",
            ],
        },
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon"})
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr("plugin_health._probe_url", lambda url, timeout=2.0: (True, "HTTP 200"))
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    assert payload["status"] == "ready"
    assert not any(check["status"] == "broken" and check["critical"] for check in payload["checks"])
    assert any(check["key"] == "mission_control_daemon_reachable" and check["status"] == "ready" for check in payload["checks"])
    assert any(check["key"] == "mcp_server_reachable" and check["status"] == "ready" for check in payload["checks"])
    assert "## Plugin Health Doctor" in payload["codex_chat_markdown"]


def test_plugin_health_degraded_when_noncritical_checks_warn(monkeypatch) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Unavailable",
            "auth_mode": None,
            "authenticated": False,
            "auth_status_detectable": True,
            "mcp_servers": [{"name": "mission-control", "status": "connected"}],
            "local_skills": [],
        },
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon"})
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr(
        "plugin_health._probe_url",
        lambda url, timeout=2.0: (False, "URLError") if url.endswith("/dashboard") else (True, "HTTP 200"),
    )
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    assert payload["status"] == "degraded"
    assert any(check["key"] == "dashboard_optional_status" and check["status"] == "unknown" for check in payload["checks"])
    assert any(check["key"] == "codex_login_status_detectable" and check["status"] == "degraded" for check in payload["checks"])
    assert "dashboard reachability is optional" in payload["codex_chat_markdown"].lower()


def test_plugin_health_broken_when_critical_checks_fail(monkeypatch, client) -> None:
    ensure_daemon_token()

    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": False,
            "cli_version": None,
            "login_status": "Unavailable",
            "auth_mode": None,
            "authenticated": False,
            "auth_status_detectable": True,
            "mcp_servers": [],
            "local_skills": [],
        },
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "web"})
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr("plugin_health._probe_url", lambda url, timeout=2.0: (False, "URLError"))
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    assert payload["status"] == "broken"
    assert any(check["key"] == "mcp_server_reachable" and check["status"] == "broken" for check in payload["checks"])
    assert any(check["key"] == "codex_cli_detected" and check["status"] == "broken" for check in payload["checks"])
    assert payload["safe_troubleshooting_commands"]

    response = client.get("/api/plugin/health")
    assert response.status_code == 200
    assert response.json()["status"] == "broken"
