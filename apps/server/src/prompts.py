from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from models import Agent, Project, Task


WORKER_REPORT_SCHEMA = {
    "agent": "string",
    "task_id": "string",
    "status": "done|blocked|needs_review|error",
    "summary": "string",
    "files_changed": ["string"],
    "tests_run": ["string"],
    "blockers": ["string"],
    "risks": ["string"],
    "recommended_next_task": "string",
}

RUNNER_RESULT_ENVELOPE_SCHEMA = {
    "status": "completed|blocked|needs_review|failed",
    "runner_type": "string",
    "lane": "implementation|browser_automation|test_execution|repo_analysis|manager_turn",
    "summary": "string",
    "report": WORKER_REPORT_SCHEMA,
    "files_changed": ["string"],
    "tests_run": ["string"],
    "commands_attempted": ["string"],
    "evidence": [
        {
            "kind": "command_output|test_result|build_result|file_change|artifact|screenshot|report|manual_note",
            "summary": "string",
            "status": "passed|failed|not_run|unknown",
            "source_path": "string|null",
            "command": "string|null",
            "metadata_json": {},
        }
    ],
    "risks": ["string"],
    "blockers": ["string"],
    "diagnostics": ["string"],
    "approvals_requested": [{}],
    "recovery_plan": ["string"],
    "edits": [{"path": "string", "content": "string|null", "summary": "string|null"}],
    "failure_classification": "transient|user_action_required|input_error|runner_bug|infra_blocker|approval_denied|null",
    "needs_approval": False,
    "metadata_json": {},
}

MANAGER_DOC_UPDATE_SCHEMA = {
    "summary_markdown": "string",
    "files": [{"filename": "string", "content": "string"}],
}

MANAGER_PLAN_SCHEMA = {
    "refined_summary": "string",
    "mvp_scope": ["string"],
    "milestones": ["string"],
    "recommended_architecture": ["string"],
    "agent_roster": [{"name": "string", "role": "string"}],
    "task_breakdown": ["string"],
    "validation_plan": ["string"],
    "risks": ["string"],
    "definition_of_done": ["string"],
    "content_markdown": "string",
    "summary_json": {},
}

MANAGER_TASK_DECOMPOSITION_SCHEMA = {
    "summary_markdown": "string",
    "milestones": ["string"],
    "tasks": [
        {
            "title": "string",
            "goal": "string",
            "scope": "string",
            "agent_role": "string",
            "milestone": "string",
            "priority": 10,
            "allowed_paths": ["string"],
            "forbidden_paths": ["string"],
            "validation_steps": ["string"],
            "success_criteria": ["string"],
            "estimated_complexity": "small|medium|large",
            "dependencies": [1],
            "status": "backlog|assigned|working|waiting_on_paths|needs_review|done|blocked",
        }
    ],
}

MANAGER_WORKER_DECISION_SCHEMA = {
    "decision_type": "assign_next_task|request_fix|mark_done|mark_blocked|retire_agent|escalate_to_user|wait",
    "summary_markdown": "string",
    "task_id": 1,
    "assign_to_agent_id": 1,
    "follow_up_title": "string",
    "follow_up_goal": "string",
    "escalation_message": "string",
}

MANAGER_HANDOFF_SCHEMA = {
    "summary_markdown": "string",
    "what_was_built": ["string"],
    "how_to_run": ["string"],
    "how_to_use": ["string"],
    "tests_builds_run": ["string"],
    "known_limitations": ["string"],
    "remaining_risks": ["string"],
    "suggested_next_improvements": ["string"],
}

MANAGER_INTERVIEW_SCHEMA = {
    "understanding": {
        "summary": "string",
        "known_facts": {},
        "unknowns": {},
        "assumptions": ["string"],
        "constraints": ["string"],
        "confidence_by_category": {"product goal": 0.0},
    },
    "next_questions": [
        {
            "question": "string",
            "why": "string",
            "category": "product goal|target users|MVP scope|core features|nice-to-have features|platform/runtime|UI/UX style|data/storage|authentication/security|integrations/connectors|agent/tool behavior|approvals/sandboxing|testing/validation|deployment/distribution|performance constraints|privacy/local-first constraints|future expansion|handoff format",
            "impact": "low|medium|high",
            "options": [{"id": "string", "label": "string", "description": "string"}],
            "allow_custom_answer": False,
            "affects": ["string"],
        }
    ],
    "more_questions_needed": True,
    "stop_reason": "string or null",
}

