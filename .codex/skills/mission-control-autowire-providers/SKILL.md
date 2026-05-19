---
name: mission-control-autowire-providers
description: Use when Codex should detect and safely autowire local Mission Control runners without enabling unsafe billing paths by default.
---

# Mission Control Autowire Providers

Use this skill when Mission Control needs a headless runner inventory and safe default runner configuration.

## Bridge boundary

- The Codex chat agent is not the Mission Control Manager.
- Codex chat inspects and configures the bridge-facing runner layer.
- Mission Control Manager uses the configured runners later; it does not decide installation.

## When to use

- The user wants Mission Control wired to the current machine.
- The user asks which runners are usable right now.
- The user wants a safe headless config generated.

## Tool and script sequence

1. Probe the machine with the backend bootstrap modules under `apps/server/src/bootstrap/`.
2. Generate or refresh the headless config through `/api/headless/autowire` or `scripts/mission-control-bootstrap.py`.
3. Report `dry_run`, `codex_cli`, `ollama`, `claude_cli`, and API-backed status honestly.
4. Keep API-backed runners disabled unless secure external config already exists and the user wants that billing path.

## What to report to the user

- Ready runners.
- Missing login steps.
- Ollama server state and local model visibility when safe.
- Whether only dry-run is available.
- The next Codex prompt the user can try immediately.

## Safety constraints

- Never store raw API keys.
- Never require UI interaction.
- Never force API billing.
- Never pretend Claude CLI or Codex CLI is authenticated if detection is inconclusive.
