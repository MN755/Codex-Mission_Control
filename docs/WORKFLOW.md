# Workflow

This document describes the intended operator flow for Mission Control from launch to handoff.

## 1. Launch

The app can be started in three common ways:

- `scripts/start-mission-control.ps1` on Windows
- `scripts/start-mission-control.bat` for double-click Windows launch
- `scripts/start-mission-control.sh` on macOS or Linux

The desktop shell is the default experience. Browser mode remains available as an explicit fallback for development or recovery.

## 2. Choose auth and provider

On startup, Mission Control presents an auth and launch surface.

For Codex projects, the user can:

- sign in with ChatGPT
- use a device-code flow
- optionally use an API key

For Claude Code and external adapters:

- Mission Control assumes the local provider auth flow is handled outside the app

## 3. Create a project

Project intake collects:

- project name
- project idea
- workspace path
- provider
- runner mode
- manager mode

At this point Mission Control creates:

- the project record
- a reserved manager agent
- initial planning docs in `<workspace>/mission-control/`

No coding should start during intake.

## 4. Run the interview

The interview step narrows scope before work begins.

- The user selects 6, 20, or 50 questions
- Questions are presented one at a time
- Answers are stored and shown in the UI
- The manager uses those answers to shape the plan

## 5. Review the plan

Mission Control generates a versioned plan that includes:

- summary
- scope
- milestones
- agent roster
- task structure
- risks
- definition of done

The user can approve the plan or request directional changes.

## 6. Generate tasks

After approval, the manager decomposes the plan into milestone-based tasks.

Rules:

- Milestone 1 should produce a runnable vertical slice
- Later milestones can deepen quality, polish, integrations, or testing
- Each task includes scope, validation, success criteria, and path hints

## 7. Start workers

The build monitor is where orchestration becomes active.

- Workers start through the selected runner
- Effective models are resolved from project settings
- Writable paths are reserved before a task begins
- Conflicting work is moved to `waiting_on_paths`
- Events stream into the live monitor over SSE

The user does not talk directly to worker agents.

## 8. Route work automatically

When a worker finishes:

- its report is parsed and stored
- task state is updated
- the manager decides what happens next

Possible next actions include:

- assign next task
- request fix
- wait
- mark blocked
- escalate to user

## 9. Validate and hand off

Before handoff, Mission Control should confirm that:

- required tasks are complete or explicitly deferred
- recorded validation steps are complete or marked as not run
- handoff content has been generated

The final handoff includes:

- what was built
- how to run it
- how to use it
- tests and builds recorded
- limitations
- risks
- suggested next improvements

## 10. Continue iterating

Change requests return to the manager path rather than bypassing orchestration. The same project can continue through multiple plan, build, and handoff cycles.
