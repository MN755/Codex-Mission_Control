# Codex Mission Control

![Codex Mission Control logo](apps/desktop/assets/mission-control-logo.png)

Codex Mission Control is a local-first desktop app for running a manager-led coding workflow across multiple agent providers. It helps one user supervise planning, task routing, worker execution, diagnostics, and final handoff from a single interface.

## What it does

- Guides first-time users through setup, provider selection, and startup defaults
- Routes every launch through a real startup coordinator with health checks and retries
- Opens into a persistent home shell after startup instead of dropping straight into a single project page
- Builds project docs, interviews the user, creates a plan, and decomposes work into tasks
- Routes every project through a manager-centered workspace keyed by project ID
- Builds adaptive swarm plans instead of relying on one fixed worker roster
- Coordinates manager and worker agents while preventing overlapping writable paths
- Streams live orchestration events into the workspace shell over SSE
- Produces a final handoff with run instructions, tests, limitations, and follow-up work

## Startup model

Mission Control has two startup modes:

- `first_time`: shown only until setup is explicitly completed
- `regular`: used on normal launches after setup

Startup always routes through `/startup`, where the app checks:

- runtime paths
- database readiness
- settings and app state
- project storage
- backend route availability
- optional provider capabilities such as Codex CLI, login status, app-server, Ollama, and other adapters

If an optional provider check fails, Mission Control can continue in degraded mode. If required checks fail, the startup coordinator retries targeted checks up to three times, then generates a diagnostic report and routes to the startup error screen.

## First-time setup wizard

The first-time wizard walks through:

1. Welcome
2. Username
3. Provider
4. API or Login
5. Connect Accounts
6. Model / Runner Defaults
7. Finish

Important behavior:

- first-run state is stored in the local backend database, not browser localStorage
- setup does not reappear after ordinary code updates or version changes
- Codex via ChatGPT Login does not require an API key
- API-based providers are clearly marked as API-key-based
- raw API keys are not stored in Mission Control's SQLite database or diagnostics

## Supported providers

- `codex`
- `ollama`
- `openai_api`
- `anthropic_api`
- `xai_api`
- `claude_code`
- `custom`

Recommended default:

- `codex` via local ChatGPT-backed Codex CLI login

Other providers are supported when their local CLI, endpoint, or adapter is available. Model availability depends on the selected provider and the current local session.

## Launching the app

### Windows

PowerShell:

```powershell
.\scripts\start-mission-control.ps1
```

Double-click:

- `scripts/start-mission-control.bat`

Create a desktop shortcut:

```powershell
.\scripts\create-desktop-shortcut.ps1
```

### macOS or Linux

```bash
./scripts/start-mission-control.sh
```

All launcher entrypoints route the app through `/startup`, not directly to the dashboard.

## Development setup

### Requirements

- Python 3.10+
- Node.js 20+
- A supported local desktop webview backend

### Backend

```powershell
cd apps/server
python -m pip install -e .[dev]
python -m uvicorn main:app --app-dir src --reload
```

### Frontend

```powershell
cd apps/dashboard
npm install
npm run dev
```

### Browser fallback on Windows

```powershell
.\scripts\start-mission-control.ps1 -Mode web
```

## Diagnostics

Mission Control writes startup diagnostics to:

- source runs: `apps/server/.runtime/diagnostics/`
- packaged builds: the writable app-data runtime directory used by the desktop shell

Reports include:

- startup summary
- failed and degraded checks
- runtime path state
- database state
- settings and app-state state
- provider detection summaries
- recent startup errors
- recommended fixes

Diagnostics intentionally redact API keys, tokens, and sensitive environment variables.

## Resetting setup intentionally

Mission Control does not auto-reset first-run state. That is deliberate.

If you need to rerun setup in development:

1. Back up the runtime database.
2. Remove or reset the single app-profile record that stores `first_run_completed`.
3. Restart the app and allow `/startup` to route back into `/setup`.

There is no automatic destructive reset in the normal user flow by default.

## Project workflow

