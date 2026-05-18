from __future__ import annotations

from dataclasses import dataclass
from typing import Any


INTERVIEW_CATEGORIES = (
    "product goal",
    "target users",
    "MVP scope",
    "core features",
    "nice-to-have features",
    "platform/runtime",
    "UI/UX style",
    "data/storage",
    "authentication/security",
    "integrations/connectors",
    "agent/tool behavior",
    "approvals/sandboxing",
    "testing/validation",
    "deployment/distribution",
    "performance constraints",
    "privacy/local-first constraints",
    "future expansion",
    "handoff format",
)


@dataclass(frozen=True)
class InterviewQuestionTemplate:
    category: str
    question: str
    why: str
    impact: str
    options: list[dict[str, str]]
    allow_custom_answer: bool
    affects: list[str]


QUESTION_BANK: list[InterviewQuestionTemplate] = [
    InterviewQuestionTemplate(
        category="product goal",
        question="What outcome would make this project feel unquestionably useful in its first version?",
        why="The manager needs a clear success target before it decides scope, architecture, and validation depth.",
        impact="high",
        options=[
            {"id": "ship_core_workflow", "label": "Ship one reliable end-to-end workflow", "description": "Prove the main task works before widening the surface area."},
            {"id": "show_command_center", "label": "Prove a strong command-center experience", "description": "Bias toward operator clarity, status visibility, and coordination UX."},
            {"id": "automate_manual_work", "label": "Automate repeated manual work first", "description": "Focus the MVP on removing a painful repeated process."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the best first outcome from the project context."},
        ],
        allow_custom_answer=True,
        affects=["success criteria", "MVP definition", "validation priorities"],
    ),
    InterviewQuestionTemplate(
        category="target users",
        question="Who needs the best first-run experience from this project?",
        why="Target users drive UX depth, docs tone, and how much safety or configuration complexity is acceptable.",
        impact="high",
        options=[
            {"id": "solo_builder", "label": "A solo builder or operator", "description": "Optimize for one person using the project locally."},
            {"id": "small_team", "label": "A small internal team", "description": "Design for a few people sharing the workflow or artifacts."},
            {"id": "mixed_roles", "label": "Different roles with different needs", "description": "Expect builders, reviewers, or operators to use different parts of the product."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Ask the manager to choose the least risky user assumption."},
        ],
        allow_custom_answer=True,
        affects=["user journeys", "docs", "permissions model"],
    ),
    InterviewQuestionTemplate(
        category="MVP scope",
        question="How aggressive should the first slice be?",
        why="The manager needs to know whether to bias toward a narrow runnable slice or a broader but shallower first release.",
        impact="high",
        options=[
            {"id": "narrow_slice", "label": "Keep it narrow and runnable", "description": "Prioritize one trustworthy vertical slice over breadth."},
            {"id": "balanced_slice", "label": "Balance depth with a few visible extras", "description": "Deliver the core loop plus a small amount of supporting surface area."},
            {"id": "broader_preview", "label": "Show a broader preview of the product", "description": "Cover more surface area, even if some edges stay lighter."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the safest scope posture."},
        ],
        allow_custom_answer=False,
        affects=["milestone count", "timeline", "scope cut strategy"],
    ),
    InterviewQuestionTemplate(
        category="core features",
        question="Which kind of capability matters most to the first usable release?",
        why="The manager needs to know what to protect when tradeoffs appear during planning.",
        impact="high",
        options=[
            {"id": "workflow_execution", "label": "A complete working flow", "description": "Make the main user journey genuinely usable first."},
            {"id": "visibility_and_status", "label": "Visibility and status awareness", "description": "Users need trustworthy insight into state, progress, or results."},
            {"id": "agent_or_tool_automation", "label": "Agent or tool automation", "description": "The main value is in reducing repeated manual work."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager select the highest-leverage feature bias."},
        ],
        allow_custom_answer=True,
        affects=["task prioritization", "acceptance criteria", "UI emphasis"],
    ),
    InterviewQuestionTemplate(
        category="nice-to-have features",
        question="If scope gets tight, what should the manager cut first?",
        why="This gives the manager permission to protect the core loop instead of pretending everything fits.",
        impact="medium",
        options=[
            {"id": "extra_polish", "label": "Extra polish and refinement", "description": "Ship the reliable core before perfecting presentation."},
            {"id": "extra_integrations", "label": "Extra integrations", "description": "Keep external hooks minimal unless they are essential."},
            {"id": "advanced_controls", "label": "Advanced controls and settings", "description": "Delay deeper configuration until the main loop works."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the safest cut line."},
        ],
        allow_custom_answer=True,
        affects=["scope guardrails", "plan revisions"],
    ),
    InterviewQuestionTemplate(
        category="platform/runtime",
        question="What runtime environment matters most for the first version?",
        why="Runtime assumptions change tool choices, packaging, testing, and the safest architecture.",
        impact="high",
        options=[
            {"id": "local_first", "label": "Local-first on the current machine", "description": "Optimize for local execution and local data first."},
            {"id": "browser_first", "label": "Browser-first experience", "description": "Assume users mainly interact through a web UI."},
            {"id": "background_jobs", "label": "Long-running or background work matters", "description": "Expect monitoring, queued work, or longer operations from day one."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Ask the manager to choose the least risky runtime model."},
        ],
        allow_custom_answer=True,
        affects=["architecture", "runner strategy", "deployment assumptions"],
    ),
    InterviewQuestionTemplate(
        category="UI/UX style",
        question="What interaction style should the first version lean toward?",
        why="The manager should not guess whether to optimize for operator density, guided flows, or minimal configuration friction.",
        impact="medium",
        options=[
            {"id": "command_center", "label": "Command-center clarity", "description": "Favor dense status, strong structure, and operational visibility."},
            {"id": "guided_product", "label": "Guided product flow", "description": "Favor step-by-step guidance and softer UI complexity."},
            {"id": "minimal_tooling", "label": "Minimal tooling UI", "description": "Keep the interface pragmatic and low-friction over ornamental."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager pick the best fit from the context."},
        ],
        allow_custom_answer=True,
        affects=["layout", "component density", "onboarding style"],
    ),
    InterviewQuestionTemplate(
        category="data/storage",
        question="How durable should project state be in the first release?",
        why="Storage expectations change architecture, backup behavior, and how much complexity the manager should tolerate.",
        impact="medium",
        options=[
            {"id": "lightweight_local_db", "label": "A lightweight local database", "description": "Keep structured local state durable and queryable."},
            {"id": "files_first", "label": "Files and docs first", "description": "Prefer readable local files unless a database is clearly needed."},
            {"id": "hybrid_local", "label": "A hybrid of docs/files and local DB", "description": "Use both when each format serves a clear purpose."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the smallest durable option."},
        ],
        allow_custom_answer=False,
        affects=["storage design", "project data model", "handoff artifacts"],
    ),
    InterviewQuestionTemplate(
        category="authentication/security",
        question="What safety posture should the manager assume while building this?",
        why="Security and trust boundaries affect approvals, integrations, deployment decisions, and how aggressively the system acts on the user’s behalf.",
        impact="high",
        options=[
            {"id": "local_safe_defaults", "label": "Local-safe defaults", "description": "Keep everything local and explicit unless broader access is required."},
            {"id": "strict_approval_gates", "label": "Strict approval gates", "description": "Favor explicit approval for sensitive actions and broader access."},
            {"id": "balanced_execution", "label": "Balanced safety with lower friction", "description": "Surface risk clearly without requiring approval for every minor action."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Ask the manager to choose the safest practical default."},
        ],
        allow_custom_answer=True,
        affects=["approval policy", "sandboxing", "integration posture"],
    ),
    InterviewQuestionTemplate(
        category="integrations/connectors",
        question="How should the first version treat external integrations or connectors?",
        why="Integrations create hidden scope and risk, so the manager needs a clear stance before planning around them.",
        impact="medium",
        options=[
            {"id": "detect_only", "label": "Detect and report what exists", "description": "Surface availability honestly without building deep integrations yet."},
            {"id": "few_real_integrations", "label": "Implement only the minimum real integrations", "description": "Build only the integrations that materially affect the core workflow."},
            {"id": "structure_for_later", "label": "Structure for integrations later", "description": "Keep the architecture ready but delay most actual integration work."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the least risky integration stance."},
        ],
        allow_custom_answer=True,
        affects=["connectors", "tooling scope", "risk profile"],
    ),
    InterviewQuestionTemplate(
        category="agent/tool behavior",
        question="How assertive should the manager and worker agents be during this project?",
        why="Agent autonomy affects how tasks are decomposed, when approvals appear, and how much manual oversight the user wants.",
        impact="medium",
        options=[
            {"id": "manager_led_cautious", "label": "Manager-led and cautious", "description": "Favor explicit coordination and more human-visible checkpoints."},
            {"id": "balanced_autonomy", "label": "Balanced autonomy", "description": "Let the manager route work proactively while surfacing important decisions."},
            {"id": "high_autonomy", "label": "Push autonomy when safe", "description": "Reduce interruptions unless the action is risky or ambiguous."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the right autonomy level."},
        ],
        allow_custom_answer=False,
        affects=["task orchestration", "approval frequency", "worker routing"],
    ),
    InterviewQuestionTemplate(
        category="approvals/sandboxing",
        question="What approval friction is acceptable for this project?",
        why="Approval expectations determine how often the manager can move without stopping and what sandbox posture is tolerable.",
        impact="medium",
        options=[
            {"id": "ask_more_often", "label": "Ask more often for safety", "description": "Favor explicit confirmation over uninterrupted flow."},
            {"id": "ask_on_sensitive_actions", "label": "Ask only on sensitive actions", "description": "Keep the flow moving but stop on meaningful risk."},
            {"id": "minimize_interruptions", "label": "Minimize interruptions where safe", "description": "Bias toward fewer prompts if the action scope is low risk."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the best approval posture."},
        ],
        allow_custom_answer=True,
        affects=["approval policy", "tool gating", "sandbox defaults"],
    ),
    InterviewQuestionTemplate(
        category="testing/validation",
        question="What validation posture should the manager target before handoff?",
        why="Testing expectations directly affect plan depth, tool use, and whether the manager can credibly declare the project handoff-ready.",
        impact="high",
        options=[
            {"id": "smoke_plus_core_tests", "label": "Smoke checks plus core tests", "description": "Cover the main workflow without building a massive harness."},
            {"id": "quality_biased", "label": "Bias toward stronger validation", "description": "Spend more effort on confidence, regression checks, and review readiness."},
            {"id": "fastest_safe_validation", "label": "Use the fastest safe validation path", "description": "Do enough to stay honest without over-investing early."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the best speed-to-confidence tradeoff."},
        ],
        allow_custom_answer=True,
        affects=["test plan", "definition of done", "handoff readiness"],
    ),
    InterviewQuestionTemplate(
        category="deployment/distribution",
        question="How should the first version be delivered or shared?",
        why="Distribution expectations shape packaging work, deployment priorities, and what counts as a complete handoff.",
        impact="medium",
        options=[
            {"id": "local_run_only", "label": "Local run instructions are enough", "description": "Deliver a project that runs locally with honest setup steps."},
            {"id": "shareable_internal_package", "label": "Make it easy to hand to another internal user", "description": "Bias toward a clearer setup and more polished packaging."},
            {"id": "deployment_path_matters", "label": "A real deployment path matters early", "description": "Prepare for an actual hosted or distributed target."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the least risky delivery posture."},
        ],
        allow_custom_answer=True,
        affects=["deployment tasks", "packaging", "handoff instructions"],
    ),
    InterviewQuestionTemplate(
        category="privacy/local-first constraints",
        question="How strict should the manager be about keeping data and execution local-first?",
        why="Local-first constraints materially affect provider choice, tooling, and what integrations are acceptable.",
        impact="high",
        options=[
            {"id": "strict_local_first", "label": "Keep it strongly local-first", "description": "Prefer local data, local execution, and explicit opt-ins for outside services."},
            {"id": "local_first_when_possible", "label": "Prefer local-first when practical", "description": "Stay local by default but allow carefully chosen external services."},
            {"id": "flexible_if_value_is_clear", "label": "Be flexible if the value is clear", "description": "Allow non-local pieces when they strongly improve the product."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the safest practical boundary."},
        ],
        allow_custom_answer=True,
        affects=["provider selection", "integration limits", "data handling"],
    ),
    InterviewQuestionTemplate(
        category="handoff format",
        question="What should the final handoff optimize for?",
        why="The manager needs to know whether the final output should emphasize run instructions, technical details, stakeholder clarity, or future work guidance.",
        impact="medium",
        options=[
            {"id": "builder_handoff", "label": "A builder-ready technical handoff", "description": "Prioritize implementation details, setup steps, and known engineering limits."},
            {"id": "operator_handoff", "label": "An operator-ready usage handoff", "description": "Prioritize how to run, use, and validate the delivered project."},
            {"id": "decision_log_handoff", "label": "A strong decision and risk summary", "description": "Prioritize why things were chosen, what changed, and what remains risky."},
            {"id": "recommend", "label": "Not sure, recommend one", "description": "Let the manager choose the best handoff style."},
        ],
        allow_custom_answer=True,
        affects=["handoff template", "docs emphasis", "final deliverables"],
    ),
]


def _batch_size(remaining_budget: int) -> int:
    if remaining_budget <= 0:
        return 0
    if remaining_budget <= 3:
        return remaining_budget
    return min(5, remaining_budget)


def _template_to_payload(template: InterviewQuestionTemplate) -> dict[str, Any]:
    return {
        "question": template.question,
        "why": template.why,
        "category": template.category,
        "impact": template.impact,
        "options": list(template.options),
        "allow_custom_answer": template.allow_custom_answer,
        "affects": list(template.affects),
    }


def select_fallback_questions(
    remaining_budget: int,
    *,
    asked_categories: set[str] | None = None,
    pending_categories: set[str] | None = None,
) -> list[dict[str, Any]]:
    asked_categories = set(asked_categories or set())
    pending_categories = set(pending_categories or set())
    limit = _batch_size(remaining_budget)
    if limit <= 0:
        return []

    selected: list[InterviewQuestionTemplate] = []
    selected_categories: set[str] = set()

    for template in QUESTION_BANK:
        if template.category in asked_categories or template.category in pending_categories:
            continue
        selected.append(template)
        selected_categories.add(template.category)
        if len(selected) >= limit:
            return [_template_to_payload(item) for item in selected]

    for template in QUESTION_BANK:
        if template.category in pending_categories or template.category in selected_categories:
            continue
        selected.append(template)
        selected_categories.add(template.category)
        if len(selected) >= limit:
            break

    return [_template_to_payload(item) for item in selected[:limit]]


def fallback_category_bank() -> list[str]:
    return list(INTERVIEW_CATEGORIES)
