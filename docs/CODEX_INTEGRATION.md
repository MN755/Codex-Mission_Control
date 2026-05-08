# Provider Integration

Mission Control is designed to sit on top of local agent tooling rather than replace it. It reuses provider CLIs, local sessions, and per-run overrides wherever possible.

## Supported providers

## Codex

- Best supported live provider path
- Works with local Codex CLI authentication
- Supports ChatGPT sign-in, device-code sign-in, and optional API-key login
- Supports per-run model overrides
- Supports per-run reasoning-effort overrides
- Supports CLI execution and experimental app-server execution

## Claude Code

- Supported through a CLI runner
- Authentication is managed by the local Claude Code environment
- Supports model overrides where the CLI supports them
- Mission Control does not assume reasoning-effort controls are available

## External adapter

- Generic local command runner for other LLMs
- Receives prompts through stdin
- Receives run settings through environment variables
- Capability depth depends on the adapter wrapper the user provides

## Authentication model

Mission Control prefers account/session reuse over custom credential handling.

### Codex

- Recommended: ChatGPT-backed local Codex sign-in
- Fallback: device-code flow
- Optional: API-key login

Mission Control does not:

- require API keys for the default Codex path
- store raw API keys in its own database
- rewrite `~/.codex/config.toml` by default

### Other providers

- Claude Code manages auth outside Mission Control
- External adapters manage auth outside Mission Control

## Runner modes

## `dry_run`

- No live provider required
- Simulates manager and worker behavior
- Useful for demos, UI work, and local testing

## `cli`

- Main production path today
- Uses provider-specific CLI invocation
- Captures stdout, stderr, exit codes, and event-like output
- Passes model, sandbox, and approval settings per run when supported

## `app_server`

- Codex-only
- Experimental
- Uses `codex app-server` over stdio JSON-RPC
- Narrowly scoped to the current MVP

## `auto`

- Selects the best supported live path for the chosen provider
- Falls back safely when a capability is unavailable

## Model and reasoning settings

Settings are stored per project.

- `manager_model`
- `default_worker_model`
- `manager_reasoning_effort`
- `default_worker_reasoning_effort`
- role-based worker overrides

Resolution order:

1. Role-specific override
2. Project default
3. Provider default

Empty values mean:

- do not force an override
- let the provider use its normal default behavior

## Manager integration

Mission Control supports two broad manager paths:

- provider-backed manager turns
- deterministic fallback

Provider-backed manager actions can be used for:

- docs generation
- interview generation
- plan synthesis
- task decomposition
- worker decisioning
- handoff generation

If a structured manager response cannot be parsed:

1. Mission Control attempts one repair pass
2. If parsing still fails, it logs the failure
3. The system falls back to deterministic behavior for that action

## Codex-specific notes

- Codex CLI is the most complete and tested live path
- ChatGPT sign-in is the recommended non-API-key experience
- API-key login is optional and may move usage onto API-billed credentials
- Codex app-server remains experimental and should not be treated as the only supported path

## Operational limits

- Provider capability parity is not guaranteed
- Available models depend on the user’s provider account and session
- Some CLIs expose richer non-interactive features than others
- External adapters are only as reliable as the wrapper command behind them
