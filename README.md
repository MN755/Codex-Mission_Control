# Codex Mission Control

Codex Mission Control is now a desktop-first local orchestration app for running multiple Codex-style workers through one manager interface. The user only talks to the Manager AI. The app creates local project docs, runs a structured interview, drafts a plan, starts or pauses workers, tracks progress, and prepares final handoff notes.

## What It Does

- Creates local project docs in `<selected-workspace>/mission-control/`
- Runs a multiple-choice project interview with 6, 20, or 50 questions
- Generates a reviewable MVP plan
- Starts worker agents through a runner layer with `auto`, `cli`, `app_server`, or `dry_run` modes
- Runs the Manager in `auto`, `codex`, or `deterministic` mode with structured fallback
- Streams project events into a live build monitor
- Stores orchestration state locally in SQLite
- Uses the user's existing Codex/ChatGPT sign-in session when the local Codex CLI is available

## Stack

- Desktop shell: Python desktop launcher with embedded local webview
- Frontend UI: React + TypeScript + Vite
- Backend service: FastAPI + SQLite + SQLAlchemy
- Realtime: Server-Sent Events
- Runners:
  - `dry_run`: local simulation for UI and workflow testing
  - `cli`: shells out to `codex exec` using local auth
  - `app_server`: best-effort experimental app-server path
  - `auto`: prefers app-server only if a local handshake succeeds, otherwise falls back to CLI

## Install

### Backend

```powershell
cd "C:\Users\mike\OneDrive\Desktop\Codex Mission Control\apps\server"
python -m pip install -e .[dev]
```

### Frontend

```powershell
cd "C:\Users\mike\OneDrive\Desktop\Codex Mission Control\apps\dashboard"
cmd /c npm.cmd install
```

## Run

### Desktop app on Windows

```powershell
cd "C:\Users\mike\OneDrive\Desktop\Codex Mission Control"
.\scripts\start-mission-control.ps1
```

- Starts the standalone desktop shell by default
- Reuses the existing built frontend bundle when present
- Writes launcher metadata under `.runtime/launcher/`
- Uses a local embedded webview when available and keeps all app traffic local

### Double-click on Windows

- Double-click [scripts/start-mission-control.bat](</C:/Users/mike/OneDrive/Desktop/Codex Mission Control/scripts/start-mission-control.bat>) to run the PowerShell launcher.

### Desktop shortcut on Windows

```powershell
cd "C:\Users\mike\OneDrive\Desktop\Codex Mission Control"
.\scripts\create-desktop-shortcut.ps1
```

- This creates `Codex Mission Control.lnk` on the current Windows desktop.

### Desktop app on macOS or Linux

```bash
cd "/path/to/Codex Mission Control"
./scripts/start-mission-control.sh
```

- This launches the same desktop shell from a POSIX shell.

### Stop the app on Windows

```powershell
cd "C:\Users\mike\OneDrive\Desktop\Codex Mission Control"
.\scripts\stop-mission-control.ps1
```

## Build Standalone Packages

### Package on Windows

```powershell
cd "C:\Users\mike\OneDrive\Desktop\Codex Mission Control"
.\scripts\package-desktop.ps1
```

- Builds a frozen desktop artifact under `.runtime/packages/windows/release/`
- Produces a `CodexMissionControl.exe`
- Also writes a zip archive for distribution

### Package on macOS or Linux

```bash
cd "/path/to/Codex Mission Control"
./scripts/package-desktop.sh
```

- macOS builds a `.app` bundle and zip archive under `.runtime/packages/macos/release/`
- Linux builds a portable bundle under `.runtime/packages/linux/release/`
- If `appimagetool` is available, Linux also emits a real `.AppImage`

### GitHub Actions Packaging

- A cross-platform packaging workflow is included at [package-desktop.yml](</C:/Users/mike/OneDrive/Desktop/Codex Mission Control/.github/workflows/package-desktop.yml>).
- It builds Windows, macOS, and Linux artifacts from GitHub Actions after the repo is pushed.

### Web fallback mode

```powershell
cd "C:\Users\mike\OneDrive\Desktop\Codex Mission Control"
.\scripts\start-mission-control.ps1 -Mode web
```

- This keeps the old backend plus frontend browser workflow available as a fallback.

### Backend

```powershell
cd "C:\Users\mike\OneDrive\Desktop\Codex Mission Control\apps\server"
python -m uvicorn main:app --app-dir src --reload
```

### Frontend

