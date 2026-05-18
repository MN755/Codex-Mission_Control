---
name: mission-control-event-digest
description: Summarize recent Mission Control events without raw logs. Use when the user wants the last 5 minutes, last 15 minutes, since last interaction, or since orchestration start summarized in bridge-safe markdown.
---

# Mission Control Event Digest

## Purpose

Return a short event digest that is useful in chat and safe by default.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants recent activity.
- A long-running orchestration needs a short event recap.
- Raw logs would be too noisy or unsafe.

## Workflow

1. Call `mission_control_get_event_digest` or the closest backed event summary path.
2. Apply the requested window: last 5 minutes, last 15 minutes, since last user interaction, or since orchestration start.
3. Summarize the major transitions, blockers, approvals, and completions.

## Mission Control calls

Tools:
- `mission_control_get_event_digest`

Resources:
- `mission-control://orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Return a concise timeline of meaningful events, not raw event spam.
- Highlight approvals, failures, pauses, resumes, and handoff-related milestones.

## Approval behavior

Reading an event digest is read-only. If the user wants action on an event, switch to the corresponding skill.

## Never do

- Do not dump raw logs or full event streams.
- Do not smooth over failures.
- Do not infer event timing without clear backing data.

## Failure and fallback

If the event-digest tool is not exposed yet, synthesize a digest from current status and known checkpoints, then label the result as approximate.

## Example invocation

`Give me a Mission Control event digest for the last 15 minutes.`
