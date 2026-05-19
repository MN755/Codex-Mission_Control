# Headless Install

Mission Control can be installed and wired for Codex chat without opening the standalone app.

## What this mode does

- clones or reuses the Mission Control repo
- syncs the repo-local plugin bundle into Codex home when possible
- syncs Mission Control skills into Codex home when possible
- generates a safe headless config
- detects local runners
- verifies daemon and plugin health
- validates MCP bridge assets
- returns a chat-ready install report

## Windows-first install flow

```powershell
.\scripts\install-mission-control-plugin.ps1 -HeadlessOnly
```

Clone into a dedicated location:

```powershell
.\scripts\install-mission-control-plugin.ps1 -RepoUrl "https://github.com/MN755/Codex-Mission_Control" -InstallDir "$env:LOCALAPPDATA\MissionControl" -HeadlessOnly
```

Dry-run and repair:

```powershell
.\scripts\install-mission-control-plugin.ps1 -DryRun
.\scripts\install-mission-control-plugin.ps1 -Repair
.\scripts\install-mission-control-plugin.ps1 -HealthCheckOnly
```

## What gets configured

- daemon host defaults to `127.0.0.1`
- repo-local Mission Control plugin assets are copied into Codex home unless explicitly skipped
- Mission Control skills are copied into Codex home unless explicitly skipped
- dashboard is disabled by default
- `dry_run` is always enabled
- `codex_cli` is enabled when installed and signed in
- `ollama` is enabled when installed and reachable
- `claude_cli` is detected but not auto-enabled when auth is unclear
- API-backed runners stay disabled unless secure external config already exists and the user explicitly wants them

## What is not forced

- no standalone UI
- no automatic API key collection
- no silent external tool installs
- no automatic model downloads
- no dashboard startup requirement

## Example Codex prompt after setup

`Use Mission Control for this repo and fix the failing tests.`
