# MCP Plugin Architecture

This page explains how the plugin package, MCP tools, MCP resources, and MCP prompts work together around the Mission Control daemon.

> Status: Current

## Why the split exists

The MCP layer should stay thin and predictable.

- Resources are read-only state summaries.
- Tools perform bridge actions.
- Prompts guide reusable workflows.
- The daemon remains the orchestration authority.

## Expected tools

Expected tools:

- `mission_control_attach_workspace`
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_answer_decision`
- `mission_control_pause`
- `mission_control_resume`
- `mission_control_get_handoff`
- `mission_control_plugin_health`
- `mission_control_enable_safe_mode`

## Expected resources

Expected resources:

- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/diagnostics`

Additional resources such as swarm-plan, risk-register, validation-summary, and orchestration event summaries may also be present depending on the package version.

## Prompts and plugin package

The plugin package should include:

- MCP config example
- prompt catalog
- resource catalog
- skill folders
- chat-safe markdown templates

Prompts should guide flows such as attach workspace, continue orchestration, review handoff, and answer pending approvals.

## Related pages

Continue with [Skills and Prompts](Skills-and-Prompts), [MCP Resources Catalog](MCP-Resources-Catalog), [MCP Prompts Catalog](MCP-Prompts-Catalog), and [MCP Bridge Endpoints](MCP-Bridge-Endpoints).
