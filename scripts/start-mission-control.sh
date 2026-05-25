#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DESKTOP_SRC="${REPO_ROOT}/apps/desktop/src"
SERVER_SRC="${REPO_ROOT}/apps/server/src"
FRONTEND_DIR="${REPO_ROOT}/apps/dashboard"
FRONTEND_DIST="${FRONTEND_DIR}/dist"
CONFIG_PATH="${MISSION_CONTROL_LAUNCHER_CONFIG:-${SCRIPT_DIR}/mission-control.config.json}"

MODE="desktop"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BACKEND_PORT=""
BIND_HOST=""
NO_BROWSER="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --backend-port)
      BACKEND_PORT="${2:-}"
      shift 2
      ;;
    --bind-host)
      BIND_HOST="${2:-}"
      shift 2
      ;;
    --no-browser)
      NO_BROWSER="1"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "${MODE}" != "desktop" && "${MODE}" != "web" ]]; then
  echo "Mode must be 'desktop' or 'web'." >&2
  exit 1
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python 3 was not found on PATH." >&2
  exit 1
fi

mapfile -t CONFIG_VALUES < <("${PYTHON_BIN}" - <<'PY' "${REPO_ROOT}" "${CONFIG_PATH}"
from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
config_path = Path(sys.argv[2])
config: dict[str, object] = {}
if config_path.exists():
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        config = {}

host = str(config.get("host") or "127.0.0.1")
backend_port = str(config.get("backendPort") or 8010)
frontend_port = str(config.get("frontendPort") or 5173)
auto_open = "1" if bool(config.get("autoOpenBrowser", True)) else "0"
launcher_dir = str((repo_root / str(config.get("launcherLogDir") or ".runtime/launcher")).resolve())

for value in (host, backend_port, frontend_port, auto_open, launcher_dir):
    print(value)
PY
)

CONFIG_HOST="${CONFIG_VALUES[0]}"
CONFIG_BACKEND_PORT="${CONFIG_VALUES[1]}"
CONFIG_FRONTEND_PORT="${CONFIG_VALUES[2]}"
AUTO_OPEN_BROWSER="${CONFIG_VALUES[3]}"
LAUNCHER_DIR="${CONFIG_VALUES[4]}"
if [[ -n "${MISSION_CONTROL_LAUNCHER_DIR:-}" ]]; then
  LAUNCHER_DIR="${MISSION_CONTROL_LAUNCHER_DIR}"
fi
mkdir -p "${LAUNCHER_DIR}"
PID_FILE="${LAUNCHER_DIR}/pids.json"

EFFECTIVE_HOST="${BIND_HOST:-${CONFIG_HOST}}"
EFFECTIVE_BACKEND_PORT="${BACKEND_PORT:-${CONFIG_BACKEND_PORT}}"

write_status() {
  echo "[Mission Control] $1"
}

assert_local_host() {
  case "${1}" in
    127.0.0.1|localhost|::1) ;;
    *)
      echo "Mission Control web mode must stay localhost-only. Refusing host '${1}'." >&2
      exit 1
      ;;
  esac
}

build_frontend_if_needed() {
  if [[ -d "${FRONTEND_DIST}" ]]; then
    write_status "Using existing frontend bundle at ${FRONTEND_DIST}"
    return
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm was not found on PATH, and the frontend bundle is missing at ${FRONTEND_DIST}." >&2
    exit 1
  fi
  write_status "Frontend bundle is missing. Building it now..."
  (
    cd "${FRONTEND_DIR}"
    npm run build
  )
  if [[ ! -d "${FRONTEND_DIST}" ]]; then
    echo "Frontend build output is missing at ${FRONTEND_DIST}" >&2
    exit 1
  fi
}

