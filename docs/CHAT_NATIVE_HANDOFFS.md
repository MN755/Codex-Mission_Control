# Chat-Native Handoffs

Mission Control handoffs in Codex bridge mode are formatted for chat first, not for a dashboard panel.

## Required sections

- status
- confidence and evidence level
- what changed
- how to run
- validation and evidence
- known limitations
- next recommended tasks
- important files or artifacts

## Rules

- do not claim tests passed without evidence
- if validation was not run, say `Validation not run.`
- if the run was dry-run, mark it clearly
- keep the message short enough for Codex chat scanning
- redact secrets and avoid raw logs

## Endpoints

- `GET /api/orchestrations/{orchestration_id}/handoff-summary`
- `GET /api/projects/{project_id}/handoff-summary`

## Fallback behavior

When no evidence-based handoff record exists yet, the bridge still returns a useful summary:

- current handoff status
- available run instructions if any
- explicit lack of validation evidence
- known artifact paths when available

## Why this exists

Codex chat is the relay surface. The user should be able to understand what changed, what was validated, and what still needs review without opening another UI just to decode the handoff.
