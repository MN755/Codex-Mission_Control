# Install From Codex

This page documents the ideal user workflow when the user asks Codex chat to install and wire up Mission Control from GitHub.

> Status: Partial / Experimental

## Ideal prompt

The ideal user prompt is:

```text
Install Mission Control from https://github.com/MN755/Codex-Mission_Control and wire it up for this workspace.
```

## What should happen

Expected flow:

1. Clone or reuse the repository.
2. Run the headless bootstrap path.
3. Probe environment and runtime prerequisites.
4. Configure daemon, MCP bridge, plugin files, and skills.
5. Detect available runners.
6. Report status back into Codex chat.
7. Ask for missing login or configuration only when needed.

## Expected output example

Example summary:

```text
Mission Control install summary

- Repo: attached
- Daemon: ready on localhost
- MCP bridge: configured
- Skills: installed
- Preferred runner: codex_cli
- Missing action: none
```

## Current reality

The repo already contains headless docs, plugin package content, MCP catalogs, and daemon start scripts.

Full one-shot install and autowire scripts should be treated as partial or planned unless verified in the current repo state.

## Related pages

See [Headless Install and Autowire](Headless-Install-and-Autowire), [Provider Autowiring](Provider-Autowiring), and [Diagnostics and Health Checks](Diagnostics-and-Health-Checks).
