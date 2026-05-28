---
name: mission-control-webapp-testing
description: Plan or run web application testing through Mission Control. Use for local browser smoke tests, console errors, accessibility checks, screenshots, and regression validation.
---

# Mission Control Webapp Testing

## Purpose

Use Mission Control to coordinate practical browser and web regression testing without making the chat agent improvise test coverage.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- A web app needs smoke testing.
- Frontend changes need browser verification.
- The user asks for screenshots, console checks, accessibility checks, or regressions.

## Workflow

1. Ask Mission Control to identify the app URL, startup command, and target flows.
2. Check the project-scoped Webwright readiness surface.
3. Request a compact test plan.
4. Prefer Webwright for approved multi-step browser checks when it is actually ready.
5. Summarize observed behavior, errors, screenshots, and gaps.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_webwright_status`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/webwright`

## User-facing output

- Include URL tested, flows checked, console/network errors, visual issues, and validation gaps.

## Approval behavior

Ask before starting servers, installing browser dependencies, or running external-network tests.

## Webwright preference

- If Webwright is ready, prefer it for multi-step browser automation, screenshot-backed verification, and reusable browser scripts.
- If Webwright is not ready, say exactly what is missing and keep the browser automation claim unverified.

## Never do

- Do not declare UI working without opening or testing the target.
- Do not edit guarded UI areas unless the user asked for UI work.
- Do not hide flaky or skipped checks.

## Failure and fallback

If browser automation is unavailable, provide a manual smoke checklist and mark automation unverified.

## Example invocation

`Use Mission Control to smoke test the local web app and report console errors.`
