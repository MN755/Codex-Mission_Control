# Headless First Direction

This page explains why Mission Control is being documented and built as a headless Codex-native platform first.

> Status: Current

## Why the standalone UI is secondary

The project direction is to make Codex chat the primary user-facing surface. That means the most important outputs are:

- bridge-safe markdown summaries
- approval and question relay text
- handoff summaries
- diagnostics summaries

The dashboard can remain in the repository as an optional observability layer, but it should not drive product decisions or roadmap sequencing right now.

## In scope now

Focus areas:

- daemon behavior
- MCP bridge tools, resources, and prompts
- plugin packaging and autowiring
- runner detection and configuration
- existing-codebase intake
- adaptive swarm safety and coordination
- approvals, diagnostics, and handoffs
- docs and skill libraries

## Out of scope unless explicitly requested

Do not focus on standalone UI unless explicitly requested.

User-facing UX means Codex chat output.

Treat these areas as optional/future unless directly assigned:

- dashboard layout work
- widget visual polish
- React navigation changes
- desktop-shell presentation changes

## How agents should treat dashboard code

Dashboard docs and code can be referenced as optional context, but they should not be treated as the product center.

For bridge work, read [Manager AI vs Codex Chat](Manager-AI-vs-Codex-Chat), [Codex Chat Workflow](Codex-Chat-Workflow), and [Skills and Prompts](Skills-and-Prompts) first.
