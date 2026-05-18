# Workflow

This document describes the user-visible workflow from launch through handoff.

## 1. Startup

Every app launch routes through `/startup`.

The startup coordinator decides between:

- `first_time`
- `regular`
- `degraded`
- `error`

Required startup checks:

- runtime paths
- database
- settings
- project storage
- backend route availability

Optional checks:

- Codex CLI and login state
- Codex app-server
- Claude Code CLI
- Ollama endpoint
- API-provider environment/session hints
- custom adapter presence
- external account placeholders such as GitHub, Vercel, and Notion

If a required check fails, Mission Control retries targeted startup work up to three times. If only optional checks fail, the app can continue in degraded mode.

## 2. First-time setup

First-time setup is shown only until the local app-state record is marked complete.

The setup wizard steps are:

1. Welcome
2. Username
3. Provider
4. API or Login
5. Connect Accounts
6. Model / Runner Defaults
7. Finish

Setup completion persists:

- username
- selected provider
- auth mode
- connected-account summary
- default runner mode
- model defaults
- sandbox and approval defaults

Ordinary updates do not reset setup.

## 3. Dashboard

Once setup is complete, `/startup` routes to `/dashboard`.

The dashboard is the post-start landing surface and includes:

- recent projects
- a new-project entry point
- degraded-mode warnings when relevant
- a real widget grid with persistent instances

Dashboard navigation rules:

- up to 3 pinned or most-recent projects stay in the sidebar
- overflow or archived projects move to `Archive`
- the widget selector is intentionally simple and local-first
- dashboard widgets are global summaries, not execution surfaces

Default dashboard widgets include:

- `Needs Attention`
- `Active Builds`
- `Recent Handoffs`
- `Runner & Provider Status`
- `Swarm Budget Overview`
- `Project Health Overview`

## 4. Project intake

The user creates a project from a general idea.

Mission Control stores:

- project metadata
- provider and runner defaults
- a reserved manager agent
- local project docs under `<workspace>/mission-control/`

No coding should begin at intake time.

## 5. Interview

The interview sharpens scope before execution.

- the user chooses a question budget from 0 to 500
- the budget is a cap, not a quota
- the manager analyzes the project idea, docs, provider settings, runner/tool availability, and prior answers before asking anything
- questions are generated in small adaptive batches, usually 3 to 5 at a time
- each question is multiple choice and includes why it is being asked, category, impact, and the decision it affects
- the manager can stop early when enough information exists
- answers and project understanding are stored locally
- deterministic fallback still exists for dry-run, tests, and provider failures, but it is labeled honestly as fallback generation

Interview state now persists:

- question budget
- questions asked
- questions remaining
- manager confidence by category
- known facts
- unknowns
- assumptions
- stop reason and stopped-early state

## 6. Plan review

The manager produces a reviewable plan with:

- refined summary
- MVP scope
- milestones
- task structure
- agent roster
- validation approach
- risks
- definition of done

The user can approve the plan or redirect it.

Plan review can now also preview swarm posture through widget-backed summaries:

- recommended agent count
- specialized roster
- missions and bottlenecks
- risk notes
- approval thresholds

## 7. Swarm planning

Before or during a milestone, the manager can create an adaptive swarm plan instead of forcing one static worker roster onto every project.

Swarm planning inputs include:

- project idea and current phase
- repo shape and docs
- interview understanding
- provider and runner settings
- tool availability
- swarm preferences such as optimization mode, aggressiveness, docs depth, and testing depth

Swarm planning outputs include:

- swarm mode
- recommended agent count
- specialized agent names and missions
- path ownership and forbidden areas
- tool/model policy
- spawn timing and retirement conditions
- coordination and path-conflict risk
- expected bottlenecks
- validation strategy

Mission Control supports these swarm modes:

- `fastest_build`
- `balanced`
- `high_quality`
- `documentation_heavy`
- `research_planning`
- `massive_codebase`
- `manager_decides`

The manager is expected to choose the largest useful swarm, not the largest possible swarm. Large swarms can require user approval when they exceed the project threshold.

## 8. Task generation

After plan approval, Mission Control decomposes work into milestone-based tasks.

Task generation rules:

- milestone 1 should create a runnable vertical slice
- later milestones add polish, integrations, and deeper validation
- each task includes scope, allowed paths, forbidden paths, dependencies, validation steps, and success criteria

