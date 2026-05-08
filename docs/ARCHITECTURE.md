# Architecture

Codex Mission Control is a local-only orchestration app with a desktop-first shell on top of the existing React + FastAPI stack.

## Main Pieces

- `apps/dashboard`
  - React + TypeScript + Vite
  - Six core screens: Launchpad, Intake, Interview, Plan Review, Build Monitor, Handoff
  - Uses REST for commands and SSE for live updates
- `apps/desktop`
  - Cross-platform Python desktop shell
  - Starts the FastAPI app locally and opens the built dashboard inside a native webview
  - Is packaging-aware for frozen Windows, macOS, and Linux builds
  - Owns the shared thought-cloud `>_` app icon assets used by the desktop shell and repo branding
- `apps/server`
  - FastAPI app
  - SQLite persistence via SQLAlchemy
  - Mission-control services for docs, interview, planning, task routing, and runners
- `workspace`
  - Local runtime data
  - Demo workspace placeholder and user-selected workspace targets
- Runtime storage
  - Source checkout mode uses `apps/server/.runtime`
  - Packaged mode uses the user's local app-data directory
  - Stores SQLite, logs, launcher metadata, and managed worktree directories
- `.codex/skills/mission-control-manager`
  - Local manager skill prompt for Codex-driven manager behavior
- `.github/workflows/package-desktop.yml`
  - Cross-platform build pipeline for Windows `.exe`, macOS `.app`, and Linux packaged artifacts

## Data Model

- `Project`: one orchestration target
- `InterviewSession` and `InterviewQuestion`: planning interview state
- `Plan`: versioned plan artifact
- `Agent`: manager or worker
- `Task`: scoped work unit with milestone, role, dependencies, success criteria, and path hints
- `AgentRun`: individual runner invocation with stdout/stderr/event logs plus parsed worker report
- `PathReservation`: explicit path ownership records for conflict prevention
- `ProjectEvent`: persistent event timeline for the live monitor

## Execution Model

1. User creates a project and picks a workspace path.
2. User authenticates with local Codex via ChatGPT sign-in, device-code flow, or an optional API-key login.
3. Backend writes local project docs to `<workspace>/mission-control/`.
4. Interview answers refine the plan.
5. Plan approval creates worker agents and milestone-based tasks.
6. A runner starts worker turns, reservations are acquired, and the backend persists events and completion reports.
7. The manager ingests worker reports, decides the next action, and either assigns follow-up work, requests a fix, waits, or escalates.
8. The frontend listens on SSE and refreshes project state as events arrive.

## Isolation

- Git workspaces are prepared for per-agent worktree use under `apps/server/.runtime/worktrees/`.
- Non-git workspaces use explicit `PathReservation` records and cached agent lock state to allow only non-overlapping writers at the same time.
- The manager writes project docs to a visible `mission-control/` folder inside the selected workspace.

## Packaging Model

- The packaged desktop app bundles:
  - the Python desktop shell
  - the FastAPI backend modules
  - the built React frontend assets
  - launcher config defaults
- Windows packaging targets a standalone `.exe`.
- macOS packaging targets a `.app` bundle.
- Linux packaging targets a portable bundle and can emit an AppImage when `appimagetool` is available.
- Packaged builds do not depend on a source checkout layout at runtime.
