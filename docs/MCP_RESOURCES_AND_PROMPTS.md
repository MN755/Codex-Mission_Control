# MCP Resources and Prompts

This compatibility document summarizes the current Mission Control MCP bridge surfaces and points to the richer catalog in [docs/MCP_RESOURCES_PROMPTS.md](./MCP_RESOURCES_PROMPTS.md).

## Tools vs Resources vs Prompts

Mission Control keeps these surfaces separate on purpose:

- tools mutate or query orchestration state through explicit calls
- resources expose safe summaries only
- prompts tell Codex how to use the bridge without improvising a fake manager workflow

Codex chat is the bridge. Mission Control Manager remains the orchestrator.

## Secret Redaction

Mission Control MCP resources return safe summaries only.

That means:

- no daemon token
- no raw API keys
- no raw shell logs by default
- no secret-bearing headers or environment dumps

If deeper diagnostics are needed, they should stay opt-in and still redact secrets.

## Current scope

Use the full catalog document for:

- the current resource catalog
- the current prompt catalog
- read-only resource rules
- approval relay behavior
- existing-codebase workflows
