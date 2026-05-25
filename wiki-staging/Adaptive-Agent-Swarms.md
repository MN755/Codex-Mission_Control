# Adaptive Agent Swarms

This page explains how Mission Control should plan, scale, and constrain worker swarms under Manager AI control.

> Status: Current

## What the Manager plans

The Manager should decide:

- swarm mode
- agent archetypes
- scale up or down timing
- path ownership and contracts
- dynamic retirement
- coordination risk
- approval threshold for larger swarms

## Swarm modes

Modes:

- `fastest_build`
- `balanced`
- `high_quality`
- `documentation_heavy`
- `research_planning`
- `massive_codebase`
- `safe_mode`

## Safety constraints

Adaptive swarms should still obey:

- max agent limits
- write scope restrictions
- path locks
- contract boundaries
- high-risk approval gates
- local performance guardrails so weaker machines are not overcommitted

## Capability-aware subagent bursts

Mission Control now reflects the current subagent policy inside burst specs instead of pretending every burst is permanently read-only.

That means:

- read-only stays the default
- limited-write bursts can use `workspace-write`
- command-capable bursts say so explicitly
- generated custom Codex subagents inherit the same policy

## User-facing explanation

Codex chat should summarize swarm state as:

- current mode
- active agents
- path conflict risk
- whether dynamic spawning is paused
- whether approval is needed before scaling

## Related pages

Read [Swarm Modes Reference](Swarm-Modes-Reference), [Agent Archetypes](Agent-Archetypes), [Path Locks and Ownership](Path-Locks-and-Ownership), and [Manager AI vs Codex Chat](Manager-AI-vs-Codex-Chat).