## 9. Project workspace

The project workspace is now the main execution surface.

Canonical route:

- `/projects/:projectId/:projectSlug?`

Route safety rules:

- `projectId` is the source of truth
- `projectSlug` is cosmetic
- wrong or missing slugs are redirected to the canonical slug
- Mission Control never loads a project by name alone

Workspace layout:

- top project action banner
- left worker agent sidebar
- center manager chat
- right manager queue and project widgets
- lower built-in task board and activity log

The workspace also exposes a swarm strategy view so the user can understand:

- which swarm mode the manager chose
- how many agents are active vs allowed
- current bottlenecks
- coordination and path-conflict risk
- pending scale-up or scale-down decisions
- whether dynamic spawning or retirement is enabled

The user talks only to the manager. Workers do not open separate user chats.

Default project widgets include:

- `Swarm Strategy`
- `Swarm Budget`
- `Agent Contracts`
- `Path Ownership Map`
- `Decision Ledger`
- `Project Health Score`
- `Validation Recipe`
- `Manager Assumptions`
- `Handoff Quality`

Other project widgets can be added as needed for:

- confidence tracking
- failure recovery
- stuck-agent detection
- review gates
- model policy
- tool routing policy
- sandbox profiles
- repo intelligence
- handoff progress
- change requests

## 10. Archive and overflow

Archive exists so the main sidebar stays focused.

Archive behavior:

- shows archived projects
- shows non-sidebar overflow projects
- supports search, sorting, and status filtering
- supports pin, archive, and unarchive actions

Archive is organizational, not destructive.

## 11. Manager loop

The manager loop is designed to answer one question quickly:

- does the user need to do anything right now?

The action banner derives that state from:

- pending manager questions
- pending command or tool approvals
- blocked tasks
- degraded runner state
- handoff readiness

Manager questions:

- use structured options instead of freeform text
- can auto-decide only for low or medium impact
- log auto-decisions as manager assumptions

Approvals:

- are project-scoped
- are recorded inline above the manager input
- are logged as manager-visible decisions
- do not show raw logs by default

Manager queue entries can now include swarm decisions such as:

- spawn a new docs specialist after backend stabilizes
- retire a research agent after architecture is settled
- add another test or debug agent after repeated failures
- scale down idle implementation agents once review gates take over

Widget boundary rules:

- widgets summarize state and point to next actions
- Manager Chat owns actual decisions, approvals, and recovery choices
- built-in tools stay in `Skills & Tools`
- widgets can summarize tool routing and approval posture, but they do not execute tools directly

## 12. App settings and project settings

Mission Control separates app-level preferences from project-level runtime controls.

Project settings can now include swarm preferences such as:

- optimization mode
- swarm aggressiveness
- max agents
- approval threshold above a configured agent count
- dynamic spawn and retirement toggles
- docs depth
- testing depth

Widget instances also persist lightweight layout controls:

- area
- order
- size
- collapsed state
- enabled state

App-wide settings include:

- display name
- theme
- startup behavior
- notification preferences
- dashboard widget preferences

Project-specific settings live under `Models & Runners` and include:

- manager model
- default worker model
- role-based overrides
- runner mode
- sandbox mode
- approval policy

## 12. Skills, tools, and diagnostics

The post-start command center includes dedicated pages for:

- `Skills & Tools`
- `Diagnostics`
- `Handoffs`

These pages expose:

- honest tool availability and permission policy
- startup and runtime health summaries
- saved diagnostic reports
- completed handoffs derived from final reports

## 13. Real-time behavior

Workspace state streams over SSE.

Key live updates include:

- manager message creation
- question creation and resolution
- approval creation and resolution
- agent status changes
- task updates
- manager queue updates

## 14. Handoff

Mission Control generates a handoff only after required work is complete or explicitly deferred.

The handoff includes:

- what was built
- how to run it
- how to use it
- tests and builds recorded
- limitations
- remaining risks
- suggested next improvements

## 15. Diagnostics and recovery

If startup or provider checks fail, the app can:

- continue in degraded mode when core services are still healthy
- generate a diagnostic report
- expose the diagnostics folder
- retry startup without destructive reset behavior

Diagnostics for source runs are saved under `apps/server/.runtime/diagnostics/`.
