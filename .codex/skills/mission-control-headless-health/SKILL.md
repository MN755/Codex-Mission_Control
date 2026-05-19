---
name: mission-control-headless-health
description: Use when Codex should diagnose Mission Control plugin, daemon, MCP, runtime, or runner health from chat without opening the standalone app.
---

# Mission Control Headless Health

Use this skill when the user wants a health doctor pass for Mission Control plugin or MCP mode.

## Bridge boundary

- The Codex chat agent is not the Mission Control Manager.
- Codex chat reports health and relays fixes.
- Mission Control Manager only matters after the bridge is healthy enough to use.

## When to use

- The user asks whether Mission Control is installed correctly.
- The daemon or MCP bridge looks unhealthy.
- The user wants copyable troubleshooting commands.

## Tool and script sequence

1. Prefer `GET /api/plugin/health` or `GET /api/headless/health`.
2. Use `scripts/mission-control-headless-health.ps1` for local shell validation.
3. Use `scripts/start-mission-control-mcp.ps1` to validate MCP bridge assets.
4. Surface recommended fixes and safe troubleshooting commands in Codex chat.

## What to report to the user

- Overall health state.
- Which checks are ready, degraded, broken, or unknown.
- What can be fixed locally without touching the UI.
- Whether the dashboard is optional rather than required.

## Safety constraints

- Never expose secrets in diagnostics.
- Never dump raw logs by default.
- Never require the standalone UI.
- Never claim the bridge is ready when health checks disagree.
