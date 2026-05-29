# Use Mission Control For This Repo

## Purpose

Start a headless Mission Control run for the current repo from Codex chat.

## Required Arguments

- `WORKSPACE_PATH`
- `USER_REQUEST`

## Intended Tool And Resource Sequence

1. Call `mission_control_attach_workspace`.
2. Call `mission_control_start_task`.
3. Call `mission_control_get_status`.
4. Call `mission_control_get_pending_decisions`.
5. Read `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status` when available.

## Expected User-Facing Codex Chat Output

- Compact orchestration status
- Statement that Mission Control owns the manager role
- Pending approvals or questions if the run is blocked on the user

## Safety Notes

- Codex is the bridge, not the manager.
- Do not spawn agents or edit files outside Mission Control mode.
- Do not bypass approvals.
