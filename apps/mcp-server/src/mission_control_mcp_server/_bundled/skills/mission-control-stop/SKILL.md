---
name: mission-control-stop
description: Stop or retire Mission Control orchestration safely. Use when the user wants no new work assigned, current state preserved, partial results summarized, and unsafe process-kill behavior avoided unless the backend explicitly supports it.
---

# Mission Control Stop

## Purpose

Stop Mission Control work safely while preserving state and partial outputs.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants to stop the run.
- The project should retire gracefully.
- A partial report should be preserved before shutdown.

## Workflow

1. Check status and pending decisions.
2. Ask Mission Control to stop assigning new work and retire the orchestration cleanly.
3. Summarize the preserved state, partial handoff if any, and what remains unfinished.
4. Avoid unsafe process termination unless the backend exposes a safe stop control.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_pause` or future stop control via Mission Control task request
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Summarize what was completed, what was stopped, what evidence was preserved, and what follow-up would be needed to restart later.
- If only a partial report exists, say so explicitly.

## Approval behavior

Stopping active work is a user decision. If the backend distinguishes graceful stop versus force stop, make that distinction explicit before acting.

## Never do

- Do not kill processes unsafely from chat.
- Do not discard partial state or handoff evidence.
- Do not call a stop successful if Mission Control only paused.

## Failure and fallback

If there is no dedicated stop control yet, use the safest pause or no-new-work pattern available, and clearly tell the user that full stop support is expected or future.

## Example invocation

`Stop the Mission Control orchestration safely and summarize the partial state.`
