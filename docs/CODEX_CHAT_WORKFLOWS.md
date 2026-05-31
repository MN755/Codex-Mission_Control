# Codex Chat Workflows

This document maps the example headless Mission Control workflows that live under [examples/codex-chat-workflows](../examples/codex-chat-workflows).

## Workflow Examples

- [use-mission-control-for-current-repo.md](../examples/codex-chat-workflows/use-mission-control-for-current-repo.md)
- [import-existing-codebase.md](../examples/codex-chat-workflows/import-existing-codebase.md)
- [approve-command.md](../examples/codex-chat-workflows/approve-command.md)
- [answer-manager-question.md](../examples/codex-chat-workflows/answer-manager-question.md)
- [check-status.md](../examples/codex-chat-workflows/check-status.md)
- [review-handoff.md](../examples/codex-chat-workflows/review-handoff.md)
- [debug-stuck-orchestration.md](../examples/codex-chat-workflows/debug-stuck-orchestration.md)
- [empty-folder-new-project.md](../examples/codex-chat-workflows/empty-folder-new-project.md)
- [enable-safe-mode.md](../examples/codex-chat-workflows/enable-safe-mode.md)
- [existing-codebase-fix-bug.md](../examples/codex-chat-workflows/existing-codebase-fix-bug.md)
- [generate-agents-md.md](../examples/codex-chat-workflows/generate-agents-md.md)
- [continue-later.md](../examples/codex-chat-workflows/continue-later.md)
- [build-your-own-x-catalog.md](../examples/codex-chat-workflows/build-your-own-x-catalog.md)
- [build-command-line-tool.md](../examples/codex-chat-workflows/build-command-line-tool.md)
- [build-data-and-search-system.md](../examples/codex-chat-workflows/build-data-and-search-system.md)
- [build-networked-system.md](../examples/codex-chat-workflows/build-networked-system.md)
- [build-web-stack.md](../examples/codex-chat-workflows/build-web-stack.md)
- [build-game-or-renderer.md](../examples/codex-chat-workflows/build-game-or-renderer.md)
- [build-ml-or-vision-system.md](../examples/codex-chat-workflows/build-ml-or-vision-system.md)
- [build-programming-language-or-shell.md](../examples/codex-chat-workflows/build-programming-language-or-shell.md)
- [build-low-level-systems.md](../examples/codex-chat-workflows/build-low-level-systems.md)

## Common Tool Sequence

Most workflows follow a repeatable sequence:

1. Attach the workspace or reuse the active project.
2. Start, resume, or inspect Mission Control work through tools.
3. Read safe summary resources for status, agents, diagnostics, swarm, or handoff.
4. Surface pending decisions in Codex chat.
5. Send user answers back through Mission Control decision tools.
6. Retrieve the handoff when complete.

## Workflow Families

### Orchestration

- Use Mission Control for the current repo
- Continue later

### Import

- Import existing codebase
- Generate `AGENTS.md`

### Approvals

- Approve command
- Answer manager question

### Status And Recovery

- Check status
- Debug stuck orchestration
- Enable safe mode

### Handoff

- Review handoff

### Build-From-Scratch Showcases

- Build-your-own-x catalog
- Build command-line tool
- Build data and search system
- Build networked system
- Build web stack
- Build game or renderer
- Build ML or vision system
- Build programming language or shell
- Build low-level systems

These showcase workflows exist to prove Mission Control is not limited to toy bugfixes. They demonstrate how the bridge can route ambitious greenfield builds like renderers, shells, databases, browsers, game systems, neural networks, or low-level runtime experiments through the same headless orchestration path.

## Bridge Reminder

In every workflow, Codex chat stays in the bridge role. Mission Control owns orchestration, swarm control, background workers, approvals, and handoff generation.
