#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_PATH="${SCRIPT_DIR}/mission-control.config.json"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LAUNCHER_DIR="${REPO_ROOT}/.runtime/launcher"
METADATA_PATH="${LAUNCHER_DIR}/daemon.json"
STDOUT_PATH="${LAUNCHER_DIR}/daemon.stdout.log"
STDERR_PATH="${LAUNCHER_DIR}/daemon.stderr.log"
LAUNCH_LOG_PATH="${LAUNCHER_DIR}/daemon.launch.log"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python was not found on PATH." >&2
  exit 1
fi

assert_local_host() {
  local host_value="$1"
  case "${host_value}" in
    127.0.0.1|localhost|::1) ;;
    *)
      echo "Mission Control headless daemon must stay localhost-only. Refusing host '${host_value}'." >&2
      exit 1
      ;;
  esac
}

append_unique_path() {
  local candidate="$1"
  [[ -n "${candidate}" ]] || return 0
  [[ -d "${candidate}" ]] || return 0
  case ":${PATH}:" in
    *":${candidate}:"*) ;;
    *) PATH="${candidate}:${PATH}" ;;
  esac
}

resolve_cli_path() {
  local explicit_path="${1:-}"
  shift || true
  if [[ -n "${explicit_path}" && -f "${explicit_path}" ]]; then
    printf '%s\n' "${explicit_path}"
    return 0
  fi
  local name
  for name in "$@"; do
    if command -v "${name}" >/dev/null 2>&1; then
      command -v "${name}"
      return 0
    fi
  done
  return 1
}

bootstrap_cli_paths() {
  append_unique_path "${HOME}/.local/bin"
  append_unique_path "/usr/local/bin"
  append_unique_path "/opt/homebrew/bin"

  if command -v npm >/dev/null 2>&1; then
    local npm_bin
    npm_bin="$(npm bin -g 2>/dev/null || true)"
    append_unique_path "${npm_bin}"
  fi
}

HOST="${MISSION_CONTROL_BACKEND_HOST:-127.0.0.1}"
PORT="${MISSION_CONTROL_BACKEND_PORT:-8010}"
if [[ -f "${CONFIG_PATH}" ]]; then
  HOST="${MISSION_CONTROL_BACKEND_HOST:-$("${PYTHON_BIN}" - <<'PY' "${CONFIG_PATH}"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as handle:
    payload = json.load(handle)
print(payload.get('host', '127.0.0.1'))
PY
)}"
  PORT="${MISSION_CONTROL_BACKEND_PORT:-$("${PYTHON_BIN}" - <<'PY' "${CONFIG_PATH}"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as handle:
    payload = json.load(handle)
print(payload.get('backendPort', 8010))
PY
)}"
fi

assert_local_host "${HOST}"
HEALTH_URL="http://${HOST}:${PORT}/api/health"
mkdir -p "${LAUNCHER_DIR}"

bootstrap_cli_paths
CODEX_CLI_PATH="${MISSION_CONTROL_CODEX_PATH:-${CODEX_CLI_PATH:-}}"
CLAUDE_CLI_PATH="${MISSION_CONTROL_CLAUDE_PATH:-${CLAUDE_CLI_PATH:-}}"
RESOLVED_CODEX_PATH="$(resolve_cli_path "${CODEX_CLI_PATH}" codex codex.exe codex.cmd || true)"
RESOLVED_CLAUDE_PATH="$(resolve_cli_path "${CLAUDE_CLI_PATH}" claude claude.cmd claude.exe || true)"

cat >"${LAUNCH_LOG_PATH}" <<EOF
generated_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
repo_root=${REPO_ROOT}
backend_host=${HOST}
backend_port=${PORT}
python_bin=${PYTHON_BIN}
server_script=${REPO_ROOT}/apps/server/src/mission_control_daemon.py
codex_cli_path=${RESOLVED_CODEX_PATH}
claude_cli_path=${RESOLVED_CLAUDE_PATH}
stdout_path=${STDOUT_PATH}
stderr_path=${STDERR_PATH}
EOF

