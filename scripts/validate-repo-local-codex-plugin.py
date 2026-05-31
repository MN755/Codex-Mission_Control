from __future__ import annotations

import json

from mission_control_bundle import (
    CANONICAL_ASSETS_DIR,
    CANONICAL_PLUGIN_MANIFEST,
    CANONICAL_README,
    REPO_LOCAL_MCP_DIR,
    REPO_LOCAL_PLUGIN_MANIFEST,
    REPO_LOCAL_PROMPTS_DIR,
    REPO_LOCAL_README,
    REPO_LOCAL_SKILLS_DIR,
    REPO_LOCAL_ASSETS_DIR,
    expected_prompt_stems,
)


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    canonical = _load_json(CANONICAL_PLUGIN_MANIFEST)
    repo_local = _load_json(REPO_LOCAL_PLUGIN_MANIFEST)
    errors: list[str] = []

    if repo_local.get("prompts") != canonical.get("prompts"):
        errors.append("Repo-local plugin prompt manifest drifted from canonical plugin.json.")
    if repo_local.get("resources") != canonical.get("resources"):
        errors.append("Repo-local plugin resource manifest drifted from canonical plugin.json.")
    if repo_local.get("skills") != canonical.get("skills"):
        errors.append("Repo-local plugin skill manifest drifted from canonical plugin.json.")
    if (repo_local.get("mcp") or {}).get("prompts_catalog") != "./mcp/prompts.json":
        errors.append("Repo-local plugin should use the local prompts catalog path.")
    if (repo_local.get("mcp") or {}).get("resources_catalog") != "./mcp/resources.json":
        errors.append("Repo-local plugin should use the local resources catalog path.")
    for filename in ("prompts.json", "resources.json"):
        if not (REPO_LOCAL_MCP_DIR / filename).exists():
            errors.append(f"Missing repo-local MCP catalog: {REPO_LOCAL_MCP_DIR / filename}")

    prompt_stems = {path.stem for path in REPO_LOCAL_PROMPTS_DIR.glob("*.md")}
    expected_stems = expected_prompt_stems()
    missing = sorted(expected_stems - prompt_stems)
    extra = sorted(prompt_stems - expected_stems)
    if missing:
        errors.append("Repo-local prompt bundle is missing prompt files: " + ", ".join(missing))
    if extra:
        errors.append("Repo-local prompt bundle has unsupported prompt files: " + ", ".join(extra))

    expected_skill_stems = {str(name) for name in list(canonical.get("skills") or [])}
    actual_skill_stems = {path.name for path in REPO_LOCAL_SKILLS_DIR.iterdir() if path.is_dir()} if REPO_LOCAL_SKILLS_DIR.exists() else set()
    missing_skills = sorted(expected_skill_stems - actual_skill_stems)
    extra_skills = sorted(actual_skill_stems - expected_skill_stems)
    if missing_skills:
        errors.append("Repo-local skill bundle is missing skill directories: " + ", ".join(missing_skills))
    if extra_skills:
        errors.append("Repo-local skill bundle has unsupported skill directories: " + ", ".join(extra_skills))

    for skill_name in sorted(expected_skill_stems):
        skill_file = REPO_LOCAL_SKILLS_DIR / skill_name / "SKILL.md"
        if not skill_file.exists():
            errors.append(f"Missing repo-local skill file: {skill_file}")

    if REPO_LOCAL_README.read_text(encoding="utf-8") != CANONICAL_README.read_text(encoding="utf-8"):
        errors.append("Repo-local plugin README drifted from canonical README.")

    expected_assets = {path.relative_to(CANONICAL_ASSETS_DIR) for path in CANONICAL_ASSETS_DIR.rglob("*") if path.is_file()}
    actual_assets = {path.relative_to(REPO_LOCAL_ASSETS_DIR) for path in REPO_LOCAL_ASSETS_DIR.rglob("*") if path.is_file()} if REPO_LOCAL_ASSETS_DIR.exists() else set()
    missing_assets = sorted(str(path) for path in expected_assets - actual_assets)
    extra_assets = sorted(str(path) for path in actual_assets - expected_assets)
    if missing_assets:
        errors.append("Repo-local asset bundle is missing files: " + ", ".join(missing_assets))
    if extra_assets:
        errors.append("Repo-local asset bundle has unsupported files: " + ", ".join(extra_assets))

    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1

    print(f"Validated repo-local Mission Control plugin bundle with {len(prompt_stems)} prompt files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
