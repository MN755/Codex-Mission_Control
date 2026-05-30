import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { CommandIcon } from "../components/CommandIcon";
import { HomeShell } from "../components/HomeShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import { WidgetGrid } from "../components/WidgetGrid";
import { WidgetSelectorPanel } from "../components/WidgetSelectorPanel";
import { useProjectStream } from "../state/useProjectStream";
import type {
  ActivityLogEntry,
  ApprovalRequest,
  ApprovalPolicy,
  AppProfile,
  Agent,
  AgentDisplayStatus,
  CodexStatus,
  DashboardSummary,
  ManagerMessage,
  ManagerQueueItem,
  ManagerQuestion,
  ProjectActionType,
  ProjectOverview,
  ProjectSettings,
  ProjectWorkflow,
  ProjectWorkspace,
  ReasoningEffort,
  RunnerMode,
  SandboxMode,
  SwarmPlan,
  SwarmPreferences,
  Task,
  WidgetDataResponse,
  WidgetDefinition,
  WidgetInstance,
  WidgetSize,
} from "../types";

function projectPath(projectId: number, slug?: string | null): string {
  return slug ? `/projects/${projectId}/${slug}` : `/projects/${projectId}`;
}

function modelsPath(projectId: number, slug?: string | null): string {
  return slug ? `/projects/${projectId}/${slug}/models-runners` : `/projects/${projectId}/models-runners`;
}

function titleCase(value: string | null | undefined): string {
  return String(value ?? "")
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

function firstLine(value: string | null | undefined): string {
  const line = String(value ?? "").split(/\r?\n/).find((entry) => entry.trim());
  return line?.trim() ?? "";
}

function formatAutoDecide(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const deltaMs = new Date(value).getTime() - Date.now();
  const totalSeconds = Math.max(0, Math.floor(deltaMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function formatShortTime(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function formatDayLabel(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) {
    return "Today";
  }
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function actionClass(severity: string): string {
  return `workspace-action workspace-action--${severity}`;
}

function actionLabel(type: ProjectActionType): string {
  switch (type) {
    case "manager_question":
      return "Manager Question";
    case "command_approval":
      return "Command Approval";
    case "tool_approval":
      return "Tool Approval";
    case "blocker":
      return "Blocker";
    case "handoff_ready":
      return "Ready for Handoff";
    case "degraded":
      return "Runner Degraded";
    case "paused":
      return "Project Paused";
    case "error":
      return "Workspace Error";
    default:
      return "No Action Needed";
  }
}

function approvalTypeLabel(approval: ApprovalRequest): string {
  switch (approval.request_type) {
    case "command":
      return "Command Approval";
    case "tool":
      return "Tool Approval";
    case "plugin":
      return "Plugin Approval";
    case "connected_app":
      return "Connected Account Approval";
    default:
      return "Approval Request";
  }
}

function riskClass(risk: string): string {
  return `status-pill status-${risk}`;
}

function boardColumnId(task: Task): "backlog" | "in_progress" | "review" | "done" {
  if (task.status === "done") {
    return "done";
  }
  if (task.status === "needs_review") {
    return "review";
  }
  if (task.status === "working" || task.status === "waiting_on_paths" || task.status === "blocked") {
    return "in_progress";
  }
  return "backlog";
}

function priorityLabel(priority: number): string {
  if (priority <= 20) {
    return "P1";
  }
  if (priority <= 40) {
    return "P2";
  }
  return "P3";
}

function overviewStatusLabel(value: ProjectOverview["checklist"][number]["status"]): string {
  switch (value) {
    case "complete":
      return "Complete";
    case "blocked":
      return "Blocked";
    case "in_progress":
      return "In Progress";
    default:
      return "Planned";
  }
}

function overviewStatusClass(value: ProjectOverview["checklist"][number]["status"]): string {
  switch (value) {
    case "complete":
      return "status-done";
    case "blocked":
      return "status-blocked";
    case "in_progress":
      return "status-working";
    default:
      return "status-idle";
  }
}

function messageTypeLabel(message: ManagerMessage): string {
  return titleCase(message.message_type);
}

function messageToneClass(message: ManagerMessage): string {
  if (message.role === "user") {
    return "workspace-message--user";
  }
  switch (message.message_type) {
    case "milestone_report":
      return "workspace-message--milestone";
    case "handoff_report":
      return "workspace-message--handoff";
    case "blocker_report":
      return "workspace-message--blocker";
    case "manager_question":
      return "workspace-message--question";
    case "command_approval":
    case "tool_approval":
      return "workspace-message--approval";
    case "system_notice":
      return "workspace-message--system";
    default:
      return message.role === "manager" ? "workspace-message--manager" : "workspace-message--agent";
  }
}

function messageModeLabel(message: ManagerMessage): string | null {
  const metadata = message.metadata_json && typeof message.metadata_json === "object" ? message.metadata_json : null;
  if (!metadata) {
    return null;
  }
  if ("simulated" in metadata && metadata.simulated === true) {
    return "Simulated dry-run";
  }
  const responseMode = "response_mode" in metadata && typeof metadata.response_mode === "string" ? metadata.response_mode : null;
  if (responseMode === "deterministic") {
    return "Deterministic response";
  }
  if (responseMode === "provider_backed") {
    return "Provider-backed";
  }
  if (responseMode === "dry_run") {
    return "Dry-run response";
  }
  return null;
}

function roleLabel(message: ManagerMessage): string {
  if (message.role === "user") {
    return "You";
  }
  if (message.role === "manager") {
    return "Manager Agent";
  }
  if (message.role === "agent") {
    return "Worker Agent";
  }
  return "System";
}

function activityClass(entry: ActivityLogEntry): string {
  return `status-pill status-${entry.severity}`;
}

function projectInitials(name: string | null | undefined): string {
  const parts = String(name ?? "Project")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("") || "PR";
}

function readinessToneClass(overview: ProjectOverview): string {
  if (overview.readiness_tone === "good") {
    return "status-done";
  }
  if (overview.readiness_tone === "danger") {
    return "status-blocked";
  }
  if (overview.readiness_tone === "warning") {
    return "status-needs_review";
  }
  return "status-idle";
}

function agentActivityClass(status: AgentDisplayStatus | string | null | undefined): string {
  return `workspace-agent-card__activity workspace-agent-card__activity--${status ?? "idle"}`;
}

function queueStatusClass(status: string): string {
  if (status === "blocked" || status === "error") {
    return "status-blocked";
  }
  if (status === "waiting_on_user" || status === "pending") {
    return "status-needs_review";
  }
  if (status === "done" || status === "resolved") {
    return "status-done";
  }
  return "status-working";
}

function messageAvatarLabel(message: ManagerMessage, userDisplayName: string): string {
  if (message.role === "user") {
    return projectInitials(userDisplayName);
  }
  if (message.role === "manager") {
    return "MC";
  }
  return "AG";
}

function taskColumnHint(title: string): string {
  switch (title) {
    case "Backlog":
      return "Manager-routed next work";
    case "In Progress":
      return "Actively assigned now";
    case "Review":
      return "Waiting for validation";
    case "Done":
      return "Finished and logged";
    default:
      return "";
  }
}

function buildShareSummary(workspace: ProjectWorkspace, currentAction: ProjectWorkspace["current_action"]): string {
  const route = projectPath(workspace.project.id, workspace.project.slug);
  const latestLine = firstLine(workspace.project.latest_activity) || firstLine(workspace.project.idea) || "No project summary recorded yet.";
  const handoff = workspace.project.final_report_json;
  const handoffSummary =
    handoff && typeof handoff.summary_markdown === "string"
      ? String(handoff.summary_markdown).trim()
      : null;

  return [
    `# ${workspace.project.name}`,
    `Route: ${route}`,
    `Phase: ${workspace.workflow.current_label}`,
    `Status: ${titleCase(workspace.project.display_status)}`,
    `Action: ${currentAction.title}`,
    `Readiness: ${workspace.overview.readiness_label}`,
    `Workspace path: ${workspace.project.workspace_path}`,
    "",
    latestLine,
    handoffSummary ? `\nHandoff summary:\n${handoffSummary}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function buildQueueSnapshot(workspace: ProjectWorkspace): string {
  const sections = [
    ["Next Up", workspace.manager_queue.next_up],
    ["Waiting on User", workspace.manager_queue.waiting_on_user],
    ["Recently Decided", workspace.manager_queue.recently_decided],
    ["Deferred", workspace.manager_queue.deferred],
  ] as const;

  return sections
    .map(([title, items]) => {
      const lines = items.length
        ? items.map((item) => `- ${item.title} (${titleCase(item.type)} / ${titleCase(item.status)})`)
        : ["- Nothing queued here right now."];
      return [`## ${title}`, ...lines].join("\n");
    })
    .join("\n\n");
}

function buildChecklistSummary(workspace: ProjectWorkspace): string {
  return workspace.overview.checklist
    .map((item) => `- ${item.label}: ${overviewStatusLabel(item.status)}${item.detail ? ` (${item.detail})` : ""}`)
    .join("\n");
}

const RUNNER_MODE_OPTIONS: Array<{ value: RunnerMode; label: string }> = [
  { value: "auto", label: "Auto" },
  { value: "cli", label: "CLI" },
  { value: "app_server", label: "App Server" },
  { value: "dry_run", label: "Dry Run" },
];

const SANDBOX_MODE_OPTIONS: Array<{ value: SandboxMode; label: string }> = [
  { value: "workspace-write", label: "Workspace Write" },
  { value: "read-only", label: "Read Only" },
];

const APPROVAL_POLICY_OPTIONS: Array<{ value: ApprovalPolicy; label: string }> = [
  { value: "on-request", label: "On Request" },
  { value: "untrusted", label: "Untrusted" },
  { value: "never", label: "Never" },
];

const REASONING_OPTIONS: Array<{ value: ReasoningEffort | ""; label: string }> = [
  { value: "", label: "Use provider default" },
  { value: "minimal", label: "Minimal" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

const SWARM_MODE_OPTIONS: Array<{ value: SwarmPreferences["optimization_mode"]; label: string }> = [
  { value: "fastest_build", label: "Fastest Build" },
  { value: "balanced", label: "Balanced" },
  { value: "high_quality", label: "High Quality" },
  { value: "documentation_heavy", label: "Documentation Heavy" },
  { value: "research_planning", label: "Research & Planning" },
  { value: "massive_codebase", label: "Massive Codebase" },
  { value: "manager_decides", label: "Manager Decides" },
];

const SWARM_AGGRESSIVENESS_OPTIONS: Array<{ value: SwarmPreferences["swarm_aggressiveness"]; label: string }> = [
  { value: "small", label: "Small" },
  { value: "medium", label: "Medium" },
  { value: "large", label: "Large" },
  { value: "maximum", label: "Maximum" },
  { value: "manager_decides", label: "Manager Decides" },
];

const DOCS_DEPTH_OPTIONS: Array<{ value: SwarmPreferences["docs_depth"]; label: string }> = [
  { value: "minimal", label: "Minimal" },
  { value: "standard", label: "Standard" },
  { value: "detailed", label: "Detailed" },
  { value: "publishable", label: "Publishable" },
];

const TESTING_DEPTH_OPTIONS: Array<{ value: SwarmPreferences["testing_depth"]; label: string }> = [
  { value: "minimal", label: "Minimal" },
  { value: "standard", label: "Standard" },
  { value: "extensive", label: "Extensive" },
  { value: "release_grade", label: "Release Grade" },
];

function summarizePaths(paths: string[] | null | undefined): string {
  const items = (paths ?? []).filter(Boolean);
  if (!items.length) {
    return "None assigned";
  }
  return items.slice(0, 3).join(", ");
}

const DEFAULT_PROJECT_WIDGET_TYPES = [
  "Swarm Strategy",
  "Swarm Budget",
  "Agent Contracts",
  "Path Ownership Map",
  "Decision Ledger",
  "Project Health Score",
  "Validation Recipe",
  "Manager Assumptions",
  "Handoff Quality",
] as const;

function confidenceFromChecklistStatus(status: ProjectOverview["checklist"][number]["status"]): number {
  switch (status) {
    case "complete":
      return 90;
    case "in_progress":
      return 55;
    case "blocked":
      return 15;
    default:
      return 30;
  }
}

function readinessStateFromOverview(overview: ProjectOverview): string {
  if (overview.readiness_tone === "good") {
    return "ready_for_handoff";
  }
  if (overview.readiness_tone === "danger") {
    return "blocked";
  }
  if (overview.readiness_tone === "warning") {
    return "needs_review";
  }
  return "unknown";
}

function legacyProjectWidgetCatalog(workspace: ProjectWorkspace | null): WidgetDefinition[] {
  const types = new Set<string>(DEFAULT_PROJECT_WIDGET_TYPES);
  for (const widgetType of Array.isArray(workspace?.available_widgets) ? workspace?.available_widgets : []) {
    if (typeof widgetType === "string" && widgetType.trim()) {
      types.add(widgetType);
    }
  }
  for (const widgetType of Array.isArray(workspace?.widgets) ? workspace?.widgets : []) {
    if (typeof widgetType === "string" && widgetType.trim()) {
      types.add(widgetType);
    }
  }

  return [...types].map((widgetType, index) => ({
    id: -(index + 1),
    widget_type: widgetType,
    title: widgetType,
    description: `Legacy compatibility widget for ${widgetType}.`,
    scope: "project",
    default_area: "project_right_sidebar",
    default_size: widgetType === "Path Ownership Map" || widgetType === "Decision Ledger" ? "large" : "medium",
    category: "Swarm",
    requires_project: true,
    requires_tool: null,
    coming_soon: widgetType === "Live Project Map",
    risk_level: null,
  }));
}

function legacyProjectWidgetInstances(workspace: ProjectWorkspace | null): WidgetInstance[] {
  if (!workspace) {
    return [];
  }
  const legacyWidgets = Array.isArray(workspace.widgets) && workspace.widgets.length ? workspace.widgets : [...DEFAULT_PROJECT_WIDGET_TYPES];
  const types = legacyWidgets.filter((widgetType, index, items) => items.indexOf(widgetType) === index);
  const now = new Date().toISOString();

  return types.map((widgetType, index) => ({
    id: -(index + 1),
    scope: "project",
    project_id: workspace.project.id,
    widget_type: widgetType,
    area: "project_right_sidebar",
    order_index: index,
    size: widgetType === "Path Ownership Map" || widgetType === "Decision Ledger" ? "large" : "medium",
    collapsed: false,
    enabled: true,
    config_json: { legacy: true },
    created_at: now,
    updated_at: now,
  }));
}

function legacyProjectWidgetData(workspace: ProjectWorkspace, instances: WidgetInstance[]): WidgetDataResponse[] {
  const now = new Date().toISOString();
  const activeAgentCount = workspace.agents.filter((agent) => agent.status !== "done" && agent.status !== "stopped").length;
  const maxAgentCount = workspace.swarm_plan?.max_agent_count ?? workspace.swarm_preferences.max_agents;
  const intensity =
    activeAgentCount >= Math.max(10, Math.ceil(maxAgentCount * 0.8))
      ? "extreme"
      : activeAgentCount >= Math.max(6, Math.ceil(maxAgentCount * 0.6))
        ? "high"
        : activeAgentCount >= Math.max(3, Math.ceil(maxAgentCount * 0.35))
          ? "medium"
          : "low";

  return instances.map((instance) => {
    switch (instance.widget_type) {
      case "Swarm Strategy":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.swarm_plan?.approval_required && !workspace.swarm_plan.approved_by_user ? "warning" : workspace.swarm_plan ? "ready" : "empty",
          data_json: {
            strategy_summary: workspace.swarm_plan?.strategy_summary ?? null,
            usage_warning: workspace.swarm_plan?.usage_warning ?? null,
            mode: workspace.swarm_plan?.mode ?? workspace.swarm_preferences.optimization_mode,
          },
          empty_state: "No swarm strategy exists yet.",
          warnings_json: workspace.swarm_plan?.usage_warning ? [workspace.swarm_plan.usage_warning] : [],
          updated_at: now,
        };
      case "Swarm Budget":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: intensity === "high" || intensity === "extreme" ? "warning" : "ready",
          data_json: {
            active_agents: activeAgentCount,
            max_agents: maxAgentCount,
            intensity,
            dynamic_spawning_paused: !workspace.swarm_preferences.allow_dynamic_spawning,
            approval_threshold: workspace.swarm_preferences.require_approval_above_agent_count,
          },
          empty_state: null,
          warnings_json: workspace.swarm_plan?.usage_warning ? [workspace.swarm_plan.usage_warning] : [],
          updated_at: now,
        };
      case "Agent Contracts":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.agents.length ? "ready" : "empty",
          data_json: {
            items: workspace.agents.map((agent) => ({
              id: agent.id,
              title: agent.name,
              detail: agent.mission ? `Mission: ${agent.mission}` : agent.current_action ?? agent.role,
              status: titleCase(agent.display_status ?? agent.status),
            })),
          },
          empty_state: "No agent contracts are active yet.",
          warnings_json: [],
          updated_at: now,
        };
      case "Path Ownership Map":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.reservations.length ? "ready" : "empty",
          data_json: {
            items: workspace.reservations.map((reservation) => ({
              id: reservation.id,
              title: reservation.path,
              detail: reservation.released_at ? "Released" : `Reserved by agent ${reservation.agent_id}`,
              status: reservation.released_at ? "released" : "active",
            })),
          },
          empty_state: "No path ownership is recorded yet.",
          warnings_json: [],
          updated_at: now,
        };
      case "Decision Ledger":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.manager_queue.recently_decided.length ? "ready" : "empty",
          data_json: {
            items: workspace.manager_queue.recently_decided.map((item) => ({
              id: item.id,
              title: item.title,
              detail: `${titleCase(item.type)} / ${titleCase(item.status)}`,
            })),
          },
          empty_state: "No recorded decisions are available yet.",
          warnings_json: [],
          updated_at: now,
        };
      case "Confidence Tracker":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.overview.checklist.length ? "ready" : "empty",
          data_json: {
            items: workspace.overview.checklist.map((item) => ({
              category: item.label,
              confidence_score: confidenceFromChecklistStatus(item.status),
              detail: item.detail,
            })),
          },
          empty_state: "No confidence scores have been recorded yet.",
          warnings_json: [],
          updated_at: now,
        };
      case "Failure Recovery":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.degraded_notices.length ? "warning" : "empty",
          data_json: {
            items: workspace.degraded_notices.map((item, index) => ({
              id: index,
              title: "Recovery suggestion",
              detail: item,
            })),
          },
          empty_state: "No recovery proposals are active.",
          warnings_json: [],
          updated_at: now,
        };
      case "Agent Stuck Detection":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.agents.some((agent) => agent.status === "blocked" || agent.display_status === "blocked") ? "warning" : "empty",
          data_json: {
            items: workspace.agents
              .filter((agent) => agent.status === "blocked" || agent.display_status === "blocked")
              .map((agent) => ({
                id: agent.id,
                title: agent.name,
                detail: agent.current_action ?? agent.last_report_summary ?? "No progress signal recorded.",
              })),
          },
          empty_state: "No agents currently look stuck.",
          warnings_json: [],
          updated_at: now,
        };
      case "Merge / Review Gates":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.overview.checklist.some((item) => item.status === "blocked") ? "warning" : "ready",
          data_json: {
            items: workspace.overview.checklist.map((item) => ({
              id: item.id,
              title: item.label,
              detail: item.detail,
              gate_type: item.status,
            })),
          },
          empty_state: "No review gates are defined yet.",
          warnings_json: [],
          updated_at: now,
        };
      case "Project Health Score":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.overview.readiness_tone === "danger" ? "warning" : "ready",
          data_json: {
            state: readinessStateFromOverview(workspace.overview),
            score: workspace.overview.handoff_progress,
            next_action: workspace.current_action.type === "manager_question" ? "Review pending manager question" : "Review current project action",
            reasons: workspace.overview.checklist.map((item) => `${item.label}: ${item.detail}`),
          },
          empty_state: null,
          warnings_json: [],
          updated_at: now,
        };
      case "Validation Recipe":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.overview.checklist.length ? "ready" : "empty",
          data_json: {
            steps: workspace.overview.checklist.map((item) => ({
              title: item.label,
              type: item.id === "documentation" ? "docs" : item.id === "testing" ? "test" : "manual",
              status: item.status,
            })),
          },
          empty_state: "No validation recipe has been defined yet.",
          warnings_json: [],
          updated_at: now,
        };
      case "Handoff Quality":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.overview.handoff_progress >= 75 ? "ready" : "warning",
          data_json: {
            quality_level: workspace.swarm_preferences.docs_depth === "publishable" ? "github_ready_release" : "developer_handoff",
            handoff_progress: workspace.overview.handoff_progress,
            readiness_label: workspace.overview.readiness_label,
            include_tests: true,
          },
          empty_state: null,
          warnings_json: [],
          updated_at: now,
        };
      case "Handoff Progress":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: "ready",
          data_json: {
            handoff_progress: workspace.overview.handoff_progress,
            readiness_label: workspace.overview.readiness_label,
            checklist: workspace.overview.checklist,
          },
          empty_state: null,
          warnings_json: [],
          updated_at: now,
        };
      case "What Changed Timeline":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.activity_log.length ? "ready" : "empty",
          data_json: {
            items: workspace.activity_log.map((entry) => ({
              id: entry.id,
              title: entry.summary,
              detail: entry.detail ?? formatShortTime(entry.created_at),
            })),
          },
          empty_state: "No timeline changes are recorded yet.",
          warnings_json: [],
          updated_at: now,
        };
      case "Agent Report Inbox":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.agents.length ? "ready" : "empty",
          data_json: {
            items: workspace.agents.map((agent) => ({
              id: agent.id,
              title: agent.name,
              detail: agent.last_report_summary ?? agent.current_action ?? "No report summary recorded.",
            })),
          },
          empty_state: "No agent reports are available yet.",
          warnings_json: [],
          updated_at: now,
        };
      case "Parallelism Safety Meter":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: workspace.swarm_plan?.path_conflict_risk === "high" ? "warning" : "ready",
          data_json: {
            score: Math.max(0, 100 - workspace.reservations.length * 10 - (workspace.swarm_plan?.coordination_risk === "high" ? 25 : workspace.swarm_plan?.coordination_risk === "medium" ? 10 : 0)),
            active_locks: workspace.reservations.filter((reservation) => !reservation.released_at).length,
            waiting_locks: 0,
            path_conflict_risk: workspace.swarm_plan?.path_conflict_risk ?? "low",
          },
          empty_state: null,
          warnings_json: [],
          updated_at: now,
        };
      case "Human Attention Queue": {
        const attentionItems = [
          {
            id: workspace.current_action.id,
            title: workspace.current_action.title,
            detail: workspace.current_action.message,
          },
          ...workspace.pending_approvals.map((approval) => ({
            id: approval.id,
            title: approval.title,
            detail: approval.reason_short,
          })),
        ];
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: attentionItems.length ? "warning" : "empty",
          data_json: { items: attentionItems },
          empty_state: "Nothing currently needs direct human attention.",
          warnings_json: [],
          updated_at: now,
        };
      }
      case "Live Project Map":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: "coming_soon",
          data_json: {},
          empty_state: "Live project mapping is still experimental. Better an honest placeholder than fake telemetry cosplay.",
          warnings_json: [],
          updated_at: now,
        };
      default:
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: "empty",
          data_json: { items: [] },
          empty_state: "No widget data is available yet.",
          warnings_json: [],
          updated_at: now,
        };
    }
  });
}

