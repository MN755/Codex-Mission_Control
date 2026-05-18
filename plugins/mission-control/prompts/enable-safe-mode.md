# Enable Safe Mode

## Purpose

Tighten Mission Control safety settings for a cautious chat-driven workflow.

## Required Arguments

- `PROJECT_ID`

## Intended Tool And Resource Sequence

1. Call `mission_control_get_project_settings`.
2. Call `mission_control_update_project_settings`.
3. Call `mission_control_get_import_safety`.
4. Call `mission_control_update_import_safety`.
5. Call `mission_control_get_tool_catalog`.
6. Call `mission_control_set_tool_permission`.

## Expected User-Facing Codex Chat Output

- Which settings were tightened
- Which tools remain blocked or approval-gated
- Whether dynamic spawning is paused

## Safety Notes

- Never claim safe mode is active unless the policy updates succeeded.
- Preserve approval-heavy behavior for risky tools and imported codebases.
