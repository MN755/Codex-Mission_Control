# Answer Pending Approval

## Purpose

Send the user's selected answer back to Mission Control and confirm the result.

## Required Arguments

- `DECISION_ID`
- `OPTION_ID`
- `SELECTED_TEXT`
- `FREE_TEXT` when needed

## Intended Tool And Resource Sequence

1. Call `mission_control_answer_decision`.
2. Call `mission_control_get_pending_decisions`.

## Expected User-Facing Codex Chat Output

- Confirmation that the answer was recorded
- Whether more pending decisions remain

## Safety Notes

- Preserve the user's exact choice.
- Do not imply the gated action already ran.
