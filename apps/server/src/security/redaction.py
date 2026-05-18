from __future__ import annotations

import re
from typing import Any


SECRET_KEY_HINTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "passwd",
    "authorization",
    "bearer",
    "private_key",
    "client_secret",
    "session_key",
)

TEXT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL), "[redacted private key]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer ***redacted***"),
    (re.compile(r"\bsk-proj-[A-Za-z0-9_-]{10,}\b"), "sk-proj-***redacted***"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"), "sk-***redacted***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "gh***redacted***"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "xox***redacted***"),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"), "AIza***redacted***"),
    (re.compile(r"\bya29\.[0-9A-Za-z\-_]+\b"), "ya29.***redacted***"),
    (re.compile(r"\bxai-[A-Za-z0-9_-]{10,}\b", re.IGNORECASE), "xai-***redacted***"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}\b", re.IGNORECASE), "sk-ant-***redacted***"),
]

ENV_ASSIGNMENT_PATTERN = re.compile(
    r"(?im)^(\s*(?:export\s+)?[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|AUTHORIZATION|BEARER|PRIVATE_KEY)[A-Z0-9_]*\s*[:=]\s*)(.+)$"
)
JSON_SECRET_PATTERN = re.compile(
    r'(?i)("?[A-Za-z0-9_.-]*(?:token|secret|password|api[_-]?key|authorization|private[_-]?key)[A-Za-z0-9_.-]*"?\s*:\s*")([^"]+)(")'
)
CLI_SECRET_PATTERN = re.compile(r"(?i)(--(?:password|token|api-key|secret)(?:=|\s+))(\S+)")


def _redact_short_secret(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return stripped
    if len(stripped) <= 8:
        return "***redacted***"
    return f"{stripped[:4]}***redacted***{stripped[-2:]}"


def redact_text(text: str) -> str:
    redacted = text
    for pattern, replacement in TEXT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    redacted = ENV_ASSIGNMENT_PATTERN.sub(r"\1***redacted***", redacted)
    redacted = JSON_SECRET_PATTERN.sub(r"\1***redacted***\3", redacted)
    redacted = CLI_SECRET_PATTERN.sub(r"\1***redacted***", redacted)
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(hint in lowered for hint in SECRET_KEY_HINTS):
                if isinstance(nested, str):
                    redacted[key] = _redact_short_secret(nested)
                else:
                    redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_value(nested)
        return redacted
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
