Resume an existing Mission Control orchestration for this workspace.

Workflow:

1. Reuse the current project/workspace with `mission_control_attach_workspace`.
2. Fetch `mission_control_get_status`.
3. If the orchestration is paused, call `mission_control_resume`.
4. Fetch updated status and pending decisions.
5. Summarize what resumed, what is blocked, and whether the user needs to answer anything.

If the bridge reports that no orchestration exists yet, say so instead of improvising one.
