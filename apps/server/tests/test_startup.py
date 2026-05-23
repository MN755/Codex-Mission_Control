from __future__ import annotations

from pathlib import Path

import diagnostics
from startup import startup_service


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


def test_required_check_failure_returns_error(monkeypatch, client) -> None:
    monkeypatch.setattr(
        startup_service,
        "_check_database",
        lambda db: startup_service._check("database", required=True, status="failed", summary="Database init failed.", error_code="MC-STORAGE-DB-UNAVAILABLE-001"),
    )
    payload = client.post("/api/startup/check", json={"attempt_number": 1, "include_optional_checks": True}).json()
    assert payload["mode"] == "error"
    assert payload["overall_status"] == "error"
    assert payload["backend_ready"] is False
    assert payload["error_code"] == "MC-STORAGE-DB-UNAVAILABLE-001"
    assert payload["recommended_route"] == "/startup-error"


def test_optional_selected_provider_failure_returns_degraded(monkeypatch, client) -> None:
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
    payload = client.post("/api/startup/check", json={"attempt_number": 1, "include_optional_checks": True}).json()
    assert payload["mode"] == "degraded"
    assert payload["overall_status"] == "degraded"
    assert payload["recommended_route"] == "/dashboard"
    assert payload["error_code"] == "MC-CLAUDE-CLI-MISSING-001"


def test_codex_provider_failure_returns_degraded(monkeypatch, client) -> None:
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
    payload = client.post("/api/startup/check", json={"attempt_number": 1, "include_optional_checks": True}).json()
    assert payload["mode"] == "degraded"
    assert payload["overall_status"] == "degraded"
    assert payload["error_code"] == "MC-CODEX-CLI-MISSING-001"


def test_retry_after_three_attempts_generates_diagnostic_report(monkeypatch, client) -> None:
    monkeypatch.setattr(
        startup_service,
        "_check_runtime_paths",
        lambda: startup_service._check("runtime_paths", required=True, status="failed", summary="Runtime path failure.", error_code="MC-BOOT-RUNTIME-PATH-001"),
    )
    payload = client.post("/api/startup/retry", json={"attempt_number": 3, "failed_check": "runtime_paths", "retry_mode": "full"}).json()
    assert payload["error_code"] == "MC-BOOT-RUNTIME-PATH-001"
    assert payload["diagnostic_report_path"]
    assert Path(payload["diagnostic_report_path"]).exists()


def test_manual_diagnostics_report_is_created(client) -> None:
    report = client.post("/api/startup/diagnostics")
    assert report.status_code == 200
    payload = report.json()
    assert Path(payload["path"]).exists()
    assert "summary" in payload


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
