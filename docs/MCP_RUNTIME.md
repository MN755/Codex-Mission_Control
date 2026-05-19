# MCP Runtime

Mission Control is headless-first in Codex chat mode.

Codex chat is the bridge.
Mission Control daemon is the orchestrator.
The Manager AI and worker runners stay behind the daemon boundary.

## Runtime Flow

Codex chat
-> Mission Control skills and prompts
-> MCP tools, resources, and prompts
-> local daemon API on `127.0.0.1`
-> Manager AI
-> worker runners

## Bridge Rules

- Codex chat does not act as the Manager AI.
- MCP tools call daemon APIs only.
- MCP resources are read-only summaries.
- MCP prompts are reusable workflow instructions.
- Pending decisions are relayed back to Codex chat for the user to answer.
- Raw logs, tokens, and secrets do not cross the bridge by default.

## Headless Boundary

- Dashboard startup is optional.
- The daemon and MCP bridge are the required runtime for Codex chat mode.
- The MCP server should bind to localhost only.
- Worker commands do not run directly from the MCP server.

## Security Model

- high-risk actions stay gated behind pending decisions
- resource reads are summary-only and redacted
- no arbitrary shell execution is exposed through MCP tools
- no standalone UI is required for orchestration, approvals, or handoff review
