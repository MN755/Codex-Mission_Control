# Architecture

Mission Control is currently headless-first.

The primary architecture is:

- Codex chat as the user-facing bridge
- a Mission Control daemon/backend that owns orchestration
- MCP tools, resources, prompts, and skills as the primary interface
- worker runners behind Mission Control control and approvals

The desktop shell and React dashboard remain optional and secondary. They are useful for observability, but they are not required for normal Mission Control use.

## Core topology

`Codex chat -> Mission Control skill or prompt -> MCP tools/resources/prompts -> Mission Control daemon -> Mission Control Manager -> worker runners`

Important boundaries:

- Codex chat is not the Manager
- the MCP server is a thin localhost client, not a planner
- the daemon owns orchestration state, pending decisions, and handoff state
- worker execution still goes through Mission Control approvals and runner policy

## Backend responsibilities

The backend lives in `apps/server`.

Primary responsibilities:

- startup coordination
- app-state persistence
- provider detection
- project orchestration
- manager and worker routing
- task and path reservation state
- diagnostics generation
- system-status reporting
- headless bootstrap, runner autowire, and install health

The same FastAPI app also serves daemon mode. The daemon binds to `127.0.0.1`, persists orchestration state, and exposes bridge-only endpoints for the MCP client.

## Bridge surfaces

Core bridge surfaces include:

- `/api/orchestrations/*`
- `/api/decisions/{decision_id}/answer`
- `/api/daemon/status`
- `/api/headless/health`
- `/api/headless/config`
- `/api/headless/autowire`
- `/api/headless/repair`
- `/api/runners/status`

Only `/api/health` remains intentionally unauthenticated for daemon probing. Bridge calls use the local shared token described in [MCP Security](MCP_SECURITY.md).

## Headless bootstrap layer

The headless bootstrap layer lives under `apps/server/src/bootstrap/`.

Its responsibilities are:

- environment probing
- dependency probing
- runner probing
- runner autowire
- headless config generation
- install report generation
- secret redaction for setup summaries

## Chat-native formatting layer

Mission Control has a dedicated formatting layer for Codex chat output.

Key modules:

- `apps/server/src/bridge_formatter.py`
- `apps/server/src/chat_markdown.py`
- `apps/server/src/event_digest_formatter.py`
- `apps/server/src/handoff_formatter.py`
- `apps/server/src/diagnostic_formatter.py`

That layer is responsible for:

- compact status summaries
- readable approval and question formatting
- evidence-based handoff formatting
- compact event digests
- diagnostic summaries
- final-envelope redaction before any bridge message leaves the backend

## Optional UI surfaces

The desktop shell in `apps/desktop` and the frontend in `apps/dashboard` remain optional support surfaces.

They may be used for observability, packaging, or operator workflows later, but they are not required for normal Mission Control use from Codex chat.

Dashboard routes, widget details, and workspace layout notes now live in [OPTIONAL_DASHBOARD_UI.md](OPTIONAL_DASHBOARD_UI.md) so this document stays aligned with the actual product direction.
