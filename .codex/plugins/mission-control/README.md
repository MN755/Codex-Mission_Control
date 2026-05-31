# Mission Control Codex Plugin Package

This folder is the repo plugin bundle for using Codex Mission Control from Codex desktop through a thin MCP bridge.

What is here:

- `plugin.json`: canonical bundle manifest
- `.codex-plugin/plugin.json`: Codex plugin metadata
- `.claude-plugin/plugin.json`: Claude Code plugin metadata
- `skills/`: Codex-facing bridge skills
- `commands/`: Claude Code slash-command workflows
- `agents/`: Claude Code worker archetypes that map to Mission Control lanes
- `prompts/`: reusable Mission Control bridge prompts
- `mcp/mission-control-mcp.example.json`: local MCP server wiring example
- `mcp/resources.json`: safe-summary MCP resource catalog
- `mcp/prompts.json`: reusable MCP prompt catalog
- `templates/`: bridge-safe markdown response templates
- `assets/icon.svg`: SVG icon asset for host compatibility
- `assets/mission-control-logo.png`: transparent PNG logo for README and plugin surfaces that prefer raster artwork

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
- Claude Code commands and agents are convenience surfaces; they still route work through Mission Control instead of creating an uncontrolled second manager.

Built-in capability packs:

- Agent Skills-style packaging: skill creation, metadata, host compatibility, and package validation.
- Code understanding: graph-style codebase maps, grounded Q&A, diff impact, domain maps, onboarding tours, and docs knowledge maps.
- Agent engineering: runnable-chain design, retrieval/RAG design, tool registries, evals/observability, memory/state policy, and graph workflows.
- Practical work surfaces: MCP building, webapp testing, document workflows, brand communications, and creative web artifacts.
- Browser-agent companion support: project-scoped Webwright readiness, safe install guidance, and browser-task routing through Mission Control instead of random chat improvisation.

See [docs/CODEX_PLUGIN_INSTALL.md](../../docs/CODEX_PLUGIN_INSTALL.md) for setup, [docs/CODEX_PLUGIN_MODE.md](../../docs/CODEX_PLUGIN_MODE.md) for bridge behavior, and [docs/MCP_SECURITY.md](../../docs/MCP_SECURITY.md) for localhost token and redaction rules.
