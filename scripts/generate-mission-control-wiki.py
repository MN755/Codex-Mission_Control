from __future__ import annotations

from pathlib import Path
from textwrap import dedent
import re

ROOT = Path(__file__).resolve().parents[1]
WIKI_DIR = ROOT / "wiki-staging"


def md_link(page: str, label: str | None = None) -> str:
    title = label or page.replace(".md", "").replace("-", " ")
    target = page.replace(".md", "")
    return f"[{title}]({target})"


def status_line(status: str) -> str:
    return f"> Status: {status}"


def render_page(title: str, summary: str, status: str, sections: list[tuple[str, str]]) -> str:
    parts = [f"# {title}", "", summary, "", status_line(status), ""]
    for heading, body in sections:
        parts.extend([f"## {heading}", "", dedent(body).strip(), ""])
    return "\n".join(parts).strip() + "\n"


PAGES: dict[str, str] = {}


def add(page: str, title: str, summary: str, status: str, sections: list[tuple[str, str]]) -> None:
    PAGES[page] = render_page(title, summary, status, sections)


core_pages = [
    "Home.md",
    "Headless-First-Direction.md",
    "Quick-Start.md",
    "Install-From-Codex.md",
    "Headless-Install-and-Autowire.md",
    "Codex-Chat-Workflow.md",
    "MCP-Plugin-Architecture.md",
    "Skills-and-Prompts.md",
    "Mission-Control-Daemon.md",
    "Runner-Configuration.md",
    "Provider-Autowiring.md",
    "Existing-Codebase-Mode.md",
    "Adaptive-Agent-Swarms.md",
    "Manager-AI-vs-Codex-Chat.md",
    "Pending-Decisions-and-Approvals.md",
    "Safety-and-Security-Model.md",
    "Diagnostics-and-Health-Checks.md",
    "Debugging-Common-Issues.md",
    "Logs-and-Runtime-Folders.md",
    "Handoffs-and-Evidence.md",
    "AGENTS-md-and-Agent-Instructions.md",
    "Development-Guide.md",
    "Testing-and-Smoke-Checks.md",
    "Troubleshooting-CLI-Runners.md",
    "Roadmap.md",
    "Glossary.md",
]

supplemental_pages = [
    "Approval-Card-Fallback-Text.md",
    "MCP-Resources-Catalog.md",
    "MCP-Prompts-Catalog.md",
    "Plugin-Health-Doctor.md",
    "Runtime-Configuration-Reference.md",
    "Bridge-Message-Format.md",
    "Codebase-Map-and-Understanding.md",
    "Validation-Summary-Reference.md",
    "Swarm-Modes-Reference.md",
    "Agent-Archetypes.md",
    "Path-Locks-and-Ownership.md",
    "Recovery-Planning.md",
    "Safe-Mode.md",
    "Dry-Run-Mode.md",
    "Localhost-Binding-and-Ports.md",
    "Install-Reports-and-Repair-Mode.md",
    "Evidence-Review-Checklist.md",
    "Contributor-Rules-for-AI-Agents.md",
    "Docs-Source-Map.md",
    "MCP-Bridge-Endpoints.md",
    "Workspace-Attach-and-Project-Lifecycle.md",
    "Manager-Questions.md",
    "Health-Doctor-Example-Output.md",
    "Known-Limitations-and-Non-Goals.md",
    "Webwright-and-Browser-Automation.md",
]

assert len(core_pages) + len(supplemental_pages) == 51

all_page_links = [page.replace(".md", "") for page in core_pages + supplemental_pages]

nav_block = "\n".join(
    [
        f"- {md_link('Home.md')}",
        f"- {md_link('Quick-Start.md')}",
        f"- {md_link('Codex-Chat-Workflow.md')}",
        f"- {md_link('Install-From-Codex.md')}",
        f"- {md_link('MCP-Plugin-Architecture.md')}",
        f"- {md_link('Runner-Configuration.md')}",
        f"- {md_link('Diagnostics-and-Health-Checks.md')}",
        f"- {md_link('Roadmap.md')}",
    ]
)

add(
    "Home.md",
    "Codex Mission Control Wiki",
    "This wiki is the long-form documentation hub for Codex Mission Control as a headless-first orchestration platform for Codex.",
    "Current",
    [
        (
            "What Mission Control is",
            f"""
            Mission Control is currently headless-first. The standalone UI is optional/future. The primary user experience is through Codex chat using the Mission Control plugin/MCP bridge.

            The core runtime path is:

            ```text
            Codex chat
              ->
            Mission Control plugin / MCP bridge
              ->
            Mission Control daemon
              ->
            Manager AI
              ->
            Worker agents / runners
            ```

            Mission Control daemon owns orchestration, Manager AI decisions, background worker coordination, approvals, and handoff generation.
            """,
        ),
        (
            "Current status summary",
            f"""
            Current repo direction is headless Codex-native orchestration.

            - Implemented/current: daemon scripts, MCP resource catalog, prompt workflows, plugin packaging, skill library, approval relay, diagnostics surfaces, operator snapshot and verification surfaces, handoff summaries
            - Partial/experimental: plugin health hardening, runner registry depth, existing-codebase safety features, richer event summaries
            - Optional companion lane: Webwright readiness and browser-task routing when the local browser-agent runtime is installed
            - Planned/future: optional dashboard observability, richer visual monitoring, packaging polish, deeper conflict handling

            Read first:

            - Users: {md_link('Quick-Start.md')}, {md_link('Install-From-Codex.md')}, {md_link('Codex-Chat-Workflow.md')}
            - Contributors: {md_link('Development-Guide.md')}, {md_link('Mission-Control-Daemon.md')}, {md_link('Safety-and-Security-Model.md')}
            - AI/Codex agents: {md_link('Manager-AI-vs-Codex-Chat.md')}, {md_link('Skills-and-Prompts.md')}, {md_link('Contributor-Rules-for-AI-Agents.md')}
            """,
        ),
        (
            "Navigation",
            f"""
            Full navigation:

            Start here:

            - {md_link('Quick-Start.md')}
            - {md_link('Install-From-Codex.md')}
            - {md_link('Headless-First-Direction.md')}

            Headless usage:

            - {md_link('Codex-Chat-Workflow.md')}
            - {md_link('Existing-Codebase-Mode.md')}
            - {md_link('Pending-Decisions-and-Approvals.md')}
            - {md_link('Handoffs-and-Evidence.md')}
            - {md_link('AGENTS-md-and-Agent-Instructions.md')}
            - {md_link('Workspace-Attach-and-Project-Lifecycle.md')}

            Architecture:

            - {md_link('MCP-Plugin-Architecture.md')}
            - {md_link('Mission-Control-Daemon.md')}
            - {md_link('Manager-AI-vs-Codex-Chat.md')}
            - {md_link('Adaptive-Agent-Swarms.md')}
            - {md_link('MCP-Bridge-Endpoints.md')}
            - {md_link('Bridge-Message-Format.md')}

            Runners and providers:

            - {md_link('Runner-Configuration.md')}
            - {md_link('Provider-Autowiring.md')}
            - {md_link('Webwright-and-Browser-Automation.md')}
            - {md_link('Troubleshooting-CLI-Runners.md')}
            - {md_link('Dry-Run-Mode.md')}
            - {md_link('Runtime-Configuration-Reference.md')}

            Safety and approvals:

            - {md_link('Safety-and-Security-Model.md')}
            - {md_link('Safe-Mode.md')}
            - {md_link('Approval-Card-Fallback-Text.md')}
            - {md_link('Manager-Questions.md')}
            - {md_link('Evidence-Review-Checklist.md')}

            Debugging and operations:

            - {md_link('Diagnostics-and-Health-Checks.md')}
            - {md_link('Debugging-Common-Issues.md')}
            - {md_link('Plugin-Health-Doctor.md')}
            - {md_link('Health-Doctor-Example-Output.md')}
            - {md_link('Logs-and-Runtime-Folders.md')}
            - {md_link('Localhost-Binding-and-Ports.md')}
            - {md_link('Recovery-Planning.md')}

            Skills, prompts, and MCP catalogs:

            - {md_link('Skills-and-Prompts.md')}
            - {md_link('MCP-Resources-Catalog.md')}
            - {md_link('MCP-Prompts-Catalog.md')}
            - {md_link('Swarm-Modes-Reference.md')}
            - {md_link('Agent-Archetypes.md')}
            - {md_link('Path-Locks-and-Ownership.md')}
            - {md_link('Validation-Summary-Reference.md')}

            Development and project context:

            - {md_link('Development-Guide.md')}
            - {md_link('Testing-and-Smoke-Checks.md')}
            - {md_link('Contributor-Rules-for-AI-Agents.md')}
            - {md_link('Docs-Source-Map.md')}
            - {md_link('Codebase-Map-and-Understanding.md')}
            - {md_link('Known-Limitations-and-Non-Goals.md')}
            - {md_link('Roadmap.md')}
            - {md_link('Glossary.md')}

            Install and repair details:

            - {md_link('Headless-Install-and-Autowire.md')}
            - {md_link('Install-Reports-and-Repair-Mode.md')}
            """,
        ),
        (
            "Practical examples",
            """
            Example prompts inside Codex chat:

            ```text
            Use Mission Control for this repo.
            Use Mission Control to understand this folder and fix the failing tests.
            Show Mission Control status.
            Show Mission Control operator snapshot.
            Show Mission Control verification brief.
            Show pending Mission Control approvals.
            Get the latest Mission Control handoff.
            Use Mission Control for a browser task with Webwright when available.
            ```
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Headless-First-Direction.md')}, {md_link('MCP-Plugin-Architecture.md')}, {md_link('Mission-Control-Daemon.md')}, and {md_link('Roadmap.md')}.
            """,
        ),
    ],
)

