---
name: mission-control-import-codebase
description: Use when Codex should attach an existing repo or folder to Mission Control in read-first import mode.
---

# Mission Control Import Codebase

## Purpose

Safely bring an existing codebase into Mission Control so the manager can understand it before work starts.

## Bridge Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## When To Use

- The current folder already contains code
- The user says `import this repo`
- The user wants Mission Control to inspect an existing project before edits

## Required Mission Control Tools, Resources, And Prompts

- Tools: `mission_control_attach_workspace`, `mission_control_get_codebase_map`, `mission_control_get_codebase_understanding`, `mission_control_set_import_interview_choice`, `mission_control_start_task`
- Resources: `mission-control://projects/{project_id}/codebase-map`, `mission-control://projects/{project_id}/status`
- Prompts: `attach-current-workspace`, `import-existing-codebase`, `start-manager-led-task`

## Step-By-Step Workflow

1. Attach the workspace in existing-codebase mode.
2. Keep the first scan read-only.
3. Retrieve the codebase map resource.
4. Retrieve the codebase understanding summary.
5. Ask the user whether to skip interview, quick clarify, full interview, or let the manager decide.
6. Send that choice through `mission_control_set_import_interview_choice`.
7. Start the requested task through Mission Control.

## What To Show The User In Codex Chat

- Imported or reused project ID
- Read-only scan outcome
- Compact codebase map summary
- Compact understanding summary
- Interview choice options

## Safety And Approval Behavior

- Treat the repo as user-owned until Mission Control says otherwise.
- Do not expose secrets from config or environment files.
- Do not start installs, builds, tests, or writes during import unless the user explicitly approves that path.

## Fallback Behavior If The Daemon Is Unavailable

- Report that import could not be delegated to Mission Control.
- Do not pretend the read-only scan happened.
- Offer to debug the bridge or postpone Mission Control usage.

## What Not To Do

- Do not skip the read-only pass for an unknown codebase.
- Do not answer the interview choice on behalf of the user.
- Do not reinterpret a successful attach as permission to edit.
