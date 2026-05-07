import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { AppShell } from "../components/AppShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import type { Plan, Project } from "../types";

const ACTIONS = [
  { id: "approve_build", label: "Approve and build" },
  { id: "simplify", label: "Make simpler" },
  { id: "ambitious", label: "Make more ambitious" },
  { id: "usability", label: "Focus more on usability" },
  { id: "quality", label: "Focus more on quality/testing" },
  { id: "rewrite", label: "Rewrite plan" },
  { id: "feature_delta", label: "Add/remove feature" },
] as const;

export function PlanReviewPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const numericProjectId = Number(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [loadedProject, loadedPlan] = await Promise.all([api.getProject(numericProjectId), api.getPlan(numericProjectId)]);
      setProject(loadedProject);
      setPlan(loadedPlan);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load plan.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [numericProjectId]);

  async function applyAction(action: string) {
    setWorking(true);
    setError(null);
    try {
      const nextPlan = await api.approvePlan(numericProjectId, { action, note: note || undefined });
      setPlan(nextPlan);
      if (action === "approve_build") {
        navigate(`/projects/${numericProjectId}/build`);
      }
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Could not update plan.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <AppShell
      projectId={numericProjectId}
      title="Plan Review"
      subtitle="Approve the manager's plan or redirect it before any build work is treated as done."
      rightRail={project ? <span className="header-chip">{project.status}</span> : null}
    >
      {loading ? (
        <LoadingBlock label="Loading plan..." />
      ) : plan ? (
        <div className="plan-grid">
          <SectionCard title="Plan summary" subtitle="The manager keeps this artifact editable until approval.">
            <div className="markdown-panel">
              <pre>{plan.content_markdown}</pre>
            </div>
          </SectionCard>

          <SectionCard title="Approval controls" subtitle="Use the quick actions to tighten the plan without opening worker chats.">
            <label>
              Optional note
              <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add any guidance for the manager here." />
            </label>
            <div className="option-grid">
              {ACTIONS.map((action) => (
                <button
                  key={action.id}
                  className={action.id === "approve_build" ? "" : "button-ghost"}
                  disabled={working}
                  onClick={() => void applyAction(action.id)}
                >
                  {working ? "Working..." : action.label}
                </button>
              ))}
            </div>
            {error ? <p className="error-text">{error}</p> : null}
          </SectionCard>

          <SectionCard title="Plan metadata" subtitle="Quick signal for milestones, roster, and task-board shape.">
            <pre className="json-panel">{JSON.stringify(plan.summary_json, null, 2)}</pre>
          </SectionCard>
        </div>
      ) : (
        <SectionCard title="No plan yet" subtitle="Finish the interview first.">
          <button onClick={() => navigate(`/projects/${numericProjectId}/interview`)}>Go to interview</button>
        </SectionCard>
      )}
    </AppShell>
  );
}

