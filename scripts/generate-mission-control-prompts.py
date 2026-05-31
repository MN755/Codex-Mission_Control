from __future__ import annotations

from mission_control_bundle import CANONICAL_PROMPTS_DIR, sync_prompt_markdown


def main() -> int:
    written = sync_prompt_markdown(CANONICAL_PROMPTS_DIR)
    print(f"Synced {len(written)} Mission Control prompt markdown files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
