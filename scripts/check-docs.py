from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS = ROOT / "docs"
WIKI = ROOT / "wiki-staging"

REQUIRED_FILES = [
    README,
    ROOT / "LICENSE",
    ROOT / "SECURITY.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "CHANGELOG.md",
    DOCS / "README.md",
    DOCS / "OVERVIEW.md",
    DOCS / "QUICK_START.md",
    DOCS / "HEADLESS_INSTALL.md",
    DOCS / "CODEX_CHAT_MODE.md",
    DOCS / "ARCHITECTURE.md",
    DOCS / "MCP_PLUGIN_BRIDGE.md",
    DOCS / "RUNNERS.md",
    DOCS / "ERROR_REGISTRY.md",
    DOCS / "AUTOWIRE_PROVIDERS.md",
    DOCS / "PENDING_DECISIONS.md",
    DOCS / "HANDOFFS.md",
    DOCS / "MISSION_CONTROL_SKILL_LIBRARY.md",
    DOCS / "MISSION_CONTROL_SKILLS.md",
    DOCS / "SECURITY.md",
    DOCS / "SKILL_PACK.md",
    DOCS / "TROUBLESHOOTING.md",
    DOCS / "PUBLIC_RELEASE_CHECKLIST.md",
]

README_FORBIDDEN = [
    "dashboard widget",
    "project workspace ui",
    "left sidebar",
    "right sidebar",
    "widget-heavy",
    "dashboard as main product",
]

STATUS_PREFIX = "> Status:"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def content(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_required_files(errors: list[str]) -> None:
    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")


def check_readme(errors: list[str]) -> None:
    text = content(README).lower()
    for phrase in README_FORBIDDEN:
        if phrase in text:
            errors.append(f"README contains forbidden phrase: {phrase}")


def iter_markdown_files() -> list[Path]:
    files = [README]
    files.extend(sorted(DOCS.glob("*.md")))
    if WIKI.exists():
        files.extend(sorted(WIKI.glob("*.md")))
    return files


def resolve_link(source: Path, target: str) -> Path | None:
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return None
    clean_target = target.split("#", 1)[0].strip().strip("<>")
    if not clean_target:
        return None
    drive_match = re.match(r"^/[A-Za-z]:/", clean_target)
    if drive_match:
        resolved = Path(clean_target[1:])
    else:
        resolved = (source.parent / clean_target).resolve()
    if not resolved.exists() and source.parent == WIKI and resolved.suffix == "":
        wiki_resolved = resolved.with_suffix(".md")
        if wiki_resolved.exists():
            return wiki_resolved
    return resolved


def check_links(errors: list[str]) -> None:
    for path in iter_markdown_files():
        text = content(path)
        for match in LINK_RE.finditer(text):
            target = match.group(1).strip()
            resolved = resolve_link(path, target)
            if resolved is None:
                continue
            if not resolved.exists():
                try:
                    rel_source = path.relative_to(ROOT)
                except ValueError:
                    rel_source = path
                errors.append(f"broken link in {rel_source}: {target}")


def check_wiki_status_labels(errors: list[str]) -> None:
    if not WIKI.exists():
        return
    for path in sorted(WIKI.glob("*.md")):
        if path.name.startswith("_") or path.name == "PUSH-TO-GITHUB-WIKI.md":
            continue
        lines = content(path).splitlines()
        if len(lines) < 2 or STATUS_PREFIX not in "\n".join(lines[:6]):
            errors.append(f"missing wiki status label: {path.relative_to(ROOT)}")


def check_generated_exports(errors: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export-error-registry.py"), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stdout.strip() or result.stderr.strip() or "generated export check failed"
        errors.append(message)


def check_skill_pack_docs(errors: list[str]) -> None:
    skills_doc = content(DOCS / "MISSION_CONTROL_SKILLS.md")
    skill_pack_doc = content(DOCS / "SKILL_PACK.md")
    library_doc = content(DOCS / "MISSION_CONTROL_SKILL_LIBRARY.md")

    lowered_skills = skills_doc.lower()
    lowered_pack = skill_pack_doc.lower()
    if "ten-skill" in lowered_skills and not any(token in lowered_skills for token in ("retired", "stale", "older references")):
        errors.append("docs/MISSION_CONTROL_SKILLS.md still references the retired ten-skill pack")
    if "ten-skill" in lowered_pack and not any(token in lowered_pack for token in ("retired", "stale", "older references")):
        errors.append("docs/SKILL_PACK.md still references the retired ten-skill pack")
    if "MISSION_CONTROL_SKILL_LIBRARY.md" not in skills_doc:
        errors.append("docs/MISSION_CONTROL_SKILLS.md must point readers at docs/MISSION_CONTROL_SKILL_LIBRARY.md")
    if "SKILL_INDEX.md" not in skills_doc or "SKILL_INDEX.md" not in skill_pack_doc:
        errors.append("Skill compatibility docs must point readers at plugins/mission-control/SKILL_INDEX.md")
    if "all " not in library_doc or "skills" not in library_doc:
        errors.append("docs/MISSION_CONTROL_SKILL_LIBRARY.md appears to be missing the current shipped-skill summary")


def main() -> int:
    errors: list[str] = []
    check_required_files(errors)
    check_readme(errors)
    check_links(errors)
    check_wiki_status_labels(errors)
    check_generated_exports(errors)
    check_skill_pack_docs(errors)

    if errors:
        print("Documentation checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Documentation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
