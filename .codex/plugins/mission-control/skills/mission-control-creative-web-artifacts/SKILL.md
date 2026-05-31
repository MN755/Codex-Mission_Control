---
name: mission-control-creative-web-artifacts
description: Plan creative web artifacts, themed pages, demos, and visual prototypes through Mission Control while preserving project guardrails and validation.
---

# Mission Control Creative Web Artifacts

## Purpose

Coordinate creative or visual web output without wandering into unapproved UI rewrites.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants a visual artifact, themed page, design prototype, or interactive demo.
- The work may touch frontend files.
- The project needs a clear visual direction before implementation.

## Workflow

1. Ask Mission Control to identify scope, target files, visual direction, and guardrails.
2. Confirm UI work is allowed for this repo.
3. Request implementation or prototype planning through managed workers.
4. Validate rendering, responsiveness, and accessibility when possible.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/risk-register`

## User-facing output

- Summarize visual direction, files touched, validation, screenshots if available, and known design risks.

## Approval behavior

Ask before editing guarded UI areas or introducing large frontend dependencies.

## Never do

- Do not ignore repository UI guardrails.
- Do not ship generic visual mush.
- Do not claim responsive behavior without checking it.

## Failure and fallback

If UI work is disallowed, return a design brief or implementation plan only.

## Example invocation

`Use Mission Control to design a bold landing-page prototype, but respect this repo's UI guardrails.`
