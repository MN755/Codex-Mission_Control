---
name: mission-control-ollama-mode
description: Use or prefer Ollama or local models through Mission Control. Use when the user explicitly wants Ollama or local-model preference and Codex should verify availability rather than assuming it exists.
---

# Mission Control Ollama Mode

## Purpose

Check and explain Mission Control Ollama or local-model mode safely.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for Ollama mode.
- Local-model preference matters.
- A local-first project should check local model availability.

## Workflow

1. Check Mission Control status for local-model or Ollama state if exposed.
2. Explain whether Ollama is available, unknown, or unavailable.
3. If the user wants the mode enabled, route that request through Mission Control policy controls.
4. If unavailable, explain the fallback clearly.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/status`

## User-facing output

- Show available, unavailable, or unknown Ollama state, the likely model-policy effect, and the fallback path.
- Be explicit about any inference.

## Approval behavior

Changing model mode is a policy decision; confirm it with the user first.

## Never do

- Do not assume Ollama is installed or running.
- Do not pretend a local model exists because the user wants one.
- Do not require API keys as a fallback without user awareness.

## Failure and fallback

If Ollama state is not surfaced yet, say so directly, treat availability as unknown, and preserve the current model policy until the backend can verify it.

## Example invocation

`Check whether Mission Control can use Ollama mode for this project.`
