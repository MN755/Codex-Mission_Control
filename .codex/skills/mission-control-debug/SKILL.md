---
name: mission-control-debug
description: Use when Mission Control orchestration is stuck, failed, degraded, or unclear from Codex chat.
---

# Mission Control Debug

## Purpose

Explain why Mission Control is stuck and surface the safest recovery path through Codex chat.

## Bridge Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## When To Use

- The run looks stuck
- The daemon or bridge is unhealthy
- The user asks why orchestration failed

## Required Mission Control Tools, Resources, And Prompts

- Tools: `mission_control_get_status`, `mission_control_get_diagnostics`, `mission_control_get_pending_decisions`, `mission_control_get_orchestration_events`, `mission_control_request_recovery_options`
- Resources: `mission-control://projects/{project_id}/diagnostics`, `mission-control://orchestrations/{orchestration_id}/events`, `mission-control://projects/{project_id}/pending-decisions`
- Prompts: `debug-failed-orchestration`, `continue-orchestration`

## Step-By-Step Workflow

1. Fetch status.
2. Fetch diagnostics, including platform profile, performance guardrails, safe debug commands, and the latest support-bundle path if present.
3. Fetch pending decisions.
4. Fetch recent orchestration events.
5. Ask Mission Control for recovery options if the tool is available.
6. Distinguish user-blocked, runner-blocked, daemon-blocked, and host-app-blocked states explicitly.
7. Return a concise blocker explanation plus the safest next commands for the detected device.

## What To Show The User In Codex Chat

- Current failure or degraded state
- Detected device family: Windows 10, Windows 11, macOS, or Linux
- Whether the run is blocked on the user, infrastructure, or manager recovery
- Relevant recent events
- Safe next options
- Support-bundle path when one exists

## Safety And Approval Behavior

- Keep raw logs, secrets, and stack traces out of the default summary.
- Treat retries or resumes as explicit actions, not assumptions.

## Fallback Behavior If The Daemon Is Unavailable

- State that bridge-level diagnostics could not reach Mission Control.
- Suggest generating the local support bundle first, then verifying the daemon before continuing.

## What Not To Do

- Do not claim a recovery worked without rechecking status.
- Do not confuse waiting for approval with a crash.
- Do not invent recovery options that Mission Control did not return.
