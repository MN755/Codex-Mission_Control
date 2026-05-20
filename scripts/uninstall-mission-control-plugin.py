from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any


def resolve_codex_home(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return Path.home().joinpath(".codex").resolve()


def _remove_tree(path: Path, *, dry_run: bool) -> bool:
    if not path.exists():
        return False
    if dry_run:
        return True
    shutil.rmtree(path)
    return True


def uninstall_plugin_bundle(codex_home: Path, *, dry_run: bool = False) -> dict[str, Any]:
    plugin_path = codex_home / "plugins" / "mission-control"
    skills_root = codex_home / "skills"
    removed_skills: list[str] = []

    plugin_removed = _remove_tree(plugin_path, dry_run=dry_run)
    if skills_root.exists():
        for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir() and path.name.startswith("mission-control")):
            if _remove_tree(skill_dir, dry_run=dry_run):
                removed_skills.append(skill_dir.name)

    return {
        "codex_home": str(codex_home),
        "dry_run": dry_run,
        "plugin_path": str(plugin_path),
        "plugin_removed": plugin_removed,
        "removed_skills": removed_skills,
        "removed_skill_count": len(removed_skills),
        "status": "ready" if plugin_removed or removed_skills else "not_installed",
    }


def _print_human(payload: dict[str, Any]) -> None:
    print("[Mission Control] Uninstall summary")
    print(f"  Codex home: {payload['codex_home']}")
    print(f"  Plugin removed: {'yes' if payload['plugin_removed'] else 'no'}")
    print(f"  Skills removed: {payload['removed_skill_count']}")
    if payload["removed_skills"]:
        for skill_name in payload["removed_skills"]:
            print(f"    - {skill_name}")
    if payload["dry_run"]:
        print("  Mode: dry-run")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remove the Mission Control Codex plugin bundle and synced skills.")
    parser.add_argument("--codex-home", default=None, help="Override the Codex home directory.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be removed without deleting files.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = uninstall_plugin_bundle(resolve_codex_home(args.codex_home), dry_run=args.dry_run)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_human(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