MANAGER_SWARM_PLAN_SCHEMA = {
    "mode": "fastest_build|balanced|high_quality|documentation_heavy|research_planning|massive_codebase|gpu_programming|manager_decides",
    "goal": "string",
    "recommended_agent_count": 5,
    "coordination_risk": "low|medium|high",
    "path_conflict_risk": "low|medium|high",
    "expected_bottlenecks": ["string"],
    "strategy_summary": "string",
    "validation_strategy": ["string"],
    "specs": [
        {
            "archetype": "frontend|backend|feature|docs|test|reviewer|security|planner|architect|integration|ops|research|migration|refactor|performance|data|ui_polish|release_handoff",
            "name": "string",
            "mission": "string",
            "model_policy": "string",
            "toolset": ["string"],
            "allowed_paths": ["string"],
            "forbidden_paths": ["string"],
            "spawn_phase": "string",
            "retire_when": "string",
            "priority": 50,
            "iteration_budget": 1,
        }
    ],
}


@dataclass(frozen=True)
class PromptProfile:
    tier: str
    label: str
    manager_rules: tuple[str, ...]
    worker_rules: tuple[str, ...]


def _gpu_mode_block(project: Project) -> str:
    from gpu_support import detect_cuda_repo_mode
    from nvidia_support import detect_project_nvidia_gpu_diagnostics

    mode = detect_cuda_repo_mode(project.workspace_path)
    if not mode.get("enabled"):
        return ""
    health = detect_project_nvidia_gpu_diagnostics(project.workspace_path)
    lines = [
        "GPU programming mode:",
        f"- Detected GPU repo mode: {mode.get('mode')}.",
        "- Treat CUDA and GPU validation as first-class work, not generic Python glue.",
        "- After kernel-affecting edits, plan a build, focused test, benchmark comparison, and Nsight profile loop.",
        "- Separate infrastructure blockers such as pending pods or saturated GPU memory from code defects before reopening the edit loop.",
    ]
    if mode.get("frameworks"):
        lines.append(f"- Detected GPU stack: {', '.join(str(item) for item in list(mode.get('frameworks') or [])[:4])}.")
    if health.get("status") in {"degraded", "warning", "unknown"}:
        lines.append(f"- Current GPU observability verdict: {health.get('summary')}")
    return "\n".join(lines)


def _tensorflow_mode_block(project: Project) -> str:
    from tensorflow_support import build_tensorflow_validation_plan, detect_tensorflow_repo_mode

    mode = detect_tensorflow_repo_mode(project.workspace_path)
    if not mode.get("enabled"):
        return ""
    validation = build_tensorflow_validation_plan(project.workspace_path)
    lines = [
        "TensorFlow product mode:",
        f"- Detected TensorFlow repo mode: {mode.get('mode')}.",
        "- Treat data pipelines, training, evaluation, export, and serving checks as separate work, not one blurry Python blob.",
        "- Prefer Keras-first implementation, explicit tf.data handling, and evidence-backed TensorBoard or test outputs after model changes.",
        "- When the repo signals TFX, TensorFlow Lite, or serving/export paths, keep those product lanes in the validation plan instead of stopping at training.",
    ]
    if mode.get("frameworks"):
        lines.append(f"- Detected TensorFlow stack: {', '.join(str(item) for item in list(mode.get('frameworks') or [])[:5])}.")
    if mode.get("product_workflows"):
        lines.append(f"- Expected product workflows: {', '.join(str(item) for item in list(mode.get('product_workflows') or [])[:6])}.")
    if validation.get("recommended_fixes"):
        lines.append(f"- Current TensorFlow validation gaps: {' '.join(str(item) for item in list(validation.get('recommended_fixes') or [])[:3])}")
    return "\n".join(lines)