check_backend_health() {
  "${PYTHON_BIN}" - <<'PY' "${EFFECTIVE_HOST}" "${EFFECTIVE_BACKEND_PORT}"
from __future__ import annotations

import json
import socket
import sys
from urllib.request import urlopen

host = sys.argv[1]
port = int(sys.argv[2])
url_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
try:
    with urlopen(f"http://{url_host}:{port}/api/health", timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        if response.status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
            raise SystemExit(0)
except Exception:
    raise SystemExit(1)
PY
}

check_port_open() {
  "${PYTHON_BIN}" - <<'PY' "${EFFECTIVE_HOST}" "${EFFECTIVE_BACKEND_PORT}"
from __future__ import annotations

import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
try:
    with socket.create_connection((host, port), timeout=0.75):
        raise SystemExit(0)
except OSError:
    raise SystemExit(1)
PY
}

wait_for_backend() {
  local attempts=0
  until check_backend_health; do
    attempts=$((attempts + 1))
    if [[ ${attempts} -ge 90 ]]; then
      echo "Mission Control backend did not become healthy in time." >&2
      exit 1
    fi
    sleep 1
  done
}

maybe_open_browser() {
  local url="$1"
  if [[ "${NO_BROWSER}" == "1" || "${AUTO_OPEN_BROWSER}" != "1" ]]; then
    write_status "Browser auto-open is disabled. Open ${url} manually."
    return
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${url}" >/dev/null 2>&1 || true
    return
  fi
  if command -v open >/dev/null 2>&1; then
    open "${url}" >/dev/null 2>&1 || true
    return
  fi
  write_status "No supported browser opener was detected. Open ${url} manually."
}

if [[ "${MODE}" == "desktop" ]]; then
  assert_local_host "${EFFECTIVE_HOST}"
  build_frontend_if_needed
  export PYTHONPATH="${DESKTOP_SRC}:${SERVER_SRC}:${PYTHONPATH:-}"
  export MISSION_CONTROL_FRONTEND_DIST="${FRONTEND_DIST}"
  export MISSION_CONTROL_LAUNCHER_DIR="${LAUNCHER_DIR}"
  write_status "Launching the desktop app..."
  cd "${REPO_ROOT}"
  exec "${PYTHON_BIN}" -m mission_control_desktop
fi

assert_local_host "${EFFECTIVE_HOST}"
build_frontend_if_needed
export PYTHONPATH="${SERVER_SRC}:${PYTHONPATH:-}"
export MISSION_CONTROL_FRONTEND_DIST="${FRONTEND_DIST}"
export MISSION_CONTROL_LAUNCHER_DIR="${LAUNCHER_DIR}"

BACKEND_URL_HOST="${EFFECTIVE_HOST}"
if [[ "${EFFECTIVE_HOST}" == *:* && "${EFFECTIVE_HOST}" != \[* ]]; then
  BACKEND_URL_HOST="[${EFFECTIVE_HOST}]"
fi
STARTUP_URL="http://${BACKEND_URL_HOST}:${EFFECTIVE_BACKEND_PORT}/startup"

if check_backend_health; then
  write_status "Backend already healthy at ${STARTUP_URL}"
  maybe_open_browser "${STARTUP_URL}"
  exit 0
fi

if check_port_open; then
  echo "Port ${EFFECTIVE_BACKEND_PORT} is already in use, but Mission Control did not report healthy on ${STARTUP_URL}." >&2
  exit 1
fi

BACKEND_STDOUT="${LAUNCHER_DIR}/backend.stdout.log"
BACKEND_STDERR="${LAUNCHER_DIR}/backend.stderr.log"
write_status "Starting Mission Control web mode on ${STARTUP_URL}"
(
  cd "${REPO_ROOT}/apps/server"
  nohup "${PYTHON_BIN}" -m uvicorn main:app --app-dir src --host "${EFFECTIVE_HOST}" --port "${EFFECTIVE_BACKEND_PORT}" >>"${BACKEND_STDOUT}" 2>>"${BACKEND_STDERR}" &
  echo $! > "${LAUNCHER_DIR}/backend.pid"
)

wait_for_backend

"${PYTHON_BIN}" - <<'PY' "${PID_FILE}" "${REPO_ROOT}" "${LAUNCHER_DIR}/backend.pid" "${BACKEND_STDOUT}" "${BACKEND_STDERR}" "${STARTUP_URL}"
from __future__ import annotations

import json
import sys
from pathlib import Path

pid_file = Path(sys.argv[1])
repo_root = Path(sys.argv[2]).resolve()
backend_pid = int(Path(sys.argv[3]).read_text(encoding="utf-8").strip())
payload = {
    "repoRoot": str(repo_root),
    "mode": "web",
    "backend": {
        "pid": backend_pid,
        "stdout": sys.argv[4],
        "stderr": sys.argv[5],
        "url": sys.argv[6],
    },
}
pid_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY

write_status "Launcher metadata written to ${PID_FILE}"
maybe_open_browser "${STARTUP_URL}"
