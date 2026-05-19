# Codex Integration

> Status: Current

This page summarizes the current Codex-facing integration model for Mission Control.

## Integration summary

Codex is the user-facing bridge. Mission Control remains the orchestrator. The bridge uses plugin packaging, MCP tools, MCP resources, MCP prompts, and skills to attach workspaces, start tasks, relay pending decisions, and retrieve handoffs.

## Preferred path

- use local Codex CLI when available
- keep the orchestration runtime in the Mission Control daemon
- surface approvals and handoffs in Codex chat
- keep standalone dashboard work optional

## Read next

- [Codex Chat Mode](CODEX_CHAT_MODE.md)
- [MCP Plugin Bridge](MCP_PLUGIN_BRIDGE.md)
- [Runners](RUNNERS.md)
