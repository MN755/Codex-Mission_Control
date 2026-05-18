from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "plugins" / "mission-control" / "skills"
PLUGIN_MANIFEST = ROOT / "plugins" / "mission-control" / "plugin.json"
INDEX_PATH = ROOT / "plugins" / "mission-control" / "SKILL_INDEX.md"
DOC_PATH = ROOT / "docs" / "MISSION_CONTROL_SKILL_LIBRARY.md"
README_PATH = ROOT / "plugins" / "mission-control" / "README.md"
INSTALL_DOC_PATH = ROOT / "docs" / "CODEX_PLUGIN_INSTALL.md"

BRIDGE_STATEMENT = "The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager."

SKILLS: list[dict[str, object]] = [
    {
        "name": "mission-control-orchestrate",
        "description": "Primary Mission Control entrypoint for the current workspace. Use when the user says to use Mission Control, have Mission Control manage the repo, run the task through the Manager, or switch this chat into Mission Control bridge mode.",
        "purpose": "Use Mission Control as the orchestrator for the current workspace and keep Codex in the bridge role.",
        "use_when": [
            "The user says to use Mission Control for this repo.",
            "The user wants Manager-led orchestration instead of direct local coding.",
            "A new Mission Control task should be attached, started, monitored, and handed back through chat.",
        ],
        "workflow": [
            "Determine the current workspace path or project reference.",
            "Call `mission_control_attach_workspace` to register or reuse the project.",
            "Call `mission_control_start_task` with the user request.",
            "Return a compact status summary from the status tool or resource.",
            "Check `mission_control_get_pending_decisions` and relay any approvals or questions.",
            "Poll only when useful instead of spamming status.",
            "Retrieve handoff through `mission_control_get_handoff` or `mission_control_get_handoff_summary` when complete.",
        ],
        "tools": [
            "`mission_control_attach_workspace`",
            "`mission_control_start_task`",
            "`mission_control_get_status`",
            "`mission_control_get_pending_decisions`",
            "`mission_control_get_handoff`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/pending-decisions`",
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://orchestrations/{orchestration_id}/status`",
        ],
        "output": [
            "Report the attached project or orchestration identifier.",
            "Show current state, pending decisions, blockers, and next checkpoint.",
            "When done, summarize the handoff with evidence level and limitations.",
        ],
        "approval": "Relay every pending approval or Manager question to the user. Do not continue past approval gates with guessed answers.",
        "never": [
            "Do not act as the Manager directly.",
            "Do not independently spawn worker agents.",
            "Do not bypass Mission Control approvals or write-permission gates.",
        ],
        "fallback": "If Mission Control tools or the bridge are unavailable, say so clearly, offer the direct local-coding fallback only with user awareness, and avoid pretending orchestration happened.",
        "example": "Use Mission Control for this repo and fix the failing tests.",
    },
    {
        "name": "mission-control-import-codebase",
        "description": "Import or attach an existing codebase into Mission Control. Use when the workspace already contains a repo and Codex should let Mission Control scan, understand, and classify it before edits.",
        "purpose": "Import an existing repo safely and let Mission Control build understanding before execution.",
        "use_when": [
            "The folder is non-empty and looks like a real codebase.",
            "The user wants Mission Control to take over an existing repo.",
            "You need codebase understanding before planning or writing.",
        ],
        "workflow": [
            "Attach the current workspace with `mission_control_attach_workspace`.",
            "Use `mission_control_import_existing_codebase` or the import prompt path for non-empty folders.",
            "Request a read-only scan first.",
            "Retrieve the codebase map and understanding summary.",
            "Ask whether to skip interview, quick clarify, full interview, or let the Manager decide.",
            "Start the requested task only after the understanding path is chosen.",
        ],
        "tools": [
            "`mission_control_attach_workspace`",
            "`mission_control_import_existing_codebase`",
            "`mission_control_get_status`",
            "`mission_control_start_task`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/codebase-map`",
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Summarize what Mission Control learned about the stack and entry points.",
            "Show the available intake choices: skip, quick clarify, full interview, or Manager decides.",
            "Report the project identifier and safest next step.",
        ],
        "approval": "Ask before any write-capable step, import permission change, or interview-skipping choice that materially changes assumptions.",
        "never": [
            "Do not run builds, installs, or tests during initial scan unless the user explicitly wants that.",
            "Do not expose `.env` contents or secrets.",
            "Do not skip understanding and jump into edits.",
        ],
        "fallback": "If import tooling is missing, attach the workspace, explain that import-specific tooling is expected or future, and rely on read-only codebase resources where available.",
        "example": "Attach this existing repo to Mission Control, scan it read-only, and then let the Manager decide how to proceed.",
    },
    {
        "name": "mission-control-status",
        "description": "Give a clean Mission Control status update. Use when the user asks for current progress, blockers, active agents, pending decisions, next step, or handoff readiness without wanting raw logs.",
        "purpose": "Return a bridge-safe Mission Control status summary.",
        "use_when": [
            "The user asks for status, progress, blockers, or what happens next.",
            "A long-running orchestration needs a concise checkpoint.",
            "The user wants a summary without opening dashboard UI or logs.",
        ],
        "workflow": [
            "Call `mission_control_get_status` or read the project or orchestration status resource.",
            "Read active agents and pending decisions resources.",
            "Identify Manager state, blockers, next expected step, and handoff readiness.",
            "Return a concise summary without event spam or raw logs.",
        ],
        "tools": ["`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://orchestrations/{orchestration_id}/status`",
            "`mission-control://projects/{project_id}/agents`",
            "`mission-control://projects/{project_id}/pending-decisions`",
            "`mission-control://projects/{project_id}/handoff`",
        ],
        "output": [
            "Include project, orchestration state, Manager state, active agents, pending decisions, blockers, next step, and handoff readiness.",
            "Keep the summary short enough for chat and safe enough for copy-paste.",
        ],
        "approval": "Status reads should be read-only. If the user asks to act on the status, switch to the matching approval, pause, resume, or stop skill.",
        "never": [
            "Do not dump raw logs.",
            "Do not invent progress if the backend is stale.",
            "Do not hide blockers to sound smoother.",
        ],
        "fallback": "If only partial resources are available, say which pieces are missing and summarize only what is backed by the resource or tool output.",
        "example": "Give me a Mission Control status update for this workspace.",
    },
    {
        "name": "mission-control-approve",
        "description": "Relay Mission Control approvals and questions to the user. Use when there are pending command approvals, tool approvals, write permissions, Manager questions, swarm approvals, recovery decisions, or handoff review gates.",
        "purpose": "Present pending Mission Control decisions clearly and relay the user response back safely.",
        "use_when": [
            "A pending decision blocks progress.",
            "The user asks what needs approval.",
            "Mission Control is waiting on user input.",
        ],
        "workflow": [
            "Fetch pending decisions with `mission_control_get_pending_decisions` or the pending-decisions resource.",
            "Render the top decision with reason, risk, options, and any relevant scope.",
            "Ask the user to choose when no answer is provided.",
            "Call `mission_control_answer_decision` with the selected answer.",
            "Confirm the updated status.",
        ],
        "tools": ["`mission_control_get_pending_decisions`", "`mission_control_answer_decision`"],
        "resources": [
            "`mission-control://projects/{project_id}/pending-decisions`",
            "`mission-control://orchestrations/{orchestration_id}/status`",
        ],
        "output": [
            "Identify the decision type: command approval, tool approval, write permission, Manager question, swarm approval, snapshot approval, handoff review, recovery decision, or scope change decision.",
            "Explain the risk and the likely impact of each option.",
            "Confirm whether the decision was accepted, denied, deferred, or still pending.",
        ],
        "approval": "This skill exists to preserve approvals. Never auto-answer a pending decision unless Mission Control explicitly marks it safe and the user already delegated that choice.",
        "never": [
            "Do not answer on the user's behalf.",
            "Do not hide the risk level.",
            "Do not bypass write-permission or swarm approval gates.",
        ],
        "fallback": "If decision-answer tooling is unavailable, present the pending decision textually and tell the user that manual resolution through the expected tool is still required.",
        "example": "Show me the pending Mission Control approval and let me choose.",
    },
    {
        "name": "mission-control-handoff",
        "description": "Retrieve and present the final Mission Control handoff. Use when the user asks for the finished result, final summary, what changed, how to run it, evidence, limitations, or next tasks.",
        "purpose": "Present the Mission Control handoff as a clean, evidence-aware final summary.",
        "use_when": [
            "The orchestration is complete or near complete.",
            "The user asks for the handoff or final report.",
            "You need to verify what changed and what evidence backs it.",
        ],
        "workflow": [
            "Call `mission_control_get_handoff` or `mission_control_get_handoff_summary`.",
            "Read the handoff resource for status, evidence level, and limitations.",
            "Summarize what changed, how to run, validation or evidence, important files, and next tasks.",
            "Warn explicitly if the run was dry-run, incomplete, or weakly evidenced.",
        ],
        "tools": ["`mission_control_get_handoff`", "`mission_control_get_handoff_summary`"],
        "resources": [
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Show status, confidence or evidence level, what changed, how to run, validation or evidence, known limitations, recommended next tasks, and important files or artifacts.",
            "Warn if tests were not run, evidence is missing, the handoff is incomplete, or the run was dry-run.",
        ],
        "approval": "If the handoff requires explicit review or sign-off, relay that approval instead of declaring the work accepted.",
        "never": [
            "Do not present a partial report as finished.",
            "Do not suppress missing evidence.",
            "Do not claim Codex performed the work directly.",
        ],
        "fallback": "If no handoff exists yet, say so directly, provide the current status, and point the user to the blocking approvals or remaining tasks.",
        "example": "Get the Mission Control handoff and summarize what changed.",
    },
    {
        "name": "mission-control-debug",
        "description": "Diagnose stuck or failed Mission Control orchestration. Use when runs are blocked, failing repeatedly, waiting too long, missing evidence, or unclear about the next recovery step.",
        "purpose": "Diagnose stuck or failed orchestration and surface recovery options.",
        "use_when": [
            "The user says the run is stuck or broken.",
            "Status looks stalled.",
            "Approvals, diagnostics, or event summaries need to be correlated.",
        ],
        "workflow": [
            "Fetch status with `mission_control_get_status`.",
            "Fetch pending decisions with `mission_control_get_pending_decisions`.",
            "Fetch diagnostics and recent event digest.",
            "Ask Mission Control for a recovery plan if available.",
            "Summarize blocker, likely causes, and next options.",
        ],
        "tools": [
            "`mission_control_get_status`",
            "`mission_control_get_pending_decisions`",
            "`mission_control_get_event_digest`",
            "`mission_control_request_recovery_plan`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/diagnostics`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "State the main blocker, supporting evidence, pending approvals, and recommended next options.",
            "Keep diagnostics summarized; do not paste raw logs by default.",
        ],
        "approval": "If recovery choices may retry commands, widen scope, or restart work, relay the decision to the user before acting.",
        "never": [
            "Do not freehand a recovery action that Mission Control has not approved.",
            "Do not dump raw logs or secrets.",
            "Do not say the system is healthy when diagnostics disagree.",
        ],
        "fallback": "If recovery tooling is missing, summarize the failure from status, diagnostics, and events, and clearly mark recovery-plan tooling as expected or future.",
        "example": "Mission Control looks stuck. Diagnose it and show my options.",
    },
    {
        "name": "mission-control-swarm",
        "description": "Inspect or adjust Mission Control swarm behavior. Use when the user wants to show the swarm plan, explain agent roles, scale up or down, change strategy, pause dynamic spawning, resume dynamic spawning, or inspect active agents.",
        "purpose": "Inspect the swarm plan and route any swarm changes through Mission Control.",
        "use_when": [
            "The user asks how the swarm is organized.",
            "The user wants to scale up, scale down, or switch swarm strategy.",
            "Agent activity needs a coordinated explanation.",
        ],
        "workflow": [
            "Read the swarm plan and active agents resources.",
            "Explain current swarm shape, role assignments, ownership boundaries, and approvals.",
            "If the user requests a change, route it through Mission Control tools or prompts.",
            "Require explicit approval before scaling above the configured threshold or changing risk posture.",
        ],
        "tools": [
            "`mission_control_get_status`",
            "`mission_control_start_task` (for swarm-change requests)",
            "`mission_control_pause` and `mission_control_resume` when pausing or resuming swarm activity is supported",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/swarm-plan`",
            "`mission-control://projects/{project_id}/agents`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Show swarm plan, active agents, ownership boundaries, approval state, and any scaling warnings.",
            "If change is requested, explain what Mission Control will need from the user next.",
        ],
        "approval": "Never scale above threshold, broaden write scope, or change dynamic spawning policy without user approval or an explicit Mission Control approval record.",
        "never": [
            "Do not invent your own swarm topology.",
            "Do not spawn workers outside Mission Control.",
            "Do not bypass swarm approvals.",
        ],
        "fallback": "If direct swarm controls are not exposed yet, explain the current swarm from resources and treat any adjustment as an expected or future Mission Control task request.",
        "example": "Show the swarm plan and explain whether we should scale up.",
    },
    {
        "name": "mission-control-safe-mode",
        "description": "Put Mission Control into strict safety mode. Use when the user wants maximum approval gating, read-only imports, destructive-action blocking, deployment blocking, or tighter external-tool controls.",
        "purpose": "Request or explain Mission Control strict safety mode for the project.",
        "use_when": [
            "The user wants every command approved.",
            "The workspace is risky or unfamiliar.",
            "The user wants deployments and external account tools disabled by default.",
        ],
        "workflow": [
            "Explain what safe mode changes: strict approvals, destructive-action blocking, deployment blocking, and read-only import behavior.",
            "Call `mission_control_enable_safe_mode` if available.",
            "Re-check status and pending decisions after the mode change.",
            "Confirm which restrictions are active and which remain expected or future.",
        ],
        "tools": ["`mission_control_enable_safe_mode`", "`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/pending-decisions`",
            "`mission-control://projects/{project_id}/swarm-plan`",
        ],
        "output": [
            "Show the enabled restrictions and any unsupported controls that are still expected or future.",
            "Tell the user how approvals will look different after safe mode.",
        ],
        "approval": "Treat safe-mode entry or exit as a meaningful policy change and confirm it with the user before changing the project posture.",
        "never": [
            "Do not claim safe mode is active without a backed status change.",
            "Do not weaken safety controls silently.",
            "Do not keep dynamic spawning active if the user asked to pause it and the backend supports that control.",
        ],
        "fallback": "If full safe-mode tooling is not implemented, document the intended restrictions in chat, mark them as expected or future, and continue operating conservatively.",
        "example": "Put this Mission Control project into strict safe mode.",
    },
    {
        "name": "mission-control-resume",
        "description": "Resume an existing Mission Control orchestration from a new Codex chat. Use when the user returns later and wants Codex to reattach, find the active or recent orchestration, show state, surface pending decisions, and continue safely.",
        "purpose": "Reattach Codex chat to an existing Mission Control run and continue safely.",
        "use_when": [
            "The user returns in a new chat and says to continue Mission Control.",
            "An existing workspace already has recent orchestration state.",
            "You need to find the last known state before acting.",
        ],
        "workflow": [
            "Attach the current workspace.",
            "Find the active or recent orchestration from status resources or the attach result.",
            "Return the last known state, active agents, blockers, and pending decisions.",
            "Resume through `mission_control_resume` only if the run is paused and it is safe to do so.",
            "If already running, summarize instead of issuing duplicate resume actions.",
        ],
        "tools": [
            "`mission_control_attach_workspace`",
            "`mission_control_get_status`",
            "`mission_control_get_pending_decisions`",
            "`mission_control_resume`",
        ],
        "resources": [
            "`mission-control://orchestrations/{orchestration_id}/status`",
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Show the recovered project or orchestration reference, last known phase, pending decisions, and whether a resume action is still needed.",
            "If safe to resume, confirm the post-resume state.",
        ],
        "approval": "Do not resume if pending approvals would immediately block or if the user has not confirmed a risky restart choice.",
        "never": [
            "Do not start a new orchestration when a resume is the right path.",
            "Do not claim recovery if no prior project can be found.",
            "Do not override paused state without checking why it was paused.",
        ],
        "fallback": "If active-or-recent orchestration lookup is limited, attach the workspace, report the latest project status you can find, and ask the user whether to resume manually through the expected Mission Control control surface.",
        "example": "Resume the existing Mission Control run for this workspace.",
    },
    {
        "name": "mission-control-agents-md",
        "description": "Generate or review AGENTS.md from Mission Control understanding. Use when the user wants AGENTS.md proposed from the codebase map, existing instructions reviewed, or a safe draft prepared before writing.",
        "purpose": "Use Mission Control understanding to propose or review AGENTS.md safely.",
        "use_when": [
            "The user asks for AGENTS.md generation or review.",
            "A repo needs agent instructions grounded in actual codebase structure.",
            "You need to compare existing AGENTS.md guidance against Mission Control understanding.",
        ],
        "workflow": [
            "Read the codebase map resource.",
            "Check AGENTS.md status or proposal tooling.",
            "Call `mission_control_generate_agents_md` or the proposal path when available.",
            "Summarize proposed sections and ask before writing any file changes.",
        ],
        "tools": ["`mission_control_generate_agents_md`"],
        "resources": [
            "`mission-control://projects/{project_id}/codebase-map`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Include project overview, setup commands, run commands, test commands, build commands, architecture notes, coding rules, do-not-touch areas, safety rules, and completion report format.",
            "Tell the user whether the result is a proposal or a written file.",
        ],
        "approval": "Always ask before writing or replacing AGENTS.md, even if the proposal looks good.",
        "never": [
            "Do not invent setup commands that are not backed by the repo or Mission Control understanding.",
            "Do not overwrite existing AGENTS.md silently.",
            "Do not expose secret paths or tokens.",
        ],
        "fallback": "If AGENTS.md tooling is not available, use the codebase map to produce a bridge-safe draft summary and clearly mark file generation as expected or future.",
        "example": "Use Mission Control to propose an AGENTS.md for this repo.",
    },
    {
        "name": "mission-control-plan",
        "description": "Ask Mission Control Manager to create or revise a plan. Use when the user asks for a plan, scope changes, imported codebases need planning, or the next milestone and validation strategy need clarification before execution.",
        "purpose": "Request a Mission Control plan or plan revision without taking over planning directly.",
        "use_when": [
            "The user asks for a plan.",
            "Scope changes require replanning.",
            "A codebase was imported and needs structured milestones before execution.",
        ],
        "workflow": [
            "Check current status and swarm plan resources first.",
            "Ask Mission Control Manager to create or revise the plan through `mission_control_start_task` or plan-specific workflow prompts.",
            "Return the plan summary with milestones, validation strategy, swarm strategy, and needed user decisions.",
            "If the plan implies approvals, surface them instead of auto-applying them.",
        ],
        "tools": ["`mission_control_get_status`", "`mission_control_start_task`"],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/swarm-plan`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Show goal, assumptions, milestones, validation strategy, swarm strategy, risks, and user decisions needed.",
            "Call out whether the plan is new, revised, approved, or waiting on feedback.",
        ],
        "approval": "If the plan changes scope, cost, model policy, or swarm scale, get user approval before asking Mission Control to execute it.",
        "never": [
            "Do not silently replace the Manager's plan with your own.",
            "Do not claim approval status that Mission Control did not report.",
            "Do not skip surfaced assumptions.",
        ],
        "fallback": "If plan-specific tooling is thin, use status and swarm resources to summarize current planning state and route the actual plan request through the Manager-led task flow.",
        "example": "Ask Mission Control Manager for a plan for this imported repo.",
    },
    {
        "name": "mission-control-interview",
        "description": "Run a full Mission Control Manager interview. Use when the project is ambiguous, project-specific intake matters, or the user wants the Manager to ask clarifying questions with budgeted depth before planning or build work.",
        "purpose": "Run a full Manager-generated interview through Codex chat.",
        "use_when": [
            "The project is new or ambiguous.",
            "Important requirements are still unknown.",
            "The user wants the Manager to gather structured clarifications first.",
        ],
        "workflow": [
            "Attach or confirm the project context.",
            "Start the interview flow through Mission Control.",
            "Relay project-specific questions with category, why, impact, and options.",
            "Respect the question budget and let the Manager stop early when enough is known.",
            "Return the resulting interview state and next planning step.",
        ],
        "tools": ["`mission_control_attach_workspace`", "`mission_control_start_task`"],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Present each question cleanly with why it matters.",
            "Summarize answered themes, remaining unknowns, and whether the Manager believes the interview is complete.",
        ],
        "approval": "The user answers the interview questions directly. Do not auto-fill answers unless the user explicitly asks you to propose one.",
        "never": [
            "Do not fall back to a generic questionnaire if the repo already answers the question.",
            "Do not keep asking after the Manager has enough context.",
            "Do not answer for the user.",
        ],
        "fallback": "If a dedicated interview tool is not available, request clarifications through a Manager-led task and preserve the same structured question format in chat.",
        "example": "Have Mission Control run the full project interview before planning.",
    },
    {
        "name": "mission-control-skip-interview",
        "description": "Skip the Mission Control interview and proceed with assumptions. Use when speed matters more than full intake and the user accepts that the Manager will proceed with explicit unknowns and later corrections if needed.",
        "purpose": "Skip full interview while keeping assumptions visible and correctable.",
        "use_when": [
            "The user wants to move fast.",
            "The repo is already descriptive enough for a first pass.",
            "A small task does not justify a long interview.",
        ],
        "workflow": [
            "Confirm that the user wants to skip interview.",
            "Summarize the likely assumptions or missing requirements.",
            "Route the skip choice through Mission Control if an approval or intake choice exists.",
            "Continue to plan or build only after the skip choice is recorded.",
        ],
        "tools": [
            "`mission_control_get_status`",
            "`mission_control_get_pending_decisions`",
            "`mission_control_answer_decision`",
            "`mission_control_start_task`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/pending-decisions`",
            "`mission-control://projects/{project_id}/codebase-map`",
        ],
        "output": [
            "Show what is assumed, what remains unknown, and how the user can correct those assumptions later.",
            "Report whether the project is now moving to planning or build.",
        ],
        "approval": "Treat skipping interview as an explicit user choice because it changes intake fidelity.",
        "never": [
            "Do not hide uncertainty.",
            "Do not skip interview implicitly.",
            "Do not pretend a skipped interview is equivalent to answered requirements.",
        ],
        "fallback": "If skip-interview is not a first-class control, document the user's choice in chat, send it through the next Manager-facing task, and clearly mark the assumption list.",
        "example": "Skip the Mission Control interview and proceed with assumptions for this urgent fix.",
    },
    {
        "name": "mission-control-quick-clarify",
        "description": "Ask only a few high-impact Mission Control clarifying questions. Use when the user wants speed, the repo already explains most things, or the task is urgent and only 3–6 targeted questions are justified.",
        "purpose": "Run a short, high-impact clarification flow instead of a full interview.",
        "use_when": [
            "The user wants speed.",
            "The task is a small fix or focused enhancement.",
            "Existing repo context answers most questions already.",
        ],
        "workflow": [
            "Attach or confirm project context.",
            "Ask Mission Control for a quick-clarify intake rather than a full interview.",
            "Relay only 3 to 6 high-impact questions.",
            "Capture the answers and resume planning or execution.",
        ],
        "tools": ["`mission_control_attach_workspace`", "`mission_control_start_task`"],
        "resources": [
            "`mission-control://projects/{project_id}/codebase-map`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Show a compact question set, why those questions matter, and what the answers unlock.",
            "After answers, summarize the clarified assumptions and next step.",
        ],
        "approval": "User answers are required; do not invent them. If the user wants you to propose answers, label them as proposals, not facts.",
        "never": [
            "Do not drift into a full interview.",
            "Do not ask low-value generic questions.",
            "Do not ignore obvious answers already present in the repo or prior handoff.",
        ],
        "fallback": "If quick-clarify is not a dedicated tool yet, phrase the request through the Manager-led task flow and constrain it to the same short question budget.",
        "example": "Ask Mission Control only the 3 to 6 highest-impact questions for this repo.",
    },
    {
        "name": "mission-control-existing-repo-fix",
        "description": "Run a direct Mission Control fix workflow for an existing repo. Use when the task is a bugfix or targeted change in a non-empty codebase and the Manager should classify the request, plan narrowly, request write permission, and execute safely.",
        "purpose": "Route targeted fixes in an existing repo through Mission Control with minimal detours.",
        "use_when": [
            "The user wants a bug fixed in an existing folder.",
            "A targeted change should not trigger a blank-project flow.",
            "Write permission and codebase understanding both matter.",
        ],
        "workflow": [
            "Attach the workspace and import it as an existing codebase.",
            "Run or read a codebase scan.",
            "Ask the Manager to classify the request and create a targeted plan.",
            "Request write permission if Mission Control requires it.",
            "Run the orchestration and keep approvals flowing through chat.",
        ],
        "tools": [
            "`mission_control_attach_workspace`",
            "`mission_control_import_existing_codebase`",
            "`mission_control_start_task`",
            "`mission_control_get_pending_decisions`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/codebase-map`",
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Show the classified task type, narrow plan, write-permission status, and next checkpoint.",
            "Avoid giant repo tours unless the user asks for them.",
        ],
        "approval": "Write permission, risky commands, and scope expansions still need approval when Mission Control policy requires them.",
        "never": [
            "Do not treat a mature repo like a new greenfield project.",
            "Do not start editing before import safety is understood.",
            "Do not bypass approvals to move faster.",
        ],
        "fallback": "If repo-fix workflow tooling is partial, combine import-codebase, codebase-map, and Manager-led task flows and make the narrow-fix intent explicit.",
        "example": "Use Mission Control to fix this existing repo without doing a full greenfield setup flow.",
    },
    {
        "name": "mission-control-run-validation",
        "description": "Ask Mission Control to run or plan validation. Use when the user wants build, tests, typecheck, lint, smoke, docs check, or manual verification routed through Mission Control with approvals preserved.",
        "purpose": "Run or plan validation through Mission Control without bypassing approval policy.",
        "use_when": [
            "The user asks to validate work.",
            "A handoff needs stronger evidence.",
            "A refactor or fix should be checked before sign-off.",
        ],
        "workflow": [
            "Determine which validation types matter: build, tests, typecheck, lint, smoke, docs, or manual checks.",
            "Ask Mission Control to run or plan the validation set.",
            "Relay any command approvals required by policy.",
            "Return the validation summary and any gaps.",
        ],
        "tools": [
            "`mission_control_start_task`",
            "`mission_control_get_status`",
            "`mission_control_get_pending_decisions`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/validation-summary`",
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Show which validations were requested, which ran, which were skipped, and what evidence exists.",
            "Call out approval-blocked validations instead of implying they ran.",
        ],
        "approval": "Commands still need approvals when project policy requires them. This skill must preserve those gates rather than blur them.",
        "never": [
            "Do not claim tests ran if Mission Control never ran them.",
            "Do not bypass command approval rules.",
            "Do not hide validation gaps.",
        ],
        "fallback": "If a validation-summary resource does not exist yet, use status, event digest, and handoff evidence to build the summary and mark the dedicated resource as expected or future.",
        "example": "Ask Mission Control to run build, tests, and typecheck for this project.",
    },
    {
        "name": "mission-control-review-tests",
        "description": "Review Mission Control testing coverage and status. Use when the user wants to know what tests exist, what ran, what failed, what was skipped, or where validation coverage is still weak.",
        "purpose": "Summarize test coverage and validation status from Mission Control evidence.",
        "use_when": [
            "The user asks about tests.",
            "A handoff needs test-focused review.",
            "Coverage and evidence quality need a status check.",
        ],
        "workflow": [
            "Read validation-summary, handoff, and status resources.",
            "Identify available test commands, executed tests, skipped tests, failures, and gaps.",
            "Summarize recommended next tests if coverage is thin.",
        ],
        "tools": ["`mission_control_get_handoff_summary`", "`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/validation-summary`",
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Summarize available test commands, tests run, tests not run, failing tests, validation gaps, and recommended next tests.",
            "Highlight whether evidence is direct, dry-run, or missing.",
        ],
        "approval": "If the user wants new tests run and policy requires command approval, shift to the run-validation flow and preserve the approval gate.",
        "never": [
            "Do not grade coverage based on intuition alone.",
            "Do not hide missing evidence.",
            "Do not treat dry-run validation as equivalent to executed validation.",
        ],
        "fallback": "If dedicated validation resources are missing, build the summary from handoff evidence and current status, then clearly label any inference.",
        "example": "Review the test coverage and tell me what still needs validation.",
    },
    {
        "name": "mission-control-generate-runbook",
        "description": "Generate an operational runbook through Mission Control. Use when the user wants RUNBOOK.md or a chat-native runbook covering startup, tests, build, debugging, local reset, logs, and deployment notes.",
        "purpose": "Generate or summarize a runbook grounded in Mission Control evidence and repo understanding.",
        "use_when": [
            "The user wants a runbook.",
            "A handoff should include stronger operational guidance.",
            "Support or onboarding documentation is needed.",
        ],
        "workflow": [
            "Read codebase map and handoff resources.",
            "Ask Mission Control to generate a runbook or prepare a runbook summary.",
            "Present the proposed sections and ask before writing any file.",
        ],
        "tools": ["`mission_control_get_handoff_summary`", "`mission_control_start_task`"],
        "resources": [
            "`mission-control://projects/{project_id}/codebase-map`",
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Cover start dev server, run tests, build, debug common failures, reset local state, logs, and deployment if configured.",
            "Tell the user whether the result is chat-only or ready to write to `RUNBOOK.md`.",
        ],
        "approval": "Ask before writing or overwriting runbook files.",
        "never": [
            "Do not invent commands that are not backed by the repo or handoff.",
            "Do not write files silently.",
            "Do not expose raw logs.",
        ],
        "fallback": "If runbook generation is not exposed yet, use handoff and codebase understanding to produce a chat-native runbook and mark file generation as expected or future.",
        "example": "Use Mission Control to generate a runbook for this repo.",
    },
    {
        "name": "mission-control-explain-codebase",
        "description": "Explain an unfamiliar codebase from Mission Control understanding. Use when the user wants stack detection, structure, entry points, how it likely runs, how tests work, risky areas, or recommended exploration next.",
        "purpose": "Explain the codebase from Mission Control resources without doing ad hoc repo archaeology first.",
        "use_when": [
            "The user asks what this repo is.",
            "An imported codebase needs a plain-English explanation.",
            "You need a safe overview before deeper work.",
        ],
        "workflow": [
            "Read codebase-map and status resources.",
            "Extract stack, structure, entry points, likely runtime path, test setup, and risky or unknown areas.",
            "Return a compact explanation and suggested next exploration.",
        ],
        "tools": ["`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/codebase-map`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Include detected stack, structure, entry points, how it likely runs, how tests work, risky or unknown areas, and suggested next exploration.",
            "Keep it at summary level unless the user asks for file-by-file detail.",
        ],
        "approval": "This is a read-only explanation. If the user wants edits afterward, switch back to Mission Control task execution with normal approvals.",
        "never": [
            "Do not dump whole file contents by default.",
            "Do not pretend uncertain areas are settled.",
            "Do not skip the codebase map if it exists.",
        ],
        "fallback": "If codebase understanding is incomplete, say what is known, what is inferred, and what still needs a deeper Mission Control scan.",
        "example": "Explain this codebase using Mission Control understanding.",
    },
    {
        "name": "mission-control-refactor-safely",
        "description": "Run a safe Mission Control refactor workflow. Use when the user wants non-trivial refactors that need codebase understanding, snapshots, path locks, contracts, validation planning, and controlled risk.",
        "purpose": "Route refactors through Mission Control safety controls before code movement begins.",
        "use_when": [
            "The user asks for a refactor.",
            "Changes may span multiple files or subsystems.",
            "Risk mitigation and validation planning matter.",
        ],
        "workflow": [
            "Require codebase understanding first.",
            "Request a snapshot or restore point if supported.",
            "Check path locks and agent contracts.",
            "Ask Mission Control for a validation plan before execution.",
            "Run the refactor only after approvals and safety boundaries are clear.",
            "Use the handoff to summarize changed files and residual risks.",
        ],
        "tools": [
            "`mission_control_request_snapshot`",
            "`mission_control_start_task`",
            "`mission_control_get_status`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/codebase-map`",
            "`mission-control://projects/{project_id}/path-locks`",
            "`mission-control://projects/{project_id}/agent-contracts`",
            "`mission-control://projects/{project_id}/validation-summary`",
        ],
        "output": [
            "Show whether understanding exists, whether a snapshot was requested, how validation will run, and what boundaries the refactor will respect.",
            "After completion, summarize changed files, validation results, and remaining risks.",
        ],
        "approval": "Require explicit approval for broad rewrites, risky snapshots, or destructive restore steps.",
        "never": [
            "Do not attempt a broad rewrite without understanding and validation.",
            "Do not restore or revert destructively without approval.",
            "Do not ignore path-lock or contract conflicts.",
        ],
        "fallback": "If snapshot, path-lock, or contract resources are not fully implemented, make those missing protections explicit and let the user decide whether to proceed with reduced guarantees.",
        "example": "Use Mission Control to refactor this module safely with validation and rollback planning.",
    },
    {
        "name": "mission-control-security-review",
        "description": "Ask Mission Control for a security review. Use when the user wants secrets risk, auth risk, dependency risk, command safety, file permission risk, deployment exposure, risky code patterns, or remediation planning summarized through Mission Control.",
        "purpose": "Request or summarize a Mission Control security review without exposing secrets.",
        "use_when": [
            "The user asks for a security review.",
            "A release or handoff should include security posture.",
            "A risky codebase needs threat-focused triage.",
        ],
        "workflow": [
            "Request a security review through Mission Control.",
            "Read status, diagnostics, and risk resources.",
            "Summarize the findings across secrets, auth, dependencies, permissions, deployment exposure, and risky patterns.",
            "Return remediation steps and any user decisions needed.",
        ],
        "tools": ["`mission_control_start_task`", "`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/risk-register`",
            "`mission-control://projects/{project_id}/diagnostics`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Cover secrets risk, auth or session issues, dependency risk, command safety, file permission risk, deployment exposure, risky code patterns, and remediation plan.",
            "Keep secrets redacted and findings bridge-safe.",
        ],
        "approval": "If remediation implies destructive changes, deployment toggles, or tool-policy changes, present them as approvals rather than applying them silently.",
        "never": [
            "Do not paste secrets or vulnerable payloads into chat.",
            "Do not claim a clean bill of health without evidence.",
            "Do not replace a real review with vague reassurance.",
        ],
        "fallback": "If dedicated security review tooling is not exposed yet, route the request through Manager-led task execution and summarize backed findings from risk and diagnostics resources.",
        "example": "Ask Mission Control for a security review of this project.",
    },
    {
        "name": "mission-control-docs-heavy",
        "description": "Switch the project toward documentation-heavy Mission Control work. Use when the user wants the swarm or plan to prioritize README, guides, examples, docs review, or public-facing written material more than feature code.",
        "purpose": "Bias Mission Control toward documentation-heavy execution without directly spawning doc writers from chat.",
        "use_when": [
            "The user wants documentation first.",
            "The repo needs README, guides, examples, or API docs work.",
            "Release or public publication depends on better docs.",
        ],
        "workflow": [
            "Review current handoff, plan, and swarm resources.",
            "Ask Mission Control to prioritize docs-heavy work and the relevant agent roles or milestones.",
            "Explain what documentation areas will be emphasized and what approvals may be needed.",
        ],
        "tools": ["`mission_control_start_task`", "`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/swarm-plan`",
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Identify the desired doc roles: README writer, user guide writer, developer guide writer, API docs writer, examples writer, or docs reviewer.",
            "Summarize the docs-heavy objective and next checkpoint.",
        ],
        "approval": "If docs-heavy mode changes swarm scale, write scope, or release posture, get user approval through Mission Control before execution.",
        "never": [
            "Do not spawn documentation agents yourself.",
            "Do not confuse docs priority with UI work.",
            "Do not claim public readiness without review.",
        ],
        "fallback": "If docs-mode controls are not first-class yet, express the priority as a Manager-led task request and track it through status and handoff outputs.",
        "example": "Switch this Mission Control project into docs-heavy mode.",
    },
    {
        "name": "mission-control-github-ready-docs",
        "description": "Prepare Mission Control docs for public GitHub. Use when documentation should be cleaned for publication, internal AI notes removed, secrets and private paths scrubbed, and install or run guidance made public-ready.",
        "purpose": "Prepare documentation for a public GitHub audience through Mission Control-aware review.",
        "use_when": [
            "The repo may go public.",
            "The user wants README-friendly documentation.",
            "Docs need secret and private-path cleanup before sharing.",
        ],
        "workflow": [
            "Review handoff, codebase map, and current docs outputs.",
            "Ask Mission Control to prepare GitHub-ready docs or treat the request as a docs-heavy change set.",
            "Summarize what will be cleaned, added, or redacted before any file write.",
        ],
        "tools": ["`mission_control_start_task`", "`mission_control_get_handoff_summary`"],
        "resources": [
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/codebase-map`",
            "`mission-control://projects/{project_id}/risk-register`",
        ],
        "output": [
            "Call out removal of internal AI notes, secrets, and private paths.",
            "Include install, run, test, limitations, and screenshot-placeholder expectations if relevant.",
        ],
        "approval": "Ask before overwriting public-facing docs or removing existing internal notes that the user still wants preserved elsewhere.",
        "never": [
            "Do not leak private paths or tokens.",
            "Do not leave internal-only AI workflow notes in public docs.",
            "Do not claim screenshots or examples exist if they do not.",
        ],
        "fallback": "If no dedicated docs-publication tool exists, route the task through Mission Control with a docs-heavy and GitHub-ready objective, then summarize the planned cleanup items.",
        "example": "Use Mission Control to make the docs GitHub-ready.",
    },
    {
        "name": "mission-control-release-prep",
        "description": "Prepare a project for release through Mission Control. Use when validation, docs, versioning, changelog, limitations, evidence, deployment readiness, and security concerns need one coordinated release-prep review.",
        "purpose": "Coordinate release-prep review through Mission Control without skipping evidence or approvals.",
        "use_when": [
            "The user asks if the project is ready to ship.",
            "A release candidate needs a final checklist.",
            "Docs, validation, and security all need coordinated review.",
        ],
        "workflow": [
            "Review handoff, validation, risk, and status resources.",
            "Ask Mission Control for a release-prep pass if needed.",
            "Summarize validation, docs, versioning, changelog, limitations, evidence, deployment readiness, and security concerns.",
            "Surface any remaining approvals or blockers.",
        ],
        "tools": [
            "`mission_control_start_task`",
            "`mission_control_get_handoff_summary`",
            "`mission_control_get_status`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/validation-summary`",
            "`mission-control://projects/{project_id}/risk-register`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Give a release-readiness summary and list unresolved blockers.",
            "Be specific about whether versioning, changelog, docs, and security are complete or still thin.",
        ],
        "approval": "If release-prep implies deployments, publishing, or policy shifts, keep those actions behind explicit approvals.",
        "never": [
            "Do not announce release readiness without evidence.",
            "Do not skip limitations or unresolved risks.",
            "Do not publish anything from chat directly.",
        ],
        "fallback": "If release-prep is not a dedicated workflow yet, synthesize the checklist from the available resources and clearly mark missing evidence.",
        "example": "Use Mission Control to do a release-prep review for this project.",
    },
    {
        "name": "mission-control-scope-creep-check",
        "description": "Ask Mission Control whether the project is drifting beyond approved scope. Use when the task list is growing, the user asks for more work midstream, or you need a Manager recommendation on include now versus defer.",
        "purpose": "Check for scope creep and preserve explicit include-now versus defer decisions.",
        "use_when": [
            "Requirements are expanding.",
            "The user asks for additional work midstream.",
            "You need the Manager's scope recommendation.",
        ],
        "workflow": [
            "Read status, plan, and risk or decision resources.",
            "Ask Mission Control to evaluate whether the work is beyond approved scope.",
            "Summarize detected scope changes, severity, include-now or defer options, and Manager recommendation.",
        ],
        "tools": ["`mission_control_start_task`", "`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/decision-ledger`",
            "`mission-control://projects/{project_id}/risk-register`",
        ],
        "output": [
            "Show detected scope changes, severity, suggested milestone placement, and the Manager recommendation.",
            "Tell the user what new approvals or replanning may be required.",
        ],
        "approval": "Treat scope expansion as a decision, not an assumption. Get the user's choice before broader execution begins.",
        "never": [
            "Do not quietly absorb major scope changes.",
            "Do not understate schedule or risk impact.",
            "Do not override the user's scoping decision.",
        ],
        "fallback": "If no dedicated scope-creep signal exists, use decision and risk resources plus current status to frame the analysis and label the recommendation source clearly.",
        "example": "Check whether this Mission Control project is drifting beyond scope.",
    },
    {
        "name": "mission-control-risk-register",
        "description": "Show or update the Mission Control risk register. Use when the user wants top risks, severity, likelihood, mitigation, owners, or current risk status summarized through Mission Control resources.",
        "purpose": "Surface the project risk register and related mitigation posture.",
        "use_when": [
            "The user asks for project risks.",
            "Release or recovery planning needs risk visibility.",
            "A plan or handoff should include mitigation state.",
        ],
        "workflow": [
            "Read the risk-register resource.",
            "Summarize top risks, severity, likelihood, mitigation, owner, and status.",
            "If the user wants changes, route them through Mission Control change or planning workflows rather than editing the register ad hoc.",
        ],
        "tools": ["`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/risk-register`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Provide a compact ranked view of top risks and mitigations.",
            "Identify which risks are active blockers versus watch items.",
        ],
        "approval": "If the user wants risk posture changes that affect execution policy, treat them as planning or tool-policy approvals.",
        "never": [
            "Do not invent risk owners or mitigation status.",
            "Do not pretend the risk register exists if it does not.",
            "Do not hide severe risks for convenience.",
        ],
        "fallback": "If no risk-register resource exists yet, summarize known risks from handoff, diagnostics, and decision resources and mark the register as expected or future.",
        "example": "Show the Mission Control risk register for this project.",
    },
    {
        "name": "mission-control-decision-ledger",
        "description": "Show important Mission Control decisions and assumptions. Use when the user wants to review user decisions, Manager assumptions, auto-decisions, rejected options, or approval history without searching raw events.",
        "purpose": "Summarize the project decision ledger and assumption trail.",
        "use_when": [
            "The user asks why a choice was made.",
            "A plan or handoff should surface assumptions.",
            "Approval history matters for auditability.",
        ],
        "workflow": [
            "Read the decision-ledger resource and current status.",
            "Summarize user decisions, Manager assumptions, auto-decisions, rejected options, and approval history.",
            "If clarification is needed, point to the pending-decision or plan revision flow.",
        ],
        "tools": ["`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/decision-ledger`",
            "`mission-control://projects/{project_id}/pending-decisions`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "List key decisions with impact and current status.",
            "Highlight assumptions that are still provisional or unconfirmed.",
        ],
        "approval": "If the ledger shows unresolved decisions, route the user to the approval skill instead of guessing.",
        "never": [
            "Do not rewrite history.",
            "Do not flatten rejected options into accepted ones.",
            "Do not hide assumptions that affect outcome quality.",
        ],
        "fallback": "If a dedicated decision-ledger resource is not yet exposed, summarize from pending decisions, plan state, and handoff notes and mark the ledger resource as expected or future.",
        "example": "Show the Mission Control decision ledger and assumptions.",
    },
    {
        "name": "mission-control-context-pack",
        "description": "Show or build Mission Control context packs for agents. Use when the user wants to know which files, docs, and constraints are being packaged for a task, why they were selected, and where context coverage is still missing.",
        "purpose": "Explain or request context-pack generation for Mission Control work.",
        "use_when": [
            "The user asks what context an agent got.",
            "A task seems under-contextualized.",
            "You need to explain token and file selection boundaries.",
        ],
        "workflow": [
            "Read codebase, status, and any context-pack summaries that exist.",
            "Explain which files or docs are included, for which target task or agent, and why.",
            "If the user requests a new pack, route it through Mission Control rather than assembling it manually in chat.",
        ],
        "tools": ["`mission_control_start_task`", "`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/codebase-map`",
            "`mission-control://projects/{project_id}/agent-contracts`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Summarize included context, missing context, target agent or task, and any token-budget pressure.",
            "Explain whether the pack is existing, proposed, or expected or future.",
        ],
        "approval": "If the user asks to widen context into sensitive areas, confirm that choice and respect Mission Control safety boundaries.",
        "never": [
            "Do not manually stuff chat with giant file dumps as a fake context pack.",
            "Do not expose secret-bearing files.",
            "Do not pretend a context pack exists if it does not.",
        ],
        "fallback": "If no explicit context-pack tooling exists, infer the likely pack from codebase map and contracts, then label that inference clearly.",
        "example": "Explain the Mission Control context pack for the current task.",
    },
    {
        "name": "mission-control-agent-contracts",
        "description": "Show or request Mission Control agent contracts. Use when the user wants to inspect a worker mission, allowed paths, forbidden paths, tools, validation obligations, stop conditions, or escalation rules.",
        "purpose": "Surface worker contract boundaries so chat can explain them without inventing them.",
        "use_when": [
            "The user asks what an agent is allowed to do.",
            "Conflicts or path ownership need explanation.",
            "A refactor or security review depends on clear worker boundaries.",
        ],
        "workflow": [
            "Read the agent-contracts resource.",
            "Map each contract to mission, allowed paths, forbidden paths, tools, validation, stop conditions, and escalation rules.",
            "If the user wants changes, route them back through Mission Control planning or swarm controls.",
        ],
        "tools": ["`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/agent-contracts`",
            "`mission-control://projects/{project_id}/agents`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Summarize contract boundaries and call out risky overlaps or missing guardrails.",
            "Keep the explanation compact and actionable.",
        ],
        "approval": "Changes to contracts can affect safety and write scope, so treat them as explicit Manager-level decisions rather than casual chat edits.",
        "never": [
            "Do not invent contract permissions.",
            "Do not widen agent scope silently.",
            "Do not claim contract isolation where none exists.",
        ],
        "fallback": "If agent contracts are not yet a first-class resource, infer boundaries from swarm plans, path locks, and agent roles, and label that as inferred state.",
        "example": "Show me the Mission Control agent contracts for this project.",
    },
    {
        "name": "mission-control-path-locks",
        "description": "Show file and path ownership and conflicts in Mission Control. Use when the user wants to know which paths are locked, which agent owns them, which tasks are waiting, or how to resolve edit collisions safely.",
        "purpose": "Explain path ownership, waiting tasks, and conflicts without touching files directly.",
        "use_when": [
            "The user asks why work is waiting.",
            "Agents may be colliding on the same files.",
            "A safe refactor depends on ownership clarity.",
        ],
        "workflow": [
            "Read the path-locks resource.",
            "Summarize locked paths, owning agent or task, waiting tasks, conflicts, and suggested resolution.",
            "Route any ownership change through Mission Control.",
        ],
        "tools": ["`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/path-locks`",
            "`mission-control://projects/{project_id}/agents`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Show locked paths, owner agent or task, waiting tasks, conflicts, and suggested resolution.",
            "Emphasize why the lock exists if Mission Control provides that detail.",
        ],
        "approval": "If resolution involves force-reassigning ownership or interrupting work, relay that as an explicit approval-worthy action.",
        "never": [
            "Do not reassign ownership from chat by assumption.",
            "Do not describe unlocked paths as locked.",
            "Do not hide conflict risk.",
        ],
        "fallback": "If a dedicated path-locks resource is missing, derive the picture from swarm state and agent status, and label it as a best-effort summary.",
        "example": "Show the Mission Control path locks and any current conflicts.",
    },
    {
        "name": "mission-control-snapshot",
        "description": "Request a Mission Control snapshot or restore point before risky work. Use when the user wants rollback safety before refactors, broad edits, or uncertain changes, preferably through git-aware snapshotting when available.",
        "purpose": "Request a rollback point before risky work without restoring anything automatically.",
        "use_when": [
            "The user asks for a snapshot.",
            "A refactor or broad change is risky.",
            "Recovery confidence should increase before edits begin.",
        ],
        "workflow": [
            "Explain the likely snapshot mechanism: git snapshot, branch, commit, or another restore point if supported.",
            "Call `mission_control_request_snapshot` when available.",
            "Confirm the snapshot result and how it may be used later.",
            "Do not perform restore actions in this skill.",
        ],
        "tools": ["`mission_control_request_snapshot`", "`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/decision-ledger`",
        ],
        "output": [
            "Explain whether a snapshot exists, what it protects, and any limits if the repo is not under git or snapshot support is absent.",
            "Keep the result operationally clear.",
        ],
        "approval": "Creating a snapshot is usually safe, but restoring from one later may be destructive and requires separate approval.",
        "never": [
            "Do not restore automatically.",
            "Do not imply rollback is guaranteed when snapshot support is weak.",
            "Do not hide unsupported state when there is no git history or snapshot tool.",
        ],
        "fallback": "If snapshot tooling does not exist, say so directly, note whether git is likely available, and mark snapshot creation as expected or future.",
        "example": "Request a Mission Control snapshot before the refactor starts.",
    },
    {
        "name": "mission-control-restore-plan",
        "description": "Generate a rollback or restore plan from Mission Control state. Use when the user wants to know what would be reverted, what evidence would be preserved, and which destructive steps would still need approval before any restore action.",
        "purpose": "Describe how rollback would work without executing it.",
        "use_when": [
            "The user asks how to roll back safely.",
            "A risky change needs a restore plan.",
            "Recovery decisions need a concrete revert outline.",
        ],
        "workflow": [
            "Review snapshot, handoff, and status state.",
            "Ask Mission Control for a restore or rollback plan if available.",
            "Summarize what would be reverted, what would remain, and which steps would need approval.",
            "Do not execute the restore in this skill.",
        ],
        "tools": [
            "`mission_control_request_snapshot`",
            "`mission_control_request_recovery_plan`",
            "`mission_control_get_status`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/decision-ledger`",
        ],
        "output": [
            "Explain the rollback target, affected files or milestones, evidence preservation, and approval gates for destructive steps.",
            "Keep it actionable enough for the user to decide.",
        ],
        "approval": "Any actual restore or revert remains behind explicit approval. This skill only prepares the plan.",
        "never": [
            "Do not execute restore steps.",
            "Do not understate destructive impact.",
            "Do not claim rollback coverage for unsnapshotted work.",
        ],
        "fallback": "If no restore-plan tool exists, build the plan from snapshot availability, handoff evidence, and current status, and mark the dedicated tool as expected or future.",
        "example": "Generate a restore plan in case the current change set goes bad.",
    },
    {
        "name": "mission-control-conflict-resolution",
        "description": "Resolve Mission Control agent or merge conflicts safely. Use when paths overlap, outputs disagree, or Mission Control needs a user-visible conflict-resolution path instead of hidden reassignment.",
        "purpose": "Summarize conflicts and route resolution through Mission Control rather than improvising edits.",
        "use_when": [
            "Agents conflict on paths or task ownership.",
            "A merge or handoff conflict needs explanation.",
            "The user wants options before forcing a resolution.",
        ],
        "workflow": [
            "Fetch conflicts from path-locks, status, and agent resources.",
            "Summarize involved agents, tasks, and paths.",
            "Ask Mission Control for resolution options if available.",
            "Present high-risk options to the user and relay the selected resolution.",
            "Confirm the updated state afterward.",
        ],
        "tools": [
            "`mission_control_get_status`",
            "`mission_control_get_pending_decisions`",
            "`mission_control_answer_decision`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/path-locks`",
            "`mission-control://projects/{project_id}/agents`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Show involved paths and agents, the likely cause, available resolution options, and the risk of each option.",
            "Confirm the chosen resolution when Mission Control records it.",
        ],
        "approval": "High-risk reassignment, merge resolution, or forced interruption should be presented as explicit decisions.",
        "never": [
            "Do not resolve conflicts by guessing the better owner.",
            "Do not hide competing risks.",
            "Do not rewrite files directly from chat to 'fix' a coordination problem.",
        ],
        "fallback": "If a conflict-resolution tool is not exposed, surface the conflict, explain that a Manager decision is still needed, and guide the user to the best matching approval or recovery flow.",
        "example": "Mission Control agents are conflicting. Show me the resolution options.",
    },
    {
        "name": "mission-control-agent-stuck",
        "description": "Diagnose a stuck Mission Control agent. Use when an agent shows no output, repeats errors, times out, asks for the same approval repeatedly, or stops making progress events.",
        "purpose": "Diagnose a stuck agent and surface recovery options through Mission Control.",
        "use_when": [
            "A specific agent looks frozen.",
            "Progress events stopped.",
            "Repeated errors or approvals suggest a stuck loop.",
        ],
        "workflow": [
            "Read agent status, event digest, diagnostics, and pending decisions.",
            "Identify the stuck signal: no output, repeated error, timeout, repeated approval request, or no progress events.",
            "Ask Mission Control for recovery options when available.",
            "Present retry, reassign, split task, pause, or debug-agent options if backed by Mission Control.",
        ],
        "tools": [
            "`mission_control_get_event_digest`",
            "`mission_control_get_status`",
            "`mission_control_request_recovery_plan`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/agents`",
            "`mission-control://projects/{project_id}/diagnostics`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Show the stuck signal, likely cause, affected agent, and safe recovery options.",
            "Keep the explanation focused on actionability.",
        ],
        "approval": "If recovery means retrying commands, reassigning work, or spawning extra debugging capacity, keep those behind Mission Control approvals.",
        "never": [
            "Do not restart or replace the agent from chat by assumption.",
            "Do not ignore a repeated approval loop.",
            "Do not claim the agent is healthy if the signals are stale.",
        ],
        "fallback": "If dedicated stuck-agent logic is not exposed yet, infer the stuck pattern from status, diagnostics, and event digest, then recommend the recovery-plan flow.",
        "example": "This Mission Control agent looks stuck. Diagnose it.",
    },
    {
        "name": "mission-control-recovery-plan",
        "description": "Ask Mission Control Manager for recovery guidance after a failure. Use when the user wants a failure summary, likely causes, recovery options, recommendation, and risks without losing the orchestration context.",
        "purpose": "Request a structured recovery plan from Mission Control after failure or uncertainty.",
        "use_when": [
            "A run failed or stalled.",
            "The user asks for recovery options.",
            "Status and diagnostics show unresolved blockers.",
        ],
        "workflow": [
            "Review status, diagnostics, and event digest.",
            "Call `mission_control_request_recovery_plan` when available.",
            "Return the failure summary, possible causes, recovery options, recommended option, and risks.",
            "If the user chooses an option, relay it through the approval flow.",
        ],
        "tools": [
            "`mission_control_request_recovery_plan`",
            "`mission_control_get_status`",
            "`mission_control_get_event_digest`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/diagnostics`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Show failure summary, causes, options, recommendation, and risks in plain language.",
            "Make it obvious which options require approval or broader scope changes.",
        ],
        "approval": "Recovery choices that restart work, relax safety controls, or widen scope must stay behind explicit user decisions.",
        "never": [
            "Do not turn a recommendation into an action automatically.",
            "Do not hide uncertainty.",
            "Do not discard current evidence while discussing recovery.",
        ],
        "fallback": "If the dedicated recovery-plan tool is absent, synthesize the same structure from status, diagnostics, and event resources and label it as a best-effort summary.",
        "example": "Ask Mission Control Manager for a recovery plan for the failed run.",
    },
    {
        "name": "mission-control-model-policy",
        "description": "Inspect or update Mission Control model-assignment policy. Use when the user wants to understand or change cost-saving, balanced, best-quality, local-first, or custom model routing across Manager, coding, docs, review, and fallback roles.",
        "purpose": "Explain or request model-policy changes while keeping billing and auth boundaries explicit.",
        "use_when": [
            "The user asks which models are being used.",
            "Cost or quality posture needs adjustment.",
            "Local-first or custom model routing should be requested.",
        ],
        "workflow": [
            "Read current project status and model-policy-related state if exposed.",
            "Summarize Manager model, coding model, docs model, review or security model, and fallback model.",
            "If the user wants a change, route it through Mission Control policy controls or a Manager-led task.",
        ],
        "tools": ["`mission_control_get_status`", "`mission_control_start_task`"],
        "resources": ["`mission-control://projects/{project_id}/status`"],
        "output": [
            "Show the current policy and the tradeoffs among cost, speed, quality, and locality.",
            "Warn clearly if a requested change may use API-billed providers.",
        ],
        "approval": "Do not switch to API-billed or higher-cost modes without explicit user awareness and approval.",
        "never": [
            "Do not ask for raw API keys in chat.",
            "Do not claim a policy changed if the backend did not accept it.",
            "Do not hide billing implications.",
        ],
        "fallback": "If model-policy controls are not first-class yet, explain the expected policy states and route the requested change through a Manager-led planning or settings task.",
        "example": "Show the Mission Control model policy and switch to balanced if needed.",
    },
    {
        "name": "mission-control-tool-policy",
        "description": "Inspect or update Mission Control tool-routing and permission policy. Use when the user wants to see allowed tools, blocked tools, approval-required tools, or per-agent archetype tool constraints.",
        "purpose": "Explain or request tool-policy changes without bypassing the policy itself.",
        "use_when": [
            "The user asks which tools are allowed.",
            "Approval-required tools need explanation.",
            "A policy change is needed for a task.",
        ],
        "workflow": [
            "Review current status and any tool-policy or approval state that Mission Control exposes.",
            "Summarize allowed, blocked, and approval-required tools plus any archetype-specific constraints.",
            "Route requested policy changes back through Mission Control rather than mutating them directly in chat.",
        ],
        "tools": ["`mission_control_get_status`", "`mission_control_start_task`"],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Show the effective tool policy, notable restrictions, and what the user would need to approve to loosen it.",
            "Keep the summary bridge-safe rather than dumping backend config.",
        ],
        "approval": "Tool-policy changes are explicit policy decisions and should be confirmed with the user before they are requested.",
        "never": [
            "Do not override the tool policy from chat.",
            "Do not blur approval-required and fully allowed tools.",
            "Do not claim blocked tools are available.",
        ],
        "fallback": "If dedicated tool-policy state is not exposed, infer current policy from pending approvals and known Mission Control controls, and label that inference clearly.",
        "example": "Show the Mission Control tool policy for this project.",
    },
    {
        "name": "mission-control-local-first",
        "description": "Switch Mission Control toward local-first behavior. Use when the user wants local files, local models, no cloud deployment, and no external APIs unless explicitly approved.",
        "purpose": "Bias the project toward local-first execution and explain the resulting constraints.",
        "use_when": [
            "The user wants local-first behavior.",
            "Cloud deployment or external APIs should be avoided.",
            "Privacy or offline constraints dominate.",
        ],
        "workflow": [
            "Explain what local-first means for the project: local files, local models when configured, no cloud deployment, and external APIs only with approval.",
            "Route the policy change through Mission Control.",
            "Confirm status after the policy change and show any unsupported controls.",
        ],
        "tools": ["`mission_control_get_status`", "`mission_control_start_task`"],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/risk-register`",
        ],
        "output": [
            "Summarize the local-first posture and any tradeoffs in capability, speed, or evidence depth.",
            "Tell the user which external actions are now blocked or approval-gated.",
        ],
        "approval": "Switching posture is a project-level decision. Confirm it explicitly before requesting the change.",
        "never": [
            "Do not imply that local-only guarantees exist if some tools still depend on external services.",
            "Do not enable deployments or external APIs while claiming local-first.",
            "Do not ask for API keys in this flow.",
        ],
        "fallback": "If no local-first toggle exists yet, document the intended constraints in chat, route them through Manager planning, and continue with the most conservative behavior available.",
        "example": "Switch this project to Mission Control local-first mode.",
    },
    {
        "name": "mission-control-ollama-mode",
        "description": "Use or prefer Ollama or local models through Mission Control. Use when the user explicitly wants Ollama or local-model preference and Codex should verify availability rather than assuming it exists.",
        "purpose": "Check and explain Mission Control Ollama or local-model mode safely.",
        "use_when": [
            "The user asks for Ollama mode.",
            "Local-model preference matters.",
            "A local-first project should check local model availability.",
        ],
        "workflow": [
            "Check Mission Control status for local-model or Ollama state if exposed.",
            "Explain whether Ollama is available, unknown, or unavailable.",
            "If the user wants the mode enabled, route that request through Mission Control policy controls.",
            "If unavailable, explain the fallback clearly.",
        ],
        "tools": ["`mission_control_get_status`", "`mission_control_start_task`"],
        "resources": ["`mission-control://projects/{project_id}/status`"],
        "output": [
            "Show available, unavailable, or unknown Ollama state, the likely model-policy effect, and the fallback path.",
            "Be explicit about any inference.",
        ],
        "approval": "Changing model mode is a policy decision; confirm it with the user first.",
        "never": [
            "Do not assume Ollama is installed or running.",
            "Do not pretend a local model exists because the user wants one.",
            "Do not require API keys as a fallback without user awareness.",
        ],
        "fallback": "If Ollama state is not surfaced yet, say so directly, treat availability as unknown, and preserve the current model policy until the backend can verify it.",
        "example": "Check whether Mission Control can use Ollama mode for this project.",
    },
    {
        "name": "mission-control-codex-cli-mode",
        "description": "Use or prefer Codex CLI runner mode through Mission Control. Use when the user wants Codex CLI as the runner, needs its status explained, or wants the distinction between subscription auth and API-based providers kept clear.",
        "purpose": "Explain or request Codex CLI runner mode while preserving local auth and approval boundaries.",
        "use_when": [
            "The user asks for Codex CLI mode.",
            "Runner selection is being reviewed.",
            "The user is confused about local Codex login versus API-billed mode.",
        ],
        "workflow": [
            "Check Mission Control status for Codex CLI runner availability.",
            "Explain runner availability, login state if surfaced, and the difference between local Codex auth and API provider mode.",
            "Route any runner-policy change through Mission Control controls.",
        ],
        "tools": ["`mission_control_get_status`", "`mission_control_start_task`"],
        "resources": ["`mission-control://projects/{project_id}/status`"],
        "output": [
            "Summarize Codex CLI availability, auth posture, and fallback if unavailable.",
            "Preserve the distinction between subscription-backed local auth and API-billed provider modes when relevant.",
        ],
        "approval": "Changing runner mode may affect cost or behavior, so confirm it before requesting the switch.",
        "never": [
            "Do not ask for raw API keys for Codex CLI mode.",
            "Do not break local Codex auth by improvising a replacement flow.",
            "Do not claim CLI availability without verification.",
        ],
        "fallback": "If Mission Control does not expose Codex CLI status yet, mark it as expected or future and preserve the current runner choice.",
        "example": "Check whether Mission Control can run this project in Codex CLI mode.",
    },
    {
        "name": "mission-control-claude-cli-mode",
        "description": "Use or prefer Claude CLI runner mode through Mission Control. Use when the user explicitly wants Claude CLI if configured and Codex should verify availability and fallback rather than assuming setup exists.",
        "purpose": "Check and explain Claude CLI runner mode through Mission Control.",
        "use_when": [
            "The user asks for Claude CLI mode.",
            "Runner availability needs comparison.",
            "Mission Control may need a non-Codex CLI runner.",
        ],
        "workflow": [
            "Check Mission Control status for Claude CLI runner availability.",
            "Explain whether it is configured, unavailable, or unknown.",
            "If the user wants it enabled, route the request through Mission Control policy or settings flow.",
            "Explain fallback if unavailable.",
        ],
        "tools": ["`mission_control_get_status`", "`mission_control_start_task`"],
        "resources": ["`mission-control://projects/{project_id}/status`"],
        "output": [
            "Summarize Claude CLI availability and the fallback path.",
            "Keep the explanation configuration-aware without demanding setup from the user if it is not already present.",
        ],
        "approval": "Switching runner mode should be an explicit user decision.",
        "never": [
            "Do not require setup the user did not ask for.",
            "Do not claim Claude CLI is ready when Mission Control cannot verify it.",
            "Do not ask for raw keys in chat.",
        ],
        "fallback": "If availability is not exposed yet, say that clearly and keep the current runner policy unchanged.",
        "example": "See whether Mission Control can prefer Claude CLI for this task.",
    },
    {
        "name": "mission-control-api-provider-mode",
        "description": "Use or explain API-provider mode through Mission Control. Use when the user explicitly wants API-backed execution, needs billing implications explained, or wants confirmation that configured secret storage rather than chat-provided keys will be used.",
        "purpose": "Explain or request API-provider mode while keeping billing and secret handling explicit.",
        "use_when": [
            "The user explicitly wants API-backed providers.",
            "A configured API provider policy needs explanation.",
            "Billing and secret-storage implications matter.",
        ],
        "workflow": [
            "Review current status and model policy.",
            "Explain that API billing may apply and that raw keys should not be pasted into chat.",
            "If the user still wants API-provider mode, route the request through Mission Control settings or task controls using configured secret storage only.",
        ],
        "tools": ["`mission_control_get_status`", "`mission_control_start_task`"],
        "resources": ["`mission-control://projects/{project_id}/status`"],
        "output": [
            "Warn about billing, explain the configured-secret-store expectation, and state whether API-provider mode is active or only requested.",
            "Keep the summary safe and non-secret-bearing.",
        ],
        "approval": "Use explicit user awareness before switching to API-billed providers or any secret-backed mode.",
        "never": [
            "Do not ask the user to paste raw keys into chat.",
            "Do not hide billing impact.",
            "Do not claim secure secret storage exists if Mission Control has not exposed it.",
        ],
        "fallback": "If API-provider controls are not exposed yet, document the desired mode and keep the current provider policy unchanged until Mission Control can apply it safely.",
        "example": "Explain the API-provider mode for this Mission Control project.",
    },
    {
        "name": "mission-control-plugin-health",
        "description": "Run a Mission Control plugin, daemon, and bridge health check. Use when the user wants to verify daemon status, MCP connectivity, skills availability, runner registry, local binding, or general bridge health from Codex chat.",
        "purpose": "Check the health of the Mission Control bridge surfaces that Codex depends on.",
        "use_when": [
            "Mission Control seems unreachable or partially broken.",
            "The user asks whether the plugin or daemon is healthy.",
            "A setup problem blocks orchestration.",
        ],
        "workflow": [
            "Call `mission_control_plugin_health` when available.",
            "Review status resources and summarize daemon, MCP, skills, runner registry, runtime folder, local binding, and optional dashboard state.",
            "Return a concise health report and likely next fix.",
        ],
        "tools": ["`mission_control_plugin_health`", "`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/diagnostics`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Check daemon, MCP, skills, Codex CLI, runner registry, runtime folder, localhost binding, and optional dashboard status.",
            "Report failures as specific components, not a vague 'it is broken.'",
        ],
        "approval": "Health reads are read-only. If the user wants a repair action that changes config or restarts components, get explicit approval first.",
        "never": [
            "Do not pretend health is good when connectivity is partial.",
            "Do not dump raw diagnostics logs by default.",
            "Do not force dashboard UI involvement.",
        ],
        "fallback": "If the dedicated health tool is absent, use diagnostics and status resources to produce a best-effort bridge health summary and label missing checks clearly.",
        "example": "Run a Mission Control plugin health check.",
    },
    {
        "name": "mission-control-event-digest",
        "description": "Summarize recent Mission Control events without raw logs. Use when the user wants the last 5 minutes, last 15 minutes, since last interaction, or since orchestration start summarized in bridge-safe markdown.",
        "purpose": "Return a short event digest that is useful in chat and safe by default.",
        "use_when": [
            "The user wants recent activity.",
            "A long-running orchestration needs a short event recap.",
            "Raw logs would be too noisy or unsafe.",
        ],
        "workflow": [
            "Call `mission_control_get_event_digest` or the closest backed event summary path.",
            "Apply the requested window: last 5 minutes, last 15 minutes, since last user interaction, or since orchestration start.",
            "Summarize the major transitions, blockers, approvals, and completions.",
        ],
        "tools": ["`mission_control_get_event_digest`"],
        "resources": [
            "`mission-control://orchestrations/{orchestration_id}/status`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Return a concise timeline of meaningful events, not raw event spam.",
            "Highlight approvals, failures, pauses, resumes, and handoff-related milestones.",
        ],
        "approval": "Reading an event digest is read-only. If the user wants action on an event, switch to the corresponding skill.",
        "never": [
            "Do not dump raw logs or full event streams.",
            "Do not smooth over failures.",
            "Do not infer event timing without clear backing data.",
        ],
        "fallback": "If the event-digest tool is not exposed yet, synthesize a digest from current status and known checkpoints, then label the result as approximate.",
        "example": "Give me a Mission Control event digest for the last 15 minutes.",
    },
    {
        "name": "mission-control-evidence-check",
        "description": "Check whether Mission Control claims have backing evidence. Use when the user wants to know whether tests, builds, screenshots, artifacts, or handoff confidence are real, missing, weak, or dry-run only.",
        "purpose": "Audit evidence quality behind Mission Control claims and handoffs.",
        "use_when": [
            "The user doubts a claim.",
            "A handoff needs an evidence review.",
            "Validation or artifact confidence matters before sign-off.",
        ],
        "workflow": [
            "Review handoff, validation, and status resources.",
            "Identify tests claimed but not run, builds claimed without output, missing screenshots or artifacts, dry-run-only evidence, and weak confidence signals.",
            "Summarize what is backed and what still needs proof.",
        ],
        "tools": ["`mission_control_get_handoff_summary`", "`mission_control_get_status`"],
        "resources": [
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/validation-summary`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "Call out weak evidence clearly and identify the concrete missing artifact or validation step.",
            "Differentiate between executed evidence and dry-run or inferred evidence.",
        ],
        "approval": "If the fix is to run additional validation that requires commands, preserve the normal approval flow.",
        "never": [
            "Do not let evidence-free claims pass as verified.",
            "Do not overstate confidence.",
            "Do not treat dry-run as proof of execution.",
        ],
        "fallback": "If evidence-specific resources are limited, inspect handoff and validation summaries, mark any inference explicitly, and note which dedicated evidence surfaces are expected or future.",
        "example": "Check whether the Mission Control handoff claims are actually backed by evidence.",
    },
    {
        "name": "mission-control-change-request",
        "description": "Run a post-handoff or mid-project Mission Control change request flow. Use when the user wants additional work classified, impact-estimated, task-created, validated, and folded into the current handoff or milestone safely.",
        "purpose": "Create a structured change request path instead of improvising scope changes in chat.",
        "use_when": [
            "The user asks for follow-up work after a handoff.",
            "A new request changes an active project.",
            "Impact and validation should be estimated before execution.",
        ],
        "workflow": [
            "Classify the request through Mission Control.",
            "Estimate impact and ask the user if the change is large or architectural.",
            "Create tasks or a new milestone through Mission Control.",
            "Run or plan validation and update the handoff after completion.",
        ],
        "tools": [
            "`mission_control_start_task`",
            "`mission_control_get_status`",
            "`mission_control_get_handoff_summary`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/decision-ledger`",
        ],
        "output": [
            "Show classification, impact, user decisions needed, planned validation, and whether the handoff will be updated or extended.",
            "Keep the change request distinct from the original baseline.",
        ],
        "approval": "Large, architectural, or risky changes should be confirmed explicitly before execution continues.",
        "never": [
            "Do not silently mutate the original scope.",
            "Do not discard earlier evidence when describing the new request.",
            "Do not skip impact discussion for large changes.",
        ],
        "fallback": "If change-request workflow tooling is incomplete, route the request through plan revision plus Manager-led task execution and clearly mark it as a change request in chat.",
        "example": "Create a Mission Control change request for the next improvement after handoff.",
    },
    {
        "name": "mission-control-continue-handoff",
        "description": "Continue work after a Mission Control handoff without losing continuity. Use when the user wants another iteration, wants limitations preserved, or needs the next change request to build on the previous handoff and evidence.",
        "purpose": "Continue from an existing handoff while preserving evidence and limitations.",
        "use_when": [
            "The user wants to keep going after handoff.",
            "A new milestone should build on the previous handoff.",
            "Earlier evidence and limitations still matter.",
        ],
        "workflow": [
            "Read the previous handoff first.",
            "Summarize preserved limitations, evidence, and unfinished work.",
            "Create a change request or next milestone through Mission Control.",
            "Track the new iteration without erasing the earlier handoff context.",
        ],
        "tools": [
            "`mission_control_get_handoff`",
            "`mission_control_start_task`",
            "`mission_control_get_status`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/decision-ledger`",
        ],
        "output": [
            "Show what carries over from the last handoff, what the new iteration changes, and what evidence must be refreshed.",
            "Keep old and new scopes distinct.",
        ],
        "approval": "Any new change request that widens scope still requires normal approvals and user consent.",
        "never": [
            "Do not lose the previous limitations.",
            "Do not overwrite the narrative as if this is a fresh project.",
            "Do not discard evidence history.",
        ],
        "fallback": "If no explicit continue-handoff workflow exists, use the prior handoff plus a change-request flow and make the continuity objective explicit in the task request.",
        "example": "Continue from the last Mission Control handoff and start the next iteration.",
    },
    {
        "name": "mission-control-pause",
        "description": "Pause Mission Control orchestration safely. Use when the user wants to pause after the current task, pause immediately, or stop assigning new work without discarding the current state.",
        "purpose": "Pause Mission Control work without losing the current state summary.",
        "use_when": [
            "The user asks to pause.",
            "Work should stop assigning new tasks.",
            "A risky moment needs a deliberate hold.",
        ],
        "workflow": [
            "Clarify the pause mode if needed: after current task, immediately, or stop assigning new tasks.",
            "Call `mission_control_pause` if supported.",
            "Confirm what is paused, what remains in flight, and what will be needed to resume.",
        ],
        "tools": ["`mission_control_pause`", "`mission_control_get_status`"],
        "resources": [
            "`mission-control://orchestrations/{orchestration_id}/status`",
            "`mission-control://projects/{project_id}/status`",
        ],
        "output": [
            "State the pause mode, active tasks affected, and the next resume checkpoint.",
            "Keep it operational and brief.",
        ],
        "approval": "Pausing is usually user-directed. If the requested pause mode could interrupt risky operations, say so before issuing it.",
        "never": [
            "Do not claim work is paused without a backed status change.",
            "Do not kill processes unsafely from chat.",
            "Do not forget to summarize what was in progress.",
        ],
        "fallback": "If the backend only supports a generic pause, explain that limitation and use the safest available pause option.",
        "example": "Pause Mission Control after the current task finishes.",
    },
    {
        "name": "mission-control-resume-agents",
        "description": "Resume paused Mission Control agents or projects when safe. Use when the user wants paused work restarted but approvals, safety conditions, and current status should be checked first.",
        "purpose": "Resume paused work only after checking safety and pending approvals.",
        "use_when": [
            "The user wants paused agents resumed.",
            "A pause has already happened and work can continue.",
            "Safety conditions must be verified before restarting.",
        ],
        "workflow": [
            "Check current status and pending decisions.",
            "Confirm the work is actually paused and not already running.",
            "Call `mission_control_resume` only if safe.",
            "Summarize the post-resume state and next checkpoint.",
        ],
        "tools": [
            "`mission_control_get_status`",
            "`mission_control_get_pending_decisions`",
            "`mission_control_resume`",
        ],
        "resources": [
            "`mission-control://orchestrations/{orchestration_id}/status`",
            "`mission-control://projects/{project_id}/pending-decisions`",
            "`mission-control://projects/{project_id}/agents`",
        ],
        "output": [
            "Show whether resume is safe, what approvals are still pending, and which agents or tasks are active again after resume.",
            "Explain clearly if resume is blocked.",
        ],
        "approval": "If pending approvals still block execution, present them first instead of resuming blindly.",
        "never": [
            "Do not resume work that was paused for unresolved risk without user awareness.",
            "Do not treat resume as a status check only.",
            "Do not restart already-running work.",
        ],
        "fallback": "If granular agent resume is not supported, explain whether resume applies at project or orchestration level and use the safest available scope.",
        "example": "Resume the paused Mission Control agents if it is safe.",
    },
    {
        "name": "mission-control-stop",
        "description": "Stop or retire Mission Control orchestration safely. Use when the user wants no new work assigned, current state preserved, partial results summarized, and unsafe process-kill behavior avoided unless the backend explicitly supports it.",
        "purpose": "Stop Mission Control work safely while preserving state and partial outputs.",
        "use_when": [
            "The user wants to stop the run.",
            "The project should retire gracefully.",
            "A partial report should be preserved before shutdown.",
        ],
        "workflow": [
            "Check status and pending decisions.",
            "Ask Mission Control to stop assigning new work and retire the orchestration cleanly.",
            "Summarize the preserved state, partial handoff if any, and what remains unfinished.",
            "Avoid unsafe process termination unless the backend exposes a safe stop control.",
        ],
        "tools": [
            "`mission_control_get_status`",
            "`mission_control_pause` or future stop control via Mission Control task request",
            "`mission_control_get_handoff_summary`",
        ],
        "resources": [
            "`mission-control://projects/{project_id}/status`",
            "`mission-control://projects/{project_id}/handoff`",
            "`mission-control://projects/{project_id}/pending-decisions`",
        ],
        "output": [
            "Summarize what was completed, what was stopped, what evidence was preserved, and what follow-up would be needed to restart later.",
            "If only a partial report exists, say so explicitly.",
        ],
        "approval": "Stopping active work is a user decision. If the backend distinguishes graceful stop versus force stop, make that distinction explicit before acting.",
        "never": [
            "Do not kill processes unsafely from chat.",
            "Do not discard partial state or handoff evidence.",
            "Do not call a stop successful if Mission Control only paused.",
        ],
        "fallback": "If there is no dedicated stop control yet, use the safest pause or no-new-work pattern available, and clearly tell the user that full stop support is expected or future.",
        "example": "Stop the Mission Control orchestration safely and summarize the partial state.",
    },
]

