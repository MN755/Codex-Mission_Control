from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InterviewQuestionTemplate:
    category: str
    question: str
    options: list[dict]


QUESTION_BANK: list[InterviewQuestionTemplate] = [
    InterviewQuestionTemplate(
        "project_type",
        "What kind of software shape should this MVP target first?",
        [
            {"id": "web_app", "label": "Web app", "description": "Browser-first experience with a responsive UI."},
            {"id": "desktop_app", "label": "Desktop app", "description": "A native or hybrid desktop workflow matters first."},
            {"id": "cli_tool", "label": "CLI or automation tool", "description": "Primary value is command-line or scriptable usage."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Pick the best fit from the idea and constraints."},
        ],
    ),
    InterviewQuestionTemplate(
        "target_platform",
        "Which platform needs the best first-run experience?",
        [
            {"id": "local_windows", "label": "Local Windows", "description": "Optimize first for Windows local development and use."},
            {"id": "portable_desktop", "label": "Portable desktop", "description": "Keep Windows first but stay cross-platform where practical."},
            {"id": "browser_only", "label": "Browser only", "description": "Assume the app mainly runs in the browser."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Choose the least risky default for the idea."},
        ],
    ),
    InterviewQuestionTemplate(
        "ui_style",
        "What UI character should the MVP lean toward?",
        [
            {"id": "functional", "label": "Functional dashboard", "description": "Clean, practical, information-dense, minimal polish risk."},
            {"id": "friendly", "label": "Friendly product UI", "description": "Softer, more guided, lighter visual feel."},
            {"id": "command_center", "label": "Mission control", "description": "Operator-style panels, clear status signals, strong structure."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Pick the UI character that suits the use case."},
        ],
    ),
    InterviewQuestionTemplate(
        "must_have",
        "Which type of capability matters most for the first usable slice?",
        [
            {"id": "core_flow", "label": "Core workflow", "description": "Get the primary end-to-end user task working first."},
            {"id": "data_view", "label": "Data visibility", "description": "Users need to inspect status, results, or records early."},
            {"id": "automation", "label": "Automation", "description": "Value comes from reducing repeated manual steps."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Choose the highest-leverage first slice."},
        ],
    ),
    InterviewQuestionTemplate(
        "nice_to_have",
        "What should the team de-prioritize if scope gets tight?",
        [
            {"id": "visual_polish", "label": "Visual polish", "description": "Ship usable functionality before extra refinement."},
            {"id": "integrations", "label": "Extra integrations", "description": "Keep external hooks minimal for the first version."},
            {"id": "advanced_settings", "label": "Advanced settings", "description": "Hide complexity until the core loop works."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Cut the least essential complexity first."},
        ],
    ),
    InterviewQuestionTemplate(
        "stack_preference",
        "How opinionated should the build be about the stack?",
        [
            {"id": "known_stack", "label": "Use a common stack", "description": "Prefer widely understood, low-friction choices."},
            {"id": "lean_stack", "label": "Use the leanest stack", "description": "Minimize dependencies and moving parts."},
            {"id": "fit_for_idea", "label": "Choose for the idea", "description": "Bias the stack toward the product shape."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Recommend a pragmatic default."},
        ],
    ),
    InterviewQuestionTemplate(
        "runtime_behavior",
        "How should users mainly interact with the product?",
        [
            {"id": "single_user_local", "label": "Single-user local", "description": "Assume one local operator or developer at a time."},
            {"id": "small_team_local", "label": "Small-team local", "description": "Prepare for a small shared workflow later."},
            {"id": "background_runs", "label": "Background runs", "description": "Longer tasks or monitoring matter from day one."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Select the lowest-friction interaction model."},
        ],
    ),
    InterviewQuestionTemplate(
        "data_storage",
        "What level of persistence is needed for the MVP?",
        [
            {"id": "simple_local_db", "label": "Simple local DB", "description": "Store enough project state locally and keep it inspectable."},
            {"id": "files_first", "label": "Files first", "description": "Prefer flat files unless structured state is necessary."},
            {"id": "hybrid_local", "label": "Hybrid local", "description": "Use both docs/files and a lightweight local DB."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Recommend the smallest durable option."},
        ],
    ),
    InterviewQuestionTemplate(
        "security",
        "How strict should the MVP be about safety boundaries?",
        [
            {"id": "local_safe_defaults", "label": "Local safe defaults", "description": "Stay local-only and require explicit broader access."},
            {"id": "strict_approvals", "label": "Strict approvals", "description": "Ask before sensitive or expansive actions."},
            {"id": "balanced", "label": "Balanced", "description": "Reduce friction while still surfacing real risk."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Pick the safest practical default."},
        ],
    ),
    InterviewQuestionTemplate(
        "integrations",
        "How should integrations be handled in the first version?",
        [
            {"id": "detect_only", "label": "Detect and report", "description": "Surface what is locally available without faking support."},
            {"id": "few_real", "label": "A few real integrations", "description": "Implement only the minimum required real hooks."},
            {"id": "pluggable_later", "label": "Pluggable later", "description": "Structure for integrations but avoid deep implementation now."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Recommend the least risky integration stance."},
        ],
    ),
    InterviewQuestionTemplate(
        "testing",
        "What test posture should the MVP target?",
        [
            {"id": "smoke_plus_units", "label": "Smoke + unit tests", "description": "Cover the core loop without building a heavy test harness."},
            {"id": "quality_biased", "label": "Quality-biased", "description": "Spend extra time on trust, regression checks, and validation."},
            {"id": "ship_fast", "label": "Ship fast", "description": "Minimal tests beyond core confidence checks."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Choose the best speed-to-confidence tradeoff."},
        ],
    ),
    InterviewQuestionTemplate(
        "timeline",
        "Which tradeoff should guide MVP scoping?",
        [
            {"id": "fast_vertical_slice", "label": "Fast vertical slice", "description": "Deliver one strong end-to-end flow quickly."},
            {"id": "broader_surface", "label": "Broader surface", "description": "Show more of the product, even if depth is lighter."},
            {"id": "strong_foundation", "label": "Stronger foundation", "description": "Invest more in architecture before breadth."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Recommend the right scope posture."},
        ],
    ),
]


def select_questions(question_count: int) -> list[InterviewQuestionTemplate]:
    if question_count not in {6, 20, 50}:
        raise ValueError("question_count must be 6, 20, or 50")

    base = QUESTION_BANK.copy()
    if question_count == 6:
        return base[:6]
    if question_count == 20:
        repeated = (base * 2)[:20]
        return [
            InterviewQuestionTemplate(
                category=f"{question.category}_{index}",
                question=question.question,
                options=question.options,
            )
            for index, question in enumerate(repeated)
        ]
    repeated = (base * 5)[:50]
    return [
        InterviewQuestionTemplate(
            category=f"{question.category}_{index}",
            question=question.question,
            options=question.options,
        )
        for index, question in enumerate(repeated)
    ]

