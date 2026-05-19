# Codex Chat Mode

> Status: Current

Codex chat mode is the primary user experience for Mission Control. The chat agent is the bridge between the user and the Mission Control daemon; it is not the Manager AI.

## Core rule

Mission Control owns:

- the Manager AI
- orchestration state
- worker coordination
- pending decisions
- diagnostics and handoff generation

Codex chat owns:

- attaching the workspace
- starting or resuming the requested task
- reading safe resources
- relaying approvals and questions
- returning compact summaries to the user

## Normal loop

1. Attach the current workspace.
2. Start or resume a Mission Control task.
3. Read status, pending decisions, diagnostics, or handoff resources as needed.
4. Relay any decision to the user and return the answer through the bridge.
5. Continue until Mission Control produces a handoff.

## Output expectations

Codex chat should present:

- compact status updates
- structured approval requests
- manager questions with context
- event digests when useful
- handoff summaries with evidence and limitations

Codex chat should not:

- invent a separate orchestration plan
- bypass Mission Control approvals
- expose secrets or raw logs by default

## Related docs

- [MCP Plugin Bridge](MCP_PLUGIN_BRIDGE.md)
- [Pending Decisions](PENDING_DECISIONS.md)
- [Handoffs](HANDOFFS.md)
- [Security](SECURITY.md)
