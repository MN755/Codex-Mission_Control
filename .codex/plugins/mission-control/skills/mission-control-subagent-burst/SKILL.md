---
name: mission-control-subagent-burst
description: Recommend or review Mission Control Codex subagent bursts for bounded read-heavy work. Use when the user wants parallel exploration, review, planning, handoff audit, or failure diagnosis without replacing the normal worker system.
---

# Mission Control Subagent Burst

## Purpose

Route short-lived Codex subagent burst recommendations through Mission Control.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The task is read-heavy and parallelizable.
- The user wants bounded parallel exploration or review.
- Mission Control should recommend whether a burst is worth it.

## Workflow

1. Check status and current orchestration context.
2. Fetch subagent policy.
3. Ask Mission Control to recommend a burst for the current task.
4. If a pending decision is created, render it in Codex chat and wait for the user.
5. After approval, fetch the batch and present spawn instructions or manual prompt text.
6. When results come back, send them to Mission Control result ingestion.

## Mission Control calls

Tools:
- `mission_control_get_status`

Daemon/API:
- `GET /api/subagent-policy`
- `POST /api/projects/{project_id}/subagent-bursts/recommend`
- `GET /api/projects/{project_id}/subagent-batches`
- `GET /api/subagents/batches/{batch_id}`
- `POST /api/subagents/batches/{batch_id}/results`
- `GET /api/decisions/{decision_id}/bridge-message`
- `POST /api/decisions/{decision_id}/answer`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Explain whether Mission Control recommends a burst.
- Show purpose, count, risk, intensity, and the proposed subagent list.
- If approved, show spawn instructions and expected report format.

## Approval behavior

Never bypass a `subagent_burst_approval` pending decision. Larger bursts must be answered by the user in Codex chat.

## Never do

- Do not replace the normal Mission Control worker system.
- Do not default to file edits or commands.
- Do not recursively fan out more agents.

## Failure and fallback

If burst planning is unavailable, say so clearly and fall back to normal Mission Control planning or status-only guidance.

## Example invocation

`Ask Mission Control whether a read-only subagent burst makes sense for this repo review.`
