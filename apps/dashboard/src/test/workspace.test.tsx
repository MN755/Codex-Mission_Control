import * as matchers from "@testing-library/jest-dom/matchers";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { ProjectWorkspacePage } from "../pages/ProjectWorkspacePage";

expect.extend(matchers);

const apiMock = vi.hoisted(() => ({
  apiBaseUrl: "http://127.0.0.1:8000",
  getProjectWorkspace: vi.fn(),
  getDashboardSummary: vi.fn(),
  getSystemStatus: vi.fn(),
  getProfile: vi.fn(),
  openProject: vi.fn(),
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
  updateProject: vi.fn(),
  createManagerMessage: vi.fn(),
  answerQuestion: vi.fn(),
  approveOnce: vi.fn(),
  denyApproval: vi.fn(),
  allowApprovalForProject: vi.fn(),
  updateWorkspaceWidgets: vi.fn(),
  updateSwarmPreferences: vi.fn(),
  createSwarmPlan: vi.fn(),
  approveSwarmPlan: vi.fn(),
  reviseSwarmPlan: vi.fn(),
  spawnSwarmAgents: vi.fn(),
  scaleSwarm: vi.fn(),
  generateManagerUpdate: vi.fn(),
  askManagerNext: vi.fn(),
  startProjectAgents: vi.fn(),
  startAgent: vi.fn(),
  pauseAgent: vi.fn(),
  stopAgent: vi.fn(),
  getAgentLogs: vi.fn(),
  addProjectWidget: vi.fn(),
  createChangeRequest: vi.fn(),
  updateWidgetInstance: vi.fn(),
  deleteWidgetInstance: vi.fn(),
  getWidgetInstanceData: vi.fn(),
  pinProject: vi.fn(),
  unpinProject: vi.fn(),
  pauseProject: vi.fn(),
  resumeProject: vi.fn(),
  archiveProject: vi.fn(),
  unarchiveProject: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: apiMock,
}));

