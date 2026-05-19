# Codex Plugin Install

Mission Control can be used from the Codex desktop app as a bridge-based orchestration workflow instead of only through the Mission Control dashboard.

## What this integration does

This integration packages the user-facing pieces needed for Codex to talk to Mission Control:

- Codex-facing skills
- reusable prompt templates
- a safe-summary MCP resource catalog
- a plugin packaging skeleton
- an MCP server wiring example
- operator documentation for approvals and status flow

What it does not do:

- replace the Mission Control Manager AI
- implement the daemon or backend orchestration layer by itself
- make the app-server mandatory
- require OpenAI API keys for the normal Codex login path

## Codex chat bridge vs Mission Control Manager

Keep these roles separate:

- Codex chat is the bridge surface. It relays user intent, polls status, surfaces approvals, and retrieves handoff output.
- Mission Control Manager is the orchestrator. It decides swarm structure, worker routing, recovery actions, and final execution sequencing.

If Codex chat starts freelancing as the manager while Mission Control mode is active, the whole integration becomes confused fast. That is a technical term.

## Prerequisites

- Mission Control backend or daemon is running locally
- Codex desktop app is installed and usable
- A Mission Control MCP bridge or equivalent local connector is available

## Start Mission Control

### Windows

```powershell
.\scripts\start-mission-control-daemon.ps1
```

### macOS or Linux

```bash
./scripts/start-mission-control-daemon.sh
```

The MCP bridge can auto-start this daemon when needed, but starting it explicitly is still the cleanest way to debug local connectivity.

## Configure the MCP server

Use one of the repo-local examples at:

- [plugins/mission-control/mcp/mission-control-mcp.example.json](../plugins/mission-control/mcp/mission-control-mcp.example.json)
- [.codex/plugins/mission-control/mcp/mission-control-mcp.local.json](../.codex/plugins/mission-control/mcp/mission-control-mcp.local.json)
- Resource catalog: [plugins/mission-control/mcp/resources.json](../plugins/mission-control/mcp/resources.json)

Expected shape:

1. Point Codex to the local Mission Control MCP bridge command.
2. Keep the MCP bridge running against localhost only.
3. Reload Codex MCP configuration.

The bridge probes `GET /api/health`, auto-starts the daemon when needed, reads the local token from runtime state, and then calls the token-guarded bridge endpoints. It does not run worker commands itself because that would be a ridiculous security model.

## Install the plugin and skills

Current state:

- `plugins/mission-control/` contains the package skeleton.
- `.codex/plugins/mission-control/` contains a repo-local Codex plugin bundle with MCP config and bridge docs.
- `.codex/skills/` contains compatible local skill copies for direct Codex skill loading where supported.

Fastest repo-local install on Windows:

```powershell
.\scripts\install-mission-control-plugin.ps1 -HeadlessOnly
```

Suggested install flow:

1. Copy or link `.codex/plugins/mission-control/` into the Codex plugin location if your Codex install does not read repo-local plugin bundles directly.
2. Copy or link these skill folders into the Codex skills directory if plugin-bundled skill discovery is not available yet:
   - `.codex/skills/mission-control-orchestrate`
   - `.codex/skills/mission-control-import-codebase`
   - `.codex/skills/mission-control-status`
   - `.codex/skills/mission-control-approve`
   - `.codex/skills/mission-control-handoff`
   - `.codex/skills/mission-control-debug`
   - `.codex/skills/mission-control-swarm`
   - `.codex/skills/mission-control-safe-mode`
   - `.codex/skills/mission-control-resume`
   - `.codex/skills/mission-control-agents-md`
3. Review [docs/CODEX_CHAT_MODE.md](./CODEX_CHAT_MODE.md), [docs/MISSION_CONTROL_SKILLS.md](./MISSION_CONTROL_SKILLS.md), and [docs/MCP_RESOURCES_PROMPTS.md](./MCP_RESOURCES_PROMPTS.md).
4. Reload Codex configuration.

## Manual fallback

If plugin installation support is incomplete, use the prompt templates directly:

- [attach-current-workspace](../plugins/mission-control/prompts/attach-current-workspace.md)
- [use-mission-control-for-this-repo](../plugins/mission-control/prompts/use-mission-control-for-this-repo.md)
- [import-existing-codebase](../plugins/mission-control/prompts/import-existing-codebase.md)
- [start-manager-led-task](../plugins/mission-control/prompts/start-manager-led-task.md)
- [continue-orchestration](../plugins/mission-control/prompts/continue-orchestration.md)
- [show-pending-approvals](../plugins/mission-control/prompts/show-pending-approvals.md)
- [answer-pending-approval](../plugins/mission-control/prompts/answer-pending-approval.md)
- [review-latest-handoff](../plugins/mission-control/prompts/review-latest-handoff.md)
- [debug-failed-orchestration](../plugins/mission-control/prompts/debug-failed-orchestration.md)
- [pause-orchestration](../plugins/mission-control/prompts/pause-orchestration.md)
- [resume-orchestration](../plugins/mission-control/prompts/resume-orchestration.md)
- [explain-current-swarm](../plugins/mission-control/prompts/explain-current-swarm.md)
- [switch-swarm-strategy](../plugins/mission-control/prompts/switch-swarm-strategy.md)
- [enable-safe-mode](../plugins/mission-control/prompts/enable-safe-mode.md)
- [generate-agents-md-proposal](../plugins/mission-control/prompts/generate-agents-md-proposal.md)

In that mode, Codex still acts as the bridge and Mission Control still acts as the manager.

For the full catalog and the safety/redaction rules, see [docs/MCP_RESOURCES_PROMPTS.md](./MCP_RESOURCES_PROMPTS.md).

For the grouped Codex skill library, see [docs/MISSION_CONTROL_SKILL_LIBRARY.md](./MISSION_CONTROL_SKILL_LIBRARY.md).

## Example Codex prompts

- `Use mission-control-orchestrate for this repo.`
- `Use mission-control-import-codebase on this workspace before edits.`
- `Use mission-control-status and tell me what is blocked.`
- `Use mission-control-approve for the pending low-risk build command.`
- `Use mission-control-resume to continue the last run.`
- `Use mission-control-agents-md and show me the proposal first.`

## Typical user flow

1. User asks Codex to use Mission Control.
2. Codex attaches the workspace through Mission Control.
3. The bridge reuses an active orchestration for that workspace when one already exists.
4. Mission Control decides whether this is a new project or an existing codebase.
5. Existing repos get a read-only understanding step first.
6. Mission Control Manager runs orchestration in the background.
7. Codex polls status and relays pending decisions.
8. Mission Control returns handoff and evidence.
9. Codex summarizes the result to the user.

## Troubleshooting

### Mission Control is not reachable

- Confirm the local backend or daemon is running.
- Confirm the MCP bridge is pointed at the correct local base URL.
- Confirm Codex reloaded the MCP config after changes.

### Codex can see the skill but not the tools

- Skill loading and MCP server loading are separate.
- Confirm both the skill path and the MCP server config are installed.

### Approvals look like plain text instead of cards

- The custom UI is optional.
- Fall back to the text format in [docs/CODEX_APPROVAL_UI.md](./CODEX_APPROVAL_UI.md).

### Existing repo import starts editing too early

- The intended flow is read-only understanding first.
- If the bridge skips that step, treat it as a bug, not as “close enough.”
