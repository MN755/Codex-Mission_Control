# Autowire Providers

Mission Control headless mode probes local runners and enables only the safe defaults.

## Safe default behavior

- `dry_run`: always enabled
- `codex_cli`: enabled only when the CLI exists and login looks valid
- `ollama`: enabled only when the local server is reachable
- `claude_cli`: detected, but not auto-enabled if auth cannot be confirmed
- `openai_api`, `anthropic_api`, `xai_api`, `custom_api`: detected only from external config and not auto-enabled by default

## Why API runners stay conservative

- Mission Control does not store raw keys in SQLite, logs, or JSON reports.
- External env configuration can be detected without printing the secret value.
- Billing-backed paths should be explicit, not accidental.

## Typical autowire outputs

- ready runners
- missing login steps
- recommended fixes
- billing warnings for API-backed paths
- next prompt the user can try in Codex chat

## Codex CLI login vs API key

Preferred:

- local Codex CLI with ChatGPT or Codex login

Fallback:

- API-backed providers only when the user already configured them externally and accepts billing
