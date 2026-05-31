# Import existing codebase


Canonical prompt: `import_existing_codebase`
Invocation name: `import_existing_codebase`

## Purpose

Attach an existing repo or folder to Mission Control with a read-only scan and understanding pass first.

## Tool Sequence

- `mission_control_import_existing_codebase`
- `mission_control_set_import_interview_choice`
- `mission_control_start_task`

## Resource Sequence

- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/status`

## Safety Notes

Do not run write-capable steps until Mission Control and the user allow them.

## Prompt Text

Import this existing codebase into Mission Control. Attach it in read-only-first mode, retrieve the codebase map and understanding summary, ask for the interview mode if needed, then start the requested task through Mission Control.
