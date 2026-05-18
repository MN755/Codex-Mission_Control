---
name: mission-control-agents-md
description: Use when Codex should generate or review AGENTS.md through Mission Control context and explicit user approval.
---

# Mission Control AGENTS.md

## Purpose

Generate or review an `AGENTS.md` proposal based on Mission Control's codebase understanding and project context.

## Bridge Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## When To Use

- The user asks to generate `AGENTS.md`
- The imported codebase has no agent instructions
- The user wants Mission Control to review or update existing instructions

## Required Mission Control Tools, Resources, And Prompts

- Tools: `mission_control_get_codebase_map`, `mission_control_get_agents_md_status`, `mission_control_propose_agents_md`
- Resources: `mission-control://projects/{project_id}/codebase-map`
- Prompts: `generate-agents-md-proposal`

## Step-By-Step Workflow

1. Read the codebase map.
2. Check `AGENTS.md` status.
3. Request an `AGENTS.md` proposal.
4. Show the proposal to the user before any write step.
5. Ask whether to accept, revise, or defer the proposal.

## What To Show The User In Codex Chat

- Whether `AGENTS.md` already exists
- Recommended path
- Proposal summary
- Proposed sections for setup, run, test, build, architecture, style, protected areas, and completion reports

## Safety And Approval Behavior

- Ask before writing or replacing `AGENTS.md`.
- Keep the proposal derived from repo context instead of generic boilerplate.

## Fallback Behavior If The Daemon Is Unavailable

- Say the proposal could not be generated through Mission Control.
- Do not fabricate that Mission Control reviewed the repo if it did not.

## What Not To Do

- Do not overwrite `AGENTS.md` without user approval.
- Do not invent setup or test commands that are unsupported by the codebase map.
