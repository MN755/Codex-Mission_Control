from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any


def discover_repo_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "plugins" / "mission-control" / "plugin.json").exists() and (parent / "README.md").exists():
            return parent
    return None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_bundled_json(filename: str) -> dict[str, Any]:
    package_files = resources.files("mission_control_mcp_server._bundled")
    return json.loads((package_files / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_plugin_manifest() -> dict[str, Any]:
    repo_root = discover_repo_root()
    if repo_root is not None:
        path = repo_root / "plugins" / "mission-control" / "plugin.json"
        if path.exists():
            return _load_json(path)
    return _load_bundled_json("plugin.json")


@lru_cache(maxsize=1)
def load_resource_catalog() -> dict[str, Any]:
    repo_root = discover_repo_root()
    if repo_root is not None:
        path = repo_root / "plugins" / "mission-control" / "mcp" / "resources.json"
        if path.exists():
            return _load_json(path)
    return _load_bundled_json("resources.json")


@lru_cache(maxsize=1)
def load_prompt_catalog() -> dict[str, Any]:
    repo_root = discover_repo_root()
    if repo_root is not None:
        path = repo_root / "plugins" / "mission-control" / "mcp" / "prompts.json"
        if path.exists():
            return _load_json(path)
    return _load_bundled_json("prompts.json")


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
