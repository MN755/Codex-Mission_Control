# MCP Bridge Endpoints

This page lists the main backend endpoints that support bridge mode and calls out which ones are MCP-backed versus daemon-only.

> Status: Current

## Core action endpoints

- `/api/health`
- `/api/plugin/health`
- `/api/orchestrations/attach-workspace`
- `/api/orchestrations`
- `/api/orchestrations/{orchestration_id}/status`
- `/api/orchestrations/{orchestration_id}/events`
- `/api/orchestrations/{orchestration_id}/pending-decisions`
- `/api/decisions/{decision_id}/answer`
- `/api/projects/{project_id}/codebase/search`

## Project intelligence endpoints

- `/api/orchestrations/{orchestration_id}/status`
- `/api/orchestrations/{orchestration_id}/events`
- `/api/projects/{project_id}`
- `/api/projects/{project_id}/orchestrations/active`
- `/api/projects/{project_id}/agents`
- `/api/orchestrations/{orchestration_id}/pending-decisions`
- `/api/projects/{project_id}/pending-decisions`
- `/api/projects/{project_id}/handoff`
- `/api/projects/{project_id}/codebase-map`
- `/api/projects/{project_id}/codebase-understanding`
- `/api/projects/{project_id}/workspace-tooling`
- `/api/projects/{project_id}/tensorflow/features`
- `/api/projects/{project_id}/tensorflow/features/{feature_id}`
- `/api/projects/{project_id}/pytorch/features`
- `/api/projects/{project_id}/pytorch/features/{feature_id}`
- `/api/projects/{project_id}/spatial/features`
- `/api/projects/{project_id}/spatial/features/{feature_id}`
- `/api/diagnostics/reports`
- `/api/orchestrations/plugin-health`
- `/api/projects/{project_id}/webwright`
- `/api/projects/{project_id}/nvidia/dynamo`
- `/api/projects/{project_id}/nvidia/nim`
- `/api/projects/{project_id}/nvidia/aiq`
- `/api/projects/{project_id}/nvidia/gpu-diagnostics`
- `/api/projects/{project_id}/nvidia/local-runtime`
- `/api/projects/{project_id}/nvidia/validation-plan`
- `/api/projects/{project_id}/swarm/preferences`
- `/api/projects/{project_id}/swarm/plan`
- `/api/projects/{project_id}/risks`
- `/api/projects/{project_id}/agent-contracts`
- `/api/projects/{project_id}/validation-coverage`
- `/api/projects/{project_id}/decision-ledger`
- `/api/projects/{project_id}/path-locks`
- `/api/projects/{project_id}/operator-snapshot`
- `/api/projects/{project_id}/instincts/preview`
- `/api/projects/{project_id}/verification-brief`
- `/api/projects/{project_id}/capability-report`
- `/api/projects/{project_id}/capability-report/{section_key}`

## Backend-only project APIs

Some daemon APIs are still backend-only, but TensorFlow, PyTorch, and spatial starter catalogs are no longer in that bucket. Those typed starter families are now surfaced through project-scoped MCP resources, prompts, and bridge tools.

## Related pages

Continue with [MCP Plugin Architecture](MCP-Plugin-Architecture), [MCP Resources Catalog](MCP-Resources-Catalog), and [Diagnostics and Health Checks](Diagnostics-and-Health-Checks).
