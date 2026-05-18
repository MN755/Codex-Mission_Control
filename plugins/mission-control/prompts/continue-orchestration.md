# Continue Orchestration

## Purpose

Check Mission Control progress and continue the bridge flow without freelancing manager behavior.

## Required Arguments

- `PROJECT_OR_ORCHESTRATION_REFERENCE`

## Intended Tool And Resource Sequence

1. Call `mission_control_get_status`.
2. Call `mission_control_get_pending_decisions`.
3. Call `mission_control_get_orchestration_events` when more context is needed.
4. Read `mission-control://projects/{project_id}/agents`.

## Expected User-Facing Codex Chat Output

- Compact status summary
- Current blockers
- Active agent summary
- Pending decisions if the user is blocking progress

## Safety Notes

- Poll only when useful.
- Stop at pending user decisions instead of improvising the answer.
