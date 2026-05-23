from __future__ import annotations

import json

from codex_cli_path import codex_command_path
from daemon_state import DAEMON_METADATA_PATH, daemon_identity_snapshot, read_daemon_metadata, update_daemon_metadata_status, write_daemon_metadata
from system_status import detect_system_status


def test_read_daemon_metadata_marks_dead_pid_as_stale(tmp_path, monkeypatch) -> None:
    metadata_path = tmp_path / "daemon.json"
    monkeypatch.setattr("daemon_state.DAEMON_METADATA_PATH", metadata_path)
    monkeypatch.setattr("daemon_state.RUNTIME_ROOT", tmp_path / "runtime")
    monkeypatch.setattr("daemon_state.LAUNCHER_ROOT", tmp_path / "launcher")
    monkeypatch.setattr("daemon_state.DAEMON_TOKEN_PATH", tmp_path / "runtime" / "daemon.token")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "mode": "daemon",
                "host": "127.0.0.1",
                "port": 8010,
                "pid": 999999,
                "started_at": "2026-05-19T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("daemon_state.process_is_running", lambda pid: False)

    payload = read_daemon_metadata()
    assert payload["status"] == "stale"
    assert payload["pid_running"] is False
    assert payload["liveness"] == "dead_pid"


def test_detect_system_status_reports_resolved_backend_port(monkeypatch) -> None:
    monkeypatch.setattr(
        "system_status.resolve_backend_binding",
        lambda: {"host": "127.0.0.1", "port": 8010, "mode": "daemon", "source": "daemon_metadata"},
    )
    monkeypatch.setattr(
        "system_status.detect_provider_statuses",
        lambda adapter_command=None, ollama_endpoint=None, adapter_args=None: [
            {
                "provider": "codex",
                "label": "Codex",
                "cli_detected": True,
                "cli_version": "codex 1.0.0",
                "login_status": "Logged in using ChatGPT",
                "auth_mode": "chatgpt",
                "authenticated": True,
                "available_models": [],
                "mcp_servers": [],
                "configured_plugins": [],
                "local_skills": [],
                "notes": [],
            }
        ],
    )

    payload = detect_system_status(selected_provider="codex")
    assert payload["backend_host"] == "127.0.0.1"
    assert payload["backend_port"] == 8010
    assert payload["configured_backend_port"] == 8010
    assert payload["backend_binding_source"] == "daemon_metadata"
    assert any("Backend binding source: daemon_metadata." == note for note in payload["notes"])


def test_codex_command_path_prefers_explicit_env_override(monkeypatch, tmp_path) -> None:
    fake_cli = tmp_path / "codex.exe"
    fake_cli.write_text("", encoding="utf-8")
    monkeypatch.setenv("MISSION_CONTROL_CODEX_PATH", str(fake_cli))
    monkeypatch.setenv("CODEX_CLI_PATH", "")
    monkeypatch.setattr("codex_cli_path.shutil.which", lambda name: None)

    resolved = codex_command_path()
    assert resolved == str(fake_cli.resolve())


def test_codex_command_path_prefers_openai_appdata_binary_over_windowsapps_alias(monkeypatch, tmp_path) -> None:
    local_app_data = tmp_path / "AppData" / "Local"
    preferred = local_app_data / "OpenAI" / "Codex" / "bin" / "codex.exe"
    fallback = local_app_data / "Microsoft" / "WindowsApps" / "codex.exe"
    preferred.parent.mkdir(parents=True, exist_ok=True)
    fallback.parent.mkdir(parents=True, exist_ok=True)
    preferred.write_text("", encoding="utf-8")
    fallback.write_text("", encoding="utf-8")

    monkeypatch.delenv("MISSION_CONTROL_CODEX_PATH", raising=False)
    monkeypatch.delenv("CODEX_CLI_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr("codex_cli_path.platform.system", lambda: "Windows")
    monkeypatch.setattr("codex_cli_path.shutil.which", lambda name: str(fallback))

    resolved = codex_command_path()
    assert resolved == str(preferred.resolve())


def test_update_daemon_metadata_status_preserves_started_at(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("daemon_state.DAEMON_METADATA_PATH", tmp_path / "daemon.json")
    monkeypatch.setattr("daemon_state.RUNTIME_ROOT", tmp_path / "runtime")
    monkeypatch.setattr("daemon_state.LAUNCHER_ROOT", tmp_path / "launcher")
    monkeypatch.setattr("daemon_state.DAEMON_TOKEN_PATH", tmp_path / "runtime" / "daemon.token")
    write_daemon_metadata(host="127.0.0.1", port=8010, pid=1234, mode="daemon", status="starting", started_at="2026-05-19T12:00:00+00:00")

    updated = update_daemon_metadata_status(status="ok", host="127.0.0.1", port=8010, pid=1234, mode="daemon")

    assert updated["status"] == "ok"
    assert updated["started_at"] == "2026-05-19T12:00:00+00:00"


def test_daemon_identity_snapshot_refreshes_current_daemon_metadata(tmp_path, monkeypatch) -> None:
    metadata_path = tmp_path / "daemon.json"
    runtime_root = tmp_path / "runtime"
    launcher_root = tmp_path / "launcher"
    monkeypatch.setattr("daemon_state.DAEMON_METADATA_PATH", metadata_path)
    monkeypatch.setattr("daemon_state.RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr("daemon_state.LAUNCHER_ROOT", launcher_root)
    monkeypatch.setattr("daemon_state.DAEMON_TOKEN_PATH", runtime_root / "daemon.token")
    monkeypatch.setenv("MISSION_CONTROL_SERVER_MODE", "daemon")
    monkeypatch.setenv("MISSION_CONTROL_BACKEND_HOST", "127.0.0.1")
    monkeypatch.setenv("MISSION_CONTROL_BACKEND_PORT", "8010")
    write_daemon_metadata(
        host="127.0.0.1",
        port=8010,
        pid=999999,
        mode="daemon",
        status="stopped",
        started_at="2026-05-19T12:00:00+00:00",
    )

    payload = daemon_identity_snapshot()
    refreshed = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert payload["metadata_status"] == "ok"
    assert payload["pid"] != 999999
    assert payload["pid_running"] is True
    assert refreshed["status"] == "ok"
    assert refreshed["pid"] == payload["pid"]
