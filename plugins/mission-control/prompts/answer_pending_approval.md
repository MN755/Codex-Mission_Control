# Answer Pending Approval

Purpose: send the user's selected answer back to Mission Control and confirm the result.
Arguments: `DECISION_ID`, `OPTION_ID`, `SELECTED_TEXT`, `FREE_TEXT`
Tool sequence: `mission_control_answer_decision` -> `mission_control_get_pending_decisions`
Resource sequence: `mission-control://projects/{project_id}/pending-decisions`
Expected output: confirmation that the decision was recorded and the updated pending state.
Safety: preserve exact user intent, especially for one-time versus project-wide approvals.
