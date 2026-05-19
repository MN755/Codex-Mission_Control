# Headless Architecture

Mission Control should be understood as a headless orchestration system first.

```text
Codex chat
  ->
Mission Control skill/prompt
  ->
MCP tools/resources/prompts
  ->
Mission Control daemon
  ->
Manager AI
  ->
Worker runners
```

## Component Split

### Codex Chat Bridge

The Codex chat agent is the user-facing bridge.

Responsibilities:

- attach a workspace
- invoke Mission Control flows
- surface status, approvals, questions, diagnostics, and handoffs
- send user answers back through bridge-safe tools

Non-responsibilities:

- it is not the Manager AI
- it should not invent separate orchestration plans
- it should not bypass Mission Control approvals

### Mission Control Daemon

The daemon is the long-running local orchestration surface.

Responsibilities:

- maintain orchestration state
- own project and run records
- expose local APIs for bridge access
- run without requiring the standalone frontend

### MCP Bridge

The MCP layer exposes the daemon to Codex through:

- tools
- resources
- prompts

It should stay thin and predictable. It is a transport and summarization layer, not a second orchestrator.

### Skills

Skills define reusable user-facing workflows for Codex-native usage such as:

- install and autowire
- attach workspace
- approve or answer pending decisions
- status and recovery checks
- handoff review

### Prompts

Prompts provide bridge-safe invocation templates for common actions. They should prefer compact status, clean redaction, and clear next actions.

### Resources

Resources expose safe summaries of live Mission Control state such as:

- project status
- swarm posture
- pending decisions
- handoff summaries
- codebase understanding

### Tools

Tools perform the actual bridge operations:

- attach
- start
- resume
- pause
- fetch status
- fetch pending decisions
- answer pending decisions
- fetch handoff

### Manager AI

The Manager AI lives inside Mission Control.

Responsibilities:

- planning
- task routing
- worker coordination
- risk and approval decisions
- handoff preparation

### Worker Runner Registry

Mission Control should manage a runner registry for:

- Codex CLI
- Ollama
- Claude CLI
- configured APIs
- other supported execution backends

The bridge should describe this as background execution capability, not as a UI feature.

### PendingDecision Relay

`PendingDecision` is the canonical relay record for:

- manager questions
- command approvals
- tool approvals
- write permissions
- swarm approvals
- recovery options

### BridgeMessage Formatter

`BridgeMessage` formatters should produce:

- compact markdown
- structured payload fields
- explicit user action requirements
- explicit redaction state

### Handoff Formatter

The handoff formatter should return chat-native final summaries with:

- outcome
- evidence-backed validation state
- remaining risks
- next actions

### Optional Dashboard

The dashboard is optional.

- it should not be required for normal Mission Control use
- it is a future observability surface, not the primary product interface
- it can remain paused or move later to `apps/dashboard-ui` or a similar package

## Architecture Rules

- dashboard is optional
- UI should not be required for normal use
- the headless daemon should run without a frontend
- bridge flows should remain usable from Codex chat alone
- repo structure should keep headless core work conceptually separate from optional standalone UI work
