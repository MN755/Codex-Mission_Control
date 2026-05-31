# Ask Manager for plan


Canonical prompt: `ask_manager_for_plan`
Invocation name: `ask_manager_for_plan`

## Purpose

Request a fresh Mission Control manager plan without replacing the manager with Codex chat logic.

## Tool Sequence

- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`

## Resource Sequence

- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/swarm-plan`

## Safety Notes

Use Mission Control as the planner. Do not invent the plan locally in Codex chat.

## Prompt Text

Ask Mission Control Manager for a plan for this project. Route the request through Mission Control, summarize the returned status and plan posture, and surface any pending decisions instead of improvising the plan in chat.