add(
    "Headless-First-Direction.md",
    "Headless First Direction",
    "This page explains why Mission Control is being documented and built as a headless Codex-native platform first.",
    "Current",
    [
        (
            "Why the standalone UI is secondary",
            """
            The project direction is to make Codex chat the primary user-facing surface. That means the most important outputs are:

            - bridge-safe markdown summaries
            - approval and question relay text
            - handoff summaries
            - diagnostics summaries

            The dashboard can remain in the repository as an optional observability layer, but it should not drive product decisions or roadmap sequencing right now.
            """,
        ),
        (
            "In scope now",
            """
            Focus areas:

            - daemon behavior
            - MCP bridge tools, resources, and prompts
            - plugin packaging and autowiring
            - runner detection and configuration
            - existing-codebase intake
            - adaptive swarm safety and coordination
            - approvals, diagnostics, and handoffs
            - docs and skill libraries
            """,
        ),
        (
            "Out of scope unless explicitly requested",
            """
            Do not focus on standalone UI unless explicitly requested.

            User-facing UX means Codex chat output.

            Treat these areas as optional/future unless directly assigned:

            - dashboard layout work
            - widget visual polish
            - React navigation changes
            - desktop-shell presentation changes
            """,
        ),
        (
            "How agents should treat dashboard code",
            f"""
            Dashboard docs and code can be referenced as optional context, but they should not be treated as the product center.

            For bridge work, read {md_link('Manager-AI-vs-Codex-Chat.md')}, {md_link('Codex-Chat-Workflow.md')}, and {md_link('Skills-and-Prompts.md')} first.
            """,
        ),
    ],
)

add(
    "Quick-Start.md",
    "Quick Start",
    "This page shows the fastest practical ways to use Mission Control from Codex chat.",
    "Current",
    [
        (
            "Fastest workflows",
            """
            A. Use in existing repo

            ```text
            Use Mission Control for this repo.
            ```

            B. Use in empty folder

            ```text
            Use Mission Control to set up this new workspace.
            ```

            C. Check status

            ```text
            Show Mission Control status.
            ```

            D. Ask for the operator snapshot

            ```text
            Show Mission Control operator snapshot.
            ```

            E. Approve pending decision

            ```text
            Show pending Mission Control approvals.
            ```

            F. Get handoff

            ```text
            Get the latest Mission Control handoff.
            ```

            G. Route a browser task through Webwright when ready

            ```text
            Use Mission Control for a browser task with Webwright when available.
            ```
            """,
        ),
        (
            "Expected flow",
            """
            1. Codex chat attaches the workspace to Mission Control.
            2. Mission Control imports or scans the repo if needed.
            3. Manager AI plans and orchestrates background workers.
            4. Pending decisions come back through Codex chat.
            5. Codex chat relays the final handoff.
            """,
        ),
        (
            "Example prompts",
            """
            Copyable examples:

            ```text
            Use Mission Control for this repo.
            Use Mission Control to understand this folder and fix the failing tests.
            Show Mission Control status.
            Show Mission Control operator snapshot.
            Show Mission Control verification brief.
            Show pending Mission Control approvals.
            Get the latest Mission Control handoff.
            Use Mission Control for a browser task with Webwright when available.
            ```
            """,
        ),
        (
            "Next reads",
            f"""
            For installation details read {md_link('Install-From-Codex.md')}. For status, approvals, and handoffs read {md_link('Codex-Chat-Workflow.md')} and {md_link('Pending-Decisions-and-Approvals.md')}. For browser-task automation and operator-ready summaries read {md_link('Webwright-and-Browser-Automation.md')} and {md_link('MCP-Resources-Catalog.md')}.
            """,
        ),
    ],
)

add(
    "Install-From-Codex.md",
    "Install From Codex",
    "This page documents the ideal user workflow when the user asks Codex chat to install and wire up Mission Control from GitHub.",
    "Partial / Experimental",
    [
        (
            "Ideal prompt",
            """
            The ideal user prompt is:

            ```text
            Install Mission Control from https://github.com/MN755/Codex-Mission_Control and wire it up for this workspace.
            ```
            """,
        ),
        (
            "What should happen",
            """
            Expected flow:

            1. Clone or reuse the repository.
            2. Run the headless bootstrap path.
            3. Probe environment and runtime prerequisites.
            4. Configure daemon, MCP bridge, plugin files, and skills.
            5. Detect available runners.
            6. Report status back into Codex chat.
            7. Ask for missing login or configuration only when needed.
            """,
        ),
        (
            "Expected output example",
            """
            Example summary:

            ```text
            Mission Control install summary

            - Repo: attached
            - Daemon: ready on localhost
            - MCP bridge: configured
            - Skills: installed
            - Preferred runner: codex_cli
            - Missing action: none
            ```
            """,
        ),
        (
            "Current reality",
            """
            The repo already contains headless docs, plugin package content, MCP catalogs, and daemon start scripts.

            Full one-shot install and autowire scripts should be treated as partial or planned unless verified in the current repo state.
            """,
        ),
        (
            "Related pages",
            f"""
            See {md_link('Headless-Install-and-Autowire.md')}, {md_link('Provider-Autowiring.md')}, and {md_link('Diagnostics-and-Health-Checks.md')}.
            """,
        ),
    ],
)

add(
    "Headless-Install-and-Autowire.md",
    "Headless Install and Autowire",
    "This page describes the intended headless bootstrap and repair experience for Mission Control plugin mode.",
    "Planned / Partial",
    [
        (
            "Planned commands",
            """
            Expected commands:

            ```powershell
            .\\scripts\\install-mission-control-plugin.ps1 -HeadlessOnly
            .\\scripts\\install-mission-control-plugin.ps1 -DryRun
            .\\scripts\\install-mission-control-plugin.ps1 -Repair
            .\\scripts\\mission-control-headless-health.ps1
            ```
            """,
        ),
        (
            "What headless install should do",
            """
            Headless-only install should:

            - avoid requiring dashboard startup
            - probe Python, runtime folders, and daemon readiness
            - configure plugin and MCP bridge files
            - copy or point to skills and prompts
            - detect runners and summarize availability
            - emit an install report suitable for Codex chat
            """,
        ),
        (
            "Repair and health modes",
            """
            Repair mode should reconcile missing plugin files, stale configs, and runtime-directory problems.

            Health mode should stay read-only and report:

            - daemon health
            - MCP bridge health
            - runner availability
            - runtime write access
            - missing prerequisites
            """,
        ),
        (
            "Current status note",
            """
            The repo currently contains daemon start scripts and plugin package content. If the specific install and health scripts above are not present, treat the command surface as planned while using the documented manual steps from the repo docs.
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Install-From-Codex.md')}, {md_link('Provider-Autowiring.md')}, and {md_link('Install-Reports-and-Repair-Mode.md')}.
            """,
        ),
    ],
)

add(
    "Codex-Chat-Workflow.md",
    "Codex Chat Workflow",
    "This page documents the actual user experience inside Codex chat when Mission Control is running in headless bridge mode.",
    "Current",
    [
        (
            "Role split",
            """
            Codex chat relays information.

            Manager AI makes orchestration decisions.

            The user approves, answers, and reviews through Codex chat.
            """,
        ),
        (
            "Status summary example",
            """
            Example:

            ```text
            Mission Control status

            - Project: repo-startup-fix
            - Phase: validation
            - Manager state: waiting on approval
            - Active agents: 2
            - Blocker: test command requires approval
            - Next step: approve or deny the requested validation run
            - Handoff readiness: not ready
            ```
            """,
        ),
        (
            "Approval and question examples",
            """
            Approval example:

            ```text
            Pending decision: command approval
            Risk: low
            Reason: Mission Control wants to run the test suite before handoff.
            Options: approve once, deny
            ```

            Manager question example:

            ```text
            Mission Control needs one product decision before planning:
            Should the final handoff prioritize builder-ready implementation detail or operator-ready usage instructions?
            ```
            """,
        ),
        (
            "Event digest, handoff, and failure examples",
            """
            Event digest example:

            ```text
            Last 15 minutes
            - Workspace attached
            - Existing repo scanned read-only
            - Manager created targeted fix plan
            - Validation command requested approval
            ```

            Handoff example:

            ```text
            Handoff summary
            - Confidence: medium
            - Validation: tests ran, typecheck skipped
            - Known limitation: deployment not verified
            ```

            Failure example:

            ```text
            Debug summary
            - Blocker: Codex CLI not detected
            - Recommended fix: verify local Codex installation and login status
            ```
            """,
        ),
        (
            "Related pages",
            f"""
            Read {md_link('Manager-AI-vs-Codex-Chat.md')}, {md_link('Pending-Decisions-and-Approvals.md')}, {md_link('Handoffs-and-Evidence.md')}, and {md_link('Debugging-Common-Issues.md')}.
            """,
        ),
    ],
)

