# Mission Control Local Plugin Bundle

This is the repo-local Codex plugin bundle for Mission Control background orchestration.

What it includes:

- a provisional local plugin manifest
- MCP server wiring for the repo-local bridge package
- repo-local bridge and install/update skills
- the Codex prompt surface for Mission Control bridge workflows
- a presentation placeholder for approval-card capable clients

What it does not do:

- replace Mission Control Manager
- execute worker shell commands from MCP
- require API keys for the normal Codex login path

Use this bundle when you want Codex desktop chat to drive Mission Control without making the dashboard mandatory.

See:

- [../../../docs/CODEX_PLUGIN_MODE.md](../../../docs/CODEX_PLUGIN_MODE.md)
- [../../../docs/MCP_RESOURCES_PROMPTS.md](../../../docs/MCP_RESOURCES_PROMPTS.md)
- [../../../wiki-staging/Install-From-Codex.md](../../../wiki-staging/Install-From-Codex.md)
