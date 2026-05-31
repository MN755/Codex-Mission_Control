# Continue orchestration


Canonical prompt: `continue_orchestration`
Invocation name: `continue_orchestration`

## Purpose

Check the current orchestration, summarize progress, and stop at pending user decisions when necessary.

## Tool Sequence

- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_get_event_digest`

## Resource Sequence

- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`

## Safety Notes

Poll only when useful and do not confuse waiting with completion.

## Prompt Text

Continue the Mission Control orchestration by checking status, a safe event digest, and pending decisions. If the run is blocked on the user, present that cleanly and stop there. If it is active, summarize progress in compact markdown.
