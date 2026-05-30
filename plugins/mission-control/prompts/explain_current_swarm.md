# Explain Current Swarm

Purpose: explain the active or proposed swarm plan in compact Codex chat language.
Arguments: `PROJECT_ID`
Tool sequence: `mission_control_get_swarm_plan`
Resource sequence: `mission-control://projects/{project_id}/swarm-plan` -> `mission-control://projects/{project_id}/agents` -> `mission-control://projects/{project_id}/risk-register`
Expected output: swarm mode, size, risks, bottlenecks, and approval posture.
Safety: do not invent a swarm plan if Mission Control has not produced one.
