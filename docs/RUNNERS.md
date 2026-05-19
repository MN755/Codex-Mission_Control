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
- `custom_api`

## Detection model

- `dry_run` is always the safe fallback
- `codex_cli` is preferred when installed and signed in
- `ollama` is treated as a local endpoint and must be reachable
- `claude_cli` depends on a working local CLI environment
- API-backed runners require explicit secure configuration and may incur billing

## Operational rules

- Mission Control should not silently switch a project onto a billed API path
- local-first options are preferred when they satisfy the task
- missing auth is surfaced as a clear blocker, not hidden as degraded success
- runner selection stays behind Mission Control policy, not ad hoc chat decisions

## Read next

- [Autowire Providers](AUTOWIRE_PROVIDERS.md)
- [Background Health](HEADLESS_HEALTH.md)
- [Troubleshooting](TROUBLESHOOTING.md)
