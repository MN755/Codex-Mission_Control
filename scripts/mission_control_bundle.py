from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PLUGIN_ROOT = ROOT / "plugins" / "mission-control"
CANONICAL_PLUGIN_MANIFEST = CANONICAL_PLUGIN_ROOT / "plugin.json"
CANONICAL_CODEX_PLUGIN_MANIFEST = CANONICAL_PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
CANONICAL_PROMPTS_CATALOG = CANONICAL_PLUGIN_ROOT / "mcp" / "prompts.json"
CANONICAL_RESOURCES_CATALOG = CANONICAL_PLUGIN_ROOT / "mcp" / "resources.json"
CANONICAL_PROMPTS_DIR = CANONICAL_PLUGIN_ROOT / "prompts"
CANONICAL_SKILLS_DIR = CANONICAL_PLUGIN_ROOT / "skills"
CANONICAL_README = CANONICAL_PLUGIN_ROOT / "README.md"
CANONICAL_ASSETS_DIR = CANONICAL_PLUGIN_ROOT / "assets"

REPO_LOCAL_PLUGIN_ROOT = ROOT / ".codex" / "plugins" / "mission-control"
REPO_LOCAL_PLUGIN_MANIFEST = REPO_LOCAL_PLUGIN_ROOT / "plugin.json"
REPO_LOCAL_PROMPTS_DIR = REPO_LOCAL_PLUGIN_ROOT / "prompts"
REPO_LOCAL_MCP_DIR = REPO_LOCAL_PLUGIN_ROOT / "mcp"
REPO_LOCAL_SKILLS_DIR = REPO_LOCAL_PLUGIN_ROOT / "skills"
REPO_LOCAL_CODEX_PLUGIN_MANIFEST = REPO_LOCAL_PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
REPO_LOCAL_README = REPO_LOCAL_PLUGIN_ROOT / "README.md"
REPO_LOCAL_ASSETS_DIR = REPO_LOCAL_PLUGIN_ROOT / "assets"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _copy_tree_exact(source: Path, target: Path) -> list[Path]:
    copied: list[Path] = []
    target.mkdir(parents=True, exist_ok=True)
    expected_rel_paths: set[Path] = set()

    for path in source.rglob("*"):
        relative = path.relative_to(source)
        expected_rel_paths.add(relative)
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied.append(destination)

    for path in sorted(target.rglob("*"), reverse=True):
        relative = path.relative_to(target)
        if relative not in expected_rel_paths:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    return copied


def load_plugin_manifest() -> dict[str, Any]:
    return _load_json(CANONICAL_PLUGIN_MANIFEST)


def load_prompt_catalog() -> list[dict[str, Any]]:
    payload = _load_json(CANONICAL_PROMPTS_CATALOG)
    return [dict(item) for item in list(payload.get("prompts") or [])]


def prompt_stems(prompt: dict[str, Any]) -> list[str]:
    names = [str(prompt["name"])]
    names.extend(str(alias) for alias in list(prompt.get("aliases") or []))
    return names


def expected_prompt_stems() -> set[str]:
    stems: set[str] = set()
    for prompt in load_prompt_catalog():
        stems.update(prompt_stems(prompt))
    return stems


