# Diagnostics and Health Checks

This page describes how to inspect plugin, daemon, MCP, runner, and runtime health without relying on the optional dashboard.

> Status: Current

## What to check

Health checks should cover:

- plugin health doctor
- daemon health
- MCP bridge health
- runner health
- runtime writable state
- Codex CLI login
- Ollama status
- Claude CLI status
- Webwright readiness when browser-agent automation is part of the task
- startup freshness and last completed check time
- degraded vs broken classification

## Example commands

Copyable checks:

```powershell
.\scripts\start-mission-control-daemon.ps1
.\scripts\mission-control-support-bundle.ps1
Invoke-WebRequest http://127.0.0.1:8010/api/health
codex --version
codex login status
```

## Example diagnostic summary

Example:

```text
Mission Control health

- Overall: degraded
- Daemon: ready
- MCP bridge: ready
- Codex CLI: missing login
- Ollama: not running
- Webwright: optional and not installed
- Runtime folder: writable
- Recommended next step: log into Codex CLI or use dry_run
```

## Related pages

Read [Plugin Health Doctor](Plugin-Health-Doctor), [Debugging Common Issues](Debugging-Common-Issues), [Troubleshooting CLI Runners](Troubleshooting-CLI-Runners), and [Logs and Runtime Folders](Logs-and-Runtime-Folders).
