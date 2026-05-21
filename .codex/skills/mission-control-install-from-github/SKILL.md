---
name: mission-control-install-from-github
description: Use when Codex should install or repair Mission Control in headless mode from GitHub or an existing local checkout.
---

# Mission Control Install From GitHub

Use this skill when the user wants Codex to install, repair, or validate Mission Control without touching the standalone UI.

## Bridge boundary

- The Codex chat agent is not the Mission Control Manager.
- Codex chat installs and wires the bridge surface.
- Mission Control Manager remains the orchestration authority after setup.

## When to use

- The user says to install Mission Control from GitHub.
- The user wants a headless-only setup.
- The user wants a repair pass for the daemon, MCP bridge, skills, or plugin package.

## One-command workflow

Use exactly one command as the primary install path:

```text
python scripts/mission-control-manage.py install
```

Only fall back to platform wrappers such as `scripts/install-mission-control-plugin.ps1` or `.sh` when the user specifically wants a shell-native entrypoint.

## Tool and script sequence

1. Use `scripts/mission-control-manage.py install` as the primary workflow.
2. Let the unified workflow install Python packages for `apps/server` and `apps/mcp-server` unless the user explicitly asks to skip that setup.
3. Let the unified workflow sync the Codex plugin bundle and `mission-control*` skills into Codex home.
4. Let the unified workflow write or update the managed `mcp_servers."mission-control"` Codex config entry.
5. Let the unified workflow run the headless bootstrap and report daemon, MCP, runner, and Ollama readiness.
6. Tell the user to force-quit and reopen Codex and Claude Code before they try to use Mission Control, because plugin and MCP changes are not loaded into already-open app sessions.
7. Tell the user that after the reload Codex should show `Mission Control` as an available plugin, not only as standalone Mission Control skills.
8. Tell the user to approve the project MCP server from `.mcp.json` if Claude Code prompts for it after reload.
9. If Codex still does not show the plugin after reload, tell the user to rerun `python scripts/mission-control-manage.py update` and restart Codex again before falling back to skill-only workarounds.

## What to report to the user

- Install status: ready, degraded, or failed.
- Which runners are ready now.
- Which runners still need user login or external config.
- Whether Ollama local support is reachable and ready now.
- Whether the daemon is running and localhost-only.
- Whether the MCP bridge assets and skill package are present.
- How the user should verify that Codex loaded the real plugin and Claude loaded the project MCP server.
- The exact one-command install, update, and uninstall commands.

## Safety constraints

- Never store secrets in Mission Control reports, docs, logs, or SQLite.
- Never require the standalone UI.
- Never force API billing.
- Never silently install missing external tools without explicit user approval.
