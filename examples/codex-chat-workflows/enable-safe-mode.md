# Enable Safe Mode

## User Message

`Enable safe mode for this imported repo.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `enable-safe-mode`
2. Tool: `mission_control_get_project_settings`
3. Tool: `mission_control_update_project_settings`
4. Tool: `mission_control_get_import_safety`
5. Tool: `mission_control_update_import_safety`
6. Tool: `mission_control_get_tool_catalog`
7. Tool: `mission_control_set_tool_permission`

## Expected Codex Chat Response

Explain which safety settings were tightened, which tools remain restricted, and whether dynamic spawning was paused.
