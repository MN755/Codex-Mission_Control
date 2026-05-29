# MCP Resources

Mission Control resources are read-only context surfaces for Codex chat.

## Resource Rules

- resources do not execute commands
- resources are summary-only by default
- resources redact secrets
- raw logs are hidden unless a future explicit safe view is added

## Resource Catalog

- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/workspace-tooling`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/webwright`
- `mission-control://projects/{project_id}/nvidia-dynamo`
- `mission-control://projects/{project_id}/nvidia-aiq`
- `mission-control://projects/{project_id}/nvidia-gpu-diagnostics`
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
- workspace tooling tells the bridge which repo-native helper lanes actually exist for intake, validation, and security before it recommends commands like a clown
- diagnostics, risk register, decision ledger, and path locks support stuck-run debugging without exposing raw internals
- the Webwright resource tells the bridge whether the local browser-agent runtime is actually ready or whether the user still has setup work to do
- the NVIDIA resources tell the bridge whether GPU-backed inference, deep research, and Prometheus/DCGM telemetry are actually available before Mission Control leans on them
- `nvidia-gpu-diagnostics` is a merged verdict, not a raw metrics dump
  it combines live Prometheus/DCGM telemetry with repo-local GPU summary files and reports whether the current failure smells like infrastructure, code, mixed, or still unknown
- operator snapshot, instincts, and verification brief give Codex or Claude chat a higher-signal operator surface for current state, execution rules, and release readiness
