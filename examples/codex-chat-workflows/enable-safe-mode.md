# Enable Safe Mode

## User Message

`Enable safe mode for this imported repo.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `enable-safe-mode`
2. Tool: `mission_control_enable_safe_mode`
3. Tool: `mission_control_get_diagnostics`
4. Resource: `mission-control://projects/{project_id}/diagnostics`
5. Resource: `mission-control://projects/{project_id}/path-locks`

## Expected Codex Chat Response

Explain which safety settings were tightened, which protections remain approval-gated, and what the diagnostics and path locks report afterward.
