# No-UI Setup

Mission Control headless mode is meant for Codex chat first.

## What that means

- you do not need the standalone dashboard to install or use Mission Control
- daemon and MCP stay localhost-only
- chat summaries, approvals, and handoffs are the primary user surface
- the dashboard stays optional for observability

## Typical workflow

1. Install or repair with the headless bootstrap script.
2. Check health.
3. Let Codex attach the current workspace.
4. Ask Codex to use Mission Control.
5. Answer approvals or manager questions in chat.
6. Review the final handoff in chat.

## Common errors

- Codex CLI installed but not logged in
- Ollama installed but not running
- Claude CLI present but auth not confirmed
- plugin package exists locally but Codex MCP config was not reloaded
- Python dependencies missing for the local daemon
