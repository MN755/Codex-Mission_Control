# Workflow

## 0. Launch

- Start everything with `.\scripts\start-mission-control.ps1` from the repo root.
- Or double-click `scripts/start-mission-control.bat` on Windows.
- On macOS and Linux, use `./scripts/start-mission-control.sh`.
- Use `.\scripts\create-desktop-shortcut.ps1` once if you want a desktop shortcut.
- The launcher now prefers the standalone desktop shell first.
- A browser-backed web mode still exists as an explicit fallback.
- For redistributable desktop artifacts, build with `.\scripts\package-desktop.ps1` on Windows or `./scripts/package-desktop.sh` on macOS/Linux.
- The GitHub Actions workflow can build all three OS targets after the repo is published.

## 1. Intake

- User enters a project name, idea, workspace path, runner mode, and manager mode.
- Backend creates the project and reserved manager agent.
- Backend writes local docs to `<workspace>/mission-control/`.
- Each project gets its own settings row for model selection, reasoning effort, runner mode, sandbox mode, approval policy, and role-based worker overrides.

## 2. Interview

- User picks 6, 20, or 50 questions.
- The UI presents one question at a time.
- Answers are persisted and shown in history.

## 3. Plan Review

- Backend generates a versioned plan.
- User can approve or ask for a directional revision.
- Revision actions create a new plan version.

## 4. Build Monitor

- Approval creates worker agents and an initial milestone-based task set.
- Managed worker sandboxes are created under `apps/server/.runtime/worktrees/` when isolation is needed.
- The backend starts compatible idle agents.
- Each manager or worker run resolves its effective model and reasoning from project settings:
  - manager uses manager model first
  - workers use role override first, then default worker model
  - empty values mean `use Codex default`
- When a task starts, its allowed paths are reserved.
- If another queued task overlaps those paths, it moves to `waiting_on_paths`.
- When a worker finishes, the backend stores the completion report, asks the manager for the next action, and routes follow-up work automatically.
- Events stream into the frontend over SSE.
- User can start, pause, stop, or inspect logs without talking to workers directly.

## 5. Handoff

- When all tracked tasks reach a done state, the manager generates a structured handoff and the project moves to `handoff_ready`.
- The Handoff screen summarizes run instructions, recorded tests, limitations, next improvements, and the manager or worker model settings used during the build.
- User follow-up changes go back through the manager message path.

## Packaging Workflow

1. Build the frontend bundle.
2. Freeze the desktop shell with PyInstaller.
3. Bundle the backend modules and frontend assets into the desktop artifact.
4. On Linux, assemble an AppDir and build an AppImage when tooling is available.
5. Publish the generated artifacts from `.runtime/packages/<platform>/release/`.
