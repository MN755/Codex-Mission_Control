# Existing Codebase Mode

This page explains how Mission Control should attach and understand a non-empty repository before writing to it.

> Status: Current

## Core workflow

Existing-codebase mode should:

1. attach the current folder
2. classify it as an existing repo
3. run a read-only scan first
4. build a codebase map
5. produce a codebase understanding summary
6. choose skip, quick, or full interview if needed
7. only then move into planning or execution

## Safety mode and AGENTS.md

Imported codebase safety mode should favor:

- read-only scan first
- approval for write permission
- AGENTS.md detection and proposal review
- progressive understanding for large repositories

## Example flow

Example prompt:

```text
Use Mission Control to understand this repo and fix startup.
```

Expected response:

```text
Mission Control attached the repo, completed a read-only scan, detected the stack, and is waiting on one clarification before planning the startup fix.
```

## Large repositories

For large repos, understanding should be progressive:

- top-level map first
- important entry points next
- focused deeper scan only when the requested task justifies it

## Related pages

Continue with [Codebase Map and Understanding](Codebase-Map-and-Understanding), [AGENTS md and Agent Instructions](AGENTS-md-and-Agent-Instructions), and [Quick Start](Quick-Start).
