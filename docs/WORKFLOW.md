# Workflow

This document describes the user-visible workflow from install through handoff.

Current priority note:

- headless Codex-native workflows are primary
- the standalone dashboard workflow remains optional
- standalone UI details live in [OPTIONAL_DASHBOARD_UI.md](OPTIONAL_DASHBOARD_UI.md)

## Headless happy path

The preferred bridge flow from Codex chat is:

1. install or repair Mission Control from the repo
2. autowire the safe available runners
3. attach the workspace
4. start or resume the orchestration
5. show a compact status summary
6. surface pending approvals or manager questions
7. send the user answer back through the bridge
8. fetch the event digest or diagnostics summary when needed
9. fetch the evidence-based handoff summary

Reference docs:

- [HEADLESS_INSTALL.md](HEADLESS_INSTALL.md)
- [AUTOWIRE_PROVIDERS.md](AUTOWIRE_PROVIDERS.md)
- [HEADLESS_HEALTH.md](HEADLESS_HEALTH.md)
- [HEADLESS_UX.md](HEADLESS_UX.md)
- [CODEX_CHAT_UX_SPEC.md](CODEX_CHAT_UX_SPEC.md)

## 1. Install and bootstrap

Mission Control should be installable from Codex chat without opening the standalone UI.

Bootstrap expectations:

- sync the repo-local plugin bundle and skills when possible
- generate a safe headless config
- start or verify the daemon
- validate MCP bridge assets
- report ready, degraded, or failed honestly

## 2. Attach and understand

When the workspace is empty, Mission Control can create a new project path.

When the workspace already contains a repo:

- attach the workspace
- prefer a read-only understanding pass first
- build a codebase map
- ask only the minimum useful clarification questions

## 3. Plan and approvals

The Manager produces a plan, swarm posture, validation strategy, and risk posture.

Codex chat is responsible for:

- relaying pending approvals
- relaying manager questions
- showing status and event digests
- returning handoff summaries

Codex chat is not responsible for inventing the orchestration plan locally.

## 4. Execution and status

During execution, the bridge should answer one question quickly:

- does the user need to do anything right now?

That means the default user-facing loop is:

- compact status summary
- pending approvals or questions
- short event digest when helpful
- diagnostics summary only when something is degraded or blocked

## 5. Handoff

The final output should stay chat-native:

- what changed
- what was validated
- what is still limited or missing
- what the next useful prompt is

No raw logs by default. No fake claims. No “tests passed” without evidence.

## Optional standalone UI

Dashboard routing, startup wizard details, widget layouts, archive behavior, and project workspace layout are intentionally treated as optional UI concerns and documented in [OPTIONAL_DASHBOARD_UI.md](OPTIONAL_DASHBOARD_UI.md).
