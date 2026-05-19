# Codex Mission Control Wiki

This wiki is the long-form documentation hub for Codex Mission Control as a headless-first orchestration platform for Codex.

> Status: Current

## What Mission Control is

Mission Control is currently headless-first. The standalone UI is optional/future. The primary user experience is through Codex chat using the Mission Control plugin/MCP bridge.

The core runtime path is:

```text
Codex chat
  ↓
Mission Control plugin / MCP bridge
  ↓
Mission Control daemon
  ↓
Manager AI
  ↓
Worker agents / runners
```

Mission Control daemon owns orchestration, Manager AI decisions, background worker coordination, approvals, and handoff generation.

## Current status summary

Current repo direction is headless Codex-native orchestration.

- Implemented/current: daemon scripts, MCP resource catalog, prompt workflows, plugin packaging, skill library, approval relay, diagnostics surfaces, handoff summaries
- Partial/experimental: plugin health hardening, runner registry depth, existing-codebase safety features, richer event summaries
- Planned/future: optional dashboard observability, richer visual monitoring, packaging polish, deeper conflict handling

Read first:

- Users: [Quick Start](Quick-Start), [Install From Codex](Install-From-Codex), [Codex Chat Workflow](Codex-Chat-Workflow)
- Contributors: [Development Guide](Development-Guide), [Mission Control Daemon](Mission-Control-Daemon), [Safety and Security Model](Safety-and-Security-Model)
- AI/Codex agents: [Manager AI vs Codex Chat](Manager-AI-vs-Codex-Chat), [Skills and Prompts](Skills-and-Prompts), [Contributor Rules for AI Agents](Contributor-Rules-for-AI-Agents)

## Navigation

Quick start:

- [Quick Start](Quick-Start)
- [Headless Happy Path](Headless-Happy-Path)
- [Copy Paste Codex Prompts](Copy-Paste-Codex-Prompts)
- [Install From Codex](Install-From-Codex)

Core usage:

- [Codex Chat Workflow](Codex-Chat-Workflow)
- [Existing Codebase Mode](Existing-Codebase-Mode)
- [Pending Decisions and Approvals](Pending-Decisions-and-Approvals)
- [Handoffs and Evidence](Handoffs-and-Evidence)

Architecture and operations:

- [MCP Plugin Architecture](MCP-Plugin-Architecture)
- [Mission Control Daemon](Mission-Control-Daemon)
- [Runner Configuration](Runner-Configuration)
- [Diagnostics and Health Checks](Diagnostics-and-Health-Checks)
- [Debugging Common Issues](Debugging-Common-Issues)

Contributor context:

- [Development Guide](Development-Guide)
- [Contributor Rules for AI Agents](Contributor-Rules-for-AI-Agents)
- [Known Limitations and Non Goals](Known-Limitations-and-Non-Goals)
- [Roadmap](Roadmap)

Use `_Sidebar.md` for the full categorized navigation.

## Practical examples

Example prompts inside Codex chat:

```text
Use Mission Control for this repo.
Use Mission Control to understand this folder and fix the failing tests.
Show Mission Control status.
Show pending Mission Control approvals.
Get the latest Mission Control handoff.
```

## Related pages

Continue with [Headless First Direction](Headless-First-Direction), [Headless Happy Path](Headless-Happy-Path), [Copy Paste Codex Prompts](Copy-Paste-Codex-Prompts), and [MCP Plugin Architecture](MCP-Plugin-Architecture).
