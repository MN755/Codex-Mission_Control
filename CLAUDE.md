# Mission Control in Claude Code

Mission Control is headless-first in this repository.

- Claude Code is the bridge between the user and Mission Control.
- Mission Control owns orchestration state, approvals, handoffs, and manager behavior.
- The Manager AI lives inside Mission Control, not inside the Claude chat.
- Worker runners stay behind Mission Control approvals and policies.

When the user asks to use Mission Control:

1. Attach or reuse the current workspace with `mission_control_attach_workspace`.
2. Start or continue the task with `mission_control_start_task`.
3. Poll `mission_control_get_status` and `mission_control_get_pending_decisions`.
4. Ask the user for approvals or answers instead of deciding for them.
5. Send answers back with `mission_control_answer_decision`.
6. Fetch `mission_control_get_event_digest` and `mission_control_get_handoff_summary` when useful.

Do not bypass Mission Control by spawning your own competing manager workflow.
Do not claim real execution, validation, or handoff evidence that the MCP bridge did not return.
