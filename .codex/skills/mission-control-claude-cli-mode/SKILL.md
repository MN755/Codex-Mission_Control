---
name: mission-control-claude-cli-mode
description: Use or prefer Claude CLI runner mode through Mission Control. Use when the user explicitly wants Claude CLI if configured and Codex should verify availability and fallback rather than assuming setup exists.
---

# Mission Control Claude Cli Mode

## Purpose

Check and explain Claude CLI runner mode through Mission Control.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for Claude CLI mode.
- Runner availability needs comparison.
- Mission Control may need a non-Codex CLI runner.

## Workflow

1. Check Mission Control status for Claude CLI runner availability.
2. Explain whether it is configured, unavailable, or unknown.
3. If the user wants it enabled, route the request through Mission Control policy or settings flow.
4. Explain fallback if unavailable.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/status`

## User-facing output

- Summarize Claude CLI availability and the fallback path.
- Keep the explanation configuration-aware without demanding setup from the user if it is not already present.

## Approval behavior

Switching runner mode should be an explicit user decision.

## Never do

- Do not require setup the user did not ask for.
- Do not claim Claude CLI is ready when Mission Control cannot verify it.
- Do not ask for raw keys in chat.

## Failure and fallback

If availability is not exposed yet, say that clearly and keep the current runner policy unchanged.

## Example invocation

`See whether Mission Control can prefer Claude CLI for this task.`