add(
    "MCP-Plugin-Architecture.md",
    "MCP Plugin Architecture",
    "This page explains how the plugin package, MCP tools, MCP resources, and MCP prompts work together around the Mission Control daemon.",
    "Current",
    [
        (
            "Why the split exists",
            """
            The MCP layer should stay thin and predictable.

            - Resources are read-only state summaries.
            - Tools perform bridge actions.
            - Prompts guide reusable workflows.
            - The daemon remains the orchestration authority.
            """,
        ),
        (
            "Expected tools",
            """
            Expected tools:

            - `mission_control_attach_workspace`
            - `mission_control_start_task`
            - `mission_control_get_status`
            - `mission_control_get_pending_decisions`
            - `mission_control_answer_decision`
            - `mission_control_pause`
            - `mission_control_resume`
            - `mission_control_get_handoff`
            - `mission_control_plugin_health`
            - `mission_control_enable_safe_mode`
            """,
        ),
        (
            "Expected resources",
            """
            Expected resources:

            - `mission-control://projects/{project_id}/status`
            - `mission-control://projects/{project_id}/agents`
            - `mission-control://projects/{project_id}/pending-decisions`
            - `mission-control://projects/{project_id}/handoff`
            - `mission-control://projects/{project_id}/codebase-map`
            - `mission-control://projects/{project_id}/diagnostics`

            Additional resources such as swarm-plan, risk-register, validation-summary, and orchestration event summaries may also be present depending on the package version.
            """,
        ),
        (
            "Prompts and plugin package",
            """
            The plugin package should include:

            - MCP config example
            - prompt catalog
            - resource catalog
            - skill folders
            - chat-safe markdown templates

            Prompts should guide flows such as attach workspace, continue orchestration, review handoff, and answer pending approvals.
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Skills-and-Prompts.md')}, {md_link('MCP-Resources-Catalog.md')}, {md_link('MCP-Prompts-Catalog.md')}, and {md_link('MCP-Bridge-Endpoints.md')}.
            """,
        ),
    ],
)

add(
    "Skills-and-Prompts.md",
    "Skills and Prompts",
    "This page documents the Mission Control skill library and the workflow prompts used by Codex chat in bridge mode.",
    "Current",
    [
        (
            "What a skill is",
            """
            A skill is a reusable Codex instruction bundle. For Mission Control, skills should:

            - keep Codex in the bridge role
            - call Mission Control tools/resources/prompts when available
            - preserve approvals
            - avoid direct shell execution inside Mission Control mode
            - summarize clearly for chat
            """,
        ),
        (
            "Bridge rules",
            """
            The Codex chat agent is not the Manager AI.

            It should not:

            - independently spawn worker agents
            - invent separate manager plans
            - bypass pending decisions
            - claim work happened without backend evidence
            """,
        ),
        (
            "Important skills",
            """
            Core skills:

            - `mission-control-orchestrate`
            - `mission-control-import-codebase`
            - `mission-control-status`
            - `mission-control-approve`
            - `mission-control-handoff`
            - `mission-control-debug`
            - `mission-control-swarm`
            - `mission-control-safe-mode`
            - `mission-control-resume`
            - `mission-control-agents-md`

            Additional bridge-oriented skills should include:

            - `mission-control-install-from-github`
            - `mission-control-autowire-providers`

            If those specific skills are not present yet, treat them as planned wrappers around the documented install/autowire flows.
            """,
        ),
        (
            "Prompts",
            """
            Common workflow prompts should cover:

            - attach current workspace
            - use Mission Control for this repo
            - import existing codebase
            - continue orchestration
            - show pending approvals
            - review latest handoff
            - explain current swarm
            - enable safe mode
            - generate AGENTS.md proposal
            """,
        ),
        (
            "Related pages",
            f"""
            Read {md_link('MCP-Plugin-Architecture.md')}, {md_link('Manager-AI-vs-Codex-Chat.md')}, {md_link('Contributor-Rules-for-AI-Agents.md')}, and {md_link('AGENTS-md-and-Agent-Instructions.md')}.
            """,
        ),
    ],
)

add(
    "Mission-Control-Daemon.md",
    "Mission Control Daemon",
    "This page explains the daemon as the long-running local orchestration surface behind the Codex chat bridge.",
    "Current",
    [
        (
            "Responsibilities",
            """
            The daemon owns:

            - orchestration sessions
            - Manager AI execution
            - worker runner registry
            - pending decisions
            - bridge messages
            - handoffs
            - diagnostics
            - runtime folders
            - event logs
            """,
        ),
        (
            "Lifecycle",
            """
            Typical lifecycle:

            1. Start on localhost.
            2. Accept bridge requests for attach, start, status, and handoff.
            3. Persist orchestration state.
            4. Coordinate Manager and worker execution.
            5. Shut down safely without dropping state.

            Copyable commands:

            ```powershell
            .\\scripts\\start-mission-control-daemon.ps1
            ```

            ```bash
            ./scripts/start-mission-control-daemon.sh
            ```
            """,
        ),
        (
            "Health and status",
            """
            Health checks should confirm:

            - daemon reachable
            - runtime folders writable
            - SQLite usable
            - localhost binding preserved
            - runner registry readable
            - plugin health summary available
            """,
        ),
        (
            "Safe shutdown",
            """
            Safe shutdown should preserve orchestration state, partial handoffs, pending decisions, and diagnostics context.

            It should not require the dashboard to be open.
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Logs-and-Runtime-Folders.md')}, {md_link('Diagnostics-and-Health-Checks.md')}, {md_link('MCP-Bridge-Endpoints.md')}, and {md_link('Runner-Configuration.md')}.
            """,
        ),
    ],
)

add(
    "Runner-Configuration.md",
    "Runner Configuration",
    "This page documents the supported runner types, how Mission Control should detect them, and what the user may need to configure.",
    "Current",
    [
        (
            "Supported runner types",
            """
            Supported runner types:

            - `dry_run`
            - `codex_cli`
            - `ollama`
            - `claude_cli`
            - `openai_api`
            - `anthropic_api`
            - `xai_api`
            - `custom`
            """,
        ),
        (
            "Detection and user action",
            """
            Detection guidance:

            - `dry_run`: always available and safe fallback
            - `codex_cli`: detect local CLI and login state; preferred when available
            - `ollama`: use the built-in `scripts/ollama_adapter.py` recipe and require a reachable local endpoint
            - `claude_cli`: detect installed CLI and configuration
            - `*_api`: use the built-in `scripts/api_provider_adapter.py` recipe but still require secure provider credentials
            - `custom`: only available when explicitly configured
            - `Webwright`: not a runner type; it is an optional browser-agent companion that should be checked separately when the task is about real browser automation
            """,
        ),
        (
            "Billing and security notes",
            """
            Notes:

            - Codex CLI via ChatGPT/Codex login should be preferred where available.
            - API providers may incur billing and require explicit configuration.
            - Ollama is local but still requires installed models and local compute budget.
            - Built-in adapter recipes reduce setup friction but do not silently make a provider ready when auth or the endpoint is still missing.
            - Dry-run is the safe fallback when no runner is ready.
            """,
        ),
        (
            "Fallback behavior",
            """
            If the preferred runner is unavailable, Mission Control should:

            1. report the reason clearly
            2. recommend a safe next runner
            3. fall back to `dry_run` only when execution confidence would otherwise be misleading
            """,
        ),
        (
            "Related pages",
            f"""
            Read {md_link('Provider-Autowiring.md')}, {md_link('Webwright-and-Browser-Automation.md')}, {md_link('Troubleshooting-CLI-Runners.md')}, {md_link('Dry-Run-Mode.md')}, and {md_link('Diagnostics-and-Health-Checks.md')}.
            """,
        ),
    ],
)

add(
    "Provider-Autowiring.md",
    "Provider Autowiring",
    "This page describes what Mission Control can detect automatically, what requires explicit user action, and what must never be automatic.",
    "Current",
    [
        (
            "What can be automatic",
            """
            Automatic probing can safely check:

            - local CLI presence
            - login state availability when the CLI exposes it
            - daemon and runtime readiness
            - localhost health endpoints
            - plugin/skill file presence
            - Ollama service presence
            - built-in adapter recipe availability for Ollama and API-backed providers
            """,
        ),
        (
            "What requires user action",
            """
            User action may still be needed for:

            - Codex login
            - Claude CLI login or install
            - API provider secrets in a secure store
            - network-heavy model downloads
            - elevated permissions outside the workspace
            - app reload after plugin or MCP configuration changes
            """,
        ),
        (
            "What should never be automatic",
            """
            Never do these automatically:

            - print raw API keys into logs, diagnostics, or docs
            - pull huge Ollama models without approval
            - silently switch to billed API providers
            - silently widen filesystem permissions
            """,
        ),
        (
            "Redaction and reporting",
            """
            Install and health reports should return:

            - detected providers
            - configured providers
            - blocked or missing prerequisites
            - next manual action

            Reports should not contain secrets.
            """,
        ),
        (
            "Related pages",
            f"""
            See {md_link('Runner-Configuration.md')}, {md_link('Install-From-Codex.md')}, {md_link('Headless-Install-and-Autowire.md')}, and {md_link('Safety-and-Security-Model.md')}.
            """,
        ),
    ],
)

