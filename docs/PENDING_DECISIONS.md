# Pending Decisions

Pending decisions are the single relay format for approvals and high-impact questions in Codex bridge mode.

## Supported decision types

- `command_approval`
- `tool_approval`
- `write_permission`
- `manager_question`
- `swarm_approval`
- `snapshot_approval`
- `handoff_review`
- `recovery_decision`
- `scope_change_decision`
- `safe_mode_confirmation`

## Endpoints

- `GET /api/orchestrations/{orchestration_id}/pending-decisions`
- `GET /api/projects/{project_id}/pending-decisions`
- `GET /api/decisions/{decision_id}/bridge-message`
- `POST /api/decisions/{decision_id}/answer`

## Response shape

Each pending decision includes:

- identity and project or orchestration linkage
- decision type
- title and message
- risk level
- allowed options
- recommended option when available
- optional presentation payload for future custom UI

## Answer behavior

`POST /api/decisions/{decision_id}/answer`:

- validates the selected option
- stores the answer payload
- updates the decision status
- writes an audit record when appropriate
- returns the answered decision plus the next compact status summary

Invalid answers are rejected instead of being guessed. Radical concept.

## Presentation payloads

Current bridge payload families:

- command approval
- tool approval
- manager question
- swarm approval
- write permission request
- handoff review
- recovery decision

Every payload is designed to work two ways:

- structured JSON for future Codex card rendering
- fallback Markdown for plain chat

## Security

- secret-looking values are redacted before they reach the bridge
- command details are summarized, not dumped as raw logs
- dangerous actions remain pending until the user answers
