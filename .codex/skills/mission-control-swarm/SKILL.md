---
name: mission-control-swarm
description: Use when the user wants to inspect or adjust Mission Control swarm strategy from Codex chat.
---

# Mission Control Swarm

## Purpose

Inspect, explain, or adjust Mission Control swarm behavior without bypassing manager approval rules.

## Bridge Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## When To Use

- `Show swarm plan`
- `Explain the swarm`
- `Scale up`
- `Scale down`
- `Switch to high_quality`
- `Pause dynamic spawning`

## Required Mission Control Tools, Resources, And Prompts

- Tools: `mission_control_get_swarm_plan`, `mission_control_update_swarm_preferences`, `mission_control_generate_swarm_plan`, `mission_control_approve_swarm_plan`
- Resources: `mission-control://projects/{project_id}/swarm-plan`, `mission-control://projects/{project_id}/agents`, `mission-control://projects/{project_id}/risk-register`
- Prompts: `explain-current-swarm`, `switch-swarm-strategy`

## Step-By-Step Workflow

1. Read the current swarm plan.
2. Explain the current mode, size, risks, and approval posture.
3. If the user asks for a change, update swarm preferences or request a new plan.
4. Respect approval requirements before changing plan scale or risk posture.
5. Return the revised plan summary.

## What To Show The User In Codex Chat

- Current swarm mode
- Agent count and expected bottlenecks
- Dynamic spawning state
- Risk and approval implications of any requested change

## Safety And Approval Behavior

- Do not change swarm size or aggression outside Mission Control policy.
- Surface any approval threshold crossing before applying it.

## Fallback Behavior If The Daemon Is Unavailable

- Report that swarm planning could not be read or changed through Mission Control.
- Do not invent a replacement swarm plan in chat.

## What Not To Do

- Do not scale or respawn agents directly from Codex chat.
- Do not promise performance gains that Mission Control did not project.
- Do not treat a draft plan as approved.
