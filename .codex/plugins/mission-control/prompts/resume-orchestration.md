# Resume orchestration

Alias for `resume_orchestration`.
Canonical prompt: `resume_orchestration`
Invocation name: `resume-orchestration`

## Purpose

Resume a paused Mission Control orchestration after the user confirms it should continue.

## Tool Sequence

- `mission_control_resume`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`

## Resource Sequence

- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`

## Safety Notes

Do not auto-resume a found orchestration without the user asking.

## Prompt Text

Resume the specified Mission Control orchestration if the user asked to continue, then summarize the updated state and any remaining pending decisions.