EXPECTED_SKILL_NAMES = {
    "mission-control-orchestrate",
    "mission-control-import-codebase",
    "mission-control-status",
    "mission-control-approve",
    "mission-control-handoff",
    "mission-control-debug",
    "mission-control-swarm",
    "mission-control-safe-mode",
    "mission-control-resume",
    "mission-control-agents-md",
    "mission-control-plan",
    "mission-control-interview",
    "mission-control-skip-interview",
    "mission-control-quick-clarify",
    "mission-control-existing-repo-fix",
    "mission-control-run-validation",
    "mission-control-review-tests",
    "mission-control-generate-runbook",
    "mission-control-explain-codebase",
    "mission-control-refactor-safely",
    "mission-control-security-review",
    "mission-control-docs-heavy",
    "mission-control-github-ready-docs",
    "mission-control-release-prep",
    "mission-control-scope-creep-check",
    "mission-control-risk-register",
    "mission-control-decision-ledger",
    "mission-control-context-pack",
    "mission-control-agent-contracts",
    "mission-control-path-locks",
    "mission-control-snapshot",
    "mission-control-restore-plan",
    "mission-control-conflict-resolution",
    "mission-control-agent-stuck",
    "mission-control-recovery-plan",
    "mission-control-model-policy",
    "mission-control-tool-policy",
    "mission-control-local-first",
    "mission-control-ollama-mode",
    "mission-control-codex-cli-mode",
    "mission-control-claude-cli-mode",
    "mission-control-api-provider-mode",
    "mission-control-plugin-health",
    "mission-control-event-digest",
    "mission-control-evidence-check",
    "mission-control-change-request",
    "mission-control-continue-handoff",
    "mission-control-pause",
    "mission-control-resume-agents",
    "mission-control-stop",
}

