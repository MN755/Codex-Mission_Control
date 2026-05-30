# MCP Plugin Bridge

> Status: Current

This page describes how Codex reaches Mission Control through plugin packaging, MCP tools, MCP resources, and MCP prompts.

## Purpose

The bridge keeps Codex chat thin. Mission Control remains the orchestrator. MCP surfaces give Codex a controlled way to attach workspaces, start tasks, read safe summaries, answer pending decisions, and retrieve handoffs.

## Surface types

- MCP tools: executable actions such as attach, start, answer, pause, and resume
- MCP resources: read-only summaries such as project status, agents, pending decisions, diagnostics, and handoff state
- MCP prompts: reusable workflow templates for common tasks
- skills: Codex-facing instructions that tell the bridge how to use Mission Control safely

## Core bridge tools

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

The full current tool catalog lives in [MCP Tools](MCP_TOOLS.md).

## Common bridge resources

- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://orchestrations/{orchestration_id}/status`

The full current resource catalog lives in [MCP Resources](MCP_RESOURCES.md), and the workflow catalog lives in [MCP Prompts](MCP_PROMPTS.md).

## Bridge rules

- attach the workspace before starting work
- prefer safe resource summaries before polling tools repeatedly
- relay user decisions instead of answering them locally
- keep raw logs and secrets out of normal chat output

## Related docs

- [Codex Chat Mode](CODEX_CHAT_MODE.md)
- [Pending Decisions](PENDING_DECISIONS.md)
- [Background Architecture](HEADLESS_ARCHITECTURE.md)
- [Security](SECURITY.md)
