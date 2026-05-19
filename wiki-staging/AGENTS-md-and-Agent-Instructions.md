# AGENTS md and Agent Instructions

This page explains why AGENTS.md matters, what it should contain, and how Mission Control should propose or use it for imported repositories.

> Status: Current

## Why AGENTS.md matters

AGENTS.md gives structured instructions to Codex-style agents and bridge flows.

It should reduce ambiguity around:

- setup and run commands
- test expectations
- architecture notes
- do-not-touch areas
- safety rules

## What it should include

Recommended sections:

- project overview
- setup commands
- run commands
- test commands
- build commands
- architecture notes
- coding rules
- do-not-touch areas
- safety rules
- completion report format

## Mission Control workflow

Mission Control should:

1. read the codebase map
2. detect whether AGENTS.md already exists
3. propose content
4. ask before writing

## Example outline

Example prompt:

```text
Use Mission Control to propose AGENTS.md from the current codebase understanding.
```

## Related pages

Read [Existing Codebase Mode](Existing-Codebase-Mode), [Skills and Prompts](Skills-and-Prompts), and [Contributor Rules for AI Agents](Contributor-Rules-for-AI-Agents).
