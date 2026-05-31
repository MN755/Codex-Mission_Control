from __future__ import annotations

import json
import importlib.util
import shutil
from pathlib import Path

import pytest


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_mission_control_skill_library_validates_cleanly(tmp_path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    mirror_root = tmp_path / "codex-skills"
    shutil.copytree(root / "plugins" / "mission-control" / "skills", mirror_root)
    monkeypatch.setenv("MISSION_CONTROL_CODEX_SKILLS_ROOT", str(mirror_root))
    module = _load_module(root / "scripts" / "validate-mission-control-skills.py", "validate_mission_control_skills")
    assert module.validate() == []


def test_skill_generator_fails_before_rewriting_when_manifest_inventory_drifts(tmp_path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    module = _load_module(root / "scripts" / "generate-mission-control-skills.py", "generate_mission_control_skills")

    plugin_root = tmp_path / "plugins" / "mission-control" / "skills"
    plugin_root.mkdir(parents=True, exist_ok=True)
    codex_root = tmp_path / ".codex" / "skills"
    codex_root.mkdir(parents=True, exist_ok=True)
    manifest_path = tmp_path / "plugin.json"
    manifest_path.write_text(json.dumps({"skills": ["alpha", "beta"]}), encoding="utf-8")

    monkeypatch.setattr(module, "PLUGIN_SKILLS_ROOT", plugin_root)
    monkeypatch.setattr(module, "CODEX_SKILLS_ROOT", codex_root)
    monkeypatch.setattr(module, "PLUGIN_MANIFEST", manifest_path)
    monkeypatch.setattr(module, "SKILLS", [{"name": "alpha", "description": "a", "purpose": "a", "use_when": [], "workflow": [], "tools": [], "resources": [], "output": [], "approval": "a", "never": [], "fallback": "a", "example": "a"}])
    monkeypatch.setattr(module, "GROUPED_SKILL_NAMES", {"alpha"})

    with pytest.raises(SystemExit, match="Generator inventory is stale relative to plugin.json"):
        module.main()

    assert list(plugin_root.iterdir()) == []
    assert list(codex_root.iterdir()) == []
