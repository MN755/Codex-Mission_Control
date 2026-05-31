# Use Mission Control for this repo


Canonical prompt: `use_mission_control_for_repo`
Invocation name: `use_mission_control_for_repo`

## Purpose

Start a manager-led Mission Control workflow for the current repo from Codex chat.

## Tool Sequence

- `mission_control_attach_workspace`
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`

## Resource Sequence

- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`

## Safety Notes

Codex is the bridge, not the manager. Do not bypass approvals.

## Prompt Text

Use Mission Control for this repo. Attach the workspace, start the requested manager-led task, summarize status, and surface pending decisions if Mission Control needs user input. Do not act like the manager yourself.
