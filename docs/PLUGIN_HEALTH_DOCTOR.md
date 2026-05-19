# Plugin Health Doctor

> Status: Partial / Experimental

Plugin Health Doctor is the read-only health summary for the Codex plugin, MCP bridge, daemon, and local runner surfaces.

## Overall result states

- `ready`
- `degraded`
- `broken`

## Checks

- daemon reachable
- MCP server reachable
- MCP tools registered when metadata is available
- MCP resources registered when metadata is available
- MCP prompts registered when metadata is available
- plugin package exists
- skill files exist
- Codex CLI detected
- runtime directory writable
- local database reachable
- localhost-only binding

## Security behavior

Health Doctor should not expose daemon tokens, API keys, `.env` contents, or raw secret values. It should return high-level state and safe troubleshooting guidance only.

## Related docs

- [Headless Health](HEADLESS_HEALTH.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security](SECURITY.md)
