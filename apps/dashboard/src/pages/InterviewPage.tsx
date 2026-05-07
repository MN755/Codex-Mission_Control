import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { AppShell } from "../components/AppShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import type { InterviewSession, Project } from "../types";

export function InterviewPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const numericProjectId = Number(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [questionCount, setQuestionCount] = useState<6 | 20 | 50>(6);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const [loadedProject, loadedSession] = await Promise.all([
          api.getProject(numericProjectId),
          api.getInterview(numericProjectId),
        ]);
        setProject(loadedProject);
        setSession(loadedSession);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load interview.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [numericProjectId]);

  const activeQuestion = session?.questions.find((question) => !question.selected_option) ?? null;
  const answerHistory = session?.questions.filter((question) => question.selected_option) ?? [];

  async function startInterview() {
    setWorking(true);
    try {
      const nextSession = await api.startInterview(numericProjectId, questionCount);
      setSession(nextSession);
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "Could not start interview.");
    } finally {
      setWorking(false);
    }
  }

  async function answerQuestion(optionId: string, selectedText: string) {
    if (!activeQuestion) {
      return;
    }
    setWorking(true);
    try {
      const nextSession = await api.answerInterview(numericProjectId, {
        question_id: activeQuestion.id,
        option_id: optionId,
        selected_text: selectedText,
      });
      setSession(nextSession);
    } catch (answerError) {
      setError(answerError instanceof Error ? answerError.message : "Could not save answer.");
    } finally {
      setWorking(false);
    }
  }

  async function generatePlan() {
    setWorking(true);
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
    <AppShell
      projectId={numericProjectId}
      title="Interview Mode"
      subtitle="Ask one question at a time so the manager can tighten the MVP without jumping into implementation."
      rightRail={project ? <span className="header-chip">{project.name}</span> : null}
    >
      {loading ? (
        <LoadingBlock label="Loading interview state..." />
      ) : (
        <div className="interview-grid">
          <SectionCard title="Question cadence" subtitle="Choose how much specificity you want before planning.">
            {!session ? (
              <div className="option-grid">
                {[6, 20, 50].map((count) => (
                  <button
                    key={count}
                    className={`selection-card ${questionCount === count ? "selection-card--active" : ""}`}
                    onClick={() => setQuestionCount(count as 6 | 20 | 50)}
                  >
                    <strong>{count}</strong>
                    <span>{count === 6 ? "Fast MVP" : count === 20 ? "Detailed build plan" : "Highly customized plan"}</span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="progress-card">
                <strong>
                  {Math.min(answerHistory.length + 1, session.question_count)} / {session.question_count}
                </strong>
                <span>{session.status === "completed" ? "Interview complete" : "Manager is collecting signal one answer at a time."}</span>
              </div>
            )}
            {!session ? (
              <button onClick={() => void startInterview()} disabled={working}>
                {working ? "Starting..." : "Start interview"}
              </button>
            ) : null}
          </SectionCard>

          <SectionCard title="Current question" subtitle="The user only answers the manager here, never worker agents.">
            {session?.status === "completed" ? (
              <div className="empty-state">
                <h3>Interview complete</h3>
                <p>The manager has enough signal to draft the plan.</p>
                <button onClick={() => void generatePlan()} disabled={working}>
                  {working ? "Generating..." : "Generate plan"}
                </button>
              </div>
            ) : activeQuestion ? (
              <div className="question-panel">
                <div className="question-panel__meta">
                  <span className="eyebrow">Question {activeQuestion.index + 1}</span>
                  <h3>{activeQuestion.question}</h3>
                </div>
                <div className="question-panel__options">
                  {activeQuestion.options.map((option) => (
                    <button
                      key={option.id}
                      className="answer-option"
                      disabled={working}
                      onClick={() => void answerQuestion(option.id, option.label)}
                    >
                      <strong>{option.label}</strong>
                      <span>{option.description}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <p>No active question. Start an interview to continue.</p>
            )}
            {error ? <p className="error-text">{error}</p> : null}
          </SectionCard>

          <SectionCard title="Answer history" subtitle="Keep the interview trace visible while refining the brief.">
            <div className="history-list">
              {answerHistory.map((question) => (
                <article key={question.id} className="history-item">
                  <strong>{question.question}</strong>
                  <span>{question.selected_text}</span>
                </article>
              ))}
              {!answerHistory.length ? <p>No answers yet.</p> : null}
            </div>
          </SectionCard>
        </div>
      )}
    </AppShell>
  );
}

