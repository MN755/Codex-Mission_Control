# Pending Decisions

> Status: Current

Pending decisions are the canonical way Mission Control asks the user for approval, scope clarification, or recovery choices through Codex chat.

## Common decision types

- `command_approval`
- `tool_approval`
- `write_permission`
- `manager_question`
- `swarm_approval`
- `snapshot_approval`
- `handoff_review`
- `recovery_decision`
- `scope_change_decision`
- `safe_mode_confirmation`

## How the flow works

1. Mission Control creates a pending decision.
2. Codex chat reads the safe summary.
3. The user chooses an option.
4. Codex returns the answer through `mission_control_answer_decision`.
5. Mission Control resumes with the recorded decision.

Invalid answers are rejected so Mission Control does not quietly continue on made-up options.

## What the user should see

- decision type
- short title
- reason
- risk level
- available options
- recommended option when appropriate
- whether the answer applies once or more broadly

## What should stay hidden by default

- raw secrets
- secret-like command arguments
- raw logs
- oversized execution payloads

## Related docs

- [Codex Chat Mode](CODEX_CHAT_MODE.md)
- [MCP Plugin Bridge](MCP_PLUGIN_BRIDGE.md)
- [Security](SECURITY.md)
- [Handoffs](HANDOFFS.md)