export function ProjectWorkspacePage() {
  const { projectId, projectSlug } = useParams();
  const navigate = useNavigate();
  const numericProjectId = Number(projectId);

  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [systemStatus, setSystemStatus] = useState<CodexStatus | null>(null);
  const [profile, setProfile] = useState<AppProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inlineNotice, setInlineNotice] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [widgetPickerOpen, setWidgetPickerOpen] = useState(false);
  const [showIdleAgents, setShowIdleAgents] = useState(false);
  const [showQueueDrawer, setShowQueueDrawer] = useState(false);
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [showAllActivity, setShowAllActivity] = useState(false);
  const [showAgentsDrawer, setShowAgentsDrawer] = useState(false);
  const [showChatSettings, setShowChatSettings] = useState(false);
  const [showSystemMessages, setShowSystemMessages] = useState(true);
  const [compactChat, setCompactChat] = useState(false);
  const [focusChat, setFocusChat] = useState(false);
  const [showSwarmPlanDrawer, setShowSwarmPlanDrawer] = useState(false);
  const [showProjectSettings, setShowProjectSettings] = useState(false);
  const [showSharePanel, setShowSharePanel] = useState(false);
  const [showChangeRequestDrawer, setShowChangeRequestDrawer] = useState(false);
  const [widgetDataState, setWidgetDataState] = useState<WidgetDataResponse[]>([]);
  const [projectNameDraft, setProjectNameDraft] = useState("");
  const [projectIdeaDraft, setProjectIdeaDraft] = useState("");
  const [changeRequestDraft, setChangeRequestDraft] = useState("");
  const [projectSettingsDraft, setProjectSettingsDraft] = useState<ProjectSettings | null>(null);
  const [swarmPreferencesDraft, setSwarmPreferencesDraft] = useState<SwarmPreferences | null>(null);
  const [projectSettingsLoadedFor, setProjectSettingsLoadedFor] = useState<number | null>(null);
  const [agentLog, setAgentLog] = useState<{ agentId: number; agentName: string; path: string | null; content: string } | null>(null);
  const [agentLogBusy, setAgentLogBusy] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const promptRegionRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const openedProjectRef = useRef<number | null>(null);

  const loadWorkspace = useCallback(async () => {
    if (!Number.isFinite(numericProjectId)) {
      setNotFound(true);
      setLoading(false);
      return;
    }

    try {
      if (openedProjectRef.current !== numericProjectId) {
        await api.openProject(numericProjectId);
        openedProjectRef.current = numericProjectId;
      }
      const [nextWorkspace, nextSummary, nextSystemStatus, nextProfile] = await Promise.all([
        api.getProjectWorkspace(numericProjectId),
        api.getDashboardSummary(),
        api.getSystemStatus(numericProjectId),
        api.getProfile(),
      ]);
      setWorkspace(nextWorkspace);
      setWidgetDataState(nextWorkspace.widget_data ?? []);
      setSummary(nextSummary);
      setSystemStatus(nextSystemStatus);
      setProfile(nextProfile);
      setNotFound(false);
      setError(null);
      const canonicalPath = projectPath(nextWorkspace.project.id, nextWorkspace.project.slug);
      const requestedPath = projectPath(nextWorkspace.project.id, projectSlug);
      if (canonicalPath !== requestedPath) {
        navigate(canonicalPath, { replace: true });
      }
    } catch (loadError) {
      const nextError = loadError instanceof Error ? loadError.message : "Failed to load project workspace.";
      if (nextError.includes("404") || nextError.toLowerCase().includes("project not found")) {
        setNotFound(true);
      } else {
        setError(nextError);
      }
    } finally {
      setLoading(false);
      setBusy(null);
    }
  }, [navigate, numericProjectId, projectSlug]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  useProjectStream(Number.isFinite(numericProjectId) ? numericProjectId : null, () => {
    void loadWorkspace();
  });

  useEffect(() => {
    if (!workspace) {
      return;
    }
    setProjectNameDraft(workspace.project.name);
    setProjectIdeaDraft(workspace.project.idea);
    setSwarmPreferencesDraft(workspace.swarm_preferences);
    if (projectSettingsLoadedFor !== workspace.project.id) {
      setProjectSettingsDraft(null);
      setProjectSettingsLoadedFor(null);
    }
    setAgentLog(null);
  }, [workspace?.project.id, workspace?.project.name, workspace?.project.idea, projectSettingsLoadedFor]);

  const agentsById = useMemo(() => {
    const entries = new Map<number, Agent>();
    for (const agent of workspace?.agents ?? []) {
      entries.set(agent.id, agent);
    }
    return entries;
  }, [workspace?.agents]);

  const projectSubtitle = useMemo(() => {
    const candidate = firstLine(workspace?.project.idea) || firstLine(workspace?.project.latest_activity);
    return candidate || "Manager-led workspace for building, reviewing, and handing off the project.";
  }, [workspace?.project.idea, workspace?.project.latest_activity]);

  const visibleMessages = useMemo(() => {
    const entries = workspace?.manager_messages ?? [];
    if (showSystemMessages) {
      return entries;
    }
    return entries.filter((entry) => entry.role !== "system");
  }, [showSystemMessages, workspace?.manager_messages]);

  const groupedMessages = useMemo(() => {
    const groups: Array<{ label: string; items: ManagerMessage[] }> = [];
    for (const messageEntry of visibleMessages) {
      const label = formatDayLabel(messageEntry.created_at);
      const previous = groups[groups.length - 1];
      if (!previous || previous.label !== label) {
        groups.push({ label, items: [messageEntry] });
      } else {
        previous.items.push(messageEntry);
      }
    }
    return groups;
  }, [visibleMessages]);

  const visibleAgents = useMemo(() => {
    const source = workspace?.agents ?? [];
    if (showIdleAgents) {
      return source;
    }
    return source.filter((agent) => agent.display_status !== "idle" && agent.display_status !== "retired");
  }, [showIdleAgents, workspace?.agents]);

  const groupedVisibleAgents = useMemo(() => {
    const groups = new Map<string, Agent[]>();
    for (const agent of visibleAgents) {
      const key = titleCase(agent.archetype ?? "general");
      const bucket = groups.get(key) ?? [];
      bucket.push(agent);
      groups.set(key, bucket);
    }
    return Array.from(groups.entries());
  }, [visibleAgents]);

  const agentSummary = useMemo(() => {
    const counts = { active: 0, waiting: 0, blocked: 0, idle: 0 };
    for (const agent of workspace?.agents ?? []) {
      if (agent.display_status === "blocked" || agent.display_status === "error" || agent.needs_approval) {
        counts.blocked += 1;
      } else if (
        agent.display_status === "active" ||
        agent.display_status === "coding" ||
        agent.display_status === "running" ||
        agent.display_status === "reviewing" ||
        agent.display_status === "monitoring" ||
        agent.display_status === "thinking"
      ) {
        counts.active += 1;
      } else if (agent.display_status === "waiting") {
        counts.waiting += 1;
      } else {
        counts.idle += 1;
      }
    }
    return `${counts.active} active, ${counts.blocked} needs attention, ${counts.waiting} waiting, ${counts.idle} idle`;
  }, [workspace?.agents]);

  const taskColumns = useMemo(() => {
    const buckets = {
      backlog: [] as Task[],
      in_progress: [] as Task[],
      review: [] as Task[],
      done: [] as Task[],
    };
    for (const task of workspace?.tasks ?? []) {
      buckets[boardColumnId(task)].push(task);
    }
    return buckets;
  }, [workspace?.tasks]);

  const pendingQuestion = workspace?.pending_question ?? null;
  const pendingApprovals = workspace?.pending_approvals ?? [];
  const fallbackWidgetInstances = useMemo(() => {
    return workspace && !(workspace.widget_instances?.length ?? 0) ? legacyProjectWidgetInstances(workspace) : [];
  }, [workspace]);
  const widgetInstances = (workspace?.widget_instances?.length ?? 0) > 0 ? workspace?.widget_instances ?? [] : fallbackWidgetInstances;
  const fallbackWidgetCatalog = useMemo(() => {
    return workspace && !(workspace.widget_catalog?.length ?? 0) ? legacyProjectWidgetCatalog(workspace) : [];
  }, [workspace]);
  const widgetCatalog = (workspace?.widget_catalog?.length ?? 0) > 0 ? workspace?.widget_catalog ?? [] : fallbackWidgetCatalog;
  const fallbackWidgetData = useMemo(() => {
    return workspace && fallbackWidgetInstances.length ? legacyProjectWidgetData(workspace, fallbackWidgetInstances) : [];
  }, [fallbackWidgetInstances, workspace]);
  const widgetDataByInstance = useMemo(() => {
    const entries = new Map<number, WidgetDataResponse>();
    for (const entry of fallbackWidgetData) {
      entries.set(entry.widget_instance_id, entry);
    }
    for (const entry of widgetDataState) {
      entries.set(entry.widget_instance_id, entry);
    }
    return entries;
  }, [fallbackWidgetData, widgetDataState]);
  const currentAction = workspace?.current_action ?? null;
  const swarmPlan = workspace?.swarm_plan ?? null;
  const swarmEvents = workspace?.swarm_events ?? [];
  const settingsFallback =
    workspace && systemStatus?.current_settings_summary?.project_id === workspace.project.id
      ? systemStatus.current_settings_summary
      : null;

  async function ensureProjectSettingsLoaded(projectIdToLoad: number) {
    if (projectSettingsLoadedFor === projectIdToLoad && projectSettingsDraft) {
      return projectSettingsDraft;
    }
    const nextSettings = await api.getSettings(projectIdToLoad);
    setProjectSettingsDraft(nextSettings);
    setProjectSettingsLoadedFor(projectIdToLoad);
    return nextSettings;
  }

  async function runAction<T>(action: () => Promise<T>, nextBusyMessage: string): Promise<T | undefined> {
    try {
      setBusy(nextBusyMessage);
      setInlineNotice(null);
      const result = await action();
      await loadWorkspace();
      return result;
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Action failed.");
      setBusy(null);
      return undefined;
    }
  }

  async function sendMessage() {
    const trimmed = message.trim();
    if (!trimmed || !workspace) {
      return;
    }
    await runAction(async () => {
      await api.createManagerMessage(workspace.project.id, trimmed);
      setMessage("");
    }, "Sending the message to the manager...");
  }

  async function answerQuestion(question: ManagerQuestion, option: Record<string, unknown>) {
    await runAction(
      async () => {
        await api.answerQuestion(question.id, {
          project_id: workspace?.project.id,
          option_id: String(option.id ?? option.label ?? "option"),
          selected_text: String(option.label ?? option.id ?? "Option"),
        });
      },
      "Recording the manager answer...",
    );
  }

  async function resolveApproval(approval: ApprovalRequest, decision: "approve" | "deny" | "allow") {
    await runAction(async () => {
      if (!workspace) {
        return;
      }
      if (decision === "approve") {
        await api.approveOnce(approval.id, workspace.project.id);
        return;
      }
      if (decision === "allow") {
        await api.allowApprovalForProject(approval.id, workspace.project.id);
        return;
      }
      await api.denyApproval(approval.id, workspace.project.id);
    }, "Recording the approval decision...");
  }

  async function addProjectWidget(widgetType: string) {
    if (!workspace) {
      return;
    }
    await runAction(async () => {
      await api.addProjectWidget(workspace.project.id, { widget_type: widgetType });
      setWidgetPickerOpen(false);
    }, `Adding ${widgetType}...`);
  }

  async function updateProjectWidget(instance: WidgetInstance, payload: { collapsed?: boolean; size?: WidgetSize; order_index?: number }) {
    await runAction(async () => {
      await api.updateWidgetInstance(instance.id, payload, workspace?.project.id);
    }, `Updating ${instance.widget_type}...`);
  }

  async function removeProjectWidget(instance: WidgetInstance) {
    await runAction(async () => {
      await api.deleteWidgetInstance(instance.id, workspace?.project.id);
    }, `Removing ${instance.widget_type}...`);
  }

  async function refreshProjectWidget(instance: WidgetInstance) {
    const nextData = await api.getWidgetInstanceData(instance.id, workspace?.project.id);
    setWidgetDataState((current) => {
      const remaining = current.filter((entry) => entry.widget_instance_id !== instance.id);
      return [...remaining, nextData];
    });
  }

  async function toggleProjectPin(projectIdToToggle: number, pinned: boolean) {
    await runAction(async () => {
      if (pinned) {
        await api.unpinProject(projectIdToToggle);
      } else {
        await api.pinProject(projectIdToToggle);
      }
    }, pinned ? "Removing the pinned project..." : "Pinning the project...");
  }

  async function copyText(value: string, successMessage: string) {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard access is unavailable in this browser.");
      }
      await navigator.clipboard.writeText(value);
      setInlineNotice(successMessage);
    } catch (copyError) {
      setInlineNotice(copyError instanceof Error ? `${copyError.message} Use the preview text to copy manually.` : "Copy failed. Use the preview text to copy manually.");
    }
  }

  async function openProjectSettingsDrawer() {
    if (!workspace) {
      return;
    }
    setShowProjectSettings(true);
    if (!projectSettingsDraft && settingsFallback) {
      setProjectSettingsDraft(settingsFallback);
    }
    try {
      setBusy("Loading project settings...");
      setInlineNotice(null);
      await ensureProjectSettingsLoaded(workspace.project.id);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Project settings could not be loaded.");
    } finally {
      setBusy(null);
    }
  }

  function updateProjectSettingsDraft(patch: Partial<ProjectSettings>) {
    setProjectSettingsDraft((current) => (current ? { ...current, ...patch } : current));
  }

  function updateSwarmPreferencesDraft(patch: Partial<SwarmPreferences>) {
    setSwarmPreferencesDraft((current) => (current ? { ...current, ...patch } : current));
  }

  async function saveProjectDetails() {
    if (!workspace) {
      return;
    }
    const nextName = projectNameDraft.trim();
    const nextIdea = projectIdeaDraft.trim();
    if (!nextName || !nextIdea) {
      setInlineNotice("Project name and description both need real text. Decorative emptiness is not configuration.");
      return;
    }
    try {
      setBusy("Saving project settings...");
      setInlineNotice(null);
      const settingsDraft = projectSettingsDraft ?? settingsFallback ?? (await ensureProjectSettingsLoaded(workspace.project.id));
      await api.updateProject(workspace.project.id, { name: nextName, idea: nextIdea });
      if (settingsDraft) {
        await api.updateSettings(workspace.project.id, {
          provider: settingsDraft.provider,
          manager_model: settingsDraft.manager_model,
          default_worker_model: settingsDraft.default_worker_model,
          manager_reasoning_effort: settingsDraft.manager_reasoning_effort,
          default_worker_reasoning_effort: settingsDraft.default_worker_reasoning_effort,
          per_role_model_overrides_json: settingsDraft.per_role_model_overrides_json,
          per_role_reasoning_overrides_json: settingsDraft.per_role_reasoning_overrides_json,
          provider_endpoint: settingsDraft.provider_endpoint,
          adapter_command: settingsDraft.adapter_command,
          adapter_args_json: settingsDraft.adapter_args_json,
          runner_mode: settingsDraft.runner_mode,
          sandbox_mode: settingsDraft.sandbox_mode,
          approval_policy: settingsDraft.approval_policy,
          workspace_widgets_json: settingsDraft.workspace_widgets_json,
          approval_overrides_json: settingsDraft.approval_overrides_json,
        });
      }
      if (swarmPreferencesDraft) {
        await api.updateSwarmPreferences(workspace.project.id, {
          optimization_mode: swarmPreferencesDraft.optimization_mode,
          swarm_aggressiveness: swarmPreferencesDraft.swarm_aggressiveness,
          max_agents: swarmPreferencesDraft.max_agents,
          require_approval_above_agent_count: swarmPreferencesDraft.require_approval_above_agent_count,
          allow_dynamic_spawning: swarmPreferencesDraft.allow_dynamic_spawning,
          allow_dynamic_retirement: swarmPreferencesDraft.allow_dynamic_retirement,
          docs_depth: swarmPreferencesDraft.docs_depth,
          testing_depth: swarmPreferencesDraft.testing_depth,
        });
      }
      setShowProjectSettings(false);
      await loadWorkspace();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Project settings update failed.");
      setBusy(null);
    }
  }

  async function reviseSwarmStrategy(note: string) {
    if (!workspace) {
      return;
    }
    await runAction(async () => {
      if (swarmPlan) {
        await api.reviseSwarmPlan(workspace.project.id, swarmPlan.id, note);
      } else {
        await api.createSwarmPlan(workspace.project.id, { goal: note || undefined });
      }
    }, "Revising the swarm strategy...");
  }

  async function approveOrCreateSwarmPlan() {
    if (!workspace) {
      return;
    }
    await runAction(async () => {
      const plan = swarmPlan ?? (await api.createSwarmPlan(workspace.project.id));
      if (!plan.approved_by_user) {
        await api.approveSwarmPlan(workspace.project.id, plan.id);
      }
    }, "Approving the swarm strategy...");
  }

  async function spawnSwarmFromPlan() {
    if (!workspace) {
      return;
    }
    await runAction(async () => {
      await api.spawnSwarmAgents(workspace.project.id);
    }, "Syncing agents to the approved swarm plan...");
  }

  async function scaleSwarm(direction: "up" | "down") {
    if (!workspace) {
      return;
    }
    await runAction(async () => {
      await api.scaleSwarm(workspace.project.id, {
        direction,
        reason:
          direction === "up"
            ? "Scale up because more parallel lanes may help."
            : "Scale down because too much parallelism is turning into coordination overhead.",
        count: 1,
      });
    }, direction === "up" ? "Scaling the swarm up..." : "Scaling the swarm down...");
  }

  async function updateDynamicSpawning(allowDynamicSpawning: boolean) {
    if (!workspace) {
      return;
    }
    const source = swarmPreferencesDraft ?? workspace.swarm_preferences;
    const nextPayload = {
      optimization_mode: source.optimization_mode,
      swarm_aggressiveness: source.swarm_aggressiveness,
      max_agents: source.max_agents,
      require_approval_above_agent_count: source.require_approval_above_agent_count,
      allow_dynamic_spawning: allowDynamicSpawning,
      allow_dynamic_retirement: source.allow_dynamic_retirement,
      docs_depth: source.docs_depth,
      testing_depth: source.testing_depth,
    };
    const saved = await runAction(
      () => api.updateSwarmPreferences(workspace.project.id, nextPayload),
      allowDynamicSpawning ? "Resuming dynamic swarm spawning..." : "Pausing dynamic swarm spawning...",
    );
    if (saved) {
      setSwarmPreferencesDraft(saved);
      setInlineNotice(allowDynamicSpawning ? "Dynamic spawning resumed." : "Dynamic spawning paused.");
    }
  }

  async function promptManagerFromWidget(prompt: string, nextBusyMessage: string, successMessage: string) {
    if (!workspace) {
      return;
    }
    const sent = await runAction(() => api.createManagerMessage(workspace.project.id, prompt), nextBusyMessage);
    if (sent) {
      setInlineNotice(successMessage);
    }
  }

  async function submitChangeRequest(askManagerToClassify: boolean) {
    const trimmed = changeRequestDraft.trim();
    if (!workspace) {
      return;
    }
    if (!trimmed) {
      setInlineNotice("A blank change request is not a requirement. It is dead air with punctuation.");
      return;
    }
    const created = await runAction(async () => {
      const record = await api.createChangeRequest(workspace.project.id, { request_text: trimmed });
      if (askManagerToClassify) {
        await api.createManagerMessage(
          workspace.project.id,
          `Classify this change request for the current project: "${record.request_text}". Estimate impact, decide whether it belongs in the current milestone, and say what tasks, docs, or validations should change.`,
        );
      }
      setShowChangeRequestDrawer(false);
      setChangeRequestDraft("");
      return record;
    }, askManagerToClassify ? "Logging the change request and asking the Manager to classify it..." : "Logging the change request...");
    if (created) {
      setInlineNotice(askManagerToClassify ? "Change request logged and routed to the Manager for triage." : "Change request logged.");
    }
  }

  async function loadAgentLog(agent: Agent) {
    try {
      setAgentLogBusy(agent.id);
      const nextLog = await api.getAgentLogs(agent.id);
      setAgentLog({
        agentId: agent.id,
        agentName: agent.name,
        path: nextLog.logs_path,
        content: nextLog.content || "",
      });
      setInlineNotice(null);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Agent log read failed.");
    } finally {
      setAgentLogBusy(null);
    }
  }

  async function runAgentControl(agent: Agent, control: "start" | "pause" | "stop") {
    const label =
      control === "start"
        ? `Starting ${agent.name}...`
        : control === "pause"
          ? `Pausing ${agent.name}...`
          : `Stopping ${agent.name}...`;

    await runAction(async () => {
      if (control === "start") {
        await api.startAgent(agent.id);
        return;
      }
      if (control === "pause") {
        await api.pauseAgent(agent.id);
        return;
      }
      await api.stopAgent(agent.id);
    }, label);
  }

  function promptManagerForTask(columnLabel: string) {
    setMessage(`Ask Manager to create a task for the ${columnLabel} column. Include scope, owner, and validation steps.`);
    composerRef.current?.focus();
  }

  function promptManagerToRevisitAssumption(item: Record<string, unknown>) {
    const assumption = String(item.assumption ?? "Unnamed assumption");
    const reason = String(item.reason ?? "No reason recorded.");
    const confidence = String(item.confidence ?? "unknown");
    void promptManagerFromWidget(
      `Revisit this Manager assumption for the current project: "${assumption}". Recorded reason: "${reason}". Confidence: ${confidence}. Confirm it, revise it, or ask one targeted follow-up question if the assumption is too weak to trust.`,
      "Asking the Manager to revisit that assumption...",
      "Manager prompt queued to revisit the assumption.",
    );
  }

  function promptManagerToClarifyConfidence(item: Record<string, unknown>) {
    const category = String(item.category ?? "unknown category");
    const score = String(item.confidence_score ?? "0");
    const reason = String(item.reason ?? "No reason recorded.");
    const unknowns = Array.isArray(item.unknowns) ? item.unknowns.map((entry) => String(entry)).filter(Boolean) : [];
    void promptManagerFromWidget(
      `Confidence is weak in ${category} (${score}% confidence). Current rationale: "${reason}". Unknowns: ${unknowns.length ? unknowns.join("; ") : "not recorded"}. Decide whether to ask a targeted follow-up question, make a documented assumption, or recommend a concrete decision to unblock the work.`,
      `Asking the Manager to clarify ${category} confidence...`,
      `Manager prompt queued for ${category} confidence follow-up.`,
    );
  }

  function promptManagerForConfidenceFollowUp(categories: string[]) {
    const trimmedCategories = categories.map((entry) => entry.trim()).filter(Boolean);
    void promptManagerFromWidget(
      `Generate follow-up questions for the lowest-confidence project areas${trimmedCategories.length ? `: ${trimmedCategories.join(", ")}` : ""}. Keep them concrete, high-impact, and tightly scoped to what would materially improve the plan.`,
      "Asking the Manager for focused follow-up questions...",
      "Manager prompt queued for confidence follow-up questions.",
    );
  }

  function promptManagerToReviewRecovery(item: Record<string, unknown>) {
    const triggerType = String(item.trigger_type ?? "unknown trigger");
    const summary = String(item.trigger_summary ?? "No trigger summary recorded.");
    const suggestedActions = Array.isArray(item.suggested_actions) ? item.suggested_actions.map((entry) => String(entry)).filter(Boolean) : [];
    void promptManagerFromWidget(
      `Review this recovery proposal for the current project. Trigger: ${triggerType}. Summary: "${summary}". Suggested actions: ${suggestedActions.length ? suggestedActions.join("; ") : "none recorded"}. Recommend the safest next move and explain whether we should retry, split scope, simplify scope, or add a debug-focused agent.`,
      "Asking the Manager to review recovery options...",
      "Manager prompt queued for failure recovery review.",
    );
  }

  function promptManagerToClassifyChangeRequest(item: Record<string, unknown>) {
    const requestText = String(item.request_text ?? "Unnamed change request");
    const classification = String(item.classification ?? "needs_triage");
    const impactEstimate = String(item.impact_estimate ?? "unknown");
    void promptManagerFromWidget(
      `Classify this change request for the current project: "${requestText}". Current classification is "${classification}" and current impact estimate is "${impactEstimate}". Decide whether it belongs in the current milestone, what scope it changes, and what tasks or docs should be updated.`,
      "Asking the Manager to classify the change request...",
      "Manager prompt queued for change-request triage.",
    );
  }

  function focusPendingReview() {
    promptRegionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (loading) {
    return (
      <HomeShell
        title="Project Workspace"
        subtitle="Opening the manager-led workspace shell."
        summary={summary}
        systemStatus={systemStatus}
        profile={profile}
        hideHeader
      >
        <LoadingBlock label="Loading project workspace..." />
      </HomeShell>
    );
  }

  if (notFound) {
    return (
      <HomeShell
        title="Project Workspace"
        subtitle="Mission Control could not find that project ID."
        summary={summary}
        systemStatus={systemStatus}
        profile={profile}
        hideHeader
      >
        <SectionCard title="Missing project" subtitle="The route is project-ID safe, so a missing ID stops here instead of opening the wrong workspace.">
          <p className="section-footnote">Return to the dashboard and open a project from the recent list.</p>
          <div className="button-row">
            <button type="button" onClick={() => navigate("/dashboard")}>
              Return to dashboard
            </button>
          </div>
        </SectionCard>
      </HomeShell>
    );
  }

  if (!workspace || !currentAction) {
    return (
      <HomeShell
        title="Project Workspace"
        subtitle="The workspace payload did not load correctly."
        summary={summary}
        systemStatus={systemStatus}
        profile={profile}
        hideHeader
      >
        <p className="error-text">{error ?? "Project workspace unavailable."}</p>
      </HomeShell>
    );
  }

  const queueTotal =
    workspace.manager_queue.next_up.length +
    workspace.manager_queue.waiting_on_user.length +
    workspace.manager_queue.recently_decided.length +
    workspace.manager_queue.deferred.length;
  const isPaused = workspace.project.status === "paused";
  const shareSummary = buildShareSummary(workspace, currentAction);
  const queueSnapshot = buildQueueSnapshot(workspace);
  const checklistSummary = buildChecklistSummary(workspace);
  const shareRoute = typeof window === "undefined" ? projectPath(workspace.project.id, workspace.project.slug) : `${window.location.origin}${projectPath(workspace.project.id, workspace.project.slug)}`;
  const handoffSummary =
    workspace.project.final_report_json && typeof workspace.project.final_report_json.summary_markdown === "string"
      ? String(workspace.project.final_report_json.summary_markdown)
      : null;
  const handoffRunInstructions =
    workspace.project.final_report_json && Array.isArray(workspace.project.final_report_json.run_instructions)
      ? workspace.project.final_report_json.run_instructions.map((item) => String(item)).filter(Boolean)
      : [];
  const handoffLimitations =
    workspace.project.final_report_json && Array.isArray(workspace.project.final_report_json.known_limitations)
      ? workspace.project.final_report_json.known_limitations.map((item) => String(item)).filter(Boolean)
      : [];

  return (
    <HomeShell
      title={workspace.project.name}
      subtitle={projectSubtitle}
      summary={summary}
      systemStatus={systemStatus}
      profile={profile}
      onProjectPinToggle={toggleProjectPin}
      hideHeader
    >
      <div className="workspace-page">
        <header className="workspace-project-header">
          <div className="workspace-project-header__identity">
            <span className="workspace-project-header__icon">
              <span className="workspace-project-header__monogram">{projectInitials(workspace.project.name)}</span>
            </span>
            <div className="workspace-project-header__copy">
              <span className="workspace-project-header__eyebrow">Project Workspace</span>
              <div className="workspace-project-header__title-row">
                <h1>{workspace.project.name}</h1>
                <span className={`status-pill ${readinessToneClass(workspace.overview)}`}>{workspace.workflow.current_label}</span>
                <button
                  type="button"
                  className="workspace-icon-button"
                  onClick={() => void toggleProjectPin(workspace.project.id, workspace.project.pinned)}
                  aria-label={workspace.project.pinned ? "Unpin current project" : "Pin current project"}
                >
                  <CommandIcon name={workspace.project.pinned ? "pin" : "pinOff"} />
                </button>
              </div>
              <p className="workspace-project-header__subtitle">{projectSubtitle}</p>
              <div className="workspace-project-header__meta-row">
                <span className="status-pill status-idle">Project #{workspace.project.id}</span>
                <span className={`status-pill status-${workspace.project.display_status}`}>{titleCase(workspace.project.display_status)}</span>
                {workspace.project.latest_milestone ? <span className="status-pill status-info">{workspace.project.latest_milestone}</span> : null}
              </div>
            </div>
          </div>
          <div className="workspace-project-header__actions">
            <button
              type="button"
              className="button-ghost workspace-header-button"
              onClick={() => setShowSharePanel(true)}
            >
              <CommandIcon name="share" />
              Share
            </button>
            <button type="button" className="button-ghost workspace-header-button" onClick={() => void openProjectSettingsDrawer()}>
              <CommandIcon name="settings" />
              Project Settings
            </button>
            <details className="workspace-menu">
              <summary className="workspace-icon-button" aria-label="More project actions">
                <CommandIcon name="more" />
              </summary>
              <div className="workspace-menu__panel">
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => void toggleProjectPin(workspace.project.id, workspace.project.pinned)}
                >
                  {workspace.project.pinned ? "Unpin project" : "Pin project"}
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() =>
                    void runAction(
                      () => (workspace.project.archived_at ? api.unarchiveProject(workspace.project.id) : api.archiveProject(workspace.project.id)),
                      workspace.project.archived_at ? "Restoring the project..." : "Archiving the project...",
                    )
                  }
                >
                  {workspace.project.archived_at ? "Restore from archive" : "Archive project"}
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => void runAction(() => api.generateManagerUpdate(workspace.project.id), "Generating a manager update...")}
                >
                  Generate manager update
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => {
                    void copyText(shareSummary, "Copied the current project summary.");
                    setShowSharePanel(false);
                  }}
                >
                  Copy project summary
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => void openProjectSettingsDrawer()}
                >
                  Edit project details
                </button>
              </div>
            </details>
          </div>
        </header>

        <WorkflowTracker workflow={workspace.workflow} />

        {inlineNotice ? <p className="workspace-inline-notice">{inlineNotice}</p> : null}

        <div className={actionClass(currentAction.severity)}>
          <span className="workspace-action__icon" aria-hidden="true">
            <CommandIcon name="attention" />
          </span>
          <div className="workspace-action__copy">
            <span className="workspace-action__eyebrow">{actionLabel(currentAction.type)}</span>
            <strong>{currentAction.title}</strong>
            <p>{currentAction.message}</p>
          </div>
          <div className="workspace-action__controls">
            {currentAction.auto_decide_at ? <span className="workspace-action__countdown">Auto-decides in {formatAutoDecide(currentAction.auto_decide_at)}</span> : null}
            {currentAction.type === "manager_question" || currentAction.type === "command_approval" || currentAction.type === "tool_approval" ? (
              <button type="button" className="workspace-action__primary" onClick={focusPendingReview}>
                <CommandIcon name="review" />
                Review Request
              </button>
            ) : (
              <button type="button" className="button-ghost workspace-header-button" onClick={() => void runAction(() => api.generateManagerUpdate(workspace.project.id), "Generating a manager update...")}>
                Generate Update
              </button>
            )}
            <button
              type="button"
              className="button-ghost workspace-header-button"
              onClick={() =>
                void runAction(
                  () => (isPaused ? api.resumeProject(workspace.project.id) : api.pauseProject(workspace.project.id)),
                  isPaused ? "Resuming the project..." : "Pausing the project...",
                )
              }
            >
              <CommandIcon name={isPaused ? "play" : "pause"} />
              {isPaused ? "Resume Project" : "Pause Project"}
            </button>
          </div>
        </div>

        <div className="workspace-grid">
          <aside className="workspace-sidebar workspace-sidebar--left">
            <SectionCard
              title="Active Agents"
              subtitle="The manager routes the work. This rail shows which agents are busy, blocked, reviewing, or waiting."
              actions={<span className="count-badge">{workspace.agents.length}</span>}
            >
              <p className="workspace-section-summary">{agentSummary}</p>
              <div className="button-row">
                <button type="button" className="button-ghost" onClick={() => setShowIdleAgents((current) => !current)}>
                  {showIdleAgents ? "Hide idle agents" : "Show idle agents"}
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => setInlineNotice("Agent spawning is still a scoped placeholder here. The existing worker roster is live.")}
                >
                  Spawn Agent
                </button>
                <button type="button" className="button-ghost" onClick={() => void runAction(() => api.startProjectAgents(workspace.project.id), "Starting idle agents...")}>
                  Start all idle agents
                </button>
              </div>
              <div className="workspace-agent-list">
                {groupedVisibleAgents.length ? (
                  groupedVisibleAgents.map(([group, agents]) => (
                    <section key={group} className="workspace-agent-group">
                      <div className="workspace-agent-group__header">
                        <strong>{group}</strong>
                        <span className="count-badge">{agents.length}</span>
                      </div>
                      <div className="workspace-agent-group__items">
                        {agents.map((agent) => (
                          <WorkspaceAgentCard key={agent.id} agent={agent} />
                        ))}
                      </div>
                    </section>
                  ))
                ) : (
                  <p className="section-footnote">No active or waiting agents right now.</p>
                )}
              </div>
              <button type="button" className="button-ghost workspace-inline-link" onClick={() => setShowAgentsDrawer(true)}>
                View all agents
              </button>
            </SectionCard>
          </aside>

          <section className={`workspace-main${focusChat ? " workspace-main--focus" : ""}`}>
            <SectionCard
              title="Manager Chat"
              subtitle="Talk only to the manager. Questions, approvals, milestones, blockers, and handoff signals all land here."
              actions={
                <div className="button-row">
                  <button type="button" className="button-ghost" onClick={() => setShowChatSettings((current) => !current)}>
                    Chat Settings
                  </button>
                  <button type="button" className="button-ghost" onClick={() => setFocusChat((current) => !current)}>
                    {focusChat ? "Exit Focus" : "Focus Chat"}
                  </button>
                </div>
              }
            >
              {showChatSettings ? (
                <div className="workspace-chat-settings">
                  <label className="checkbox-row">
                    <input type="checkbox" checked={showSystemMessages} onChange={(event) => setShowSystemMessages(event.target.checked)} />
                    <span>Show system notices</span>
                  </label>
                  <label className="checkbox-row">
                    <input type="checkbox" checked={compactChat} onChange={(event) => setCompactChat(event.target.checked)} />
                    <span>Compact timeline density</span>
                  </label>
                </div>
              ) : null}

              <div className={`workspace-chat${compactChat ? " workspace-chat--compact" : ""}`}>
                <div className="workspace-chat__history">
                  {groupedMessages.length ? (
                    groupedMessages.map((group) => (
                      <div key={group.label} className="workspace-chat__day-group">
                        <div className="workspace-date-separator">{group.label}</div>
                        {group.items.map((entry) => (
                          <ManagerMessageCard
                            key={entry.id}
                            message={entry}
                            agentName={entry.related_agent_id ? agentsById.get(entry.related_agent_id)?.name ?? null : null}
                            userDisplayName={profile?.display_name ?? "You"}
                          />
                        ))}
                      </div>
                    ))
                  ) : (
                    <p className="section-footnote">No manager messages yet. Start the conversation below.</p>
                  )}
                </div>

                <div ref={promptRegionRef} className="workspace-chat__pending">
                  {pendingQuestion ? (
                    <QuestionCard
                      question={pendingQuestion}
                      onAnswer={(option) => void answerQuestion(pendingQuestion, option)}
                    />
                  ) : null}
                  {pendingApprovals.map((approval) => (
                    <ApprovalCard
                      key={approval.id}
                      approval={approval}
                      requestingAgentName={approval.requesting_agent_id ? agentsById.get(approval.requesting_agent_id)?.name ?? null : null}
                      onResolve={(decision) => void resolveApproval(approval, decision)}
                    />
                  ))}
                </div>

                <div className="workspace-chat__composer">
                  <div className="workspace-composer__controls">
                    <button
                      type="button"
                      className="workspace-icon-button"
                      onClick={() => setInlineNotice("Attachments are not wired yet. Route files and notes through the manager message until that lands.")}
                      aria-label="Add project context"
                    >
                      <CommandIcon name="attach" />
                    </button>
                    <button
                      type="button"
                      className="workspace-icon-button"
                      onClick={() => {
                        setMessage("Summarize the current project state and tell me what needs attention next.");
                        composerRef.current?.focus();
                      }}
                      aria-label="Ask for AI assist"
                    >
                      <CommandIcon name="sparkle" />
                    </button>
                  </div>
                  <textarea
                    ref={composerRef}
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    placeholder="Message Manager Agent..."
                  />
                  <div className="button-row">
                    {busy ? <span className="section-footnote">{busy}</span> : null}
                    <button type="button" onClick={() => void sendMessage()}>
                      <CommandIcon name="send" />
                      Send
                    </button>
                  </div>
                </div>
              </div>
            </SectionCard>
            {error ? <p className="error-text">{error}</p> : null}
          </section>

          <aside className="workspace-sidebar workspace-sidebar--right">
            <SectionCard
              title="Manager Queue"
              subtitle="What the manager is routing next, what needs you, what was decided, and what is intentionally deferred."
              actions={
                <button type="button" className="button-ghost workspace-inline-link" onClick={() => setShowQueueDrawer(true)}>
                  View full queue
                </button>
              }
            >
              <div className="workspace-queue-header">
                <span className="count-badge">{queueTotal}</span>
              </div>
              <QueueSection title="Next Up" items={workspace.manager_queue.next_up} limit={3} />
              <QueueSection title="Waiting on User" items={workspace.manager_queue.waiting_on_user} limit={3} />
              <QueueSection title="Recently Decided" items={workspace.manager_queue.recently_decided} limit={3} />
              <QueueSection title="Deferred" items={workspace.manager_queue.deferred} limit={3} />
            </SectionCard>

            <SectionCard
              title="Project Widgets"
              subtitle="Modular workspace summaries. Manager Chat still owns actual decisions because pretending otherwise would be a design crime."
              actions={
                <button type="button" className="button-ghost" onClick={() => setWidgetPickerOpen((current) => !current)}>
                  <CommandIcon name="plus" />
                </button>
              }
            >
              <WidgetGrid
                instances={widgetInstances.filter((instance) => instance.area === "project_right_sidebar")}
                dataByInstance={widgetDataByInstance}
                onCollapseToggle={(instance) => void updateProjectWidget(instance, { collapsed: !instance.collapsed })}
                onMove={(instance, direction) =>
                  void updateProjectWidget(instance, {
                    order_index: Math.max(0, instance.order_index + (direction === "up" ? -1 : 1)),
                  })
                }
              onRemove={(instance) => void removeProjectWidget(instance)}
              onRefresh={(instance) => void refreshProjectWidget(instance)}
              onSizeChange={(instance, size) => void updateProjectWidget(instance, { size })}
              renderBody={(instance, data) =>
                renderProjectWidgetBody(instance, data, workspace, {
                  onViewSwarmPlan: () => setShowSwarmPlanDrawer(true),
                  onReviseSwarmStrategy: () => void reviseSwarmStrategy("Revise the swarm strategy based on the current project state."),
                  onApproveSwarmStrategy: () => void approveOrCreateSwarmPlan(),
                  onSpawnSwarmPlan: () => void spawnSwarmFromPlan(),
                  onScaleSwarmUp: () => void scaleSwarm("up"),
                  onScaleSwarmDown: () => void scaleSwarm("down"),
                  onPauseDynamicSpawning: () => void updateDynamicSpawning(false),
                  onResumeDynamicSpawning: () => void updateDynamicSpawning(true),
                  onOpenProjectSettings: () => void openProjectSettingsDrawer(),
                  onOpenChangeRequestDrawer: () => setShowChangeRequestDrawer(true),
                  onAskManagerToRevisitAssumption: promptManagerToRevisitAssumption,
                  onAskManagerToClarifyConfidence: promptManagerToClarifyConfidence,
                  onGenerateConfidenceFollowUp: promptManagerForConfidenceFollowUp,
                  onAskManagerToReviewRecovery: promptManagerToReviewRecovery,
                  onAskManagerToClassifyChangeRequest: promptManagerToClassifyChangeRequest,
                  onRequestWritePermission: () => void runAction(() => api.updateWritePermission(workspace.project.id, "write_allowed"), "Updating write permission..."),
                  onOpenImportReview: () => navigate(`/projects/${workspace.project.id}/import/review`),
                })
              }
            />
              {widgetPickerOpen ? (
                <WidgetSelectorPanel
                  scope="project"
                  catalog={widgetCatalog}
                  addedWidgetTypes={widgetInstances.map((instance) => instance.widget_type)}
                  onAdd={(widgetType) => void addProjectWidget(widgetType)}
                />
              ) : null}
            </SectionCard>
          </aside>
        </div>

        <div className="workspace-lower-grid">
          <SectionCard
            title="Task Board"
            subtitle="Compact distribution view. The manager still owns the workflow so this does not become Jira with delusions."
            actions={
              <button type="button" className="button-ghost workspace-inline-link" onClick={() => setShowAllTasks((current) => !current)}>
                {showAllTasks ? "Collapse task board" : "View all tasks"}
              </button>
            }
          >
            <div className="workspace-task-board">
              <TaskColumn
                title="Backlog"
                tasks={taskColumns.backlog}
                agentsById={agentsById}
                expanded={showAllTasks}
                onAddTask={() => promptManagerForTask("Backlog")}
              />
              <TaskColumn
                title="In Progress"
                tasks={taskColumns.in_progress}
                agentsById={agentsById}
                expanded={showAllTasks}
                onAddTask={() => promptManagerForTask("In Progress")}
              />
              <TaskColumn
                title="Review"
                tasks={taskColumns.review}
                agentsById={agentsById}
                expanded={showAllTasks}
                onAddTask={() => promptManagerForTask("Review")}
              />
              <TaskColumn
                title="Done"
                tasks={taskColumns.done}
                agentsById={agentsById}
                expanded={showAllTasks}
                onAddTask={() => promptManagerForTask("Done")}
              />
            </div>
          </SectionCard>

          <SectionCard
            title="Activity Log"
            subtitle="Recent project events without making you read a cave wall of raw logs."
            actions={
              <button type="button" className="button-ghost workspace-inline-link" onClick={() => setShowAllActivity((current) => !current)}>
                {showAllActivity ? "Collapse activity" : "View full activity log"}
              </button>
            }
          >
            <ActivityLogPanel entries={workspace.activity_log} expanded={showAllActivity} />
          </SectionCard>
        </div>

        <SectionCard
          title="Additional Project Widgets"
          subtitle="Optional lower-panel widgets for deeper context without turning the core workspace into a panel farm."
        >
          <WidgetGrid
            instances={widgetInstances.filter((instance) => instance.area === "project_bottom")}
            dataByInstance={widgetDataByInstance}
            onCollapseToggle={(instance) => void updateProjectWidget(instance, { collapsed: !instance.collapsed })}
            onMove={(instance, direction) =>
              void updateProjectWidget(instance, {
                order_index: Math.max(0, instance.order_index + (direction === "up" ? -1 : 1)),
              })
            }
            onRemove={(instance) => void removeProjectWidget(instance)}
            onRefresh={(instance) => void refreshProjectWidget(instance)}
            onSizeChange={(instance, size) => void updateProjectWidget(instance, { size })}
            renderBody={(instance, data) =>
              renderProjectWidgetBody(instance, data, workspace, {
                onViewSwarmPlan: () => setShowSwarmPlanDrawer(true),
                onReviseSwarmStrategy: () => void reviseSwarmStrategy("Revise the swarm strategy based on the current project state."),
                onApproveSwarmStrategy: () => void approveOrCreateSwarmPlan(),
                onSpawnSwarmPlan: () => void spawnSwarmFromPlan(),
                onScaleSwarmUp: () => void scaleSwarm("up"),
                onScaleSwarmDown: () => void scaleSwarm("down"),
                onPauseDynamicSpawning: () => void updateDynamicSpawning(false),
                onResumeDynamicSpawning: () => void updateDynamicSpawning(true),
                onOpenProjectSettings: () => void openProjectSettingsDrawer(),
                onOpenChangeRequestDrawer: () => setShowChangeRequestDrawer(true),
                onAskManagerToRevisitAssumption: promptManagerToRevisitAssumption,
                onAskManagerToClarifyConfidence: promptManagerToClarifyConfidence,
                onGenerateConfidenceFollowUp: promptManagerForConfidenceFollowUp,
                onAskManagerToReviewRecovery: promptManagerToReviewRecovery,
                onAskManagerToClassifyChangeRequest: promptManagerToClassifyChangeRequest,
                onRequestWritePermission: () => void runAction(() => api.updateWritePermission(workspace.project.id, "write_allowed"), "Updating write permission..."),
                onOpenImportReview: () => navigate(`/projects/${workspace.project.id}/import/review`),
              })
            }
          />
        </SectionCard>

        {showQueueDrawer ? (
          <WorkspaceDrawer
            title="Full Manager Queue"
            subtitle="The manager's routing picture without making you reverse-engineer it from scattered panels."
            onClose={() => setShowQueueDrawer(false)}
            actions={
              <>
                <button type="button" className="button-ghost" onClick={focusPendingReview}>
                  Jump to pending review
                </button>
                <button
                  type="button"
                  onClick={() => void runAction(() => api.generateManagerUpdate(workspace.project.id), "Refreshing the manager queue...")}
                >
                  Refresh queue
                </button>
              </>
            }
          >
            <QueueInspector queue={workspace.manager_queue} onJumpToReview={focusPendingReview} />
          </WorkspaceDrawer>
        ) : null}

        {showAgentsDrawer ? (
          <WorkspaceDrawer
            title="All Agents"
            subtitle="Full roster controls for this project, without making the main workspace read like a monitoring dashboard threw up."
            onClose={() => setShowAgentsDrawer(false)}
            actions={
              <button type="button" onClick={() => void runAction(() => api.startProjectAgents(workspace.project.id), "Starting idle agents...")}>
                Start idle agents
              </button>
            }
          >
            <div className="workspace-agent-inspector-list">
              {workspace.agents.map((agent) => (
                <article key={agent.id} className="workspace-agent-inspector-card">
                  <div className="workspace-agent-inspector-card__top">
                    <div className="workspace-agent-inspector-card__identity">
                      <span className="workspace-agent-inspector-card__avatar">{projectInitials(agent.name)}</span>
                      <div>
                        <strong>{agent.name}</strong>
                        <p>{agent.role}</p>
                      </div>
                    </div>
                    <span className={`status-pill status-${agent.display_status ?? agent.status}`}>{titleCase(agent.display_status ?? agent.status)}</span>
                  </div>
                  <div className="workspace-agent-inspector-card__details">
                    <span>Model: {agent.active_model ?? "Use provider default"}</span>
                    <span>Runner: {agent.runner_mode ?? agent.active_runner_type ?? "idle"}</span>
                    <span>Current task: {agent.current_task_title ?? "No tasks assigned"}</span>
                    <span>Latest report: {agent.last_report_summary ?? "No recent report yet."}</span>
                  </div>
                  <div className="workspace-agent-inspector-card__actions">
                    {agent.kind !== "manager" ? (
                      <button type="button" className="button-ghost" onClick={() => void runAgentControl(agent, "start")}>
                        Start
                      </button>
                    ) : null}
                    {agent.kind !== "manager" ? (
                      <button type="button" className="button-ghost" onClick={() => void runAgentControl(agent, "pause")}>
                        Pause
                      </button>
                    ) : null}
                    {agent.kind !== "manager" ? (
                      <button type="button" className="button-ghost" onClick={() => void runAgentControl(agent, "stop")}>
                        Stop
                      </button>
                    ) : null}
                    <button type="button" className="button-ghost" onClick={() => void loadAgentLog(agent)}>
                      {agentLogBusy === agent.id ? "Loading logs..." : "View logs"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
            <div className="workspace-agent-log-panel">
              <div className="workspace-agent-log-panel__header">
                <strong>{agentLog ? `${agentLog.agentName} log preview` : "Latest agent logs"}</strong>
                <span className="section-footnote">{agentLog?.path ?? "Select an agent to inspect the latest runner log."}</span>
              </div>
              <pre>{agentLog?.content || "No agent log loaded yet."}</pre>
            </div>
          </WorkspaceDrawer>
        ) : null}

        {showSwarmPlanDrawer ? (
          <WorkspaceDrawer
            title="Swarm Plan"
            subtitle="Manager-controlled swarm planning, with actual path ownership and retirement logic instead of one static agent template pretending to be strategy."
            onClose={() => setShowSwarmPlanDrawer(false)}
            actions={
              <>
                <button type="button" className="button-ghost" onClick={() => void reviseSwarmStrategy("Revise the swarm plan based on the current workspace state.")}>
                  Revise Swarm Strategy
                </button>
                <button type="button" className="button-ghost" onClick={() => void approveOrCreateSwarmPlan()}>
                  {swarmPlan?.approved_by_user ? "Re-approve Strategy" : "Approve Strategy"}
                </button>
                <button type="button" onClick={() => void spawnSwarmFromPlan()}>
                  Sync Agents
                </button>
              </>
            }
          >
            <SwarmPlanInspector
              plan={swarmPlan}
              preferences={workspace.swarm_preferences}
              events={swarmEvents}
              onScaleUp={() => void scaleSwarm("up")}
              onScaleDown={() => void scaleSwarm("down")}
            />
          </WorkspaceDrawer>
        ) : null}

        {showProjectSettings ? (
          <WorkspaceDrawer
            title="Project Settings"
            subtitle="Project-scoped controls live here. Global app settings can stay out of the way for once."
            onClose={() => setShowProjectSettings(false)}
            actions={
              <>
                <button type="button" className="button-ghost" onClick={() => navigate(modelsPath(workspace.project.id, workspace.project.slug))}>
                  Models & Runners
                </button>
                <button type="button" onClick={() => void saveProjectDetails()}>
                  Save changes
                </button>
              </>
            }
          >
            <div className="workspace-settings-layout">
              <section className="workspace-settings-section">
                <div className="workspace-settings-project-tile">
                  <span className="workspace-settings-project-tile__avatar">{projectInitials(workspace.project.name)}</span>
                  <div>
                    <strong>{workspace.project.name}</strong>
                    <span>Project #{workspace.project.id}</span>
                    <span>{workspace.project.workspace_path}</span>
                  </div>
                </div>
                <div className="workspace-settings-grid">
                  <label>
                    <span>Project name</span>
                    <input value={projectNameDraft} onChange={(event) => setProjectNameDraft(event.target.value)} />
                  </label>
                  <label>
                    <span>Project description</span>
                    <textarea value={projectIdeaDraft} onChange={(event) => setProjectIdeaDraft(event.target.value)} />
                  </label>
                </div>
              </section>

              <section className="workspace-settings-section">
                <div className="workspace-settings-section__header">
                  <div>
                    <h3>Execution Defaults</h3>
                    <p>Project-scoped overrides for runner behavior. Advanced per-role control still lives in Models &amp; Runners, where it belongs.</p>
                  </div>
                  <span className={`status-pill status-${workspace.project.display_status}`}>{titleCase(workspace.project.display_status)}</span>
                </div>
                {projectSettingsDraft ?? settingsFallback ? (
                  <div className="workspace-settings-grid workspace-settings-grid--triple">
                    <label>
                      <span>Provider</span>
                      <input value={titleCase((projectSettingsDraft ?? settingsFallback)!.provider)} readOnly />
                    </label>
                    <label>
                      <span>Runner mode</span>
                      <select
                        value={(projectSettingsDraft ?? settingsFallback)!.runner_mode}
                        onChange={(event) => updateProjectSettingsDraft({ runner_mode: event.target.value as RunnerMode })}
                      >
                        {RUNNER_MODE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Sandbox mode</span>
                      <select
                        value={(projectSettingsDraft ?? settingsFallback)!.sandbox_mode}
                        onChange={(event) => updateProjectSettingsDraft({ sandbox_mode: event.target.value as SandboxMode })}
                      >
                        {SANDBOX_MODE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Approval policy</span>
                      <select
                        value={(projectSettingsDraft ?? settingsFallback)!.approval_policy}
                        onChange={(event) => updateProjectSettingsDraft({ approval_policy: event.target.value as ApprovalPolicy })}
                      >
                        {APPROVAL_POLICY_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Manager model override</span>
                      <input
                        value={(projectSettingsDraft ?? settingsFallback)!.manager_model ?? ""}
                        placeholder="Use provider default"
                        onChange={(event) => updateProjectSettingsDraft({ manager_model: event.target.value || null })}
                      />
                    </label>
                    <label>
                      <span>Default worker model override</span>
                      <input
                        value={(projectSettingsDraft ?? settingsFallback)!.default_worker_model ?? ""}
                        placeholder="Use provider default"
                        onChange={(event) => updateProjectSettingsDraft({ default_worker_model: event.target.value || null })}
                      />
                    </label>
                    <label>
                      <span>Manager reasoning effort</span>
                      <select
                        value={(projectSettingsDraft ?? settingsFallback)!.manager_reasoning_effort ?? ""}
                        onChange={(event) =>
                          updateProjectSettingsDraft({ manager_reasoning_effort: (event.target.value || null) as ReasoningEffort | null })
                        }
                      >
                        {REASONING_OPTIONS.map((option) => (
                          <option key={option.value || "default"} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Worker reasoning effort</span>
                      <select
                        value={(projectSettingsDraft ?? settingsFallback)!.default_worker_reasoning_effort ?? ""}
                        onChange={(event) =>
                          updateProjectSettingsDraft({ default_worker_reasoning_effort: (event.target.value || null) as ReasoningEffort | null })
                        }
                      >
                        {REASONING_OPTIONS.map((option) => (
                          <option key={`worker-${option.value || "default"}`} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                ) : (
                  <p className="section-footnote">Loading project-scoped execution settings...</p>
                )}
              </section>

              <section className="workspace-settings-section">
                <div className="workspace-settings-section__header">
                  <div>
                    <h3>Swarm Preferences</h3>
                    <p>Tell the Manager whether this project should bias toward speed, quality, research, docs depth, or a larger swarm. More agents are not magic. They are overhead with better marketing.</p>
                  </div>
                  {swarmPlan ? <span className={`status-pill status-${swarmPlan.coordination_risk}`}>{titleCase(swarmPlan.mode)}</span> : null}
                </div>
                {swarmPreferencesDraft ? (
                  <>
                    <div className="workspace-settings-grid workspace-settings-grid--triple">
                      <label>
                        <span>Optimization mode</span>
                        <select
                          value={swarmPreferencesDraft.optimization_mode}
                          onChange={(event) =>
                            updateSwarmPreferencesDraft({ optimization_mode: event.target.value as SwarmPreferences["optimization_mode"] })
                          }
                        >
                          {SWARM_MODE_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>Swarm aggressiveness</span>
                        <select
                          value={swarmPreferencesDraft.swarm_aggressiveness}
                          onChange={(event) =>
                            updateSwarmPreferencesDraft({ swarm_aggressiveness: event.target.value as SwarmPreferences["swarm_aggressiveness"] })
                          }
                        >
                          {SWARM_AGGRESSIVENESS_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>Max agents</span>
                        <input
                          type="number"
                          min={1}
                          max={50}
                          value={swarmPreferencesDraft.max_agents}
                          onChange={(event) => updateSwarmPreferencesDraft({ max_agents: Number(event.target.value) || 1 })}
                        />
                      </label>
                      <label>
                        <span>Approval above agent count</span>
                        <input
                          type="number"
                          min={1}
                          max={50}
                          value={swarmPreferencesDraft.require_approval_above_agent_count}
                          onChange={(event) =>
                            updateSwarmPreferencesDraft({ require_approval_above_agent_count: Number(event.target.value) || 1 })
                          }
                        />
                      </label>
                      <label>
                        <span>Docs depth</span>
                        <select
                          value={swarmPreferencesDraft.docs_depth}
                          onChange={(event) => updateSwarmPreferencesDraft({ docs_depth: event.target.value as SwarmPreferences["docs_depth"] })}
                        >
                          {DOCS_DEPTH_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>Testing depth</span>
                        <select
                          value={swarmPreferencesDraft.testing_depth}
                          onChange={(event) =>
                            updateSwarmPreferencesDraft({ testing_depth: event.target.value as SwarmPreferences["testing_depth"] })
                          }
                        >
                          {TESTING_DEPTH_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <div className="workspace-settings-flags">
                      <label className="checkbox-row">
                        <input
                          type="checkbox"
                          checked={swarmPreferencesDraft.allow_dynamic_spawning}
                          onChange={(event) => updateSwarmPreferencesDraft({ allow_dynamic_spawning: event.target.checked })}
                        />
                        <span>Allow dynamic spawning</span>
                      </label>
                      <label className="checkbox-row">
                        <input
                          type="checkbox"
                          checked={swarmPreferencesDraft.allow_dynamic_retirement}
                          onChange={(event) => updateSwarmPreferencesDraft({ allow_dynamic_retirement: event.target.checked })}
                        />
                        <span>Allow dynamic retirement</span>
                      </label>
                    </div>
                    <div className="workspace-settings-note">
                      <strong>Swarm safety</strong>
                      <span>Plans above the configured threshold require approval before Mission Control fans out the worker count. Because letting a local app spawn chaos by default would be an idiotic product choice.</span>
                    </div>
                  </>
                ) : (
                  <p className="section-footnote">Loading swarm preferences...</p>
                )}
              </section>

              <section className="workspace-settings-section">
                <div className="workspace-settings-actions">
                  <button
                    type="button"
                    className="button-ghost"
                    onClick={() => void toggleProjectPin(workspace.project.id, workspace.project.pinned)}
                  >
                    {workspace.project.pinned ? "Unpin from sidebar" : "Pin to sidebar"}
                  </button>
                  <button
                    type="button"
                    className="button-ghost"
                    onClick={() =>
                      void runAction(
                        () => (workspace.project.archived_at ? api.unarchiveProject(workspace.project.id) : api.archiveProject(workspace.project.id)),
                        workspace.project.archived_at ? "Restoring the project..." : "Archiving the project...",
                      )
                    }
                  >
                    {workspace.project.archived_at ? "Restore from archive" : "Archive project"}
                  </button>
                  <button
                    type="button"
                    className="button-ghost"
                    onClick={() =>
                      void runAction(
                        () => (isPaused ? api.resumeProject(workspace.project.id) : api.pauseProject(workspace.project.id)),
                        isPaused ? "Resuming the project..." : "Pausing the project...",
                      )
                    }
                  >
                    {isPaused ? "Resume project" : "Pause project"}
                  </button>
                </div>
                <div className="workspace-settings-note">
                  <strong>Project route safety</strong>
                  <span>The route is anchored to project ID {workspace.project.id}. Renaming the project updates the cosmetic slug without risking the wrong workspace.</span>
                </div>
              </section>
            </div>
          </WorkspaceDrawer>
        ) : null}

        {showChangeRequestDrawer ? (
          <WorkspaceDrawer
            title="New Change Request"
            subtitle="Log the requested change, then let the Manager decide whether it belongs in the current milestone or becomes a scoped follow-up."
            onClose={() => setShowChangeRequestDrawer(false)}
            actions={
              <>
                <button type="button" className="button-ghost" onClick={() => void submitChangeRequest(false)}>
                  Save only
                </button>
                <button type="button" onClick={() => void submitChangeRequest(true)}>
                  Save and ask Manager
                </button>
              </>
            }
          >
            <div className="workspace-drawer-grid mission-widget-composer">
              <label>
                <span>Change request</span>
                <textarea
                  value={changeRequestDraft}
                  onChange={(event) => setChangeRequestDraft(event.target.value)}
                  placeholder="Describe the requested change, why it matters, and anything the Manager should preserve."
                />
              </label>
              <div className="mission-widget-note-list">
                <p className="section-footnote">
                  Use this when the user wants to alter scope without burying the request in random chat history.
                </p>
                <p className="section-footnote">
                  Save only if you just need it recorded. Save and ask Manager if you want classification, impact, and task routing immediately.
                </p>
              </div>
            </div>
          </WorkspaceDrawer>
        ) : null}

        {showSharePanel ? (
          <WorkspaceDrawer
            title="Share / Export"
            subtitle="No fake collaboration theater. These actions copy or package real local project state."
            onClose={() => setShowSharePanel(false)}
          >
            <div className="workspace-share-grid">
              <button
                type="button"
                className="selection-card"
                onClick={() => void copyText(shareSummary, "Copied the current project summary.")}
              >
                <strong>Copy project summary</strong>
                <span>Phase, action state, readiness, and local path in one clean payload.</span>
              </button>
              <button
                type="button"
                className="selection-card"
                onClick={() => void copyText(shareRoute, "Copied the workspace route.")}
              >
                <strong>Copy workspace link</strong>
                <span>Useful for local handoff notes or reopening the exact project route.</span>
              </button>
              <button
                type="button"
                className="selection-card"
                onClick={() => void copyText(workspace.project.workspace_path, "Copied the local workspace path.")}
              >
                <strong>Copy local workspace path</strong>
                <span>The real project folder, because that tends to matter more than a fake share URL.</span>
              </button>
              <button
                type="button"
                className="selection-card"
                disabled={!handoffSummary}
                onClick={() => {
                  if (handoffSummary) {
                    void copyText(handoffSummary, "Copied the current handoff summary.");
                  }
                }}
              >
                <strong>Copy handoff summary</strong>
                <span>{handoffSummary ? "Use the latest handoff-ready summary." : "No handoff summary exists yet."}</span>
              </button>
              <button
                type="button"
                className="selection-card"
                disabled={!handoffRunInstructions.length}
                onClick={() => {
                  if (handoffRunInstructions.length) {
                    void copyText(handoffRunInstructions.join("\n"), "Copied the run instructions.");
                  }
                }}
              >
                <strong>Copy run instructions</strong>
                <span>{handoffRunInstructions.length ? "Lift the latest run steps straight from the handoff." : "No run instructions exist yet."}</span>
              </button>
              <button
                type="button"
                className="selection-card"
                onClick={() => void copyText(queueSnapshot, "Copied the current manager queue snapshot.")}
              >
                <strong>Copy queue snapshot</strong>
                <span>Current routing state without forcing someone to read three panels and guess.</span>
              </button>
              <button
                type="button"
                className="selection-card"
                onClick={() => navigate(`/projects/${workspace.project.id}/handoff`)}
              >
                <strong>Open handoff view</strong>
                <span>Jump directly to the current project handoff page.</span>
              </button>
            </div>
            <div className="workspace-share-preview-grid">
              <div className="workspace-share-preview">
                <strong>Project summary preview</strong>
                <pre>{shareSummary}</pre>
              </div>
              <div className="workspace-share-preview">
                <strong>Readiness checklist</strong>
                <pre>{checklistSummary || "No checklist summary yet."}</pre>
              </div>
              <div className="workspace-share-preview">
                <strong>Manager queue snapshot</strong>
                <pre>{queueSnapshot}</pre>
              </div>
              <div className="workspace-share-preview">
                <strong>Known limitations</strong>
                <pre>{handoffLimitations.length ? handoffLimitations.join("\n") : "No known limitations recorded yet."}</pre>
              </div>
            </div>
          </WorkspaceDrawer>
        ) : null}
      </div>
    </HomeShell>
  );
}

function WorkflowTracker({ workflow }: { workflow: ProjectWorkflow }) {
  return (
    <div className="workspace-workflow">
      {workflow.steps.map((step) => (
        <div key={step.id} className={`workspace-workflow__step workspace-workflow__step--${step.state}`}>
          <span className="workspace-workflow__ordinal">{step.ordinal}</span>
          <div className="workspace-workflow__copy">
            <span className="workspace-workflow__label">{step.label}</span>
            <span className="workspace-workflow__state">{step.state === "complete" ? "Complete" : step.state === "current" ? "Current" : "Up next"}</span>
          </div>
          {step.state === "complete" ? (
            <span className="workspace-workflow__check" aria-hidden="true">
              <CommandIcon name="check" />
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function WorkspaceAgentCard({ agent }: { agent: Agent }) {
  return (
    <article className={`workspace-agent-card workspace-agent-card--${agent.display_status ?? agent.status}`}>
      <div className="workspace-agent-card__top">
        <div className="workspace-agent-card__identity">
          <span className="workspace-agent-card__avatar">{projectInitials(agent.name)}</span>
          <div className="workspace-agent-card__identity-copy">
            <strong>{agent.name}</strong>
            <p>{agent.active_model ?? "Use provider default"}</p>
          </div>
        </div>
        <span className={`status-pill status-${agent.display_status ?? agent.status}`}>{titleCase(agent.display_status ?? agent.status)}</span>
      </div>
      <div className="workspace-agent-card__labels">
        {agent.archetype ? <span className="workspace-agent-card__archetype">{titleCase(agent.archetype)}</span> : null}
        <span className="workspace-agent-card__role">{agent.role}</span>
      </div>
      <p className="workspace-agent-card__task">{agent.mission ?? agent.current_task_title ?? agent.current_action ?? "No tasks assigned."}</p>
      <div className="workspace-agent-card__meta">
        <span>Runner: {agent.runner_mode ?? agent.active_runner_type ?? "idle"}</span>
        <span>Task: {agent.current_task_title ?? agent.current_action ?? "No tasks assigned"}</span>
        <span>Retire when: {agent.retire_when ?? "Manager keeps this agent until the mission closes."}</span>
        <span>{agent.last_report_summary ?? "No recent report yet."}</span>
      </div>
      <div className={agentActivityClass(agent.display_status ?? agent.status)} aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
    </article>
  );
}

function ManagerMessageCard({
  message,
  agentName,
  userDisplayName,
}: {
  message: ManagerMessage;
  agentName: string | null;
  userDisplayName: string;
}) {
  const segments = message.content_markdown
    .split(/\n{2,}/)
    .map((segment) => segment.trim())
    .filter(Boolean);
  const modeLabel = messageModeLabel(message);

  return (
    <article className={`workspace-message ${messageToneClass(message)}`}>
      <span className={`workspace-message__avatar workspace-message__avatar--${message.role}`} aria-hidden="true">
        {messageAvatarLabel(message, userDisplayName)}
      </span>
      <div className="workspace-message__body">
        <div className="workspace-message__meta">
          <div className="workspace-message__identity">
            <strong>{roleLabel(message)}</strong>
            <span>{formatShortTime(message.created_at)}</span>
          </div>
          <span className={`workspace-message__tag workspace-message__tag--${message.message_type}`}>{messageTypeLabel(message)}</span>
        </div>
        <div className="workspace-message__content">
          {(segments.length ? segments : [message.content_markdown]).map((segment, index) => (
            <p key={`${message.id}-${index}`}>{segment}</p>
          ))}
        </div>
        <div className="workspace-message__footer">
          <div className="workspace-message__context">
            {agentName ? <small>{agentName}</small> : null}
            {modeLabel ? <small>{modeLabel}</small> : null}
          </div>
          <div className="workspace-message__controls">
            <button
              type="button"
              className="workspace-icon-button"
              aria-label="Copy message"
              onClick={() => {
                void navigator.clipboard?.writeText(message.content_markdown);
              }}
            >
              <CommandIcon name="copy" />
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}

function QuestionCard({
  question,
  onAnswer,
}: {
  question: ManagerQuestion;
  onAnswer: (option: Record<string, unknown>) => void;
}) {
  const recommended = question.manager_recommendation
    ? question.options_json.find((option) => String(option.label ?? option.id) === question.manager_recommendation || String(option.id ?? "") === question.manager_recommendation)
    : null;

  return (
    <div className="workspace-prompt-card workspace-prompt-card--question">
      <div className="workspace-prompt-card__header">
        <div>
          <span className="workspace-prompt-card__eyebrow">Manager question</span>
          <strong>Question ({titleCase(question.impact)} Impact)</strong>
          <p>{question.question}</p>
        </div>
        <div className="workspace-prompt-card__meta">
          <span className={`status-pill status-${question.impact}`}>{titleCase(question.impact)}</span>
          <small>{formatShortTime(question.created_at)}</small>
        </div>
      </div>
      <div className="workspace-prompt-card__actions">
        {question.auto_decide_at ? <p className="section-footnote">Auto-decides in {formatAutoDecide(question.auto_decide_at)}</p> : null}
        {recommended ? (
          <button type="button" className="button-ghost workspace-inline-link" onClick={() => onAnswer(recommended)}>
            Not sure, recommend one
          </button>
        ) : null}
      </div>
      <div className="option-grid">
        {question.options_json.map((option) => (
          <button key={String(option.id ?? option.label ?? "option")} type="button" className="selection-card" onClick={() => onAnswer(option)}>
            <strong>{String(option.label ?? option.id ?? "Option")}</strong>
            {"description" in option ? <span>{String(option.description ?? "")}</span> : null}
          </button>
        ))}
      </div>
    </div>
  );
}

function ApprovalCard({
  approval,
  requestingAgentName,
  onResolve,
}: {
  approval: ApprovalRequest;
  requestingAgentName: string | null;
  onResolve: (decision: "approve" | "deny" | "allow") => void;
}) {
  const command = typeof approval.request_payload_json.command === "string" ? approval.request_payload_json.command : approval.title;
  const scope = typeof approval.request_payload_json.scope === "string" ? approval.request_payload_json.scope : "Project workspace";
  const access = typeof approval.request_payload_json.access === "string" ? approval.request_payload_json.access : null;
  const canAllowForProject = approval.risk_level === "low" || approval.risk_level === "medium";
  const contextItems = [
    { label: approval.request_type === "command" ? "Command" : "Tool", value: command },
    { label: "Working directory", value: approval.cwd },
    { label: "Access requested", value: access },
    { label: "Runner reference", value: approval.runner_ref },
  ].filter((item) => item.value);

  return (
    <div className="workspace-prompt-card workspace-prompt-card--approval">
      <div className="workspace-prompt-card__header">
        <div>
          <span className="workspace-prompt-card__eyebrow">{approvalTypeLabel(approval)}</span>
          <strong>
            {approvalTypeLabel(approval)} ({titleCase(approval.risk_level)} Risk)
          </strong>
          <p>{requestingAgentName ? `Requested by ${requestingAgentName}. ` : ""}{approval.reason_short}</p>
        </div>
        <span className={riskClass(approval.risk_level)}>{titleCase(approval.risk_level)}</span>
      </div>
      <div className="workspace-approval-layout">
        <div className="workspace-approval-layout__main">
          <div className="workspace-approval-requester">
            <span className="workspace-approval-requester__avatar">{projectInitials(requestingAgentName ?? approval.title)}</span>
            <div>
              <strong>{requestingAgentName ?? "Manager-routed request"}</strong>
              <span>{approval.reason_short}</span>
            </div>
          </div>
          <div className="workspace-approval-summary">
            {contextItems.map((item) => (
              <div key={item.label}>
                <dt>{item.label}</dt>
                <dd>{String(item.value)}</dd>
              </div>
            ))}
          </div>
        </div>
        <div className="workspace-approval-layout__side">
          <div className="workspace-approval-metric">
            <dt>Risk Level</dt>
            <dd>{titleCase(approval.risk_level)}</dd>
          </div>
          <div className="workspace-approval-metric">
            <dt>Scope</dt>
            <dd>{scope}</dd>
          </div>
          <div className="workspace-approval-metric">
            <dt>Status</dt>
            <dd>{titleCase(approval.status)}</dd>
          </div>
        </div>
      </div>
      <details className="workspace-approval-details">
        <summary>View details</summary>
        <div className="workspace-approval-details__content">
          <p className="section-footnote">Expanded details stay hidden by default because raw approval payloads are for inspection, not decoration.</p>
          <pre>{JSON.stringify(approval.request_payload_json, null, 2)}</pre>
        </div>
      </details>
      <div className="button-row">
        <button type="button" onClick={() => onResolve("approve")}>
          Approve once
        </button>
        <button type="button" className="button-ghost" onClick={() => onResolve("deny")}>
          Deny
        </button>
        {canAllowForProject ? (
          <button type="button" className="button-ghost" onClick={() => onResolve("allow")}>
            Always Allow for Project
          </button>
        ) : null}
      </div>
    </div>
  );
}

function QueueSection({ title, items, limit }: { title: string; items: ManagerQueueItem[]; limit: number }) {
  const visible = items.slice(0, limit);
  return (
    <div className="workspace-queue-section">
      <h3>
        {title} <span className="section-footnote">({items.length})</span>
      </h3>
      <div className="workspace-queue-list">
        {visible.length ? (
          visible.map((item) => (
            <article key={item.id} className="workspace-queue-item">
              <div className="workspace-queue-item__copy">
                <strong>{item.title}</strong>
                <span>{titleCase(item.type)}</span>
              </div>
              <span className={`status-pill ${queueStatusClass(item.status)}`}>{titleCase(item.status)}</span>
            </article>
          ))
        ) : (
          <p className="section-footnote">Nothing queued here right now.</p>
        )}
      </div>
    </div>
  );
}

function SwarmStrategyPanel({
  plan,
  preferences,
  currentAgentCount,
  onViewPlan,
  onRevise,
  onApprove,
  onSpawn,
  onScaleUp,
  onScaleDown,
}: {
  plan: SwarmPlan | null;
  preferences: SwarmPreferences;
  currentAgentCount: number;
  onViewPlan: () => void;
  onRevise: () => void;
  onApprove: () => void;
  onSpawn: () => void;
  onScaleUp: () => void;
  onScaleDown: () => void;
}) {
  if (!plan) {
    return (
      <div className="workspace-swarm-panel">
        <p className="section-footnote">No swarm plan exists yet. Generate one once the Manager has enough context to stop pretending one roster fits every project.</p>
        <div className="button-row">
          <button type="button" onClick={onApprove}>
            Generate Swarm Plan
          </button>
          <button type="button" className="button-ghost" onClick={onRevise}>
            Revise Strategy
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-swarm-panel">
      <div className="workspace-swarm-panel__metrics">
        <div className="workspace-swarm-panel__metric">
          <span>Mode</span>
          <strong>{titleCase(plan.mode)}</strong>
        </div>
        <div className="workspace-swarm-panel__metric">
          <span>Active / max</span>
          <strong>
            {currentAgentCount} / {plan.max_agent_count}
          </strong>
        </div>
        <div className="workspace-swarm-panel__metric">
          <span>Recommended</span>
          <strong>{plan.recommended_agent_count} agents</strong>
        </div>
      </div>
      <p className="workspace-swarm-panel__summary">{plan.strategy_summary}</p>
      <div className="workspace-swarm-panel__status-grid">
        <span className={`status-pill status-${plan.coordination_risk}`}>Coordination risk: {titleCase(plan.coordination_risk)}</span>
        <span className={`status-pill status-${plan.path_conflict_risk}`}>Path conflict: {titleCase(plan.path_conflict_risk)}</span>
        <span className={`status-pill ${preferences.allow_dynamic_spawning ? "status-done" : "status-idle"}`}>
          Dynamic spawning {preferences.allow_dynamic_spawning ? "enabled" : "paused"}
        </span>
        <span className={`status-pill ${preferences.allow_dynamic_retirement ? "status-done" : "status-idle"}`}>
          Dynamic retirement {preferences.allow_dynamic_retirement ? "enabled" : "paused"}
        </span>
      </div>
      {plan.current_bottleneck ? (
        <div className="workspace-swarm-panel__note">
          <strong>Current bottleneck</strong>
          <span>{plan.current_bottleneck}</span>
        </div>
      ) : null}
      {plan.usage_warning ? <p className="workspace-swarm-panel__warning">{plan.usage_warning}</p> : null}
      {plan.approval_required && !plan.approved_by_user ? (
        <p className="workspace-swarm-panel__warning">
          This plan needs approval before Mission Control spawns the full swarm. More agents are not free speed. They are coordination overhead wearing a cape.
        </p>
      ) : null}
      <div className="button-row">
        <button type="button" className="button-ghost" onClick={onViewPlan}>
          View Swarm Plan
        </button>
        <button type="button" className="button-ghost" onClick={onRevise}>
          Revise Swarm Strategy
        </button>
        <button type="button" className="button-ghost" onClick={onApprove}>
          {plan.approved_by_user ? "Refresh Approval" : "Approve Strategy"}
        </button>
        <button type="button" className="button-ghost" onClick={onSpawn}>
          Sync Agents
        </button>
        <button type="button" className="button-ghost" disabled={!preferences.allow_dynamic_spawning} onClick={onScaleUp}>
          Scale Up
        </button>
        <button type="button" className="button-ghost" disabled={!preferences.allow_dynamic_retirement} onClick={onScaleDown}>
          Scale Down
        </button>
      </div>
    </div>
  );
}

function SwarmPlanInspector({
  plan,
  preferences,
  events,
  onScaleUp,
  onScaleDown,
}: {
  plan: SwarmPlan | null;
  preferences: SwarmPreferences;
  events: ProjectWorkspace["swarm_events"];
  onScaleUp: () => void;
  onScaleDown: () => void;
}) {
  if (!plan) {
    return <p className="section-footnote">No swarm plan exists yet. Generate one first so the Manager can stop improvising around a missing strategy.</p>;
  }

  return (
    <div className="workspace-swarm-drawer">
      <section className="workspace-swarm-drawer__section">
        <div className="workspace-swarm-drawer__summary">
          <div>
            <span>Mode</span>
            <strong>{titleCase(plan.mode)}</strong>
          </div>
          <div>
            <span>Recommended</span>
            <strong>{plan.recommended_agent_count}</strong>
          </div>
          <div>
            <span>Approval threshold</span>
            <strong>{preferences.require_approval_above_agent_count}</strong>
          </div>
          <div>
            <span>Plan status</span>
            <strong>{titleCase(plan.status)}</strong>
          </div>
        </div>
        <p className="workspace-swarm-panel__summary">{plan.strategy_summary}</p>
        <div className="workspace-swarm-panel__status-grid">
          <span className={`status-pill status-${plan.coordination_risk}`}>Coordination risk: {titleCase(plan.coordination_risk)}</span>
          <span className={`status-pill status-${plan.path_conflict_risk}`}>Path conflict: {titleCase(plan.path_conflict_risk)}</span>
          <span className={`status-pill ${plan.approved_by_user ? "status-done" : "status-needs_review"}`}>
            {plan.approved_by_user ? "Approved" : "Needs approval"}
          </span>
        </div>
        {plan.usage_warning ? <p className="workspace-swarm-panel__warning">{plan.usage_warning}</p> : null}
      </section>

      <section className="workspace-swarm-drawer__section">
        <div className="workspace-swarm-drawer__header">
          <h3>Agent roster</h3>
          <span className="count-badge">{plan.specs.length}</span>
        </div>
        <div className="workspace-swarm-spec-list">
          {plan.specs.map((spec) => (
            <article key={spec.id} className="workspace-swarm-spec-card">
              <div className="workspace-swarm-spec-card__top">
                <div>
                  <strong>{spec.name}</strong>
                  <p>{titleCase(spec.archetype)} specialist</p>
                </div>
                <span className={`status-pill status-${spec.status === "spawned" ? "done" : spec.status === "deferred" ? "needs_review" : "info"}`}>
                  {titleCase(spec.status)}
                </span>
              </div>
              <p className="workspace-swarm-spec-card__mission">{spec.mission}</p>
              <div className="workspace-swarm-spec-card__meta">
                <span>Spawn phase: {titleCase(spec.spawn_phase.replace(/_/g, " "))}</span>
                <span>Priority: {spec.priority}</span>
                <span>Model policy: {spec.model_policy}</span>
                <span>Allowed paths: {summarizePaths(spec.allowed_paths_json)}</span>
                <span>Forbidden paths: {summarizePaths(spec.forbidden_paths_json)}</span>
                <span>Retire when: {spec.retire_when}</span>
              </div>
              {spec.toolset_json.length ? (
                <div className="workspace-swarm-spec-card__tools">
                  {spec.toolset_json.map((tool) => (
                    <span key={tool} className="status-pill status-idle">
                      {titleCase(tool.replace(/_/g, " "))}
                    </span>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </section>

      <section className="workspace-swarm-drawer__section">
        <div className="workspace-swarm-drawer__header">
          <h3>Expected bottlenecks</h3>
          <span className="count-badge">{plan.expected_bottlenecks_json.length}</span>
        </div>
        {plan.expected_bottlenecks_json.length ? (
          <ul className="workspace-swarm-drawer__list">
            {plan.expected_bottlenecks_json.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="section-footnote">No major bottlenecks were recorded for this plan.</p>
        )}
      </section>

      <section className="workspace-swarm-drawer__section">
        <div className="workspace-swarm-drawer__header">
          <h3>Validation strategy</h3>
          <div className="button-row">
            <button type="button" className="button-ghost" disabled={!preferences.allow_dynamic_spawning} onClick={onScaleUp}>
              Scale Up
            </button>
            <button type="button" className="button-ghost" disabled={!preferences.allow_dynamic_retirement} onClick={onScaleDown}>
              Scale Down
            </button>
          </div>
        </div>
        {plan.validation_strategy_json.length ? (
          <ul className="workspace-swarm-drawer__list">
            {plan.validation_strategy_json.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="section-footnote">Validation guidance is not populated for this plan yet.</p>
        )}
      </section>

      <section className="workspace-swarm-drawer__section">
        <div className="workspace-swarm-drawer__header">
          <h3>Swarm events</h3>
          <span className="count-badge">{events.length}</span>
        </div>
        <div className="workspace-swarm-event-list">
          {events.length ? (
            events.map((event) => (
              <article key={event.id} className="workspace-swarm-event">
                <div className="workspace-swarm-event__meta">
                  <span>{formatShortTime(event.created_at)}</span>
                  <span className="status-pill status-info">{titleCase(event.event_type.replace(/_/g, " "))}</span>
                </div>
                <strong>{event.message}</strong>
              </article>
            ))
          ) : (
            <p className="section-footnote">No swarm events recorded yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function ProjectOverviewPanel({ overview }: { overview: ProjectOverview }) {
  return (
    <div className="workspace-overview">
      <div className="workspace-overview__progress">
        <div className="workspace-overview__progress-header">
          <strong>Handoff Progress</strong>
          <span>{overview.handoff_progress}%</span>
        </div>
        <div className="workspace-progress-bar" aria-hidden="true">
          <span style={{ width: `${Math.min(100, Math.max(0, overview.handoff_progress))}%` }} />
        </div>
      </div>
      <div className="workspace-overview__checklist">
        {overview.checklist.map((item) => (
          <div key={item.id} className="workspace-overview__item">
            <div>
              <strong>{item.label}</strong>
              <span>{item.detail}</span>
            </div>
            <span className={`status-pill ${overviewStatusClass(item.status)}`}>{overviewStatusLabel(item.status)}</span>
          </div>
        ))}
      </div>
      <div className="workspace-overview__readiness">
        <strong>Overall Readiness</strong>
        <span className={`status-pill ${readinessToneClass(overview)}`}>
          {overview.readiness_label}
        </span>
      </div>
    </div>
  );
}

function QueueInspector({
  queue,
  onJumpToReview,
}: {
  queue: ProjectWorkspace["manager_queue"];
  onJumpToReview: () => void;
}) {
  return (
    <div className="workspace-drawer-grid">
      <QueueInspectorSection title="Next Up" items={queue.next_up} />
      <QueueInspectorSection title="Waiting on User" items={queue.waiting_on_user} actionLabel="Review request" onAction={onJumpToReview} />
      <QueueInspectorSection title="Recently Decided" items={queue.recently_decided} />
      <QueueInspectorSection title="Deferred" items={queue.deferred} />
    </div>
  );
}

function QueueInspectorSection({
  title,
  items,
  actionLabel,
  onAction,
}: {
  title: string;
  items: ManagerQueueItem[];
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <section className="workspace-queue-drawer-section">
      <div className="workspace-queue-drawer-section__header">
        <h3>{title}</h3>
        <span className="count-badge">{items.length}</span>
      </div>
      <div className="workspace-queue-drawer-section__list">
        {items.length ? (
          items.map((item) => (
            <article key={item.id} className="workspace-queue-drawer-item">
              <div>
                <strong>{item.title}</strong>
                <p>{titleCase(item.type)} / {titleCase(item.status)}</p>
              </div>
              {actionLabel && onAction ? (
                <button type="button" className="button-ghost" onClick={onAction}>
                  {actionLabel}
                </button>
              ) : null}
            </article>
          ))
        ) : (
          <p className="section-footnote">Nothing queued here right now.</p>
        )}
      </div>
    </section>
  );
}

function WorkspaceDrawer({
  title,
  subtitle,
  actions,
  onClose,
  children,
}: {
  title: string;
  subtitle: string;
  actions?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="workspace-drawer-backdrop" role="presentation" onClick={onClose}>
      <aside className="workspace-drawer" role="dialog" aria-modal="true" aria-label={title} onClick={(event) => event.stopPropagation()}>
        <div className="workspace-drawer__header">
          <div>
            <h2>{title}</h2>
            <p>{subtitle}</p>
          </div>
          <div className="workspace-drawer__actions">
            {actions}
            <button type="button" className="workspace-icon-button" onClick={onClose} aria-label={`Close ${title}`}>
              x
            </button>
          </div>
        </div>
        <div className="workspace-drawer__content">{children}</div>
      </aside>
    </div>
  );
}

function TaskColumn({
  title,
  tasks,
  agentsById,
  expanded,
  onAddTask,
}: {
  title: string;
  tasks: Task[];
  agentsById: Map<number, Agent>;
  expanded: boolean;
  onAddTask: () => void;
}) {
  const visible = expanded ? tasks : tasks.slice(0, 3);
  return (
    <div className={`workspace-task-column workspace-task-column--${title.toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="workspace-task-column__header">
        <div>
          <h3>{title}</h3>
          <span className="workspace-task-column__hint">{taskColumnHint(title)}</span>
        </div>
        <span className="count-badge">{tasks.length}</span>
      </div>
      <div className="workspace-task-column__items">
        {visible.length ? (
          visible.map((task) => {
            const assignedAgent = task.assigned_agent_id ? agentsById.get(task.assigned_agent_id) ?? null : null;
            return (
              <article key={task.id} className="workspace-task-card">
                <div className="workspace-task-card__top">
                  <strong>{task.title}</strong>
                  <span className={`status-pill ${task.status === "done" ? "status-done" : task.status === "blocked" ? "status-blocked" : task.status === "needs_review" ? "status-needs_review" : "status-working"}`}>
                    {priorityLabel(task.priority)}
                  </span>
                </div>
                <p>{assignedAgent ? assignedAgent.name : task.agent_role ?? "Manager-routed task"}</p>
                <small>{task.waiting_reason ?? titleCase(task.status)}</small>
              </article>
            );
          })
        ) : (
          <p className="section-footnote">No tasks in this column.</p>
        )}
      </div>
      <button type="button" className="button-ghost workspace-inline-link" onClick={onAddTask}>
        <CommandIcon name="plus" />
        Add task
      </button>
    </div>
  );
}

function ActivityLogPanel({ entries, expanded }: { entries: ActivityLogEntry[]; expanded: boolean }) {
  const visible = expanded ? entries : entries.slice(0, 7);
  return (
    <div className="workspace-activity-log">
      <div className="workspace-activity-log__header">
        <span className="count-badge">{entries.length}</span>
        <span className="section-footnote">{expanded ? "Showing the full recent timeline." : "Showing the latest events only."}</span>
      </div>
      <div className="workspace-activity-log__list">
        {visible.length ? (
          visible.map((entry) => (
            <article key={entry.id} className="workspace-activity-log__item">
              <div className="workspace-activity-log__meta">
                <span>{formatShortTime(entry.created_at)}</span>
                <span className={activityClass(entry)}>{titleCase(entry.event_type.replace(/[._]/g, " "))}</span>
              </div>
              <strong>{entry.summary}</strong>
              {entry.detail ? <p>{entry.detail}</p> : null}
              {entry.agent_name ? (
                <div className="workspace-activity-log__footer">
                  <small className="workspace-activity-log__agent">{entry.agent_name}</small>
                </div>
              ) : null}
            </article>
          ))
        ) : (
          <p className="section-footnote">No activity recorded yet.</p>
        )}
      </div>
    </div>
  );
}

function ProjectWidgetList({
  items,
  renderActions,
}: {
  items: Array<Record<string, unknown>>;
  renderActions?: (item: Record<string, unknown>) => ReactNode;
}) {
  return (
    <div className="mission-widget-list">
      {items.map((item, index) => (
        <article key={`${String(item.id ?? item.title ?? item.name ?? index)}`} className="mission-widget-list__item">
          <strong>{String(item.title ?? item.agent_name ?? item.category ?? item.gate_type ?? item.assumption ?? item.request_text ?? "Item")}</strong>
          <span>
            {String(
              item.detail ??
                item.message ??
                item.reason ??
                item.status ??
                item.mission ??
                item.trigger_summary ??
                item.decision ??
                item.impact_estimate ??
                "",
            )}
          </span>
          {renderActions ? <div className="mission-widget-list__actions">{renderActions(item)}</div> : null}
        </article>
      ))}
    </div>
  );
}

function ProjectWidgetFacts({ rows }: { rows: Array<{ label: string; value: string }> }) {
  return (
    <div className="mission-widget-facts">
      {rows.map((row) => (
        <div key={row.label} className="mission-widget-facts__row">
          <span>{row.label}</span>
          <strong>{row.value}</strong>
        </div>
      ))}
    </div>
  );
}

function renderProjectWidgetBody(
  instance: WidgetInstance,
  data: WidgetDataResponse | undefined,
  workspace: ProjectWorkspace,
  actions: {
    onViewSwarmPlan: () => void;
    onReviseSwarmStrategy: () => void;
    onApproveSwarmStrategy: () => void;
    onSpawnSwarmPlan: () => void;
    onScaleSwarmUp: () => void;
    onScaleSwarmDown: () => void;
    onPauseDynamicSpawning: () => void;
    onResumeDynamicSpawning: () => void;
    onOpenProjectSettings: () => void;
    onOpenChangeRequestDrawer: () => void;
    onAskManagerToRevisitAssumption: (item: Record<string, unknown>) => void;
    onAskManagerToClarifyConfidence: (item: Record<string, unknown>) => void;
    onGenerateConfidenceFollowUp: (categories: string[]) => void;
    onAskManagerToReviewRecovery: (item: Record<string, unknown>) => void;
    onAskManagerToClassifyChangeRequest: (item: Record<string, unknown>) => void;
    onRequestWritePermission: () => void;
    onOpenImportReview: () => void;
  },
) {
  if (!data) {
    return <p className="section-footnote">No widget data is available yet.</p>;
  }

  if (data.status === "coming_soon" || data.status === "needs_setup" || data.status === "unsupported") {
    return <p className="section-footnote">{data?.empty_state ?? "No widget data is available yet."}</p>;
  }

  const payload = data.data_json;
  const items = Array.isArray(payload.items) ? (payload.items as Array<Record<string, unknown>>) : [];
  if (data.status === "empty") {
    if (instance.widget_type === "Change Request Mode") {
      return (
        <>
          <p className="section-footnote">{data.empty_state ?? "No widget data is available yet."}</p>
          <div className="mission-widget-actions">
            <button type="button" className="button-ghost" onClick={actions.onOpenChangeRequestDrawer}>
              New change request
            </button>
          </div>
        </>
      );
    }
    return <p className="section-footnote">{data.empty_state ?? "No widget data is available yet."}</p>;
  }

  switch (instance.widget_type) {
    case "Swarm Strategy":
      return (
        <SwarmStrategyPanel
          plan={workspace.swarm_plan}
          preferences={workspace.swarm_preferences}
          currentAgentCount={workspace.agents.length}
          onViewPlan={actions.onViewSwarmPlan}
          onRevise={actions.onReviseSwarmStrategy}
          onApprove={actions.onApproveSwarmStrategy}
          onSpawn={actions.onSpawnSwarmPlan}
          onScaleUp={actions.onScaleSwarmUp}
          onScaleDown={actions.onScaleSwarmDown}
        />
      );
    case "Swarm Budget":
      return (
        <>
          <ProjectWidgetFacts
            rows={[
              { label: "Active agents", value: `${String(payload.active_agents ?? 0)} / ${String(payload.max_agents ?? 0)}` },
              { label: "Intensity", value: String(payload.intensity ?? "Unknown") },
              { label: "Dynamic spawning", value: payload.dynamic_spawning_paused ? "Paused" : "Enabled" },
              { label: "Approval threshold", value: String(payload.approval_threshold ?? "Unknown") },
            ]}
          />
          <div className="mission-widget-actions">
            <button
              type="button"
              className="button-ghost"
              onClick={payload.dynamic_spawning_paused ? actions.onResumeDynamicSpawning : actions.onPauseDynamicSpawning}
            >
              {payload.dynamic_spawning_paused ? "Resume dynamic spawning" : "Pause dynamic spawning"}
            </button>
            <button type="button" className="button-ghost" onClick={actions.onOpenProjectSettings}>
              Open swarm settings
            </button>
          </div>
        </>
      );
    case "Agent Contracts":
    case "Path Ownership Map":
    case "Decision Ledger":
    case "Agent Stuck Detection":
    case "Merge / Review Gates":
    case "Approval Audit Log":
    case "Risk Assessment":
    case "What Changed Timeline":
    case "Agent Report Inbox":
    case "Human Attention Queue":
      return items.length ? <ProjectWidgetList items={items} /> : <p className="section-footnote">{data.empty_state ?? "Nothing to show."}</p>;
    case "Confidence Tracker": {
      const confidenceItems = items.map((item) => ({
        ...item,
        title: item.category,
        detail: `${String(item.confidence_score ?? 0)}% confidence${item.reason ? ` · ${String(item.reason)}` : ""}`,
      }));
      const lowestConfidence = Array.isArray(payload.lowest_confidence) ? payload.lowest_confidence.map((entry) => String(entry)).filter(Boolean) : [];
      return confidenceItems.length ? (
        <>
          <ProjectWidgetList
            items={confidenceItems}
            renderActions={(item) => (
              <button type="button" className="button-ghost" onClick={() => actions.onAskManagerToClarifyConfidence(item)}>
                Ask Manager to clarify
              </button>
            )}
          />
          <div className="mission-widget-actions">
            <button type="button" className="button-ghost" onClick={() => actions.onGenerateConfidenceFollowUp(lowestConfidence)}>
              Generate follow-up questions
            </button>
          </div>
        </>
      ) : (
        <p className="section-footnote">No confidence scores recorded yet.</p>
      );
    }
    case "Failure Recovery": {
      const recoveryItems = items.map((item) => ({
        ...item,
        title: item.trigger_summary ?? item.title,
        detail: `${titleCase(String(item.trigger_type ?? "recovery"))}${item.selected_action ? ` · selected: ${String(item.selected_action)}` : ""}`,
      }));
      return recoveryItems.length ? (
        <ProjectWidgetList
          items={recoveryItems}
          renderActions={(item) => (
            <button type="button" className="button-ghost" onClick={() => actions.onAskManagerToReviewRecovery(item)}>
              Ask Manager to review
            </button>
          )}
        />
      ) : (
        <p className="section-footnote">{data.empty_state ?? "No recovery proposals are active right now."}</p>
      );
    }
    case "Manager Assumptions": {
      const assumptionItems = items.map((item) => ({
        ...item,
        title: item.assumption,
        detail: `${item.reason ? String(item.reason) : "No reason recorded."}${item.confidence ? ` · confidence ${String(item.confidence)}` : ""}`,
      }));
      return assumptionItems.length ? (
        <ProjectWidgetList
          items={assumptionItems}
          renderActions={(item) => (
            <button type="button" className="button-ghost" onClick={() => actions.onAskManagerToRevisitAssumption(item)}>
              Ask Manager to revisit
            </button>
          )}
        />
      ) : (
        <p className="section-footnote">{data.empty_state ?? "No active Manager assumptions are recorded right now."}</p>
      );
    }
    case "Change Request Mode": {
      const changeItems = items.map((item) => ({
        ...item,
        title: item.request_text,
        detail: `${titleCase(String(item.classification ?? "needs_triage"))} · ${titleCase(String(item.impact_estimate ?? "unknown"))} · ${titleCase(String(item.status ?? "new"))}`,
      }));
      return (
        <>
          {changeItems.length ? (
            <ProjectWidgetList
              items={changeItems}
              renderActions={(item) => (
                <button type="button" className="button-ghost" onClick={() => actions.onAskManagerToClassifyChangeRequest(item)}>
                  Ask Manager to classify
                </button>
              )}
            />
          ) : (
            <p className="section-footnote">{data.empty_state ?? "No change requests have been logged for this project yet."}</p>
          )}
          <div className="mission-widget-actions">
            <button type="button" className="button-ghost" onClick={actions.onOpenChangeRequestDrawer}>
              New change request
            </button>
          </div>
        </>
      );
    }
    case "Project Health Score":
      return (
        <>
          <ProjectWidgetFacts
            rows={[
              { label: "State", value: String(payload.state ?? "Unknown") },
              { label: "Score", value: `${String(payload.score ?? 0)}/100` },
              { label: "Next action", value: String(payload.next_action ?? "Unknown") },
            ]}
          />
          {Array.isArray(payload.reasons) ? (
            <div className="mission-widget-note-list">
              {(payload.reasons as string[]).slice(0, 4).map((reason) => (
                <p key={reason} className="section-footnote">
                  {reason}
                </p>
              ))}
            </div>
          ) : null}
        </>
      );
    case "Model Assignment Policy":
      return (
        <ProjectWidgetFacts
          rows={[
            { label: "Policy", value: String(payload.policy_name ?? "Unknown") },
            { label: "Manager", value: String(payload.manager_model ?? "Default") },
            { label: "Coding", value: String(payload.coding_model ?? "Default") },
            { label: "Fallback", value: String(payload.fallback_model ?? "Default") },
          ]}
        />
      );
    case "Tool Routing Policy":
      return items.length ? <ProjectWidgetList items={items.map((item) => ({ ...item, title: item.agent_archetype, detail: `Allowed: ${String((item.allowed_tools as unknown[] | undefined)?.length ?? 0)}, approval: ${String((item.requires_approval as unknown[] | undefined)?.length ?? 0)}` }))} /> : <p className="section-footnote">No tool routing policies exist yet.</p>;
    case "Sandbox Profiles": {
      const currentProfile = (payload.current_profile as Record<string, unknown> | undefined) ?? {};
      return (
        <ProjectWidgetFacts
          rows={[
            { label: "Profile", value: String(currentProfile.name ?? "Unknown") },
            { label: "Network", value: String(currentProfile.network_policy ?? "Unknown") },
            { label: "Writes", value: String(currentProfile.file_write_policy ?? "Unknown") },
            { label: "Command approval", value: String(currentProfile.command_approval_policy ?? "Unknown") },
          ]}
        />
      );
    }
    case "Security Policy": {
      const rows = Array.isArray(payload.rows) ? (payload.rows as Array<Record<string, unknown>>) : [];
      const notes = Array.isArray(payload.notes) ? (payload.notes as string[]) : [];
      return (
        <>
          <ProjectWidgetFacts
            rows={rows.map((row) => ({
              label: String(row.label ?? "Policy"),
              value: String(row.value ?? "Unknown"),
            }))}
          />
          {notes.length ? (
            <div className="mission-widget-note-list">
              {notes.map((note) => (
                <p key={note} className="section-footnote">
                  {note}
                </p>
              ))}
            </div>
          ) : null}
        </>
      );
    }
    case "Repo Intelligence":
      return (
        <ProjectWidgetFacts
          rows={[
            { label: "Languages", value: Array.isArray(payload.languages) ? (payload.languages as string[]).join(", ") || "Unknown" : "Unknown" },
            { label: "Frameworks", value: Array.isArray(payload.frameworks) ? (payload.frameworks as string[]).join(", ") || "Unknown" : "Unknown" },
            { label: "Build commands", value: Array.isArray(payload.build_commands) ? String((payload.build_commands as string[]).length) : "0" },
            { label: "Important folders", value: Array.isArray(payload.important_folders) ? String((payload.important_folders as string[]).length) : "0" },
          ]}
        />
      );
    case "Codebase Map":
      return (
        <>
          <ProjectWidgetFacts
            rows={[
              { label: "Languages", value: Array.isArray(payload.languages) ? ((payload.languages as string[]).join(", ") || "Unknown") : "Unknown" },
              { label: "Frameworks", value: Array.isArray(payload.frameworks) ? ((payload.frameworks as string[]).join(", ") || "Unknown") : "Unknown" },
              { label: "Commands", value: Array.isArray(payload.build_commands) ? String((payload.build_commands as string[]).length + ((payload.test_commands as string[] | undefined)?.length ?? 0)) : "0" },
              { label: "Folders", value: Array.isArray(payload.important_folders) ? String((payload.important_folders as string[]).length) : "0" },
            ]}
          />
          <div className="mission-widget-actions">
            <button type="button" className="button-ghost" onClick={actions.onOpenImportReview}>
              Open import review
            </button>
          </div>
        </>
      );
    case "Codebase Understanding":
      return (
        <>
          <p className="section-footnote">{String(payload.summary ?? "No summary available.")}</p>
          <ProjectWidgetFacts
            rows={[
              { label: "Run confidence", value: String(Math.round(Number((payload.confidence_by_area as Record<string, number> | undefined)?.run_commands ?? 0) * 100)) + "%" },
              { label: "Test confidence", value: String(Math.round(Number((payload.confidence_by_area as Record<string, number> | undefined)?.test_commands ?? 0) * 100)) + "%" },
              { label: "Interview mode", value: String(payload.recommended_interview_mode ?? "Unknown") },
              { label: "Generation", value: String(payload.generation_mode ?? "Unknown") },
            ]}
          />
          <div className="mission-widget-actions">
            <button type="button" className="button-ghost" onClick={actions.onOpenImportReview}>
              Review report
            </button>
          </div>
        </>
      );
    case "Imported Codebase Safety":
      return (
        <>
          <ProjectWidgetFacts
            rows={[
              { label: "Write mode", value: String(payload.write_permission_status ?? "Unknown") },
              { label: "Snapshot first", value: payload.require_snapshot_before_edits ? "Recommended" : "Optional" },
              { label: "Build approval", value: payload.require_approval_for_build_commands ? "Required" : "Relaxed" },
              { label: "Test approval", value: payload.require_approval_for_test_commands ? "Required" : "Relaxed" },
            ]}
          />
          <div className="mission-widget-actions">
            {payload.write_permission_status === "read_only" ? (
              <button type="button" className="button-ghost" onClick={actions.onRequestWritePermission}>
                Request write permission
              </button>
            ) : null}
            <button type="button" className="button-ghost" onClick={actions.onOpenImportReview}>
              Review safety
            </button>
          </div>
        </>
      );
    case "AGENTS.md Status":
      return (
        <>
          <ProjectWidgetFacts
            rows={[
              { label: "Present", value: payload.has_agents_md ? "Yes" : "No" },
              { label: "Action", value: String(payload.recommended_action ?? "Unknown") },
              { label: "Path", value: String(payload.path ?? "Not detected") },
              { label: "Summary", value: String(payload.summary ?? "No summary available") },
            ]}
          />
          <div className="mission-widget-actions">
            <button type="button" className="button-ghost" onClick={actions.onOpenImportReview}>
              Review AGENTS.md
            </button>
          </div>
        </>
      );
    case "Scan Coverage":
      return (
        <>
          <ProjectWidgetFacts
            rows={[
              { label: "Depth", value: String(payload.scan_depth ?? "Unknown") },
              { label: "Size", value: String(payload.codebase_size ?? "Unknown") },
              { label: "Indexed", value: Array.isArray(payload.indexed_areas) ? String((payload.indexed_areas as string[]).length) : "0" },
              { label: "Unindexed", value: Array.isArray(payload.unindexed_areas) ? String((payload.unindexed_areas as string[]).length) : "0" },
            ]}
          />
          <div className="mission-widget-actions">
            <button type="button" className="button-ghost" onClick={actions.onOpenImportReview}>
              Open scan review
            </button>
          </div>
        </>
      );
    case "Validation Recipe": {
      const steps = Array.isArray(payload.steps) ? (payload.steps as Array<Record<string, unknown>>) : [];
      return steps.length ? <ProjectWidgetList items={steps.map((step) => ({ title: step.title, detail: `${String(step.type ?? "step")} / ${String(step.status ?? "pending")}` }))} /> : <p className="section-footnote">No validation steps are defined yet.</p>;
    }
    case "Handoff Quality":
      return (
        <ProjectWidgetFacts
          rows={[
            { label: "Quality level", value: String(payload.quality_level ?? "Unknown") },
            { label: "Handoff progress", value: `${String(payload.handoff_progress ?? workspace.overview.handoff_progress)}%` },
            { label: "Readiness", value: String(payload.readiness_label ?? workspace.overview.readiness_label) },
            { label: "Include tests", value: payload.include_tests ? "Yes" : "No" },
          ]}
        />
      );
    case "Handoff Progress":
      return (
        <ProjectWidgetFacts
          rows={[
            { label: "Progress", value: `${String(payload.handoff_progress ?? workspace.overview.handoff_progress)}%` },
            { label: "Readiness", value: String(payload.readiness_label ?? workspace.overview.readiness_label) },
            { label: "Checklist items", value: Array.isArray(payload.checklist) ? String((payload.checklist as unknown[]).length) : "0" },
          ]}
        />
      );
    case "Parallelism Safety Meter":
      return (
        <ProjectWidgetFacts
          rows={[
            { label: "Safety score", value: `${String(payload.score ?? 0)}/100` },
            { label: "Active locks", value: String(payload.active_locks ?? 0) },
            { label: "Waiting locks", value: String(payload.waiting_locks ?? 0) },
            { label: "Path conflict risk", value: String(payload.path_conflict_risk ?? "Unknown") },
          ]}
        />
      );
    default:
      return <p className="section-footnote">This widget is live but still using a thin MVP renderer.</p>;
  }
}
