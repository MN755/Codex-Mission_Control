# Contributing

> Status: Current

This page describes the project-specific development expectations for contributors working on Codex Mission Control.

## Current direction

Mission Control is designed first for background running through Codex chat.

- Codex chat is the user-facing bridge
- Mission Control daemon owns orchestration
- the Manager AI lives inside Mission Control
- worker agents stay behind Mission Control approvals
- the standalone dashboard is optional and not the current product center

## Focus areas

- daemon and runtime behavior
- MCP bridge tools, resources, and prompts
- plugin packaging and skills
- pending decisions and handoffs
- diagnostics, security, and docs

## Avoid unless explicitly requested

- dashboard pages
- project workspace UI
- widget work
- sidebars
- frontend layout or visual polish

## Setup and validation

```powershell
cd apps/server
python -m pip install -e .[dev]
python -m pytest
```

## Documentation expectations

- keep public docs concise and factual
- describe Codex chat as the bridge, not the Manager
- label planned or partial behavior honestly
- do not include secrets in examples, logs, or reports

## Related docs

- [Public release checklist](PUBLIC_RELEASE_CHECKLIST.md)
- [Optional Dashboard UI](OPTIONAL_DASHBOARD_UI.md)
- [Workflow](WORKFLOW.md)
