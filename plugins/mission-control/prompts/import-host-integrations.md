# Import host integrations

Alias for `import_host_integrations`.

Canonical prompt: `import_host_integrations`
Invocation name: `import-host-integrations`

## Tool Sequence

- `mission_control_import_host_integrations`
- `mission_control_get_integration_connections`

## Resource Sequence

- `mission-control://integrations/connections`

## Safety Notes

Report imported metadata and blockers only. Never claim host credentials were copied or verified unless the backend actually proved it.

## Prompt Text

Import integration metadata from any detected Codex or Claude host assets into Mission Control. Then summarize what was discovered, what became connected or host-imported, and which high-value families still need real setup.
