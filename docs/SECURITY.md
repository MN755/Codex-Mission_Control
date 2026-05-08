# Security

Mission Control is intended to be local-first and least-surprising by default. This document covers the main trust boundaries and operating assumptions for the MVP.

## Default posture

- Runs locally by default
- Binds the backend to loopback addresses
- Uses local provider CLIs instead of a separate hosted auth layer
- Avoids dangerous bypass flags by default
- Stores orchestration state locally

## Authentication

### Codex

- Preferred path: ChatGPT-backed local sign-in
- Device-code sign-in is available as a fallback
- API-key login is optional

Mission Control does not store raw API keys in its own database. If an API-key login path is used, it is passed to the local Codex login flow rather than retained as an application secret.

### Other providers

- Claude Code auth is managed by the local Claude environment
- External adapter auth is managed by the adapter or wrapper command

## Network exposure

Mission Control is not designed to be exposed publicly.

- Keep the backend on localhost
- Treat any non-loopback binding as a deliberate, higher-risk configuration
- Do not expose experimental provider surfaces without additional controls

## Workspace safety

Mission Control tries to reduce agent collisions rather than pretending they do not happen.

- Git-backed work can be isolated through worktree-oriented flows
- Non-git workspaces use path reservations
- Conflicting tasks are held in `waiting_on_paths`
- Generated docs stay inside the selected workspace

## Runner safety defaults

The intended defaults are:

- sandbox: `workspace-write`
- approval: `on-request`

Mission Control does not silently escalate around those defaults. If a task needs more access, the intended behavior is to surface that need instead of bypassing guardrails behind the user’s back.

## Provider configuration

Mission Control prefers per-run overrides to global mutation.

- Empty model fields mean `use provider default`
- Empty reasoning fields mean `use provider default`
- Project settings are scoped to Mission Control
- The app does not rewrite global Codex config by default

## Logging and local data

Mission Control stores local runtime data such as:

- SQLite state
- launcher metadata
- run logs
- stdout and stderr captures
- event logs

Source runs use `apps/server/.runtime`. Packaged builds use a writable local app-data directory.

## Desktop packaging considerations

- Packaged builds are unsigned unless platform signing is added separately
- Unsigned binaries may trigger operating-system trust warnings
- Linux AppImage generation depends on system-compatible tooling

## Known security limits

- Codex app-server support is experimental
- External adapters can widen the trust boundary depending on how they are implemented
- Provider model availability and behavior depend on the current local account and session
- The MVP does not attempt enterprise policy enforcement or centralized secrets management

## Recommended operating practice

- Use ChatGPT-backed Codex sign-in when you want to stay off API billing
- Use dry-run mode for UI demos and workflow validation
- Review any external adapter wrapper before trusting it on sensitive code
- Keep the selected workspace narrow and intentional
- Treat packaged binaries as local-distribution artifacts unless you add signing and notarization
