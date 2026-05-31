# Mission Control Local Plugin Bundle

This is the repo-local Codex plugin bundle for Mission Control background orchestration.

What it includes:

- a repo-local plugin manifest that mirrors the canonical Mission Control prompt and resource catalogs
- MCP server wiring for the repo-local bridge package
- a bridge skill entrypoint plus the synced prompt bundle
- local MCP prompt and resource catalogs for offline repo checks
- a presentation placeholder for approval-card capable clients

What it does not do:

- replace Mission Control Manager
- execute worker shell commands from MCP
- require API keys for the normal Codex login path

Use this bundle when you want Codex desktop chat to drive Mission Control without making the dashboard mandatory.

See:

- [../../../docs/CODEX_PLUGIN_MODE.md](../../../docs/CODEX_PLUGIN_MODE.md)
- [../../../docs/MCP_PLUGIN_BRIDGE.md](../../../docs/MCP_PLUGIN_BRIDGE.md)
- [../../../docs/SECURITY.md](../../../docs/SECURITY.md)
- [../../../docs/CODEX_PLUGIN_INSTALL.md](../../../docs/CODEX_PLUGIN_INSTALL.md)
- [../../../docs/MISSION_CONTROL_SKILL_LIBRARY.md](../../../docs/MISSION_CONTROL_SKILL_LIBRARY.md)
