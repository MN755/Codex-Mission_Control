# Start Manager Led Task

Purpose: start a Mission Control task for an attached project and return compact status.
Arguments: `PROJECT_ID`, `USER_REQUEST`
Tool sequence: `mission_control_start_task` -> `mission_control_get_status` -> `mission_control_get_pending_decisions`
Expected output: orchestration state plus user-blocking decisions if any.
Safety: respect existing pending decisions instead of replacing them with a local plan.
