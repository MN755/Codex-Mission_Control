Review Mission Control pending decisions and relay the user's answer if one was provided in `$ARGUMENTS`.

Workflow:

1. Fetch `mission_control_get_pending_decisions`.
2. If there are no pending decisions, say so directly.
3. If `$ARGUMENTS` is empty, list the pending decisions with the available options and recommended option.
4. If `$ARGUMENTS` clearly matches an option id or label for the top pending decision, call `mission_control_answer_decision`.
5. After answering, fetch `mission_control_get_status` and summarize the new state.

Do not guess at the user's intent when the option is ambiguous.