# The remaining generation logic is simple and deterministic.

GROUPS: list[tuple[str, list[str]]] = [
    (
        "Core bridge workflows",
        [
            "mission-control-orchestrate",
            "mission-control-import-codebase",
            "mission-control-status",
            "mission-control-approve",
            "mission-control-handoff",
            "mission-control-resume",
            "mission-control-pause",
            "mission-control-stop",
            "mission-control-safe-mode",
        ],
    ),
    (
        "Planning and intake",
        [
            "mission-control-plan",
            "mission-control-interview",
            "mission-control-skip-interview",
            "mission-control-quick-clarify",
            "mission-control-existing-repo-fix",
            "mission-control-change-request",
            "mission-control-continue-handoff",
        ],
    ),
    (
        "Execution and swarm control",
        [
            "mission-control-swarm",
            "mission-control-resume-agents",
            "mission-control-agent-contracts",
            "mission-control-path-locks",
            "mission-control-context-pack",
            "mission-control-snapshot",
            "mission-control-restore-plan",
            "mission-control-conflict-resolution",
            "mission-control-agent-stuck",
        ],
    ),
    (
        "Validation, evidence, and release",
        [
            "mission-control-run-validation",
            "mission-control-review-tests",
            "mission-control-evidence-check",
            "mission-control-release-prep",
            "mission-control-generate-runbook",
            "mission-control-github-ready-docs",
            "mission-control-docs-heavy",
            "mission-control-handoff",
        ],
    ),
    (
        "Diagnostics and policy",
        [
            "mission-control-debug",
            "mission-control-recovery-plan",
            "mission-control-plugin-health",
            "mission-control-event-digest",
            "mission-control-risk-register",
            "mission-control-decision-ledger",
            "mission-control-scope-creep-check",
            "mission-control-security-review",
            "mission-control-model-policy",
            "mission-control-tool-policy",
            "mission-control-local-first",
            "mission-control-ollama-mode",
            "mission-control-codex-cli-mode",
            "mission-control-claude-cli-mode",
            "mission-control-api-provider-mode",
            "mission-control-explain-codebase",
            "mission-control-refactor-safely",
            "mission-control-agents-md",
        ],
    ),
]

