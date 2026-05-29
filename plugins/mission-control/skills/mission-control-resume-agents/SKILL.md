---
name: mission-control-resume-agents
description: Resume paused Mission Control agents or projects when safe. Use when the user wants paused work restarted but approvals, safety conditions, and current status should be checked first.
---

# Mission Control Resume Agents

## Purpose

Resume paused work only after checking safety and pending approvals.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants paused agents resumed.
- A pause has already happened and work can continue.
- Safety conditions must be verified before restarting.

## Workflow

1. Check current status and pending decisions.
2. Confirm the work is actually paused and not already running.
3. Call `mission_control_resume` only if safe.
4. Summarize the post-resume state and next checkpoint.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_resume`

Resources:
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/agents`

## User-facing output

- Show whether resume is safe, what approvals are still pending, and which agents or tasks are active again after resume.
- Explain clearly if resume is blocked.

## Approval behavior

If pending approvals still block execution, present them first instead of resuming blindly.

## Never do

- Do not resume work that was paused for unresolved risk without user awareness.
- Do not treat resume as a status check only.
- Do not restart already-running work.

## Failure and fallback

If granular agent resume is not supported, explain whether resume applies at project or orchestration level and use the safest available scope.

## Example invocation

`Resume the paused Mission Control agents if it is safe.`
