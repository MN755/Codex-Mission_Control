# Start Manager-led task

Alias for `start_manager_led_task`.
Canonical prompt: `start_manager_led_task`
Invocation name: `start-manager-led-task`

## Purpose

Start a Mission Control task for an already attached project and return compact status.

## Tool Sequence

- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`

## Resource Sequence

- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`

## Safety Notes

Respect existing pending decisions instead of replacing them with a new local plan.

## Prompt Text

Start a Mission Control manager-led task for the attached project. Return compact status and surface any pending decisions immediately if the orchestration is waiting on the user.
