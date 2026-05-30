# Enable Safe Mode

Purpose: tighten project safety settings for a cautious Mission Control run.
Arguments: `PROJECT_ID`
Tool sequence: `mission_control_enable_safe_mode` -> `mission_control_get_diagnostics`
Resource sequence: `mission-control://projects/{project_id}/diagnostics` -> `mission-control://projects/{project_id}/path-locks`
Expected output: which safety settings were tightened and what remains approval-gated.
Safety: never claim safe mode is active unless the policy updates succeeded.
