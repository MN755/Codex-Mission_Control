# Debug failed orchestration


Canonical prompt: `debug_failed_orchestration`
Invocation name: `debug_failed_orchestration`

## Purpose

Collect the minimum safe context needed to explain a stuck or failed Mission Control run, including device-aware diagnostics.

## Tool Sequence

- `mission_control_get_status`
- `mission_control_get_diagnostics`
- `mission_control_get_pending_decisions`
- `mission_control_get_event_digest`
- `mission_control_request_recovery_plan`

## Resource Sequence

- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/decision-ledger`

## Safety Notes

Do not expose raw logs or secrets by default.

## Prompt Text

Debug the failed or stuck Mission Control orchestration by collecting status, diagnostics, pending decisions, and a safe event digest. Include platform-aware diagnostics, performance guardrails, safe debug commands, and the latest support-bundle path when available. If needed, create a recovery plan request and summarize the safest next moves.
