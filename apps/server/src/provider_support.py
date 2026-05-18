from __future__ import annotations

from typing import Literal


ProviderId = Literal["codex", "ollama", "openai_api", "anthropic_api", "xai_api", "claude_code", "custom"]


PROVIDER_LABELS: dict[str, str] = {
    "codex": "Codex",
    "ollama": "Ollama",
    "openai_api": "OpenAI API",
    "anthropic_api": "Anthropic API",
    "xai_api": "xAI API",
    "claude_code": "Claude Code",
    "custom": "Custom provider",
}

PROVIDER_ALIASES: dict[str, str] = {
    "external_adapter": "custom",
    "api": "openai_api",
    "openclaw": "custom",
    "claude": "claude_code",
}


def normalize_provider(value: str | None) -> str:
    if not value:
        return "codex"
    lowered = value.strip().lower()
    if lowered in PROVIDER_ALIASES:
        lowered = PROVIDER_ALIASES[lowered]
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
    return normalized in {"codex", "ollama", "custom"}


def provider_uses_adapter(provider: str) -> bool:
    return normalize_provider(provider) in {"ollama", "openai_api", "anthropic_api", "xai_api", "custom"}
