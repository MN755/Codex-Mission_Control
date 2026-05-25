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

Full navigation:

Start here:

- [Quick Start](Quick-Start)
- [Install From Codex](Install-From-Codex)
- [Headless First Direction](Headless-First-Direction)

Headless usage:

- [Codex Chat Workflow](Codex-Chat-Workflow)
- [Existing Codebase Mode](Existing-Codebase-Mode)
- [Pending Decisions and Approvals](Pending-Decisions-and-Approvals)
- [Handoffs and Evidence](Handoffs-and-Evidence)
- [AGENTS md and Agent Instructions](AGENTS-md-and-Agent-Instructions)
- [Workspace Attach and Project Lifecycle](Workspace-Attach-and-Project-Lifecycle)

Architecture:

- [MCP Plugin Architecture](MCP-Plugin-Architecture)
- [Mission Control Daemon](Mission-Control-Daemon)
- [Manager AI vs Codex Chat](Manager-AI-vs-Codex-Chat)
- [Adaptive Agent Swarms](Adaptive-Agent-Swarms)
- [MCP Bridge Endpoints](MCP-Bridge-Endpoints)
- [Bridge Message Format](Bridge-Message-Format)

Runners and providers:

- [Runner Configuration](Runner-Configuration)
- [Provider Autowiring](Provider-Autowiring)
- [Troubleshooting CLI Runners](Troubleshooting-CLI-Runners)
- [Dry Run Mode](Dry-Run-Mode)
- [Runtime Configuration Reference](Runtime-Configuration-Reference)

Safety and approvals:

- [Safety and Security Model](Safety-and-Security-Model)
- [Safe Mode](Safe-Mode)
- [Approval Card Fallback Text](Approval-Card-Fallback-Text)
- [Manager Questions](Manager-Questions)
- [Evidence Review Checklist](Evidence-Review-Checklist)

Debugging and operations:

- [Diagnostics and Health Checks](Diagnostics-and-Health-Checks)
- [Debugging Common Issues](Debugging-Common-Issues)
- [Plugin Health Doctor](Plugin-Health-Doctor)
- [Health Doctor Example Output](Health-Doctor-Example-Output)
- [Logs and Runtime Folders](Logs-and-Runtime-Folders)
- [Localhost Binding and Ports](Localhost-Binding-and-Ports)
- [Recovery Planning](Recovery-Planning)

Skills, prompts, and MCP catalogs:

- [Skills and Prompts](Skills-and-Prompts)
- [MCP Resources Catalog](MCP-Resources-Catalog)
- [MCP Prompts Catalog](MCP-Prompts-Catalog)
- [Swarm Modes Reference](Swarm-Modes-Reference)
- [Agent Archetypes](Agent-Archetypes)
- [Path Locks and Ownership](Path-Locks-and-Ownership)
- [Validation Summary Reference](Validation-Summary-Reference)

Development and project context:

- [Development Guide](Development-Guide)
- [Testing and Smoke Checks](Testing-and-Smoke-Checks)
- [Contributor Rules for AI Agents](Contributor-Rules-for-AI-Agents)
- [Docs Source Map](Docs-Source-Map)
- [Codebase Map and Understanding](Codebase-Map-and-Understanding)
- [Known Limitations and Non Goals](Known-Limitations-and-Non-Goals)
- [Roadmap](Roadmap)
- [Glossary](Glossary)

Install and repair details:

- [Headless Install and Autowire](Headless-Install-and-Autowire)
- [Install Reports and Repair Mode](Install-Reports-and-Repair-Mode)

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

Continue with [Headless First Direction](Headless-First-Direction), [MCP Plugin Architecture](MCP-Plugin-Architecture), [Mission Control Daemon](Mission-Control-Daemon), and [Roadmap](Roadmap).
