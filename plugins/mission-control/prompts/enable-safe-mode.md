# Enable Safe Mode

## Purpose

Tighten Mission Control safety settings for a cautious chat-driven workflow.

## Required Arguments

- `PROJECT_ID`

## Intended Tool And Resource Sequence

1. Call `mission_control_enable_safe_mode`.
2. Call `mission_control_get_diagnostics`.
3. Read `mission-control://projects/{project_id}/diagnostics`.
4. Read `mission-control://projects/{project_id}/path-locks`.

## Expected User-Facing Codex Chat Output

- Which settings were tightened
- Which tools remain blocked or approval-gated
- Whether dynamic spawning is paused

## Safety Notes

- Never claim safe mode is active unless the policy updates succeeded.
- Preserve approval-heavy behavior for risky tools and imported codebases.
