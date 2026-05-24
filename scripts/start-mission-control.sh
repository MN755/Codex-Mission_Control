#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DESKTOP_SRC="${REPO_ROOT}/apps/desktop/src"
SERVER_SRC="${REPO_ROOT}/apps/server/src"
FRONTEND_DIR="${REPO_ROOT}/apps/dashboard"
FRONTEND_DIST="${FRONTEND_DIR}/dist"
CONFIG_PATH="${SCRIPT_DIR}/mission-control.config.json"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python 3 was not found on PATH." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm was not found on PATH." >&2
  exit 1
fi

echo "[Mission Control] Building the desktop frontend bundle..."
(cd "${FRONTEND_DIR}" && npm run build)

if [[ ! -d "${FRONTEND_DIST}" ]]; then
  echo "Frontend build output is missing at ${FRONTEND_DIST}" >&2
  exit 1
fi

LAUNCHER_DIR="$("${PYTHON_BIN}" - <<'PY' "${REPO_ROOT}" "${CONFIG_PATH}"
from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
config_path = Path(sys.argv[2])
launcher_dir = ".runtime/launcher"
if config_path.exists():
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict):
        launcher_dir = str(payload.get("launcherLogDir") or launcher_dir)
print((repo_root / launcher_dir).resolve())
PY
)"
mkdir -p "${LAUNCHER_DIR}"

export PYTHONPATH="${DESKTOP_SRC}:${SERVER_SRC}:${PYTHONPATH:-}"
export MISSION_CONTROL_FRONTEND_DIST="${FRONTEND_DIST}"
export MISSION_CONTROL_LAUNCHER_DIR="${LAUNCHER_DIR}"

echo "[Mission Control] Launching the desktop app..."
cd "${REPO_ROOT}"
"${PYTHON_BIN}" -m mission_control_desktop
