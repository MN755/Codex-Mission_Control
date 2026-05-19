# AGENTS.md

## Current Direction

Codex Mission Control is currently headless-first.

- Codex chat is the user-facing bridge
- Mission Control daemon owns orchestration
- the Manager AI lives inside Mission Control
- worker runners remain behind Mission Control approvals
- MCP tools/resources/prompts, plugin packaging, and skills are the primary interface
- the standalone dashboard is optional, paused, and not the current product center

The Codex chat agent is not the Manager AI. It is the bridge between the user and Mission Control.

## UI Guardrail

Do not edit app/dashboard/frontend UI files unless the user explicitly asks for UI work.

This includes:

- `apps/dashboard/**`
- frontend UI pages
- widget components
- CSS
- design system files

Exception:

- if frontend tests break because of backend or bridge changes, make only the minimum compatibility fix required to restore test/build health

## Work On Instead

Prefer work in:

- daemon/runtime behavior
- MCP bridge
- plugin packaging
- skills and prompts
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

## Headless-First Architecture

The primary runtime path is:

`Codex chat -> Mission Control skill/prompt -> MCP tools/resources/prompts -> Mission Control daemon -> Manager AI -> worker runners`

The standalone UI is optional and should not be required for normal use.

## Coding And Testing Commands

Backend setup:

```powershell
cd apps/server
python -m pip install -e .[dev]
```

Backend tests:

```powershell
cd apps/server
python -m pytest
```

Backend daemon:

```powershell
.\scripts\start-mission-control-daemon.ps1
```

Optional dashboard build:

```powershell
cd apps/dashboard
npm install
npm run build
```

Use dashboard commands only when explicitly assigned UI work or when a backend change requires a minimal compatibility check.

## Safety Rules

- do not fake orchestration, approvals, handoffs, test results, or runner behavior
- do not bypass Mission Control approvals
- do not expose secrets in docs, prompts, handoffs, diagnostics, or summaries
- do not claim tests passed unless they actually passed
- do not quietly widen scope from headless/core work into standalone UI work
- do not rewrite unrelated in-flight work from other agents

## Docs Expectations

- keep headless Codex-native workflows primary
- describe Codex chat as the bridge, not the Manager
- describe the dashboard as optional when it appears in docs
- prefer accurate command and payload examples over aspirational UI descriptions
- keep examples redacted and evidence-based

## Completion Report Format

When finishing a task, report:

1. summary of changes
2. files changed
3. validation run
4. known gaps or follow-up risk

If a task changes behavior but validation was not run, state that explicitly.

## Conflict Avoidance

- check ownership boundaries in the user request before editing shared areas
- prefer isolated edits and narrow write scopes
- if another agent is clearly working on a file family, avoid it unless required
- do not expand into dashboard/UI work as a side quest during headless/core tasks
