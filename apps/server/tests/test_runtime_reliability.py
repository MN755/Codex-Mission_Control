from __future__ import annotations

import json

from codex_cli_path import codex_command_path
from daemon_state import DAEMON_METADATA_PATH, daemon_identity_snapshot, read_daemon_metadata, update_daemon_metadata_status, write_daemon_metadata
from runtime_paths import ensure_runtime_paths
from system_status import detect_system_status


def test_daemon_listener_healthy_uses_socket_connect(monkeypatch) -> None:
    calls: list[tuple[tuple[str, int], float]] = []
    payloads: list[bytes] = []

    class FakeSocket:
        def __init__(self) -> None:
            self._responses = [b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}", b""]

        def settimeout(self, _timeout) -> None:
            return None

        def sendall(self, payload: bytes) -> None:
            payloads.append(payload)

        def recv(self, _size: int) -> bytes:
            return self._responses.pop(0)

        def shutdown(self, _how) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(
        "daemon_state.socket.create_connection",
        lambda address, timeout=0: calls.append((address, timeout)) or FakeSocket(),
    )

    from daemon_state import daemon_listener_healthy

    assert daemon_listener_healthy("127.0.0.1", 8010, timeout=2.5) is True
    assert calls == [(("127.0.0.1", 8010), 2.5)]
    assert payloads
    assert payloads[0].startswith(b"GET /api/health HTTP/1.1\r\n")
    assert b"Connection: close" in payloads[0]


def test_daemon_listener_healthy_returns_false_on_socket_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "daemon_state.socket.create_connection",
        lambda address, timeout=0: (_ for _ in ()).throw(OSError("listener gone")),
    )

    from daemon_state import daemon_listener_healthy

    assert daemon_listener_healthy("127.0.0.1", 8010) is False


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


def test_read_daemon_metadata_marks_live_pid_without_listener_as_stale(tmp_path, monkeypatch) -> None:
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
                "pid": 4321,
                "started_at": "2026-05-19T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("daemon_state.process_is_running", lambda pid: True)
    monkeypatch.setattr("daemon_state.daemon_listener_healthy", lambda host, port, timeout=1.0: False)

    payload = read_daemon_metadata()

    assert payload["status"] == "stale"
    assert payload["pid_running"] is True
    assert payload["listener_healthy"] is False
    assert payload["liveness"] == "listener_missing"


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
    monkeypatch.setattr("daemon_state.daemon_listener_healthy", lambda host, port, timeout=1.0: True)
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


def test_daemon_identity_snapshot_omits_repo_root_outside_source_checkout(monkeypatch) -> None:
    monkeypatch.setattr("daemon_state.SOURCE_REPO_ROOT", None)
    monkeypatch.setattr(
        "daemon_state.resolve_backend_binding",
        lambda prefer_live_metadata=False: {
            "host": "127.0.0.1",
            "port": 8010,
            "mode": "daemon",
            "source": "launcher_config",
        },
    )
    monkeypatch.setattr(
        "daemon_state.read_daemon_metadata",
        lambda validate_liveness=True: {
            "status": "ok",
            "stored_status": "ok",
            "pid": 1234,
            "pid_running": True,
            "started_at": "2026-05-29T12:00:00+00:00",
        },
    )

    payload = daemon_identity_snapshot()

    assert payload["repo_root"] is None


