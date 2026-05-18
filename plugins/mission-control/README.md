# Mission Control Codex Plugin Package

This folder is the repo plugin bundle for using Codex Mission Control from Codex desktop through a thin MCP bridge.

What is here:

- `plugin.json`: provisional bundle manifest
- `skills/`: Codex-facing bridge skills
- `prompts/`: reusable Mission Control bridge prompts
- `mcp/mission-control-mcp.example.json`: local MCP server wiring example
- `mcp/resources.json`: safe-summary MCP resource catalog
- `mcp/prompts.json`: reusable MCP prompt catalog
- `templates/`: bridge-safe markdown response templates
- `assets/icon.svg`: placeholder icon asset

What is not here:

- a replacement for the Mission Control daemon
- a separate manager brain living inside Codex chat
- raw shell execution hooks from the MCP layer
- secret-bearing logs or full transcripts

Bridge boundaries:

- Codex chat is the user-facing relay.
- Mission Control Manager remains the orchestration authority.
- The MCP server talks to the localhost daemon only.
- The daemon owns orchestration state, approvals, and worker coordination.
- The MCP bridge can auto-start the local daemon when it is missing, because returning a README instead of doing the obvious would be pathetic.

See [docs/CODEX_PLUGIN_INSTALL.md](../../docs/CODEX_PLUGIN_INSTALL.md) for setup, [docs/CODEX_PLUGIN_MODE.md](../../docs/CODEX_PLUGIN_MODE.md) for bridge behavior, and [docs/MCP_SECURITY.md](../../docs/MCP_SECURITY.md) for localhost token and redaction rules.
