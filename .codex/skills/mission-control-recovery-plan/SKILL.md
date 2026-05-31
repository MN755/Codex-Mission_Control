---
name: mission-control-recovery-plan
description: Ask Mission Control Manager for recovery guidance after a failure. Use when the user wants a failure summary, likely causes, recovery options, recommendation, and risks without losing the orchestration context.
---

# Mission Control Recovery Plan

## Purpose

Request a structured recovery plan from Mission Control after failure or uncertainty.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- A run failed or stalled.
- The user asks for recovery options.
- Status and diagnostics show unresolved blockers.

## Workflow

1. Review status, diagnostics, and event digest.
2. Call `mission_control_request_recovery_plan` when available.
3. Return the failure summary, possible causes, recovery options, recommended option, and risks.
4. If the user chooses an option, relay it through the approval flow.

## Mission Control calls

Tools:
- `mission_control_request_recovery_plan`
- `mission_control_get_status`
- `mission_control_get_event_digest`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Show failure summary, causes, options, recommendation, and risks in plain language.
- Make it obvious which options require approval or broader scope changes.

## Approval behavior

Recovery choices that restart work, relax safety controls, or widen scope must stay behind explicit user decisions.

## Never do

- Do not turn a recommendation into an action automatically.
- Do not hide uncertainty.
- Do not discard current evidence while discussing recovery.

## Failure and fallback

If the dedicated recovery-plan tool is absent, synthesize the same structure from status, diagnostics, and event resources and label it as a best-effort summary.

## Example invocation

`Ask Mission Control Manager for a recovery plan for the failed run.`
