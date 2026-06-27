from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

import diagnostics
from db import SessionLocal
from models import AppProfile
from startup import startup_service


@pytest.fixture(autouse=True)
def _fast_startup_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(
        "startup.detect_codex_status",
        lambda: {
            "provider": "codex",
            "label": "Codex",
            "cli_detected": True,
            "cli_path": "codex",
            "cli_path_exists": True,
            "cli_execution_available": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Logged in using ChatGPT",
            "auth_mode": "chatgpt",
            "authenticated": True,
            "auth_status_detectable": True,
            "supports_model_override": True,
            "supports_reasoning_effort": True,
            "supports_app_server": True,
            "supports_builtin_auth": True,
            "available_models": [],
            "configured_plugins": [],
            "configured_mcp_servers": [],
            "local_skills": [],
            "mcp_servers": [],
            "mcp_state": {},
            "notes": [],
            "app_server_supported": True,
        },
    )
    monkeypatch.setattr(
        "startup.detect_provider_statuses",
        lambda selected_provider=None, adapter_command=None, provider_endpoint=None, adapter_args=None: [
            {
                "provider": "codex",
                "label": "Codex",
                "runtime_ready": True,
                "runtime_summary": "Codex CLI ready.",
                "login_status": "Logged in using ChatGPT",
                "cli_detected": True,
                "cli_version": "codex 1.0.0",
                "authenticated": True,
            },
            {
                "provider": "claude_code",
                "label": "Claude Code",
                "runtime_ready": False,
                "runtime_summary": "Claude CLI missing.",
                "login_status": "Claude CLI missing.",
                "cli_detected": False,
                "cli_version": None,
                "authenticated": False,
            },
            {
                "provider": "ollama",
                "label": "Ollama",
                "runtime_ready": True,
                "runtime_summary": "Ollama endpoint reachable.",
                "login_status": "Ollama endpoint reachable.",
                "cli_detected": True,
                "cli_version": "http://localhost:11434",
                "authenticated": True,
            },
            {
                "provider": "openai_api",
                "label": "OpenAI API",
                "runtime_ready": False,
                "runtime_summary": "OpenAI API key missing.",
                "login_status": "OpenAI API key missing.",
                "cli_detected": False,
                "cli_version": None,
                "authenticated": False,
            },
            {
                "provider": "anthropic_api",
                "label": "Anthropic API",
                "runtime_ready": False,
                "runtime_summary": "Anthropic API key missing.",
                "login_status": "Anthropic API key missing.",
                "cli_detected": False,
                "cli_version": None,
                "authenticated": False,
            },
            {
                "provider": "xai_api",
                "label": "xAI API",
                "runtime_ready": False,
                "runtime_summary": "xAI API key missing.",
                "login_status": "xAI API key missing.",
                "cli_detected": False,
                "cli_version": None,
                "authenticated": False,
            },
            {
                "provider": "nvidia_dynamo",
                "label": "NVIDIA Dynamo",
                "runtime_ready": False,
                "runtime_summary": "NVIDIA Dynamo frontend is not reachable.",
                "login_status": "NVIDIA Dynamo frontend is not reachable.",
                "cli_detected": False,
                "cli_version": None,
                "authenticated": False,
            },
            {
                "provider": "nvidia_nim",
                "label": "NVIDIA NIM",
                "runtime_ready": False,
                "runtime_summary": "NVIDIA NIM endpoint is not reachable.",
                "login_status": "NVIDIA NIM endpoint is not reachable.",
                "cli_detected": False,
                "cli_version": None,
                "authenticated": False,
            },
            {
                "provider": "custom",
                "label": "Custom Adapter",
                "runtime_ready": False,
                "runtime_summary": "Custom adapter is not configured.",
                "login_status": "Custom adapter is not configured.",
                "cli_detected": False,
                "cli_version": None,
                "authenticated": False,
            },
        ],
    )
    monkeypatch.setattr(
        "diagnostics.detect_device_profile",
        lambda: {
            "platform_label": "Windows Test Rig",
            "architecture": "x86_64",
            "cpu_count": 12,
            "memory_total_gb": 32,
            "platform_hints": [],
        },
    )
    monkeypatch.setattr(
        "diagnostics.detect_performance_profile",
        lambda: {
            "resource_tier": "high",
            "lag_risk": "low",
            "recommended_swarm_max_agents": 4,
        },
    )
    monkeypatch.setattr(
        "diagnostics.platform_debug_commands",
        lambda backend_port=8010: [
            f"Invoke-WebRequest http://127.0.0.1:{backend_port}/api/health",
            "python -m pytest apps/server/tests/test_startup.py -q",
        ],
    )


