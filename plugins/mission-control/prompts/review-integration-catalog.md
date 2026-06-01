# Review integration catalog

Alias for `review_integration_catalog`.

Canonical prompt: `review_integration_catalog`
Invocation name: `review-integration-catalog`

## Tool Sequence

- `mission_control_get_integrations_catalog`
- `mission_control_get_integration_connections`

## Resource Sequence

- `mission-control://integrations/catalog`
- `mission-control://integrations/connections`

## Safety Notes

Summarize normalized status and blockers. Do not expose raw credentials or pretend a detected CLI is the same thing as a working remote integration.

## Prompt Text

Review the Mission Control cross-host integration catalog and normalized connection registry. Summarize which integration families are already usable, which are host-imported only, which still need setup, and the highest-signal next fixes.
