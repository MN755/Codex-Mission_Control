# Architecture

Codex Mission Control is a local-first desktop orchestration app built from three major layers:

- a desktop shell
- a React frontend
- a FastAPI backend

The split keeps orchestration logic testable while still shipping as a desktop product.

## Desktop shell

The desktop shell lives in `apps/desktop`.

Responsibilities:

- launch the local backend
- open the UI in a native webview
- bundle frontend assets for packaged builds
- persist writable runtime state in a local app-data location when frozen

The web launcher remains available as a fallback for development and recovery.

## Frontend

The frontend lives in `apps/dashboard`.

Key routes:

- `/startup`
- `/setup`
- `/startup-error`
- `/dashboard`
- `/archive`
- `/handoffs`
- `/diagnostics`
- `/skills-tools`
- `/settings`
- `/models-runners`
- project-specific intake, interview, workspace, models, and handoff routes

The frontend uses REST for commands and SSE for live orchestration updates.

The main post-start route model is now:

- `/dashboard` for the home shell
- `/projects/:projectId/:projectSlug?` for the primary workspace shell

The home shell owns global navigation and high-level summaries. The project shell owns the manager loop for a single project.

## Widget platform

Mission Control now uses a real widget platform for summary-style dashboard and workspace UI instead of hardcoding every panel forever and calling that architecture.

Core records:

- `WidgetDefinition`: seeded catalog entry with title, description, scope, category, default area, default size, and availability flags
- `WidgetInstance`: persisted placement, ordering, collapsed state, enabled state, and per-instance config
- `AppEvent`: global event stream for dashboard and widget invalidation

Core response model:

- `WidgetDataResponse`: per-instance payload with status, rendered data, warnings, empty state, and update timestamp

Scopes:

- `dashboard`
- `project`

Supported areas:

- dashboard: `dashboard_main`, `dashboard_right`, `dashboard_bottom`, `dashboard_custom`
- project: `project_right_sidebar`, `project_bottom`, `project_overview`, `project_custom`

The frontend currently surfaces the common areas first and stores the rest for forward compatibility. That is deliberate. Building a clean minimum system beats shipping a fake dashboard builder with commitment issues.

## Backend

The backend lives in `apps/server`.

Primary responsibilities:

- startup coordination
- app-state persistence
- provider detection
- project orchestration
- manager and worker routing
- task and path reservation state
- diagnostics generation
- system-status reporting

## Startup subsystem

The startup subsystem is composed of modules such as:

- `startup.py`
- `runtime_paths.py`
- `diagnostics.py`
- app-profile persistence helpers

It exposes a structured startup state machine with:

- mode
- overall status
- check list
- retry count
- degraded reasons
- diagnostics path

This subsystem is the source of truth for first-time setup vs regular startup routing.

## App-state persistence

Mission Control reuses the single-row app-profile record as the durable app-state source.

That record stores:

- install id
- first-run completion
- setup version completed
- username
- selected provider
- auth mode
- connected-account summary
- default runner and model preferences
- theme and startup behavior
- dashboard widget preferences
- tool permission overrides
- recent startup error state
- timestamps such as created, updated, and last opened

This prevents ordinary code updates from retriggering setup.

## Project model

The main orchestration data model includes:

- `Project`
- `ProjectSettings`
- `SwarmPreferences`
- `SwarmPlan`
- `SwarmAgentSpec`
- `AgentArchetype`
- `SwarmEvent`
- `InterviewSession`
- `InterviewQuestion`
- `ProjectUnderstanding`
- `Plan`
- `Agent`
- `Task`
- `AgentRun`
- `PathReservation`
- `ProjectEvent`
- `ManagerMessage`
- `ManagerQuestion`
- `ApprovalRequest`

Additional command-center state includes:

