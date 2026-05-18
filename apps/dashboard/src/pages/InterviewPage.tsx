import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { LoadingBlock } from "../components/LoadingBlock";
import { ProjectShell } from "../components/ProjectShell";
import { SectionCard } from "../components/SectionCard";
import type { InterviewQuestion, InterviewSession, Project, ProjectUnderstanding } from "../types";

function budgetLabel(value: number) {
  if (value === 0) {
    return "Manager assumptions";
  }
  if (value <= 6) {
    return "Quick MVP";
  }
  if (value <= 20) {
    return "Recommended";
  }
  if (value <= 50) {
    return "Detailed";
  }
  return "Extreme";
}

function answerText(question: InterviewQuestion) {
  return question.custom_answer?.trim() || question.selected_text || "No answer recorded.";
}

function understandingFromSession(session: InterviewSession | null): ProjectUnderstanding | null {
  if (!session) {
    return null;
  }
  return {
    project_id: session.project_id,
    summary: session.understanding_summary || "",
    known_facts_json: session.known_facts,
    unknowns_json: session.unknowns,
    assumptions_json: session.assumptions,
    constraints_json: session.constraints,
    confidence_by_category_json: session.confidence,
    updated_at: new Date().toISOString(),
  };
}

export function InterviewPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const numericProjectId = Number(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [understanding, setUnderstanding] = useState<ProjectUnderstanding | null>(null);
  const [loading, setLoading] = useState(true);
  const [questionBudget, setQuestionBudget] = useState(20);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [customAnswer, setCustomAnswer] = useState("");
  const autoAdvanceRef = useRef<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [loadedProject, loadedSession, loadedUnderstanding] = await Promise.all([
          api.getProject(numericProjectId),
          api.getInterview(numericProjectId),
          api.getProjectUnderstanding(numericProjectId),
        ]);
        setProject(loadedProject);
        setSession(loadedSession);
        setUnderstanding(loadedSession ? understandingFromSession(loadedSession) : loadedUnderstanding);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load interview.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [numericProjectId]);

  const pendingQuestions = useMemo(
    () => session?.questions.filter((question) => question.status === "pending" && !question.selected_option_id) ?? [],
    [session],
  );
  const answeredQuestions = useMemo(
    () => session?.questions.filter((question) => question.status === "answered" || Boolean(question.selected_option_id)) ?? [],
    [session],
  );
  const activeQuestion = pendingQuestions[0] ?? null;
  const activeOption = activeQuestion?.options.find((option) => option.id === selectedOptionId) ?? null;
  const fallbackActive = Boolean(import.meta.env.DEV && session?.generation_sources.includes("fallback_generated"));

  useEffect(() => {
    setSelectedOptionId(null);
    setCustomAnswer("");
  }, [activeQuestion?.id]);

  useEffect(() => {
    if (!session || session.status !== "in_progress" || pendingQuestions.length > 0 || session.questions_remaining <= 0 || working) {
      return;
    }
    const key = `${session.id}:${session.questions_asked}:${answeredQuestions.length}`;
    if (autoAdvanceRef.current === key) {
      return;
    }
    autoAdvanceRef.current = key;
    setWorking(true);
    void api
      .generateNextInterview(numericProjectId)
      .then((nextSession) => {
        setSession(nextSession);
        setUnderstanding(understandingFromSession(nextSession));
      })
      .catch((nextError) => {
        setError(nextError instanceof Error ? nextError.message : "Could not generate the next interview batch.");
      })
      .finally(() => {
        setWorking(false);
      });
  }, [answeredQuestions.length, numericProjectId, pendingQuestions.length, session, working]);

  async function startInterview() {
    setWorking(true);
    setError(null);
    try {
      const nextSession = await api.startInterview(numericProjectId, questionBudget);
      setSession(nextSession);
      setUnderstanding(understandingFromSession(nextSession));
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "Could not start interview.");
    } finally {
      setWorking(false);
    }
  }

  async function submitAnswer() {
    if (!activeQuestion || !selectedOptionId || !activeOption) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      let nextSession = await api.answerInterviewQuestion(activeQuestion.id, {
        project_id: numericProjectId,
        option_id: selectedOptionId,
        selected_text: activeOption.label,
        custom_answer: activeQuestion.allow_custom_answer ? customAnswer || null : null,
      });
      if (nextSession.status === "in_progress" && nextSession.questions_remaining > 0) {
        const hasPendingQuestions = nextSession.questions.some((question) => question.status === "pending" && !question.selected_option_id);
        if (!hasPendingQuestions) {
          nextSession = await api.generateNextInterview(numericProjectId);
        }
      }
      setSession(nextSession);
      setUnderstanding(understandingFromSession(nextSession));
    } catch (answerError) {
      setError(answerError instanceof Error ? answerError.message : "Could not save answer.");
    } finally {
      setWorking(false);
    }
  }

  async function finishInterview() {
    setWorking(true);
    setError(null);
    try {
      const nextSession = await api.finishInterview(numericProjectId);
      setSession(nextSession);
      setUnderstanding(understandingFromSession(nextSession));
    } catch (finishError) {
      setError(finishError instanceof Error ? finishError.message : "Could not finish interview.");
    } finally {
      setWorking(false);
    }
  }

  async function generatePlan() {
    setWorking(true);
    setError(null);
    try {
      await api.generatePlan(numericProjectId);
      navigate(`/projects/${numericProjectId}/plan`);
    } catch (planError) {
      setError(planError instanceof Error ? planError.message : "Could not generate plan.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <ProjectShell
      project={project}
      title="Interview Mode"
      subtitle="The Manager asks project-specific questions in small batches, updates its understanding, and stops when it has enough signal."
      rightRail={project ? <span className="header-chip">{project.name}</span> : null}
    >
      {loading ? (
        <LoadingBlock label="Loading interview state..." />
      ) : (
        <div className="interview-grid">
          <SectionCard title="Question budget" subtitle="The budget caps how deep the interview can go. It does not force the manager to waste your time.">
            {!session ? (
              <div className="interview-budget">
                <div className="interview-budget__header">
                  <strong>{questionBudget}</strong>
                  <span>{budgetLabel(questionBudget)}</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={500}
                  step={1}
                  value={questionBudget}
                  onChange={(event) => setQuestionBudget(Number(event.target.value))}
                />
                <div className="interview-budget__legend">
                  <span>0: Manager assumptions</span>
                  <span>6: Quick MVP</span>
                  <span>20: Recommended</span>
                  <span>50: Detailed</span>
                  <span>100+: Extreme</span>
                </div>
                <p className="section-footnote">
                  The manager asks only what materially changes architecture, scope, validation, tooling, or handoff.
                </p>
              </div>
            ) : (
              <div className="status-grid">
                <div className="metric-card">
                  <span>Budget</span>
                  <strong>{session.question_budget}</strong>
                </div>
                <div className="metric-card">
                  <span>Asked</span>
                  <strong>{session.questions_asked}</strong>
                </div>
                <div className="metric-card">
                  <span>Answered</span>
                  <strong>{answeredQuestions.length}</strong>
                </div>
                <div className="metric-card">
                  <span>Remaining</span>
                  <strong>{session.questions_remaining}</strong>
                </div>
              </div>
            )}
            {!session ? (
              <button onClick={() => void startInterview()} disabled={working}>
                {working ? "Starting..." : "Start interview"}
              </button>
            ) : (
              <div className="button-row">
                {session.status !== "completed" ? (
                  <button type="button" className="button-ghost" onClick={() => void finishInterview()} disabled={working}>
                    {working ? "Finishing..." : "Finish with current understanding"}
                  </button>
                ) : null}
                {session.status === "completed" ? (
                  <button onClick={() => void generatePlan()} disabled={working}>
                    {working ? "Generating..." : "Generate plan"}
                  </button>
                ) : null}
              </div>
            )}
          </SectionCard>

          <SectionCard title="Current question" subtitle="The user answers the Manager here. The Manager decides whether another batch is still worth asking.">
            {session?.status === "completed" ? (
              <div className="empty-state">
                <h3>{session.stopped_early ? "Manager has enough information" : "Interview complete"}</h3>
                <p>{session.stop_reason || "The manager can move to planning with the captured project understanding."}</p>
                <button onClick={() => void generatePlan()} disabled={working}>
                  {working ? "Generating..." : "Generate plan"}
                </button>
              </div>
            ) : activeQuestion ? (
              <div className="question-panel">
                <div className="question-panel__meta">
                  <span className="eyebrow">Question {activeQuestion.index + 1}</span>
                  <div className="button-row">
                    {activeQuestion.category ? <span className="header-chip">{activeQuestion.category}</span> : null}
                    <span className={`status-pill status-pill--${activeQuestion.impact === "high" ? "danger" : activeQuestion.impact === "medium" ? "warning" : "info"}`}>
                      {activeQuestion.impact} impact
                    </span>
                    {fallbackActive ? <span className="status-pill status-pill--muted">Fallback generation</span> : null}
                  </div>
                  <h3>{activeQuestion.question}</h3>
                  {activeQuestion.why ? <p className="section-footnote">{activeQuestion.why}</p> : null}
                  {activeQuestion.affects.length ? (
                    <p className="section-footnote">Affects: {activeQuestion.affects.join(", ")}</p>
                  ) : null}
                </div>
                <div className="question-panel__options">
                  {activeQuestion.options.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      className={`answer-option ${selectedOptionId === option.id ? "answer-option--selected" : ""}`}
                      disabled={working}
                      onClick={() => setSelectedOptionId(option.id)}
                    >
                      <strong>{option.label}</strong>
                      <span>{option.description}</span>
                    </button>
                  ))}
                </div>
                {activeQuestion.allow_custom_answer ? (
                  <label className="stack-form">
                    <span className="eyebrow">Optional custom answer</span>
                    <textarea
                      rows={3}
                      value={customAnswer}
                      onChange={(event) => setCustomAnswer(event.target.value)}
                      placeholder="Add extra project-specific context if the options do not cover it."
                    />
                  </label>
                ) : null}
                <div className="button-row">
                  <button onClick={() => void submitAnswer()} disabled={working || !selectedOptionId}>
                    {working ? "Saving..." : "Submit answer"}
                  </button>
                  <span className="section-footnote">
                    {pendingQuestions.length > 1 ? `${pendingQuestions.length - 1} more question(s) already queued in this batch.` : "The manager will decide whether another batch is needed after this answer."}
                  </span>
                </div>
              </div>
            ) : session?.status === "in_progress" ? (
              <div className="progress-card">
                <span className="loading-block__dot" />
                <span>The manager is updating its project understanding and deciding whether another question batch is necessary.</span>
              </div>
            ) : (
              <p>No active question. Start an interview to continue.</p>
            )}
            {error ? <p className="error-text">{error}</p> : null}
          </SectionCard>

          <SectionCard title="Project understanding" subtitle="This is the manager’s evolving model of the project, not a bag of generic answers.">
            <div className="history-list">
              <article className="history-item">
                <strong>Summary</strong>
                <span>{understanding?.summary || session?.understanding_summary || "The manager has not summarized the project yet."}</span>
              </article>
              <article className="history-item">
                <strong>Known facts</strong>
                <span>{Object.keys(understanding?.known_facts_json || {}).length} category bucket(s) confirmed.</span>
              </article>
              <article className="history-item">
                <strong>Unknowns</strong>
                <span>{Object.keys(understanding?.unknowns_json || {}).length} bucket(s) still open.</span>
              </article>
              <article className="history-item">
                <strong>Confidence</strong>
                <span>
                  {Object.entries(session?.confidence || {}).length
                    ? Object.entries(session?.confidence || {})
                        .map(([category, value]) => `${category}: ${Math.round(value * 100)}%`)
                        .join(" · ")
                    : "The manager has not published category confidence yet."}
                </span>
              </article>
              {understanding?.constraints_json.length ? (
                <article className="history-item">
                  <strong>Constraints</strong>
                  <span>{understanding.constraints_json.join(" · ")}</span>
                </article>
              ) : null}
              {understanding?.assumptions_json.length ? (
                <article className="history-item">
                  <strong>Assumptions</strong>
                  <span>{understanding.assumptions_json.join(" · ")}</span>
                </article>
              ) : null}
            </div>
          </SectionCard>

          <SectionCard title="Answer history" subtitle="Keep the interview trace visible so the plan is anchored to real decisions.">
            <div className="history-list">
              {answeredQuestions.map((question) => (
                <article key={question.id} className="history-item">
                  <strong>{question.question}</strong>
                  <span>{answerText(question)}</span>
                </article>
              ))}
              {!answeredQuestions.length ? <p>No answers yet.</p> : null}
            </div>
          </SectionCard>
        </div>
      )}
    </ProjectShell>
  );
}
