import * as matchers from "@testing-library/jest-dom/matchers";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { PlanReviewPage } from "../pages/PlanReviewPage";

expect.extend(matchers);

const apiMock = vi.hoisted(() => ({
  getProject: vi.fn(),
  getPlan: vi.fn(),
  getSwarmPlan: vi.fn(),
  createSwarmPlan: vi.fn(),
  approveSwarmPlan: vi.fn(),
  reviseSwarmPlan: vi.fn(),
  approvePlan: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: apiMock,
}));

const project = {
  id: 7,
  name: "Workspace Demo",
  slug: "workspace-demo",
  idea: "Demo",
  workspace_path: "/tmp/demo",
  status: "plan_ready",
  runner_mode: "dry_run",
  manager_mode: "auto",
  created_by: "Morgan",
  docs_path: "/tmp/demo/mission-control",
  final_report_json: null,
  pinned: true,
  archived_at: null,
  last_opened_at: new Date().toISOString(),
  latest_milestone: "Milestone 1",
  latest_activity: "Plan ready.",
  handoff_status: "not_ready",
  display_status: "planning",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const plan = {
  id: 4,
  project_id: 7,
  version: 1,
  content_markdown: "# Plan\n\nBuild the workspace shell first.",
  status: "pending_approval",
  summary_json: {
    task_breakdown: [
      { title: "Build workspace shell", agent_role: "Frontend specialist", milestone: "Milestone 1", goal: "Render the shell." },
    ],
  },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const swarmPlan = {
  id: 21,
  project_id: 7,
  milestone_id: 4,
  mode: "documentation_heavy",
  goal: "Create a docs-heavy swarm preview.",
  recommended_agent_count: 6,
  max_agent_count: 8,
  coordination_risk: "medium",
  path_conflict_risk: "low",
  expected_bottlenecks_json: ["Docs quality depends on the product path staying stable."],
  validation_strategy_json: ["Review docs against the real product behavior before handoff."],
  strategy_summary: "Split docs into audience-specific lanes while keeping one builder focused on the core product path.",
  approved_by_user: false,
  status: "pending_approval",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  approval_required: false,
  usage_warning: null,
  active_agent_count: 0,
  current_bottleneck: "Docs quality depends on the product path staying stable.",
  dynamic_spawning_enabled: true,
  dynamic_retirement_enabled: true,
  specs: [
    {
      id: 201,
      swarm_plan_id: 21,
      project_id: 7,
      archetype: "docs",
      name: "README Writer",
      mission: "Own the quick-start README.",
      model_policy: "Prefer concise docs writing.",
      toolset_json: ["docs_editing"],
      allowed_paths_json: ["README.md"],
      forbidden_paths_json: ["src"],
      spawn_phase: "build_start",
      retire_when: "README is accurate.",
      priority: 10,
      status: "planned",
    },
    {
      id: 202,
      swarm_plan_id: 21,
      project_id: 7,
      archetype: "docs",
      name: "API Docs Writer",
      mission: "Document the API after backend behavior stabilizes.",
      model_policy: "Prefer reference-friendly docs writing.",
      toolset_json: ["docs_editing"],
      allowed_paths_json: ["docs"],
      forbidden_paths_json: ["src"],
      spawn_phase: "after_backend_stabilizes",
      retire_when: "API docs reflect current behavior.",
      priority: 20,
      status: "deferred",
    },
  ],
};

beforeEach(() => {
  Object.values(apiMock).forEach((value) => {
    if (typeof value === "function" && "mockReset" in value) {
      value.mockReset();
    }
  });
  apiMock.getProject.mockResolvedValue(project);
  apiMock.getPlan.mockResolvedValue(plan);
  apiMock.getSwarmPlan.mockResolvedValue(swarmPlan);
  apiMock.createSwarmPlan.mockResolvedValue(swarmPlan);
  apiMock.approveSwarmPlan.mockResolvedValue({ ...swarmPlan, approved_by_user: true, status: "approved" });
  apiMock.reviseSwarmPlan.mockResolvedValue({ ...swarmPlan, strategy_summary: "Revised docs-heavy swarm strategy." });
  apiMock.approvePlan.mockResolvedValue(plan);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("plan review swarm preview", () => {
  it("renders the swarm preview with roster and bottlenecks", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/plan"]}>
        <Routes>
          <Route path="/projects/:projectId/plan" element={<PlanReviewPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Swarm Plan Preview")).toBeInTheDocument();
    expect(screen.getByText("README Writer")).toBeInTheDocument();
    expect(screen.getByText("API Docs Writer")).toBeInTheDocument();
    expect(screen.getByText("Docs quality depends on the product path staying stable.")).toBeInTheDocument();
  });

  it("approves the swarm plan from plan review", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/plan"]}>
        <Routes>
          <Route path="/projects/:projectId/plan" element={<PlanReviewPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Approve Swarm Plan" }));

    await waitFor(() => {
      expect(apiMock.approveSwarmPlan).toHaveBeenCalledWith(7, 21);
    });
  });

  it("generates a swarm preview when none exists yet", async () => {
    apiMock.getSwarmPlan.mockResolvedValueOnce(null);

    render(
      <MemoryRouter initialEntries={["/projects/7/plan"]}>
        <Routes>
          <Route path="/projects/:projectId/plan" element={<PlanReviewPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(apiMock.createSwarmPlan).toHaveBeenCalledWith(7, {
        goal: "Prepare the worker swarm strategy for the approved plan for Workspace Demo.",
        milestone_id: 4,
      });
    });
  });
});