def test_new_install_routes_to_first_time_setup(client) -> None:
    response = client.get("/api/startup/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "first_time"
    assert payload["overall_status"] == "ready"
    assert payload["backend_ready"] is True
    assert payload["onboarding_complete"] is False
    assert payload["recommended_route"] == "/setup"
    assert payload["first_run_completed"] is False
    assert payload["status_source"] == "fresh"
    assert payload["checked_at"] is not None


def test_complete_first_run_persists_and_routes_to_dashboard(monkeypatch, client) -> None:
    monkeypatch.setattr(
        startup_service,
        "_provider_optional_checks",
        lambda profile: [
            startup_service._check("codex_cli", required=False, status="passed", summary="Codex CLI ready."),
            startup_service._check("codex_login", required=False, status="passed", summary="Codex login ready."),
            startup_service._check("app_server", required=False, status="passed", summary="Codex app server ready."),
        ],
    )
    complete = client.post(
        "/api/startup/complete-first-run",
        json={
            "username": "Morgan",
            "provider": "codex",
            "auth_mode": "chatgpt",
            "connected_accounts_summary": {"github": {"status": "not_connected"}},
            "default_runner_mode": "auto",
        },
    )
    assert complete.status_code == 200
    assert complete.json()["first_run_completed"] is True

    status = client.get("/api/startup/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["mode"] == "regular"
    assert payload["backend_ready"] is True
    assert payload["onboarding_complete"] is True
    assert payload["recommended_route"] == "/dashboard"
    assert payload["first_run_completed"] is True


def test_complete_first_run_persists_builtin_ollama_adapter_recipe(client) -> None:
    complete = client.post(
        "/api/startup/complete-first-run",
        json={
            "username": "Morgan",
            "provider": "ollama",
            "auth_mode": "local",
            "default_runner_mode": "auto",
            "provider_endpoint": "http://localhost:11434",
        },
    )
    assert complete.status_code == 200
    db = SessionLocal()
    try:
        profile = db.scalar(select(AppProfile).order_by(AppProfile.updated_at.desc(), AppProfile.id.desc()))
        assert profile is not None
        assert profile.provider_endpoint == "http://localhost:11434"
        assert profile.adapter_command
        assert profile.adapter_args_json
        normalized_path = profile.adapter_args_json[0].replace("\\", "/")
        assert normalized_path.endswith("scripts/ollama_adapter.py")
    finally:
        db.close()


def test_required_check_failure_returns_error(monkeypatch, client, bridge_headers) -> None:
    monkeypatch.setattr(
        startup_service,
        "_check_database",
        lambda db: startup_service._check("database", required=True, status="failed", summary="Database init failed.", error_code="MC-STORAGE-DB-UNAVAILABLE-001"),
    )
    payload = client.post("/api/startup/check", json={"attempt_number": 1, "include_optional_checks": True}, headers=bridge_headers).json()
    assert payload["mode"] == "error"
    assert payload["overall_status"] == "error"
    assert payload["backend_ready"] is False
    assert payload["error_code"] == "MC-STORAGE-DB-UNAVAILABLE-001"
    assert payload["recommended_route"] == "/startup-error"


def test_optional_selected_provider_failure_returns_degraded(monkeypatch, client, bridge_headers) -> None:
    client.post(
        "/api/startup/complete-first-run",
        json={
            "username": "Morgan",
            "provider": "claude_code",
            "auth_mode": "external",
            "default_runner_mode": "auto",
        },
    )
    monkeypatch.setattr(
        startup_service,
        "_provider_optional_checks",
        lambda profile: [
            startup_service._check("claude_code", required=False, status="failed", summary="Claude CLI missing.", error_code="MC-CLAUDE-CLI-MISSING-001")
        ],
    )
    payload = client.post("/api/startup/check", json={"attempt_number": 1, "include_optional_checks": True}, headers=bridge_headers).json()
    assert payload["mode"] == "degraded"
    assert payload["overall_status"] == "degraded"
    assert payload["recommended_route"] == "/dashboard"
    assert payload["error_code"] == "MC-CLAUDE-CLI-MISSING-001"


def test_codex_provider_failure_returns_degraded(monkeypatch, client, bridge_headers) -> None:
    client.post(
        "/api/startup/complete-first-run",
        json={
            "username": "Morgan",
            "provider": "codex",
            "auth_mode": "chatgpt",
            "default_runner_mode": "auto",
        },
    )
    monkeypatch.setattr(
        startup_service,
        "_provider_optional_checks",
        lambda profile: [
            startup_service._check("codex_cli", required=False, status="failed", summary="Codex CLI missing.", error_code="MC-CODEX-CLI-MISSING-001")
        ],
    )
    payload = client.post("/api/startup/check", json={"attempt_number": 1, "include_optional_checks": True}, headers=bridge_headers).json()
    assert payload["mode"] == "degraded"
    assert payload["overall_status"] == "degraded"
    assert payload["error_code"] == "MC-CODEX-CLI-MISSING-001"


def test_retry_after_three_attempts_generates_diagnostic_report(monkeypatch, client, bridge_headers) -> None:
    monkeypatch.setattr(
        startup_service,
        "_check_runtime_paths",
        lambda: startup_service._check("runtime_paths", required=True, status="failed", summary="Runtime path failure.", error_code="MC-BOOT-RUNTIME-PATH-001"),
    )
    payload = client.post("/api/startup/retry", json={"attempt_number": 3, "failed_check": "runtime_paths", "retry_mode": "full"}, headers=bridge_headers).json()
    assert payload["error_code"] == "MC-BOOT-RUNTIME-PATH-001"
    assert payload["diagnostic_report_path"]
    assert Path(payload["diagnostic_report_path"]).exists()


def test_manual_diagnostics_report_is_created(client) -> None:
    report = client.post("/api/startup/diagnostics")
    assert report.status_code == 200
    payload = report.json()
    assert Path(payload["path"]).exists()
    assert Path(payload["json_path"]).exists()
    assert Path(payload["bundle_path"]).exists()
    assert payload["report_id"].startswith("diagnostic-")
    assert payload["safe_debug_commands"]
    assert payload["platform_profile"]["platform_label"]
    assert payload["performance_profile"]["recommended_swarm_max_agents"] >= 1
    assert payload["runtime_blockers"] == []
    assert payload["backend_binding"]["host"]
    assert "mode" in payload["daemon_identity"]
    assert "status" in payload["daemon_metadata"]
    assert payload["repo_version_control"]["status"] == "not_configured"
    assert sorted(payload["bundle_members"]) == sorted([Path(payload["path"]).name, Path(payload["json_path"]).name])
    assert payload["bundle_metadata"]["exists"] is True
    assert payload["bundle_metadata"]["member_count"] >= 2
    assert "summary" in payload


def test_startup_status_is_recomputed_instead_of_returning_stale_cached_payload(monkeypatch, client) -> None:
    calls = {"count": 0}

    def fake_backend_route() -> dict:
        calls["count"] += 1
        return startup_service._check(
            "backend_route",
            required=True,
            status="passed",
            summary=f"Backend route check #{calls['count']}",
        )

    monkeypatch.setattr(startup_service, "_check_backend_route", fake_backend_route)

    first = client.get("/api/startup/status")
    second = client.get("/api/startup/status")

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 2
    assert any(item["summary"] == "Backend route check #2" for item in second.json()["checks"])


def test_selected_openai_provider_without_api_key_degrades_startup(monkeypatch, client, bridge_headers) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client.post(
        "/api/startup/complete-first-run",
        json={
            "username": "Morgan",
            "provider": "openai_api",
            "auth_mode": "api_key",
            "default_runner_mode": "auto",
        },
    )
    payload = client.post("/api/startup/check", json={"attempt_number": 1, "include_optional_checks": True}, headers=bridge_headers).json()
    assert payload["mode"] == "degraded"
    assert payload["overall_status"] == "degraded"
    assert payload["error_code"] == "MC-API-KEY-MISSING-001"
    assert "openai_api" in payload["failed_checks"]


def test_selected_custom_provider_without_adapter_degrades_startup(client, bridge_headers) -> None:
    client.post(
        "/api/startup/complete-first-run",
        json={
            "username": "Morgan",
            "provider": "custom",
            "auth_mode": "external",
            "default_runner_mode": "auto",
        },
    )
    payload = client.post("/api/startup/check", json={"attempt_number": 1, "include_optional_checks": True}, headers=bridge_headers).json()
    assert payload["mode"] == "degraded"
    assert payload["overall_status"] == "degraded"
    assert payload["error_code"] == "MC-RUNNER-NONE-AVAILABLE-001"
    assert "custom" in payload["failed_checks"]


def test_selected_nvidia_dynamo_provider_without_frontend_degrades_startup(monkeypatch, client, bridge_headers) -> None:
    monkeypatch.setattr(
        "startup.detect_provider_statuses",
        lambda selected_provider=None, adapter_command=None, provider_endpoint=None, adapter_args=None: [
            {
                "provider": "codex",
                "runtime_ready": True,
                "runtime_summary": "ready",
                "login_status": "ready",
                "cli_detected": True,
                "authenticated": True,
                "app_server_supported": True,
                "configured_plugins": [],
                "configured_mcp_servers": [],
                "local_skills": [],
                "mcp_servers": [],
                "mcp_state": {},
                "notes": [],
            },
            {
                "provider": "claude_code",
                "runtime_ready": False,
                "runtime_summary": "missing",
                "login_status": "missing",
                "cli_detected": False,
            },
            {
                "provider": "ollama",
                "runtime_ready": False,
                "runtime_summary": "offline",
                "login_status": "offline",
                "cli_detected": False,
            },
            {
                "provider": "openai_api",
                "runtime_ready": False,
                "runtime_summary": "missing",
                "login_status": "missing",
                "cli_detected": False,
            },
            {
                "provider": "anthropic_api",
                "runtime_ready": False,
                "runtime_summary": "missing",
                "login_status": "missing",
                "cli_detected": False,
            },
            {
                "provider": "xai_api",
                "runtime_ready": False,
                "runtime_summary": "missing",
                "login_status": "missing",
                "cli_detected": False,
            },
            {
                "provider": "nvidia_dynamo",
                "runtime_ready": False,
                "runtime_summary": "NVIDIA Dynamo frontend is not reachable.",
                "login_status": "NVIDIA Dynamo frontend is not reachable.",
                "cli_detected": False,
            },
            {
                "provider": "custom",
                "runtime_ready": False,
                "runtime_summary": "missing",
                "login_status": "missing",
                "cli_detected": False,
            },
        ],
    )
    client.post(
        "/api/startup/complete-first-run",
        json={
            "username": "Morgan",
            "provider": "nvidia_dynamo",
            "auth_mode": "external",
            "default_runner_mode": "auto",
        },
    )
    payload = client.post("/api/startup/check", json={"attempt_number": 1, "include_optional_checks": True}, headers=bridge_headers).json()
    assert payload["mode"] == "degraded"
    assert payload["overall_status"] == "degraded"
    assert payload["error_code"] == "MC-RUNNER-NONE-AVAILABLE-001"
    assert "nvidia_dynamo" in payload["failed_checks"]


def test_diagnostics_collects_daemon_launcher_logs(monkeypatch, tmp_path) -> None:
    launcher = tmp_path / "launcher"
    launcher.mkdir()
    (launcher / "daemon.stdout.log").write_text("daemon out\n", encoding="utf-8")
    (launcher / "daemon.stderr.log").write_text("daemon err\n", encoding="utf-8")
    monkeypatch.setattr(diagnostics, "LAUNCHER_ROOT", launcher)
    report_root = tmp_path / "diagnostics"
    report_root.mkdir()
    monkeypatch.setattr(diagnostics, "diagnostics_root", lambda: report_root)

    report = diagnostics.write_diagnostic_report(
        startup_status={"mode": "regular", "overall_status": "ready", "checks": []},
        system_status={},
        settings_status=None,
        recent_errors=None,
    )

    payload = Path(report["json_path"]).read_text(encoding="utf-8")
    assert "daemon out" in payload
    assert "daemon err" in payload
    assert Path(report["bundle_path"]).exists()


def test_diagnostic_reports_preserve_optional_project_scope_metadata(monkeypatch, tmp_path) -> None:
    report_root = tmp_path / "diagnostics"
    report_root.mkdir()
    monkeypatch.setattr(diagnostics, "diagnostics_root", lambda: report_root)

    diagnostics.write_diagnostic_report(
        startup_status={"mode": "regular", "overall_status": "ready", "checks": []},
        system_status={},
        settings_status=None,
        recent_errors=None,
        project_id=42,
        project_name="Scoped Diagnostics",
        workspace_path="C:/demo/scoped",
    )

    reports = diagnostics.list_diagnostic_reports()

    assert reports
    assert reports[0]["report_id"].startswith("diagnostic-")
    assert reports[0]["project_id"] == 42
    assert reports[0]["project_name"] == "Scoped Diagnostics"
    assert reports[0]["workspace_path"] == "C:/demo/scoped"
    assert reports[0]["bundle_members"]
    assert reports[0]["bundle_metadata"]["exists"] is True
    assert reports[0]["repo_version_control"]["status"] == "missing_workspace"


def test_preview_status_reuses_provider_detection_when_profile_probe_key_is_unchanged(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_detect_provider_statuses(selected_provider=None, adapter_command=None, provider_endpoint=None, adapter_args=None):
        calls["count"] += 1
        return [
            {
                "provider": "codex",
                "label": "Codex",
                "runtime_ready": True,
                "runtime_summary": "Codex CLI ready.",
                "login_status": "Logged in using ChatGPT",
                "cli_detected": True,
                "cli_version": "codex 1.0.0",
                "authenticated": True,
            }
        ]

    monkeypatch.setattr("startup.detect_provider_statuses", fake_detect_provider_statuses)

    db = SessionLocal()
    try:
        startup_service.preview_status(db, attempt_number=1, include_optional_checks=False)
    finally:
        db.close()

    assert calls["count"] == 1
