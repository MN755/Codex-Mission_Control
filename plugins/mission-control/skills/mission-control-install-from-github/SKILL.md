---
name: mission-control-install-from-github
description: Install or repair Mission Control for headless Codex use from a repo checkout or GitHub clone.
---

# Mission Control Install From GitHub

## Purpose

Install or repair the Mission Control bridge assets, daemon bootstrap path, and headless runtime without requiring the standalone UI.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user says to install Mission Control from GitHub or from the current repo.
- The user wants a headless-only setup.
- The daemon, plugin bundle, or local skills need a repair pass.

## One-command workflow

Use exactly one command as the primary install path:

```text
python scripts/mission-control-manage.py install
```

Only fall back to `scripts/install-mission-control-plugin.ps1` or `.sh` when the user explicitly wants a shell-native wrapper.

## Workflow

1. Run `scripts/mission-control-manage.py install` as the primary workflow.
2. Let the unified workflow install Python packages for `apps/server` and `apps/mcp-server` unless the user explicitly asks to skip package setup.
3. Let the unified workflow sync the repo-local plugin bundle and Mission Control skills into Codex home.
4. Let the unified workflow write or update the managed `mcp_servers."mission-control"` Codex config entry.
5. Let the unified workflow run headless bootstrap, daemon verification, bridge verification, and Ollama/Codex runner reporting.
6. Tell the user to force-quit and reopen Codex and Claude Code before they try to use Mission Control, because plugin and MCP changes are not loaded into already-open app sessions.
7. Tell the user that after the reload Codex should show `Mission Control` as an available plugin, not only as standalone Mission Control skills.

## Mission Control calls

Scripts:
- `scripts/mission-control-manage.py`
- `scripts/install-mission-control-plugin.ps1`
- `scripts/mission-control-bootstrap.py`
- `scripts/start-mission-control-daemon.ps1`
- `scripts/mission-control-headless-health.ps1`
- `scripts/start-mission-control-mcp.ps1`

Endpoints:
- `GET /api/headless/config`
- `POST /api/headless/autowire`
- `GET /api/headless/health`
- `GET /api/runners/status`

## User-facing output

- Report install status as `ready`, `degraded`, or `failed`.
- Show ready runners, unavailable runners, daemon status, MCP status, Ollama readiness, and the next Codex prompt.
- Include the exact install, update, and uninstall one-command invocations.
- State clearly that the dashboard is optional and not required for setup.

## Approval behavior

- Safe probing and local config generation are fine.
- Do not silently install missing external CLIs, model weights, or API credentials.
- Ask before any new dependency or billing-backed tool path would be introduced.

## Never do

- Do not require the standalone UI.
- Do not store raw secrets in Mission Control config, logs, or reports.
- Do not pretend API-backed runners are free or already authenticated when they are not.

Never require the standalone UI.

## Failure and fallback

- If backend dependencies are missing, say so directly and point to the backend install command.
- If the daemon can start but MCP is not configured, mark the setup degraded instead of pretending it is fully ready.
- If only `dry_run` is available, report that honestly and offer the dry-run follow-up prompt.

## Example invocation

`Install Mission Control from this repo and wire up everything available.`
