# Answer pending approval


Canonical prompt: `answer_pending_approval`
Invocation name: `answer_pending_approval`

## Purpose

Send the user's selected answer back to Mission Control and confirm the result.

## Tool Sequence

- `mission_control_answer_decision`
- `mission_control_get_pending_decisions`

## Resource Sequence

- `mission-control://projects/{project_id}/pending-decisions`

## Safety Notes

Preserve exact user intent, especially for one-time versus project-wide approvals.

## Prompt Text

Answer the pending Mission Control decision with the user's chosen option, then confirm the updated decision state without implying that any blocked action already ran.