def test_listener_guard_stops_daemon_after_repeated_health_failures(monkeypatch) -> None:
    import threading

    from mission_control_daemon import _listener_guard

    class FakeServer:
        def __init__(self) -> None:
            self.started = True
            self.should_exit = False

    server = FakeServer()
    stop_event = threading.Event()
    listener_failure_event = threading.Event()
    updates: list[dict[str, object]] = []
    exit_codes: list[int] = []
    checks = {"count": 0}

    def fake_healthcheck(host: str, port: int) -> bool:
        checks["count"] += 1
        return False

    def fake_update(**kwargs) -> dict[str, object]:
        updates.append(kwargs)
        return kwargs

    def fake_exit(code: int) -> None:
        exit_codes.append(code)

    monkeypatch.setenv("MISSION_CONTROL_SERVER_MODE", "daemon")

    _listener_guard(
        server,
        host="127.0.0.1",
        port=8010,
        stop_event=stop_event,
        listener_failure_event=listener_failure_event,
        interval_seconds=0.0,
        failure_threshold=2,
        min_outage_seconds=0.0,
        healthcheck=fake_healthcheck,
        metadata_updater=fake_update,
        sleep_fn=lambda _seconds: None,
        exit_process=fake_exit,
    )

    assert checks["count"] == 2
    assert listener_failure_event.is_set() is True
    assert server.should_exit is True
    assert exit_codes == [1]
    assert updates
    assert updates[0]["status"] == "failed"
    assert "listener guard lost localhost health" in str(updates[0]["last_error"]).lower()


def test_listener_guard_tolerates_transient_failures_inside_outage_window(monkeypatch) -> None:
    import threading

    from mission_control_daemon import _listener_guard

    class FakeServer:
        def __init__(self) -> None:
            self.started = True
            self.should_exit = False

    server = FakeServer()
    stop_event = threading.Event()
    listener_failure_event = threading.Event()
    updates: list[dict[str, object]] = []
    exit_codes: list[int] = []
    checks = iter([False, False, True])
    moments = iter([0.0, 1.0, 2.0])

    def fake_healthcheck(host: str, port: int) -> bool:
        healthy = next(checks)
        if healthy:
            stop_event.set()
        return healthy

    def fake_update(**kwargs) -> dict[str, object]:
        updates.append(kwargs)
        return kwargs

    def fake_exit(code: int) -> None:
        exit_codes.append(code)

    monkeypatch.setenv("MISSION_CONTROL_SERVER_MODE", "daemon")

    _listener_guard(
        server,
        host="127.0.0.1",
        port=8010,
        stop_event=stop_event,
        listener_failure_event=listener_failure_event,
        interval_seconds=0.0,
        failure_threshold=2,
        min_outage_seconds=10.0,
        healthcheck=fake_healthcheck,
        metadata_updater=fake_update,
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: next(moments),
        exit_process=fake_exit,
    )

    assert listener_failure_event.is_set() is False
    assert server.should_exit is False
    assert updates == []
    assert exit_codes == []


def test_ensure_runtime_paths_probes_writable_diagnostics_root(monkeypatch, tmp_path) -> None:
    runtime_root = tmp_path / "runtime"
    diagnostics_dir = runtime_root / "diagnostics"

    class FixedUuid:
        hex = "fixedprobe"

    monkeypatch.setattr("runtime_paths.RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr("runtime_paths.RUNTIME_LOGS_ROOT", runtime_root / "logs")
    monkeypatch.setattr("runtime_paths.WORKTREE_ROOT", tmp_path / "worktrees")
    monkeypatch.setattr("runtime_paths.WORKSPACE_ROOT", tmp_path / "workspace")
    monkeypatch.setattr("runtime_paths.LAUNCHER_ROOT", tmp_path / "launcher")
    monkeypatch.setattr("runtime_paths.DB_PATH", runtime_root / "mission-control.db")
    monkeypatch.setattr("runtime_paths.DAEMON_METADATA_PATH", runtime_root / "daemon.json")
    monkeypatch.setattr("runtime_paths.DAEMON_TOKEN_PATH", runtime_root / "daemon.token")
    monkeypatch.setattr("runtime_paths.RUNNING_FROM_SOURCE", True)
    monkeypatch.setattr("runtime_paths.ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr("runtime_paths.uuid.uuid4", lambda: FixedUuid())

    payload = ensure_runtime_paths()

    assert diagnostics_dir.is_dir()
    assert not (diagnostics_dir / ".write-probe-fixedprobe.tmp").exists()
    assert payload["diagnostics_root"] == str(diagnostics_dir)
    assert payload["db_path"] == str(runtime_root / "mission-control.db")
    assert payload["daemon_metadata_path"] == str(runtime_root / "daemon.json")
    assert payload["daemon_token_path"] == str(runtime_root / "daemon.token")
