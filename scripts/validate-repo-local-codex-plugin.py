from __future__ import annotations

import json

from mission_control_bundle import (
    CANONICAL_PLUGIN_MANIFEST,
    REPO_LOCAL_MCP_DIR,
    REPO_LOCAL_PLUGIN_MANIFEST,
    REPO_LOCAL_PROMPTS_DIR,
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

    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1

    print(f"Validated repo-local Mission Control plugin bundle with {len(prompt_stems)} prompt files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