def _pytorch_mode_block(project: Project) -> str:
    from pytorch_support import build_pytorch_validation_plan, detect_pytorch_repo_mode

    mode = detect_pytorch_repo_mode(project.workspace_path)
    if not mode.get("enabled"):
        return ""
    validation = build_pytorch_validation_plan(project.workspace_path)
    lines = [
        "PyTorch product mode:",
        f"- Detected PyTorch repo mode: {mode.get('mode')}.",
        "- Treat dataloaders, training, evaluation, checkpoints, and export as separate validation lanes instead of one giant tensor-shaped shrug.",
        "- Record the actual device, precision, and batch size used after model edits so PyTorch evidence does not turn into folklore.",
        "- When the repo signals distributed, profiler, or export workflows, keep those lanes explicit instead of pretending one pytest run told the whole truth.",
    ]
    if mode.get("frameworks"):
        lines.append(f"- Detected PyTorch stack: {', '.join(str(item) for item in list(mode.get('frameworks') or [])[:5])}.")
    if mode.get("product_workflows"):
        lines.append(f"- Expected product workflows: {', '.join(str(item) for item in list(mode.get('product_workflows') or [])[:6])}.")
    if validation.get("recommended_fixes"):
        lines.append(f"- Current PyTorch validation gaps: {' '.join(str(item) for item in list(validation.get('recommended_fixes') or [])[:3])}")
    return "\n".join(lines)


def build_prompt_profile(*, provider: str | None = None, model: str | None = None, reasoning_effort: str | None = None) -> PromptProfile:
    provider_text = (provider or "").strip().lower()
    model_text = (model or "").strip().lower()
    reasoning_text = (reasoning_effort or "").strip().lower()

    if (
        ("gpt-5.5" in model_text and "mini" not in model_text)
        or "claude-opus" in model_text
        or "opus 4" in model_text
        or ("codex" in provider_text and reasoning_text in {"high", "xhigh"})
    ):
        return PromptProfile(
            tier="elite",
            label="elite planner",
            manager_rules=(
                "You can evaluate multiple plausible approaches before choosing one, but present only the chosen path plus the key tradeoff.",
                "Use richer context when it materially improves the decision, not because you feel lonely.",
                "For task, interview, or swarm outputs, precision matters more than breadth; keep every item distinct and justified.",
            ),
            worker_rules=(
                "You may coordinate related changes across multiple allowed files when the task truly requires it.",
                "Prefer the smallest coherent fix, but include the full set of necessary in-scope edits when a single-file patch would be fake.",
                "Keep the final report terse even when the reasoning behind it was not.",
            ),
        )
    if any(token in model_text for token in ("gpt-5.4", "gpt-oss:20b", "codestral", "qwen2.5-coder:14b", "codellama:13b", "claude-sonnet", "sonnet")):
        return PromptProfile(
            tier="strong",
            label="strong builder",
            manager_rules=(
                "Handle moderate ambiguity directly, but avoid speculative branches that do not change the decision.",
                "Keep structured outputs tight: enough detail to execute, not enough to become their own climate system.",
                "Bias toward 3-5 strong items over longer lists.",
            ),
            worker_rules=(
                "Work across the minimum number of in-scope files needed for a correct fix.",
                "Do not spend tokens narrating obvious steps; spend them avoiding bad edits.",
                "If testing was not run, say so plainly instead of decorating the absence.",
            ),
        )
    if (
        any(token in model_text for token in ("qwen2.5:7b", "qwen2.5-coder:7b", "llama3", "gemma3", "deepseek-r1", "7b", "8b"))
        or provider_text == "ollama"
    ):
        return PromptProfile(
            tier="weak_local",
            label="compact local model",
            manager_rules=(
                "Prefer the smallest valid output shape and stay close to the payload facts.",
                "Avoid subtle inference, optional branches, or long explanations unless explicitly requested.",
                "For plans, tasks, interviews, or swarm rosters, keep the item count minimal and high-signal.",
            ),
            worker_rules=(
                "Favor one narrow change at a time and avoid opportunistic cleanup.",
                "Prefer single-file edits when they can solve the task honestly.",
                "Do not claim a fix, refactor, or validation result unless the output proves it directly.",
            ),
        )
    if "mini" in model_text or reasoning_text in {"minimal", "low", "none"}:
        return PromptProfile(
            tier="compact",
            label="compact hosted model",
            manager_rules=(
                "Be concise and literal; do not elaborate unless the payload requires it.",
                "Use short lists and explicit wording over nuanced but fragile phrasing.",
                "Prefer the direct answer over a tour of every path not taken.",
            ),
            worker_rules=(
                "Keep changes tightly scoped and reports short.",
                "Avoid speculative cleanup or broad rewrites.",
                "Return the requested structure exactly; correctness beats style.",
            ),
        )
    return PromptProfile(
        tier="standard",
        label="standard general model",
        manager_rules=(
            "Balance speed, clarity, and precision; avoid both underspecifying and rambling.",
            "Use context when it helps the decision, but keep the final answer lean.",
            "Prefer actionable structure over commentary.",
        ),
        worker_rules=(
            "Keep the edit set coherent and modest.",
            "Stay literal about test evidence and risk.",
            "Do not widen scope unless the task explicitly demands it.",
        ),
    )


