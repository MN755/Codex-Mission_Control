# Ask Manager For Plan

Purpose: request a fresh Mission Control manager plan without replacing the manager with Codex chat logic.
Arguments: `PROJECT_ID`, `USER_REQUEST`
Tool sequence: `mission_control_start_task` -> `mission_control_get_status` -> `mission_control_get_pending_decisions`
Expected output: compact status plus the latest manager plan posture or plan-blocking decision.
Safety: use Mission Control as the planner instead of improvising a local plan in chat.
