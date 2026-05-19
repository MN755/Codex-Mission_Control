from __future__ import annotations

import json
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any

from errors.registry import ErrorDefinition, get_error_definition
from security.redaction import redact_value


def _redaction_status(original: dict[str, Any], redacted: dict[str, Any]) -> str:
    return "redacted" if json.dumps(original, default=str, sort_keys=True) != json.dumps(redacted, default=str, sort_keys=True) else "clean"


@dataclass
class MissionControlError(Exception):
    code: str
    detail: str | None = None
    title: str | None = None
    severity: str | None = None
    breakpoint: str | None = None
    retryable: bool | None = None
    user_action_required: bool | None = None
    recommended_fix: str | None = None
    http_status: int | None = None
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    orchestration_id: int | None = None
    project_id: int | None = None
    runner: str | None = None
    safe_details: dict[str, Any] = field(default_factory=dict)
    caused_by: Exception | None = None
    instance: str | None = None

    def __post_init__(self) -> None:
        definition = get_error_definition(self.code)
        self.definition: ErrorDefinition = definition
        self.family = definition.family
        self.title = self.title or definition.title
        self.detail = self.detail or definition.default_detail
        self.severity = self.severity or definition.severity
        self.breakpoint = self.breakpoint or definition.default_breakpoint
        self.retryable = definition.retryable if self.retryable is None else self.retryable
        self.user_action_required = definition.user_action_required if self.user_action_required is None else self.user_action_required
        self.recommended_fix = self.recommended_fix or definition.recommended_fix
        self.http_status = self.http_status or definition.http_status
        original_safe_details = dict(self.safe_details or {})
        self.safe_details = dict(redact_value(original_safe_details) or {})
        self.redaction_status = _redaction_status(original_safe_details, self.safe_details)
        super().__init__(self.detail)

    @property
    def problem_type(self) -> str:
        return f"https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#{self.definition.docs_anchor}"

    def to_problem_details(self, *, instance: str | None = None) -> dict[str, Any]:
        payload = {
            "type": self.problem_type,
            "title": self.title,
            "status": self.http_status,
            "detail": self.detail,
            "instance": instance or self.instance or "",
            "code": self.code,
            "family": self.family,
            "severity": self.severity,
            "breakpoint": self.breakpoint,
            "retryable": bool(self.retryable),
            "user_action_required": bool(self.user_action_required),
            "recommended_fix": self.recommended_fix,
            "correlation_id": self.correlation_id,
            "orchestration_id": self.orchestration_id,
            "project_id": self.project_id,
            "runner": self.runner,
            "redaction_status": self.redaction_status,
            "safe_details": self.safe_details,
        }
        return payload

    def to_log_event(self) -> dict[str, Any]:
        stacktrace = traceback.format_exception(self.caused_by) if self.caused_by is not None else None
        return {
            "code": self.code,
            "family": self.family,
            "severity": self.severity,
            "breakpoint": self.breakpoint,
            "retryable": bool(self.retryable),
            "user_action_required": bool(self.user_action_required),
            "recommended_fix": self.recommended_fix,
            "correlation_id": self.correlation_id,
            "project_id": self.project_id,
            "orchestration_id": self.orchestration_id,
            "runner": self.runner,
            "redaction_status": self.redaction_status,
            "safe_details": self.safe_details,
            "exception.type": type(self.caused_by).__name__ if self.caused_by is not None else "MissionControlError",
            "exception.message": str(self.caused_by) if self.caused_by is not None else self.detail,
            "exception.stacktrace": "".join(stacktrace) if stacktrace else None,
        }


def as_mission_control_error(
    exc: Exception,
    *,
    code: str = "MC-UNKNOWN-UNEXPECTED-001",
    breakpoint: str | None = None,
    detail: str | None = None,
    safe_details: dict[str, Any] | None = None,
    project_id: int | None = None,
    orchestration_id: int | None = None,
    runner: str | None = None,
) -> MissionControlError:
    if isinstance(exc, MissionControlError):
        return exc
    return MissionControlError(
        code=code,
        detail=detail or str(exc) or None,
        breakpoint=breakpoint,
        safe_details=safe_details or {"original_exception_type": type(exc).__name__},
        project_id=project_id,
        orchestration_id=orchestration_id,
        runner=runner,
        caused_by=exc,
    )
