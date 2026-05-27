# MCP Resources

Mission Control resources are read-only context surfaces for Codex chat.

## Resource Rules

- resources do not execute commands
- resources are summary-only by default
- resources redact secrets
- raw logs are hidden unless a future explicit safe view is added

## Resource Catalog

- `mission-control://orchestrations/{orchestration_id}/status`
- `mission-control://orchestrations/{orchestration_id}/events`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/risk-register`
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/path-locks`
- `mission-control://projects/{project_id}/operator-snapshot`
- `mission-control://projects/{project_id}/instincts`
- `mission-control://projects/{project_id}/verification-brief`

## Why These Exist

- status and events support compact progress reporting
- pending decisions support approval relay
- handoff supports final bridge summaries
- codebase map supports imported repo understanding
- diagnostics, risk register, decision ledger, and path locks support stuck-run debugging without exposing raw internals
- operator snapshot, instincts, and verification brief give Codex or Claude chat a higher-signal operator surface for current state, execution rules, and release readiness
