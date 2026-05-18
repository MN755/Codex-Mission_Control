# Codex Chat Mode

Mission Control now has a headless Codex-chat mode.

That mode is not the standalone dashboard with fewer pixels. It is a bridge workflow where Codex chat speaks to the Mission Control daemon through MCP tools, resources, and prompts.

## Core Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

Mission Control owns:

- the Manager AI
- background orchestration
- adaptive swarm planning
- worker execution
- approvals and recovery state
- final handoff generation

Codex chat owns:

- attaching the workspace
- relaying user intent
- reading safe MCP resources
- calling Mission Control tools
- surfacing approvals and questions
- passing the user's answer back to Mission Control
- summarizing status and handoff output in bridge-safe markdown

## Headless Workflow Loop

1. The user asks Codex to use Mission Control.
2. Codex attaches the current workspace through `mission_control_attach_workspace`.
3. Codex starts or resumes work through Mission Control tools.
4. Codex reads safe resources for status, agents, decisions, swarm, diagnostics, and handoff.
5. If Mission Control needs a decision, Codex renders it in chat and waits for the user.
6. Codex sends the answer back through the decision tool.
7. Mission Control continues in the background.
8. Codex retrieves the final handoff and summarizes it.

## Safety Model

- MCP resources are read-only context.
- MCP resources must not run commands.
- MCP resources must not expose secrets, tokens, env dumps, or raw logs by default.
- MCP prompts are reusable workflow instructions.
- MCP tools perform actions and must respect approvals.
- Codex chat must not bypass Mission Control approvals.

## Approvals And Questions

Pending approvals and manager questions are surfaced in Codex chat, not answered automatically.

The bridge should show:

- what Mission Control wants
- why it wants it
- risk level
- the safe options available
- whether the answer is one-time or project-wide

The bridge should not:

- pick an answer on behalf of the user
- widen approval scope without explicit user consent
- run the blocked action directly from Codex chat

## Handoff Retrieval

When Mission Control reports that work is ready for handoff, Codex chat should summarize:

- what changed
- how to run it
- what validation exists
- what limitations remain
- what next steps are recommended

If evidence is missing or the run was dry-run only, say so directly.

## No Dashboard Requirement

The standalone Mission Control dashboard is optional for this mode.

This pass assumes:

- no dashboard is required
- no React UI work is required
- no API key is required for normal Codex login-based usage

The bridge should remain useful from inside Codex chat alone.
