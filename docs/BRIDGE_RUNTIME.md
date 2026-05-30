# Bridge Runtime

Mission Control's Codex bridge runtime is the headless layer that turns orchestration state into compact, redacted chat output.

This layer is intentionally not the standalone app UI. No dashboard pages, widgets, or React surfaces are required for it to work.

## Core models

`BridgeMessage`

- structured machine payload for MCP or plugin consumers
- fallback Markdown for plain Codex chat
- explicit `user_action_required`
- explicit `redaction_status`

`PendingDecision`

- normalized approval and question relay record
- one answer surface for commands, tools, manager questions, recovery choices, and handoff review

## What it formats

- compact status summaries
- compact event digests
- approval requests
- manager questions
- safe mode updates
- handoff summaries
- diagnostics summaries

## Main endpoints

- `GET /api/projects/{project_id}/orchestrations/{orchestration_id}/status-summary`
- `GET /api/projects/{project_id}/status-summary`
- `GET /api/projects/{project_id}/orchestrations/{orchestration_id}/event-digest`
- `GET /api/projects/{project_id}/event-digest`
- `GET /api/projects/{project_id}/orchestrations/{orchestration_id}/handoff-summary`
- `GET /api/projects/{project_id}/handoff-summary`
- `GET /api/orchestrations/{orchestration_id}/pending-decisions`
- `GET /api/projects/{project_id}/pending-decisions`
- `GET /api/decisions/{decision_id}/bridge-message`
- `POST /api/decisions/{decision_id}/answer`
- `GET /api/plugin/health`
- `POST /api/plugin/health/check`
- `GET /api/projects/{project_id}/safe-mode`
- `POST /api/projects/{project_id}/safe-mode`
- `POST /api/mission-control/resume-workspace`

## Service functions

These are kept clean so an MCP layer can call them directly:

- `get_status_summary`
- `get_event_digest`
- `get_pending_decisions`
- `answer_decision`
- `get_handoff_summary`
- `plugin_health`
- `enable_safe_mode`
- `resume_workspace`

## Safety rules

- no raw logs in default bridge output
- no secrets in summaries, digests, diagnostics, handoffs, or approvals
- high-risk actions stay approval-gated
- dashboard availability is optional in bridge mode

## Resume behavior

`POST /api/mission-control/resume-workspace` accepts a workspace path and returns:

- active orchestration summary when one exists
- pending decisions, if any
- a useful "nothing active" response when the workspace is known but idle
- a clean not-found response when Mission Control has never seen the workspace
