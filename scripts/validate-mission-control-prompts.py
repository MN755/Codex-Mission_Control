from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PROMPTS_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "prompts.json"
CANONICAL_PROMPTS_DIR = ROOT / "plugins" / "mission-control" / "prompts"
REPO_LOCAL_PROMPTS_DIR = ROOT / ".codex" / "plugins" / "mission-control" / "prompts"


def _load_prompt_entries() -> list[dict]:
    payload = json.loads(CANONICAL_PROMPTS_CATALOG.read_text(encoding="utf-8"))
    return [dict(entry) for entry in list(payload.get("prompts") or [])]


def _expected_prompt_stems() -> set[str]:
    stems: set[str] = set()
    for entry in _load_prompt_entries():
        stems.add(str(entry["name"]))
        stems.update(str(alias) for alias in list(entry.get("aliases") or []))
    return stems


def _validate_prompt_directory(prompt_root: Path, *, label: str, errors: list[str]) -> None:
    actual = {path.stem for path in prompt_root.glob("*.md")}
    expected = _expected_prompt_stems()
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{label} is missing prompt files: {', '.join(missing)}")
    if extra:
        errors.append(f"{label} has unsupported prompt files: {', '.join(extra)}")


def validate() -> list[str]:
    errors: list[str] = []
    _validate_prompt_directory(CANONICAL_PROMPTS_DIR, label="plugins/mission-control/prompts", errors=errors)
    _validate_prompt_directory(REPO_LOCAL_PROMPTS_DIR, label=".codex/plugins/mission-control/prompts", errors=errors)

    for entry in _load_prompt_entries():
        canonical_path = CANONICAL_PROMPTS_DIR / f"{entry['name']}.md"
        if not canonical_path.exists():
            errors.append(f"Missing canonical prompt file: {canonical_path}")
            continue
        canonical_text = canonical_path.read_text(encoding="utf-8")
        if not canonical_text.strip():
            errors.append(f"Canonical prompt file is empty: {canonical_path}")
            continue
        for alias in list(entry.get("aliases") or []):
            alias_path = CANONICAL_PROMPTS_DIR / f"{alias}.md"
            if not alias_path.exists():
                errors.append(f"Missing canonical alias prompt file: {alias_path}")
                continue
            alias_text = alias_path.read_text(encoding="utf-8")
            if f"Canonical prompt: `{entry['name']}`" not in alias_text:
                errors.append(f"Alias prompt missing canonical prompt marker: {alias_path}")
            if f"Invocation name: `{alias}`" not in alias_text:
                errors.append(f"Alias prompt missing invocation marker: {alias_path}")
            if canonical_text.split("## Tool Sequence", 1)[1] != alias_text.split("## Tool Sequence", 1)[1]:
                errors.append(f"Alias prompt drifted from canonical contract: {alias_path}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        print(f"{len(errors)} validation error(s) found.")
        return 1
    print(f"Validated {len(_expected_prompt_stems())} Mission Control prompt markdown files across canonical and repo-local bundles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
