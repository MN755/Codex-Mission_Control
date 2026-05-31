---
name: mission-control-skip-interview
description: Skip the Mission Control interview and proceed with assumptions. Use when speed matters more than full intake and the user accepts that the Manager will proceed with explicit unknowns and later corrections if needed.
---

# Mission Control Skip Interview

## Purpose

Skip full interview while keeping assumptions visible and correctable.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants to move fast.
- The repo is already descriptive enough for a first pass.
- A small task does not justify a long interview.

## Workflow

1. Confirm that the user wants to skip interview.
2. Summarize the likely assumptions or missing requirements.
3. Route the skip choice through Mission Control if an approval or intake choice exists.
4. Continue to plan or build only after the skip choice is recorded.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_answer_decision`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/codebase-map`

## User-facing output

- Show what is assumed, what remains unknown, and how the user can correct those assumptions later.
- Report whether the project is now moving to planning or build.

## Approval behavior

Treat skipping interview as an explicit user choice because it changes intake fidelity.

## Never do

- Do not hide uncertainty.
- Do not skip interview implicitly.
- Do not pretend a skipped interview is equivalent to answered requirements.

## Failure and fallback

If skip-interview is not a first-class control, document the user's choice in chat, send it through the next Manager-facing task, and clearly mark the assumption list.

## Example invocation

`Skip the Mission Control interview and proceed with assumptions for this urgent fix.`
