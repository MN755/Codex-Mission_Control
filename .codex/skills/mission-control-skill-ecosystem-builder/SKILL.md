---
name: mission-control-skill-ecosystem-builder
description: Build, audit, or package Mission Control skills and plugin skill bundles. Use when the user wants reusable skills, skill metadata, skill tests, marketplace packaging, or cross-host skill compatibility.
---

# Mission Control Skill Ecosystem Builder

## Purpose

Route skill design and packaging work through Mission Control so reusable instructions stay testable, discoverable, and host-safe.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants a new skill or skill pack.
- Existing skills need cleanup, metadata, tests, or marketplace packaging.
- A skill should work across Codex, Claude Code, or other agent hosts.

## Workflow

1. Ask Mission Control to identify the skill goal, trigger conditions, required assets, and host compatibility.
2. Request a skill contract with frontmatter, workflow, examples, failure modes, and safety boundaries.
3. Validate the skill with package/catalog checks.
4. Summarize changed assets and any host reload requirements.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/validation-summary`

## User-facing output

- Explain the skill purpose, triggers, files changed, validation run, and how the host discovers it.
- Keep examples concrete and copy-pasteable.

## Approval behavior

Ask before publishing, installing globally, or overwriting user-owned skill assets.

## Never do

- Do not copy third-party skill text wholesale.
- Do not ship a skill without clear trigger criteria.
- Do not claim host compatibility without validation.

## Failure and fallback

If package validation is unavailable, produce a draft skill and mark host compatibility as unverified.

## Example invocation

`Use Mission Control to create a reusable skill for release readiness checks.`
