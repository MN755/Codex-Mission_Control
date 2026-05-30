# Switch Swarm Strategy

Purpose: request a change to swarm strategy and summarize the updated plan or approval requirement.
Arguments: `PROJECT_ID`, `STRATEGY_REQUEST`
Tool sequence: `mission_control_update_swarm_preferences` -> `mission_control_generate_swarm_plan` -> `mission_control_get_swarm_plan`
Resource sequence: `mission-control://projects/{project_id}/swarm-plan`
Expected output: updated swarm preferences and the revised or pending-approval plan summary.
Safety: respect Mission Control approval thresholds for larger or riskier swarms.
