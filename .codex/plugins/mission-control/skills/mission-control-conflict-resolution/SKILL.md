---
name: mission-control-conflict-resolution
description: Resolve Mission Control agent or merge conflicts safely. Use when paths overlap, outputs disagree, or Mission Control needs a user-visible conflict-resolution path instead of hidden reassignment.
---

# Mission Control Conflict Resolution

## Purpose

Summarize conflicts and route resolution through Mission Control rather than improvising edits.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- Agents conflict on paths or task ownership.
- A merge or handoff conflict needs explanation.
- The user wants options before forcing a resolution.

## Workflow

1. Fetch conflicts from path-locks, status, and agent resources.
2. Summarize involved agents, tasks, and paths.
3. Ask Mission Control for resolution options if available.
4. Present high-risk options to the user and relay the selected resolution.
5. Confirm the updated state afterward.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_answer_decision`

Resources:
- `mission-control://projects/{project_id}/path-locks`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Show involved paths and agents, the likely cause, available resolution options, and the risk of each option.
- Confirm the chosen resolution when Mission Control records it.

## Approval behavior

High-risk reassignment, merge resolution, or forced interruption should be presented as explicit decisions.

## Never do

- Do not resolve conflicts by guessing the better owner.
- Do not hide competing risks.
- Do not rewrite files directly from chat to 'fix' a coordination problem.

## Failure and fallback

If a conflict-resolution tool is not exposed, surface the conflict, explain that a Manager decision is still needed, and guide the user to the best matching approval or recovery flow.

## Example invocation

`Mission Control agents are conflicting. Show me the resolution options.`