```powershell
cd "C:\Users\mike\OneDrive\Desktop\Codex Mission Control\apps\dashboard"
cmd /c npm.cmd run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

## Desktop Requirements

- Python 3.10+
- Node.js and npm for building the dashboard bundle from source
- `pywebview` is included in the Python desktop dependencies
- `PyInstaller` is used for packaged desktop artifacts
- Windows: WebView2 is recommended for the native embedded view
- Linux: a supported local webview backend such as WebKitGTK or Qt may still be needed
- macOS: the desktop shell uses the native Cocoa webview path through `pywebview`
- Packaged builds store writable runtime state under the user's local app-data directory instead of writing into the installed app bundle

## ChatGPT / Codex Sign-In

- This app is designed to reuse your existing local Codex login.
- Run `codex login status` to confirm you are signed in.
- The MVP does not request or store OpenAI API keys.
- To keep usage tied to ChatGPT/Codex sign-in rather than API credits, use `cli` or `auto` runner modes and stay signed into the local Codex CLI.
- The app does not modify `~/.codex/config.toml` by default.
- Manager `auto` mode tries the local Codex runner path first and falls back to deterministic orchestration if structured output is unavailable.
- The desktop shell still uses the same local Codex CLI or app-server authentication model as the web version. It does not switch to API keys.

## Model Settings

- Settings are per-project, not global.
- Open `Settings` from the project nav to configure:
  - manager model
  - default worker model
  - manager reasoning effort
  - default worker reasoning effort
  - runner mode
  - sandbox mode
  - approval policy
  - role-based worker overrides
- Empty model or reasoning values mean `use Codex default`.
- The CLI runner passes per-run overrides directly to Codex instead of editing your global config.
- Availability of any specific model depends on your current Codex or ChatGPT plan and local sign-in session.

## Manager Modes

- `auto`: tries Codex-backed manager turns for docs, planning, task generation, worker decisions, and handoff, then falls back to deterministic behavior.
- `codex`: prefers Codex-backed manager turns, but still falls back deterministically on parse or runner failure.
- `deterministic`: keeps the full workflow local and rule-based for dry-run demos and resilient fallback behavior.

## First Project Flow

1. Open the Project Intake screen.
2. Enter a project name, a general idea, and a target workspace path.
3. Choose a runner mode.
4. Click `Create project docs`.
5. Complete the interview.
6. Review the generated plan.
7. Choose `Approve and build` to start workers.
8. Monitor agents, tasks, events, and logs in Build Monitor.
9. Use the Handoff screen for run notes, tests recorded, limitations, and change requests.

## Dry-Run Demo

- Pick runner mode `dry_run`.
- Use the bundled demo workspace path under `apps/server/.runtime/demo-project` or any local workspace path you control.
- Complete the interview and approve the plan.
- The build monitor will simulate worker startup, progress, completion reports, and final handoff behavior.

## CLI Runner Configuration

- `codex` must be on `PATH`.
- The CLI runner uses `codex exec --json` and `codex exec resume`.
- If a manager or worker model is set, the runner passes `--model`.
- If a reasoning effort is set, the runner passes `-c model_reasoning_effort="..."`.
- It does not use `--dangerously-bypass-approvals-and-sandbox`.
- Default sandbox mode is `workspace-write`.
- Default approval mode is `on-request`.
- The CLI runner records stdout, stderr, event logs, exit codes, and session references under `apps/server/.runtime/logs/`.

## App-Server Status

- The backend includes a real experimental `app_server` runner path.
- It performs a local handshake against `codex app-server` over stdio JSON-RPC.
- The MVP treats this path as best-effort and falls back to the CLI runner in `auto` mode if the handshake fails.
- See `docs/CODEX_INTEGRATION.md` for the exact behavior and limitations.

## Limitations

- The desktop shell is implemented as a local native window over the same FastAPI + React stack, so the UI is no longer browser-dependent in normal use, but it still relies on a working local webview backend.
- Packaged Windows `.exe`, macOS `.app`, and Linux AppImage-style artifacts are unsigned by default. They are suitable for local distribution and testing, not notarized storefront delivery.
- The app-server integration is intentionally narrow and environment-dependent.
- Manager task generation is milestone-based, but still intentionally lightweight rather than deeply project-specific.
- Source checkout runs store runtime state under `apps/server/.runtime/`. Packaged runs use the user's app-data directory.
- Non-git workspaces use explicit path reservations to prevent overlapping edits instead of full worktree isolation.
- Manager behavior includes deterministic fallback paths for resilience, especially in `dry_run` mode.
- Validation depth depends on the target workspace and available local tooling.
