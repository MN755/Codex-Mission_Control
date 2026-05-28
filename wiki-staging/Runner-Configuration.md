# Runner Configuration

This page documents the supported runner types, how Mission Control should detect them, and what the user may need to configure.

> Status: Current

## Supported runner types

Supported runner types:

- `dry_run`
- `codex_cli`
- `ollama`
- `claude_cli`
- `openai_api`
- `anthropic_api`
- `xai_api`
- `custom`

## Detection and user action

Detection guidance:

- `dry_run`: always available and safe fallback
- `codex_cli`: detect local CLI and login state; preferred when available
- `ollama`: use the built-in `scripts/ollama_adapter.py` recipe and require a reachable local endpoint
- `claude_cli`: detect installed CLI and configuration
- `*_api`: use the built-in `scripts/api_provider_adapter.py` recipe but still require secure provider credentials
- `custom`: only available when explicitly configured
- `Webwright`: not a runner type; it is an optional browser-agent companion that should be checked separately when the task is about real browser automation

## Billing and security notes

Notes:

- Codex CLI via ChatGPT/Codex login should be preferred where available.
- API providers may incur billing and require explicit configuration.
- Ollama is local but still requires installed models and local compute budget.
- Built-in adapter recipes reduce setup friction but do not silently make a provider ready when auth or the endpoint is still missing.
- Dry-run is the safe fallback when no runner is ready.

## Fallback behavior

If the preferred runner is unavailable, Mission Control should:

1. report the reason clearly
2. recommend a safe next runner
3. fall back to `dry_run` only when execution confidence would otherwise be misleading

## Related pages

Read [Provider Autowiring](Provider-Autowiring), [Webwright and Browser Automation](Webwright-and-Browser-Automation), [Troubleshooting CLI Runners](Troubleshooting-CLI-Runners), [Dry Run Mode](Dry-Run-Mode), and [Diagnostics and Health Checks](Diagnostics-and-Health-Checks).
