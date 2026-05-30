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
- [enable-safe-mode.md](../examples/codex-chat-workflows/enable-safe-mode.md)
- [generate-agents-md.md](../examples/codex-chat-workflows/generate-agents-md.md)
- [continue-later.md](../examples/codex-chat-workflows/continue-later.md)
- [empty-folder-new-project.md](../examples/codex-chat-workflows/empty-folder-new-project.md)
- [existing-codebase-fix-bug.md](../examples/codex-chat-workflows/existing-codebase-fix-bug.md)

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

## Bridge Reminder

In every workflow, Codex chat stays in the bridge role. Mission Control owns orchestration, swarm control, background workers, approvals, and handoff generation.
