# Debug Failed Orchestration

## Purpose

Collect the minimum safe context needed to explain a stuck or failed Mission Control run.

## Required Arguments

- `PROJECT_OR_ORCHESTRATION_REFERENCE`

## Intended Tool And Resource Sequence

1. Call `mission_control_get_status`.
2. Call `mission_control_get_diagnostics`.
3. Call `mission_control_get_pending_decisions`.
4. Call `mission_control_get_event_digest`.
5. Call `mission_control_request_recovery_plan`.
6. Read `mission-control://projects/{project_id}/diagnostics`.
7. Read `mission-control://projects/{project_id}/decision-ledger`.

## Expected User-Facing Codex Chat Output

- Concise blocker explanation
- Safe event digest
- Safe recovery options

## Safety Notes

- Keep logs and stack traces summarized, not dumped.
- Distinguish user-blocked state from infrastructure failure.
