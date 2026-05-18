# Start Manager-Led Task

## Purpose

Start a Mission Control task for an attached project and return the first useful bridge-safe update.

## Required Arguments

- `PROJECT_ID`
- `USER_REQUEST`

## Intended Tool And Resource Sequence

1. Call `mission_control_start_task`.
2. Call `mission_control_get_status`.
3. Call `mission_control_get_pending_decisions`.

## Expected User-Facing Codex Chat Output

- Orchestration ID
- Current phase
- Manager status
- Pending user decisions if any

## Safety Notes

- Do not replace existing pending decisions with local guesses.
- Do not claim work completed unless Mission Control says so.
