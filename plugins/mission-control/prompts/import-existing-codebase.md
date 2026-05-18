# Import Existing Codebase

## Purpose

Attach an existing codebase to Mission Control with a read-only understanding pass first.

## Required Arguments

- `WORKSPACE_PATH`
- `USER_REQUEST`

## Intended Tool And Resource Sequence

1. Call `mission_control_attach_workspace` in existing-codebase mode.
2. Call `mission_control_get_codebase_map`.
3. Call `mission_control_get_codebase_understanding`.
4. Read `mission-control://projects/{project_id}/codebase-map`.
5. Call `mission_control_set_import_interview_choice`.
6. Call `mission_control_start_task`.

## Expected User-Facing Codex Chat Output

- Read-only import result
- Compact codebase map summary
- Compact understanding summary
- Interview choice request

## Safety Notes

- Do not start write-capable actions during the initial scan.
- Do not expose file contents or secrets by default.
