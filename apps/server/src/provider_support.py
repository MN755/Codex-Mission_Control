from __future__ import annotations

from typing import Literal


ProviderId = Literal["codex", "claude_code", "external_adapter"]


PROVIDER_LABELS: dict[str, str] = {
    "codex": "Codex",
    "claude_code": "Claude Code",
    "external_adapter": "External adapter",
}


def normalize_provider(value: str | None) -> str:
    if not value:
        return "codex"
    lowered = value.strip().lower()
    if lowered in PROVIDER_LABELS:
        return lowered
    return "codex"


def provider_label(provider: str) -> str:
    normalized = normalize_provider(provider)
    return PROVIDER_LABELS.get(normalized, "Provider")


def default_label(provider: str) -> str:
    return f"{provider_label(provider)} default"


def supports_app_server(provider: str) -> bool:
    return normalize_provider(provider) == "codex"


def supports_builtin_auth(provider: str) -> bool:
    return normalize_provider(provider) == "codex"


def supports_reasoning_effort(provider: str) -> bool:
    normalized = normalize_provider(provider)
    return normalized in {"codex", "external_adapter"}
