---
name: mission-control-safe-mode
description: Put Mission Control into strict safety mode. Use when the user wants maximum approval gating, read-only imports, destructive-action blocking, deployment blocking, or tighter external-tool controls.
---

# Mission Control Safe Mode

## Purpose

Request or explain Mission Control strict safety mode for the project.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants every command approved.
- The workspace is risky or unfamiliar.
- The user wants deployments and external account tools disabled by default.

## Workflow

1. Explain what safe mode changes: strict approvals, destructive-action blocking, deployment blocking, and read-only import behavior.
2. Call `mission_control_enable_safe_mode` if available.
3. Re-check status and pending decisions after the mode change.
4. Confirm which restrictions are active and which remain expected or future.

## Mission Control calls

Tools:
- `mission_control_enable_safe_mode`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/swarm-plan`

## User-facing output

- Show the enabled restrictions and any unsupported controls that are still expected or future.
- Tell the user how approvals will look different after safe mode.

## Approval behavior

Treat safe-mode entry or exit as a meaningful policy change and confirm it with the user before changing the project posture.

## Never do

- Do not claim safe mode is active without a backed status change.
- Do not weaken safety controls silently.
- Do not keep dynamic spawning active if the user asked to pause it and the backend supports that control.

## Failure and fallback

If full safe-mode tooling is not implemented, document the intended restrictions in chat, mark them as expected or future, and continue operating conservatively.

## Example invocation

`Put this Mission Control project into strict safe mode.`
