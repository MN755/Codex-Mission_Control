# Review Latest Handoff

Purpose: retrieve the latest Mission Control handoff and summarize it for Codex chat.
Arguments: `PROJECT_OR_ORCHESTRATION_REFERENCE`
Tool sequence: `mission_control_get_handoff_summary`
Expected output: what changed, how to run it, validation posture, limitations, and next steps.
Safety: warn if the handoff is dry-run or missing evidence.
