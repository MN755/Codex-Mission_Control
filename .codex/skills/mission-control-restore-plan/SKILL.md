---
name: mission-control-restore-plan
description: Generate a rollback or restore plan from Mission Control state. Use when the user wants to know what would be reverted, what evidence would be preserved, and which destructive steps would still need approval before any restore action.
---

# Mission Control Restore Plan

## Purpose

Describe how rollback would work without executing it.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks how to roll back safely.
- A risky change needs a restore plan.
- Recovery decisions need a concrete revert outline.

## Workflow

1. Review snapshot, handoff, and status state.
2. Ask Mission Control for a restore or rollback plan if available.
3. Summarize what would be reverted, what would remain, and which steps would need approval.
4. Do not execute the restore in this skill.

## Mission Control calls

Tools:
- `mission_control_request_snapshot`
- `mission_control_request_recovery_plan`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/decision-ledger`

## User-facing output

- Explain the rollback target, affected files or milestones, evidence preservation, and approval gates for destructive steps.
- Keep it actionable enough for the user to decide.

## Approval behavior

Any actual restore or revert remains behind explicit approval. This skill only prepares the plan.

## Never do

- Do not execute restore steps.
- Do not understate destructive impact.
- Do not claim rollback coverage for unsnapshotted work.

## Failure and fallback

If no restore-plan tool exists, build the plan from snapshot availability, handoff evidence, and current status, and mark the dedicated tool as expected or future.

## Example invocation

`Generate a restore plan in case the current change set goes bad.`
