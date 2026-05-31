# Use Webwright for browser task


Canonical prompt: `use_webwright_for_browser_task`
Invocation name: `use_webwright_for_browser_task`

## Purpose

Check Webwright readiness for the attached project and route a browser task through Mission Control with explicit setup guidance if the runtime is missing.

## Tool Sequence

- `mission_control_get_webwright_status`
- `mission_control_start_task`
- `mission_control_get_status`

## Resource Sequence

- `mission-control://projects/{project_id}/webwright`
- `mission-control://projects/{project_id}/status`

## Safety Notes

Prefer Webwright for multi-step browser work when it is actually installed. If it is missing, say so plainly and do not fake browser coverage.

## Prompt Text

Use Mission Control for a browser task with Webwright when available. First load the project-scoped Webwright readiness summary. If Webwright is not ready, explain the exact missing runtime pieces and the safe install steps. If it is ready, start the requested browser task through Mission Control and summarize the current status without pretending Codex chat is the browser agent itself.
