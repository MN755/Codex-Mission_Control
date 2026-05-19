from __future__ import annotations

from typing import Any

from security.redaction import redact_text as _redact_text
from security.redaction import redact_value as _redact_value


def redact_bootstrap_text(text: str) -> str:
    return _redact_text(text)


def redact_bootstrap_value(value: Any) -> Any:
    return _redact_value(value)


def redaction_status(value: Any) -> str:
    return "redacted" if str(value) != str(_redact_value(value)) else "clean"
