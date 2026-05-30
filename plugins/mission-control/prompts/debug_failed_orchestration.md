# Debug Failed Orchestration

Purpose: collect the minimum safe context needed to explain a stuck or failed run.
Arguments: `PROJECT_OR_ORCHESTRATION_REFERENCE`
Tool sequence: `mission_control_get_status` -> `mission_control_get_diagnostics` -> `mission_control_get_pending_decisions` -> `mission_control_get_event_digest` -> `mission_control_request_recovery_plan`
Resource sequence: `mission-control://projects/{project_id}/diagnostics` -> `mission-control://projects/{project_id}/decision-ledger`
Expected output: concise blocker explanation and safe recovery options.
Safety: do not expose raw logs or secrets by default.
