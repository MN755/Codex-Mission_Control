#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_PATH="${MISSION_CONTROL_LAUNCHER_CONFIG:-${SCRIPT_DIR}/mission-control.config.json}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python was not found on PATH." >&2
  exit 1
fi

"${PYTHON_BIN}" - <<'PY' "${REPO_ROOT}" "${CONFIG_PATH}" "${MISSION_CONTROL_LAUNCHER_DIR:-}"
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
config_path = Path(sys.argv[2])
launcher_override = str(sys.argv[3]).strip()
config: dict[str, object] = {}
if config_path.exists():
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        config = {}

launcher_dir = Path(launcher_override).expanduser().resolve() if launcher_override else (repo_root / str(config.get("launcherLogDir") or ".runtime/launcher")).resolve()
pid_file = launcher_dir / "pids.json"

if not pid_file.exists():
    print(f"No launcher PID file found at {pid_file}")
    raise SystemExit(0)

metadata = json.loads(pid_file.read_text(encoding="utf-8"))
tracked_entries = ("backend", "frontend", "desktop")


def process_command_line(pid: int) -> str:
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_tracked_process(name: str, entry: object) -> None:
    if not isinstance(entry, dict):
        return
    raw_pid = entry.get("pid")
    if not isinstance(raw_pid, int) or raw_pid <= 0:
        return
    if not process_running(raw_pid):
        return
    command_line = process_command_line(raw_pid)
    if command_line and str(repo_root) not in command_line:
        print(f"Skipping PID {raw_pid} for {name} because the command line does not match this repo.", file=sys.stderr)
        return
    os.kill(raw_pid, signal.SIGTERM)
    deadline = time.time() + 10
    while time.time() < deadline:
        if not process_running(raw_pid):
            break
        time.sleep(0.25)
    else:
        os.kill(raw_pid, signal.SIGKILL)
    print(f"Stopped {name} (PID {raw_pid})")


for process_name in tracked_entries:
    stop_tracked_process(process_name, metadata.get(process_name))

pid_file.unlink(missing_ok=True)
(launcher_dir / "backend.pid").unlink(missing_ok=True)
print("Mission Control processes stopped.")
PY
