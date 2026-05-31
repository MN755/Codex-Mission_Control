# Enable safe mode

Alias for `enable_safe_mode`.
Canonical prompt: `enable_safe_mode`
Invocation name: `enable-safe-mode`

## Purpose

Tighten project safety settings for a cautious Mission Control run.

## Tool Sequence

- `mission_control_enable_safe_mode`
- `mission_control_get_diagnostics`

## Resource Sequence

- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/path-locks`

## Safety Notes

Never claim safe mode is active unless the policy updates succeeded.

## Prompt Text

Enable Mission Control safe mode for this project by tightening approvals, preserving read-only import posture, pausing dynamic spawning when supported, and restricting risky tools. Then summarize the resulting safety posture.
