# MCP Security

Mission Control’s MCP bridge is intentionally boring from a security perspective. Good. Security theater is for people who like incident writeups.

## Localhost-only boundary

- the daemon binds to `127.0.0.1` by default
- the MCP bridge talks to the daemon over localhost only
- the bridge is not intended for LAN exposure
- the dashboard and browser-facing routes remain separate from bridge-only endpoints

## Shared local token

Bridge-only endpoints require `X-Mission-Control-Token`.

Token behavior:

- the daemon creates the token on startup if it does not already exist
- the token is stored in local runtime state for the same machine user
- the MCP bridge reads that token and sends it on protected requests
- `/api/health` remains unauthenticated so the bridge can probe daemon readiness

The token is never returned in:

- normal API payloads
- MCP resources
- handoff content
- widget summaries
- frontend pages

## Protected bridge actions

Protected endpoints include orchestration attach, orchestration start or resume control, pending-decision reads, decision answers, and daemon status.

These calls expose orchestration state or can change it, so pretending they should be public just because localhost exists would be deeply unserious.

## Secret handling

The MCP bridge and daemon should not expose:

- raw API keys
- auth tokens
- secret headers
- environment variable dumps
- raw logs by default
- full command payloads when those contain secret arguments

Safe summary resources expose:

- status
- counts
- decision titles
- risk labels
- handoff summaries
- codebase structure summaries

If a deeper inspection path is added later, it should stay opt-in and still redact secrets.

## Command execution boundary

The MCP bridge does not run shell commands directly.

All actual execution remains inside Mission Control through:

- runner selection
- approval policy
- sandbox policy
- project-scoped decisions

That keeps Codex chat from becoming an accidental remote shell with a nicer font.

## Approval model

High-risk actions still require explicit user approval. The bridge can surface a structured presentation payload for a Codex-style approval card, but text fallback is always supported.

Decision records should capture:

- what was requested
- why it was requested
- the risk level
- the chosen option
- when the user answered

## Operational notes

- if the configured port is occupied and health checks fail, the bridge reports the problem instead of killing the mystery process
- if the daemon restarts, in-flight orchestration sessions are reconciled to `paused`
- if a decision is still pending, orchestration status reports `waiting_for_user` rather than hallucinating progress
