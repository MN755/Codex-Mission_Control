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

HOST="${MISSION_CONTROL_BACKEND_HOST:-127.0.0.1}"
PORT="${MISSION_CONTROL_BACKEND_PORT:-8010}"
if [[ -f "${CONFIG_PATH}" ]]; then
  HOST="${MISSION_CONTROL_BACKEND_HOST:-$(python3 - <<'PY' "${CONFIG_PATH}"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as handle:
    payload = json.load(handle)
print(payload.get('host', '127.0.0.1'))
PY
)}"
  PORT="${MISSION_CONTROL_BACKEND_PORT:-$(python3 - <<'PY' "${CONFIG_PATH}"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as handle:
    payload = json.load(handle)
print(payload.get('backendPort', 8010))
PY
)}"
fi

HEALTH_URL="http://${HOST}:${PORT}/api/health"
LAUNCHER_DIR="${REPO_ROOT}/.runtime/launcher"
mkdir -p "${LAUNCHER_DIR}"

if python3 - <<'PY' "${HEALTH_URL}"
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
        ok = response.status == 200 and b'"status"' in response.read()
except Exception:
    ok = False
sys.exit(0 if ok else 1)
PY
then
  echo "[Mission Control] Daemon already healthy at ${HEALTH_URL}"
  exit 0
fi

export MISSION_CONTROL_SERVER_MODE="daemon"
export MISSION_CONTROL_BACKEND_HOST="${HOST}"
export MISSION_CONTROL_BACKEND_PORT="${PORT}"
export MISSION_CONTROL_REPO_ROOT="${REPO_ROOT}"

nohup "${PYTHON_BIN}" "${REPO_ROOT}/apps/server/src/mission_control_daemon.py" \
  >"${LAUNCHER_DIR}/daemon.stdout.log" \
  2>"${LAUNCHER_DIR}/daemon.stderr.log" &

for _ in $(seq 1 60); do
  if python3 - <<'PY' "${HEALTH_URL}"
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
        ok = response.status == 200 and b'"status"' in response.read()
except Exception:
    ok = False
sys.exit(0 if ok else 1)
PY
  then
    echo "[Mission Control] Daemon started at ${HEALTH_URL}"
    exit 0
  fi
  sleep 0.5
done

echo "Mission Control daemon did not become healthy in time." >&2
exit 1
