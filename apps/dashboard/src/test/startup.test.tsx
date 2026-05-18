import * as matchers from "@testing-library/jest-dom/matchers";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { SetupPage } from "../pages/SetupPage";
import { StartupErrorPage } from "../pages/StartupErrorPage";

expect.extend(matchers);


const startupStatusFirstTime = {
  mode: "first_time",
  first_run_completed: false,
  setup_version_completed: null,
  current_setup_version: "startup-v1",
  install_id: "install-1",
  startup_attempt: 1,
  max_startup_attempts: 3,
  overall_status: "ready",
  checks: [],
  recommended_route: "/setup",
  error_code: null,
  error_summary: null,
  diagnostic_report_path: null,
  degraded_reasons: [],
  failed_checks: [],
  startup_started_at: new Date().toISOString(),
  last_completed_at: new Date().toISOString(),
};

const startupStatusRegular = {
  ...startupStatusFirstTime,
  mode: "regular",
  first_run_completed: true,
  overall_status: "ready",
  recommended_route: "/dashboard",
};

const startupStatusError = {
  ...startupStatusFirstTime,
  mode: "error",
  overall_status: "error",
  recommended_route: "/startup-error",
  error_code: "MC-BOOT-002",
  error_summary: "Database init failed.",
  failed_checks: ["database"],
  checks: [
    {
      name: "database",
      required: true,
      status: "failed",
      summary: "Database init failed.",
      error_code: "MC-BOOT-002",
      details: {},
    },
  ],
};

const profile = {
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
  provider_endpoint: null,
  adapter_command: null,
  adapter_args_json: [],
  recent_startup_error_json: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  last_opened_at: new Date().toISOString(),
};

const systemStatus = {
  selected_provider: "codex",
  selected_provider_label: "Codex via ChatGPT Login",
  cli_detected: true,
  cli_version: "codex-cli 0.1",
  login_status: "Logged in using ChatGPT",
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
  provider_statuses: [
    {
      provider: "codex",
      label: "Codex via ChatGPT Login",
      cli_detected: true,
      cli_version: "codex-cli 0.1",
      authenticated: true,
      auth_mode: "chatgpt",
      auth_status_detectable: true,
      login_status: "Logged in using ChatGPT",
      supports_model_override: true,
      supports_reasoning_effort: true,
      supports_app_server: true,
      supports_builtin_auth: true,
      available_models: [],
      notes: [],
    },
    {
      provider: "ollama",
      label: "Ollama / Local Models",
      cli_detected: true,
      cli_version: "http://localhost:11434",
      authenticated: true,
      auth_mode: "local",
      auth_status_detectable: true,
      login_status: "Ollama endpoint reachable at http://localhost:11434.",
      supports_model_override: true,
      supports_reasoning_effort: true,
      supports_app_server: false,
      supports_builtin_auth: false,
      available_models: ["llama3.2:latest", "qwen2.5-coder:7b"],
      notes: [],
    },
  ],
  mcp_servers: [],
  configured_plugins: [],
  local_skills: [],
  current_auth_job: null,
  notes: [],
  startup_summary: startupStatusRegular,
  app_state_summary: profile,
};

const authState = {
  authenticated: true,
  auth_mode: "chatgpt",
  login_status: "Logged in using ChatGPT",
  cli_detected: true,
  provider: "codex",
  current_job: null,
  chatgpt_supported: true,
  device_auth_supported: true,
  api_key_supported: true,
  provider_statuses: [],
  notes: [],
};

const apiMock = vi.hoisted(() => ({
  getStartupStatus: vi.fn(),
  runStartupCheck: vi.fn(),
  retryStartup: vi.fn(),
  completeFirstRun: vi.fn(),
  runDiagnostics: vi.fn(),
  openDiagnosticsFolder: vi.fn(),
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  getAuthState: vi.fn(),
  loginWithChatGpt: vi.fn(),
  loginWithDeviceCode: vi.fn(),
  loginWithApiKey: vi.fn(),
  logoutCodex: vi.fn(),
  getSystemStatus: vi.fn(),
  listProjects: vi.fn(),
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
  apiMock.getProfile.mockResolvedValue(profile);
  apiMock.getAuthState.mockResolvedValue(authState);
  apiMock.getSystemStatus.mockResolvedValue(systemStatus);
  apiMock.listProjects.mockResolvedValue([]);
  apiMock.completeFirstRun.mockResolvedValue(profile);
  apiMock.runDiagnostics.mockResolvedValue({
    path: "/runtime/diagnostics/report.md",
    summary: "Generated",
    error_code: null,
    recommended_fixes: [],
  });
  apiMock.openDiagnosticsFolder.mockResolvedValue({ ok: true, path: "/runtime/diagnostics", message: "Opened" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("startup routing", () => {
  it("routes first-time startup into setup", async () => {
    apiMock.getStartupStatus.mockResolvedValue(startupStatusFirstTime);

    render(
      <MemoryRouter initialEntries={["/startup"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "First-time setup" })).toBeInTheDocument();
  });

  it("routes completed setup into dashboard", async () => {
    apiMock.getStartupStatus.mockResolvedValue(startupStatusRegular);

    render(
      <MemoryRouter initialEntries={["/startup"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });
});

describe("startup error page", () => {
  it("renders failed checks", async () => {
    apiMock.getStartupStatus.mockResolvedValue(startupStatusError);

    render(
      <MemoryRouter>
        <StartupErrorPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("MC-BOOT-002")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Failed checks" })).toBeInTheDocument();
    expect(screen.getByText("database: Database init failed.")).toBeInTheDocument();
  });
});

describe("setup wizard", () => {
  it("can complete with Codex login choice and skip connected accounts", async () => {
    render(
      <MemoryRouter>
        <SetupPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "First-time setup" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Username" })).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("What should the manager call you?"), { target: { value: "Morgan" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: /Codex via ChatGPT Login/i }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "I am signed in" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Skip for now" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: /Finish and open Dashboard/i }));

    await waitFor(() => expect(apiMock.completeFirstRun).toHaveBeenCalled());
    expect(apiMock.completeFirstRun.mock.calls[0][0]).toMatchObject({
      username: "Morgan",
      provider: "codex",
      auth_mode: "chatgpt",
    });
  });

  it("shows detected Ollama models in the setup model pickers", async () => {
    apiMock.getProfile.mockResolvedValue({
      ...profile,
      selected_provider: "ollama",
      provider_endpoint: "http://localhost:11434",
    });
    apiMock.getSystemStatus.mockResolvedValue({
      ...systemStatus,
      selected_provider: "ollama",
      selected_provider_label: "Ollama / Local Models",
      available_models: ["llama3.2:latest", "qwen2.5-coder:7b"],
    });

    render(
      <MemoryRouter>
        <SetupPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "First-time setup" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.change(screen.getByPlaceholderText("What should the manager call you?"), { target: { value: "Morgan" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: /Ollama \/ Local Models/i }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Skip for now" }));

    fireEvent.click(await screen.findByRole("button", { name: /browse manager model options/i }));
    expect(await screen.findByRole("button", { name: "llama3.2:latest" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "llama3.2:latest" }));
    expect(screen.getByDisplayValue("llama3.2:latest")).toBeInTheDocument();
  });
});
