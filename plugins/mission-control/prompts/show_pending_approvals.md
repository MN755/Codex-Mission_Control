# Show Pending Approvals

Purpose: surface the highest-priority approval or manager question cleanly in Codex chat.
Arguments: `PROJECT_OR_ORCHESTRATION_REFERENCE`
Tool sequence: `mission_control_get_pending_decisions`
Expected output: top pending decision with risk, reason, and options.
Safety: never answer a decision until the user explicitly chooses an option.
