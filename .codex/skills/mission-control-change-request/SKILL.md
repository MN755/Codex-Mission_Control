---
name: mission-control-change-request
description: Run a post-handoff or mid-project Mission Control change request flow. Use when the user wants additional work classified, impact-estimated, task-created, validated, and folded into the current handoff or milestone safely.
---

# Mission Control Change Request

## Purpose

Create a structured change request path instead of improvising scope changes in chat.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for follow-up work after a handoff.
- A new request changes an active project.
- Impact and validation should be estimated before execution.

## Workflow

1. Classify the request through Mission Control.
2. Estimate impact and ask the user if the change is large or architectural.
3. Create tasks or a new milestone through Mission Control.
4. Run or plan validation and update the handoff after completion.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/decision-ledger`

## User-facing output

- Show classification, impact, user decisions needed, planned validation, and whether the handoff will be updated or extended.
- Keep the change request distinct from the original baseline.

## Approval behavior

Large, architectural, or risky changes should be confirmed explicitly before execution continues.

## Never do

- Do not silently mutate the original scope.
- Do not discard earlier evidence when describing the new request.
- Do not skip impact discussion for large changes.

## Failure and fallback

If change-request workflow tooling is incomplete, route the request through plan revision plus Manager-led task execution and clearly mark it as a change request in chat.

## Example invocation

`Create a Mission Control change request for the next improvement after handoff.`
