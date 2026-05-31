# Skills and Prompts

This page documents the Mission Control skill library and the workflow prompts used by Codex chat in bridge mode.

> Status: Current

## What a skill is

A skill is a reusable Codex instruction bundle. For Mission Control, skills should:

- keep Codex in the bridge role
- call Mission Control tools/resources/prompts when available
- preserve approvals
- avoid direct shell execution inside Mission Control mode
- summarize clearly for chat

## Bridge rules

The Codex chat agent is not the Manager AI.

It should not:

- independently spawn worker agents
- invent separate manager plans
- bypass pending decisions
- claim work happened without backend evidence

## Important skills

Core skills:

- `mission-control-orchestrate`
- `mission-control-import-codebase`
- `mission-control-status`
- `mission-control-approve`
- `mission-control-handoff`
- `mission-control-debug`
- `mission-control-swarm`
- `mission-control-safe-mode`
- `mission-control-resume`
- `mission-control-agents-md`

Additional bridge-oriented skills should include:

- `mission-control-install-from-github`
- `mission-control-autowire-providers`
- `mission-control-plugin-health`
- `mission-control-knowledge-base-map`

Specialized shipped lanes include:

- NVIDIA/CUDA skills such as `mission-control-cuda-kernel-generation`, `mission-control-cuda-tile-refactor`, and `mission-control-nsight-profiling`
- TensorFlow skills such as `mission-control-tensorflow-scaffolding`, `mission-control-tf-data-pipelines`, `mission-control-tensorflow-serving`, and `mission-control-tflite-deployment`

These are shipped skills, not imaginary roadmap stickers.

## Prompts

Common workflow prompts should cover:

- attach current workspace
- use Mission Control for this repo
- import existing codebase
- continue orchestration
- show pending approvals
- review latest handoff
- explain current swarm
- enable safe mode
- generate AGENTS.md proposal
- review project capabilities
- review one named capability section
- ask Manager for a fresh plan

## Related pages

Read [MCP Plugin Architecture](MCP-Plugin-Architecture), [Manager AI vs Codex Chat](Manager-AI-vs-Codex-Chat), [Contributor Rules for AI Agents](Contributor-Rules-for-AI-Agents), and [AGENTS md and Agent Instructions](AGENTS-md-and-Agent-Instructions).
