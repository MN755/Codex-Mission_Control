---
name: mission-control-rag-retrieval-design
description: Design retrieval, indexing, chunking, ranking, and RAG workflows through Mission Control. Use for docs search, code search, semantic recall, and context-pack construction.
---

# Mission Control RAG Retrieval Design

## Purpose

Design retrieval systems that support agent work without turning context into a random pile of embeddings.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants semantic search, RAG, retrievers, or context packs.
- Large docs or codebases need selective context.
- Retrieval quality needs evaluation.

## Workflow

1. Ask Mission Control to define corpus, chunking, metadata, ranking, and freshness rules.
2. Choose local-first or API-backed retrieval based on policy.
3. Define context-pack boundaries and citation expectations.
4. Plan retrieval evaluation with representative questions.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/validation-summary`

## User-facing output

- Summarize corpus scope, retrieval design, freshness, privacy posture, eval plan, and limitations.

## Approval behavior

Ask before sending private content to external embedding or vector services.

## Never do

- Do not imply semantic search is accurate without evals.
- Do not leak secrets into indexes.
- Do not use stale indexes without saying so.

## Failure and fallback

If no retriever exists, propose a simple lexical baseline before vector search.

## Example invocation

`Use Mission Control to design a local-first RAG path for this docs folder.`
