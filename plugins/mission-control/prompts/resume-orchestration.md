# Resume Orchestration

## Purpose

Resume a paused Mission Control orchestration after the user asks to continue.

## Required Arguments

- `ORCHESTRATION_ID`

## Intended Tool And Resource Sequence

1. Call `mission_control_resume`.
2. Call `mission_control_get_status`.
3. Call `mission_control_get_pending_decisions`.

## Expected User-Facing Codex Chat Output

- Confirmation that the orchestration resumed
- Updated status summary
- Any remaining user-blocking decisions

## Safety Notes

- Do not auto-resume just because a paused orchestration exists.
- Recheck state after resuming.
