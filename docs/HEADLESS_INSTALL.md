# Background Install

> Status: Current

This page documents the shipped headless install path for Mission Control. Codex chat is the bridge, the daemon owns orchestration, and the standalone dashboard is optional.

## One-Command Install

Use the unified installer first:

```powershell
python scripts/mission-control-manage.py install
```

That is the current supported one-command install path.

## Optional PowerShell Wrapper

If you specifically want the PowerShell wrapper, it still exists:

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

## What the unified install flow does

- clones or reuses the Mission Control repo
- runs the daemon/plugin/MCP install workflow through `scripts/mission-control-manage.py`
- probes local prerequisites, daemon readiness, and safe runner availability
- syncs plugin, MCP, prompt, and skill assets into Codex-facing locations unless explicitly skipped
- returns a compact install summary that stays safe for chat

## Validate After Install

```powershell
python scripts/mission-control-manage.py codex-smoke --json
powershell -ExecutionPolicy Bypass -File scripts/smoke-headless-happy-path.ps1
```

The second command validates the real small happy path instead of just claiming the daemon exists.

## Health and Repair Posture

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
- [Headless Happy Path](HEADLESS_HAPPY_PATH.md)
- [Runner Support Matrix](RUNNERS.md)
- [Autowire Providers](AUTOWIRE_PROVIDERS.md)
- [Troubleshooting](TROUBLESHOOTING.md)
