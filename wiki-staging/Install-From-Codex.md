# Install From Codex

This page documents the current Codex-native install workflow when the user asks Codex chat to install and wire up Mission Control from GitHub.

> Status: Current

## Recommended prompt

Ask Codex chat directly:

```text
Install Mission Control from https://github.com/MN755/Codex-Mission_Control and wire it up for this workspace.
```

## What the shipped flow does

The shipped headless install path is real, not aspirational:

1. Clone or reuse the repository.
2. Run the unified install workflow through `scripts/install-mission-control-plugin.ps1` or `scripts/mission-control-manage.py install`.
3. Probe local prerequisites, runtime folders, daemon readiness, and safe local runners.
4. Sync plugin, MCP, and skill assets into Codex-facing locations unless explicitly skipped.
5. Return a compact install summary back into Codex chat without requiring the standalone dashboard.

## Current PowerShell entrypoint

The shipped PowerShell installer currently supports these parameters:

- `-RepoUrl`
- `-InstallDir`
- `-CodexHome`
- `-DryRun`
- `-SkipCodexSync`
- `-SkipPythonSetup`
- `-PythonCommand`
- `-DaemonHost`
- `-DaemonPort`

Practical examples:

```powershell
.\scripts\install-mission-control-plugin.ps1
.\scripts\install-mission-control-plugin.ps1 -DryRun
.\scripts\install-mission-control-plugin.ps1 -InstallDir C:\MissionControl
.\scripts\install-mission-control-plugin.ps1 -SkipCodexSync -SkipPythonSetup
.\scripts\install-mission-control-plugin.ps1 -DaemonHost 127.0.0.1 -DaemonPort 8010
```

## Expected output

A healthy run should end with a compact summary such as:

```text
Mission Control install summary

- Repo: attached
- Daemon: ready on localhost
- MCP bridge: configured
- Skills: available
- Preferred runner: codex_cli
- Missing action: none
```

## Related pages

See [Headless Install and Autowire](Headless-Install-and-Autowire), [Provider Autowiring](Provider-Autowiring), and [Diagnostics and Health Checks](Diagnostics-and-Health-Checks).
