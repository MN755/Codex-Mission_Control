# Diagnostic Summaries

Mission Control exposes a chat-native diagnostic summary for Codex plugin mode.

## Route

- `GET /api/headless/diagnostic-summary`

This route is bridge-token guarded and returns a `BridgeMessage`.

## Output goals

- show overall status: `ready`, `degraded`, or `broken`
- show what works
- show what needs attention
- show recommended fixes
- show copyable safe commands
- remind the user that the dashboard is optional
- never leak raw secrets

## Example

```md
## Mission Control Diagnostics

**Status:** degraded
**Dashboard:** optional

### What works
- Daemon reachable: Mission Control daemon health endpoint responded successfully.
- Runner registry available: Runner inventory is readable.

### What needs attention
- MCP server reachable: Mission Control MCP server is configured but currently disconnected.
- Codex login status detectable: Codex login status could not be confirmed cleanly.

### Recommended fixes
- Verify the MCP bridge command and reload Codex MCP configuration.
- Run `codex login status` and sign in again if needed.

### Safe commands
- `codex mcp list --json`
- `codex login status`
```

## Redaction

Diagnostic summaries are redacted like any other bridge message.

They must not expose:

- API keys
- bearer tokens
- private keys
- raw `.env` values
- secret-looking provider tokens
