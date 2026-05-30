from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SKILLS_ROOT = ROOT / "plugins" / "mission-control" / "skills"
CODEX_SKILLS_ROOT = Path(os.environ.get("MISSION_CONTROL_CODEX_SKILLS_ROOT", str(ROOT / ".codex" / "skills")))
INDEX_PATH = ROOT / "plugins" / "mission-control" / "SKILL_INDEX.md"
DOC_PATH = ROOT / "docs" / "MISSION_CONTROL_SKILL_LIBRARY.md"
PLUGIN_MANIFEST = ROOT / "plugins" / "mission-control" / "plugin.json"
COMMANDS_ROOT = ROOT / "plugins" / "mission-control" / "commands"
SKILL_STALE_MARKERS = [
    "mission_control_open_dashboard",
    "mission-control://projects/current/",
    "mission-control://projects/{project_id}/events",
]

def _skill_directories(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {item.name for item in root.iterdir() if item.is_dir()}


def _count_line(path: Path) -> int | None:
    if not path.exists():
        return None
    match = re.search(r"Total indexed skills:\s*(\d+)", path.read_text(encoding="utf-8"))
    return int(match.group(1)) if match else None


def validate() -> list[str]:
    errors: list[str] = []
    index_content = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
    doc_content = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8")) if PLUGIN_MANIFEST.exists() else {}

    if not INDEX_PATH.exists():
        errors.append(f"Missing index: {INDEX_PATH}")
    if not DOC_PATH.exists():
        errors.append(f"Missing docs file: {DOC_PATH}")
    else:
        for phrase in [
            "Mission Control is the headless or background orchestrator.",
            "## How the library is grouped",
            "## How Codex should use these skills",
            "## Approval relay",
            "## Headless mode",
        ]:
            if phrase not in doc_content:
                errors.append(f"Docs missing phrase: {phrase}")

    manifest_skills = list(manifest.get("skills") or [])
    if not manifest_skills:
        errors.append("plugin.json is missing the shipped skills list")
        return errors
    if len(manifest_skills) != len(set(manifest_skills)):
        errors.append("plugin.json contains duplicate Mission Control skill names")

    expected_skills = set(manifest_skills)
    plugin_skill_dirs = _skill_directories(PLUGIN_SKILLS_ROOT)
    codex_skill_dirs = _skill_directories(CODEX_SKILLS_ROOT)

    missing_plugin_dirs = sorted(expected_skills - plugin_skill_dirs)
    if missing_plugin_dirs:
        errors.append(
            "plugins/mission-control/skills is missing shipped skills: " + ", ".join(missing_plugin_dirs)
        )
    extra_plugin_dirs = sorted(plugin_skill_dirs - expected_skills)
    if extra_plugin_dirs:
        errors.append(
            "plugins/mission-control/skills has unexpected extra directories: " + ", ".join(extra_plugin_dirs)
        )

    missing_codex_dirs = sorted(expected_skills - codex_skill_dirs)
    if missing_codex_dirs:
        errors.append(".codex/skills is missing shipped skills: " + ", ".join(missing_codex_dirs))
    extra_codex_dirs = sorted(codex_skill_dirs - expected_skills)
    if extra_codex_dirs:
        errors.append(".codex/skills has unexpected extra directories: " + ", ".join(extra_codex_dirs))

    for command_name in ((manifest.get("claude_code") or {}).get("primary_commands") or []):
        command_path = COMMANDS_ROOT / f"{command_name}.md"
        if not command_path.exists():
            errors.append(f"Missing Claude command file: {command_path}")

    for resource in manifest.get("resources", []):
        if resource.startswith("mission-control://orchestrations/"):
            errors.append(f"plugin.json still advertises an unscoped orchestration resource: {resource}")

    expected_index_count = len(expected_skills)
    actual_index_count = _count_line(INDEX_PATH)
    if actual_index_count is None:
        errors.append(f"Skill index is missing the total-count line: {INDEX_PATH}")
    elif actual_index_count != expected_index_count:
        errors.append(
            f"Skill index count drift: expected {expected_index_count}, found {actual_index_count}"
        )

    if f"all {expected_index_count} skills" not in doc_content:
        errors.append(
            f"Skill library docs do not mention the current shipped count ({expected_index_count})"
        )

    for skill_name in manifest_skills:
        plugin_skill_path = PLUGIN_SKILLS_ROOT / skill_name / "SKILL.md"
        codex_skill_path = CODEX_SKILLS_ROOT / skill_name / "SKILL.md"

        if not plugin_skill_path.exists():
            errors.append(f"Missing plugin skill file: {plugin_skill_path}")
            continue
        if not codex_skill_path.exists():
            errors.append(f"Missing .codex mirror skill file: {codex_skill_path}")
            continue

        plugin_content = plugin_skill_path.read_text(encoding="utf-8")
        codex_content = codex_skill_path.read_text(encoding="utf-8")

        if plugin_content != codex_content:
            errors.append(f".codex mirror drift for {skill_name}: {codex_skill_path} does not match plugin copy")

        if not plugin_content.strip():
            errors.append(f"Plugin skill file is empty: {plugin_skill_path}")
        if not codex_content.strip():
            errors.append(f".codex mirror skill file is empty: {codex_skill_path}")

        if plugin_content.startswith("---") and f"name: {skill_name}" not in plugin_content:
            errors.append(f"Frontmatter name mismatch in {plugin_skill_path}")
        for marker in SKILL_STALE_MARKERS:
            if marker in plugin_content:
                errors.append(f"Stale Mission Control reference {marker!r} found in {plugin_skill_path}")
        if f"`{skill_name}`" not in index_content:
            errors.append(f"Skill index missing {skill_name}")

    for marker in SKILL_STALE_MARKERS:
        if marker in index_content:
            errors.append(f"Stale Mission Control reference {marker!r} found in {INDEX_PATH}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        print(f"{len(errors)} validation error(s) found.")
        return 1
    manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    print(f"Validated {len(manifest.get('skills') or [])} Mission Control skills successfully across plugin and .codex mirrors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