def prompt_profile_block(*, provider: str | None = None, model: str | None = None, reasoning_effort: str | None = None, audience: str) -> str:
    profile = build_prompt_profile(provider=provider, model=model, reasoning_effort=reasoning_effort)
    rules = profile.manager_rules if audience == "manager" else profile.worker_rules
    role_label = "Manager" if audience == "manager" else "Worker"
    return "\n".join(
        [
            f"{role_label} execution profile:",
            f"- Treat the current model as: {profile.label}.",
            "- These are default biases, not hard laws. Break them when the task evidence clearly requires it.",
            *[f"- {rule}" for rule in rules],
        ]
    )


def _manager_action_biases(action: str, profile: PromptProfile) -> tuple[str, ...]:
    normalized = (action or "").strip().lower()
    if normalized.startswith("interview."):
        common = (
            "Bias toward only the highest-leverage unknowns; do not burn question budget on trivia.",
            "Keep categories distinct so the user is not answering the same question wearing a fake mustache.",
        )
        if profile.tier == "weak_local":
            return common + (
                "Prefer 2-3 sharp questions in the next batch unless the payload makes more strictly necessary.",
                "Keep every question and rationale short, literal, and directly tied to implementation decisions.",
            )
        if profile.tier in {"elite", "strong"}:
            return common + (
                "You may ask a slightly broader batch when the payoff is real, but prioritize ordering and impact over volume.",
                "Use nuanced tradeoffs only when they help choose a materially better next question.",
            )
        return common + (
            "Keep the next batch focused and implementation-relevant.",
        )
    if normalized in {"tasks.decompose", "plan.generate"}:
        common = (
            "Bias toward tasks or plan steps with explicit ownership, dependencies, and validation.",
            "Prefer concrete path or subsystem boundaries over vague phases.",
        )
        if profile.tier == "weak_local":
            return common + (
                "Default to a compact task set with crisp titles and minimal overlap.",
                "Avoid ornate milestone structures unless the payload explicitly demands them.",
            )
        if profile.tier in {"elite", "strong"}:
            return common + (
                "You may express deeper sequencing and cross-cutting validation when it materially reduces execution risk.",
                "Use more than the minimum number of tasks only when the extra split improves coordination, not aesthetics.",
            )
        return common + (
            "Keep decomposition practical and execution-ready.",
        )
    if normalized == "swarm.plan":
        common = (
            "Bias toward the smallest swarm that still creates real parallelism.",
            "Avoid duplicate specialists unless their path ownership or mission is clearly different.",
        )
        if profile.tier == "weak_local":
            return common + (
                "Default to a conservative roster and low coordination complexity unless the payload strongly justifies expansion.",
                "Prefer fewer, clearer specs over ambitious but collision-prone specialization.",
            )
        if profile.tier in {"elite", "strong"}:
            return common + (
                "You may recommend more specialized agents when coordination boundaries are explicit and useful.",
                "Balance implementation speed with review and validation roles instead of brute-force parallelism.",
            )
        return common + (
            "Keep the roster disciplined and easy to coordinate.",
        )
    return ()