RELATED_SKILLS: dict[str, list[str]] = {
    "mission-control-orchestrate": ["mission-control-status", "mission-control-approve", "mission-control-handoff"],
    "mission-control-import-codebase": ["mission-control-explain-codebase", "mission-control-plan", "mission-control-existing-repo-fix"],
    "mission-control-status": ["mission-control-event-digest", "mission-control-debug", "mission-control-handoff"],
    "mission-control-approve": ["mission-control-status", "mission-control-safe-mode", "mission-control-recovery-plan"],
    "mission-control-handoff": ["mission-control-evidence-check", "mission-control-review-tests", "mission-control-continue-handoff"],
    "mission-control-debug": ["mission-control-recovery-plan", "mission-control-plugin-health", "mission-control-agent-stuck"],
    "mission-control-swarm": ["mission-control-agent-contracts", "mission-control-path-locks", "mission-control-resume-agents"],
    "mission-control-safe-mode": ["mission-control-tool-policy", "mission-control-local-first", "mission-control-approve"],
    "mission-control-resume": ["mission-control-status", "mission-control-resume-agents", "mission-control-approve"],
    "mission-control-agents-md": ["mission-control-explain-codebase", "mission-control-generate-runbook", "mission-control-docs-heavy"],
    "mission-control-plan": ["mission-control-interview", "mission-control-quick-clarify", "mission-control-scope-creep-check"],
    "mission-control-interview": ["mission-control-plan", "mission-control-skip-interview", "mission-control-quick-clarify"],
    "mission-control-skip-interview": ["mission-control-plan", "mission-control-quick-clarify", "mission-control-existing-repo-fix"],
    "mission-control-quick-clarify": ["mission-control-interview", "mission-control-existing-repo-fix", "mission-control-plan"],
    "mission-control-existing-repo-fix": ["mission-control-import-codebase", "mission-control-run-validation", "mission-control-handoff"],
    "mission-control-run-validation": ["mission-control-review-tests", "mission-control-evidence-check", "mission-control-release-prep"],
    "mission-control-review-tests": ["mission-control-run-validation", "mission-control-evidence-check", "mission-control-handoff"],
    "mission-control-generate-runbook": ["mission-control-handoff", "mission-control-docs-heavy", "mission-control-github-ready-docs"],
    "mission-control-explain-codebase": ["mission-control-import-codebase", "mission-control-agents-md", "mission-control-context-pack"],
    "mission-control-refactor-safely": ["mission-control-snapshot", "mission-control-path-locks", "mission-control-run-validation"],
    "mission-control-security-review": ["mission-control-risk-register", "mission-control-release-prep", "mission-control-tool-policy"],
    "mission-control-docs-heavy": ["mission-control-github-ready-docs", "mission-control-generate-runbook", "mission-control-release-prep"],
    "mission-control-github-ready-docs": ["mission-control-docs-heavy", "mission-control-release-prep", "mission-control-generate-runbook"],
    "mission-control-release-prep": ["mission-control-run-validation", "mission-control-handoff", "mission-control-security-review"],
    "mission-control-scope-creep-check": ["mission-control-plan", "mission-control-change-request", "mission-control-risk-register"],
    "mission-control-risk-register": ["mission-control-security-review", "mission-control-scope-creep-check", "mission-control-decision-ledger"],
    "mission-control-decision-ledger": ["mission-control-approve", "mission-control-plan", "mission-control-scope-creep-check"],
    "mission-control-context-pack": ["mission-control-agent-contracts", "mission-control-explain-codebase", "mission-control-path-locks"],
    "mission-control-agent-contracts": ["mission-control-path-locks", "mission-control-swarm", "mission-control-context-pack"],
    "mission-control-path-locks": ["mission-control-conflict-resolution", "mission-control-agent-contracts", "mission-control-refactor-safely"],
    "mission-control-snapshot": ["mission-control-restore-plan", "mission-control-refactor-safely", "mission-control-recovery-plan"],
    "mission-control-restore-plan": ["mission-control-snapshot", "mission-control-recovery-plan", "mission-control-handoff"],
    "mission-control-conflict-resolution": ["mission-control-path-locks", "mission-control-agent-stuck", "mission-control-swarm"],
    "mission-control-agent-stuck": ["mission-control-debug", "mission-control-recovery-plan", "mission-control-event-digest"],
    "mission-control-recovery-plan": ["mission-control-debug", "mission-control-agent-stuck", "mission-control-stop"],
    "mission-control-model-policy": ["mission-control-tool-policy", "mission-control-local-first", "mission-control-api-provider-mode"],
    "mission-control-tool-policy": ["mission-control-safe-mode", "mission-control-model-policy", "mission-control-local-first"],
    "mission-control-local-first": ["mission-control-ollama-mode", "mission-control-model-policy", "mission-control-safe-mode"],
    "mission-control-ollama-mode": ["mission-control-local-first", "mission-control-model-policy", "mission-control-codex-cli-mode"],
    "mission-control-codex-cli-mode": ["mission-control-model-policy", "mission-control-claude-cli-mode", "mission-control-api-provider-mode"],
    "mission-control-claude-cli-mode": ["mission-control-codex-cli-mode", "mission-control-model-policy", "mission-control-api-provider-mode"],
    "mission-control-api-provider-mode": ["mission-control-model-policy", "mission-control-codex-cli-mode", "mission-control-claude-cli-mode"],
    "mission-control-plugin-health": ["mission-control-debug", "mission-control-status", "mission-control-event-digest"],
    "mission-control-event-digest": ["mission-control-status", "mission-control-debug", "mission-control-agent-stuck"],
    "mission-control-evidence-check": ["mission-control-review-tests", "mission-control-handoff", "mission-control-run-validation"],
    "mission-control-change-request": ["mission-control-continue-handoff", "mission-control-plan", "mission-control-scope-creep-check"],
    "mission-control-continue-handoff": ["mission-control-handoff", "mission-control-change-request", "mission-control-release-prep"],
    "mission-control-pause": ["mission-control-resume", "mission-control-resume-agents", "mission-control-stop"],
    "mission-control-resume-agents": ["mission-control-resume", "mission-control-pause", "mission-control-swarm"],
    "mission-control-stop": ["mission-control-pause", "mission-control-handoff", "mission-control-recovery-plan"],
}


