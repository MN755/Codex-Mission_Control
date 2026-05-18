from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import LAUNCHER_ROOT, RUNTIME_LOGS_ROOT
from runtime_paths import diagnostics_root, runtime_path_payload


SENSITIVE_ENV_KEYS = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY", "CODEX_API_KEY"}


def _tail(path: Path, max_lines: int = 40) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()[-max_lines:]
    except OSError:
        return []


def _redact_value(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("sk-"):
        return "sk-***redacted***"
    if len(stripped) > 16:
        return f"{stripped[:4]}***redacted***{stripped[-2:]}"
    return "***redacted***"


def _sanitized_environment() -> dict[str, str]:
    payload: dict[str, str] = {}
    for key in sorted(SENSITIVE_ENV_KEYS):
        if key in os.environ:
            payload[key] = _redact_value(os.environ[key])
    return payload


def write_diagnostic_report(
    *,
    startup_status: dict[str, Any],
    system_status: dict[str, Any],
    settings_status: dict[str, Any] | None,
    recent_errors: dict[str, Any] | None,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc)
    stamp = timestamp.strftime("%Y%m%d-%H%M%S")
    report_dir = diagnostics_root()
    markdown_path = report_dir / f"diagnostic-{stamp}.md"
    json_path = report_dir / f"diagnostic-{stamp}.json"

    launcher_logs = []
    if LAUNCHER_ROOT.exists():
        for name in ("backend.stdout.log", "frontend.stdout.log", "desktop.stdout.log"):
            launcher_logs.extend(_tail(LAUNCHER_ROOT / name, max_lines=10))

    runtime_logs = []
    if RUNTIME_LOGS_ROOT.exists():
        log_files = sorted(RUNTIME_LOGS_ROOT.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
        for path in log_files[:3]:
            runtime_logs.append({"path": str(path), "tail": _tail(path, max_lines=10)})

    recommended_fixes = []
    for check in startup_status.get("checks", []):
        if check.get("status") == "failed":
            recommended_fixes.append(f"Review the `{check.get('name')}` check: {check.get('summary')}")
    if not recommended_fixes:
        recommended_fixes.append("Review optional provider checks and confirm the selected local runner is installed.")

    payload = {
        "timestamp": timestamp.isoformat(),
        "startup_status": startup_status,
        "system_status": system_status,
        "settings_status": settings_status,
        "recent_errors": recent_errors,
        "platform": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "python": sys.version,
            "node_detected": bool(shutil.which("node")),
            "npm_detected": bool(shutil.which("npm") or shutil.which("npm.cmd")),
        },
        "runtime_paths": runtime_path_payload(),
        "sanitized_environment": _sanitized_environment(),
        "recent_launcher_logs": launcher_logs,
        "recent_runtime_logs": runtime_logs,
        "recommended_fixes": recommended_fixes,
    }

    markdown = [
        "# Mission Control Diagnostic Report",
        "",
        f"- Timestamp: {payload['timestamp']}",
        f"- Startup mode: {startup_status.get('mode')}",
        f"- Overall status: {startup_status.get('overall_status')}",
        f"- Error code: {startup_status.get('error_code') or 'None'}",
        "",
        "## Failed checks",
        "",
    ]
    failed_checks = [check for check in startup_status.get("checks", []) if check.get("status") == "failed"]
    if failed_checks:
        markdown.extend(
            [
                f"- `{check.get('name')}`: {check.get('summary')} ({check.get('error_code') or 'no code'})"
                for check in failed_checks
            ]
        )
    else:
        markdown.append("- No failed checks were recorded.")
    markdown.extend(
        [
            "",
            "## Required checks",
            "",
        ]
    )
    for check in startup_status.get("checks", []):
        marker = "required" if check.get("required") else "optional"
        markdown.append(f"- `{check.get('name')}` [{marker}]: {check.get('status')} - {check.get('summary')}")
    markdown.extend(
        [
            "",
            "## Runtime paths",
            "",
        ]
    )
    markdown.extend([f"- {key}: `{value}`" for key, value in runtime_path_payload().items()])
    markdown.extend(
        [
            "",
            "## Provider status",
            "",
            f"- Selected provider: {system_status.get('selected_provider_label')}",
            f"- CLI detected: {system_status.get('cli_detected')}",
            f"- Login status: {system_status.get('login_status')}",
            f"- App-server handshake: {system_status.get('app_server_handshake_status')}",
            "",
            "## Recommended fixes",
            "",
        ]
    )
    markdown.extend([f"- {fix}" for fix in recommended_fixes])
    markdown.extend(
        [
            "",
            "## Recent launcher logs",
            "",
            "```text",
            *launcher_logs[-30:],
            "```",
            "",
        ]
    )

    markdown_path.write_text("\n".join(markdown).strip() + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return {
        "path": str(markdown_path),
        "json_path": str(json_path),
        "summary": startup_status.get("error_summary") or startup_status.get("overall_status") or "Diagnostic report generated.",
        "error_code": startup_status.get("error_code"),
        "recommended_fixes": recommended_fixes,
    }


def open_folder(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"ok": False, "path": str(target), "message": "Path does not exist."}
    try:
        if sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": str(target), "message": str(exc)}
    return {"ok": True, "path": str(target), "message": "Opened diagnostics folder."}


def list_diagnostic_reports() -> list[dict[str, Any]]:
    report_dir = diagnostics_root()
    items: list[dict[str, Any]] = []
    for path in sorted(report_dir.glob("diagnostic-*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        json_path = path.with_suffix(".json")
        summary = "Diagnostic report"
        error_code: str | None = None
        created_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if json_path.exists():
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                summary = str(
                    payload.get("startup_status", {}).get("error_summary")
                    or payload.get("startup_status", {}).get("overall_status")
                    or summary
                )
                error_code = payload.get("startup_status", {}).get("error_code")
                timestamp = payload.get("timestamp")
                if isinstance(timestamp, str):
                    created_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (OSError, json.JSONDecodeError, ValueError):
                pass
        items.append(
            {
                "path": str(path),
                "json_path": str(json_path) if json_path.exists() else None,
                "created_at": created_at,
                "error_code": error_code,
                "summary": summary,
            }
        )
    return items