def _project_state_biases(project: Project, *, action: str | None = None, task: Task | None = None) -> tuple[str, ...]:
    normalized_action = (action or "").strip().lower()
    biases: list[str] = []
    if project.source_type == "existing_folder":
        biases.extend(
            [
                "Treat the repository as real inherited state. Prefer diagnosis, bounded change, and evidence over reinvention.",
                "Assume hidden constraints exist in the current codebase unless the task evidence proves otherwise.",
            ]
        )
        if normalized_action in {"tasks.decompose", "plan.generate", "swarm.plan"}:
            biases.append("Bias toward targeted repair, validation, and subsystem ownership before broad greenfield-style expansion.")
    elif project.source_type == "idea":
        biases.extend(
            [
                "Treat the workspace as a fresh build unless the payload says otherwise.",
                "Bias toward outcome clarity, first slice viability, and avoiding fake complexity.",
            ]
        )
    if task is not None and task.allowed_paths_json:
        if len(task.allowed_paths_json) == 1:
            biases.append(f"Path ownership is intentionally narrow here. Default to that single area: {task.allowed_paths_json[0]}.")
        else:
            biases.append("Multiple paths are allowed, but that is permission, not a quota. Use only the paths the fix actually needs.")
    return tuple(biases)


def _worker_task_biases(task: Task, profile: PromptProfile) -> tuple[str, ...]:
    combined = " ".join(filter(None, [task.title, task.goal, task.scope])).lower()
    is_fix = any(token in combined for token in ("fix", "correct", "repair", "implement", "update", "change", "patch"))
    is_validation = any(token in combined for token in ("reproduce", "validate", "verification", "handoff", "test", "inspect"))
    common = ("Let the repo evidence drive the decision, not the model's desire to sound accomplished.",)
    if is_fix:
        if profile.tier == "weak_local":
            return common + (
                "Default to the narrowest plausible edit, ideally one file, unless the evidence clearly requires more.",
                "Name the exact failing path in your own reasoning and avoid speculative cleanup.",
            )
        if profile.tier in {"elite", "strong"}:
            return common + (
                "Default to a narrow fix, but permit multi-file edits when they are the smallest honest solution.",
                "Use surrounding context to avoid partial fixes that only look neat from a distance.",
            )
        return common + (
            "Prefer a small, honest fix over broad cleanup.",
        )
    if is_validation:
        return common + (
            "Do not claim file changes for reproduce, inspect, or validation work unless the task explicitly requires an edit.",
            "Bias toward crisp evidence capture: what was run, what failed, and what that implies next.",
        )
    return common + (
        "Keep the execution path straightforward and evidence-based.",
    )


def manager_system_prompt(project: Project, *, provider: str | None = None, model: str | None = None, reasoning_effort: str | None = None) -> str:
    profile_block = prompt_profile_block(provider=provider, model=model, reasoning_effort=reasoning_effort, audience="manager")
    gpu_block = _gpu_mode_block(project)
    tensorflow_block = _tensorflow_mode_block(project)
    pytorch_block = _pytorch_mode_block(project)
    return f"""You are the Manager AI for Codex Mission Control.

Project name: {project.name}
Project idea:
{project.idea}

Responsibilities:
- Restate and refine the project idea.
- Ask interview questions when needed.
- Convert answers into project docs.
- Produce and revise plans.
- Create worker tasks.
- Assign non-overlapping tasks.
- Track worker reports.
- Decide the next action for finished workers.
- Prioritize usability, speed, and quality.
- Never claim a project is done unless validation was performed or explicitly marked as not run.

{profile_block}

{gpu_block}

{tensorflow_block}
{pytorch_block}

When you reply with structured content, keep it concise and machine-friendly.
"""


def project_context_block(project: Project, docs_path: str, plan_markdown: str | None = None, user_name: str | None = None) -> str:
    plan_section = f"\nCurrent approved plan:\n{plan_markdown}\n" if plan_markdown else ""
    return f"""Project: {project.name}
Workspace path: {project.workspace_path}
Project docs path: {docs_path}
Preferred user name: {user_name or project.created_by or "Operator"}
Primary goal: ship a usable MVP quickly without fake demos.
{plan_section}
"""


