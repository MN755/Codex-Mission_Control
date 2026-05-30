---
name: mission-control-evals-observability
description: Design or run evaluation, tracing, callback, telemetry, and regression-observability workflows for Mission Control agents.
---

# Mission Control Evals And Observability

## Purpose

Make agent quality measurable with evals, traces, evidence, and regression checks instead of vibes in a trench coat.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants evals or quality gates.
- Agent behavior needs traceability.
- A workflow needs regression tests or benchmark cases.

## Workflow

1. Ask Mission Control to identify success criteria and failure modes.
2. Define eval cases, expected outputs, evidence checks, and scoring.
3. Capture trace points for model calls, tools, approvals, and handoffs.
4. Summarize results and recommend gates.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_event_digest`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/handoff`

## User-facing output

- Include eval cases, pass/fail status, trace coverage, regressions, and evidence gaps.

## Approval behavior

Ask before running costly model/API eval suites or uploading traces externally.

## Never do

- Do not call an eval meaningful without representative cases.
- Do not log secrets in traces.
- Do not reduce quality to a single opaque score.

## Failure and fallback

If automated evals are unavailable, produce a manual eval rubric and seed cases.

## Example invocation

`Use Mission Control to design evals for the Ollama worker edit path.`
