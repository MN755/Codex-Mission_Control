from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from config import REPO_ROOT
from provider_support import normalize_provider, provider_uses_adapter


@dataclass(frozen=True)
class AdapterRecipe:
    provider: str
    command: str
    args: list[str]
    source: str


_BUILTIN_ADAPTER_SCRIPTS = {
    "ollama": REPO_ROOT / "scripts" / "ollama_adapter.py",
    "openai_api": REPO_ROOT / "scripts" / "api_provider_adapter.py",
    "anthropic_api": REPO_ROOT / "scripts" / "api_provider_adapter.py",
    "xai_api": REPO_ROOT / "scripts" / "api_provider_adapter.py",
}


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_args(values: list[str] | None) -> list[str]:
    return [item.strip() for item in list(values or []) if item and item.strip()]


def default_adapter_recipe(provider: str) -> AdapterRecipe | None:
    normalized = normalize_provider(provider)
    script_path = _BUILTIN_ADAPTER_SCRIPTS.get(normalized)
    if not script_path:
        return None
    return AdapterRecipe(
        provider=normalized,
        command=str(Path(sys.executable).resolve()),
        args=[str(script_path.resolve())],
        source="builtin",
    )


def resolve_adapter_recipe(provider: str, command: str | None = None, args: list[str] | None = None) -> AdapterRecipe | None:
    normalized = normalize_provider(provider)
    if not provider_uses_adapter(normalized):
        return None
    normalized_command = _normalize_text(command)
    normalized_args = _normalize_args(args)
    if normalized_command:
        return AdapterRecipe(
            provider=normalized,
            command=normalized_command,
            args=normalized_args,
            source="explicit",
        )
    return default_adapter_recipe(normalized)

