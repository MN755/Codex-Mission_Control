from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    try:
        os.kill(resolved_pid, 0)
    except OSError:
        return False
    return True


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
    DAEMON_METADATA_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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
    payload.setdefault("status", "ok")
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
        if payload.get("pid") and not pid_running:
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
