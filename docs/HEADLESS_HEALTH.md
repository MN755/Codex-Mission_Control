# Headless Health

Mission Control exposes a headless install doctor for Codex plugin and MCP mode.

## Endpoints

- `GET /api/plugin/health`
- `GET /api/headless/health`
- `GET /api/runners/status`

## What gets checked

- daemon reachability
- MCP server presence and live status when Codex exposes it
- MCP tools, resources, and prompts metadata when available
- plugin package files
- local skill files
- runner registry
- runtime directory writability
- SQLite reachability
- localhost-only binding
- dashboard status as optional only

## PowerShell health command

```powershell
.\scripts\mission-control-headless-health.ps1
```

## MCP asset validation

```powershell
.\scripts\start-mission-control-mcp.ps1
```

That script validates the stdio bridge assets and expected local wiring. It does not pretend the MCP bridge is a public TCP server, because that would be nonsense.
Use `-Serve` only if you intentionally want to launch the stdio MCP process in the foreground.
