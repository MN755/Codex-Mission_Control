# Webwright

> Status: Current

Mission Control now treats [Webwright](https://github.com/microsoft/Webwright) as an optional browser-agent companion.

That means:

- Mission Control does not replace Webwright.
- Mission Control does detect whether the local Webwright runtime is ready.
- Mission Control can route browser-task workflows toward Webwright when it is actually installed.
- Mission Control will say "missing" or "partial" plainly when the runtime is not there.

## What Mission Control uses from Webwright

- the terminal-native, code-as-action browser-task model
- Playwright-backed multi-step browser automation
- reusable script output instead of one-shot click traces
- screenshot-backed verification posture

## What Mission Control does not do

- vendor the full Webwright repository into the Mission Control daemon
- treat Webwright like a model provider
- claim browser automation ran when the Webwright runtime is missing

## Runtime expectations

Mission Control's Webwright readiness surface checks for:

- a detectable `webwright` runtime or importable Python package
- Playwright package presence
- project signals that suggest browser automation would be useful, such as:
  - `package.json` referencing Playwright
  - `playwright.config.*`
  - `tests/e2e` or `e2e`

## Recommended upstream install path

From the upstream Webwright repository:

```bash
git clone https://github.com/microsoft/Webwright
cd Webwright
python -m pip install -e .
playwright install chromium
```

Mission Control already provides the bridge surface, so this install is about the runtime itself, not about adding a second competing plugin.

## Mission Control surfaces

- REST: `/api/projects/{project_id}/webwright`
- MCP resource: `mission-control://projects/{project_id}/webwright`
- MCP tool: `mission_control_get_webwright_status`
- MCP prompt: `use_webwright_for_browser_task`
- Skill: `mission-control-webapp-testing`

## Best use cases

- multi-step browser flows that should end as reusable scripts
- screenshot-backed web verification
- browser tasks where logs and rerunnable artifacts matter more than a persistent browser session
