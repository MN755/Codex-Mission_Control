# Overview

> Status: Current

Codex Mission Control is a background-running orchestration platform that lets one Codex chat work through a local Mission Control daemon instead of coordinating every task manually.

## Product summary

Mission Control keeps the user-facing conversation in Codex chat while moving project planning, worker coordination, approvals, diagnostics, and handoffs into a dedicated local runtime. The Codex chat agent is the bridge. The Manager AI lives inside Mission Control and directs the work.

## What Mission Control does

- attaches a workspace to a project record
- imports an existing codebase with a read-only intake pass
- creates and updates plans through the Manager AI
- coordinates background worker agents and runner selection
- raises pending decisions for risky or ambiguous actions
- returns status, diagnostics, event digests, and handoffs in chat-safe summaries

## What it does not require

- a standalone dashboard
- a cloud control plane
- raw API keys for the preferred Codex CLI path
- raw logs in normal chat summaries

## Read next

- [Quick Start](QUICK_START.md)
- [Background Install](HEADLESS_INSTALL.md)
- [Codex Chat Mode](CODEX_CHAT_MODE.md)
- [Background Architecture](HEADLESS_ARCHITECTURE.md)
