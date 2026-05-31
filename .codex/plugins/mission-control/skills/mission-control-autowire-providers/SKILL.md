---
name: mission-control-autowire-providers
description: Probe and safely autowire local Mission Control runners for headless Codex use.
---

# Mission Control Autowire Providers

## Purpose

Build an honest runner inventory and generate a safe headless configuration without enabling unsafe billing paths by default.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants Mission Control wired to the current machine.
- The user asks which runners are usable right now.
- The daemon is installed, but runner configuration needs a safe default pass.

## Workflow

1. Probe `dry_run`, `codex_cli`, `ollama`, `claude_cli`, and API-backed runners.
2. Generate or refresh headless config through `/api/headless/autowire` or `scripts/mission-control-bootstrap.py`.
3. Enable only runners that are safely configured already.
4. Keep API-backed paths opt-in and billing-aware.

## Mission Control calls

Modules:
- `apps/server/src/bootstrap/environment_probe.py`
- `apps/server/src/bootstrap/runner_probe.py`
- `apps/server/src/bootstrap/runner_autowire.py`

Endpoints:
- `POST /api/headless/autowire`
- `GET /api/headless/config`
- `GET /api/runners/status`

## User-facing output

- Show ready runners and safe defaults.
- Show missing login or runtime steps.
- Show billing warnings for API-backed runners.
- Provide the next Codex prompt the user can try immediately.

## Approval behavior

- Do not enable new paid API paths implicitly.
- Do not pull Ollama models automatically.
- Do not ask for secrets that are not actually required for the currently safe path.

## Never do

- Do not require UI interaction.
- Do not store raw API keys.
- Do not claim Claude CLI or Codex CLI is authenticated when detection is inconclusive.

Never require UI interaction.

## Failure and fallback

- If no live runner is ready, keep `dry_run` enabled and say that setup is degraded but usable.
- If a runner is installed but not logged in or not running, show the exact recommended fix instead of vague advice.
- If only external env config exists, keep the report redacted and billing-aware.

## Example invocation

`Autowire Mission Control providers and tell me which runners are actually usable.`
