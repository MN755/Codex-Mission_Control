import * as matchers from "@testing-library/jest-dom/matchers";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ArchivePage } from "../pages/ArchivePage";
import { DashboardPage } from "../pages/DashboardPage";
import { DiagnosticsPage } from "../pages/DiagnosticsPage";
import { HandoffsPage } from "../pages/HandoffsPage";
import { ModelsRunnersPage } from "../pages/ModelsRunnersPage";
import { SettingsPage } from "../pages/SettingsPage";
import { SkillsToolsPage } from "../pages/SkillsToolsPage";

expect.extend(matchers);

const baseProfile = {
  id: 1,
  install_id: "install-1",
  display_name: "Morgan",
  preferred_provider_choice: "codex",
  preferred_start_mode: "new_project",
  selected_provider: "codex",
  auth_mode: "chatgpt",
  connected_accounts_json: {},
  first_run_completed: true,
  setup_version_completed: "startup-v1",
  onboarding_completed: true,
  default_runner_mode: "auto",
  manager_model: null,
  default_worker_model: null,
  manager_reasoning_effort: null,
  default_worker_reasoning_effort: null,
  sandbox_mode: "workspace-write",
  approval_policy: "on-request",
  theme: "system",
  startup_behavior: "dashboard",
  notification_preferences_json: { desktop_toasts: false, sound: false, action_required_only: true },
  dashboard_widgets_json: [],
  dashboard_widget_preferences_json: {},
  tool_permission_overrides_json: {},
  provider_endpoint: null,
  adapter_command: null,
  adapter_args_json: [],
  recent_startup_error_json: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  last_opened_at: new Date().toISOString(),
};

const baseStatus = {
  selected_provider: "codex",
  selected_provider_label: "Codex via ChatGPT Login",
  cli_detected: true,
  cli_version: "codex-cli",
  login_status: "Logged in",
  auth_mode: "chatgpt",
  authenticated: true,
  app_server_supported: true,
  app_server_handshake_status: "available",
  app_server_transport: "stdio_jsonrpc",
  effective_runner_mode: "auto",
  dry_run_available: true,
  runtime_directory: "/runtime",
  diagnostics_directory: "/runtime/diagnostics",
  backend_port: 8000,
  frontend_port: 5173,
  active_runs: [],
  current_settings_summary: null,
  selected_manager_model: null,
  selected_default_worker_model: null,
  available_models: [],
  provider_statuses: [],
  mcp_servers: [],
  configured_plugins: [],
  local_skills: ["mission-control-manager"],
  current_auth_job: null,
  notes: [],
  startup_summary: {
    mode: "regular",
    first_run_completed: true,
    setup_version_completed: "startup-v1",
    current_setup_version: "startup-v1",
    install_id: "install-1",
    startup_attempt: 1,
    max_startup_attempts: 3,
    overall_status: "ready",
    checks: [{ name: "runtime_paths", required: true, status: "passed", summary: "ok", error_code: null, details: {} }],
    recommended_route: "/dashboard",
    error_code: null,
    error_summary: null,
    diagnostic_report_path: null,
    degraded_reasons: [],
    failed_checks: [],
    startup_started_at: new Date().toISOString(),
    last_completed_at: new Date().toISOString(),
  },
  app_state_summary: baseProfile,
};

