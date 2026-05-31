---
name: mission-control-agent-stuck
description: Diagnose a stuck Mission Control agent. Use when an agent shows no output, repeats errors, times out, asks for the same approval repeatedly, or stops making progress events.
---

# Mission Control Agent Stuck

## Purpose

Diagnose a stuck agent and surface recovery options through Mission Control.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- A specific agent looks frozen.
- Progress events stopped.
- Repeated errors or approvals suggest a stuck loop.

## Workflow

1. Read agent status, event digest, diagnostics, and pending decisions.
2. Identify the stuck signal: no output, repeated error, timeout, repeated approval request, or no progress events.
3. Ask Mission Control for recovery options when available.
4. Present retry, reassign, split task, pause, or debug-agent options if backed by Mission Control.

## Mission Control calls

Tools:
- `mission_control_get_event_digest`
- `mission_control_get_status`
- `mission_control_request_recovery_plan`

Resources:
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Show the stuck signal, likely cause, affected agent, and safe recovery options.
- Keep the explanation focused on actionability.

## Approval behavior

If recovery means retrying commands, reassigning work, or spawning extra debugging capacity, keep those behind Mission Control approvals.

## Never do

- Do not restart or replace the agent from chat by assumption.
- Do not ignore a repeated approval loop.
- Do not claim the agent is healthy if the signals are stale.

## Failure and fallback

If dedicated stuck-agent logic is not exposed yet, infer the stuck pattern from status, diagnostics, and event digest, then recommend the recovery-plan flow.

## Example invocation

`This Mission Control agent looks stuck. Diagnose it.`
