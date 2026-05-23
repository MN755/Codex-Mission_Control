from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from config import ensure_runtime_dirs
from daemon_state import ensure_daemon_token, resolve_backend_binding, update_daemon_metadata_status, write_daemon_metadata
from main import app

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def main() -> None:
    ensure_runtime_dirs()
    ensure_daemon_token()
    os.environ.setdefault("MISSION_CONTROL_SERVER_MODE", "daemon")
    binding = resolve_backend_binding(prefer_live_metadata=False)
    host = str(binding["host"])
    port = int(binding["port"])
    if host.strip().lower() not in LOCAL_HOSTS:
        raise RuntimeError(f"Mission Control daemon must stay localhost-only. Refusing host {host!r}.")
    started_at = write_daemon_metadata(
        host=host,
        port=port,
        pid=os.getpid(),
        mode=os.environ["MISSION_CONTROL_SERVER_MODE"],
        status="starting",
    )["started_at"]
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
        update_daemon_metadata_status(
            status="stopped",
            host=host,
            port=port,
            pid=os.getpid(),
            mode=os.environ["MISSION_CONTROL_SERVER_MODE"],
        )
    except Exception as exc:
        write_daemon_metadata(
            host=host,
            port=port,
            pid=os.getpid(),
            mode=os.environ["MISSION_CONTROL_SERVER_MODE"],
            status="failed",
            started_at=started_at,
            last_error=f"{type(exc).__name__}: {exc}",
        )
        raise


if __name__ == "__main__":
    main()
