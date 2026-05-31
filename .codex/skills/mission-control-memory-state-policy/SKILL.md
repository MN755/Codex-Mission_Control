---
name: mission-control-memory-state-policy
description: Define memory, state, checkpoints, resumability, and retention policy for Mission Control workflows and agents.
---

# Mission Control Memory And State Policy

## Purpose

Control what Mission Control remembers, where it stores state, and how agents resume without hallucinating continuity.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks how state, memory, checkpoints, or resumability work.
- A workflow needs durable context or retention limits.
- Privacy or cleanup rules matter.

## Workflow

1. Ask Mission Control for current project state, runtime paths, and handoff artifacts.
2. Classify state as ephemeral, project-local, reusable, or sensitive.
3. Define retention, redaction, checkpoint, and resume rules.
4. Return policy and any cleanup or snapshot actions.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_request_snapshot`

Resources:
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/diagnostics`

## User-facing output

- Explain stored state, retention, resume points, privacy risks, and cleanup options.

## Approval behavior

Ask before deleting state, exporting memory, or persisting sensitive context.

## Never do

- Do not hide memory locations.
- Do not retain secrets by default.
- Do not resume from stale assumptions without checking status.

## Failure and fallback

If state inventory is incomplete, recommend a snapshot and diagnostic pass.

## Example invocation

`Use Mission Control to explain what it remembers for this project and how to clean it up.`