- dashboard summary derivation
- archive and pin metadata on `Project`
- legacy dashboard widget preferences on `AppProfile`
- legacy project widget preferences on `ProjectSettings`
- `WidgetDefinition`
- `WidgetInstance`
- `AppEvent`
- `SwarmBudget`
- `AgentContract`
- `PathLock`
- `DecisionRecord`
- `ProjectConfidence`
- `RecoveryPlan`
- `AgentStuckSignal`
- `ReviewGate`
- `ModelPolicy`
- `ToolRoutingPolicy`
- `SandboxProfile`
- `ManagerAssumption`
- `RepoIntelligenceSummary`
- `ValidationRecipe`
- `HandoffQualityPreference`
- `ChangeRequest`
- tool permission overrides and a static tool catalog
- swarm planning preferences, plans, and event history

These records support planning, execution, path safety, event replay, widget summaries, and final handoff.

## Widget-backed support models

The widget system relies on real backend state instead of fake card text:

- `SwarmBudget` stores active-agent budget, approval threshold, intensity, and dynamic-spawn pause state
- `AgentContract` stores agent mission, boundaries, tools, validation requirements, stop conditions, and completion expectations
- `PathLock` stores higher-level ownership and waiting-path state for widget display and swarm planning
- `DecisionRecord` stores manager, user, auto-manager, and agent decisions with impact areas and reversibility
- `ProjectConfidence` stores confidence by category plus unresolved unknowns
- `RecoveryPlan` stores manager-proposed recovery paths for blocked or failing work
- `AgentStuckSignal` stores timeout and repeated-failure indicators
- `ReviewGate` stores required or optional review, test, docs, security, and handoff gates
- `ModelPolicy` stores role-to-model routing and fallback policy
- `ToolRoutingPolicy` stores allowed, approval-required, and blocked tools by archetype
- `SandboxProfile` stores named sandbox and approval behavior bundles
- `ManagerAssumption` stores active manager assumptions and later reversals or rejection
- `RepoIntelligenceSummary` stores safe filesystem-derived repo shape data
- `ValidationRecipe` stores validation steps and run posture
- `HandoffQualityPreference` stores expected handoff depth and required sections
- `ChangeRequest` stores follow-up request intake and triage state

## Interview model

The interview subsystem is now manager-driven instead of a static local questionnaire.

Key records:

- `InterviewSession` stores budget, questions asked, stop state, and the session-level confidence and known-facts snapshot
- `InterviewQuestion` stores project-scoped adaptive questions, impact, rationale, source, and answer state
- `ProjectUnderstanding` stores the manager's rolling summary of known facts, unknowns, assumptions, constraints, and confidence by category

The manager interview flow works in turns:

1. `interview.strategy` analyzes project context and produces the first question batch plus an initial understanding snapshot.
2. The user answers questions.
3. `interview.next_batch` updates understanding and decides whether more questions are still worth asking.
4. The manager can stop early whenever enough planning signal exists.

Question generation always stays project-scoped and route-safe through `projectId`.

When live manager generation is unavailable, the backend falls back to a deterministic interview batch generator and marks those questions as `fallback_generated` rather than pretending they came from the live manager.

## Swarm planning model

The swarm subsystem is manager-driven and project-scoped.

Key records:

- `SwarmPreferences` stores user-facing swarm controls such as optimization mode, aggressiveness, max agents, approval threshold, docs depth, testing depth, and dynamic spawn or retire flags.
- `SwarmPlan` stores the current manager-generated swarm strategy, including the selected mode, recommended agent count, risk levels, expected bottlenecks, strategy summary, validation strategy, and approval state.
- `SwarmAgentSpec` stores the planned worker roster for that swarm, including archetype, specialized name, mission, model policy, toolset, path ownership, spawn phase, and retirement condition.
- `AgentArchetype` stores reusable templates for agent types such as frontend, backend, docs, reviewer, security, planner, research, and release handoff.
- `SwarmEvent` stores the swarm history, including plan creation, approval, spawn, retire, reassignment, scaling, bottleneck, and strategy-change events.

Swarm planning rules:

