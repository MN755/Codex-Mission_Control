from __future__ import annotations

import uuid
from pathlib import Path

from config import (
    APP_SUPPORT_ROOT,
    DAEMON_METADATA_PATH,
    DAEMON_TOKEN_PATH,
    DB_PATH,
    LAUNCHER_ROOT,
    RUNTIME_LOGS_ROOT,
    RUNTIME_ROOT,
    RUNNING_FROM_SOURCE,
    WORKSPACE_ROOT,
    WORKTREE_ROOT,
    ensure_runtime_dirs,
)


def ensure_runtime_paths() -> dict[str, str]:
    ensure_runtime_dirs()
    _verify_directory_writable(diagnostics_root())
    return runtime_path_payload()


def runtime_path_payload() -> dict[str, str]:
    payload = {
        "runtime_root": str(RUNTIME_ROOT),
        "logs_root": str(RUNTIME_LOGS_ROOT),
        "worktree_root": str(WORKTREE_ROOT),
        "workspace_root": str(WORKSPACE_ROOT),
        "launcher_root": str(LAUNCHER_ROOT),
        "diagnostics_root": str(diagnostics_root()),
        "db_path": str(DB_PATH),
        "daemon_metadata_path": str(DAEMON_METADATA_PATH),
        "daemon_token_path": str(DAEMON_TOKEN_PATH),
    }
    if not RUNNING_FROM_SOURCE:
        payload["app_support_root"] = str(APP_SUPPORT_ROOT)
    return payload


def diagnostics_root() -> Path:
    root = RUNTIME_ROOT / "diagnostics"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _verify_directory_writable(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / f".write-probe-{uuid.uuid4().hex}.tmp"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
