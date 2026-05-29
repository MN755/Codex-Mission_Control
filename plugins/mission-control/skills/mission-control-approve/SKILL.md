---
name: mission-control-approve
description: Relay Mission Control approvals and questions to the user. Use when there are pending command approvals, tool approvals, write permissions, Manager questions, swarm approvals, recovery decisions, or handoff review gates.
---

# Mission Control Approve

## Purpose

Present pending Mission Control decisions clearly and relay the user response back safely.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- A pending decision blocks progress.
- The user asks what needs approval.
- Mission Control is waiting on user input.

## Workflow

1. Fetch pending decisions with `mission_control_get_pending_decisions` or the pending-decisions resource.
2. Render the top decision with reason, risk, options, and any relevant scope.
3. Ask the user to choose when no answer is provided.
4. Call `mission_control_answer_decision` with the selected answer.
5. Confirm the updated status.

## Mission Control calls

Tools:
- `mission_control_get_pending_decisions`
- `mission_control_answer_decision`

Resources:
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`

## User-facing output

- Identify the decision type: command approval, tool approval, write permission, Manager question, swarm approval, snapshot approval, handoff review, recovery decision, or scope change decision.
- Explain the risk and the likely impact of each option.
- Confirm whether the decision was accepted, denied, deferred, or still pending.

## Approval behavior

This skill exists to preserve approvals. Never auto-answer a pending decision unless Mission Control explicitly marks it safe and the user already delegated that choice.

## Never do

- Do not answer on the user's behalf.
- Do not hide the risk level.
- Do not bypass write-permission or swarm approval gates.

## Failure and fallback

If decision-answer tooling is unavailable, present the pending decision textually and tell the user that manual resolution through the expected tool is still required.

## Example invocation

`Show me the pending Mission Control approval and let me choose.`
