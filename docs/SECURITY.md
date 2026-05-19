# Security

Mission Control is designed to be local-first, explicit about trust boundaries, and conservative by default.

See also:

- [Security Model](./SECURITY_MODEL.md)
- [Approval Policy](./APPROVAL_POLICY.md)

## Default posture

- backend bound to loopback by default
- local SQLite state
- local runtime folders
- local provider CLIs or endpoints
- no required cloud control plane

## Startup and diagnostics

Startup checks are split into:

- required checks that must pass for normal startup
- optional checks that can fail without blocking the dashboard

If required checks fail repeatedly, Mission Control writes a diagnostic report to the local diagnostics folder. Reports are meant to help with local recovery, not to export secrets.

Diagnostics do not intentionally include:

- raw API keys
- auth tokens
- cookie values
- full environment dumps with sensitive names

The same rule now applies to chat-native bridge output:

- status summaries
- approval requests
- manager questions
- event digests
- handoff summaries
- diagnostic summaries

Bridge messages are redacted at the final formatter envelope before they are returned from the API.

## Authentication model

### Codex

Recommended path:

- local Codex CLI with ChatGPT-backed sign-in

Fallbacks:

- device-code login
- optional API-key login

Mission Control does not require an API key for the Codex login path and does not store raw API keys in its own SQLite database.

### Other providers

- Claude Code auth is managed outside Mission Control
- Ollama is treated as a local endpoint, not a hosted secret flow
- API-based providers are explicitly marked as API-key-based
- custom adapters are trusted only to the extent the adapter command is trusted

## Provider configuration

Mission Control prefers per-run overrides instead of mutating global provider config.

- empty model fields mean `use provider default`
- empty reasoning-effort fields mean `use provider default`
- the app does not rewrite global Codex config by default

## Workspace safety

Mission Control does not assume workers can safely edit the same files.

- path reservations are recorded for active work
- conflicting tasks move to `waiting_on_paths`
- write-capable work is coordinated instead of allowed to overlap silently

This is a safety measure, not a perfect sandbox.

## Project-scoped decisions

Workspace questions, approvals, messages, and queue items are project-scoped.

That means:

- the canonical workspace route uses `projectId` as the source of truth
- slug mismatches redirect instead of silently loading a different project
- approval decisions are submitted with the current project context
- command and tool approvals are logged as explicit user decisions

Mission Control does not auto-approve high-risk actions and does not auto-decide high-impact manager questions.

Security policy is now explicit and persisted:

- global and project-scoped approval defaults are stored as `SecurityPolicy`
- requested actions are normalized into deterministic `RiskAssessment` records
- approval outcomes are persisted in `ApprovalAuditLog`
- secrets are redacted before those records are shown or stored

## Tool permissions

The `Skills & Tools` page exposes a local catalog with explicit permission policy.

Important behavior:

- unsupported environments are marked honestly instead of faked
- higher-risk tools default to ask-first policies
- permission overrides are stored locally, not inferred from vague usage history
- tool access policy is separate from provider authentication state

## Sandbox and approval defaults

Intended defaults:

- sandbox: `workspace-write`
- approval: `on-request`

Mission Control should surface when a task needs broader access instead of bypassing those defaults behind the user's back.

What it will not auto-approve:

- destructive deletes
- writes outside the workspace
- direct credential access
- deployment actions denied by policy
- high-risk actions requiring explicit user approval

## Headless bridge safety

Headless plugin mode is localhost-first and token-guarded.

- bridge-only endpoints require the local daemon token
- `/api/health` stays open for safe local health probing
- chat-native summaries never expose daemon tokens, provider keys, or raw logs by default
- approval payloads are structured for user review, not for direct shell execution from the bridge

## Widget boundary security

Mission Control now uses widgets heavily, but widgets are intentionally summary surfaces rather than secret tunnels into execution.

Rules:

- widgets summarize state
- Manager Chat owns approvals, questions, and recovery decisions
- built-in tools remain in `Skills & Tools`
- widgets do not execute web search, browser tests, deployments, or similar tools directly

That boundary matters because blending summaries, approvals, and execution into the same card is how apps accidentally become permission-confusion generators.

## Widget data safety

Widget data is scoped and persisted:

- dashboard widgets are global summaries
- project widgets are scoped to a single project ID
- widget instances store placement, size, order, and config
- widget data responses store summary data, warnings, and honest empty states

Widget APIs should not leak one project's decision history, path ownership, recovery state, or assumptions into another project's view.

## Repo intelligence safety

The `Repo Intelligence` widget uses a lightweight filesystem scan only.

Important guardrail:

- it reads files and metadata
- it does not execute build commands, test commands, package scripts, or other untrusted repo commands

That keeps repo indexing useful without turning “show me the framework” into “surprise, we ran whatever nonsense was hiding in `package.json`.”

## Path ownership and coordination safety

Mission Control now exposes both low-level path reservations and higher-level `PathLock` ownership data.

Safety intent:

- multiple agents should not silently edit the same writable area
- ownership conflicts should be visible before they become merge sludge
- widgets can show waiting locks and conflicts without granting edit access

This still is not a perfect sandbox. It is a coordination layer that reduces easy mistakes and makes conflicts explicit.

## Runtime storage

Source runs store runtime data under `apps/server/.runtime`.

That can include:

- SQLite database
- launcher metadata
- run logs
- diagnostics
- event logs

Packaged builds use a writable local app-data directory chosen by the desktop shell.

## Event streams

Mission Control now emits both project-scoped and app-scoped live events:

- `ProjectEvent` for workspace updates
- `AppEvent` for global dashboard and widget refresh

Security posture:

- streams are local-first and intended for loopback use
- event payloads carry summary data and invalidation hints
- widgets should refresh targeted data instead of reloading large payloads by default

## Reset behavior

Mission Control does not automatically reset first-run setup or runtime state after code updates or version changes.

Intentional setup reset is a manual development operation unless a dedicated admin or reset tool is added later. Back up runtime data before changing the app-state record.

## Network exposure

Mission Control is not intended to be exposed publicly without additional controls.

- keep the backend on localhost
- treat non-loopback binding as a deliberate higher-risk configuration
- do not assume experimental provider surfaces are hardened for public exposure

## Known limits

- Codex app-server support is experimental
- custom adapters may widen the trust boundary
- connected-account cards in setup are placeholders unless you configure real integrations
- unsigned desktop binaries may trigger OS trust warnings until you add signing or notarization
- approval payloads are redacted by default, so the workspace is optimized for safe summaries rather than full raw execution detail
- tool availability may vary by OS, installed local runtimes, and external setup outside Mission Control
