Enable Mission Control safe mode for this workspace.

Workflow:

1. Reuse the current project/workspace with `mission_control_attach_workspace`.
2. Call `mission_control_enable_safe_mode`.
3. Fetch `mission_control_get_status`.
4. Explain what safe mode changed, what approvals are likely now, and whether Mission Control is waiting on the user.

Do not pretend safe mode makes unsafe actions disappear. It just raises the approval bar like it should.
