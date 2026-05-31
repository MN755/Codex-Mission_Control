from __future__ import annotations

from mission_control_bundle import sync_repo_local_plugin_bundle


def main() -> int:
    result = sync_repo_local_plugin_bundle()
    print("Synced repo-local Mission Control plugin bundle.")
    print(f"- manifest: {result['manifest']}")
    print(f"- prompts: {len(result['prompt_files'])}")
    print(f"- prompts catalog: {result['prompts_catalog']}")
    print(f"- resources catalog: {result['resources_catalog']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
