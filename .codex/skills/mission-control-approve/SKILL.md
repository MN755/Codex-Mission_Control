---
name: mission-control-approve
description: Use when Mission Control needs a user approval or manager-question answer relayed through Codex chat.
---

# Mission Control Approve

## Purpose

Render pending approvals or questions clearly, collect the user's answer, and send that answer back to Mission Control.

## Bridge Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## When To Use

- There are pending approvals
- There are pending manager questions
- The user asks to approve or deny a Mission Control request

## Required Mission Control Tools, Resources, And Prompts

- Tools: `mission_control_get_pending_decisions`, `mission_control_answer_decision`
- Resources: `mission-control://projects/{project_id}/pending-decisions`
- Prompts: `show-pending-approvals`, `answer-pending-approval`

## Step-By-Step Workflow

1. Call `mission_control_get_pending_decisions`.
2. Render the top pending decision in Codex chat.
3. Explain the risk level and available options.
4. Ask the user to choose.
5. Call `mission_control_answer_decision`.
6. Return a confirmation and refreshed decision state.

## What To Show The User In Codex Chat

- Decision type
- Why it is needed
- Risk level
- Exact options and recommended option when present
- Confirmation after the answer is recorded

## Safety And Approval Behavior

- Always ask the user before answering.
- Preserve one-time versus project-wide approval distinctions.
- Keep secret-bearing command details redacted unless Mission Control safely exposed them.

## Fallback Behavior If The Daemon Is Unavailable

- Say the decision could not be sent back to Mission Control.
- Do not imply the approval was recorded.

## What Not To Do

- Do not approve or deny anything on the user's behalf.
- Do not bypass Mission Control by running the gated action directly.
- Do not widen an approval scope unless the user explicitly picked that option.
