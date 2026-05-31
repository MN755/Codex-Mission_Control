---
name: mission-control-context-pack
description: Show or build Mission Control context packs for agents. Use when the user wants to know which files, docs, and constraints are being packaged for a task, why they were selected, and where context coverage is still missing.
---

# Mission Control Context Pack

## Purpose

Explain or request context-pack generation for Mission Control work.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks what context an agent got.
- A task seems under-contextualized.
- You need to explain token and file selection boundaries.

## Workflow

1. Read codebase, status, and any context-pack summaries that exist.
2. Explain which files or docs are included, for which target task or agent, and why.
3. If the user requests a new pack, route it through Mission Control rather than assembling it manually in chat.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Summarize included context, missing context, target agent or task, and any token-budget pressure.
- Explain whether the pack is existing, proposed, or expected or future.

## Approval behavior

If the user asks to widen context into sensitive areas, confirm that choice and respect Mission Control safety boundaries.

## Never do

- Do not manually stuff chat with giant file dumps as a fake context pack.
- Do not expose secret-bearing files.
- Do not pretend a context pack exists if it does not.

## Failure and fallback

If no explicit context-pack tooling exists, infer the likely pack from codebase map and contracts, then label that inference clearly.

## Example invocation

`Explain the Mission Control context pack for the current task.`
