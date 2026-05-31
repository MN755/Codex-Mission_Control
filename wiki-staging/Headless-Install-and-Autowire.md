# Headless Install and Autowire

This page describes the current shipped headless bootstrap and autowire surface for Mission Control plugin mode.

> Status: Current

## Current commands

The shipped headless entrypoints are:

```powershell
.\scripts\install-mission-control-plugin.ps1
.\scripts\install-mission-control-plugin.ps1 -DryRun
.\scripts\mission-control-headless-health.ps1
```

Supporting entrypoints also exist through `scripts/mission-control-manage.py install`, `update`, and `uninstall`.

## What the installer actually supports

The PowerShell wrapper forwards the following supported parameters to the unified install workflow:

- `-RepoUrl`
- `-InstallDir`
- `-CodexHome`
- `-DryRun`
- `-SkipCodexSync`
- `-SkipPythonSetup`
- `-PythonCommand`
- `-DaemonHost`
- `-DaemonPort`

Unsupported fantasy flags such as `-HeadlessOnly`, `-Repair`, and `-HealthCheckOnly` are not part of the shipped command surface.

## What headless install does

The shipped workflow is headless-first:

- avoid requiring dashboard startup
- probe Python, runtime folders, daemon readiness, and local runners
- configure plugin, MCP bridge, prompts, and skills
- summarize what is ready, degraded, or blocked for Codex chat
- keep repair-like actions explicit instead of pretending they happened

## Health and repair reality

`mission-control-headless-health.ps1` is the read-only health lane.

Install and update workflows handle asset sync and configuration repair implicitly when their shipped options are used. If you need a dry run, use `-DryRun` instead of inventing extra wrapper flags.

## Related pages

Continue with [Install From Codex](Install-From-Codex), [Provider Autowiring](Provider-Autowiring), and [Install Reports and Repair Mode](Install-Reports-and-Repair-Mode).
