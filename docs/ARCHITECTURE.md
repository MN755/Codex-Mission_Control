# Architecture

> Status: Current

This page summarizes the product architecture at a high level. Use it when you need the component model without the lower-level implementation notes.

## Runtime path

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

## Major components

- Codex chat: user-facing bridge
- MCP bridge: tools, resources, and prompts exposed to Codex
- Mission Control daemon: orchestration runtime and state owner
- Manager AI: planner and coordinator inside Mission Control
- worker agents: background execution units governed by runner and approval policy

## Primary boundaries

- Codex chat is not the Manager AI.
- Resources summarize state but do not execute commands.
- Tools perform actions and must respect approval policy.
- The daemon keeps orchestration state local and loopback-oriented by default.
- The standalone dashboard is optional and not required for normal background operation.

## Read next

- [Background Architecture](HEADLESS_ARCHITECTURE.md)
- [MCP Plugin Bridge](MCP_PLUGIN_BRIDGE.md)
- [Runners](RUNNERS.md)
- [Security](SECURITY.md)
