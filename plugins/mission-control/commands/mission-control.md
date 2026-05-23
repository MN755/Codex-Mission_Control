---
description: Start or continue a Mission Control task from Claude Code
disable-model-invocation: false
---

Use Mission Control for the current repository.

Workflow:

1. Confirm the `mission-control` MCP server is available. If it is missing, tell the user to approve the project MCP server from `.mcp.json` and stop.
2. Attach or reuse the current workspace with `mission_control_attach_workspace`.
3. If `$ARGUMENTS` is empty, ask the user for the task.
4. Start or continue the task with `mission_control_start_task` using `$ARGUMENTS`.
5. Fetch status and pending decisions.
6. Report state, blockers, active agents, pending approvals, and next action.

Claude Code is the bridge. Mission Control is the Manager.
