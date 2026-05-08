# Architecture

Codex Mission Control is a local-first orchestration system built as a desktop shell over a React frontend and a FastAPI backend. The desktop shell is the primary product surface; the browser mode exists as a fallback for development and recovery.

## Design goals

- Keep all orchestration local by default
- Reuse existing provider CLI sessions instead of rebuilding auth
- Give the user one manager interface instead of many worker conversations
- Coordinate worker tasks without overlapping writes
- Stay small enough to run on a normal workstation

## Top-level components

## Desktop shell

- Lives in `apps/desktop`
- Starts the backend locally and opens the UI in a native webview
- Provides the app icon, packaged entrypoints, and frozen-runtime behavior
- Keeps the product usable as a standalone desktop app rather than a hosted web service

## Frontend

- Lives in `apps/dashboard`
- React + TypeScript + Vite
- Main product surfaces:
  - startup and auth
  - project intake
  - interview
  - plan review
  - build monitor
  - handoff
- Uses REST for commands and SSE for live updates

## Backend

- Lives in `apps/server`
- FastAPI + SQLAlchemy + SQLite
- Owns orchestration state, provider resolution, manager logic, task routing, and event streaming

## Runtime and workspaces

- Source runs store app state under `apps/server/.runtime`
- Packaged builds store writable runtime state under the user’s local app-data directory
- User project docs are written into `<workspace>/mission-control/`

## Data model

- `Project`: the top-level orchestration record
- `ProjectSettings`: provider, runner, model, reasoning, and approval settings per project
- `InterviewSession` and `InterviewQuestion`: planning interview state
- `Plan`: versioned plan output
- `Agent`: manager or worker identity plus current activity
- `Task`: milestone-based work unit with scope, validation, dependencies, and path hints
- `AgentRun`: a concrete provider invocation and its logs
- `PathReservation`: path ownership records used to prevent overlapping edits
- `ProjectEvent`: durable event stream for the build monitor

## Execution flow

1. The user creates a project.
2. Mission Control creates initial docs and a reserved manager agent.
3. The interview refines requirements.
4. The manager produces a versioned plan.
5. Approved plans are decomposed into milestone-based tasks.
6. Eligible tasks are assigned to workers through the selected runner.
7. Path reservations are acquired before write-capable work starts.
8. Worker reports are parsed and fed back into the manager.
9. The manager assigns follow-up work, requests fixes, waits, or escalates.
10. When required work is complete, the manager generates a handoff.

## Provider model

Mission Control separates orchestration from provider execution.

- The backend decides what should happen next.
- The runner layer decides how that action is executed against a local provider.
- The manager can run deterministically or through a provider-backed path.

This allows the same workflow to operate across:

- Codex CLI
- Codex app-server (experimental)
- Claude Code CLI
- External local adapters

## Concurrency and file safety

Mission Control does not assume workers can safely edit the same files.

- Git-backed workspaces are prepared for isolated worktree-style execution
- Non-git workspaces use `PathReservation` records
- Tasks that conflict with active reservations move to `waiting_on_paths`
- Reservation state is visible in the build monitor

## Packaging model

The packaging pipeline freezes the desktop shell and bundles:

- desktop Python entrypoint
- backend modules
- built frontend assets
- launcher defaults
- generated icon assets

Targets:

- Windows `.exe`
- macOS `.app`
- Linux portable bundle and optional AppImage

## Why the architecture is split this way

The project intentionally keeps orchestration logic in the backend and presentation logic in the frontend so the system can:

- stay testable without the GUI
- preserve desktop packaging flexibility
- support multiple providers behind one task model
- fall back gracefully when live manager execution is unavailable
