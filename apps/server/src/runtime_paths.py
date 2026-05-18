from __future__ import annotations

from pathlib import Path

from config import APP_SUPPORT_ROOT, LAUNCHER_ROOT, RUNTIME_LOGS_ROOT, RUNTIME_ROOT, RUNNING_FROM_SOURCE, WORKSPACE_ROOT, WORKTREE_ROOT, ensure_runtime_dirs


def ensure_runtime_paths() -> dict[str, str]:
    ensure_runtime_dirs()
    return runtime_path_payload()


def runtime_path_payload() -> dict[str, str]:
    payload = {
        "runtime_root": str(RUNTIME_ROOT),
        "logs_root": str(RUNTIME_LOGS_ROOT),
        "worktree_root": str(WORKTREE_ROOT),
        "workspace_root": str(WORKSPACE_ROOT),
        "launcher_root": str(LAUNCHER_ROOT),
    }
    if not RUNNING_FROM_SOURCE:
        payload["app_support_root"] = str(APP_SUPPORT_ROOT)
    return payload


def diagnostics_root() -> Path:
    root = RUNTIME_ROOT / "diagnostics"
    root.mkdir(parents=True, exist_ok=True)
    return root
