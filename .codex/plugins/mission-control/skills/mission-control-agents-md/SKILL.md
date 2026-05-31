---
name: mission-control-agents-md
description: Generate or review AGENTS.md from Mission Control understanding. Use when the user wants AGENTS.md proposed from the codebase map, existing instructions reviewed, or a safe draft prepared before writing.
---

# Mission Control Agents Md

## Purpose

Use Mission Control understanding to propose or review AGENTS.md safely.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for AGENTS.md generation or review.
- A repo needs agent instructions grounded in actual codebase structure.
- You need to compare existing AGENTS.md guidance against Mission Control understanding.

## Workflow

1. Read the codebase map resource.
2. Check AGENTS.md status or proposal tooling.
3. Call `mission_control_generate_agents_md` or the proposal path when available.
4. Summarize proposed sections and ask before writing any file changes.

## Mission Control calls

Tools:
- `mission_control_generate_agents_md`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Include project overview, setup commands, run commands, test commands, build commands, architecture notes, coding rules, do-not-touch areas, safety rules, and completion report format.
- Tell the user whether the result is a proposal or a written file.

## Approval behavior

Always ask before writing or replacing AGENTS.md, even if the proposal looks good.

## Never do

- Do not invent setup commands that are not backed by the repo or Mission Control understanding.
- Do not overwrite existing AGENTS.md silently.
- Do not expose secret paths or tokens.

## Failure and fallback

If AGENTS.md tooling is not available, use the codebase map to produce a bridge-safe draft summary and clearly mark file generation as expected or future.

## Example invocation

`Use Mission Control to propose an AGENTS.md for this repo.`