def _write_skill(skill: dict[str, object]) -> None:
    path = SKILLS_ROOT / str(skill["name"])
    path.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"name: {skill['name']}",
        f"description: {skill['description']}",
        "---",
        "",
        f"# {str(skill['name']).replace('-', ' ').title()}",
        "",
        "## Purpose",
        "",
        str(skill["purpose"]),
        "",
        BRIDGE_STATEMENT,
        "",
        "## Use when",
        "",
    ]
    lines.extend(f"- {item}" for item in skill["use_when"])  # type: ignore[index]
    lines.extend(["", "## Workflow", ""])
    lines.extend(f"{index}. {item}" for index, item in enumerate(skill["workflow"], start=1))  # type: ignore[index]
    lines.extend(["", "## Mission Control calls", "", "Tools:"])
    lines.extend(f"- {item}" for item in skill["tools"])  # type: ignore[index]
    lines.extend(["", "Resources:"])
    lines.extend(f"- {item}" for item in skill["resources"])  # type: ignore[index]
    lines.extend(["", "## User-facing output", ""])
    lines.extend(f"- {item}" for item in skill["output"])  # type: ignore[index]
    lines.extend(["", "## Approval behavior", "", str(skill["approval"]), "", "## Never do", ""])
    lines.extend(f"- {item}" for item in skill["never"])  # type: ignore[index]
    lines.extend(["", "## Failure and fallback", "", str(skill["fallback"]), "", "## Example invocation", "", f"`{skill['example']}`", ""])
    (path / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")

    display_name = str(skill["name"]).replace("mission-control-", "").replace("-", " ").title()
    short_description = str(skill["purpose"])
    if len(short_description) > 100:
        short_description = short_description[:97].rstrip() + "..."
    agents_dir = path / "agents"
    agents_dir.mkdir(exist_ok=True)
    (agents_dir / "openai.yaml").write_text(
        "interface:\n"
        f'  display_name: "{display_name}"\n'
        f'  short_description: "{short_description.replace(chr(34), chr(39))}"\n',
        encoding="utf-8",
    )


def _write_index() -> None:
    skill_map = {str(skill["name"]): skill for skill in SKILLS}
    lines = [
        "# Mission Control Skill Index",
        "",
        "Canonical skill library for Codex chat when it is acting as the Mission Control bridge.",
        "",
        f"Total indexed skills: {len(SKILLS)}",
        "",
    ]
    for group_name, names in GROUPS:
        lines.append(f"## {group_name}")
        lines.append("")
        lines.append("| Skill name | Purpose | When to use | Primary tools/resources | Related skills |")
        lines.append("| --- | --- | --- | --- | --- |")
        for name in names:
            skill = skill_map[name]
            primary = ", ".join(list(skill["tools"])[:2] + list(skill["resources"])[:2])  # type: ignore[index]
            when = list(skill["use_when"])[0]  # type: ignore[index]
            related = ", ".join(RELATED_SKILLS[name])
            lines.append(f"| `{name}` | {skill['purpose']} | {when} | {primary} | {related} |")
        lines.append("")
    INDEX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_docs() -> None:
    lines = [
        "# Mission Control Skill Library",
        "",
        "Mission Control is the headless or background orchestrator. Codex chat is the bridge surface inside the Codex desktop app.",
        "",
        BRIDGE_STATEMENT,
        "",
        "## How the library is grouped",
        "",
        "- Core bridge workflows handle attach, start, status, approvals, handoff, pause, resume, and stop.",
        "- Planning and intake workflows handle import, interviews, clarifications, plans, and scoped follow-up requests.",
        "- Execution and swarm workflows handle swarm plans, contracts, path locks, snapshots, and conflict or stuck-agent handling.",
        "- Validation, evidence, docs, and release workflows keep proof, runbooks, public docs, and release readiness explicit.",
        "- Diagnostics and policy workflows cover recovery, health, model or tool policy, local-first posture, and provider modes.",
        "",
        "## How Codex should use these skills",
        "",
        "- Trigger the narrowest skill that matches the user request.",
        "- Prefer Mission Control tools for actions and Mission Control resources for read-only summaries.",
        "- Use MCP prompts when a flow already exists instead of reinventing the workflow in chat.",
        "- Keep summaries compact, bridge-safe, and honest about unknowns.",
        "- If a tool or resource is missing, mark it as expected or future and fall back gracefully without faking execution.",
        "",
        "## Bridge rule",
        "",
        f"- {BRIDGE_STATEMENT}",
        "- Codex chat should not independently spawn worker agents while Mission Control mode is active.",
        "- Codex chat should not bypass Mission Control approvals, write gates, or swarm controls.",
        "",
        "## Approval relay",
        "",
        "- Use `mission-control-approve` whenever pending decisions exist.",
        "- Explain risk, options, and likely impact before asking the user to choose.",
        "- Confirm the recorded answer after `mission_control_answer_decision` succeeds.",
        "",
        "## Headless mode",
        "",
        "- This library is designed for Codex desktop chat and headless Mission Control orchestration.",
        "- It does not depend on dashboard UI flows, widget reading, or frontend layout state.",
        "- Status, diagnostics, handoff, and event summaries should stay useful even when only MCP tools and resources are available.",
        "",
        "## Examples",
        "",
        "- `Use Mission Control for this repo.` -> `mission-control-orchestrate`",
        "- `Attach this existing repo and let the Manager understand it.` -> `mission-control-import-codebase`",
        "- `What is blocked right now?` -> `mission-control-status` or `mission-control-approve`",
        "- `Give me the final handoff.` -> `mission-control-handoff`",
        "- `The run looks stuck.` -> `mission-control-debug` or `mission-control-recovery-plan`",
        "- `Make this local-first and prefer Ollama if available.` -> `mission-control-local-first` plus `mission-control-ollama-mode`",
        "",
        "## Index",
        "",
        "See `plugins/mission-control/SKILL_INDEX.md` for the grouped index of all 50 skills.",
    ]
    DOC_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _update_manifest_and_docs() -> None:
    manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    manifest["skills"] = [str(skill["name"]) for skill in SKILLS]
    PLUGIN_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    readme = README_PATH.read_text(encoding="utf-8")
    if "SKILL_INDEX.md" not in readme:
        readme = readme.replace(
            "- `skills/`: Codex-facing skill definitions\n",
            "- `skills/`: Codex-facing skill definitions\n- `SKILL_INDEX.md`: grouped index of the Mission Control skill library\n",
        )
    if "MISSION_CONTROL_SKILL_LIBRARY.md" not in readme:
        readme = readme.replace(
            "See [docs/CODEX_PLUGIN_INSTALL.md](../../docs/CODEX_PLUGIN_INSTALL.md) for setup and operator guidance, and [docs/MCP_RESOURCES_AND_PROMPTS.md](../../docs/MCP_RESOURCES_AND_PROMPTS.md) for the resource and prompt catalog.\n",
            "See [docs/CODEX_PLUGIN_INSTALL.md](../../docs/CODEX_PLUGIN_INSTALL.md) for setup and operator guidance, [docs/MCP_RESOURCES_AND_PROMPTS.md](../../docs/MCP_RESOURCES_AND_PROMPTS.md) for the resource and prompt catalog, and [docs/MISSION_CONTROL_SKILL_LIBRARY.md](../../docs/MISSION_CONTROL_SKILL_LIBRARY.md) for the skill grouping and usage rules.\n",
        )
    README_PATH.write_text(readme, encoding="utf-8")

    install_doc = INSTALL_DOC_PATH.read_text(encoding="utf-8")
    if "MISSION_CONTROL_SKILL_LIBRARY.md" not in install_doc:
        install_doc = install_doc.replace(
            "For the full catalog and the safety/redaction rules, see [docs/MCP_RESOURCES_AND_PROMPTS.md](./MCP_RESOURCES_AND_PROMPTS.md).\n",
            "For the full catalog and the safety/redaction rules, see [docs/MCP_RESOURCES_AND_PROMPTS.md](./MCP_RESOURCES_AND_PROMPTS.md).\n\nFor the grouped Codex skill library, see [docs/MISSION_CONTROL_SKILL_LIBRARY.md](./MISSION_CONTROL_SKILL_LIBRARY.md).\n",
        )
    INSTALL_DOC_PATH.write_text(install_doc, encoding="utf-8")


def main() -> None:
    names = {str(skill["name"]) for skill in SKILLS}
    if names != EXPECTED_SKILL_NAMES:
        missing = sorted(EXPECTED_SKILL_NAMES - names)
        extra = sorted(names - EXPECTED_SKILL_NAMES)
        raise SystemExit(f"Skill manifest mismatch. Missing={missing} Extra={extra}")
    for skill in SKILLS:
        _write_skill(skill)
    _write_index()
    _write_docs()
    _update_manifest_and_docs()


if __name__ == "__main__":
    main()
