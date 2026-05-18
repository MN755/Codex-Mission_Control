import * as matchers from "@testing-library/jest-dom/matchers";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { InterviewPage } from "../pages/InterviewPage";

expect.extend(matchers);

const apiMock = vi.hoisted(() => ({
  getProject: vi.fn(),
  getInterview: vi.fn(),
  getProjectUnderstanding: vi.fn(),
  startInterview: vi.fn(),
  answerInterviewQuestion: vi.fn(),
  generateNextInterview: vi.fn(),
  finishInterview: vi.fn(),
  generatePlan: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: apiMock,
}));

const baseProject = {
  id: 5,
  name: "Adaptive Interview Demo",
  slug: "adaptive-interview-demo",
  idea: "Build a project command center.",
  workspace_path: "/tmp/adaptive-interview-demo",
  status: "interview_in_progress",
  runner_mode: "dry_run",
  manager_mode: "auto",
  created_by: "Morgan",
  docs_path: "/tmp/adaptive-interview-demo/mission-control",
  final_report_json: null,
  pinned: true,
  archived_at: null,
  last_opened_at: new Date().toISOString(),
  latest_milestone: null,
  latest_activity: "Interview active.",
  handoff_status: null,
  display_status: "planning",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const baseUnderstanding = {
  project_id: 5,
  summary: "The manager is still collecting the highest-impact requirements.",
  known_facts_json: {},
  unknowns_json: { priority: ["Target users still unclear."] },
  assumptions_json: [],
  constraints_json: ["Local-first"],
  confidence_by_category_json: { "product goal": 0.45 },
  updated_at: new Date().toISOString(),
};

function buildSession(overrides: Record<string, unknown> = {}) {
  return {
    id: 10,
    project_id: 5,
    question_budget: 20,
    questions_asked: 1,
    questions_remaining: 19,
    manager_mode: "auto",
    stopped_early: false,
    stop_reason: null,
    confidence: { "target users": 0.55 },
    understanding_summary: "The manager needs to narrow the target users and scope posture.",
    known_facts: { project: [{ label: "Title", value: "Adaptive Interview Demo" }] },
    unknowns: { priority: ["Target users still unclear."] },
    assumptions: [],
    constraints: ["Local-first"],
    generation_sources: ["manager_ai"],
    question_count: 20,
    current_index: 0,
    status: "in_progress",
    questions: [
      {
        id: 42,
        project_id: 5,
        index: 0,
        question: "Who should the first version optimize for?",
        why: "The manager needs to shape UX and docs around the real user.",
        category: "target users",
        impact: "high",
        options: [
          { id: "solo", label: "Solo operator", description: "Optimize for one builder." },
          { id: "team", label: "Small team", description: "Optimize for a small internal team." },
          { id: "recommend", label: "Not sure, recommend one", description: "Let the manager choose." },
        ],
        allow_custom_answer: true,
        selected_option_id: null,
        selected_text: null,
        custom_answer: null,
        affects: ["docs", "user journey"],
        status: "pending",
        question_source: "manager_ai",
        answered_at: null,
        rationale: null,
        selected_option: null,
      },
    ],
    ...overrides,
  };
}

function renderInterviewPage() {
  return render(
    <MemoryRouter initialEntries={["/projects/5/interview"]}>
      <Routes>
        <Route path="/projects/:projectId/interview" element={<InterviewPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  Object.values(apiMock).forEach((value) => {
    if (typeof value === "function" && "mockReset" in value) {
      value.mockReset();
    }
  });
  apiMock.getProject.mockResolvedValue(baseProject);
  apiMock.getInterview.mockResolvedValue(null);
  apiMock.getProjectUnderstanding.mockResolvedValue(baseUnderstanding);
  apiMock.startInterview.mockResolvedValue(buildSession());
  apiMock.answerInterviewQuestion.mockResolvedValue(buildSession({ status: "completed", stopped_early: true, stop_reason: "The manager has enough information." }));
  apiMock.generateNextInterview.mockResolvedValue(buildSession());
  apiMock.finishInterview.mockResolvedValue(buildSession({ status: "completed", stopped_early: true, stop_reason: "Finished with current understanding." }));
  apiMock.generatePlan.mockResolvedValue({ id: 1 });
});

afterEach(() => {
  cleanup();
});

describe("InterviewPage", () => {
  it("renders the budget slider with the expected labels", async () => {
    renderInterviewPage();

    expect(await screen.findByText("Question budget")).toBeInTheDocument();
    expect(screen.getByRole("slider")).toHaveValue("20");
    expect(screen.getByText("0: Manager assumptions")).toBeInTheDocument();
    expect(screen.getByText("6: Quick MVP")).toBeInTheDocument();
    expect(screen.getByText("20: Recommended")).toBeInTheDocument();
    expect(screen.getByText("50: Detailed")).toBeInTheDocument();
  });

  it("renders question metadata and submits a custom answer", async () => {
    apiMock.getInterview.mockResolvedValue(buildSession({ generation_sources: ["fallback_generated"] }));
    renderInterviewPage();

    expect(await screen.findByText("Who should the first version optimize for?")).toBeInTheDocument();
    expect(screen.getByText("The manager needs to shape UX and docs around the real user.")).toBeInTheDocument();
    expect(screen.getByText("target users")).toBeInTheDocument();
    expect(screen.getByText("high impact")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Small team"));
    fireEvent.change(screen.getByPlaceholderText("Add extra project-specific context if the options do not cover it."), {
      target: { value: "The first release should work for engineers and reviewers." },
    });
    fireEvent.click(screen.getByText("Submit answer"));

    await waitFor(() => {
      expect(apiMock.answerInterviewQuestion).toHaveBeenCalledWith(42, {
        project_id: 5,
        option_id: "team",
        selected_text: "Small team",
        custom_answer: "The first release should work for engineers and reviewers.",
      });
    });
  });

  it("requests the next batch after the current batch is exhausted", async () => {
    apiMock.getInterview.mockResolvedValue(buildSession());
    apiMock.answerInterviewQuestion.mockResolvedValue(
      buildSession({
        questions_asked: 1,
        questions_remaining: 19,
        questions: [
          {
            ...buildSession().questions[0],
            status: "answered",
            selected_option_id: "solo",
            selected_text: "Solo operator",
            selected_option: "solo",
          },
        ],
      }),
    );
    apiMock.generateNextInterview.mockResolvedValue(
      buildSession({
        questions_asked: 4,
        questions_remaining: 16,
        current_index: 1,
        questions: [
          {
            ...buildSession().questions[0],
            status: "answered",
            selected_option_id: "solo",
            selected_text: "Solo operator",
            selected_option: "solo",
          },
          {
            id: 43,
            project_id: 5,
            index: 1,
            question: "How narrow should the first MVP slice be?",
            why: "The manager needs a scope guardrail before planning.",
            category: "MVP scope",
            impact: "medium",
            options: [
              { id: "narrow", label: "Keep it narrow", description: "Bias toward one reliable slice." },
              { id: "balanced", label: "Balanced slice", description: "Allow a little extra surface area." },
            ],
            allow_custom_answer: false,
            selected_option_id: null,
            selected_text: null,
            custom_answer: null,
            affects: ["scope", "milestones"],
            status: "pending",
            question_source: "manager_ai",
            answered_at: null,
            rationale: null,
            selected_option: null,
          },
        ],
      }),
    );

    renderInterviewPage();

    expect(await screen.findByText("Who should the first version optimize for?")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Solo operator"));
    fireEvent.click(screen.getByText("Submit answer"));

    await waitFor(() => {
      expect(apiMock.generateNextInterview).toHaveBeenCalledWith(5);
    });
    expect(await screen.findByText("How narrow should the first MVP slice be?")).toBeInTheDocument();
  });

  it("supports the zero-budget path and stop-early completion state", async () => {
    apiMock.startInterview.mockResolvedValue(
      buildSession({
        question_budget: 0,
        questions_asked: 0,
        questions_remaining: 0,
        status: "completed",
        stopped_early: false,
        stop_reason: "Manager assumptions mode requested.",
        questions: [],
        understanding_summary: "The manager will proceed with assumptions for this project.",
        generation_sources: [],
      }),
    );
    renderInterviewPage();

    await screen.findByText("Question budget");
    fireEvent.change(screen.getByRole("slider"), { target: { value: "0" } });
    fireEvent.click(screen.getByText("Start interview"));

    expect(await screen.findByText("Interview complete")).toBeInTheDocument();
    expect(screen.getByText("Manager assumptions mode requested.")).toBeInTheDocument();
  });
});
