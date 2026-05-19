---
name: mission-control-headless-health
description: Diagnose Mission Control daemon, MCP, plugin, runtime, and runner health from Codex chat.
---

# Mission Control Headless Health

## Purpose

Run the headless health doctor for Mission Control and summarize what is healthy, degraded, broken, or merely optional.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks whether Mission Control is installed correctly.
- The daemon or MCP bridge looks unhealthy.
- The user wants a copyable health summary without opening the standalone UI.

## Workflow

1. Prefer `GET /api/plugin/health` or `GET /api/headless/health`.
2. Use `scripts/mission-control-headless-health.ps1` for local shell validation.
3. Use `scripts/start-mission-control-mcp.ps1` to validate MCP bridge assets.
4. Summarize safe troubleshooting commands and the most likely next fix.

## Mission Control calls

Tools and endpoints:
- `mission_control_plugin_health`
- `GET /api/plugin/health`
- `GET /api/headless/health`
- `GET /api/runners/status`

Scripts:
- `scripts/mission-control-headless-health.ps1`
- `scripts/start-mission-control-mcp.ps1`

## User-facing output

- Report overall health state and the critical failing checks.
- Distinguish daemon status, MCP status, skill package state, runtime writability, DB reachability, and localhost-only binding.
- State explicitly that dashboard reachability is optional in headless mode.

## Approval behavior

- Health reads are read-only.
- If the user wants repairs that change config or restart services, say so and then use the repair path intentionally.

## Never do

- Do not expose secrets in diagnostics.
- Do not dump raw logs by default.
- Do not require the standalone UI.

Never require the standalone UI.

## Failure and fallback

- If the dedicated endpoint is unavailable, summarize the missing component and point to the safe troubleshooting commands.
- If daemon health and MCP health disagree, report the disagreement instead of inventing a clean bill of health.
- If only the plugin bundle is present, say the bridge assets are installed but not fully wired.

## Example invocation

`Run a Mission Control headless health check and tell me what is degraded.`
