# Optional Dashboard UI

The standalone Mission Control dashboard is currently optional and paused as a product priority.

It may remain in the repo as:

- a future observability surface
- a local operator console
- a separate app or package later

It is not required for normal Mission Control use from Codex chat.

## Current Rule

Headless Codex-native workflows are primary.

Do not spend current core-agent time on:

- dashboard UI
- project workspace UI
- widget UI
- sidebars
- settings pages
- visual polish
- React layout work
- frontend redesigns

## What The Dashboard Is For

If it is used later, the dashboard should be treated as:

- optional observability
- optional inspection of orchestration state
- optional operator tooling

It should not become a required dependency for:

- install
- attach
- orchestration
- approvals
- status
- diagnostics
- handoff

## Deferred UI Details

These details were moved out of the primary architecture and workflow docs so the repo stops centering the paused UI.

### Optional dashboard routes

- `/startup`
- `/setup`
- `/startup-error`
- `/dashboard`
- `/archive`
- `/handoffs`
- `/diagnostics`
- `/skills-tools`
- `/settings`
- `/models-runners`
- project-specific intake, interview, workspace, models, and handoff routes

### Optional widget model

- dashboard widgets are global summaries
- project widgets summarize project-scoped state
- widgets do not execute tools directly
- widget layout and placement are observability concerns, not core runtime requirements

### Optional project workspace layout

- top project action banner
- left worker agent sidebar
- center manager chat
- right manager queue and project widgets
- lower task board and activity log

### Optional archive behavior

- archived and overflow projects can live in `Archive`
- sidebar curation is an optional UI concern, not part of headless orchestration

## Related Docs

- [Architecture](ARCHITECTURE.md)
- [Workflow](WORKFLOW.md)
- [Headless UX](HEADLESS_UX.md)
