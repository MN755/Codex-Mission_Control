# Pause Orchestration

Purpose: pause the active Mission Control orchestration and confirm the new state.
Arguments: `ORCHESTRATION_ID`
Tool sequence: `mission_control_pause` -> `mission_control_get_status`
Resource sequence: `mission-control://orchestrations/{orchestration_id}/status`
Expected output: confirmation that the orchestration is paused and what remains pending.
Safety: confirm the right orchestration before changing its state.
