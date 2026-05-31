# Review project capabilities

Alias for `review_project_capabilities`.
Canonical prompt: `review_project_capabilities`
Invocation name: `review-project-capabilities`

## Purpose

Load the full project capability report when the operator needs the whole Mission Control execution and readiness picture in one pass.

## Tool Sequence

- `mission_control_get_capability_report`

## Resource Sequence

- `mission-control://projects/{project_id}/capability-report`

## Safety Notes

Summarize the report instead of dumping every field blindly, and do not treat one healthy lane as proof that the whole project is healthy.

## Prompt Text

Review the full Mission Control capability report for the attached project. Summarize the strongest ready lanes, the partial or blocked lanes, the safest next commands, and the highest-signal gaps that still limit execution quality.
