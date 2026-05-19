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

## Tool and script sequence

1. Prefer `scripts/install-mission-control-plugin.ps1` for Windows installs.
2. Use `scripts/mission-control-bootstrap.py` for dry-run, repair, or JSON reporting.
3. Start or verify the daemon with `scripts/start-mission-control-daemon.ps1`.
4. Verify bridge health with `scripts/mission-control-headless-health.ps1`.
5. Validate MCP bridge assets with `scripts/start-mission-control-mcp.ps1`.

## What to report to the user

- Install status: ready, degraded, or failed.
- Which runners are ready now.
- Which runners still need user login or external config.
- Whether the daemon is running and localhost-only.
- Whether the MCP bridge assets and skill package are present.

## Safety constraints

- Never store secrets in Mission Control reports, docs, logs, or SQLite.
- Never require the standalone UI.
- Never force API billing.
- Never silently install missing external tools without explicit user approval.
