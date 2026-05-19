from __future__ import annotations


SEVERITY_LEVELS = ("debug", "info", "warning", "error", "fatal")

USER_STATUS_BY_SEVERITY: dict[str, str] = {
    "debug": "ready",
    "info": "ready",
    "warning": "degraded",
    "error": "failed",
    "fatal": "fatal",
}

HEALTH_STATUS_BY_SEVERITY: dict[str, str] = {
    "debug": "unknown",
    "info": "ready",
    "warning": "degraded",
    "error": "broken",
    "fatal": "broken",
}


def normalize_severity(value: str) -> str:
    lowered = str(value or "error").strip().lower()
    return lowered if lowered in SEVERITY_LEVELS else "error"
