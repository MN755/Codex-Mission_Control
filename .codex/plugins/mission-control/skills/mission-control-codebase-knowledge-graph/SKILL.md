---
name: mission-control-codebase-knowledge-graph
description: Build or inspect a Mission Control codebase knowledge graph. Use for file/function/class maps, dependency relationships, architectural layers, guided tours, and searchable understanding.
---

# Mission Control Codebase Knowledge Graph

## Purpose

Turn codebase understanding into a structured graph-like map that Mission Control can use for planning, onboarding, impact analysis, and handoffs.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks to understand a repo.
- A large codebase needs mapping before changes.
- Planning needs dependencies, layers, or guided tour output.

## Workflow

1. Ask Mission Control to scan project files, languages, frameworks, entrypoints, and instructions.
2. Request graph nodes for files, modules, classes, functions, commands, and domains where available.
3. Request edges for imports, calls, ownership, tests, and runtime relationships.
4. Summarize layers, hotspots, unknowns, and a guided reading order.

## Mission Control calls

Tools:
- `mission_control_import_existing_codebase`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Provide key nodes, relationships, layers, hotspots, and the next-best files to read.

## Approval behavior

Ask before running expensive scans, indexing huge folders, or committing generated graph artifacts.

## Never do

- Do not generate a graph that is pretty but useless.
- Do not include secrets or bulky generated files.
- Do not pretend inferred relationships are proven.

## Failure and fallback

If graph generation is unavailable, use the existing codebase map and clearly label it as a map rather than a full graph.

## Example invocation

`Use Mission Control to build a knowledge graph for this repo and show me the guided tour.`
