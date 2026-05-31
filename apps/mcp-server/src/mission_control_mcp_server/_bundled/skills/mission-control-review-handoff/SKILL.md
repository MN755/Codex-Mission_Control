---
name: mission-control-review-handoff
description: Use when Codex should retrieve Mission Control status, evidence, and final handoff notes for review with the user.
---

# Mission Control Review Handoff

Use this skill when the user asks for status, proof of work, handoff review, or the final output from a Mission Control-managed run.

## Responsibilities

- Fetch current run status from Mission Control.
- Check for pending approvals, recovery prompts, or blocked steps.
- Retrieve handoff notes, evidence, validation summaries, and follow-up recommendations when available.
- Present the results clearly in Codex chat without pretending Codex itself ran the work.

## Review rules

- Distinguish active work, blocked work, and completed work.
- Call out missing evidence instead of smoothing it over.
- If approval is pending, ask the user instead of guessing.
- If the handoff is incomplete, say which section is still missing.
