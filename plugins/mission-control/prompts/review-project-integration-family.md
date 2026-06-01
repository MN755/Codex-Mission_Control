# Review project integration family

Alias for `review_project_integration_family`.

Canonical prompt: `review_project_integration_family`
Invocation name: `review-project-integration-family`

## Tool Sequence

- `mission_control_get_project_integration_family`

## Resource Sequence

- `mission-control://projects/{project_id}/integrations/{family}`

## Safety Notes

Keep the output scoped to the requested family and do not oversell host-imported metadata as a verified live connection.

## Prompt Text

Review one project-scoped Mission Control integration family. Summarize its current status, imported host hints, safe commands, available actions, blockers, and the highest-signal next fix if the lane is still partial.
