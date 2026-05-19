# Troubleshooting CLI Runners

This page is a focused runner troubleshooting reference for Codex CLI, Ollama, Claude CLI, API providers, and dry-run mode.

> Status: Current

## Codex CLI

Detection:

- CLI installed
- login status readable

Common issues:

- CLI missing
- not logged in

Fixes:

- verify installation
- run login flow
- re-run plugin health checks

## Ollama and Claude CLI

Ollama:

- detect service
- detect installed models
- common issue: service not running
- common issue: requested model missing locally

Claude CLI:

- detect CLI
- common issue: not configured on the local machine
- fallback: keep current runner or use dry_run

## API providers and dry-run

API providers:

- require explicit secure config
- may incur billing
- should never require raw key pasting into chat

Dry-run:

- safe fallback
- useful for docs, bridge behavior, and workflow validation
- should not be presented as proof of real execution

## Checks and fixes by runner

Codex CLI checks:

```powershell
codex --version
codex login status
```

Ollama checks:

- confirm the service is running
- confirm the required model is installed

Claude CLI checks:

- confirm the CLI exists on PATH
- confirm local configuration is present

API provider checks:

- confirm secure provider config exists
- confirm billing expectations are understood

## Related pages

Continue with [Runner Configuration](Runner-Configuration), [Provider Autowiring](Provider-Autowiring), [Dry Run Mode](Dry-Run-Mode), and [Debugging Common Issues](Debugging-Common-Issues).
