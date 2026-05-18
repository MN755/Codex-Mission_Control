---
name: mission-control-scope-creep-check
description: Ask Mission Control whether the project is drifting beyond approved scope. Use when the task list is growing, the user asks for more work midstream, or you need a Manager recommendation on include now versus defer.
---

# Mission Control Scope Creep Check

## Purpose

Check for scope creep and preserve explicit include-now versus defer decisions.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- Requirements are expanding.
- The user asks for additional work midstream.
- You need the Manager's scope recommendation.

## Workflow

1. Read status, plan, and risk or decision resources.
2. Ask Mission Control to evaluate whether the work is beyond approved scope.
3. Summarize detected scope changes, severity, include-now or defer options, and Manager recommendation.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/risk-register`

## User-facing output

- Show detected scope changes, severity, suggested milestone placement, and the Manager recommendation.
- Tell the user what new approvals or replanning may be required.

## Approval behavior

Treat scope expansion as a decision, not an assumption. Get the user's choice before broader execution begins.

## Never do

- Do not quietly absorb major scope changes.
- Do not understate schedule or risk impact.
- Do not override the user's scoping decision.

## Failure and fallback

If no dedicated scope-creep signal exists, use decision and risk resources plus current status to frame the analysis and label the recommendation source clearly.

## Example invocation

`Check whether this Mission Control project is drifting beyond scope.`
