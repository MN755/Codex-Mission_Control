---
name: mission-control-update
description: Use when Codex should refresh an existing Mission Control install, resync the plugin and skills, and rerun headless repair/bootstrap.
---

# Mission Control Update

Use this skill when the user wants one-command update or repair behavior for Mission Control.

The Codex chat agent is not the Mission Control Manager.

## One-command workflow

```text
python scripts/mission-control-manage.py update
```

## Expectations

- Update Python packages for the backend and MCP bridge unless the user explicitly asks to skip package setup.
- Resync the Codex plugin bundle and `mission-control*` skills into Codex home.
- Refresh the managed `mcp_servers."mission-control"` registration.
- Rerun headless repair/bootstrap and report daemon, bridge, runner, and Ollama readiness.
- Tell the user to force-quit and reopen Codex and Claude Code before they try to use Mission Control, because plugin and MCP changes are not loaded into already-open app sessions.
- Tell the user that after the reload Codex should show `Mission Control` as an available plugin, not only as standalone Mission Control skills.
- Tell the user to approve the project MCP server from `.mcp.json` if Claude Code prompts for it after reload.
- If Codex still does not show the plugin after reload, tell the user to rerun `python scripts/mission-control-manage.py update` and restart Codex again instead of acting like skills-only mode is enough.

## Safety constraints

- Do not bypass Mission Control approvals.
- Do not claim Codex or Ollama readiness without the workflow output proving it.
- Do not require the standalone UI.

Never require the standalone UI.
