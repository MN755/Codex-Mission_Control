---
name: mission-control-mcp-builder
description: Design, build, or audit MCP servers and tool/resource/prompt contracts through Mission Control. Use for MCP schemas, stdio startup, auth boundaries, plugin packaging, and smoke tests.
---

# Mission Control MCP Builder

## Purpose

Coordinate MCP server development with explicit contracts, auth checks, and repeatable smoke tests.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants to build or repair an MCP server.
- Tool, resource, or prompt schemas need review.
- Plugin packaging or stdio startup is failing.

## Workflow

1. Ask Mission Control to map the intended MCP surface.
2. Check tool inputs, resource URIs, prompt names, auth, stdio startup, and host reload needs.
3. Request implementation or repair through managed workers.
4. Run an initialize/list/tool-call smoke test when possible.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_plugin_health`

Resources:
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Report contract status, auth posture, startup result, callable tool status, and remaining host actions.

## Approval behavior

Require approval before adding external network access, secrets, or write-capable tools.

## Never do

- Do not expose tokens in diagnostics.
- Do not call a bridge healthy just because `tools/list` works.
- Do not bypass host MCP approval.

## Failure and fallback

If live host loading cannot be proven, separate configured, loaded, and callable states.

## Example invocation

`Use Mission Control to build an MCP server for this repo and prove the tool call path works.`
