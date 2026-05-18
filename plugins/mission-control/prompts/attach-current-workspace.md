# Attach Current Workspace

## Purpose

Attach the current workspace to Mission Control and report the safest next step for Codex chat.

## Required Arguments

- `WORKSPACE_PATH`
- `USER_REQUEST`

## Intended Tool And Resource Sequence

1. Call `mission_control_attach_workspace`.
2. Call `mission_control_get_status` if an orchestration already exists.
3. Read `mission-control://projects/{project_id}/status` for a compact safe summary.

## Expected User-Facing Codex Chat Output

- Attached or reused project ID
- Reused orchestration ID if one exists
- Read-only import posture warning if the folder is an existing codebase
- Safest recommended next prompt

## Safety Notes

- Prefer read-only-first behavior for existing codebases.
- Do not expose secrets.
- Do not claim attachment worked if the daemon did not confirm it.
