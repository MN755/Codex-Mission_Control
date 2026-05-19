# Background Health

> Status: Current

Mission Control exposes structured health checks for the daemon, MCP bridge, runtime folders, database, and runners so Codex chat can report whether the background-running system is ready, degraded, blocked, or failed.

## Primary checks

- daemon reachability
- MCP bridge registration
- plugin package presence
- skill availability
- runner detection
- runtime directory writability
- local database reachability
- localhost-only binding

Each health item can carry:

- `code`
- `status`
- `severity`
- `summary`
- `recommended_fix`
- `user_action_required`
- `retryable`
- `breakpoint`
- `correlation_id`

## Useful commands

```powershell
.\scripts\mission-control-headless-health.ps1
.\scripts\start-mission-control-mcp.ps1
```

## Expected summary

```text
Mission Control health

- Overall: ready
- Daemon: ready
- MCP bridge: ready
- Codex CLI: ready
- Runtime folder: writable
```

## Common coded health states

| Code | Meaning | Typical status |
| --- | --- | --- |
| `MC-DAEMON-NOT-RUNNING-001` | daemon is not available | `broken` |
| `MC-MCP-BRIDGE-MISSING-001` | MCP bridge is missing or not configured | `broken` |
| `MC-CODEX-CLI-MISSING-001` | Codex CLI is not on PATH | `degraded` |
| `MC-CODEX-LOGIN-UNKNOWN-001` | Codex login could not be confirmed | `degraded` |
| `MC-RUNNER-NONE-AVAILABLE-001` | only dry-run remains usable | `degraded` |
| `MC-STORAGE-DB-UNAVAILABLE-001` | SQLite runtime is unavailable | `broken` |
| `MC-STORAGE-RUNTIME-WRITE-FAILED-001` | runtime folder is not writable | `broken` |
| `MC-NETWORK-LOCALHOST-UNREACHABLE-001` | local daemon endpoint is unreachable | `broken` |

## Example health item

```json
{
  "key": "codex-cli",
  "status": "degraded",
  "summary": "Codex CLI is not available.",
  "code": "MC-CODEX-CLI-MISSING-001",
  "severity": "warning",
  "breakpoint": "codex_cli.detect",
  "recommended_fix": "Install Codex CLI or expose it on PATH, or continue with dry-run mode.",
  "user_action_required": true
}
```

## How to use health output

1. Check the `code`.
2. Check whether `user_action_required` is true.
3. Follow `recommended_fix`.
4. If the issue persists, search the code in [Mission Control Errors](ERRORS.md) and the breakpoint in [Debug Breakpoints](DEBUG_BREAKPOINTS.md).

## Related docs

- [Mission Control Errors](ERRORS.md)
- [Debug Breakpoints](DEBUG_BREAKPOINTS.md)
- [Diagnostic Taxonomy](DIAGNOSTIC_TAXONOMY.md)
- [Background Install](HEADLESS_INSTALL.md)
- [Plugin Health Doctor](PLUGIN_HEALTH_DOCTOR.md)
- [Troubleshooting](TROUBLESHOOTING.md)
