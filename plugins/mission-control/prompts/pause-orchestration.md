# Pause Orchestration

## Purpose

Pause the active Mission Control orchestration cleanly from Codex chat.

## Required Arguments

- `ORCHESTRATION_ID`

## Intended Tool And Resource Sequence

1. Call `mission_control_pause`.
2. Call `mission_control_get_status`.

## Expected User-Facing Codex Chat Output

- Confirmation that the orchestration is paused
- Remaining pending decisions or blockers

## Safety Notes

- Confirm the correct orchestration ID before pausing.
- Treat pausing as an explicit state change.
