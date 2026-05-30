# Mission Control Skills

This compatibility document points to the current first-party Codex-facing Mission Control skill library.

The skill library exists in both repo layouts:

- [plugins/mission-control/skills](../plugins/mission-control/skills)
- [.codex/skills](../.codex/skills)

Every skill in this pack follows the same rule:

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## Canonical Sources

Use these files as the authoritative references for the current skill surface:

- [plugins/mission-control/plugin.json](../plugins/mission-control/plugin.json) for the shipped skill manifest
- [plugins/mission-control/SKILL_INDEX.md](../plugins/mission-control/SKILL_INDEX.md) for the grouped plugin index
- [docs/MISSION_CONTROL_SKILL_LIBRARY.md](./MISSION_CONTROL_SKILL_LIBRARY.md) for bridge usage guidance and grouping notes

## Core Bridge Workflows

These are the most common entrypoints, not an exhaustive inventory:

- `mission-control-orchestrate`
- `mission-control-import-codebase`
- `mission-control-status`
- `mission-control-approve`
- `mission-control-handoff`
- `mission-control-debug`
- `mission-control-swarm`
- `mission-control-safe-mode`
- `mission-control-resume`
- `mission-control-agents-md`

## Skill Design Requirements

Each `SKILL.md` in this library includes:

- purpose
- when to use
- required Mission Control tools, resources, and prompts
- step-by-step workflow
- what to show the user in Codex chat
- safety and approval behavior
- fallback behavior if the daemon is unavailable
- what not to do

## Compatibility Note

Older docs may still mention the original starter workflow set. Treat the plugin manifest, grouped index, and library doc above as the current source of truth for the full shipped skill surface.
