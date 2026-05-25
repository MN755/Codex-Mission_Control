# Subagent Policy

Mission Control keeps subagent bursts behind an explicit policy.

## Defaults

- `enabled`: `true`
- `default_mode`: `read_only`
- `max_subagents_per_burst`: `6`
- `max_runtime_seconds`: `600`
- `allow_file_edits`: `false`
- `allow_commands`: `false`
- `require_user_approval_above_count`: `3`
- `default_spawn_method`: `codex_chat_bridge`

## Allowed Task Types

- `codebase_exploration`
- `review`
- `planning`
- `handoff_audit`
- `failure_diagnosis`

## When Mission Control Should Recommend a Burst

- the task is read-heavy
- the scope is bounded
- the work can be split into independent reports
- results can be merged cleanly
- commands and file edits fit the current policy

## When Mission Control Should Not Recommend a Burst

- the task is simple
- coordinated edits are required but the current policy is still read-only
- the same shared files would be touched
- scope is unclear
- the likely cost is higher than the value

## Capability-aware behavior

- if `default_mode` is `limited_write` or `allow_file_edits` is `true`, burst specs use `workspace-write`
- if `allow_commands` is `true`, Mission Control says so explicitly in the burst prompt and approval card
- generated custom Codex subagents now inherit the current policy instead of staying permanently read-only

## Approval Rule

If a burst exceeds the configured approval threshold, Mission Control creates a pending decision instead of assuming consent.

That pending decision is rendered in Codex chat.
The user answer is relayed back through Mission Control.
