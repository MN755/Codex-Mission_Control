---
name: mission-control-path-locks
description: Show file and path ownership and conflicts in Mission Control. Use when the user wants to know which paths are locked, which agent owns them, which tasks are waiting, or how to resolve edit collisions safely.
---

# Mission Control Path Locks

## Purpose

Explain path ownership, waiting tasks, and conflicts without touching files directly.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks why work is waiting.
- Agents may be colliding on the same files.
- A safe refactor depends on ownership clarity.

## Workflow

1. Read the path-locks resource.
2. Summarize locked paths, owning agent or task, waiting tasks, conflicts, and suggested resolution.
3. Route any ownership change through Mission Control.

## Mission Control calls

Tools:
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/path-locks`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Show locked paths, owner agent or task, waiting tasks, conflicts, and suggested resolution.
- Emphasize why the lock exists if Mission Control provides that detail.

## Approval behavior

If resolution involves force-reassigning ownership or interrupting work, relay that as an explicit approval-worthy action.

## Never do

- Do not reassign ownership from chat by assumption.
- Do not describe unlocked paths as locked.
- Do not hide conflict risk.

## Failure and fallback

If a dedicated path-locks resource is missing, derive the picture from swarm state and agent status, and label it as a best-effort summary.

## Example invocation

`Show the Mission Control path locks and any current conflicts.`