def worker_task_prompt(
    project: Project,
    agent: Agent,
    task: Task,
    docs_path: str,
    plan_markdown: str | None = None,
    context_pack_markdown: str | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    context = project_context_block(project, docs_path, plan_markdown)
    context_pack_section = f"\nRelevant context pack:\n{context_pack_markdown}\n" if context_pack_markdown else ""
    profile = build_prompt_profile(provider=provider, model=model, reasoning_effort=reasoning_effort)
    profile_block = prompt_profile_block(provider=provider, model=model, reasoning_effort=reasoning_effort, audience="worker")
    gpu_block = _gpu_mode_block(project)
    tensorflow_block = _tensorflow_mode_block(project)
    pytorch_block = _pytorch_mode_block(project)
    worker_bias_block = "\n".join(f"- {rule}" for rule in _worker_task_biases(task, profile))
    state_bias_block = "\n".join(f"- {rule}" for rule in _project_state_biases(project, task=task))
    return f"""You are a Codex worker agent operating under Codex Mission Control.

Task ID: {task.id}
Agent name: {agent.name}
Agent role: {agent.role}

{context}
{context_pack_section}

Goal:
{task.goal}

Scope:
{task.scope}

Allowed files/areas:
{json.dumps(task.allowed_paths_json, indent=2)}

Forbidden files/areas:
{json.dumps(task.forbidden_paths_json, indent=2)}

Requirements:
- Stay inside the task scope.
- Do not touch forbidden paths.
- If a required action needs approval, stop and report it.
- Prefer the smallest coherent set of changes.
- Do not claim testing was run if it was not run.

{profile_block}

{gpu_block}

{tensorflow_block}
{pytorch_block}

Task-specific execution biases:
{worker_bias_block}

Project-state biases:
{state_bias_block}

Validation steps:
{json.dumps(task.validation_steps_json, indent=2)}

Completion envelope JSON schema:
{json.dumps(RUNNER_RESULT_ENVELOPE_SCHEMA, indent=2)}

Rules for the completion envelope:
- The outer result envelope is mandatory.
- Keep report.agent and report.task_id aligned with this task.
- Put the human-readable summary in both summary and report.summary when they differ only in detail.
- If you ran tests, benchmarks, profiling, browser steps, or repo analysis commands, record them in tests_run, commands_attempted, and evidence.
- If you need approval or hit a runner/tooling problem, classify it with failure_classification instead of hiding it in prose.

Return only a JSON object matching the envelope schema as your final answer.
"""


def manager_message_prompt(
    project: Project,
    docs_path: str,
    user_message: str,
    user_name: str | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    profile_block = prompt_profile_block(provider=provider, model=model, reasoning_effort=reasoning_effort, audience="manager")
    gpu_block = _gpu_mode_block(project)
    tensorflow_block = _tensorflow_mode_block(project)
    pytorch_block = _pytorch_mode_block(project)
    return f"""You are the Manager AI for the project "{project.name}".

Project docs live at: {docs_path}
Call the user "{user_name or project.created_by or "Operator"}" unless they ask you to change that.

The user sent this message:
{user_message}

{profile_block}

{gpu_block}

{tensorflow_block}
{pytorch_block}

Respond as the manager coordinating the project. If the message requests changes, outline the next step clearly.
"""


def manager_action_prompt(
    project: Project,
    docs_path: str,
    *,
    action: str,
    objective: str,
    response_schema: dict,
    payload: dict,
    plan_markdown: str | None = None,
    user_name: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    context = project_context_block(project, docs_path, plan_markdown, user_name)
    profile = build_prompt_profile(provider=provider, model=model, reasoning_effort=reasoning_effort)
    profile_block = prompt_profile_block(provider=provider, model=model, reasoning_effort=reasoning_effort, audience="manager")
    gpu_block = _gpu_mode_block(project)
    tensorflow_block = _tensorflow_mode_block(project)
    pytorch_block = _pytorch_mode_block(project)
    action_biases = _manager_action_biases(action, profile)
    state_biases = _project_state_biases(project, action=action)
    action_bias_block = "\n".join(f"- {rule}" for rule in [*action_biases, *state_biases])
    task_bias_section = f"\nTask-specific decision biases:\n{action_bias_block}" if action_bias_block else ""
    return f"""You are the Manager AI for Codex Mission Control.

Action: {action}
Objective:
{objective}

{context}

Input payload:
{json.dumps(payload, indent=2, default=str)}

{profile_block}

{gpu_block}

{tensorflow_block}
{pytorch_block}{task_bias_section}

Response rules:
- Return only valid JSON.
- Do not wrap the JSON in markdown fences.
- Match this schema exactly:
{json.dumps(response_schema, indent=2, default=str)}

Manager priorities, in order:
1. Usability for the user
2. Speed of building
3. Quality
"""


def manager_interview_prompt(
    project: Project,
    *,
    action: str,
    objective: str,
    payload: dict,
    response_schema: dict,
    user_name: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    profile = build_prompt_profile(provider=provider, model=model, reasoning_effort=reasoning_effort)
    profile_block = prompt_profile_block(provider=provider, model=model, reasoning_effort=reasoning_effort, audience="manager")
    gpu_block = _gpu_mode_block(project)
    tensorflow_block = _tensorflow_mode_block(project)
    pytorch_block = _pytorch_mode_block(project)
    action_bias_block = "\n".join(f"- {rule}" for rule in [*_manager_action_biases(action, profile), *_project_state_biases(project, action=action)])
    task_bias_section = f"\nTask-specific decision biases:\n{action_bias_block}" if action_bias_block else ""
    return f"""You are the Manager AI for Codex Mission Control.

Project: {project.name}
Project idea:
{project.idea}

Action: {action}
Objective:
{objective}

Preferred user name: {user_name or project.created_by or "Operator"}

{profile_block}

{gpu_block}

{tensorflow_block}
{pytorch_block}{task_bias_section}

Interview requirements:
- You are interviewing the user to gather project-specific requirements.
- Do not ask generic questions unless they are clearly relevant to this project.
- Use the project idea, current docs, tool availability, provider settings, prior answers, and known constraints.
- Ask the highest-impact unknowns first.
- Avoid asking about topics that are already answered or already confident enough.
- Every question must be multiple choice and materially affect implementation or handoff quality.
- Include "Not sure, recommend one" only when it genuinely helps unblock the user.
- Stop early when enough information exists to plan the project responsibly.
- Return only valid JSON matching the schema exactly.

Input payload:
{json.dumps(payload, indent=2, default=str)}

Response schema:
{json.dumps(response_schema, indent=2, default=str)}
"""


def manager_swarm_prompt(
    project: Project,
    *,
    payload: dict,
    response_schema: dict,
    user_name: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    profile = build_prompt_profile(provider=provider, model=model, reasoning_effort=reasoning_effort)
    profile_block = prompt_profile_block(provider=provider, model=model, reasoning_effort=reasoning_effort, audience="manager")
    gpu_block = _gpu_mode_block(project)
    tensorflow_block = _tensorflow_mode_block(project)
    pytorch_block = _pytorch_mode_block(project)
    action_bias_block = "\n".join(f"- {rule}" for rule in [*_manager_action_biases("swarm.plan", profile), *_project_state_biases(project, action="swarm.plan")])
    task_bias_section = f"\nTask-specific decision biases:\n{action_bias_block}" if action_bias_block else ""
    return f"""You are the Manager AI for Codex Mission Control.

Project: {project.name}
Project idea:
{project.idea}

Preferred user name: {user_name or project.created_by or "Operator"}

{profile_block}

{gpu_block}

{tensorflow_block}
{pytorch_block}{task_bias_section}

You are producing an adaptive swarm plan for this specific project.

Swarm planning rules:
- Choose the largest useful swarm, not the largest possible swarm.
- More agents are not automatically better.
- Avoid spawning vague agents or multiple agents that will obviously fight over the same files.
- Use the project idea, docs, repo shape, interview understanding, runner/tool limits, and project preferences.
- Multiple agents from the same archetype are allowed only when they have distinct missions and path ownership.
- Give each specialist an explicit iteration budget so optimization and review loops do not run forever.
- Documentation-heavy projects may use multiple docs specialists.
- High-quality projects should emphasize review, testing, and security.
- Massive codebases should assign subsystem or path ownership before aggressive parallel edits.
- If architecture is still unclear, bias toward planner, architect, and research help before broad implementation parallelism.
- Explain the strategy, coordination risk, path conflict risk, and likely bottlenecks.
- Return only valid JSON matching the schema exactly.

Input payload:
{json.dumps(payload, indent=2, default=str)}

Response schema:
{json.dumps(response_schema, indent=2, default=str)}
"""


def app_server_input_items(text: str) -> list[dict]:
    return [{"type": "text", "text": text}]


def docs_manifest_path(project: Project) -> Path:
    return Path(project.docs_path or "") / "MANIFEST.json"
