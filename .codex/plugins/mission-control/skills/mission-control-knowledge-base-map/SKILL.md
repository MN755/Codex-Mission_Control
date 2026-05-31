---
name: mission-control-knowledge-base-map
description: Build or inspect a graph-style map of docs, wiki pages, claims, entities, and relationships through Mission Control.
---

# Mission Control Knowledge Base Map

## Purpose

Turn documentation and wiki material into a navigable claim/entity map with source-aware summaries.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants to understand a docs folder or knowledge base.
- Wiki pages need relationship mapping.
- Claims and entities need source tracking.

## Workflow

1. Ask Mission Control to scan docs and identify pages, entities, claims, links, and categories.
2. Map explicit links separately from inferred relationships.
3. Detect orphan pages, duplicate concepts, and stale claims.
4. Return a source-aware map and recommended cleanup.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/risk-register`
- `mission-control://projects/{project_id}/handoff`

## User-facing output

- Include entities, claims, relationships, orphan/stale areas, and source confidence.

## Approval behavior

Ask before rewriting docs or committing generated graph artifacts.

## Never do

- Do not blur explicit links with inferred relationships.
- Do not quote large copyrighted docs into chat.
- Do not claim knowledge-base completeness without scan coverage.

## Failure and fallback

If docs are too large, propose an incremental scan scope.

## Example invocation

`Use Mission Control to map the docs folder into claims, entities, and stale areas.`