const baseSummary = {
  sidebar_projects: [
    {
      id: 7,
      name: "Alpha",
      slug: "alpha",
      idea: "Idea",
      workspace_path: "/tmp/alpha",
      status: "building",
      runner_mode: "dry_run",
      manager_mode: "auto",
      created_by: "Morgan",
      docs_path: "/tmp/alpha/docs",
      final_report_json: null,
      pinned: true,
      archived_at: null,
      last_opened_at: new Date().toISOString(),
      latest_milestone: "Milestone A",
      latest_activity: "Latest update",
      handoff_status: "not_ready",
      display_status: "building",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ],
  recent_projects: [
    {
      id: 7,
      name: "Alpha",
      slug: "alpha",
      idea: "Idea",
      workspace_path: "/tmp/alpha",
      status: "building",
      runner_mode: "dry_run",
      manager_mode: "auto",
      created_by: "Morgan",
      docs_path: "/tmp/alpha/docs",
      final_report_json: null,
      pinned: true,
      archived_at: null,
      last_opened_at: new Date().toISOString(),
      latest_milestone: "Milestone A",
      latest_activity: "Latest update",
      handoff_status: "not_ready",
      display_status: "building",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ],
  archive_count: 1,
  active_builds: [
    {
      project_id: 7,
      project_name: "Alpha",
      project_slug: "alpha",
      task_id: 3,
      task_title: "Implement auth middleware",
      stage: "Building",
      agent_name: "Builder",
      runner_type: "dry_run",
      updated_at: new Date().toISOString(),
    },
  ],
  attention_items: [
    {
      id: "7:approval-1",
      project_id: 7,
      project_name: "Alpha",
      project_slug: "alpha",
      kind: "command_approval",
      summary: "Action needed: approve command.",
      detail: "Approve a workspace command before the build can continue.",
      severity: "warning",
      target: "/projects/7/alpha",
      created_at: new Date().toISOString(),
    },
  ],
  blocked_agents: [],
  recent_handoffs: [],
  runner_status: { effective_runner_mode: "auto", app_server_handshake_status: "available" },
  connected_accounts: {},
  model_defaults: { manager_model: null },
  widgets: ["Needs Attention", "Active Builds", "Recent Handoffs", "Runner & Provider Status"],
  available_widgets: ["Needs Attention", "Active Builds", "Recent Handoffs", "Runner & Provider Status", "Connected Accounts"],
};

const apiMock = vi.hoisted(() => ({
  getDashboardSummary: vi.fn(),
  getSystemStatus: vi.fn(),
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  listProjects: vi.fn(),
  archiveProject: vi.fn(),
  unarchiveProject: vi.fn(),
  pinProject: vi.fn(),
  unpinProject: vi.fn(),
  listDiagnosticReports: vi.fn(),
  getStartupStatus: vi.fn(),
  runDiagnostics: vi.fn(),
  openDiagnosticsFolder: vi.fn(),
  retryStartup: vi.fn(),
  getTools: vi.fn(),
  getSkills: vi.fn(),
  updateToolPermission: vi.fn(),
  listHandoffs: vi.fn(),
  getProject: vi.fn(),
  getAgents: vi.fn(),
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
  addDashboardWidget: vi.fn(),
  updateWidgetInstance: vi.fn(),
  deleteWidgetInstance: vi.fn(),
  getWidgetInstanceData: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: apiMock,
}));

beforeEach(() => {
  Object.values(apiMock).forEach((value) => {
    if (typeof value === "function" && "mockReset" in value) {
      value.mockReset();
    }
  });
  apiMock.getDashboardSummary.mockResolvedValue(baseSummary);
  apiMock.getSystemStatus.mockResolvedValue(baseStatus);
  apiMock.getProfile.mockResolvedValue(baseProfile);
  apiMock.updateProfile.mockResolvedValue(baseProfile);
  apiMock.listProjects.mockResolvedValue([
    ...baseSummary.recent_projects,
    {
      ...baseSummary.recent_projects[0],
      id: 12,
      name: "Archived Project",
      slug: "archived-project",
      archived_at: new Date().toISOString(),
      display_status: "archived",
    },
  ]);
  apiMock.archiveProject.mockResolvedValue(null);
  apiMock.unarchiveProject.mockResolvedValue(null);
  apiMock.pinProject.mockResolvedValue(null);
  apiMock.unpinProject.mockResolvedValue(null);
  apiMock.listDiagnosticReports.mockResolvedValue([
    {
      path: "/runtime/diagnostics/diagnostic-1.md",
      json_path: "/runtime/diagnostics/diagnostic-1.json",
      created_at: new Date().toISOString(),
      error_code: "MC-BOOT-006",
      summary: "Codex CLI missing.",
    },
  ]);
  apiMock.getStartupStatus.mockResolvedValue(baseStatus.startup_summary);
  apiMock.runDiagnostics.mockResolvedValue({
    path: "/runtime/diagnostics/diagnostic-2.md",
    summary: "Generated.",
    error_code: null,
    recommended_fixes: [],
  });
  apiMock.openDiagnosticsFolder.mockResolvedValue({ ok: true, path: "/runtime/diagnostics", message: "Opened diagnostics folder." });
  apiMock.retryStartup.mockResolvedValue(baseStatus.startup_summary);
  apiMock.getTools.mockResolvedValue([
    {
      id: "file-search",
      name: "File Search",
      category: "Core tools",
      summary: "Search files.",
      availability: "available",
      permission_policy: "ask_once_per_project",
      risk_level: "low",
      notes: [],
    },
  ]);
  apiMock.getSkills.mockResolvedValue([{ name: "mission-control-manager", source: "local_codex", available: true, summary: "Skill summary." }]);
  apiMock.updateToolPermission.mockResolvedValue({ tool_id: "file-search", permission_policy: "allow_for_project" });
  apiMock.listHandoffs.mockResolvedValue([
    {
      project_id: 7,
      project_name: "Alpha",
      project_slug: "alpha",
      created_at: new Date().toISOString(),
      status: "ready",
      summary: "Handoff summary",
      artifacts_path: "/tmp/alpha/docs",
      tests_count: 2,
      run_instructions: ["npm run dev"],
      known_limitations: ["Local only"],
    },
  ]);
  apiMock.getProject.mockResolvedValue(baseSummary.recent_projects[0]);
  apiMock.getAgents.mockResolvedValue([]);
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
    runner_mode: "auto",
    sandbox_mode: "workspace-write",
    approval_policy: "on-request",
    workspace_widgets_json: [],
    approval_overrides_json: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
  apiMock.updateSettings.mockResolvedValue({
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
    runner_mode: "auto",
    sandbox_mode: "workspace-write",
    approval_policy: "on-request",
    workspace_widgets_json: [],
    approval_overrides_json: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
  apiMock.addDashboardWidget.mockResolvedValue({
    id: 42,
    scope: "dashboard",
    project_id: null,
    widget_type: "Connected Accounts",
    area: "dashboard_bottom",
    order_index: 4,
    size: "medium",
    collapsed: false,
    enabled: true,
    config_json: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
  apiMock.updateWidgetInstance.mockResolvedValue(null);
  apiMock.deleteWidgetInstance.mockResolvedValue(null);
  apiMock.getWidgetInstanceData.mockResolvedValue(null);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("command center pages", () => {
  it("renders dashboard recent projects and opens the widget selector", async () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Recent Projects")).toBeInTheDocument();
    expect(screen.getByText("System Health")).toBeInTheDocument();
    expect(screen.getByText("Needs Attention")).toBeInTheDocument();
    expect(screen.getByText("Runner & Provider Status")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add widget" }));
    expect(await screen.findByText("Widget Selector")).toBeInTheDocument();
  });

  it("adds a dashboard widget from the selector", async () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Add widget" }));
    const selectorCards = await screen.findAllByText("Connected Accounts");
    const card = selectorCards.find((entry) => entry.closest(".widget-selector-card")) ?? null;
    const widgetCard = card?.closest(".widget-selector-card") ?? null;
    expect(widgetCard).not.toBeNull();
    fireEvent.click(within(widgetCard as HTMLElement).getByRole("button", { name: "Add widget" }));

    await waitFor(() => {
      expect(apiMock.addDashboardWidget).toHaveBeenCalledWith({ widget_type: "Connected Accounts" });
    });
  });

  it("keeps the dashboard usable when a secondary home request fails", async () => {
    apiMock.getSystemStatus.mockRejectedValueOnce(new Error("Failed to fetch"));
    apiMock.getSystemStatus.mockRejectedValueOnce(new Error("Failed to fetch"));

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Recent Projects")).toBeInTheDocument();
    expect(screen.getByText("Home data partially degraded")).toBeInTheDocument();
  });

  it("renders the exact empty widget message when no dashboard widgets are selected", async () => {
    apiMock.getDashboardSummary.mockResolvedValueOnce({
      ...baseSummary,
      widgets: [],
    });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Select the plus symbol in the bottom-right corner to add customizable widgets!")).toBeInTheDocument();
  });

  it("renders archived projects on the archive page", async () => {
    render(
      <MemoryRouter initialEntries={["/archive"]}>
        <Routes>
          <Route path="/archive" element={<ArchivePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Archived Project")).toBeInTheDocument();
  });

  it("renders the app settings page", async () => {
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByDisplayValue("Morgan")).toBeInTheDocument();
  });

  it("renders the project models and runners page", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/alpha/models-runners"]}>
        <Routes>
          <Route path="/projects/:projectId/:projectSlug/models-runners" element={<ModelsRunnersPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Provider and models")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Use provider default for manager")).toBeInTheDocument();
  });

  it("renders diagnostics, tools, and handoffs pages", async () => {
    render(
      <MemoryRouter initialEntries={["/diagnostics"]}>
        <Routes>
          <Route path="/diagnostics" element={<DiagnosticsPage />} />
          <Route path="/skills-tools" element={<SkillsToolsPage />} />
          <Route path="/handoffs" element={<HandoffsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Saved reports")).toBeInTheDocument();

    cleanup();

    render(
      <MemoryRouter initialEntries={["/skills-tools"]}>
        <Routes>
          <Route path="/skills-tools" element={<SkillsToolsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("File Search")).toBeInTheDocument();

    cleanup();

    render(
      <MemoryRouter initialEntries={["/handoffs"]}>
        <Routes>
          <Route path="/handoffs" element={<HandoffsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("Handoff summary")).toBeInTheDocument();
  });
});
