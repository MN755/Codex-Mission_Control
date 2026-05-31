# Background Install

> Status: Current

This page documents the shipped headless install path for Mission Control. Codex chat is the bridge, the daemon owns orchestration, and the standalone dashboard is optional.

## Recommended PowerShell entrypoint

```powershell
.\scripts\install-mission-control-plugin.ps1
.\scripts\install-mission-control-plugin.ps1 -DryRun
.\scripts\install-mission-control-plugin.ps1 -InstallDir C:\MissionControl
.\scripts\install-mission-control-plugin.ps1 -SkipCodexSync -SkipPythonSetup
.\scripts\install-mission-control-plugin.ps1 -DaemonHost 127.0.0.1 -DaemonPort 8010
```

The shipped PowerShell wrapper currently supports:

- `-RepoUrl`
- `-InstallDir`
- `-CodexHome`
- `-DryRun`
- `-SkipCodexSync`
- `-SkipPythonSetup`
- `-PythonCommand`
- `-DaemonHost`
- `-DaemonPort`

## What the install flow does

- clones or reuses the Mission Control repo
- runs the unified install workflow through `scripts/mission-control-manage.py`
- probes local prerequisites, daemon readiness, and safe runner availability
- syncs plugin, MCP, prompt, and skill assets into Codex-facing locations unless explicitly skipped
- returns a compact install summary that stays safe for chat

## Health and repair posture

- `.\scripts\mission-control-headless-health.ps1` is the read-only health lane
- install and update workflows handle missing asset sync and config reconciliation through the shipped workflow, not fake wrapper flags
- if you want a non-mutating rehearsal, use `-DryRun`

Unsupported wrapper flags such as `-HeadlessOnly`, `-Repair`, and `-HealthCheckOnly` are not part of the shipped PowerShell installer surface.

## Expected summary

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
- [Troubleshooting](TROUBLESHOOTING.md)
