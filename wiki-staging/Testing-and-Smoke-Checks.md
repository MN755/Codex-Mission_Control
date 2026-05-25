# Testing and Smoke Checks

This page explains what should be validated before calling a Mission Control change ready for handoff.

> Status: Current

## What to test

Validation targets:

- backend tests
- MCP catalog and prompt checks
- skill validation
- headless happy path
- runner detection smoke checks
- startup freshness and provider-adapter smoke checks
- subagent policy behavior checks
- diagnostic summary output

## Example commands

Copyable examples:

```powershell
cd apps/server
python -m pytest
```

```powershell
python scripts\validate-mission-control-skills.py
```

## What should pass before handoff

Before handoff, aim to have:

- relevant tests run
- validation gaps called out honestly
- skill or catalog docs regenerated if changed
- diagnostics clean enough to explain known degraded states

## Related pages

Read [Handoffs and Evidence](Handoffs-and-Evidence), [Validation Summary Reference](Validation-Summary-Reference), and [Diagnostics and Health Checks](Diagnostics-and-Health-Checks).