add(
    "Existing-Codebase-Mode.md",
    "Existing Codebase Mode",
    "This page explains how Mission Control should attach and understand a non-empty repository before writing to it.",
    "Current",
    [
        (
            "Core workflow",
            """
            Existing-codebase mode should:

            1. attach the current folder
            2. classify it as an existing repo
            3. run a read-only scan first
            4. build a codebase map
            5. produce a codebase understanding summary
            6. choose skip, quick, or full interview if needed
            7. only then move into planning or execution

            Scan outputs should prefer repo-relative metadata for docs, CI, deployment files, and risk flags so the same understanding survives across machines.
            """,
        ),
        (
            "Safety mode and AGENTS.md",
            """
            Imported codebase safety mode should favor:

            - read-only scan first
            - approval for write permission
            - AGENTS.md detection and proposal review
            - progressive understanding for large repositories
            """,
        ),
        (
            "Example flow",
            """
            Example prompt:

            ```text
            Use Mission Control to understand this repo and fix startup.
            ```

            Expected response:

            ```text
            Mission Control attached the repo, completed a read-only scan, detected the stack, and is waiting on one clarification before planning the startup fix.
            ```
            """,
        ),
        (
            "Large repositories",
            """
            For large repos, understanding should be progressive:

            - top-level map first
            - important entry points next
            - focused deeper scan only when the requested task justifies it
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Codebase-Map-and-Understanding.md')}, {md_link('AGENTS-md-and-Agent-Instructions.md')}, and {md_link('Quick-Start.md')}.
            """,
        ),
    ],
)

add(
    "Adaptive-Agent-Swarms.md",
    "Adaptive Agent Swarms",
    "This page explains how Mission Control should plan, scale, and constrain worker swarms under Manager AI control.",
    "Current",
    [
        (
            "What the Manager plans",
            """
            The Manager should decide:

            - swarm mode
            - agent archetypes
            - scale up or down timing
            - path ownership and contracts
            - dynamic retirement
            - coordination risk
            - approval threshold for larger swarms
            """,
        ),
        (
            "Swarm modes",
            """
            Modes:

            - `fastest_build`
            - `balanced`
            - `high_quality`
            - `documentation_heavy`
            - `research_planning`
            - `massive_codebase`
            - `safe_mode`
            """,
        ),
        (
            "Safety constraints",
            """
            Adaptive swarms should still obey:

            - max agent limits
            - write scope restrictions
            - path locks
            - contract boundaries
            - high-risk approval gates
            - local performance guardrails so weaker machines are not overcommitted
            """,
        ),
        (
            "Capability-aware subagent bursts",
            """
            Mission Control now reflects the current subagent policy inside burst specs instead of pretending every burst is permanently read-only.

            That means:

            - read-only stays the default
            - limited-write bursts can use `workspace-write`
            - command-capable bursts say so explicitly
            - generated custom Codex subagents inherit the same policy
            """,
        ),
        (
            "User-facing explanation",
            """
            Codex chat should summarize swarm state as:

            - current mode
            - active agents
            - path conflict risk
            - whether dynamic spawning is paused
            - whether approval is needed before scaling
            """,
        ),
        (
            "Related pages",
            f"""
            Read {md_link('Swarm-Modes-Reference.md')}, {md_link('Agent-Archetypes.md')}, {md_link('Path-Locks-and-Ownership.md')}, and {md_link('Manager-AI-vs-Codex-Chat.md')}.
            """,
        ),
    ],
)

add(
    "Manager-AI-vs-Codex-Chat.md",
    "Manager AI vs Codex Chat",
    "This page defines the most important role split in the project: Codex chat is the bridge, and Mission Control Manager AI is the orchestrator.",
    "Current",
    [
        (
            "Correct role model",
            """
            User only sees Codex chat.

            Codex chat sends requests downward and relays status upward.

            Mission Control Manager AI remains the project lead behind the bridge.

            Worker agents stay behind the Manager.
            """,
        ),
        (
            "What Codex chat should do",
            """
            Codex chat should:

            - attach the workspace
            - start or continue a Mission Control task
            - show compact status
            - relay approvals and manager questions
            - return handoffs and diagnostics
            """,
        ),
        (
            "What Codex chat should not do",
            """
            Codex chat should not:

            - become a second manager
            - independently spawn workers
            - bypass approvals
            - invent handoffs
            - silently change scope
            """,
        ),
        (
            "Example",
            """
            Good:

            ```text
            Mission Control wants approval to run the test suite. Approve once or deny?
            ```

            Bad:

            ```text
            I decided to skip the approval and just run the tests myself.
            ```
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Codex-Chat-Workflow.md')}, {md_link('Pending-Decisions-and-Approvals.md')}, and {md_link('Skills-and-Prompts.md')}.
            """,
        ),
    ],
)

add(
    "Pending-Decisions-and-Approvals.md",
    "Pending Decisions and Approvals",
    "This page explains the PendingDecision model, user approval flow, risk levels, and decision categories used by Mission Control.",
    "Current",
    [
        (
            "Decision model",
            """
            Pending decisions cover:

            - command approvals
            - tool approvals
            - write permissions
            - manager questions
            - swarm approvals
            - snapshot approvals
            - handoff review
            - recovery decisions
            - scope change decisions
            - safe mode confirmations
            """,
        ),
        (
            "Risk levels and auto-decision rules",
            """
            Expected risk labels:

            - low
            - medium
            - high
            - critical

            High-risk and critical actions should not auto-approve. Auto-decision rules, if present, should stay limited to low-risk, well-scoped actions and still record an audit trail.
            """,
        ),
        (
            "Examples",
            """
            Command approval example:

            ```text
            Pending decision: command approval
            Risk: low
            Command summary: run the repo test suite
            ```

            Manager question example:

            ```text
            Pending decision: manager question
            Risk: medium
            Question: should the final handoff optimize for builder detail or operator usage?
            ```
            """,
        ),
        (
            "User flow",
            """
            1. Mission Control creates the decision.
            2. Codex chat renders a safe summary.
            3. User answers through chat.
            4. Codex sends the answer back through the decision tool.
            5. Mission Control resumes or remains blocked.
            """,
        ),
        (
            "Related pages",
            f"""
            Read {md_link('Approval-Card-Fallback-Text.md')}, {md_link('Manager-Questions.md')}, {md_link('Safe-Mode.md')}, and {md_link('Safety-and-Security-Model.md')}.
            """,
        ),
    ],
)

add(
    "Safety-and-Security-Model.md",
    "Safety and Security Model",
    "This page summarizes the practical safety model for headless Mission Control operation, approvals, redaction, and local-only daemon behavior.",
    "Current",
    [
        (
            "Core principles",
            """
            Mission Control is local-first.

            The daemon should be localhost-only.

            Secrets should never appear in logs, docs, diagnostics, approval summaries, or handoffs.

            High-risk actions should remain behind explicit approval.
            """,
        ),
        (
            "What is not allowed",
            """
            Mission Control should not:

            - expose raw API keys in storage or docs
            - run arbitrary shell commands through MCP as an uncontrolled escape hatch
            - silently switch to billed providers
            - skip safe imported-codebase mode
            - weaken approvals to make demos look smoother
            """,
        ),
        (
            "Imported codebase safety",
            """
            Imported codebases should default to:

            - read-only scan first
            - write permission prompts
            - redacted summaries
            - cautious runner use
            """,
        ),
        (
            "Billing and external effects",
            """
            API billing warnings should be explicit.

            Plugin/account side effects should remain gated.

            Network-heavy actions such as model pulls or dependency installs should not be treated like harmless local reads.
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Provider-Autowiring.md')}, {md_link('Pending-Decisions-and-Approvals.md')}, {md_link('Safe-Mode.md')}, and {md_link('Logs-and-Runtime-Folders.md')}.
            """,
        ),
    ],
)

add(
    "Diagnostics-and-Health-Checks.md",
    "Diagnostics and Health Checks",
    "This page describes how to inspect plugin, daemon, MCP, runner, and runtime health without relying on the optional dashboard.",
    "Current",
    [
        (
            "What to check",
            """
            Health checks should cover:

            - plugin health doctor
            - daemon health
            - MCP bridge health
            - runner health
            - runtime writable state
            - Codex CLI login
            - Ollama status
            - Claude CLI status
            - Webwright readiness when browser-agent automation is part of the task
            - startup freshness and last completed check time
            - degraded vs broken classification
            """,
        ),
        (
            "Example commands",
            """
            Copyable checks:

            ```powershell
            .\\scripts\\start-mission-control-daemon.ps1
            .\\scripts\\mission-control-support-bundle.ps1
            Invoke-WebRequest http://127.0.0.1:8010/api/health
            codex --version
            codex login status
            ```
            """,
        ),
        (
            "Example diagnostic summary",
            """
            Example:

            ```text
            Mission Control health

            - Overall: degraded
            - Daemon: ready
            - MCP bridge: ready
            - Codex CLI: missing login
            - Ollama: not running
            - Webwright: optional and not installed
            - Runtime folder: writable
            - Recommended next step: log into Codex CLI or use dry_run
            ```
            """,
        ),
        (
            "Related pages",
            f"""
            Read {md_link('Plugin-Health-Doctor.md')}, {md_link('Debugging-Common-Issues.md')}, {md_link('Troubleshooting-CLI-Runners.md')}, and {md_link('Logs-and-Runtime-Folders.md')}.
            """,
        ),
    ],
)

