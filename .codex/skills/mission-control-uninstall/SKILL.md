---
name: mission-control-uninstall
description: Use when Codex should remove the Mission Control plugin bundle, synced skills, and managed Codex MCP registration.
---

# Mission Control Uninstall

Use this skill when the user wants one-command Mission Control cleanup from Codex home.

The Codex chat agent is not the Mission Control Manager.

## One-command workflow

```text
python scripts/mission-control-manage.py uninstall
```

## Expectations

- Remove the Mission Control plugin bundle from Codex home.
- Remove synced `mission-control*` skills from Codex home.
- Remove the managed `mcp_servers."mission-control"` config block.
- Stop the local Mission Control daemon when safe, unless the user asks to keep it running.
- Never require the standalone UI.

## Safety constraints

- Do not delete the source repository checkout unless the user explicitly asks for that.
- Do not claim the uninstall is complete without reporting what was actually removed.
