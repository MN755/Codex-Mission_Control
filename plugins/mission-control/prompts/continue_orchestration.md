# Continue Orchestration

Purpose: summarize current progress and stop cleanly when the run is waiting on the user.
Arguments: `PROJECT_OR_ORCHESTRATION_REFERENCE`
Tool sequence: `mission_control_get_status` -> `mission_control_get_pending_decisions` -> `mission_control_get_event_digest`
Expected output: progress summary, blockers, and pending decisions if present.
Safety: poll only when useful and do not confuse waiting with completion.
