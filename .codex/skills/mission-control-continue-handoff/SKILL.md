---
name: mission-control-continue-handoff
description: Continue work after a Mission Control handoff without losing continuity. Use when the user wants another iteration, wants limitations preserved, or needs the next change request to build on the previous handoff and evidence.
---

# Mission Control Continue Handoff

## Purpose

Continue from an existing handoff while preserving evidence and limitations.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants to keep going after handoff.
- A new milestone should build on the previous handoff.
- Earlier evidence and limitations still matter.

## Workflow

1. Read the previous handoff first.
2. Summarize preserved limitations, evidence, and unfinished work.
3. Create a change request or next milestone through Mission Control.
4. Track the new iteration without erasing the earlier handoff context.

## Mission Control calls

Tools:
- `mission_control_get_handoff`
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/decision-ledger`

## User-facing output

- Show what carries over from the last handoff, what the new iteration changes, and what evidence must be refreshed.
- Keep old and new scopes distinct.

## Approval behavior

Any new change request that widens scope still requires normal approvals and user consent.

## Never do

- Do not lose the previous limitations.
- Do not overwrite the narrative as if this is a fresh project.
- Do not discard evidence history.

## Failure and fallback

If no explicit continue-handoff workflow exists, use the prior handoff plus a change-request flow and make the continuity objective explicit in the task request.

## Example invocation

`Continue from the last Mission Control handoff and start the next iteration.`
