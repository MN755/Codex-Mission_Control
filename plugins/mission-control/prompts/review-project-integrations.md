# Review project integrations

Alias for `review_project_integrations`.

Canonical prompt: `review_project_integrations`
Invocation name: `review-project-integrations`

## Tool Sequence

- `mission_control_get_project_integrations`

## Resource Sequence

- `mission-control://projects/{project_id}/integrations`

## Safety Notes

Keep the output project-scoped and evidence-based. Do not treat a detected config file as proof that the live provider is actually usable.

## Prompt Text

Review the project-scoped Mission Control integrations report. Summarize the ready families, the blocked or partial ones, the safest next commands, and the biggest gaps that still limit this project's integration posture.
