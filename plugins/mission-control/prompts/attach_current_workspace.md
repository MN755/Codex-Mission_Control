# Attach Current Workspace

Purpose: attach the current folder to Mission Control and report the safest next step.
Arguments: `WORKSPACE_PATH`, `USER_REQUEST`
Tool sequence: `mission_control_attach_workspace` -> `mission_control_get_status`
Resource sequence: `mission-control://projects/{project_id}/status`
Expected output: attached project or orchestration ID plus a compact status summary.
Safety: prefer read-only-first behavior for existing codebases and never expose secrets.
