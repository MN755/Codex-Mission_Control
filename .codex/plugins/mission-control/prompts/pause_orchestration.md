# Pause orchestration


Canonical prompt: `pause_orchestration`
Invocation name: `pause_orchestration`

## Purpose

Pause the active Mission Control orchestration and confirm the new state.

## Tool Sequence

- `mission_control_pause`
- `mission_control_get_status`

## Resource Sequence

- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`

## Safety Notes

Pausing is a state change. Confirm the right orchestration before doing it.

## Prompt Text

Pause the specified Mission Control orchestration and then confirm the paused state with a compact status summary.
