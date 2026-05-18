# Show Pending Approvals

## Purpose

Render the current Mission Control approval or question queue for Codex chat.

## Required Arguments

- `PROJECT_OR_ORCHESTRATION_REFERENCE`

## Intended Tool And Resource Sequence

1. Call `mission_control_get_pending_decisions`.
2. Read `mission-control://projects/{project_id}/pending-decisions`.

## Expected User-Facing Codex Chat Output

- Highest-priority pending decision
- Risk level
- Choice options
- Clear ask for user input

## Safety Notes

- Do not answer the decision automatically.
- Keep secret-bearing command details redacted.
