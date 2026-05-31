---
name: mission-control-agent-graph-workflows
description: Design graph-style agent workflows with nodes, edges, gates, retries, checkpoints, and human approvals through Mission Control.
---

# Mission Control Agent Graph Workflows

## Purpose

Model complex agent work as controllable graph workflows instead of linear hope with extra steps.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- A task needs branching, retries, approval gates, or subagents.
- The user wants a workflow diagram or execution plan.
- Failure handling and resumability matter.

## Workflow

1. Ask Mission Control to define workflow nodes, edges, inputs, outputs, and gates.
2. Identify deterministic steps, model steps, tool steps, human approvals, and checkpoints.
3. Define retry and fallback behavior for each failure class.
4. Summarize the graph and execute only through Mission Control approvals.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/decision-ledger`

## User-facing output

- Provide nodes, edges, gates, retries, checkpoints, and current execution state.

## Approval behavior

Ask before increasing agent count, adding tools, or executing risky branches.

## Never do

- Do not spawn parallel work outside Mission Control.
- Do not hide approval gates.
- Do not let graph complexity outrun the task.

## Failure and fallback

If graph execution is overkill, recommend a simpler linear workflow and say why.

## Example invocation

`Use Mission Control to design a graph workflow for release validation and rollback.`