vi.mock("../state/useProjectStream", () => ({
  useProjectStream: vi.fn(),
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

const baseWorkspace = {
  project: {
    id: 7,
    name: "Workspace Demo",
    slug: "workspace-demo",
    idea: "Demo",
    workspace_path: "/tmp/demo",
    status: "building",
    runner_mode: "dry_run",
    manager_mode: "auto",
    created_by: "Morgan",
    docs_path: "/tmp/demo/mission-control",
    final_report_json: null,
    pinned: true,
    archived_at: null,
    last_opened_at: new Date().toISOString(),
    latest_milestone: "Milestone 1",
    latest_activity: "Dry-run demo active.",
    handoff_status: "not_ready",
    display_status: "building",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  current_action: {
    id: "question-1",
    project_id: 7,
    type: "manager_question",
    severity: "warning",
    title: "Manager question: choose an option.",
    message: "Which slice should the manager validate first?",
    requesting_agent_id: 2,
    related_task_id: 4,
    command_id: null,
    tool_request_id: null,
    question_id: 1,
    created_at: new Date().toISOString(),
    expires_at: null,
    auto_decide_at: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
    resolved_at: null,
    actions_json: [],
  },
  action_history: [],
  manager_messages: [
    {
      id: 1,
      project_id: 7,
      role: "manager",
      message_type: "normal_update",
      content_markdown: "Dry-run demo active.",
      created_at: new Date().toISOString(),
      related_agent_id: null,
      related_task_id: null,
      actions_json: null,
      resolved_at: null,
      metadata_json: { simulated: true },
    },
  ],
  pending_question: {
    id: 1,
    project_id: 7,
    question: "Which slice should the manager validate first?",
    options_json: [
      { id: "ui", label: "UI shell", description: "Shell first." },
      { id: "workflow", label: "Workflow loop", description: "Loop first." },
    ],
    impact: "low",
    status: "pending",
    selected_option_id: null,
    selected_text: null,
    manager_recommendation: "Workflow loop",
    auto_decide_at: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
    created_at: new Date().toISOString(),
    resolved_at: null,
    related_task_id: 4,
    related_agent_id: 2,
    metadata_json: { simulated: true },
  },
  pending_approvals: [],
  agents: [
    {
      id: 2,
      project_id: 7,
      name: "Builder Agent A",
      role: "Primary implementation",
      kind: "worker",
      status: "working",
      current_task_id: 4,
      swarm_plan_id: 21,
      workspace_path: "/tmp/demo",
      archetype: "feature",
      mission: "Own the simulated vertical slice for the dry-run workspace.",
      retire_when: "Retire after the dry-run slice is validated.",
      session_ref: null,
      locked_paths_json: [],
      failure_count: 0,
      last_report_summary: "Dry-run demo seeded.",
      active_model: "Codex default",
      active_reasoning_effort: "Codex default",
      active_runner_type: "dry_run",
      current_action: "Preparing a simulated dry-run step",
      current_task_title: "Simulated vertical slice",
      display_status: "coding",
      runner_mode: "dry_run",
      needs_approval: false,
      last_update: new Date().toISOString(),
    },
  ],
  manager_queue: {
    next_up: [{ id: "task-4", type: "task", title: "Review the dry-run queue", status: "queued", related_task_id: 4, related_agent_id: 2, created_at: new Date().toISOString() }],
    waiting_on_user: [],
    recently_decided: [],
    deferred: [],
  },
  widgets: [],
  available_widgets: ["Milestones", "Path Locks", "Recent Decisions"],
  reservations: [],
  task_summary: { total: 1, by_status: { assigned: 1 } },
  milestone_summary: { items: [{ title: "Dry-run workspace demo", total: 1, done: 0 }] },
  workflow: {
    current_phase: "build",
    current_label: "Build",
    steps: [
      { id: "intake", label: "Intake", state: "complete", ordinal: 1 },
      { id: "interview", label: "Interview", state: "complete", ordinal: 2 },
      { id: "plan_review", label: "Plan Review", state: "complete", ordinal: 3 },
      { id: "build", label: "Build", state: "current", ordinal: 4 },
      { id: "validation", label: "Validation", state: "upcoming", ordinal: 5 },
      { id: "handoff", label: "Handoff", state: "upcoming", ordinal: 6 },
    ],
  },
  overview: {
    handoff_progress: 48,
    readiness_label: "In Progress",
    readiness_tone: "warning",
    checklist: [
      { id: "architecture", label: "Architecture", status: "complete", detail: "Plan approved." },
      { id: "frontend", label: "Frontend", status: "in_progress", detail: "UI shell underway." },
      { id: "backend", label: "Backend", status: "planned", detail: "No explicit backend task yet." },
    ],
  },
  tasks: [
    {
      id: 4,
      project_id: 7,
      assigned_agent_id: 2,
      title: "Simulated vertical slice",
      goal: "Demo the workspace loop",
      scope: "Workspace shell",
      agent_role: "Primary implementation",
      milestone: "Dry-run workspace demo",
      allowed_paths_json: [],
      forbidden_paths_json: [],
      validation_steps_json: [],
      success_criteria_json: [],
      estimated_complexity: "medium",
      dependencies_json: [],
      status: "working",
      failure_count: 0,
      waiting_reason: null,
      priority: 20,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ],
  activity_log: [
    {
      id: 101,
      event_type: "manager_message_created",
      created_at: new Date().toISOString(),
      summary: "Manager normal update",
      detail: "Dry-run demo active.",
      severity: "info",
      agent_id: null,
      agent_name: null,
      task_id: null,
    },
  ],
  degraded_notices: [],
  swarm_preferences: {
    project_id: 7,
    optimization_mode: "fastest_build",
    swarm_aggressiveness: "large",
    max_agents: 12,
    require_approval_above_agent_count: 10,
    allow_dynamic_spawning: true,
    allow_dynamic_retirement: true,
    docs_depth: "standard",
    testing_depth: "standard",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  swarm_plan: {
    id: 21,
    project_id: 7,
    milestone_id: 4,
    mode: "fastest_build",
    goal: "Get the first vertical slice working fast without letting agents trample the same paths.",
    recommended_agent_count: 11,
    max_agent_count: 12,
    coordination_risk: "high",
    path_conflict_risk: "medium",
    expected_bottlenecks_json: ["UI and backend slices can collide if path ownership gets sloppy."],
    validation_strategy_json: ["Smoke-test the first runnable slice before scaling further."],
    strategy_summary: "Use a fast vertical-slice swarm with strict path ownership and quick smoke validation.",
    approved_by_user: false,
    status: "pending_approval",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    approval_required: true,
    usage_warning: "Large swarm: expect higher coordination overhead and more provider/runtime intensity.",
    active_agent_count: 1,
    current_bottleneck: "UI and backend slices can collide if path ownership gets sloppy.",
    dynamic_spawning_enabled: true,
    dynamic_retirement_enabled: true,
    specs: [
      {
        id: 201,
        swarm_plan_id: 21,
        project_id: 7,
        archetype: "feature",
        name: "Vertical Slice Builder",
        mission: "Own the first usable end-to-end slice and keep it runnable early.",
        model_policy: "Prefer the default worker model with medium reasoning for fast iteration.",
        toolset_json: ["feature_work", "tests"],
        allowed_paths_json: ["src"],
        forbidden_paths_json: ["docs"],
        spawn_phase: "build_start",
        retire_when: "The first runnable vertical slice is merged and demoable.",
        priority: 10,
        status: "spawned",
      },
      {
        id: 202,
        swarm_plan_id: 21,
        project_id: 7,
        archetype: "test",
        name: "Smoke Test Runner",
        mission: "Validate the first slice once it is runnable.",
        model_policy: "Prefer a careful model when commands need explanation.",
        toolset_json: ["test_runner"],
        allowed_paths_json: ["tests"],
        forbidden_paths_json: [],
        spawn_phase: "after_first_slice",
        retire_when: "Smoke validation is recorded.",
        priority: 20,
        status: "deferred",
      },
    ],
  },
  swarm_events: [
    {
      id: 7001,
      project_id: 7,
      swarm_plan_id: 21,
      event_type: "swarm_plan_created",
      message: "Swarm plan created in fastest_build mode with 11 recommended worker agents.",
      agent_id: null,
      created_at: new Date().toISOString(),
      metadata_json: { mode: "fastest_build" },
    },
  ],
};

function widgetInstance(id: number, widgetType: string) {
  return {
    id,
    scope: "project" as const,
    project_id: 7,
    widget_type: widgetType,
    area: "project_right_sidebar" as const,
    order_index: 0,
    size: "medium" as const,
    collapsed: false,
    enabled: true,
    config_json: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function widgetData(id: number, widgetType: string, dataJson: Record<string, unknown>, status: "ready" | "warning" | "empty" = "ready", emptyState: string | null = null) {
  return {
    widget_instance_id: id,
    widget_type: widgetType,
    title: widgetType,
    status,
    data_json: dataJson,
    empty_state: emptyState,
    warnings_json: [],
    updated_at: new Date().toISOString(),
  };
}

beforeEach(() => {
  Object.values(apiMock).forEach((value) => {
    if (typeof value === "function" && "mockReset" in value) {
      value.mockReset();
    }
  });
  apiMock.getProjectWorkspace.mockResolvedValue(baseWorkspace);
  apiMock.getDashboardSummary.mockResolvedValue({
    sidebar_projects: [baseWorkspace.project],
    recent_projects: [baseWorkspace.project],
    archive_count: 0,
    active_builds: [],
    attention_items: [],
    blocked_agents: [],
    recent_handoffs: [],
    runner_status: {},
    connected_accounts: {},
    model_defaults: {},
    widgets: [],
    available_widgets: [],
  });
  apiMock.getSystemStatus.mockResolvedValue({
    startup_summary: { overall_status: "ready" },
    authenticated: false,
    selected_provider: "codex",
  });
  apiMock.getProfile.mockResolvedValue({
    display_name: "Alex Vega",
    selected_provider: "codex",
  });
  apiMock.openProject.mockResolvedValue(baseWorkspace.project);
  apiMock.getSettings.mockResolvedValue({
    project_id: 7,
    provider: "codex",
    manager_model: null,
    default_worker_model: null,
    manager_reasoning_effort: null,
    default_worker_reasoning_effort: null,
    per_role_model_overrides_json: {},
    per_role_reasoning_overrides_json: {},
    provider_endpoint: null,
    adapter_command: null,
    adapter_args_json: [],
    runner_mode: "dry_run",
    sandbox_mode: "workspace-write",
    approval_policy: "on-request",
    workspace_widgets_json: [],
    approval_overrides_json: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
  apiMock.updateSettings.mockResolvedValue(null);
  apiMock.updateProject.mockResolvedValue({ ...baseWorkspace.project, name: "Workspace Demo Refined", slug: "workspace-demo-refined", idea: "Refined idea" });
  apiMock.createManagerMessage.mockResolvedValue(baseWorkspace.manager_messages[0]);
  apiMock.answerQuestion.mockResolvedValue(baseWorkspace.pending_question);
  apiMock.approveOnce.mockResolvedValue(null);
  apiMock.denyApproval.mockResolvedValue(null);
  apiMock.allowApprovalForProject.mockResolvedValue(null);
  apiMock.updateWorkspaceWidgets.mockResolvedValue(null);
  apiMock.updateSwarmPreferences.mockResolvedValue(baseWorkspace.swarm_preferences);
  apiMock.createSwarmPlan.mockResolvedValue(baseWorkspace.swarm_plan);
  apiMock.approveSwarmPlan.mockResolvedValue({ ...baseWorkspace.swarm_plan, approved_by_user: true, status: "approved" });
  apiMock.reviseSwarmPlan.mockResolvedValue({ ...baseWorkspace.swarm_plan, strategy_summary: "Revised swarm strategy." });
  apiMock.spawnSwarmAgents.mockResolvedValue({
    ok: true,
    message: "Swarm sync complete",
    swarm_plan: { ...baseWorkspace.swarm_plan, approved_by_user: true, status: "active" },
    agents_spawned: 2,
    agents_retired: 0,
  });
  apiMock.scaleSwarm.mockResolvedValue({
    ok: true,
    message: "Swarm scaled",
    swarm_plan: { ...baseWorkspace.swarm_plan, approved_by_user: true, status: "active" },
    agents_spawned: 1,
    agents_retired: 0,
  });
  apiMock.generateManagerUpdate.mockResolvedValue(baseWorkspace.manager_messages[0]);
  apiMock.askManagerNext.mockResolvedValue(baseWorkspace.manager_messages[0]);
  apiMock.startProjectAgents.mockResolvedValue(null);
  apiMock.startAgent.mockResolvedValue(null);
  apiMock.pauseAgent.mockResolvedValue(null);
  apiMock.stopAgent.mockResolvedValue(null);
  apiMock.getAgentLogs.mockResolvedValue({ agent_id: 2, logs_path: "/tmp/demo/log.txt", content: "latest log line" });
  apiMock.addProjectWidget.mockResolvedValue({
    id: 71,
    scope: "project",
    project_id: 7,
    widget_type: "Repo Intelligence",
    area: "project_right_sidebar",
    order_index: 9,
    size: "medium",
    collapsed: false,
    enabled: true,
    config_json: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
  apiMock.createChangeRequest.mockResolvedValue({
    id: 901,
    project_id: 7,
    request_text: "Add an explicit change request flow",
    classification: "needs_triage",
    impact_estimate: "unknown",
    status: "new",
    related_tasks_json: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
  apiMock.updateWidgetInstance.mockResolvedValue(null);
  apiMock.deleteWidgetInstance.mockResolvedValue(null);
  apiMock.getWidgetInstanceData.mockResolvedValue(null);
  apiMock.pinProject.mockResolvedValue(baseWorkspace.project);
  apiMock.unpinProject.mockResolvedValue({ ...baseWorkspace.project, pinned: false });
  apiMock.pauseProject.mockResolvedValue({ ...baseWorkspace.project, status: "paused" });
  apiMock.resumeProject.mockResolvedValue(baseWorkspace.project);
  apiMock.archiveProject.mockResolvedValue({ ...baseWorkspace.project, archived_at: new Date().toISOString() });
  apiMock.unarchiveProject.mockResolvedValue(baseWorkspace.project);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("project workspace", () => {
  it("renders the action banner and exact empty widget text", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Manager question: choose an option.")).toBeInTheDocument();
    expect(screen.getByText("Select the plus symbol in the bottom-right corner to add customizable widgets!")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Workspace Demo" })).toBeInTheDocument();
    expect(screen.getByText("Task Board")).toBeInTheDocument();
  });

  it("answers a pending manager question", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Workflow loop/i }));

    await waitFor(() => {
      expect(apiMock.answerQuestion).toHaveBeenCalledWith(1, {
        project_id: 7,
        option_id: "workflow",
        selected_text: "Workflow loop",
      });
    });
  });

  it("resolves a pending approval card", async () => {
    apiMock.getProjectWorkspace.mockResolvedValue({
      ...baseWorkspace,
      pending_question: null,
      current_action: {
        ...baseWorkspace.current_action,
        id: "approval-11",
        type: "command_approval",
        title: "Action needed: approve command approval.",
        message: "The validation agent needs one simulated approval.",
      },
      pending_approvals: [
        {
          id: 11,
          project_id: 7,
          request_type: "command",
          requesting_agent_id: 2,
          task_id: 4,
          title: "Install the local validation package",
          reason_short: "The validation agent wants to run a simulated dependency install.",
          risk_level: "medium",
          status: "pending",
          cwd: "/tmp/demo",
          request_payload_json: { command: "python -m pip install simulated-package" },
          runner_ref: null,
          resolved_by: null,
          created_at: new Date().toISOString(),
          resolved_at: null,
        },
      ],
      activity_log: [
        ...baseWorkspace.activity_log,
        {
          id: 102,
          event_type: "approval_created",
          created_at: new Date().toISOString(),
          summary: "Approval requested: Install the local validation package",
          detail: "The validation agent wants to run a simulated dependency install.",
          severity: "warning",
          agent_id: 2,
          agent_name: "Builder Agent A",
          task_id: 4,
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Approve once" }));
    await waitFor(() => expect(apiMock.approveOnce).toHaveBeenCalledWith(11, 7));
  });

  it("corrects a slug mismatch", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/wrong-slug"]}>
        <LocationProbe />
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/projects/7/workspace-demo"));
  });

  it("shows a not-found state when the project is missing", async () => {
    apiMock.getProjectWorkspace.mockRejectedValue(new Error("Project not found"));

    render(
      <MemoryRouter initialEntries={["/projects/999"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Missing project" })).toBeInTheDocument();
  });

  it("renders the queue and activity log panels", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Manager Queue")).toBeInTheDocument();
    expect(screen.getByText("Review the dry-run queue")).toBeInTheDocument();
    expect(screen.getByText("Activity Log")).toBeInTheDocument();
    expect(screen.getByText("Manager normal update")).toBeInTheDocument();
  });

  it("renders the swarm strategy panel with a large-swarm warning", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Swarm Strategy")).toBeInTheDocument();
    expect(screen.getByText("Use a fast vertical-slice swarm with strict path ownership and quick smoke validation.")).toBeInTheDocument();
    expect(screen.getByText("Large swarm: expect higher coordination overhead and more provider/runtime intensity.")).toBeInTheDocument();
    expect(screen.getAllByText("Feature").length).toBeGreaterThan(0);
    expect(screen.getByText("Own the simulated vertical slice for the dry-run workspace.")).toBeInTheDocument();
  });

  it("removes a project widget through the widget settings menu", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click((await screen.findAllByLabelText("Widget settings"))[0]);
    fireEvent.click((await screen.findAllByRole("button", { name: "Remove widget" }))[0]);

    await waitFor(() => {
      expect(apiMock.deleteWidgetInstance).toHaveBeenCalled();
    });
  });

  it("opens the full queue drawer", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "View full queue" }));

    expect(await screen.findByRole("dialog", { name: "Full Manager Queue" })).toBeInTheDocument();
    expect(screen.getByText("The manager's routing picture without making you reverse-engineer it from scattered panels.")).toBeInTheDocument();
  });

  it("opens the swarm plan drawer", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click((await screen.findAllByRole("button", { name: "View Swarm Plan" }))[0]);

    expect(await screen.findByRole("dialog", { name: "Swarm Plan" })).toBeInTheDocument();
    expect(screen.getByText("Vertical Slice Builder")).toBeInTheDocument();
    expect(screen.getByText("Smoke Test Runner")).toBeInTheDocument();
  });

  it("saves project metadata from the settings drawer", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Project Settings" }));
    expect(await screen.findByDisplayValue("Dry Run")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Fastest Build")).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue("Workspace Demo"), { target: { value: "Workspace Demo Refined" } });
    fireEvent.change(screen.getByDisplayValue("Demo"), { target: { value: "Refined idea" } });
    fireEvent.change(screen.getByDisplayValue("12"), { target: { value: "9" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(apiMock.updateProject).toHaveBeenCalledWith(7, { name: "Workspace Demo Refined", idea: "Refined idea" });
      expect(apiMock.updateSettings).toHaveBeenCalled();
      expect(apiMock.updateSwarmPreferences).toHaveBeenCalledWith(7, expect.objectContaining({ max_agents: 9 }));
    });
  });

  it("opens the share export drawer", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));

    expect(await screen.findByRole("dialog", { name: "Share / Export" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy project summary" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Copy queue snapshot/i })).toBeInTheDocument();
  });

  it("opens the full agent inspector and loads agent logs", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "View all agents" }));
    expect(await screen.findByRole("dialog", { name: "All Agents" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View logs" }));

    await waitFor(() => {
      expect(apiMock.getAgentLogs).toHaveBeenCalledWith(7, 2);
    });
    expect(await screen.findByText("latest log line")).toBeInTheDocument();
  });

  it("creates a change request from the widget drawer and asks the manager to classify it", async () => {
    apiMock.createChangeRequest.mockResolvedValueOnce({
      id: 902,
      project_id: 7,
      request_text: "Add a manager-owned change request triage step",
      classification: "needs_triage",
      impact_estimate: "unknown",
      status: "new",
      related_tasks_json: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    apiMock.getProjectWorkspace.mockResolvedValue({
      ...baseWorkspace,
      widgets: ["Change Request Mode"],
      widget_instances: [widgetInstance(801, "Change Request Mode")],
      widget_data: [
        widgetData(
          801,
          "Change Request Mode",
          {},
          "empty",
          "No change requests have been logged for this project yet.",
        ),
      ],
    });

    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "New change request" }));
    expect(await screen.findByRole("dialog", { name: "New Change Request" })).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Describe the requested change, why it matters, and anything the Manager should preserve."), {
      target: { value: "Add a manager-owned change request triage step" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save and ask Manager" }));

    await waitFor(() => {
      expect(apiMock.createChangeRequest).toHaveBeenCalledWith(7, {
        request_text: "Add a manager-owned change request triage step",
      });
      expect(apiMock.createManagerMessage).toHaveBeenCalledWith(
        7,
        expect.stringContaining('Add a manager-owned change request triage step'),
      );
    });
  });

  it("routes an assumption revisit request through the manager from the widget", async () => {
    apiMock.getProjectWorkspace.mockResolvedValue({
      ...baseWorkspace,
      widgets: ["Manager Assumptions"],
      widget_instances: [widgetInstance(802, "Manager Assumptions")],
      widget_data: [
        widgetData(802, "Manager Assumptions", {
          items: [
            {
              assumption: "Avoid paid hosted infrastructure for the first milestone",
              reason: "The project is supposed to stay local-first unless the user says otherwise.",
              confidence: 0.72,
              status: "active",
            },
          ],
        }),
      ],
    });

    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Ask Manager to revisit" }));

    await waitFor(() => {
      expect(apiMock.createManagerMessage).toHaveBeenCalledWith(
        7,
        expect.stringContaining("Avoid paid hosted infrastructure for the first milestone"),
      );
    });
  });

  it("pauses dynamic spawning from the swarm budget widget", async () => {
    apiMock.getProjectWorkspace.mockResolvedValue({
      ...baseWorkspace,
      widgets: ["Swarm Budget"],
      widget_instances: [widgetInstance(803, "Swarm Budget")],
      widget_data: [
        widgetData(803, "Swarm Budget", {
          active_agents: 1,
          max_agents: 12,
          intensity: "medium",
          dynamic_spawning_paused: false,
          approval_threshold: 10,
        }),
      ],
    });

    render(
      <MemoryRouter initialEntries={["/projects/7/workspace-demo"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug?" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Pause dynamic spawning" }));

    await waitFor(() => {
      expect(apiMock.updateSwarmPreferences).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ allow_dynamic_spawning: false }),
      );
    });
  });
});
