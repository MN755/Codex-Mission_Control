---
name: mission-control-debug
description: Diagnose stuck or failed Mission Control orchestration. Use when runs are blocked, failing repeatedly, waiting too long, missing evidence, or unclear about the next recovery step.
---

# Mission Control Debug

## Purpose

Diagnose stuck or failed orchestration and surface recovery options.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user says the run is stuck or broken.
- Status looks stalled.
- Approvals, diagnostics, or event summaries need to be correlated.

## Workflow

1. Fetch status with `mission_control_get_status`.
2. Fetch pending decisions with `mission_control_get_pending_decisions`.
3. Fetch diagnostics and recent event digest, including platform profile, performance guardrails, safe debug commands, and the latest support-bundle path when present.
4. Ask Mission Control for a recovery plan if available.
5. Distinguish user-blocked, runner-blocked, daemon-blocked, and host-app-blocked states explicitly.
6. Summarize blocker, likely causes, and the safest next options for the detected device.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_get_event_digest`
- `mission_control_request_recovery_plan`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- State the main blocker, supporting evidence, pending approvals, detected device family, and recommended next options.
- Include the support-bundle path when one exists.
- Keep diagnostics summarized; do not paste raw logs by default.

## Approval behavior

If recovery choices may retry commands, widen scope, or restart work, relay the decision to the user before acting.

## Never do

- Do not freehand a recovery action that Mission Control has not approved.
- Do not dump raw logs or secrets.
- Do not say the system is healthy when diagnostics disagree.

## Failure and fallback

If recovery tooling is missing, summarize the failure from status, diagnostics, and events, suggest generating the local support bundle first, and clearly mark recovery-plan tooling as expected or future.

## Example invocation

`Mission Control looks stuck. Diagnose it and show my options.`
