from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path


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
