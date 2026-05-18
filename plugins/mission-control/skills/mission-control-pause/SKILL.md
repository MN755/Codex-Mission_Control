---
name: mission-control-pause
description: Pause Mission Control orchestration safely. Use when the user wants to pause after the current task, pause immediately, or stop assigning new work without discarding the current state.
---

# Mission Control Pause

## Purpose

Pause Mission Control work without losing the current state summary.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks to pause.
- Work should stop assigning new tasks.
- A risky moment needs a deliberate hold.

## Workflow

1. Clarify the pause mode if needed: after current task, immediately, or stop assigning new tasks.
2. Call `mission_control_pause` if supported.
3. Confirm what is paused, what remains in flight, and what will be needed to resume.

## Mission Control calls

Tools:
- `mission_control_pause`
- `mission_control_get_status`

Resources:
- `mission-control://orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/status`

## User-facing output

- State the pause mode, active tasks affected, and the next resume checkpoint.
- Keep it operational and brief.

## Approval behavior

Pausing is usually user-directed. If the requested pause mode could interrupt risky operations, say so before issuing it.

## Never do

- Do not claim work is paused without a backed status change.
- Do not kill processes unsafely from chat.
- Do not forget to summarize what was in progress.

## Failure and fallback

If the backend only supports a generic pause, explain that limitation and use the safest available pause option.

## Example invocation

`Pause Mission Control after the current task finishes.`
