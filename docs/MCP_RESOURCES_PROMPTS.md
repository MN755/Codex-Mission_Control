# MCP Resources And Prompts

Mission Control's headless Codex integration is built from two reusable layers:

- MCP resources for read-only safe context
- MCP prompts for reusable workflow instructions

The canonical machine-readable catalogs live here:

- [plugins/mission-control/mcp/resources.json](../plugins/mission-control/mcp/resources.json)
- [plugins/mission-control/mcp/prompts.json](../plugins/mission-control/mcp/prompts.json)

## Resource Rules

- Resources are read-only.
- Resources must not run commands.
- Resources must not expose secrets.
- Resources should return compact safe summaries by default.

## Resource Catalog

### Project-scoped orchestration resources

- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events`

### Project resources

- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/workspace-tooling`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/webwright`
- `mission-control://projects/{project_id}/nvidia-dynamo`
- `mission-control://projects/{project_id}/nvidia-nim`
- `mission-control://projects/{project_id}/nvidia-aiq`
- `mission-control://projects/{project_id}/nvidia-gpu-diagnostics`
- `mission-control://projects/{project_id}/nvidia-local-runtime`
- `mission-control://projects/{project_id}/nvidia-validation-plan`
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/risk-register`
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/path-locks`
- `mission-control://projects/{project_id}/operator-snapshot`
- `mission-control://projects/{project_id}/instincts`
- `mission-control://projects/{project_id}/verification-brief`

## Prompt Rules

- Prompts are reusable workflows, not manager replacements.
- Prompts should tell Codex which Mission Control tools and resources to use.
- Prompts should preserve the bridge role and approval boundaries.

## Prompt Catalog

- `attach-current-workspace`
- `use-mission-control-for-this-repo`
- `import-existing-codebase`
- `start-manager-led-task`
- `continue-orchestration`
- `show-pending-approvals`
- `answer-pending-approval`
- `review-latest-handoff`
- `debug-failed-orchestration`
- `use-webwright-for-browser-task`
- `pause-orchestration`
- `resume-orchestration`
- `explain-current-swarm`
- `switch-swarm-strategy`
- `enable-safe-mode`
- `generate-agents-md-proposal`
- `install-from-github`
- `autowire-providers`
- `ask-manager-for-plan`

## Prompt To Tool Pattern

Typical prompt flow:

1. Use a prompt to choose the bridge workflow.
2. Call the required Mission Control tools.
3. Read the required safe resources.
4. Summarize the result in Codex chat.
5. Stop for user input when Mission Control raises a decision.

## Approval Relay Basics

The prompt catalog assumes that pending decisions are always surfaced in Codex chat before they are answered.

That means:

- read pending decisions
- render them clearly
- ask the user
- send the answer back through the decision tool

No shortcuts. Those are how permission bugs breed.

## AGENTS.md And Existing Codebases

The prompt catalog also covers:

- read-only import-first workflows for existing repos
- `AGENTS.md` proposal generation through Mission Control context
- safe-mode workflows for stricter approvals and tool posture
- install and autowire workflows for headless bootstrap and local-first provider setup

## Dashboard Scope

The dashboard is optional and not part of this focus.

These resources and prompts are designed to make Mission Control usable from Codex chat alone.
