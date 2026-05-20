Use Mission Control for this repository and treat Claude Code as the bridge, not the Manager.

If the `mission-control` MCP server is unavailable, tell the user to approve the project MCP server from `.mcp.json` in Claude Code and stop there instead of pretending the bridge exists.

Workflow:

1. Attach or reuse the current workspace with `mission_control_attach_workspace`.
2. If `$ARGUMENTS` is empty, ask the user for the task Mission Control should run.
3. Start or continue the task with `mission_control_start_task` using the user's request from `$ARGUMENTS`.
4. Fetch `mission_control_get_status`.
5. If there are pending approvals or questions, fetch `mission_control_get_pending_decisions` and present them clearly.
6. Summarize the current state compactly and honestly. Mark dry-run clearly if the bridge reports dry-run.

Do not become the Manager AI yourself.
