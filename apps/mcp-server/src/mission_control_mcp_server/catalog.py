from __future__ import annotations

import importlib.resources
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def discover_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "plugins" / "mission-control" / "plugin.json").exists() and (parent / "README.md").exists():
            return parent
    raise RuntimeError("Could not discover the Codex Mission Control repository root.")


def _load_bundled_json(filename: str) -> dict[str, Any]:
    package_files = importlib.resources.files("mission_control_mcp_server._bundled")
    text = (package_files / filename).read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Bundled Mission Control asset {filename} is not a JSON object.")
    return payload


def _load_repo_json(*parts: str) -> dict[str, Any] | None:
    try:
        path = discover_repo_root().joinpath(*parts)
    except RuntimeError:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_plugin_manifest() -> dict[str, Any]:
    return _load_repo_json("plugins", "mission-control", "plugin.json") or _load_bundled_json("plugin.json")


@lru_cache(maxsize=1)
def load_resource_catalog() -> dict[str, Any]:
    return _load_repo_json("plugins", "mission-control", "mcp", "resources.json") or _load_bundled_json("resources.json")


@lru_cache(maxsize=1)
def load_prompt_catalog() -> dict[str, Any]:
    return _load_repo_json("plugins", "mission-control", "mcp", "prompts.json") or _load_bundled_json("prompts.json")


def resource_entries() -> list[dict[str, Any]]:
    return list(load_resource_catalog().get("resources", []))


def prompt_entries() -> list[dict[str, Any]]:
    return list(load_prompt_catalog().get("prompts", []))


def prompt_entry(name: str) -> dict[str, Any]:
    for entry in prompt_entries():
        aliases = [str(alias) for alias in entry.get("aliases", [])]
        if entry["name"] == name or name in aliases:
            return entry
    raise RuntimeError(f"Unknown Mission Control prompt: {name}")
