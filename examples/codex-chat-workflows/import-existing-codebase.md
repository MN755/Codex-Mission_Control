# Import Existing Codebase

## User Message

`Import this existing repo into Mission Control before doing anything else.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `import-existing-codebase`
2. Tool: `mission_control_import_existing_codebase`
3. Resource: `mission-control://projects/{project_id}/codebase-map`
4. Resource: `mission-control://projects/{project_id}/status`
5. Tool: `mission_control_set_import_interview_choice`
6. Tool: `mission_control_start_task`

## Expected Codex Chat Response

Return a read-only import summary, a compact codebase map summary, the interview choice request, and the next Mission Control step.
