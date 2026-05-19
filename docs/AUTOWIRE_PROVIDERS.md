# Autowire Providers

> Status: Partial / Experimental

Provider autowiring probes the local environment and enables only the runners that are available, safe, and clearly understood.

## Default behavior

- `dry_run` is always enabled
- `codex_cli` is enabled only when the CLI is present and login can be confirmed
- `ollama` is enabled only when the local server is reachable
- `claude_cli` may be detected without being auto-enabled
- API-backed runners remain disabled unless secure external configuration already exists and the user explicitly wants them

## Safety rules

- do not print raw API keys, tokens, or `.env` contents
- do not trigger billed providers silently
- do not pull large local models without user awareness
- do not treat missing authentication as a successful configuration

## Expected autowire output

- ready runners
- blocked or unknown runners
- missing login or local service steps
- billing notes for API-backed options
- a recommended next action in Codex chat

## Related docs

- [Background Install](HEADLESS_INSTALL.md)
- [Runners](RUNNERS.md)
- [Background Health](HEADLESS_HEALTH.md)
- [Security](SECURITY.md)
