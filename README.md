# Codex Mission Control

![Codex Mission Control logo](apps/desktop/assets/mission-control-logo.png)

Codex Mission Control is a local-first desktop app for orchestrating multiple coding agents through a single manager interface. It turns a rough project idea into docs, an interview, a scoped plan, coordinated worker tasks, and a final handoff without requiring the user to talk to each worker directly.

## Why it exists

Most local agent workflows break down when the user has to manually re-prompt every worker, track overlapping file edits, and remember what happened between runs. Mission Control adds a lightweight manager layer on top of local agent tooling so one person can supervise a small AI build team from a single desktop app.

## Highlights

- Desktop-first UX for Windows, macOS, and Linux
- Local FastAPI + SQLite backend with React frontend
- Guided intake, interview, planning, build monitor, and handoff flow
- Manager orchestration with deterministic fallback
- Worker coordination with path reservation and conflict prevention
- Dry-run mode for demos and UI testing
- Codex CLI support with ChatGPT sign-in or optional API-key login
- Claude Code and external adapter support
- One-click launch scripts and cross-platform packaging workflow

## Current status

This is an MVP focused on proving the workflow locally:

- The core product works as a local desktop app
- Codex CLI is the most complete live provider path today
- Codex app-server support exists but remains experimental
- Claude Code and external adapters are supported through CLI-style runners

## Quick start

### Requirements

- Python 3.10+
- Node.js 20+
- A supported local webview backend
  - Windows: WebView2 recommended
  - macOS: native Cocoa webview path
  - Linux: WebKitGTK or Qt-based backend depending on environment

### Install dependencies

Backend:

```powershell
cd apps/server
python -m pip install -e .[dev]
```

Frontend:

```powershell
cd apps/dashboard
npm install
```

### Start the app

Windows PowerShell:

```powershell
.\scripts\start-mission-control.ps1
```

Windows double-click:

- Run `scripts/start-mission-control.bat`

macOS or Linux:

```bash
./scripts/start-mission-control.sh
```

### Create a desktop shortcut on Windows

```powershell
.\scripts\create-desktop-shortcut.ps1
```

### Stop a source-launched instance on Windows

```powershell
.\scripts\stop-mission-control.ps1
```

## Authentication and providers

### Codex

- Recommended path: sign in with ChatGPT through the local Codex CLI
- Device-code sign-in is available as a fallback
- Optional API-key login is available, but it may use API billing depending on your account
- Mission Control does not edit `~/.codex/config.toml` by default
- Mission Control does not store raw API keys in its own database

### Claude Code

- Uses the local Claude Code CLI
- Authentication is managed outside Mission Control

### External adapter

- Lets you wire in another local LLM command or wrapper
- Mission Control sends task context over stdin and environment variables

## What the app does

1. Create local project docs inside `<workspace>/mission-control/`
2. Run a structured interview with 6, 20, or 50 questions
3. Generate a reviewable plan
4. Decompose the plan into milestone-based worker tasks
5. Launch workers, stream events, and track reservations in the build monitor
6. Ingest worker reports and route next actions automatically
7. Generate a structured handoff with run instructions and known limitations

## Runner modes

- `dry_run`: offline simulation for demos, tests, and UI work
- `cli`: use the selected local provider CLI directly
- `app_server`: experimental Codex-only app-server integration
- `auto`: choose the best supported runner for the selected provider and fall back safely

## Manager modes

- `auto`: try live provider-backed manager turns, then fall back deterministically
- `provider`: prefer live provider-backed manager turns
- `deterministic`: local rules and templates only

## Model settings

Mission Control stores model settings per project.

- Empty model fields mean `use provider default`
- Empty reasoning fields mean `use provider default`
- Worker settings can be overridden by role
- Per-run overrides take precedence over global provider defaults

## Packaging

Source packaging scripts:

- `scripts/package-desktop.ps1`
- `scripts/package-desktop.sh`
- `scripts/package-desktop.py`

GitHub Actions workflow:

- `.github/workflows/package-desktop.yml`

Packaging targets:

- Windows: standalone `.exe`
- macOS: `.app` bundle
- Linux: portable bundle and AppImage when tooling is available

## Development

Backend dev server:

```powershell
cd apps/server
python -m uvicorn main:app --app-dir src --reload
```

Frontend dev server:

```powershell
cd apps/dashboard
npm run dev
```

Browser fallback mode on Windows:

```powershell
.\scripts\start-mission-control.ps1 -Mode web
```

## Repository layout

```text
apps/
  dashboard/   React desktop UI
  desktop/     Desktop shell and packaging assets
  server/      FastAPI backend, orchestration logic, runners
docs/          Public design and operations docs
scripts/       Launch, stop, shortcut, and packaging scripts
workspace/     Local workspace placeholder
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Provider Integration](docs/CODEX_INTEGRATION.md)
- [Workflow](docs/WORKFLOW.md)
- [Security](docs/SECURITY.md)

## Limitations

- Codex app-server is still experimental
- Native desktop behavior depends on the host webview backend
- Packaged binaries are unsigned unless you add platform signing separately
- Provider feature depth varies between Codex, Claude Code, and external adapters
- Validation quality depends on the target workspace and available local tooling

## License and usage note

This project is designed to run against local provider tooling and the user’s existing account/session where supported. Review your provider terms, local authentication setup, and billing model before using API-key-based flows.
