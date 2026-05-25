# Background Install

> Status: Current

This page describes the preferred install path for Mission Control: set up the daemon, plugin assets, MCP bridge, and skills for background running without relying on the standalone UI.

## What the background install does

- prepares or reuses a local Mission Control checkout
- syncs plugin and skill assets when supported
- generates a safe local configuration
- probes supported runners
- verifies daemon and MCP bridge health
- returns a compact install summary for Codex chat

## PowerShell examples

```powershell
.\scripts\install-mission-control-plugin.ps1 -HeadlessOnly
.\scripts\install-mission-control-plugin.ps1 -DryRun
.\scripts\install-mission-control-plugin.ps1 -Repair
.\scripts\install-mission-control-plugin.ps1 -HealthCheckOnly
```

## Default behavior

- daemon host defaults to `127.0.0.1`
- `dry_run` is always available
- `codex_cli` is preferred when installed and signed in
- `ollama` uses the built-in local adapter recipe and becomes runnable only when the local endpoint is reachable
- API-backed runners use built-in adapter recipes but stay non-runnable unless they were configured securely and intentionally
- requested `install_path` is now treated as real source-of-truth for plugin and skill path reporting instead of cosmetic metadata

## What is not automatic

- no dashboard requirement
- no silent API billing
- no raw API key collection in chat
- no automatic large model downloads
- no destructive repair actions without user awareness

## Expected install summary

```text
Mission Control install summary

- Repo: attached
- Daemon: ready on localhost
- MCP bridge: configured
- Skills: available
- Preferred runner: codex_cli
- Missing action: none
```

## Related docs

- [Quick Start](QUICK_START.md)
- [Autowire Providers](AUTOWIRE_PROVIDERS.md)
- [Background Health](HEADLESS_HEALTH.md)
- [Troubleshooting](TROUBLESHOOTING.md)
