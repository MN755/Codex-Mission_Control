# Development Guide

This page gives contributors a practical map of the repository and the current headless-first development priorities.

> Status: Current

## Repo structure

Major areas:

- `apps/server/` for backend and daemon logic
- `plugins/mission-control/` for plugin package, MCP catalogs, prompts, and skills
- `.codex/skills/` and `.codex/plugins/` for repo-local Codex integration assets
- `scripts/` for launchers, generators, and validators
- `docs/` for long-form repo documentation
- `examples/` for Codex workflow examples

## Current contribution direction

Prefer work on:

- daemon and runtime behavior
- MCP bridge and catalogs
- headless install and health flows
- skills, prompts, and bridge-safe formatting
- diagnostics, security, and tests

Do not focus on the optional standalone UI unless explicitly asked.

## Useful commands

Backend setup:

```powershell
cd apps/server
python -m pip install -e .[dev]
python -m pytest
```

Daemon start:

```powershell
.\scripts\start-mission-control-daemon.ps1
```

## Related pages

Continue with [Testing and Smoke Checks](Testing-and-Smoke-Checks), [Contributor Rules for AI Agents](Contributor-Rules-for-AI-Agents), [Docs Source Map](Docs-Source-Map), and [Roadmap](Roadmap).
