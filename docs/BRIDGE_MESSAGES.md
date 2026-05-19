# Bridge Messages

Mission Control uses `BridgeMessage` responses for chat-native output.

## BridgeMessage fields

- `id`
- `project_id`
- `orchestration_id`
- `source_type`
- `message_type`
- `title`
- `summary`
- `user_action_required`
- `risk_level`
- `options_json`
- `machine_payload_json`
- `fallback_markdown`
- `redaction_status`
- `created_at`

## Source types

- `manager`
- `system`
- `agent`
- `security`
- `diagnostics`
- `handoff`

## Message types

- `status_update`
- `approval_request`
- `manager_question`
- `warning`
- `blocked`
- `handoff_ready`
- `failed`
- `recovery_options`
- `swarm_update`
- `diagnostic_summary`
- `event_digest`
- `safe_mode_update`

## Formatter modules

Bridge chat output is built through these backend modules:

- [apps/server/src/bridge_formatter.py](</C:/Users/mike/OneDrive/Desktop/Codex Mission Control/apps/server/src/bridge_formatter.py>)
- [apps/server/src/chat_markdown.py](</C:/Users/mike/OneDrive/Desktop/Codex Mission Control/apps/server/src/chat_markdown.py>)
- [apps/server/src/handoff_formatter.py](</C:/Users/mike/OneDrive/Desktop/Codex Mission Control/apps/server/src/handoff_formatter.py>)
- [apps/server/src/event_digest_formatter.py](</C:/Users/mike/OneDrive/Desktop/Codex Mission Control/apps/server/src/event_digest_formatter.py>)
- [apps/server/src/diagnostic_formatter.py](</C:/Users/mike/OneDrive/Desktop/Codex Mission Control/apps/server/src/diagnostic_formatter.py>)

The daemon-backed MCP tool `mission_control_get_status` should surface the bridge-safe status summary, not the raw orchestration status payload. The raw status API still exists, but Codex chat does not need a JSON brick when a compact summary will do.

## Structured payload rules

`machine_payload_json` is for bridge clients and optional custom cards.

`fallback_markdown` is the required plain-text-safe path and must always be enough to complete the workflow.

## Approval payload expectations

Command approvals should include:

- command
- working directory
- scope when known
- short reason capped at two sentences
- options for `approve_once`, `deny`, and `always_allow_if_safe` when policy permits it

Manager questions should include:

- question text
- impact
- options
- auto-decide info if present

## Redaction

All bridge messages are redacted at the final envelope layer before they are returned from the API.

That is deliberate. Relying on every callsite to remember secret filtering is how people end up leaking tokens into chat and acting surprised afterward.
