# Runners

> Status: Partial / Experimental

Mission Control uses runners to execute background work. Runner availability depends on the local machine, installed tools, authentication state, and explicit configuration.

## Supported runner types

- `dry_run`
- `codex_cli`
- `ollama`
- `claude_cli`
- `openai_api`
- `anthropic_api`
- `xai_api`

## Detection model

- `dry_run` is always the safe fallback
- `codex_cli` is preferred when installed and signed in
- `ollama` uses the built-in `scripts/ollama_adapter.py` recipe and still requires a reachable local endpoint
- `claude_cli` depends on a working local CLI environment
- API-backed runners use the built-in `scripts/api_provider_adapter.py` recipe, still require secure external API keys, and may incur billing

## Built-in adapter recipes

- Mission Control now ships first-class default adapter recipes for `ollama`, `openai_api`, `anthropic_api`, and `xai_api`
- those recipes use the current Python interpreter plus the repo-local adapter script
- users can still override the adapter command or args explicitly when they need a custom path
- `custom` providers stay opt-in and do not get a fake default recipe

## Operational rules

- Mission Control should not silently switch a project onto a billed API path
- local-first options are preferred when they satisfy the task
- missing auth is surfaced as a clear blocker, not hidden as degraded success
- runner selection stays behind Mission Control policy, not ad hoc chat decisions

## Read next

- [Autowire Providers](AUTOWIRE_PROVIDERS.md)
- [Background Health](HEADLESS_HEALTH.md)
- [Troubleshooting](TROUBLESHOOTING.md)
