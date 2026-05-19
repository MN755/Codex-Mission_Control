# Pending Decisions

Pending decisions are the single relay format for approvals and high-impact questions in Codex bridge mode.

## Supported decision types

- `command_approval`
- `tool_approval`
- `write_permission`
- `manager_question`
- `swarm_approval`
- `subagent_burst_approval`
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

Attach ambiguity also uses the same relay model. If Mission Control finds multiple projects for one workspace, it raises a pending decision instead of guessing and making a mess.

## Response shape

Each pending decision includes:

- `id`
- `project_id`
- `orchestration_id`
- `decision_type`
- `title`
- `message`
- `requesting_agent_id`
- `related_task_id`
- `risk_level`
- `options_json`
- `recommended_option`
- `status`
- `presentation_json`
- `created_at`
- `answered_at`
- `answer_json`

## Answer behavior

`POST /api/decisions/{decision_id}/answer`:

- validates the selected option
- stores the answer payload
- updates the decision status
- writes an audit record when appropriate
- returns the answered decision plus the next compact status summary

That next summary now also works for attach-workspace decisions instead of shrugging and returning `null`, which was not exactly a shining example of bridge ergonomics.

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

Bridge messages are available at `GET /api/decisions/{decision_id}/bridge-message` so Codex chat can render the decision without acting like the manager.

## Security

- secret-looking values are redacted before they reach the bridge
- command details are summarized, not dumped as raw logs
- dangerous actions remain pending until the user answers
