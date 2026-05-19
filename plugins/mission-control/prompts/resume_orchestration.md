# Resume Orchestration

Purpose: resume a paused Mission Control orchestration after the user confirms it should continue.
Arguments: `ORCHESTRATION_ID`
Tool sequence: `mission_control_resume` -> `mission_control_get_status` -> `mission_control_get_pending_decisions`
Expected output: confirmation that the orchestration resumed or a clear explanation of what still blocks it.
Safety: do not auto-resume a found orchestration without the user asking.
