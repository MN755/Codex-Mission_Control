from __future__ import annotations

from collections import Counter

from models import InterviewQuestion, Project


def summarize_answers(questions: list[InterviewQuestion]) -> dict:
    answer_map = {str(question.index): (question.selected_option or "unanswered") for question in questions}
    labels = [question.selected_text for question in questions if question.selected_text]
    counts = Counter(question.selected_option for question in questions if question.selected_option)
    return {
        "answer_map": answer_map,
        "selected_labels": labels,
        "top_preferences": counts.most_common(5),
    }


def build_plan_markdown(project: Project, questions: list[InterviewQuestion], action_bias: str | None = None, note: str | None = None) -> tuple[str, dict]:
    summary = summarize_answers(questions)
    bias_line = {
        "simplify": "Bias toward a smaller, more controllable MVP.",
        "ambitious": "Bias toward a broader first cut while keeping the core slice runnable.",
        "usability": "Bias toward operator clarity and onboarding quality.",
        "quality": "Bias toward stronger validation and safer delivery.",
        "rewrite": "Reframe the plan from first principles while preserving the project goal.",
        "feature_delta": "Incorporate the requested feature adjustment without expanding unrelated scope.",
    }.get(action_bias or "", "Bias toward a fast, trustworthy vertical slice.")

    label_preview = ", ".join(summary["selected_labels"][:6]) or "Answers still favor general discovery."
    note_block = f"\nUser note:\n{note}\n" if note else ""
    milestones = [
        "Milestone 1: ship a runnable vertical slice with a trustworthy core workflow.",
        "Milestone 2: tighten usability, reduce friction, and expand only the most valuable next slice.",
        "Milestone 3: validate, document, and hand off the project with real run instructions.",
    ]
    validation_plan = [
        "Confirm install and run instructions are real.",
        "Run the best available build, test, and smoke commands.",
        "Record what was actually run, what passed, and what remains manual.",
    ]
    risks = [
        "Scope drift if interview choices remain broad.",
        "Integration assumptions that depend on local tooling.",
        "False confidence if validation is skipped or simulated.",
    ]
    definition_of_done = [
        "The main workflow works locally.",
        "Docs are current.",
        "Build and test instructions are accurate.",
        "Known limitations are documented.",
    ]
    content = f"""# {project.name} MVP Plan

## Refined Project Summary
- Build a local-first MVP for: {project.idea}
- Interview signals: {label_preview}
- Planning bias: {bias_line}

## MVP Scope
- Deliver one usable, end-to-end workflow that proves the product value.
- Keep dependencies and setup local-friendly.
- Avoid speculative feature branches or enterprise-heavy admin features.{note_block}

## Milestones
1. {milestones[0]}
2. {milestones[1]}
3. {milestones[2]}

## Recommended Architecture
- Local-first app shell with a lightweight backend and a responsive frontend.
- Persistent local storage for project state plus local markdown docs for planning artifacts.
- Clear separation between manager coordination, worker execution, and verification.

## Agent Roster
- Manager AI: interviews the user, maintains the plan, routes work, and checks completion reports.
- Builder Agent A: focuses on the primary implementation path.
- Builder Agent B: handles a second non-overlapping slice when safe.
- Validation Agent: handles tests, smoke checks, docs, and review-ready notes.

## Task Breakdown
- Backlog setup and scoping.
- Runnable vertical slice implementation.
- Usability and operator polish.
- Validation and handoff.

## Validation and Test Plan
- {validation_plan[0]}
- {validation_plan[1]}
- {validation_plan[2]}

## Risks
- {risks[0]}
- {risks[1]}
- {risks[2]}

## Definition of Done
- {definition_of_done[0]}
- {definition_of_done[1]}
- {definition_of_done[2]}
- {definition_of_done[3]}
"""
    summary_json = {
        "refined_summary": f"Build a local-first MVP for {project.idea}",
        "mvp_scope": [
            "Deliver one usable, end-to-end workflow.",
            "Keep dependencies and setup local-friendly.",
            "Avoid speculative scope.",
        ],
        "milestones": milestones,
        "recommended_architecture": [
            "Local-first app shell with a lightweight backend and responsive frontend.",
            "Persistent local state plus markdown planning docs.",
            "Clear separation between manager coordination, worker execution, and validation.",
        ],
        "agent_roster": [
            {"name": "Manager AI", "role": "Coordination and planning"},
            {"name": "Builder Agent A", "role": "Primary implementation"},
            {"name": "Builder Agent B", "role": "Secondary non-overlapping slice"},
            {"name": "Validation Agent", "role": "Testing and handoff"},
        ],
        "task_breakdown": [
            "Backlog setup and scoping",
            "Runnable vertical slice",
            "Usability pass",
            "Validation and handoff",
        ],
        "validation_plan": validation_plan,
        "risks": risks,
        "definition_of_done": definition_of_done,
        "task_board_preview": [
            {"column": "Backlog", "items": ["Scope setup", "Core implementation", "Validation"]},
            {"column": "Assigned", "items": []},
            {"column": "Working", "items": []},
            {"column": "Waiting On Paths", "items": []},
            {"column": "Needs Review", "items": []},
            {"column": "Done", "items": []},
            {"column": "Blocked", "items": []},
        ],
        "answer_summary": summary,
    }
    return content, summary_json
