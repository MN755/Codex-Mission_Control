---
name: mission-control-run-validation
description: Ask Mission Control to run or plan validation. Use when the user wants build, tests, typecheck, lint, smoke, docs check, or manual verification routed through Mission Control with approvals preserved.
---

# Mission Control Run Validation

## Purpose

Run or plan validation through Mission Control without bypassing approval policy.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks to validate work.
- A handoff needs stronger evidence.
- A refactor or fix should be checked before sign-off.

## Workflow

1. Determine which validation types matter: build, tests, typecheck, lint, smoke, docs, or manual checks.
2. Ask Mission Control to run or plan the validation set.
3. Relay any command approvals required by policy.
4. Return the validation summary and any gaps.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Show which validations were requested, which ran, which were skipped, and what evidence exists.
- Call out approval-blocked validations instead of implying they ran.

## Approval behavior

Commands still need approvals when project policy requires them. This skill must preserve those gates rather than blur them.

## Never do

- Do not claim tests ran if Mission Control never ran them.
- Do not bypass command approval rules.
- Do not hide validation gaps.

## Failure and fallback

If a validation-summary resource does not exist yet, use status, event digest, and handoff evidence to build the summary and mark the dedicated resource as expected or future.

## Example invocation

`Ask Mission Control to run build, tests, and typecheck for this project.`
