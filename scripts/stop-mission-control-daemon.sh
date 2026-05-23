#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_PATH="${SCRIPT_DIR}/mission-control.config.json"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python was not found on PATH." >&2
  exit 1
fi

"${PYTHON_BIN}" - <<'PY' "${REPO_ROOT}" "${CONFIG_PATH}"
from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
import urllib.request
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
config_path = Path(sys.argv[2])
config = {}
if config_path.exists():
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        config = {}

host = str(os.environ.get("MISSION_CONTROL_BACKEND_HOST") or config.get("host") or "127.0.0.1")
port = int(os.environ.get("MISSION_CONTROL_BACKEND_PORT") or config.get("backendPort") or 8010)
launcher_dir = repo_root / str(config.get("launcherLogDir") or ".runtime/launcher")
metadata_path = launcher_dir / "daemon.json"


def url_host(value: str) -> str:
    return f"[{value}]" if ":" in value and not value.startswith("[") else value


def fetch_identity() -> dict:
    url = f"http://{url_host(host)}:{port}/api/diagnostics/identity"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status != 200:
                return {}
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def port_open() -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.75):
            return True
    except OSError:
        return False


identity = fetch_identity()
pid = int(identity.get("pid") or 0)
if identity and (str(identity.get("repo_root") or "") != str(repo_root) or str(identity.get("mode") or "") != "daemon"):
    raise SystemExit(f"Refusing to stop port {port}: daemon identity does not match this repository.")

if pid <= 0 and metadata_path.exists():
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        pid = int(metadata.get("pid") or 0)
    except Exception:
        pid = 0

if pid <= 0:
    if port_open():
        raise SystemExit(f"Refusing to stop port {port}: process identity could not be confirmed.")
    print(f"[Mission Control] No daemon metadata found at {metadata_path}")
    raise SystemExit(0)

try:
    os.kill(pid, 0)
except OSError:
    if metadata_path.exists():
        metadata_path.unlink()
    print(f"[Mission Control] Daemon PID {pid} was not running.")
    raise SystemExit(0)

os.kill(pid, signal.SIGTERM)
deadline = time.time() + 10
while time.time() < deadline:
    try:
        os.kill(pid, 0)
    except OSError:
        break
    time.sleep(0.25)
else:
    os.kill(pid, signal.SIGKILL)

if metadata_path.exists():
    metadata_path.unlink()
print(f"[Mission Control] Daemon stopped (PID {pid}).")
PY
