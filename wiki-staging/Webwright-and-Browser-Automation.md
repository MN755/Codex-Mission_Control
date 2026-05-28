# Webwright and Browser Automation

This page explains how Mission Control integrates the upstream Webwright runtime as an optional browser-agent companion instead of pretending browser automation is a normal model runner.

> Status: Current

## What this integration means

Mission Control does not vendor the whole Webwright repository and it does not treat Webwright like a provider.

Instead, Mission Control exposes:

- a project-scoped readiness check
- explicit setup guidance when the runtime is missing
- browser-task routing guidance when the runtime is ready
- bridge-safe summaries for Codex or Claude chat

## When to use it

Prefer Webwright when the task needs:

- real multi-step browser automation
- screenshot-backed verification
- rerunnable browser scripts instead of one-off chat claims

Do not treat it as mandatory for ordinary app smoke checks or non-browser coding work.

## Mission Control surfaces

Current surfaces:

- REST: `/api/projects/{project_id}/webwright`
- MCP resource: `mission-control://projects/{project_id}/webwright`
- MCP tool: `mission_control_get_webwright_status`
- MCP prompt: `use_webwright_for_browser_task`
- Skill lane: `mission-control-webapp-testing`

## Upstream install path

The upstream runtime setup is:

```bash
git clone https://github.com/microsoft/Webwright
cd Webwright
python -m pip install -e .
playwright install chromium
```

Mission Control already provides the orchestration bridge. This install is only about getting the local Webwright runtime ready.

## Related pages

Continue with [Runner Configuration](Runner-Configuration), [MCP Resources Catalog](MCP-Resources-Catalog), [MCP Prompts Catalog](MCP-Prompts-Catalog), and [Debugging Common Issues](Debugging-Common-Issues).
