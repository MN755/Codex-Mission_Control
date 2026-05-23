from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if os.name == "nt":
    from ctypes import byref, windll
    from ctypes.wintypes import DWORD

from config import (
    DAEMON_METADATA_PATH,
    DAEMON_TOKEN_PATH,
    DEFAULT_BACKEND_HOST,
    DEFAULT_BACKEND_PORT,
    LAUNCHER_ROOT,
    REPO_ROOT,
    RUNTIME_ROOT,
    ensure_runtime_dirs,
    load_launcher_config,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_port(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _default_binding() -> tuple[str, int]:
    launcher_config = load_launcher_config()
    host = str(
        os.environ.get("MISSION_CONTROL_BACKEND_HOST")
        or launcher_config.get("host")
        or DEFAULT_BACKEND_HOST
    )
    port = _parse_port(
        os.environ.get("MISSION_CONTROL_BACKEND_PORT") or launcher_config.get("backendPort"),
        DEFAULT_BACKEND_PORT,
    )
    return host, port


def process_is_running(pid: Any) -> bool:
    try:
        resolved_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if resolved_pid <= 0:
        return False
    if resolved_pid == os.getpid():
        return True
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        handle = windll.kernel32.OpenProcess(process_query_limited_information, False, resolved_pid)
        if not handle:
            return False
        try:
            exit_code = DWORD()
            if not windll.kernel32.GetExitCodeProcess(handle, byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            windll.kernel32.CloseHandle(handle)
    try:
        os.kill(resolved_pid, 0)
    except OSError:
        return False
    return True


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    encoded = json.dumps(payload, indent=2)
    last_error: OSError | None = None
    try:
        for attempt in range(3):
            try:
                temp_path.write_text(encoded, encoding="utf-8")
                os.replace(temp_path, path)
                return
            except OSError as exc:
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
        if last_error is not None:
            raise last_error
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


def ensure_daemon_token() -> str:
    ensure_runtime_dirs()
    if DAEMON_TOKEN_PATH.exists():
        token = DAEMON_TOKEN_PATH.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    DAEMON_TOKEN_PATH.write_text(token, encoding="utf-8")
    return token


def read_daemon_token() -> str | None:
    if not DAEMON_TOKEN_PATH.exists():
        return None
    token = DAEMON_TOKEN_PATH.read_text(encoding="utf-8").strip()
    return token or None


def write_daemon_metadata(
    *,
    host: str,
    port: int,
    pid: int,
    mode: str,
    status: str = "ok",
    started_at: str | None = None,
    last_error: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_dirs()
    payload = {
        "status": status,
        "mode": mode,
        "host": host,
        "port": port,
        "pid": pid,
        "started_at": started_at or utc_now().isoformat(),
        "updated_at": utc_now().isoformat(),
        "repo_root": str(REPO_ROOT),
        "runtime_root": str(RUNTIME_ROOT),
        "launcher_root": str(LAUNCHER_ROOT),
    }
    if last_error:
        payload["last_error"] = last_error
    _write_json_atomic(DAEMON_METADATA_PATH, payload)
    return payload


def update_daemon_metadata_status(
    *,
    status: str,
    host: str | None = None,
    port: int | None = None,
    pid: int | None = None,
    mode: str | None = None,
    last_error: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_dirs()
    payload = read_daemon_metadata(validate_liveness=False)
    default_host, default_port = _default_binding()
    resolved_host = host or str(payload.get("host") or default_host)
    resolved_port = port if port is not None else _parse_port(payload.get("port"), default_port)
    resolved_pid = int(pid if pid is not None else payload.get("pid") or 0)
    resolved_mode = mode or str(payload.get("mode") or os.environ.get("MISSION_CONTROL_SERVER_MODE", "web"))
    started_at = str(payload.get("started_at") or utc_now().isoformat())
    return write_daemon_metadata(
        host=resolved_host,
        port=resolved_port,
        pid=resolved_pid,
        mode=resolved_mode,
        status=status,
        started_at=started_at,
        last_error=last_error,
    )


def read_daemon_metadata(*, validate_liveness: bool = True) -> dict[str, Any]:
    default_host, default_port = _default_binding()
    if not DAEMON_METADATA_PATH.exists():
        return {
            "status": "missing",
            "mode": os.environ.get("MISSION_CONTROL_SERVER_MODE", "web"),
            "host": default_host,
            "port": default_port,
            "pid": 0,
            "pid_running": False,
            "started_at": utc_now().isoformat(),
            "liveness": "missing",
        }
    try:
        payload = json.loads(DAEMON_METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {}
    stored_status = str(payload.get("status") or "ok")
    payload["stored_status"] = stored_status
    payload["metadata_status"] = stored_status
    payload["status"] = stored_status
    payload.setdefault("mode", os.environ.get("MISSION_CONTROL_SERVER_MODE", "web"))
    payload.setdefault("host", default_host)
    payload["port"] = _parse_port(payload.get("port"), default_port)
    payload.setdefault("pid", 0)
    payload.setdefault("started_at", utc_now().isoformat())
    payload.setdefault("repo_root", str(REPO_ROOT))
    payload.setdefault("runtime_root", str(RUNTIME_ROOT))
    payload.setdefault("launcher_root", str(LAUNCHER_ROOT))
    pid_running = process_is_running(payload.get("pid"))
    payload["pid_running"] = pid_running
    if validate_liveness:
        if payload.get("pid") and not pid_running and stored_status not in {"stopped", "failed"}:
            payload["status"] = "stale"
            payload["liveness"] = "dead_pid"
        else:
            payload["liveness"] = "running" if pid_running else "unknown"
    else:
        payload["liveness"] = "unchecked"
    return payload


def resolve_backend_binding(*, prefer_live_metadata: bool = True) -> dict[str, Any]:
    launcher_config = load_launcher_config()
    metadata = read_daemon_metadata(validate_liveness=True)
    env_host = os.environ.get("MISSION_CONTROL_BACKEND_HOST")
    env_port_text = os.environ.get("MISSION_CONTROL_BACKEND_PORT")
    env_port = _parse_port(env_port_text, DEFAULT_BACKEND_PORT) if env_port_text is not None else None
    metadata_is_live = prefer_live_metadata and bool(metadata.get("pid_running")) and metadata.get("status") == "ok"

    if env_host or env_port is not None:
        source = "env"
    elif metadata_is_live:
        source = "daemon_metadata"
    elif launcher_config:
        source = "launcher_config"
    else:
        source = "defaults"

    host = (
        env_host
        or (str(metadata.get("host")) if metadata_is_live and metadata.get("host") else None)
        or str(launcher_config.get("host") or DEFAULT_BACKEND_HOST)
    )
    port = (
        env_port
        if env_port is not None
        else (
            _parse_port(metadata.get("port"), DEFAULT_BACKEND_PORT)
            if metadata_is_live
            else _parse_port(launcher_config.get("backendPort"), DEFAULT_BACKEND_PORT)
        )
    )
    return {
        "host": host,
        "port": port,
        "mode": (
            os.environ.get("MISSION_CONTROL_SERVER_MODE")
            or (str(metadata.get("mode")) if metadata_is_live and metadata.get("mode") else None)
            or "web"
        ),
        "source": source,
        "metadata": metadata,
    }


def daemon_dashboard_url(project_id: int | None = None) -> str:
    binding = resolve_backend_binding()
    host = binding["host"]
    port = int(binding["port"])
    if project_id is not None:
        return f"http://{host}:{port}/projects/{project_id}"
    return f"http://{host}:{port}/dashboard"


def daemon_identity_snapshot() -> dict[str, Any]:
    binding = resolve_backend_binding(prefer_live_metadata=False)
    host = str(binding["host"])
    port = int(binding["port"])
    mode = str(binding.get("mode") or "unknown")
    if os.environ.get("MISSION_CONTROL_SERVER_MODE") == "daemon":
        current_metadata = read_daemon_metadata(validate_liveness=False)
        if (
            str(current_metadata.get("status") or "") != "ok"
            or int(current_metadata.get("pid") or 0) != os.getpid()
            or str(current_metadata.get("host") or "") != host
            or _parse_port(current_metadata.get("port"), port) != port
            or str(current_metadata.get("mode") or "") != mode
        ):
            update_daemon_metadata_status(
                status="ok",
                host=host,
                port=port,
                pid=os.getpid(),
                mode=mode,
            )
    metadata = read_daemon_metadata(validate_liveness=True)
    return {
        "status": "ok",
        "mode": mode,
        "host": host,
        "port": port,
        "base_url": f"http://{host}:{port}",
        "binding_source": str(binding.get("source") or "unknown"),
        "repo_root": str(REPO_ROOT),
        "runtime_root": str(RUNTIME_ROOT),
        "launcher_root": str(LAUNCHER_ROOT),
        "metadata_status": str(metadata.get("status") or "unknown"),
        "stored_metadata_status": str(metadata.get("stored_status") or metadata.get("status") or "unknown"),
        "pid": int(metadata.get("pid") or 0),
        "pid_running": bool(metadata.get("pid_running")),
        "started_at": metadata.get("started_at"),
        "token_required": True,
    }
