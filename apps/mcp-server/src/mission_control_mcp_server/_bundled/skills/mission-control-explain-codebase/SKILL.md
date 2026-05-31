---
name: mission-control-explain-codebase
description: Explain an unfamiliar codebase from Mission Control understanding. Use when the user wants stack detection, structure, entry points, how it likely runs, how tests work, risky areas, or recommended exploration next.
---

# Mission Control Explain Codebase

## Purpose

Explain the codebase from Mission Control resources without doing ad hoc repo archaeology first.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks what this repo is.
- An imported codebase needs a plain-English explanation.
- You need a safe overview before deeper work.

## Workflow

1. Verify the Mission Control bridge surface first:
   - prefer named `mission_control_*` tools when exposed
   - in Codex CLI sessions, use `codex mcp list` if needed to tell "registered" apart from "callable here"
   - if exposure is unclear, confirm MCP registration or resource visibility before claiming understanding resources are unavailable
2. Read codebase-map and status resources.
3. Extract stack, structure, entry points, likely runtime path, test setup, and risky or unknown areas.
4. Return a compact explanation and suggested next exploration.

## Mission Control calls

Tools:
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Include detected stack, structure, entry points, how it likely runs, how tests work, risky or unknown areas, and suggested next exploration.
- Keep it at summary level unless the user asks for file-by-file detail.

## Approval behavior

This is a read-only explanation. If the user wants edits afterward, switch back to Mission Control task execution with normal approvals.

## Never do

- Do not dump whole file contents by default.
- Do not pretend uncertain areas are settled.
- Do not skip the codebase map if it exists.

## Failure and fallback

If codebase understanding is incomplete, say what is known, what is inferred, and what still needs a deeper Mission Control scan. If the issue is partial MCP exposure rather than a missing bridge, say that precisely.

## Example invocation

`Explain this codebase using Mission Control understanding.`
