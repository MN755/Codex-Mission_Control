from __future__ import annotations

import importlib.resources
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "plugins" / "mission-control" / "plugin.json").exists() and (parent / "README.md").exists():
            return parent
    return None


def discover_repo_root() -> Path:
    repo_root = _find_repo_root()
    if repo_root is not None:
        return repo_root
    raise RuntimeError("Could not discover the Codex Mission Control repository root.")


def _load_packaged_json(name: str) -> dict[str, Any]:
    asset = importlib.resources.files("mission_control_mcp_server").joinpath("assets", name)
    return json.loads(asset.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_plugin_manifest() -> dict[str, Any]:
    repo_root = _find_repo_root()
    if repo_root is not None:
        path = repo_root / "plugins" / "mission-control" / "plugin.json"
        return json.loads(path.read_text(encoding="utf-8"))
    return _load_packaged_json("plugin.json")


@lru_cache(maxsize=1)
def load_resource_catalog() -> dict[str, Any]:
    repo_root = _find_repo_root()
    if repo_root is not None:
        path = repo_root / "plugins" / "mission-control" / "mcp" / "resources.json"
        return json.loads(path.read_text(encoding="utf-8"))
    return _load_packaged_json("resources.json")


@lru_cache(maxsize=1)
def load_prompt_catalog() -> dict[str, Any]:
    repo_root = _find_repo_root()
    if repo_root is not None:
        path = repo_root / "plugins" / "mission-control" / "mcp" / "prompts.json"
        return json.loads(path.read_text(encoding="utf-8"))
    return _load_packaged_json("prompts.json")


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
