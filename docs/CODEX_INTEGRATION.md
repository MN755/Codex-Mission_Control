# Codex Integration

This MVP is designed to preserve the user's local Codex environment instead of rebuilding authentication, tools, or plugin access.

## Desktop Shell

- The primary user-facing surface is now a local desktop shell.
- The desktop app starts the same FastAPI backend in-process and serves the built React UI locally.
- The desktop shell does not switch authentication models. Manager and worker runs still rely on the local Codex CLI or experimental app-server path.
- Frozen desktop builds keep the same Codex integration model. Packaging changes the shell, not the authentication path.

## Authentication

- The backend checks `codex login status`.
- The intended path is `Logged in using ChatGPT`.
- The app never asks for OpenAI API keys and does not store them.
- The app does not edit `~/.codex/config.toml` unless you do that separately outside Mission Control.

## Runner Modes

### `dry_run`

- Simulates manager and worker behavior for the full UI flow.
- No Codex login required.

### `cli`

- Uses `codex exec --json` for first turns.
- Uses `codex exec resume` for follow-up turns when a session reference exists.
- Passes `--model` only when a per-project or per-role model override is set.
- Passes `-c model_reasoning_effort="..."` only when reasoning effort is set.
- Passes sandbox and approval policy per run rather than relying on global config edits.
- Captures stdout/stderr into local log files.
- Captures parsed event logs and exit codes for each run.
- Uses local auth and local config.

### `app_server`

- Uses `codex app-server` over stdio JSON-RPC.
- Performs `initialize` / `initialized`.
- Starts or resumes a thread, then starts a turn.
- Carries requested model and reasoning metadata where the protocol allows it.
- This path is experimental and intentionally narrow in the MVP.
- If a requested model or reasoning override cannot be honored safely in `auto`, the app prefers the CLI fallback path.

### `auto`

- Runs a handshake against `codex app-server`.
- If the handshake succeeds, uses the app-server runner.
- If the handshake fails, falls back to the CLI runner automatically.

## Manager Modes

### `auto`

- Uses the same local runner stack as workers when possible.
- Falls back to deterministic orchestration when the runner is unavailable or the returned JSON is malformed.

### `codex`

- Prefers Codex-backed structured manager actions.
- Still falls back deterministically instead of failing the whole workflow.

### `deterministic`

- Uses template-driven docs, planning, task decomposition, and routing.
- This is the default fallback path for `dry_run`.

## Local Detection

The system status endpoint reports:

- Codex CLI version
- Login status and auth mode
- App-server support
- Launcher-aware backend and frontend ports
- Current per-project settings summary when a project id is provided
- Configured MCP servers
- Configured plugins discovered in `~/.codex/config.toml`
- Installed local skills discovered in `~/.codex/skills`

## Connectors, Plugins, Skills, and MCP

- The app does not implement fake connectors.
- It depends on whatever the local Codex environment already exposes.
- The worker runners use the local Codex CLI or app-server so they can inherit available tools and configuration where the local environment supports it.

## Practical Limits

- The MVP does not guarantee full parity between CLI and app-server behavior.
- The app-server protocol may change over time.
- Some local Codex features can be detected and documented but not deeply orchestrated in v1.
- The manager only trusts structured JSON responses after a direct parse or one repair pass, otherwise it falls back to deterministic behavior.
- Model availability depends on the current Codex plan or ChatGPT-backed local session.
- Native desktop behavior still depends on a working local embedded webview backend on the host OS.
- Packaged builds do not modify `~/.codex/config.toml`; per-run flags remain the preferred override path.
- App-server model-selection behavior in packaged builds is still experimental for the same reasons it is experimental in source mode.
