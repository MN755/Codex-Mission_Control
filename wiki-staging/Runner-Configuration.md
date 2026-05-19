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
- `custom_api`

## Detection and user action

Detection guidance:

- `dry_run`: always available and safe fallback
- `codex_cli`: detect local CLI and login state; preferred when available
- `ollama`: detect installed service and available local models
- `claude_cli`: detect installed CLI and configuration
- `*_api`: detect only configured secure provider settings, never raw chat-pasted keys
- `custom_api`: only available when explicitly configured

## Billing and security notes

Notes:

- Codex CLI via ChatGPT/Codex login should be preferred where available.
- API providers may incur billing and require explicit configuration.
- Ollama is local but still requires installed models and local compute budget.
- Dry-run is the safe fallback when no runner is ready.

## Fallback behavior

If the preferred runner is unavailable, Mission Control should:

1. report the reason clearly
2. recommend a safe next runner
3. fall back to `dry_run` only when execution confidence would otherwise be misleading

## Related pages

Read [Provider Autowiring](Provider-Autowiring), [Troubleshooting CLI Runners](Troubleshooting-CLI-Runners), [Dry Run Mode](Dry-Run-Mode), and [Diagnostics and Health Checks](Diagnostics-and-Health-Checks).
