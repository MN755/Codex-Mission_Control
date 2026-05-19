# Current Direction

Codex Mission Control is currently headless-first.

Mission Control should be treated as a background orchestration platform for Codex where:

- Codex chat is the user-facing surface
- Mission Control daemon owns orchestration
- MCP tools, MCP resources, MCP prompts, plugin packaging, and skills are the primary interface
- the Manager AI lives inside Mission Control
- the Codex chat agent is only a bridge
- worker runners stay behind Mission Control approvals and runner policy

The standalone dashboard and app UI are paused, optional, and secondary. They can remain in the repo, but they are not the current product center. If a standalone UI grows again later, it can move into its own app or package without changing the headless core.

Agents should not work on standalone UI unless the user explicitly instructs them to do UI work.

## Do Not Work On

- dashboard UI
- project workspace UI
- widget UI
- sidebars
- app settings UI
- visual polish
- React layout changes
- frontend redesigns

## Work On Instead

- daemon
- MCP bridge
- plugin package
- skills
- prompt templates
- resources
- tool schemas
- pending decision relay
- bridge-safe markdown
- runner registry
- headless bootstrap
- diagnostics
- security
- tests
- docs

## Product Positioning

Mission Control should be described as:

"A headless/background orchestration platform for Codex where a Codex chat acts as the bridge to a Manager AI that coordinates many background worker agents."

That positioning is the current source of truth for docs, prompts, repo guidance, and future implementation choices.
