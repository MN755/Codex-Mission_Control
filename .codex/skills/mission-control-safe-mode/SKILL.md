---
name: mission-control-safe-mode
description: Use when the user wants Mission Control to operate in a stricter approval-heavy safety posture.
---

# Mission Control Safe Mode

## Purpose

Tighten Mission Control safety settings for risky, unfamiliar, or imported workspaces.

## Bridge Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## When To Use

- The user asks for strict safety
- The repo is unfamiliar
- External tools or destructive actions should be gated harder

## Required Mission Control Tools, Resources, And Prompts

- Tools: `mission_control_get_project_settings`, `mission_control_update_project_settings`, `mission_control_get_import_safety`, `mission_control_update_import_safety`, `mission_control_get_tool_catalog`, `mission_control_set_tool_permission`
- Resources: `mission-control://projects/{project_id}/diagnostics`, `mission-control://projects/{project_id}/pending-decisions`
- Prompts: `enable-safe-mode`

## Step-By-Step Workflow

1. Read current settings and import safety state.
2. Require approvals for commands.
3. Pause dynamic spawning if supported.
4. Block destructive actions.
5. Disable deployment or external-account tools unless explicitly approved.
6. Enforce read-only scan behavior for imported codebases.

## What To Show The User In Codex Chat

- Which safety knobs were tightened
- Which tools remain blocked or approval-gated
- Whether dynamic spawning was paused

## Safety And Approval Behavior

- Favor `ask_every_time` or equivalent conservative settings.
- Preserve Mission Control approval flow instead of replacing it with Codex judgment.

## Fallback Behavior If The Daemon Is Unavailable

- Say that safe mode changes could not be applied through Mission Control.
- Do not claim the environment is protected if the policy update did not happen.

## What Not To Do

- Do not silently relax safety later.
- Do not use safe mode as an excuse to bypass Mission Control.
- Do not grant project-wide tool access without explicit user approval.