1. The manager chooses the largest useful swarm, not the largest possible swarm.
2. Multiple agents of the same archetype are allowed only when their missions and writable areas are meaningfully separated.
3. Massive-codebase mode emphasizes repo analysis and subsystem ownership before broad parallelism.
4. Documentation-heavy mode can produce multiple docs specialists.
5. High-quality mode biases toward review, testing, and security.
6. Approval controls gate unusually large swarms or aggressive scale-ups.

Dry-run mode uses the same swarm data model and UI surfaces, but spawned agents remain simulated and are not misrepresented as real provider-backed executions.

## Dashboard and project widget model

Dashboard widgets are global summaries. Project widgets are scoped to a single project. That split matters because “one panel to rule them all” is how context leaks and accidental nonsense happen.

Dashboard widgets summarize:

- attention items
- active builds
- handoffs
- provider and runner state
- swarm budget pressure across projects
- project health
- recent decisions and change requests

Project widgets summarize:

- swarm strategy and budget
- agent contracts
- path ownership
- decision history
- confidence and assumptions
- failure recovery
- stuck-agent signals
- review gates
- model, tool, and sandbox policy
- repo intelligence
- validation recipes
- handoff readiness and quality
- change-request state

## Project workspace model

The project workspace is intentionally manager-centered.

Core regions:

- top action banner derived from live project state
- left worker roster with derived display statuses
- center durable manager feed and input
- right queue plus project widgets
- lower task board and activity log as built-in execution panels

Important UI boundary:

- `Manager Chat`, `Manager Queue`, `Task Board`, and `Activity Log` remain built-in surfaces
- summary panels become widgets
- approvals and questions stay in Manager Chat instead of mutating state from random cards

The backend exposes an aggregate workspace payload so the frontend can render the core loop from one project-scoped response instead of stitching together many unrelated calls.

Important safety rule:

- project routes always resolve by `projectId`, never by name alone

## Home shell model

The home shell uses a summary-oriented backend shape instead of loading each page from unrelated low-level queries.

Key command-center aggregates include:

- dashboard summary
- project sidebar vs archive split
- recent handoff summaries
- startup and runtime diagnostics
- tool and skill catalog data
- widget catalog and widget instances
- widget data summaries keyed by scope and project

## Provider model

Mission Control separates orchestration from provider execution.

Supported provider identities:

- `codex`
- `ollama`
- `openai_api`
- `anthropic_api`
- `xai_api`
- `claude_code`
- `custom`

The backend decides what to do next. The runner layer decides how to invoke the selected provider or local adapter.

## Execution model

1. Startup verifies core health.
2. Setup persists user and provider defaults.
3. The dashboard launches project workflows.
4. The manager generates docs, plans, and tasks.
5. Workers execute tasks through the selected runner.
6. The workspace loop can surface questions or approvals before the next action runs.
7. Path reservations prevent conflicting edits.
8. Worker reports feed back into manager routing.
9. Handoff is generated when required work is complete.

## Diagnostics model

Diagnostics are generated when startup cannot recover or when the user requests them manually.

Reports contain:

- startup summary
- failed and degraded checks
- runtime-path state
- database state
- settings and provider state
- recent startup errors
- recommended fixes

Reports intentionally avoid storing raw secrets.

## Live update model

Mission Control uses SSE for both project-scoped and app-scoped summary refresh:

- `ProjectEvent` feeds workspace updates
- `AppEvent` feeds dashboard widget invalidation

Important event families now include:

- `widget_instances_updated`
- `widget_data_updated`
- `swarm_budget_updated`
- `agent_contract_updated`
- `path_lock_updated`
- `decision_record_created`
- `confidence_updated`
- `recovery_plan_created`
- `stuck_signal_created`
- `review_gate_updated`
- `project_health_updated`
- `validation_recipe_updated`
- `handoff_quality_updated`
- `change_request_updated`

The frontend refreshes only the affected widget summaries instead of reloading the entire shell like it has never heard of restraint.
