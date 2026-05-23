---
name: mission-control-plugin-health
description: Run a Mission Control plugin, daemon, and bridge health check. Use when the user wants to verify daemon status, MCP connectivity, skills availability, runner registry, local binding, or general bridge health from Codex chat.
---

# Mission Control Plugin Health

## Purpose

Check the health of the Mission Control bridge surfaces that Codex depends on.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- Mission Control seems unreachable or partially broken.
- The user asks whether the plugin or daemon is healthy.
- A setup problem blocks orchestration.

## Workflow

1. Call `mission_control_plugin_health` when available.
2. If named health tools are not exposed, confirm whether the MCP server is still registered before saying the plugin is missing.
3. In Codex CLI sessions, use `codex mcp list` when needed to distinguish a registered server from a callable bridge surface.
4. Review status resources and summarize daemon, MCP, skills, runner registry, runtime folder, local binding, and optional dashboard state.
5. Return a concise health report and likely next fix.

## Mission Control calls

Tools:
- `mission_control_plugin_health`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Check daemon, MCP, skills, Codex CLI, runner registry, runtime folder, localhost binding, and optional dashboard status.
- Report failures as specific components, not a vague 'it is broken.'

## Approval behavior

Health reads are read-only. If the user wants a repair action that changes config or restarts components, get explicit approval first.

## Never do

- Do not pretend health is good when connectivity is partial.
- Do not dump raw diagnostics logs by default.
- Do not force dashboard UI involvement.

## Failure and fallback

If the dedicated health tool is absent, first distinguish between plugin missing and plugin registered with only partial MCP exposure. Then use diagnostics and status resources to produce a best-effort bridge health summary and label missing checks clearly.

## Example invocation

`Run a Mission Control plugin health check.`
