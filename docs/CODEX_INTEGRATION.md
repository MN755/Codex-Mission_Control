# Provider Integration

Mission Control is built to sit on top of local agent tooling instead of replacing it. The app decides what work should happen; the runner layer decides how to execute that work against a provider.

## Provider identities

Mission Control currently recognizes:

- `codex`
- `ollama`
- `openai_api`
- `anthropic_api`
- `xai_api`
- `claude_code`
- `custom`

Legacy provider labels are normalized into these identifiers during load and migration.

## Codex

Codex is the most complete live provider path today.

Supported behaviors:

- local CLI detection
- ChatGPT-backed login detection
- device-code login support
- optional API-key login handoff
- per-run model overrides
- per-run reasoning-effort overrides
- per-run sandbox and approval overrides
- experimental app-server detection

Mission Control does not require OpenAI API keys for the preferred Codex login path.

## Codex plugin bridge mode

Mission Control can also be exposed inside the Codex desktop app through a plugin plus MCP bridge model.

In that mode:

- Codex chat is the user-facing bridge
- Mission Control Manager remains the orchestration authority
- approvals and manager questions are relayed through Codex chat
- the plugin package carries skills, prompts, and MCP wiring guidance rather than pretending to replace Mission Control's backend

Current bridge tool set:

- `mission_control_attach_workspace`
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_answer_decision`
- `mission_control_pause`
- `mission_control_resume`
- `mission_control_get_handoff`
- `mission_control_open_dashboard`

Current safe resources:

- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://orchestrations/{orchestration_id}/status`

Bridge behavior:

- attach the workspace first
- reuse the active orchestration for that workspace when one already exists
- poll compact status instead of pretending streaming is guaranteed
- relay every approval and manager question back to the user
- send the user’s selected option back through `mission_control_answer_decision`
- fetch the evidence-backed handoff only when Mission Control reports readiness

Installation and packaging guidance lives in [docs/CODEX_PLUGIN_INSTALL.md](CODEX_PLUGIN_INSTALL.md). Bridge behavior and security are documented in [docs/CODEX_PLUGIN_MODE.md](CODEX_PLUGIN_MODE.md) and [docs/MCP_SECURITY.md](MCP_SECURITY.md).

Headless bridge runtime docs:

- [Bridge Runtime](BRIDGE_RUNTIME.md)
- [Pending Decisions](PENDING_DECISIONS.md)
- [Plugin Health Doctor](PLUGIN_HEALTH_DOCTOR.md)
- [Chat-Native Handoffs](CHAT_NATIVE_HANDOFFS.md)

## Codex login vs API billing

Preferred non-API-key flow:

- sign in through the local Codex CLI using the ChatGPT-backed login flow

Why that matters:

- it preserves the user's existing Codex or ChatGPT session where supported
- it avoids forcing Mission Control onto API-key-based billing

Optional API-key login exists for users who intentionally want that path, but Mission Control does not store the raw key in its own database.

## Workspace behavior with Codex

When Codex is the selected provider, the project workspace still keeps one user-facing conversation:

- the user talks only to the Manager AI
- manager replies are stored as durable workspace messages
- command and tool approvals are surfaced inline inside the manager workspace
- worker activity remains visible in sidebars instead of opening separate user chats

In dry-run mode, the same workspace loop is exercised with clearly marked simulated messages, questions, approvals, and agent status changes. Mission Control does not claim real Codex execution happened in that mode.

Codex-specific runtime controls are edited from the project-scoped `Models & Runners` page rather than from a global settings screen.

## Widgets, Manager Chat, and tools

Codex integration now lives inside a stricter UI boundary instead of leaking controls everywhere.

Rules:

- `Manager Chat` remains the place where the user approves commands, answers manager questions, and handles recovery or strategy prompts
- dashboard and project widgets summarize provider, model, sandbox, tool-routing, and health state
- widgets do not execute Codex tools directly
- built-in tool configuration remains in `Skills & Tools`

Examples:

- `Runner & Provider Status` summarizes Codex CLI/login posture
- `Model Assignment Policy` summarizes role-to-model routing
- `Tool Routing Policy` summarizes which archetypes can use which tools
- `Sandbox Profiles` summarizes command and deployment restrictions

This keeps the manager loop coherent instead of forcing users to guess whether a decision belongs in chat, in settings, or in some random card with a refresh icon.

## Claude Code

Claude Code is supported through a CLI-style runner.

- authentication is handled by the local Claude environment
- Mission Control does not fake a Claude auth flow
- capability depth depends on the local CLI's non-interactive support

## Ollama

Ollama is treated as a local-first provider option.

- setup collects a local endpoint such as `http://localhost:11434`
- startup can check endpoint reachability
- degraded mode is allowed when Ollama is selected but not reachable

## API-based providers

The setup wizard can represent:

- `openai_api`
- `anthropic_api`
- `xai_api`

These are clearly labeled as API-key-based providers.

Current security posture:

- Mission Control does not store raw API keys in SQLite
- if secure storage is not available, the app stores only non-secret metadata and leaves the provider in a degraded or externally configured state

## Custom provider

`custom` is the generic adapter path.

- the adapter command is user-supplied
- prompts are passed through stdin
- run settings can be passed through environment variables
- trust depends on the adapter wrapper the user installs

## Runner modes

- `dry_run`: local simulation, no live provider required
- `cli`: main production path for provider CLIs
- `app_server`: experimental Codex-only path
- `auto`: choose the best supported path and fall back safely

Per-run overrides still take precedence over the local Codex defaults for that run only. Mission Control does not rewrite the global Codex config by default.

## Adaptive swarm execution with Codex

Codex is now used inside adaptive swarm planning instead of a fixed worker roster.

Important behavior:

- the Manager chooses the largest useful swarm, not the largest possible swarm
- multiple agents of the same archetype are allowed only when missions and writable areas are meaningfully separated
- `Swarm Budget` and `Swarm Strategy` widgets summarize intensity, approval thresholds, and scale posture
- `Agent Contracts` and `Path Ownership Map` expose mission boundaries and path safety before workers collide
- dry-run mode can simulate these swarm decisions honestly without pretending real Codex-backed agents were launched

## Model and reasoning settings

Mission Control supports:

- manager model
- default worker model
- role-based worker overrides
- manager reasoning effort
- default worker reasoning effort

Resolution order for worker runs:

1. role override
2. project default
3. provider default

Empty values mean the app should not force an override.

These settings are intentionally project-scoped:

- the top-level `Models & Runners` navigation entry redirects into the most relevant project context
- old project settings routes should redirect to the canonical models page
- the app does not treat model choice as a single global switch for all projects

## Startup integration

Startup checks are provider-aware.

Examples:

- Codex: CLI, login state, app-server availability
- Claude Code: CLI presence and auth detectability if available
- Ollama: local endpoint reachability
- API providers: external credential or environment readiness
- custom: adapter command presence

Provider failures are usually optional and therefore produce degraded mode instead of a hard startup stop.

The `Diagnostics` and `Dashboard` pages surface this provider state without forcing users into raw CLI output or raw provider logs.

## Live update model

Codex-backed project state now refreshes through scoped event streams:

- project SSE updates the workspace and project widgets
- app-level SSE updates dashboard widgets

The goal is targeted refresh, not brute-force reloading the whole shell because a single approval changed.

## Known limits

- Codex app-server remains experimental
- provider feature parity is not guaranteed
- model availability depends on the user's active local account, endpoint, or session
- custom adapters are only as reliable as the wrapper command behind them
