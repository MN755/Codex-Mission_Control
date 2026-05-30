# Headless Happy Path

Mission Control should be usable from Codex chat without opening the dashboard at all.

## Scenario

User says:

`Use Mission Control for this repo and fix the failing tests.`

Expected bridge flow:

1. Attach the workspace.
2. Reuse or import the project safely.
3. Start or resume a background orchestration.
4. Show a compact status summary in Codex chat.
5. Surface any pending approval or manager question.
6. Send the user answer back through the bridge.
7. Show a compact event digest.
8. Generate or fetch the evidence-based handoff summary.

## Primary endpoints

- `POST /api/headless/attach-workspace`
- `POST /api/orchestrations`
- `GET /api/projects/{project_id}/orchestrations/{orchestration_id}/status-summary`
- `GET /api/orchestrations/{orchestration_id}/pending-decisions`
- `POST /api/decisions/{decision_id}/answer`
- `GET /api/projects/{project_id}/orchestrations/{orchestration_id}/event-digest`
- `GET /api/projects/{project_id}/orchestrations/{orchestration_id}/handoff-summary`
- `POST /api/headless/happy-path-demo`

`/api/orchestrations/attach-workspace` still exists for compatibility, but the headless-first path should use `/api/headless/attach-workspace`.

## Deterministic acceptance test

The backend happy-path test lives in:

- `apps/server/tests/test_headless_happy_path.py`

It covers:

- attach workspace
- start orchestration
- status summary markdown
- pending command approval formatting
- answering the decision
- compact event digest
- dry-run handoff generation
- redaction of secrets from chat output

## Deterministic demo route

`POST /api/headless/happy-path-demo` runs a dry-run-only bridge walkthrough:

1. attach workspace
2. force `dry_run`
3. create or reuse an orchestration
4. wait for or seed a pending decision
5. render the bridge message
6. answer the decision
7. return an event digest
8. return a dry-run handoff summary

It does not claim real edits or real test execution happened, because lying in the demo path would be an impressively stupid design choice.

## Smoke script

The manual smoke script lives in:

- [scripts/smoke-headless-happy-path.ps1](../scripts/smoke-headless-happy-path.ps1)

It will:

1. verify the local daemon, or start it if allowed
2. create a temporary repo-shaped workspace
3. attach that workspace
4. switch the project to `dry_run`
5. start an orchestration
6. print the chat-native status summary
7. print and answer one pending decision
8. print the event digest
9. generate and print the handoff summary

## Why this exists

If the happy path only works from the dashboard, Mission Control is not actually headless. It is just pretending while the dashboard does the real work behind the curtain.
