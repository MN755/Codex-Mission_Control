# Provider Integration

This MVP is designed to preserve the user's local provider environment instead of rebuilding authentication, tools, or plugin access from scratch.

## Desktop Shell

- The primary user-facing surface is now a local desktop shell.
- The desktop app starts the same FastAPI backend in-process and serves the built React UI locally.
- The desktop shell does not switch authentication models. Manager and worker runs still rely on the selected local provider CLI.
- Frozen desktop builds keep the same local-provider integration model. Packaging changes the shell, not the authentication path.

## Authentication

- The desktop app launches into a local authentication choice screen for `Codex`.
- The recommended Codex path is `Sign in with ChatGPT`, which runs the local `codex login` flow.
- A `Use device code` fallback is available when browser-based login is inconvenient.
- An optional API-key path runs `codex login --with-api-key`.
- Mission Control does not persist the raw API key in its own database or settings.
- The backend checks `codex login status`.
- `Claude Code` keeps its own login flow outside Mission Control.
- `external_adapter` uses whatever authentication the user-supplied adapter command already implements.
- The app does not edit `~/.codex/config.toml` unless you do that separately outside Mission Control.

## Runner Modes

### `dry_run`

- Simulates manager and worker behavior for the full UI flow.
- No live provider login required.

### `cli`

- `Codex` uses `codex exec --json` for first turns and `codex exec resume` for follow-up turns when a session reference exists.
- `Claude Code` uses non-interactive CLI runs and per-run `--model` overrides when configured.
- `external_adapter` runs a user-supplied local command and passes Mission Control context over stdin plus environment variables.
- Model overrides are passed only when configured.
- Reasoning effort is passed directly to Codex, forwarded to external adapters, and currently ignored for Claude Code.
- Sandbox and approval policy stay per-run rather than relying on global config edits.
- Stdout, stderr, parsed event logs, and exit codes are captured locally.

### `app_server`

- Uses `codex app-server` over stdio JSON-RPC.
- Performs `initialize` / `initialized`.
- Starts or resumes a thread, then starts a turn.
- Carries requested model and reasoning metadata where the protocol allows it.
- This path is `Codex`-only, experimental, and intentionally narrow in the MVP.
- If a requested model or reasoning override cannot be honored safely in `auto`, the app prefers the Codex CLI fallback path.

### `auto`

- `Codex`: runs a handshake against `codex app-server`, prefers app-server when it succeeds, and falls back to the CLI runner automatically.
- `Claude Code`: resolves to the CLI runner.
- `external_adapter`: resolves to the adapter runner.

## Manager Modes

### `auto`

- Uses the same local runner stack as workers when possible.
- Falls back to deterministic orchestration when the runner is unavailable or the returned JSON is malformed.

### `provider`

- Prefers live provider-backed structured manager actions.
- Still falls back deterministically instead of failing the whole workflow.

### `deterministic`

- Uses template-driven docs, planning, task decomposition, and routing.
- This is the default fallback path for `dry_run`.

## Local Detection

The system status endpoint reports:

- Provider selection and provider capability matrix
- Codex CLI version
- Codex login status and auth mode when detectable
- The latest local auth job state from the desktop launchpad
- App-server support for Codex
- Launcher-aware backend and frontend ports
- Current per-project settings summary when a project id is provided
- Configured MCP servers
- Configured plugins discovered in `~/.codex/config.toml`
- Installed local skills discovered in `~/.codex/skills`

## Connectors, Plugins, Skills, and MCP

- The app does not implement fake connectors.
- Codex projects depend on whatever the local Codex environment already exposes.
- Claude Code and external-adapter projects inherit only what those local CLIs or wrappers expose.

## Practical Limits

- The MVP does not guarantee full parity between providers.
- The app-server protocol may change over time.
- Some local provider features can be detected and documented but not deeply orchestrated in v1.
- The manager only trusts structured JSON responses after a direct parse or one repair pass, otherwise it falls back to deterministic behavior.
- Model availability depends on the current provider, plan, and local session.
- Native desktop behavior still depends on a working local embedded webview backend on the host OS.
- Packaged builds do not modify `~/.codex/config.toml`; per-run flags remain the preferred override path.
- Codex app-server model-selection behavior in packaged builds is still experimental for the same reasons it is experimental in source mode.
