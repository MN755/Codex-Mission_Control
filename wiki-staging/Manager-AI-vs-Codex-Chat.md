# Manager AI vs Codex Chat

This page defines the most important role split in the project: Codex chat is the bridge, and Mission Control Manager AI is the orchestrator.

> Status: Current

## Correct role model

User only sees Codex chat.

Codex chat sends requests downward and relays status upward.

Mission Control Manager AI remains the project lead behind the bridge.

Worker agents stay behind the Manager.

## What Codex chat should do

Codex chat should:

- attach the workspace
- start or continue a Mission Control task
- show compact status
- relay approvals and manager questions
- return handoffs and diagnostics

## What Codex chat should not do

Codex chat should not:

- become a second manager
- independently spawn workers
- bypass approvals
- invent handoffs
- silently change scope

## Example

Good:

```text
Mission Control wants approval to run the test suite. Approve once or deny?
```

Bad:

```text
I decided to skip the approval and just run the tests myself.
```

## Related pages

Continue with [Codex Chat Workflow](Codex-Chat-Workflow), [Pending Decisions and Approvals](Pending-Decisions-and-Approvals), and [Skills and Prompts](Skills-and-Prompts).
