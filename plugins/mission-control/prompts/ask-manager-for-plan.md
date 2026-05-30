# Ask Manager for Plan

# Ask Manager For Plan

## Purpose

Request a fresh Mission Control manager plan without replacing the manager with Codex chat logic.

## Required Arguments

- `PROJECT_ID`
- `USER_REQUEST`

## Intended Tool And Resource Sequence

1. Call `mission_control_start_task`.
2. Call `mission_control_get_status`.
3. Call `mission_control_get_pending_decisions`.
4. Read `mission-control://projects/{project_id}/status`.
5. Read `mission-control://projects/{project_id}/swarm-plan`.

## Expected User-Facing Codex Chat Output

- Compact status summary
- Current manager plan posture
- Plan-blocking decision when Mission Control needs user input

## Safety Notes

- Use Mission Control as the planner.
- Do not improvise the plan locally in Codex chat.
