from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from errors.problem import MissionControlError
from errors.severity import HEALTH_STATUS_BY_SEVERITY


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_problem_details(error: MissionControlError, *, instance: str | None = None) -> dict[str, Any]:
    return error.to_problem_details(instance=instance)


def format_codex_chat_error(error: MissionControlError) -> str:
    safe_lines = []
    for key, value in error.safe_details.items():
        rendered = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
        safe_lines.append(f"- {key.replace('_', ' ').title()}: {rendered}")
    if not safe_lines:
        safe_lines.append("- No additional safe details were recorded.")
    return "\n".join(
        [
            f"## Mission Control Error: {error.code}",
            "",
            f"**Where:** {error.breakpoint}",
            f"**Severity:** {error.severity}",
            f"**User action required:** {'Yes' if error.user_action_required else 'No'}",
            f"**Retryable:** {'Yes' if error.retryable else 'No'}",
            "",
            "### What happened",
            error.detail or error.title or "Mission Control reported an error.",
            "",
            "### Recommended fix",
            error.recommended_fix or "Inspect the correlation ID and retry after checking local diagnostics.",
            "",
            "### Safe details",
            *safe_lines,
        ]
    )


def format_log_event(error: MissionControlError) -> dict[str, Any]:
    return error.to_log_event()


def format_diagnostic_report_item(error: MissionControlError) -> dict[str, Any]:
    return {
        "code": error.code,
        "title": error.title,
        "severity": error.severity,
        "breakpoint": error.breakpoint,
        "recommended_fix": error.recommended_fix,
        "user_action_required": bool(error.user_action_required),
        "correlation_id": error.correlation_id,
        "redaction_status": error.redaction_status,
        "safe_details": error.safe_details,
    }


def format_install_report_item(error: MissionControlError) -> dict[str, Any]:
    return {
        "code": error.code,
        "summary": error.detail,
        "severity": error.severity,
        "recommended_fix": error.recommended_fix,
        "user_action_required": bool(error.user_action_required),
        "retryable": bool(error.retryable),
        "breakpoint": error.breakpoint,
    }


def format_health_check_item(
    *,
    check_id: str,
    label: str,
    status: str,
    summary: str,
    critical: bool,
    error: MissionControlError | None = None,
    fix: str | None = None,
    commands: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recommended_fix = fix or (error.recommended_fix if error is not None else None)
    payload = {
        "key": check_id,
        "label": label,
        "status": status,
        "summary": summary,
        "recommended_fix": recommended_fix,
        "details_json": dict(details or (error.safe_details if error is not None else {})),
        "checked_at": _utc_now(),
        "critical": critical,
        "commands": list(commands or []),
        "code": error.code if error is not None else None,
        "family": error.family if error is not None else None,
        "severity": error.severity if error is not None else None,
        "breakpoint": error.breakpoint if error is not None else None,
        "retryable": bool(error.retryable) if error is not None else None,
        "user_action_required": bool(error.user_action_required) if error is not None else None,
        "correlation_id": error.correlation_id if error is not None else None,
        "redaction_status": error.redaction_status if error is not None else "clean",
    }
    return payload


def derive_health_status(error: MissionControlError, *, critical: bool) -> str:
    derived = HEALTH_STATUS_BY_SEVERITY.get(error.severity or "error", "broken")
    if critical and derived == "degraded":
        return "broken"
    return derived
