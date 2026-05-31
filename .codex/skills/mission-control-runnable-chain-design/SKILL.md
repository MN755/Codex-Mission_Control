---
name: mission-control-runnable-chain-design
description: Design LangChain-style runnable chains, model pipelines, and composable agent steps inside Mission Control without requiring LangChain as a runtime dependency.
---

# Mission Control Runnable Chain Design

## Purpose

Apply composable chain design patterns to Mission Control workflows while keeping the runtime provider-agnostic.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants an LLM pipeline or agent workflow designed.
- A task needs staged prompt, tool, validation, and handoff steps.
- Provider interchangeability matters.

## Workflow

1. Ask Mission Control to identify inputs, model calls, tools, transforms, validators, and outputs.
2. Model the workflow as composable steps with explicit contracts.
3. Define retry, fallback, and human-approval boundaries.
4. Recommend implementation in Mission Control primitives or external frameworks only when useful.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Provide chain stages, inputs/outputs, tools, error handling, and validation checkpoints.

## Approval behavior

Ask before adding new external services or write-capable tools.

## Never do

- Do not force LangChain where Mission Control primitives are enough.
- Do not hide state or retry behavior.
- Do not make model outputs look executable without validation.

## Failure and fallback

If implementation details are unknown, return an architecture sketch and questions.

## Example invocation

`Use Mission Control to design a provider-agnostic chain for triaging issues.`
