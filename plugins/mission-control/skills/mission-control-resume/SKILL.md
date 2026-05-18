---
name: mission-control-resume
description: Resume an existing Mission Control orchestration from a new Codex chat. Use when the user returns later and wants Codex to reattach, find the active or recent orchestration, show state, surface pending decisions, and continue safely.
---

# Mission Control Resume

## Purpose

Reattach Codex chat to an existing Mission Control run and continue safely.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user returns in a new chat and says to continue Mission Control.
- An existing workspace already has recent orchestration state.
- You need to find the last known state before acting.

## Workflow

1. Attach the current workspace.
2. Find the active or recent orchestration from status resources or the attach result.
3. Return the last known state, active agents, blockers, and pending decisions.
4. Resume through `mission_control_resume` only if the run is paused and it is safe to do so.
5. If already running, summarize instead of issuing duplicate resume actions.

## Mission Control calls

Tools:
- `mission_control_attach_workspace`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_resume`

Resources:
- `mission-control://orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Show the recovered project or orchestration reference, last known phase, pending decisions, and whether a resume action is still needed.
- If safe to resume, confirm the post-resume state.

## Approval behavior

Do not resume if pending approvals would immediately block or if the user has not confirmed a risky restart choice.

## Never do

- Do not start a new orchestration when a resume is the right path.
- Do not claim recovery if no prior project can be found.
- Do not override paused state without checking why it was paused.

## Failure and fallback

If active-or-recent orchestration lookup is limited, attach the workspace, report the latest project status you can find, and ask the user whether to resume manually through the expected Mission Control control surface.

## Example invocation

`Resume the existing Mission Control run for this workspace.`
