# Autowire Providers

> Status: Partial / Experimental

Provider autowiring probes the local environment and enables only the runners that are available, safe, and clearly understood.

## Default behavior

- `dry_run` is always enabled
- `codex_cli` is enabled only when the CLI is present and login can be confirmed
- `ollama` gets a built-in local adapter recipe, but it is only runnable when the local server is reachable
- `claude_cli` may be detected without being auto-enabled
- API-backed runners get a built-in adapter recipe, but they stay non-runnable until secure external configuration already exists

## What autowire now persists

- selected provider endpoint for endpoint-backed providers
- built-in adapter command and args for `ollama`, `openai_api`, `anthropic_api`, and `xai_api`
- install-path-aware plugin and skill paths in the headless config
- a fresh startup status check instead of stale cached bootstrap state

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
