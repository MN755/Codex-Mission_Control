# Debug Failed Orchestration

## Purpose

Collect the minimum safe context needed to explain a stuck or failed Mission Control run.

## Required Arguments

- `PROJECT_OR_ORCHESTRATION_REFERENCE`

## Intended Tool And Resource Sequence

1. Call `mission_control_get_status`.
2. Call `mission_control_get_diagnostics`.
3. Call `mission_control_get_pending_decisions`.
4. Call `mission_control_get_orchestration_events`.
5. Call `mission_control_request_recovery_options` if available.

## Expected User-Facing Codex Chat Output

- Concise blocker explanation
- Relevant recent events
- Safe recovery options

## Safety Notes

- Keep logs and stack traces summarized, not dumped.
- Distinguish user-blocked state from infrastructure failure.
