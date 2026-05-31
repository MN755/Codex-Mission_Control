# Show pending approvals

Alias for `show_pending_approvals`.
Canonical prompt: `show_pending_approvals`
Invocation name: `show-pending-approvals`

## Purpose

Load the current pending decisions and present the top user-facing approval or question cleanly.

## Tool Sequence

- `mission_control_get_pending_decisions`

## Resource Sequence

- `mission-control://projects/{project_id}/pending-decisions`

## Safety Notes

Do not answer the decision until the user explicitly chooses an option.

## Prompt Text

Show the current pending approvals or manager questions from Mission Control. Render the highest-priority decision in compact markdown with risk, reason, and options.
