# Review Latest Handoff

## Purpose

Retrieve and summarize the latest Mission Control handoff in Codex chat.

## Required Arguments

- `PROJECT_OR_ORCHESTRATION_REFERENCE`

## Intended Tool And Resource Sequence

1. Call `mission_control_get_handoff`.
2. Read `mission-control://projects/{project_id}/validation-summary` when available.

## Expected User-Facing Codex Chat Output

- What changed
- How to run it
- Validation or evidence posture
- Limitations
- Next steps

## Safety Notes

- Warn on dry-run handoffs or missing evidence.
- Do not overstate readiness.
