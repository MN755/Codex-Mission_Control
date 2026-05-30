# Use Mission Control For Repo

Purpose: start a manager-led Mission Control workflow for the current repo from Codex chat.
Arguments: `WORKSPACE_PATH`, `USER_REQUEST`
Tool sequence: `mission_control_attach_workspace` -> `mission_control_start_task` -> `mission_control_get_status` -> `mission_control_get_pending_decisions`
Resource sequence: `mission-control://orchestrations/{orchestration_id}/status` -> `mission-control://projects/{project_id}/pending-decisions`
Expected output: compact status and any pending decisions that need the user.
Safety: Codex is the bridge, not the manager. Do not bypass approvals.
