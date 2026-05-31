# Review latest handoff

Alias for `review_latest_handoff`.
Canonical prompt: `review_latest_handoff`
Invocation name: `review-latest-handoff`

## Purpose

Retrieve the latest Mission Control handoff and summarize it for Codex chat.

## Tool Sequence

- `mission_control_get_handoff_summary`

## Resource Sequence

- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/validation-summary`

## Safety Notes

Warn if the handoff is dry-run or missing evidence.

## Prompt Text

Review the latest Mission Control handoff and summarize what changed, how to run it, what validation exists, what limitations remain, and what next steps are recommended.
