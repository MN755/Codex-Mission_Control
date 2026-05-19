# Codex Mission Control Wiki

This wiki is the long-form documentation hub for Codex Mission Control as a background-running orchestration platform for Codex.

> Status: Current

Mission Control is built first for background running. The standalone UI is optional or future-facing. The primary user experience is through Codex chat using the Mission Control plugin and MCP bridge.

## Runtime model

```text
Codex chat
  ->
Mission Control plugin / MCP bridge
  ->
Mission Control daemon
  ->
Manager AI
  ->
Worker agents / runners
```

Mission Control daemon owns orchestration state, approvals, diagnostics, and handoff generation. Codex chat is the bridge between the user and Mission Control.

## Start here

For users:

- [Quick Start](Quick-Start)
- [Background-Running Happy Path](Headless-Happy-Path)
- [Copy Paste Codex Prompts](Copy-Paste-Codex-Prompts)
- [Codex Chat Workflow](Codex-Chat-Workflow)

For contributors:

- [Development Guide](Development-Guide)
- [Mission Control Daemon](Mission-Control-Daemon)
- [Safety and Security Model](Safety-and-Security-Model)
- [Known Limitations and Non Goals](Known-Limitations-and-Non-Goals)

For AI and Codex agents:

- [Manager AI vs Codex Chat](Manager-AI-vs-Codex-Chat)
- [Skills and Prompts](Skills-and-Prompts)
- [Contributor Rules for AI Agents](Contributor-Rules-for-AI-Agents)

## Current status

- Current: daemon, MCP catalogs, skill library, pending decision relay, diagnostics, and handoff summaries
- Partial / experimental: runner depth, some autowiring paths, deeper orchestration hardening
- Optional / future: standalone observability surfaces

## Related repository docs

- [Repository README](https://github.com/MN755/Codex-Mission_Control)
- [Docs index](https://github.com/MN755/Codex-Mission_Control/blob/main/docs/README.md)
- [Background install](https://github.com/MN755/Codex-Mission_Control/blob/main/docs/HEADLESS_INSTALL.md)
- [Security](https://github.com/MN755/Codex-Mission_Control/blob/main/docs/SECURITY.md)

Use [_Sidebar](_Sidebar) for the full navigation list.
