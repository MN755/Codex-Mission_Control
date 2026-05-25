#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python is required to run Mission Control headless health checks." >&2
  exit 1
fi

exec "${PYTHON_BIN}" "${REPO_ROOT}/scripts/mission-control-bootstrap.py" --install-path "${REPO_ROOT}" --health-check-only "$@"
