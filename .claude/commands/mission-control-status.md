Check Mission Control status for this workspace.

Workflow:

1. Reuse the current project/workspace through `mission_control_attach_workspace` if needed.
2. Fetch `mission_control_get_status`.
3. Fetch `mission_control_get_pending_decisions` if the status says user action is required.
4. Fetch `mission_control_get_event_digest` with `window=last_15_minutes` when recent progress matters.
5. Summarize:
   - current phase
   - whether user action is required
   - blockers
   - next expected step

Keep the response compact. No raw logs.
