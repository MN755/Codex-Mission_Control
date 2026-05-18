from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DAEMON_METADATA_PATH, DAEMON_TOKEN_PATH, DEFAULT_BACKEND_HOST, DEFAULT_BACKEND_PORT, ensure_runtime_dirs


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def write_daemon_metadata(*, host: str, port: int, pid: int, mode: str) -> dict[str, Any]:
    ensure_runtime_dirs()
    payload = {
        "status": "ok",
        "mode": mode,
        "host": host,
        "port": port,
        "pid": pid,
        "started_at": utc_now().isoformat(),
    }
    DAEMON_METADATA_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def read_daemon_metadata() -> dict[str, Any]:
    if not DAEMON_METADATA_PATH.exists():
        return {
            "status": "unknown",
            "mode": os.environ.get("MISSION_CONTROL_SERVER_MODE", "web"),
            "host": os.environ.get("MISSION_CONTROL_BACKEND_HOST", DEFAULT_BACKEND_HOST),
            "port": int(os.environ.get("MISSION_CONTROL_BACKEND_PORT", DEFAULT_BACKEND_PORT)),
            "pid": os.getpid(),
            "started_at": utc_now().isoformat(),
        }
    try:
        payload = json.loads(DAEMON_METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {}
    payload.setdefault("status", "ok")
    payload.setdefault("mode", os.environ.get("MISSION_CONTROL_SERVER_MODE", "web"))
    payload.setdefault("host", os.environ.get("MISSION_CONTROL_BACKEND_HOST", DEFAULT_BACKEND_HOST))
    payload.setdefault("port", int(os.environ.get("MISSION_CONTROL_BACKEND_PORT", DEFAULT_BACKEND_PORT)))
    payload.setdefault("pid", os.getpid())
    payload.setdefault("started_at", utc_now().isoformat())
    return payload


def daemon_dashboard_url(project_id: int | None = None) -> str:
    metadata = read_daemon_metadata()
    host = metadata.get("host", DEFAULT_BACKEND_HOST)
    port = int(metadata.get("port", DEFAULT_BACKEND_PORT))
    if project_id is not None:
        return f"http://{host}:{port}/projects/{project_id}"
    return f"http://{host}:{port}/dashboard"
