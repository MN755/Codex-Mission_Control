# Mission Control Skills

Mission Control now ships a full first-party Codex skill library, not the old ten-skill starter pack.

The current source of truth lives in:

- [docs/MISSION_CONTROL_SKILL_LIBRARY.md](./MISSION_CONTROL_SKILL_LIBRARY.md)
- [plugins/mission-control/SKILL_INDEX.md](../plugins/mission-control/SKILL_INDEX.md)
- [plugins/mission-control/skills](../plugins/mission-control/skills)
- [.codex/skills](../.codex/skills)

Every skill in this pack still follows the same non-negotiable rule:

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## What This Document Is For

Use this page as the compatibility entrypoint when older docs or wiki pages still reference `docs/MISSION_CONTROL_SKILLS.md`.

It now redirects readers to the current library instead of pretending the shipped surface is still a ten-skill bundle.

## Current Guidance

- Use [docs/MISSION_CONTROL_SKILL_LIBRARY.md](./MISSION_CONTROL_SKILL_LIBRARY.md) for the grouped library overview and usage rules.
- Use [plugins/mission-control/SKILL_INDEX.md](../plugins/mission-control/SKILL_INDEX.md) for the full shipped skill inventory.
- Treat the plugin manifest in [plugins/mission-control/plugin.json](../plugins/mission-control/plugin.json) as the canonical shipped-skill list.
- Expect the repo-local `.codex` mirror to track the canonical plugin skill tree.

## Compatibility Note

Older references to the "ten-skill bridge pack" are stale. The shipped Mission Control bundle now includes the broader headless skill library, including install/update, diagnostics, CUDA/NVIDIA workflows, evaluation support, and other specialized bridge skills.