add(
    "Debugging-Common-Issues.md",
    "Debugging Common Issues",
    "This page collects the most common failure patterns for headless Mission Control usage and the fastest checks to run from Codex chat or a local shell.",
    "Current",
    [
        (
            "Daemon will not start",
            """
            Symptoms:

            - health endpoint unavailable
            - startup script exits immediately

            Likely cause:

            - port conflict
            - Python environment not ready
            - another Mission Control daemon already owns the expected identity on the same port

            Checks:

            ```powershell
            .\\scripts\\start-mission-control-daemon.ps1
            Invoke-WebRequest http://127.0.0.1:8010/api/health
            ```

            Fix:

            - verify Python environment
            - inspect port usage
            - confirm which repo root owns the live daemon
            - check runtime folder permissions
            """,
        ),
        (
            "MCP bridge unreachable",
            """
            Symptoms:

            - Codex can see skills but not tools
            - status requests fail

            Likely cause:

            - MCP config not loaded
            - daemon token mismatch
            - bridge cannot reach localhost daemon
            - host app reload still has not happened after plugin or MCP config changes

            Checks:

            - inspect MCP config
            - verify daemon health
            - run plugin health doctor if available

            Fix:

            - reload Codex MCP config
            - restart daemon
            - re-run health checks
            """,
        ),
        (
            "Codex CLI missing or not logged in",
            """
            Symptoms:

            - preferred runner falls back unexpectedly
            - health doctor reports missing login

            Likely cause:

            - local CLI not installed or not authenticated

            Checks:

            ```powershell
            codex --version
            codex login status
            ```

            Fix:

            - install Codex CLI if missing
            - complete local login
            - re-run health checks
            """,
        ),
        (
            "Ollama installed but not running",
            """
            Symptoms:

            - Ollama mode requested but unavailable
            - local-model runner not detected

            Likely cause:

            - service stopped
            - no model installed
            - provider adapter was overridden badly

            Checks:

            - verify Ollama service is active
            - verify the intended model exists locally

            Fix:

            - start Ollama
            - install the required local model with explicit user awareness
            - restore the built-in adapter recipe unless a custom override is intentional
            - fall back to Codex CLI or dry-run if needed
            """,
        ),
        (
            "API provider selected but still degraded",
            """
            Symptoms:

            - OpenAI, Anthropic, or xAI was selected
            - startup or runner status still says runtime is not ready

            Likely cause:

            - the built-in adapter recipe exists, but the external API key is still missing

            Checks:

            - verify the provider key in the host environment
            - rerun the support bundle and health checks

            Fix:

            - set the API key outside chat
            - rerun startup or plugin health
            """,
        ),
        (
            "Claude CLI not detected",
            """
            Symptoms:

            - Claude CLI mode requested but unavailable

            Likely cause:

            - CLI not installed or not configured

            Checks:

            - verify CLI presence on PATH
            - inspect local configuration

            Fix:

            - install or configure Claude CLI
            - keep current runner policy until it is verified
            """,
        ),
        (
            "Webwright not ready",
            """
            Symptoms:

            - browser-task workflow reports setup blockers
            - Mission Control refuses to fake browser-agent execution

            Likely cause:

            - `webwright` is not installed in the same Python environment as Mission Control
            - Playwright or Chromium runtime is missing

            Checks:

            - inspect the project-scoped Webwright readiness surface
            - verify the local Python environment

            Fix:

            - install the upstream Webwright runtime
            - install the Chromium browser runtime through Playwright
            - rerun the readiness check before claiming browser coverage
            """,
        ),
        (
            "API provider not configured",
            """
            Symptoms:

            - API runner requested but unavailable

            Likely cause:

            - secure provider config missing

            Checks:

            - inspect configured provider state in Mission Control

            Fix:

            - configure the provider through the secure path
            - do not paste raw keys into chat
            """,
        ),
        (
            "Pending approval stuck",
            """
            Symptoms:

            - orchestration remains waiting on user
            - the same approval keeps reappearing

            Likely cause:

            - user answer never reached Mission Control
            - answer payload invalid
            - upstream command remains blocked

            Checks:

            - re-fetch pending decisions
            - confirm the decision id and selected option

            Fix:

            - answer the decision again through the bridge tool
            - inspect bridge health if answers are not recorded
            """,
        ),
        (
            "Handoff missing evidence",
            """
            Symptoms:

            - final summary exists but confidence is weak
            - claims are not backed by validation

            Likely cause:

            - validation skipped
            - dry-run only
            - artifacts not recorded

            Checks:

            - review validation summary
            - review evidence checklist

            Fix:

            - run the missing validation through Mission Control
            - mark remaining gaps honestly if validation cannot run
            """,
        ),
        (
            "Import scan slow or huge repo scan",
            """
            Symptoms:

            - existing-codebase attach takes too long
            - codebase understanding appears too broad

            Likely cause:

            - repository is large
            - scan is trying to go too deep too early

            Checks:

            - review the initial codebase map scope
            - check whether a focused task was provided

            Fix:

            - use progressive understanding
            - start with top-level map and focused entry points
            """,
        ),
        (
            "Permissions denied or port already in use",
            """
            Symptoms:

            - write-permission failures
            - daemon startup collision

            Likely cause:

            - workspace boundary restriction
            - another process already bound to the port

            Checks:

            - confirm the target path is inside the intended workspace
            - inspect port usage before restarting the daemon

            Fix:

            - request the correct write permission through Mission Control
            - free or change the daemon port deliberately
            """,
        ),
        (
            "Cross references",
            """
            Dedicated follow-up pages:

            See dedicated pages:

            - {codex}
            - {runners}
            - {codebase}
            - {handoff}
            """.format(
                codex=md_link("Troubleshooting-CLI-Runners.md"),
                runners=md_link("Runner-Configuration.md"),
                codebase=md_link("Existing-Codebase-Mode.md"),
                handoff=md_link("Handoffs-and-Evidence.md"),
            ),
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Diagnostics-and-Health-Checks.md')}, {md_link('Localhost-Binding-and-Ports.md')}, {md_link('Recovery-Planning.md')}, and {md_link('Health-Doctor-Example-Output.md')}.
            """,
        ),
    ],
)

add(
    "Logs-and-Runtime-Folders.md",
    "Logs and Runtime Folders",
    "This page explains where Mission Control stores runtime state, diagnostics, logs, and install reports, and what should not be shared publicly.",
    "Current",
    [
        (
            "What lives in runtime folders",
            """
            Expect runtime storage for:

            - SQLite state
            - daemon token or bridge runtime metadata
            - diagnostics reports
            - event summaries
            - install or repair reports
            - local configuration snapshots
            """,
        ),
        (
            "What not to share",
            """
            Do not share publicly:

            - daemon tokens
            - raw approval payloads with secrets
            - private paths that reveal local user details
            - unredacted diagnostics bundles
            """,
        ),
        (
            "Collecting a safe debug bundle",
            """
            Safe debug bundle guidance:

            1. prefer summarized diagnostics
            2. redact usernames, tokens, and paths where needed
            3. include health doctor output, not raw logs first
            4. include the exact command or step that failed
            """,
        ),
        (
            "Related pages",
            f"""
            Read {md_link('Diagnostics-and-Health-Checks.md')}, {md_link('Plugin-Health-Doctor.md')}, and {md_link('Safety-and-Security-Model.md')}.
            """,
        ),
    ],
)

add(
    "Handoffs-and-Evidence.md",
    "Handoffs and Evidence",
    "This page documents the handoff format, evidence standards, dry-run warnings, and review expectations for Mission Control results.",
    "Current",
    [
        (
            "Required handoff sections",
            """
            Handoffs should include:

            - status
            - confidence and evidence level
            - what changed
            - how to run
            - validation and evidence
            - known limitations
            - next recommended tasks
            - important files or artifacts
            """,
        ),
        (
            "Evidence rules",
            """
            Do not claim tests or builds passed without evidence.

            If validation was not run, say so explicitly.

            If the run was dry-run, mark it clearly.
            """,
        ),
        (
            "Review checklist",
            """
            Reviewers should ask:

            - were commands actually run?
            - are the claims backed by output or artifacts?
            - are known limitations honest?
            - does the handoff say what still needs review?
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Evidence-Review-Checklist.md')}, {md_link('Testing-and-Smoke-Checks.md')}, and {md_link('Codex-Chat-Workflow.md')}.
            """,
        ),
    ],
)

add(
    "AGENTS-md-and-Agent-Instructions.md",
    "AGENTS md and Agent Instructions",
    "This page explains why AGENTS.md matters, what it should contain, and how Mission Control should propose or use it for imported repositories.",
    "Current",
    [
        (
            "Why AGENTS.md matters",
            """
            AGENTS.md gives structured instructions to Codex-style agents and bridge flows.

            It should reduce ambiguity around:

            - setup and run commands
            - test expectations
            - architecture notes
            - do-not-touch areas
            - safety rules
            """,
        ),
        (
            "What it should include",
            """
            Recommended sections:

            - project overview
            - setup commands
            - run commands
            - test commands
            - build commands
            - architecture notes
            - coding rules
            - do-not-touch areas
            - safety rules
            - completion report format
            """,
        ),
        (
            "Mission Control workflow",
            """
            Mission Control should:

            1. read the codebase map
            2. detect whether AGENTS.md already exists
            3. propose content
            4. ask before writing
            """,
        ),
        (
            "Example outline",
            """
            Example prompt:

            ```text
            Use Mission Control to propose AGENTS.md from the current codebase understanding.
            ```
            """,
        ),
        (
            "Related pages",
            f"""
            Read {md_link('Existing-Codebase-Mode.md')}, {md_link('Skills-and-Prompts.md')}, and {md_link('Contributor-Rules-for-AI-Agents.md')}.
            """,
        ),
    ],
)

add(
    "Development-Guide.md",
    "Development Guide",
    "This page gives contributors a practical map of the repository and the current headless-first development priorities.",
    "Current",
    [
        (
            "Repo structure",
            """
            Major areas:

            - `apps/server/` for backend and daemon logic
            - `plugins/mission-control/` for plugin package, MCP catalogs, prompts, and skills
            - `.codex/skills/` and `.codex/plugins/` for repo-local Codex integration assets
            - `scripts/` for launchers, generators, and validators
            - `docs/` for long-form repo documentation
            - `examples/` for Codex workflow examples
            """,
        ),
        (
            "Current contribution direction",
            """
            Prefer work on:

            - daemon and runtime behavior
            - MCP bridge and catalogs
            - headless install and health flows
            - skills, prompts, and bridge-safe formatting
            - diagnostics, security, and tests

            Do not focus on the optional standalone UI unless explicitly asked.
            """,
        ),
        (
            "Useful commands",
            """
            Backend setup:

            ```powershell
            cd apps/server
            python -m pip install -e .[dev]
            python -m pytest
            ```

            Daemon start:

            ```powershell
            .\\scripts\\start-mission-control-daemon.ps1
            ```
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Testing-and-Smoke-Checks.md')}, {md_link('Contributor-Rules-for-AI-Agents.md')}, {md_link('Docs-Source-Map.md')}, and {md_link('Roadmap.md')}.
            """,
        ),
    ],
)

add(
    "Testing-and-Smoke-Checks.md",
    "Testing and Smoke Checks",
    "This page explains what should be validated before calling a Mission Control change ready for handoff.",
    "Current",
    [
        (
            "What to test",
            """
            Validation targets:

            - backend tests
            - MCP catalog and prompt checks
            - skill validation
            - headless happy path
            - runner detection smoke checks
            - startup freshness and provider-adapter smoke checks
            - subagent policy behavior checks
            - diagnostic summary output
            """,
        ),
        (
            "Example commands",
            """
            Copyable examples:

            ```powershell
            cd apps/server
            python -m pytest
            ```

            ```powershell
            python scripts\\validate-mission-control-skills.py
            ```
            """,
        ),
        (
            "What should pass before handoff",
            """
            Before handoff, aim to have:

            - relevant tests run
            - validation gaps called out honestly
            - skill or catalog docs regenerated if changed
            - diagnostics clean enough to explain known degraded states
            """,
        ),
        (
            "Related pages",
            f"""
            Read {md_link('Handoffs-and-Evidence.md')}, {md_link('Validation-Summary-Reference.md')}, and {md_link('Diagnostics-and-Health-Checks.md')}.
            """,
        ),
    ],
)

add(
    "Troubleshooting-CLI-Runners.md",
    "Troubleshooting CLI Runners",
    "This page is a focused runner troubleshooting reference for Codex CLI, Ollama, Claude CLI, API providers, and dry-run mode.",
    "Current",
    [
        (
            "Codex CLI",
            """
            Detection:

            - CLI installed
            - login status readable

            Common issues:

            - CLI missing
            - not logged in

            Fixes:

            - verify installation
            - run login flow
            - re-run plugin health checks
            """,
        ),
        (
            "Ollama and Claude CLI",
            """
            Ollama:

            - detect service
            - detect installed models
            - common issue: service not running
            - common issue: requested model missing locally

            Claude CLI:

            - detect CLI
            - common issue: not configured on the local machine
            - fallback: keep current runner or use dry_run
            """,
        ),
        (
            "API providers and dry-run",
            """
            API providers:

            - require explicit secure config
            - may incur billing
            - should never require raw key pasting into chat

            Dry-run:

            - safe fallback
            - useful for docs, bridge behavior, and workflow validation
            - should not be presented as proof of real execution
            """,
        ),
        (
            "Checks and fixes by runner",
            """
            Codex CLI checks:

            ```powershell
            codex --version
            codex login status
            ```

            Ollama checks:

            - confirm the service is running
            - confirm the required model is installed

            Claude CLI checks:

            - confirm the CLI exists on PATH
            - confirm local configuration is present

            API provider checks:

            - confirm secure provider config exists
            - confirm billing expectations are understood
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Runner-Configuration.md')}, {md_link('Provider-Autowiring.md')}, {md_link('Dry-Run-Mode.md')}, and {md_link('Debugging-Common-Issues.md')}.
            """,
        ),
    ],
)

add(
    "Roadmap.md",
    "Roadmap",
    "This page tracks current, next, and later priorities for headless Mission Control.",
    "Current",
    [
        (
            "Now",
            """
            Current priorities:

            - headless install and autowire
            - MCP bridge
            - skills
            - pending decisions
            - chat-native handoff
            - existing codebase mode
            - health doctor
            """,
        ),
        (
            "Next",
            """
            Next priorities:

            - real worker orchestration hardening
            - better runner registry
            - deeper codebase indexing
            - conflict resolver
            - evidence handoff improvements
            - release packaging
            """,
        ),
        (
            "Later",
            """
            Later priorities:

            - optional dashboard UI
            - richer visual observability
            - app-server experiments
            - marketplace-style plugin packaging
            """,
        ),
        (
            "Related pages",
            f"""
            See {md_link('Headless-First-Direction.md')}, {md_link('Mission-Control-Daemon.md')}, and {md_link('Known-Limitations-and-Non-Goals.md')}.
            """,
        ),
    ],
)

add(
    "Glossary.md",
    "Glossary",
    "This page defines the core Mission Control vocabulary used throughout the wiki and repo docs.",
    "Current",
    [
        (
            "Core terms",
            """
            - Mission Control: the local orchestration platform
            - Manager AI: the orchestration authority inside Mission Control
            - Codex chat bridge: the user-facing relay surface
            - worker agent: background execution unit under Manager control
            - daemon: the long-running local backend
            - MCP: Model Context Protocol surface used to expose tools, resources, and prompts
            - tool: action surface
            - resource: read-only summary surface
            - prompt: reusable workflow instruction
            - skill: Codex instruction bundle
            - runner: execution backend such as Codex CLI or Ollama
            - pending decision: approval or question record
            - bridge message: chat-safe message format
            - handoff: final or partial outcome summary
            - dry-run: safe simulation mode without claiming real execution
            - headless mode: operation without relying on the standalone dashboard
            - imported codebase mode: safe attach flow for an existing repo
            - swarm plan: Manager-defined worker strategy
            - agent contract: worker boundary definition
            - path lock: file ownership barrier between tasks
            - evidence: validation output backing a claim
            """,
        ),
        (
            "Related pages",
            f"""
            For deeper context read {md_link('Manager-AI-vs-Codex-Chat.md')}, {md_link('MCP-Plugin-Architecture.md')}, and {md_link('Adaptive-Agent-Swarms.md')}.
            """,
        ),
    ],
)


def add_reference_page(filename: str, title: str, summary: str, bullets: list[str], related: list[str], status: str = "Current") -> None:
    sections = [
        (
            "Reference",
            "\n".join(f"- {item}" for item in bullets),
        ),
        (
            "Example",
            """
            Use this page when a user or contributor needs a compact reference instead of a full architecture walkthrough.
            """,
        ),
        (
            "Related pages",
            "\n".join(f"- {md_link(page)}" for page in related),
        ),
    ]
    add(filename, title, summary, status, sections)


add_reference_page(
    "Approval-Card-Fallback-Text.md",
    "Approval Card Fallback Text",
    "This page documents the plain-markdown fallback format for approvals when rich card rendering is unavailable.",
    [
        "show decision type",
        "show reason",
        "show risk level",
        "show options",
        "show recommended option only when backed by Mission Control",
        "avoid raw command dumps when secrets may appear",
    ],
    ["Pending-Decisions-and-Approvals.md", "Manager-Questions.md", "Codex-Chat-Workflow.md"],
)

add_reference_page(
    "MCP-Resources-Catalog.md",
    "MCP Resources Catalog",
    "This page summarizes the read-only MCP resources exposed or expected for Mission Control bridge mode.",
    [
        "`mission-control://orchestrations/{orchestration_id}/status`",
        "`mission-control://orchestrations/{orchestration_id}/events`",
        "`mission-control://projects/{project_id}/status`",
        "`mission-control://projects/{project_id}/agents`",
        "`mission-control://projects/{project_id}/pending-decisions`",
        "`mission-control://projects/{project_id}/handoff`",
        "`mission-control://projects/{project_id}/codebase-map`",
        "`mission-control://projects/{project_id}/workspace-tooling`",
        "`mission-control://projects/{project_id}/diagnostics`",
        "`mission-control://projects/{project_id}/webwright`",
        "`mission-control://projects/{project_id}/nvidia-dynamo`",
        "`mission-control://projects/{project_id}/nvidia-aiq`",
        "`mission-control://projects/{project_id}/nvidia-gpu-diagnostics`",
        "`mission-control://projects/{project_id}/swarm-plan`",
        "`mission-control://projects/{project_id}/risk-register`",
        "`mission-control://projects/{project_id}/agent-contracts`",
        "`mission-control://projects/{project_id}/validation-summary`",
        "`mission-control://projects/{project_id}/decision-ledger`",
        "`mission-control://projects/{project_id}/path-locks`",
        "`mission-control://projects/{project_id}/operator-snapshot`",
        "`mission-control://projects/{project_id}/instincts`",
        "`mission-control://projects/{project_id}/verification-brief`",
    ],
    ["MCP-Plugin-Architecture.md", "MCP-Prompts-Catalog.md", "Mission-Control-Daemon.md"],
)

add_reference_page(
    "MCP-Prompts-Catalog.md",
    "MCP Prompts Catalog",
    "This page summarizes the prompt workflows packaged for Mission Control bridge mode.",
    [
        "attach current workspace",
        "use Mission Control for this repo",
        "import existing codebase",
        "start manager-led task",
        "continue orchestration",
        "show pending approvals",
        "answer pending approval",
        "review latest handoff",
        "debug failed orchestration",
        "use Webwright for browser task",
        "enable safe mode",
    ],
    ["MCP-Plugin-Architecture.md", "Skills-and-Prompts.md", "Quick-Start.md"],
)

add_reference_page(
    "Plugin-Health-Doctor.md",
    "Plugin Health Doctor",
    "This page summarizes the Mission Control plugin health doctor surface and what it should report.",
    [
        "daemon reachable",
        "MCP bridge reachable",
        "MCP catalogs loaded",
        "skill files present",
        "runner registry readable",
        "runtime folder writable",
        "dashboard optional state only",
    ],
    ["Diagnostics-and-Health-Checks.md", "Health-Doctor-Example-Output.md", "Debugging-Common-Issues.md"],
)

add_reference_page(
    "Runtime-Configuration-Reference.md",
    "Runtime Configuration Reference",
    "This page is a compact reference for the runtime pieces Mission Control expects locally.",
    [
        "localhost daemon binding",
        "runtime directory",
        "SQLite database",
        "plugin bundle files",
        "skill directories",
        "runner configuration",
        "diagnostics path",
    ],
    ["Mission-Control-Daemon.md", "Logs-and-Runtime-Folders.md", "Provider-Autowiring.md"],
)

add_reference_page(
    "Bridge-Message-Format.md",
    "Bridge Message Format",
    "This page documents what good bridge-safe markdown should look like for status, approvals, diagnostics, and handoffs.",
    [
        "compact title",
        "explicit current state",
        "explicit blocker or next step",
        "redacted secrets",
        "no raw giant logs",
        "clear user action when needed",
    ],
    ["Codex-Chat-Workflow.md", "Approval-Card-Fallback-Text.md", "Handoffs-and-Evidence.md"],
)

add_reference_page(
    "Codebase-Map-and-Understanding.md",
    "Codebase Map and Understanding",
    "This page explains the output Mission Control should return after scanning an existing repository in read-only mode.",
    [
        "detected languages and frameworks",
        "entry points",
        "important folders",
        "build commands",
        "test commands",
        "risk flags",
        "understanding summary",
    ],
    ["Existing-Codebase-Mode.md", "AGENTS-md-and-Agent-Instructions.md", "Workspace-Attach-and-Project-Lifecycle.md"],
)

add_reference_page(
    "Validation-Summary-Reference.md",
    "Validation Summary Reference",
    "This page is the compact reference for how Mission Control should summarize validation state and gaps.",
    [
        "tests run",
        "tests not run",
        "build status",
        "lint/typecheck status",
        "manual verification notes",
        "known evidence gaps",
    ],
    ["Testing-and-Smoke-Checks.md", "Handoffs-and-Evidence.md", "Evidence-Review-Checklist.md"],
)

add_reference_page(
    "Swarm-Modes-Reference.md",
    "Swarm Modes Reference",
    "This page is the short reference for Manager swarm modes and the tradeoffs each mode implies.",
    [
        "fastest_build: speed first",
        "balanced: moderate coordination and quality",
        "high_quality: stronger review and validation",
        "documentation_heavy: docs-first output",
        "research_planning: analysis-first path",
        "massive_codebase: progressive understanding and bounded scope",
        "safe_mode: tight approvals and reduced aggressiveness",
    ],
    ["Adaptive-Agent-Swarms.md", "Agent-Archetypes.md", "Safe-Mode.md"],
)

add_reference_page(
    "Agent-Archetypes.md",
    "Agent Archetypes",
    "This page summarizes the kinds of worker roles Mission Control may assign inside a swarm plan.",
    [
        "implementation worker",
        "validation worker",
        "docs writer",
        "security reviewer",
        "research or planning helper",
        "release or handoff helper",
    ],
    ["Adaptive-Agent-Swarms.md", "Path-Locks-and-Ownership.md", "Contributor-Rules-for-AI-Agents.md"],
)

add_reference_page(
    "Path-Locks-and-Ownership.md",
    "Path Locks and Ownership",
    "This page explains why Mission Control tracks path ownership and how that should be surfaced in chat.",
    [
        "locked path",
        "owning agent",
        "waiting task",
        "conflict risk",
        "suggested resolution",
    ],
    ["Adaptive-Agent-Swarms.md", "Path-Locks-and-Ownership.md", "Recovery-Planning.md"],
)

add_reference_page(
    "Recovery-Planning.md",
    "Recovery Planning",
    "This page summarizes how Mission Control should explain failure causes and recovery options before taking action.",
    [
        "failure summary",
        "likely causes",
        "retry options",
        "reassign or split options",
        "pause or stop options",
        "user approval points",
    ],
    ["Debugging-Common-Issues.md", "Pending-Decisions-and-Approvals.md", "Handoffs-and-Evidence.md"],
)

add_reference_page(
    "Safe-Mode.md",
    "Safe Mode",
    "This page explains the strict safety posture that can be applied to a Mission Control project.",
    [
        "require all command approvals",
        "block destructive actions",
        "disable deployments by default",
        "disable external account tools unless approved",
        "prefer read-only import behavior",
        "pause dynamic spawning when supported",
    ],
    ["Safety-and-Security-Model.md", "Pending-Decisions-and-Approvals.md", "Adaptive-Agent-Swarms.md"],
)

add_reference_page(
    "Dry-Run-Mode.md",
    "Dry Run Mode",
    "This page explains dry-run mode as a safe fallback that must never be confused with real execution evidence.",
    [
        "useful for docs and bridge testing",
        "safe fallback when no live runner is ready",
        "must be labeled clearly in status and handoff",
        "not proof that commands really ran",
    ],
    ["Runner-Configuration.md", "Handoffs-and-Evidence.md", "Troubleshooting-CLI-Runners.md"],
)

add_reference_page(
    "Localhost-Binding-and-Ports.md",
    "Localhost Binding and Ports",
    "This page explains the daemon binding model and the common port-related failures to check first.",
    [
        "bind to 127.0.0.1 by default",
        "treat public exposure as out of scope",
        "verify health endpoint on localhost",
        "check for port conflicts before retry loops",
    ],
    ["Mission-Control-Daemon.md", "Diagnostics-and-Health-Checks.md", "Debugging-Common-Issues.md"],
)

add_reference_page(
    "Install-Reports-and-Repair-Mode.md",
    "Install Reports and Repair Mode",
    "This page summarizes what a headless install report or repair report should contain.",
    [
        "repo location",
        "daemon state",
        "plugin files present",
        "skill files present",
        "runner detection summary",
        "missing actions or repairs applied",
    ],
    ["Install-From-Codex.md", "Headless-Install-and-Autowire.md", "Diagnostics-and-Health-Checks.md"],
    "Planned / Partial",
)

add_reference_page(
    "Evidence-Review-Checklist.md",
    "Evidence Review Checklist",
    "This page gives reviewers a short checklist for deciding whether a Mission Control handoff is evidence-backed enough.",
    [
        "claims match actual validation output",
        "dry-run clearly labeled",
        "limitations present",
        "missing tests called out",
        "important files listed",
        "next tasks realistic",
    ],
    ["Handoffs-and-Evidence.md", "Validation-Summary-Reference.md", "Testing-and-Smoke-Checks.md"],
)

add_reference_page(
    "Contributor-Rules-for-AI-Agents.md",
    "Contributor Rules for AI Agents",
    "This page restates the AI-agent contribution rules for the project in a wiki-friendly form.",
    [
        "treat Codex chat as the bridge, not the Manager",
        "avoid standalone UI work unless explicitly asked",
        "prefer daemon, MCP, skills, diagnostics, security, and docs work",
        "do not fake execution or approvals",
        "do not expose secrets",
        "report validation honestly",
    ],
    ["Development-Guide.md", "Skills-and-Prompts.md", "Manager-AI-vs-Codex-Chat.md"],
)

add_reference_page(
    "Docs-Source-Map.md",
    "Docs Source Map",
    "This page lists the main repo docs that feed the wiki so contributors know where to refresh source material.",
    [
        "README.md",
        "CURRENT_DIRECTION.md",
        "AGENTS.md",
        "docs/HEADLESS_ARCHITECTURE.md",
        "docs/CODEX_PLUGIN_INSTALL.md",
        "docs/CODEX_PLUGIN_MODE.md",
        "docs/MCP_TOOLS.md",
        "docs/MCP_RESOURCES.md",
        "docs/MCP_PROMPTS.md",
        "docs/PENDING_DECISIONS.md",
        "docs/PLUGIN_HEALTH_DOCTOR.md",
        "docs/SECURITY_MODEL.md",
        "docs/WEBWRIGHT.md",
        "plugins/mission-control/*",
    ],
    ["Development-Guide.md", "Home.md", "Mission-Control-Daemon.md"],
)

add_reference_page(
    "MCP-Bridge-Endpoints.md",
    "MCP Bridge Endpoints",
    "This page lists the main backend endpoints that support bridge mode and what each one is for.",
    [
        "`/api/health`",
        "`/api/orchestrations/attach-workspace`",
        "`/api/orchestrations`",
        "`/api/orchestrations/{id}/status`",
        "`/api/orchestrations/{id}/pending-decisions`",
        "`/api/decisions/{id}/answer`",
        "`/api/orchestrations/{id}/handoff`",
        "`/api/plugin/health`",
        "`/api/projects/{project_id}/webwright`",
        "`/api/projects/{project_id}/operator-snapshot`",
        "`/api/projects/{project_id}/instincts/preview`",
        "`/api/projects/{project_id}/verification-brief`",
    ],
    ["MCP-Plugin-Architecture.md", "Mission-Control-Daemon.md", "Diagnostics-and-Health-Checks.md"],
)

add_reference_page(
    "Workspace-Attach-and-Project-Lifecycle.md",
    "Workspace Attach and Project Lifecycle",
    "This page explains how a folder becomes a Mission Control project and how that project moves through import, planning, execution, and handoff.",
    [
        "attach workspace",
        "classify empty vs existing folder",
        "scan or import",
        "plan and execution",
        "pending decisions",
        "handoff",
        "follow-up change requests",
    ],
    ["Existing-Codebase-Mode.md", "Quick-Start.md", "Handoffs-and-Evidence.md"],
)

add_reference_page(
    "Manager-Questions.md",
    "Manager Questions",
    "This page documents how Manager-generated questions should be relayed to the user through Codex chat.",
    [
        "question should include why it matters",
        "question should include category or impact",
        "options should be explicit when possible",
        "Codex chat should not answer automatically",
    ],
    ["Pending-Decisions-and-Approvals.md", "Codex-Chat-Workflow.md", "Manager-AI-vs-Codex-Chat.md"],
)

add_reference_page(
    "Health-Doctor-Example-Output.md",
    "Health Doctor Example Output",
    "This page shows the shape of a useful plugin health summary without copying raw internal logs.",
    [
        "overall status",
        "per-check status",
        "recommended fixes",
        "safe copyable commands",
        "redacted notes",
    ],
    ["Plugin-Health-Doctor.md", "Diagnostics-and-Health-Checks.md", "Debugging-Common-Issues.md"],
)

add_reference_page(
    "Known-Limitations-and-Non-Goals.md",
    "Known Limitations and Non Goals",
    "This page captures the current edges of the product so the wiki does not oversell unfinished systems.",
    [
        "standalone dashboard is optional, not primary",
        "some install/autowire surfaces remain planned or partial",
        "runner support depth varies by local environment",
        "worker orchestration hardening is still in progress",
        "plugin packaging may evolve",
    ],
    ["Roadmap.md", "Headless-First-Direction.md", "Troubleshooting-CLI-Runners.md"],
)

add(
    "Webwright-and-Browser-Automation.md",
    "Webwright and Browser Automation",
    "This page explains how Mission Control integrates the upstream Webwright runtime as an optional browser-agent companion instead of pretending browser automation is a normal model runner.",
    "Current",
    [
        (
            "What this integration means",
            """
            Mission Control does not vendor the whole Webwright repository and it does not treat Webwright like a provider.

            Instead, Mission Control exposes:

            - a project-scoped readiness check
            - explicit setup guidance when the runtime is missing
            - browser-task routing guidance when the runtime is ready
            - bridge-safe summaries for Codex or Claude chat
            """,
        ),
        (
            "When to use it",
            """
            Prefer Webwright when the task needs:

            - real multi-step browser automation
            - screenshot-backed verification
            - rerunnable browser scripts instead of one-off chat claims

            Do not treat it as mandatory for ordinary app smoke checks or non-browser coding work.
            """,
        ),
        (
            "Mission Control surfaces",
            """
            Current surfaces:

            - REST: `/api/projects/{project_id}/webwright`
            - MCP resource: `mission-control://projects/{project_id}/webwright`
            - MCP tool: `mission_control_get_webwright_status`
            - MCP prompt: `use_webwright_for_browser_task`
            - Skill lane: `mission-control-webapp-testing`
            """,
        ),
        (
            "Upstream install path",
            """
            The upstream runtime setup is:

            ```bash
            git clone https://github.com/microsoft/Webwright
            cd Webwright
            python -m pip install -e .
            playwright install chromium
            ```

            Mission Control already provides the orchestration bridge. This install is only about getting the local Webwright runtime ready.
            """,
        ),
        (
            "Related pages",
            f"""
            Continue with {md_link('Runner-Configuration.md')}, {md_link('MCP-Resources-Catalog.md')}, {md_link('MCP-Prompts-Catalog.md')}, and {md_link('Debugging-Common-Issues.md')}.
            """,
        ),
    ],
)

# Sidebar and footer
PAGES["_Sidebar.md"] = dedent(
    f"""
    ## Start Here
    - {md_link('Home.md')}
    - {md_link('Quick-Start.md')}
    - {md_link('Headless-First-Direction.md')}
    - {md_link('Install-From-Codex.md')}

    ## Headless Usage
    - {md_link('Codex-Chat-Workflow.md')}
    - {md_link('Existing-Codebase-Mode.md')}
    - {md_link('Pending-Decisions-and-Approvals.md')}
    - {md_link('Handoffs-and-Evidence.md')}
    - {md_link('AGENTS-md-and-Agent-Instructions.md')}

    ## Architecture
    - {md_link('MCP-Plugin-Architecture.md')}
    - {md_link('Mission-Control-Daemon.md')}
    - {md_link('Manager-AI-vs-Codex-Chat.md')}
    - {md_link('Adaptive-Agent-Swarms.md')}
    - {md_link('MCP-Bridge-Endpoints.md')}

    ## Runners
    - {md_link('Runner-Configuration.md')}
    - {md_link('Provider-Autowiring.md')}
    - {md_link('Webwright-and-Browser-Automation.md')}
    - {md_link('Troubleshooting-CLI-Runners.md')}
    - {md_link('Dry-Run-Mode.md')}

    ## Safety
    - {md_link('Safety-and-Security-Model.md')}
    - {md_link('Safe-Mode.md')}
    - {md_link('Logs-and-Runtime-Folders.md')}
    - {md_link('Evidence-Review-Checklist.md')}

    ## Debugging
    - {md_link('Diagnostics-and-Health-Checks.md')}
    - {md_link('Debugging-Common-Issues.md')}
    - {md_link('Plugin-Health-Doctor.md')}
    - {md_link('Health-Doctor-Example-Output.md')}

    ## Development
    - {md_link('Development-Guide.md')}
    - {md_link('Testing-and-Smoke-Checks.md')}
    - {md_link('Contributor-Rules-for-AI-Agents.md')}
    - {md_link('Docs-Source-Map.md')}

    ## Roadmap
    - {md_link('Roadmap.md')}
    - {md_link('Known-Limitations-and-Non-Goals.md')}
    - {md_link('Glossary.md')}
    """
).strip() + "\n"

PAGES["_Footer.md"] = dedent(
    """
    ---
    Source repository: [MN755/Codex-Mission_Control](https://github.com/MN755/Codex-Mission_Control)

    Useful repo docs:

    - `README.md`
    - `CURRENT_DIRECTION.md`
    - `AGENTS.md`
    - `docs/`
    - `plugins/mission-control/`
    """
).strip() + "\n"


def validate_links() -> list[str]:
    existing = {name.replace(".md", "") for name in PAGES.keys()}
    broken: list[str] = []
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for name, content in PAGES.items():
        for target in pattern.findall(content):
            if target.startswith("http"):
                continue
            clean = target.split("#", 1)[0].strip()
            if not clean:
                continue
            if clean not in existing:
                broken.append(f"{name} -> {clean}")
    return broken


def main() -> None:
    WIKI_DIR.mkdir(exist_ok=True)
    for existing in WIKI_DIR.glob("*.md"):
        if existing.name not in {"PUSH-TO-GITHUB-WIKI.md"}:
            existing.unlink()
    for name, content in PAGES.items():
        (WIKI_DIR / name).write_text(content, encoding="utf-8")

    (WIKI_DIR / "PUSH-TO-GITHUB-WIKI.md").write_text(
        dedent(
            """
            # Push To GitHub Wiki

            This staging folder was generated locally because the live wiki repository could not be cloned from this environment.

            ## HTTPS flow

            ```bash
            git clone https://github.com/MN755/Codex-Mission_Control.wiki.git
            cd Codex-Mission_Control.wiki
            cp /path/to/wiki-staging/*.md .
            git status
            git add .
            git commit -m "Add Mission Control headless documentation wiki"
            git push origin master
            ```

            ## SSH flow

            ```bash
            git clone git@github.com:MN755/Codex-Mission_Control.wiki.git
            cd Codex-Mission_Control.wiki
            cp /path/to/wiki-staging/*.md .
            git status
            git add .
            git commit -m "Add Mission Control headless documentation wiki"
            git push origin master
            ```

            ## Windows PowerShell copy example

            ```powershell
            git clone https://github.com/MN755/Codex-Mission_Control.wiki.git
            Set-Location .\\Codex-Mission_Control.wiki
            Copy-Item ..\\wiki-staging\\*.md .
            git status
            git add .
            git commit -m "Add Mission Control headless documentation wiki"
            git push origin master
            ```
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    broken = validate_links()
    if broken:
        raise SystemExit("Broken internal links:\n" + "\n".join(broken))

    content_pages = [name for name in PAGES if name not in {"_Sidebar.md", "_Footer.md"}]
    print(f"Generated {len(content_pages)} content wiki pages plus sidebar/footer in {WIKI_DIR}")


if __name__ == "__main__":
    main()
