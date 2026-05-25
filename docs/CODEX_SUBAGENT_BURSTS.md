# Codex Subagent Bursts

Mission Control subagent bursts are short-lived, bounded, parallel Codex subagent recommendations for read-heavy work.

Codex chat is the bridge.
Mission Control Manager is still the orchestrator.
The normal Mission Control worker system is still the default for coordinated implementation work.

## What They Are For

- codebase exploration
- multi-angle review
- planning
- handoff audit
- failure diagnosis

## What They Are Not For

- coordinated multi-file edits
- command-heavy execution
- recursive delegation
- open-ended work with fuzzy scope

## Default Safety Posture

- read-only by default
- no file edits by default
- no commands by default
- no recursive fan-out
- depth stays at `1`
- larger bursts require user approval

If policy is widened to `limited_write` or command-capable mode, Mission Control now reflects that explicitly in the generated burst specs, manual prompts, and custom subagent agent files instead of pretending every burst is read-only forever.

## Codex Chat Workflow

1. Codex asks Mission Control for a burst recommendation.
2. Mission Control may create a `subagent_burst_approval` pending decision.
3. Codex chat renders the bridge-safe burst recommendation.
4. The user approves, trims, skips, or lets the Manager decide.
5. Mission Control records the batch and later ingests subagent results.

## Spawn Methods

- `codex_chat_bridge`
  Mission Control returns a chat-safe burst plan for Codex to carry out.
- `manual_prompt`
  Mission Control returns copyable prompt text.
- `codex_cli`
  Documented as a future or controlled path. It is not the default in this pass.

## Resource Warning

Bursting increases token and coordination cost.
If the task is simple, use the normal path and stop pretending more agents automatically means more intelligence.
