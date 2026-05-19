# Glossary

This page defines the core Mission Control vocabulary used throughout the wiki and repo docs.

> Status: Current

## Core terms

- Mission Control: the local orchestration platform
- Manager AI: the orchestration authority inside Mission Control
- Codex chat bridge: the user-facing relay surface
- worker agent: background execution unit under Manager control
- daemon: the long-running local backend
- MCP: Model Context Protocol surface used to expose tools, resources, and prompts
- tool: action surface
- resource: read-only summary surface
- prompt: reusable workflow instruction
- skill: Codex instruction bundle
- runner: execution backend such as Codex CLI or Ollama
- pending decision: approval or question record
- bridge message: chat-safe message format
- handoff: final or partial outcome summary
- dry-run: safe simulation mode without claiming real execution
- headless mode: operation without relying on the standalone dashboard
- imported codebase mode: safe attach flow for an existing repo
- swarm plan: Manager-defined worker strategy
- agent contract: worker boundary definition
- path lock: file ownership barrier between tasks
- evidence: validation output backing a claim

## Related pages

For deeper context read [Manager AI vs Codex Chat](Manager-AI-vs-Codex-Chat), [MCP Plugin Architecture](MCP-Plugin-Architecture), and [Adaptive Agent Swarms](Adaptive-Agent-Swarms).
