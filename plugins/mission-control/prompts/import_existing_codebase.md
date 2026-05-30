# Import Existing Codebase

Purpose: attach an existing repo or folder with a read-only scan and understanding pass first.
Arguments: `WORKSPACE_PATH`, `USER_REQUEST`
Tool sequence: `mission_control_import_existing_codebase` -> `mission_control_set_import_interview_choice` -> `mission_control_start_task`
Resource sequence: `mission-control://projects/{project_id}/codebase-map` -> `mission-control://projects/{project_id}/status`
Expected output: codebase map summary, understanding summary, and interview choice request if needed.
Safety: do not move into write-capable execution until Mission Control and the user allow it.