1. Start in the dashboard
2. Create a project from a general idea
3. Run the interview
4. Review and approve the plan
5. Review the adaptive swarm plan and approve it when required
6. Generate and assign tasks
7. Work inside the project workspace:
   - top action banner tells whether the user is needed
   - center manager chat is the only user-facing conversation surface
   - left sidebar shows worker agent status
   - the swarm strategy panel shows mode, risks, bottlenecks, and scaling controls
   - right sidebar shows the manager queue and project widgets
   - command and tool approvals are resolved inline above the manager input
8. Monitor workers, path reservations, and swarm scaling decisions
9. Review handoff output
10. Request follow-up changes through the manager

## Adaptive swarm planning

Mission Control no longer assumes one fixed roster like `Planner + Coder + Tester + Docs`.

Instead, the Manager creates a **Swarm Plan** per project or milestone. The plan decides:

- swarm mode
- recommended and maximum agent count
- specialized agent names and missions
- allowed and forbidden paths
- toolset and model policy
- spawn timing and retirement conditions
- coordination and path-conflict risk
- expected bottlenecks
- validation strategy

Supported optimization modes:

- `fastest_build`
- `balanced`
- `high_quality`
- `documentation_heavy`
- `research_planning`
- `massive_codebase`
- `manager_decides`

Project-level swarm preferences control:

- optimization mode
- swarm aggressiveness
- max agents
- approval threshold for large swarms
- dynamic spawning and retirement
- docs depth
- testing depth

Dry-run mode demonstrates different swarm behavior honestly. It can simulate adaptive spawn and retire decisions, but it does not claim that real provider-backed Codex agents were launched.

## Post-start command center

After startup completes, Mission Control uses two explicit shells:

- a **home shell** for `Dashboard`, `Archive`, `Handoffs`, `Models & Runners`, `Skills & Tools`, `Diagnostics`, and `Settings`
- a **project workspace shell** for `/projects/:projectId/:projectSlug?`

The home shell keeps navigation, runtime status, and quick project access stable. The project workspace shell keeps the manager conversation centered while workers, queue state, and widgets stay visible around it.

## Dashboard and archive

The dashboard is the post-start home base. It includes:

- a Recent Projects bar
- a New Project card
- a real persisted widget grid
- a bottom-right widget selector

Sidebar project behavior is intentionally constrained:

- up to 3 pinned or most-recent projects stay in the main sidebar
- older or archived projects overflow into `Archive`
- archive, pin, and restore actions remain tied to project IDs, not project names

Archive supports search, sorting, filtering, pinning, and archive or unarchive actions without destructive delete-by-default behavior.

## Widget system

Mission Control now uses a real widget system instead of a string list pretending to be layout state.

Core widget model:

- `WidgetDefinition`: seeded catalog entry with scope, category, size, and capability metadata
- `WidgetInstance`: persisted placement, order, size, collapsed state, and per-widget config
- `WidgetDataResponse`: scoped data payload with status, warnings, and honest empty states
- `AppEvent` plus project events: targeted SSE refresh instead of blunt full-page reloads

Supported scopes:

- `dashboard`
- `project`

Supported areas:

- dashboard: `dashboard_main`, `dashboard_right`, `dashboard_bottom`, `dashboard_custom`
- project: `project_right_sidebar`, `project_bottom`, `project_overview`, `project_custom`

This pass intentionally exposes the core areas first instead of pretending a full drag-and-drop builder is somehow the urgent problem:

- dashboard: `dashboard_main`, `dashboard_bottom`
- project: `project_right_sidebar`, `project_bottom`

Default dashboard widgets:

- `Needs Attention`
- `Active Builds`
- `Recent Handoffs`
- `Runner & Provider Status`
- `Swarm Budget Overview`
- `Project Health Overview`

Default project widgets:

- `Swarm Strategy`
- `Swarm Budget`
- `Agent Contracts`
- `Path Ownership Map`
- `Decision Ledger`
- `Project Health Score`
- `Validation Recipe`
- `Manager Assumptions`
- `Handoff Quality`

Empty widget areas use the exact in-product message:

