---
name: mission-control-status
description: Give a clean Mission Control status update. Use when the user asks for current progress, blockers, active agents, pending decisions, next step, or handoff readiness without wanting raw logs.
---

# Mission Control Status

## Purpose

Return a bridge-safe Mission Control status summary.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for status, progress, blockers, or what happens next.
- A long-running orchestration needs a concise checkpoint.
- The user wants a summary without opening dashboard UI or logs.

## Workflow

1. Call `mission_control_get_status` or read the project or orchestration status resource.
2. Read active agents and pending decisions resources.
3. Identify Manager state, blockers, next expected step, and handoff readiness.
4. Return a concise summary without event spam or raw logs.

## Mission Control calls

Tools:
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`

## User-facing output

- Include project, orchestration state, Manager state, active agents, pending decisions, blockers, next step, and handoff readiness.
- Keep the summary short enough for chat and safe enough for copy-paste.

## Approval behavior

Status reads should be read-only. If the user asks to act on the status, switch to the matching approval, pause, resume, or stop skill.

## Never do

- Do not dump raw logs.
- Do not invent progress if the backend is stale.
- Do not hide blockers to sound smoother.

## Failure and fallback

If only partial resources are available, say which pieces are missing and summarize only what is backed by the resource or tool output.

## Example invocation

`Give me a Mission Control status update for this workspace.`
