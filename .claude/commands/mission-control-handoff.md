Review the latest Mission Control handoff for this workspace.

Workflow:

1. Reuse the current project/workspace through `mission_control_attach_workspace` if needed.
2. Fetch `mission_control_get_handoff_summary`.
3. If helpful, fetch `mission_control_get_event_digest` with `window=since_last_user_interaction`.
4. Summarize:
   - handoff status
   - evidence or missing evidence
   - how to run
   - known limitations
   - next recommended tasks

Do not claim tests passed unless the handoff evidence says they passed.
