---
name: mission-control-decision-ledger
description: Show important Mission Control decisions and assumptions. Use when the user wants to review user decisions, Manager assumptions, auto-decisions, rejected options, or approval history without searching raw events.
---

# Mission Control Decision Ledger

## Purpose

Summarize the project decision ledger and assumption trail.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks why a choice was made.
- A plan or handoff should surface assumptions.
- Approval history matters for auditability.

## Workflow

1. Read the decision-ledger resource and current status.
2. Summarize user decisions, Manager assumptions, auto-decisions, rejected options, and approval history.
3. If clarification is needed, point to the pending-decision or plan revision flow.

## Mission Control calls

Tools:
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/status`

## User-facing output

- List key decisions with impact and current status.
- Highlight assumptions that are still provisional or unconfirmed.

## Approval behavior

If the ledger shows unresolved decisions, route the user to the approval skill instead of guessing.

## Never do

- Do not rewrite history.
- Do not flatten rejected options into accepted ones.
- Do not hide assumptions that affect outcome quality.

## Failure and fallback

If a dedicated decision-ledger resource is not yet exposed, summarize from pending decisions, plan state, and handoff notes and mark the ledger resource as expected or future.

## Example invocation

`Show the Mission Control decision ledger and assumptions.`