health_check() {
  "${PYTHON_BIN}" - <<'PY' "${1}"
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
        ok = response.status == 200 and b'"status"' in response.read()
except Exception:
    ok = False
sys.exit(0 if ok else 1)
PY
}

if health_check "${HEALTH_URL}"; then
  echo "[Mission Control] Daemon already healthy at ${HEALTH_URL}"
  exit 0
fi

if "${PYTHON_BIN}" - <<'PY' "${HOST}" "${PORT}"
import socket, sys
host = sys.argv[1]
port = int(sys.argv[2])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.75)
try:
    sys.exit(0 if sock.connect_ex((host, port)) == 0 else 1)
finally:
    sock.close()
PY
then
  echo "Port ${PORT} is already occupied on ${HOST}. Pick another backend port or stop the conflicting service first." >&2
  exit 1
fi

export MISSION_CONTROL_SERVER_MODE="daemon"
export MISSION_CONTROL_BACKEND_HOST="${HOST}"
export MISSION_CONTROL_BACKEND_PORT="${PORT}"
export MISSION_CONTROL_REPO_ROOT="${REPO_ROOT}"
if [[ -n "${RESOLVED_CODEX_PATH}" ]]; then
  export MISSION_CONTROL_CODEX_PATH="${RESOLVED_CODEX_PATH}"
fi
if [[ -n "${RESOLVED_CLAUDE_PATH}" ]]; then
  export MISSION_CONTROL_CLAUDE_PATH="${RESOLVED_CLAUDE_PATH}"
fi

nohup "${PYTHON_BIN}" -u "${REPO_ROOT}/apps/server/src/mission_control_daemon.py" \
  >"${STDOUT_PATH}" \
  2>"${STDERR_PATH}" &
DAEMON_PID=$!

for _ in $(seq 1 60); do
  if health_check "${HEALTH_URL}"; then
    break
  fi
  if ! kill -0 "${DAEMON_PID}" >/dev/null 2>&1; then
    echo "Mission Control daemon exited before becoming healthy." >&2
    tail -n 20 "${STDERR_PATH}" 2>/dev/null || true
    tail -n 20 "${STDOUT_PATH}" 2>/dev/null || true
    exit 1
  fi
  sleep 0.5
done

if ! health_check "${HEALTH_URL}"; then
  echo "Mission Control daemon did not become healthy in time." >&2
  exit 1
fi

sleep 2
if ! kill -0 "${DAEMON_PID}" >/dev/null 2>&1; then
  echo "Mission Control daemon became briefly reachable and then exited." >&2
  tail -n 20 "${STDERR_PATH}" 2>/dev/null || true
  tail -n 20 "${STDOUT_PATH}" 2>/dev/null || true
  exit 1
fi

if ! health_check "${HEALTH_URL}"; then
  echo "Mission Control daemon passed the initial health check but did not stay reachable." >&2
  tail -n 20 "${STDERR_PATH}" 2>/dev/null || true
  tail -n 20 "${STDOUT_PATH}" 2>/dev/null || true
  exit 1
fi

if [[ -f "${METADATA_PATH}" ]]; then
  if ! "${PYTHON_BIN}" - <<'PY' "${METADATA_PATH}" "${REPO_ROOT}" "${HOST}" "${PORT}" "${DAEMON_PID}"
import json, sys
metadata_path, repo_root, host, port_text, pid_text = sys.argv[1:]
port = int(port_text)
pid = int(pid_text)
try:
    with open(metadata_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
except Exception:
    sys.exit(1)
if str(payload.get("host")) != host:
    sys.exit(1)
if int(payload.get("port") or 0) != port:
    sys.exit(1)
if str(payload.get("mode")) != "daemon":
    sys.exit(1)
repo_value = str(payload.get("repo_root") or "")
if repo_value and repo_value != repo_root:
    sys.exit(1)
if int(payload.get("pid") or 0) != pid:
    sys.exit(1)
sys.exit(0)
PY
  then
    echo "Mission Control daemon answered health checks, but daemon metadata did not validate the expected repo/host/port identity." >&2
    exit 1
  fi
fi

echo "[Mission Control] Daemon started on PID ${DAEMON_PID} at ${HEALTH_URL}"