def render_prompt_markdown(prompt: dict[str, Any], stem: str) -> str:
    canonical_name = str(prompt["name"])
    title = str(prompt.get("title") or canonical_name.replace("_", " ").replace("-", " ").title())
    description = str(prompt.get("description") or "").strip()
    tool_sequence = [str(item) for item in list(prompt.get("tool_sequence") or [])]
    resource_sequence = [str(item) for item in list(prompt.get("resource_sequence") or [])]
    safety = str(prompt.get("safety_notes") or "").strip()
    prompt_text = str(prompt.get("prompt_text") or "").strip()
    alias_notice = ""
    if stem != canonical_name:
        alias_notice = f"Alias for `{canonical_name}`.\n"

    lines = [
        f"# {title}",
        "",
        alias_notice.rstrip(),
        f"Canonical prompt: `{canonical_name}`",
        f"Invocation name: `{stem}`",
        "",
    ]
    if description:
        lines.extend(["## Purpose", "", description, ""])
    lines.extend(["## Tool Sequence", ""])
    lines.extend([f"- `{item}`" for item in tool_sequence] or ["- No explicit Mission Control tools are declared."])
    lines.extend(["", "## Resource Sequence", ""])
    lines.extend([f"- `{item}`" for item in resource_sequence] or ["- No explicit Mission Control resources are declared."])
    lines.extend(["", "## Safety Notes", "", safety or "Use safe summaries and surface pending approvals instead of inventing answers.", ""])
    lines.extend(["## Prompt Text", "", prompt_text or "No prompt text was declared.", ""])
    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def sync_prompt_markdown(prompt_root: Path) -> list[Path]:
    prompt_root.mkdir(parents=True, exist_ok=True)
    expected_files: set[str] = set()
    written: list[Path] = []
    for prompt in load_prompt_catalog():
        for stem in prompt_stems(prompt):
            expected_files.add(f"{stem}.md")
            target = prompt_root / f"{stem}.md"
            target.write_text(render_prompt_markdown(prompt, stem), encoding="utf-8")
            written.append(target)
    for existing in prompt_root.glob("*.md"):
        if existing.name not in expected_files:
            existing.unlink()
    return written


def sync_repo_local_plugin_bundle() -> dict[str, Any]:
    canonical_manifest = load_plugin_manifest()
    repo_local_manifest = _load_json(REPO_LOCAL_PLUGIN_MANIFEST)
    repo_local_manifest["display_name"] = canonical_manifest.get("display_name")
    repo_local_manifest["version"] = canonical_manifest.get("version")
    repo_local_manifest["status"] = canonical_manifest.get("status")
    repo_local_manifest["description"] = "Repo-local Codex plugin bundle for Mission Control headless orchestration."
    repo_local_manifest["notes"] = list(canonical_manifest.get("notes") or [])
    repo_local_manifest["skills"] = list(canonical_manifest.get("skills") or [])
    repo_local_manifest["prompts"] = list(canonical_manifest.get("prompts") or [])
    repo_local_manifest["resources"] = list(canonical_manifest.get("resources") or [])
    repo_local_manifest["assets"] = dict(canonical_manifest.get("assets") or {})
    repo_local_manifest.setdefault("mcp", {})
    repo_local_manifest["mcp"]["resources_catalog"] = "./mcp/resources.json"
    repo_local_manifest["mcp"]["prompts_catalog"] = "./mcp/prompts.json"
    _write_json(REPO_LOCAL_PLUGIN_MANIFEST, repo_local_manifest)

    REPO_LOCAL_MCP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CANONICAL_PROMPTS_CATALOG, REPO_LOCAL_MCP_DIR / "prompts.json")
    shutil.copy2(CANONICAL_RESOURCES_CATALOG, REPO_LOCAL_MCP_DIR / "resources.json")
    prompt_files = sync_prompt_markdown(REPO_LOCAL_PROMPTS_DIR)
    skill_files = _copy_tree_exact(CANONICAL_SKILLS_DIR, REPO_LOCAL_SKILLS_DIR)
    shutil.copy2(CANONICAL_CODEX_PLUGIN_MANIFEST, REPO_LOCAL_CODEX_PLUGIN_MANIFEST)
    shutil.copy2(CANONICAL_README, REPO_LOCAL_README)
    asset_files = _copy_tree_exact(CANONICAL_ASSETS_DIR, REPO_LOCAL_ASSETS_DIR)
    return {
        "manifest": str(REPO_LOCAL_PLUGIN_MANIFEST),
        "prompt_files": [str(path) for path in prompt_files],
        "skill_files": [str(path) for path in skill_files if path.name == "SKILL.md"],
        "skill_count": len(list(canonical_manifest.get("skills") or [])),
        "resources_catalog": str(REPO_LOCAL_MCP_DIR / "resources.json"),
        "prompts_catalog": str(REPO_LOCAL_MCP_DIR / "prompts.json"),
        "codex_plugin_manifest": str(REPO_LOCAL_CODEX_PLUGIN_MANIFEST),
        "readme": str(REPO_LOCAL_README),
        "asset_files": [str(path) for path in asset_files],
    }
