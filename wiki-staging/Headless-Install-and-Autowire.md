# Headless Install and Autowire

This page describes the intended headless bootstrap and repair experience for Mission Control plugin mode.

> Status: Current

## Planned commands

Expected commands:

```powershell
.\scripts\install-mission-control-plugin.ps1 -HeadlessOnly
.\scripts\install-mission-control-plugin.ps1 -DryRun
.\scripts\install-mission-control-plugin.ps1 -Repair
.\scripts\mission-control-headless-health.ps1
```

## What headless install should do

Headless-only install should:

- avoid requiring dashboard startup
- probe Python, runtime folders, and daemon readiness
- configure plugin and MCP bridge files
- copy or point to skills and prompts
- detect runners and summarize availability
- emit an install report suitable for Codex chat

## Repair and health modes

Repair mode should reconcile missing plugin files, stale configs, and runtime-directory problems.

Health mode should stay read-only and report:

- daemon health
- MCP bridge health
- runner availability
- runtime write access
- missing prerequisites

## Current status note

The repo already ships install and health scripts for headless plugin workflows. Use those entrypoints first, then fall back to the manual diagnostics and repair guidance when local prerequisites are missing or degraded.

## Related pages

Continue with [Install From Codex](Install-From-Codex), [Provider Autowiring](Provider-Autowiring), and [Install Reports and Repair Mode](Install-Reports-and-Repair-Mode).
