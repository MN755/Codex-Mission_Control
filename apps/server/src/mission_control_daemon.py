from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from config import DEFAULT_BACKEND_HOST, DEFAULT_BACKEND_PORT, ensure_runtime_dirs
from daemon_state import ensure_daemon_token, write_daemon_metadata
from main import app


def main() -> None:
    ensure_runtime_dirs()
    ensure_daemon_token()
    host = os.environ.get("MISSION_CONTROL_BACKEND_HOST", DEFAULT_BACKEND_HOST)
    port = int(os.environ.get("MISSION_CONTROL_BACKEND_PORT", DEFAULT_BACKEND_PORT))
    os.environ.setdefault("MISSION_CONTROL_SERVER_MODE", "daemon")
    write_daemon_metadata(host=host, port=port, pid=os.getpid(), mode=os.environ["MISSION_CONTROL_SERVER_MODE"])
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