`Select the plus symbol in the bottom-right corner to add customizable widgets!`

## Widgets vs Manager Chat vs tools

Mission Control now draws a hard boundary between summary panels, decisions, and execution. Amazing what happens when an app stops trying to do everything from every card.

Widgets are for:

- concise state summaries
- health and risk visibility
- swarm posture and ownership visibility
- model, sandbox, and tool-routing summaries
- handoff readiness and change-management summaries

Manager Chat is for:

- approvals
- manager questions
- recovery proposals
- assumption changes
- change-request triage
- swarm revision prompts

Tools stay in `Skills & Tools`:

- widgets can summarize tool routing and approval posture
- widgets do not execute web search, browser tests, deployments, or other built-in tools
- Manager Chat remains the place where tool approvals and follow-up decisions surface

## High-impact project widgets

Project widgets currently emphasize the parts of the workspace that actually change execution quality instead of ornamental dashboard filler:

- `Swarm Budget`: active agents, intensity, approval threshold, premium-model pressure, and dynamic-spawn pause state
- `Agent Contracts`: mission, boundaries, allowed tools, validation expectations, and completion shape per agent
- `Path Ownership Map`: active path locks, waiting work, and conflict risk instead of magical thinking about concurrent edits
- `Decision Ledger`: manager decisions, user approvals, assumptions, and reversible changes
- `Confidence Tracker`: low-confidence planning areas and unknowns by category
- `Failure Recovery`: recovery proposals without unsafe rollback theater
- `Agent Stuck Detection`: timeout, repeated-error, and repeated-approval signals
- `Merge / Review Gates`: required gates for code review, tests, docs, security, and handoff
- `Repo Intelligence`: safe filesystem scanning for frameworks, entry points, build commands, CI, and deployment config without running untrusted commands
- `Validation Recipe`: persisted validation steps and approval posture
- `Handoff Quality`: the expected output quality level and included sections
- `Change Request Mode`: follow-up requests and their manager triage state

## Project workspace model

Project routes use:

- `/projects/:projectId/:projectSlug?`

Important behavior:

- `projectId` is authoritative
- `projectSlug` is cosmetic
- missing or incorrect slugs are redirected to the canonical slug
- the app never loads a project by name alone

The workspace core loop is intentionally manager-led:

- the user talks only to the Manager AI
- follow-up questions are answered in structured cards
- command and tool approvals are recorded as project-scoped decisions
- worker activity is visible without exposing raw logs by default
- dry-run mode seeds a safe simulated question-and-approval loop so the UI can be exercised without live Codex execution

## Models, tools, diagnostics, and handoffs

Mission Control keeps these post-start pages separate so each surface stays focused:

- `Models & Runners`: project-specific provider, model, reasoning, sandbox, and approval settings
- `Skills & Tools`: local tool catalog with availability, risk, and permission policy
- `Diagnostics`: startup status, runtime status, saved reports, and retry actions
- `Handoffs`: completed project handoffs derived from real final reports

Important behavior:

- `Models & Runners` is project-scoped by design
- empty model values mean `use provider default`
- diagnostics reports are stored locally and redact secrets
- tool availability is honest about unsupported or not-yet-configured environments

## Runner modes

- `dry_run`: local simulation for demos and UI testing
- `cli`: provider CLI execution
- `app_server`: experimental Codex app-server path
- `auto`: choose the best supported live path and fall back safely

## Security posture

- local-first by default
- no required OpenAI API keys for the Codex login path
- no raw API keys stored in Mission Control state
- loopback-only backend by default
- sandbox and approval defaults remain conservative

More detail:

- [Architecture](docs/ARCHITECTURE.md)
- [Workflow](docs/WORKFLOW.md)
- [Provider Integration](docs/CODEX_INTEGRATION.md)
- [Security](docs/SECURITY.md)

## Current limits

- Codex app-server support remains experimental
- Provider capability depth varies by local CLI or adapter
- Packaged binaries are unsigned unless you add platform signing yourself
- Connected accounts in setup are honest placeholders unless you configure them separately
