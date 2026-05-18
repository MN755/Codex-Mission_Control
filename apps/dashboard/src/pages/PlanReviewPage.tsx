import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { LoadingBlock } from "../components/LoadingBlock";
import { ProjectShell } from "../components/ProjectShell";
import { SectionCard } from "../components/SectionCard";
import type { Plan, Project, SwarmPlan } from "../types";

const ACTIONS = [
  { id: "approve_build", label: "Approve and build" },
  { id: "simplify", label: "Make simpler" },
  { id: "ambitious", label: "Make more ambitious" },
  { id: "usability", label: "Focus more on usability" },
  { id: "quality", label: "Focus more on quality/testing" },
  { id: "rewrite", label: "Rewrite plan" },
  { id: "feature_delta", label: "Add/remove feature" },
] as const;

function titleCase(value: string | null | undefined): string {
  return String(value ?? "")
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

export function PlanReviewPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const numericProjectId = Number(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [swarmPlan, setSwarmPlan] = useState<SwarmPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function loadSwarmPreview(loadedProject: Project, loadedPlan: Plan | null) {
    if (!loadedPlan) {
      setSwarmPlan(null);
      return;
    }
    const existing = await api.getSwarmPlan(loadedProject.id);
    if (existing) {
      setSwarmPlan(existing);
      return;
    }
    const generated = await api.createSwarmPlan(loadedProject.id, {
      goal: `Prepare the worker swarm strategy for the approved plan for ${loadedProject.name}.`,
      milestone_id: loadedPlan.id,
    });
    setSwarmPlan(generated);
  }

  async function load() {
    try {
      const [loadedProject, loadedPlan] = await Promise.all([api.getProject(numericProjectId), api.getPlan(numericProjectId)]);
      setProject(loadedProject);
      setPlan(loadedPlan);
      await loadSwarmPreview(loadedProject, loadedPlan);
      setError(null);
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
        const loadedProject = await api.getProject(numericProjectId);
        navigate(loadedProject.slug ? `/projects/${numericProjectId}/${loadedProject.slug}` : `/projects/${numericProjectId}`);
        return;
      }
      await load();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Could not update plan.");
    } finally {
      setWorking(false);
    }
  }

  async function approveSwarmStrategy() {
    if (!project) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      const planPreview =
        swarmPlan ??
        (await api.createSwarmPlan(project.id, {
          goal: `Prepare the worker swarm strategy for ${project.name}.`,
          milestone_id: plan?.id ?? null,
        }));
      setSwarmPlan(await api.approveSwarmPlan(project.id, planPreview.id));
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Could not approve the swarm strategy.");
    } finally {
      setWorking(false);
    }
  }

  async function reviseSwarmStrategy() {
    if (!project) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      if (swarmPlan) {
        setSwarmPlan(await api.reviseSwarmPlan(project.id, swarmPlan.id, note || "Revise the swarm strategy to better fit the updated plan review feedback."));  
      } else {
        setSwarmPlan(
          await api.createSwarmPlan(project.id, {
            goal: note || `Design a better swarm strategy for ${project.name}.`,
            milestone_id: plan?.id ?? null,
          }),
        );
      }
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Could not revise the swarm strategy.");
    } finally {
      setWorking(false);
    }
  }

  const taskBreakdown = Array.isArray(plan?.summary_json?.task_breakdown)
    ? (plan?.summary_json?.task_breakdown as Array<Record<string, unknown>>)
    : [];

  return (
    <ProjectShell
      project={project}
      title="Plan Review"
      subtitle="Approve the manager's plan and worker strategy before any build work is allowed to pretend it knows what it's doing."
      rightRail={
        <div className="button-row">
          {plan ? <span className="header-chip">{titleCase(plan.status)}</span> : null}
          {swarmPlan ? <span className="header-chip">{titleCase(swarmPlan.mode)}</span> : null}
        </div>
      }
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

          <SectionCard title="Swarm Plan Preview" subtitle="The Manager chooses the largest useful swarm, not the largest possible one. Revolutionary restraint.">
            {swarmPlan ? (
              <div className="workspace-swarm-drawer">
                <div className="workspace-swarm-drawer__summary">
                  <div>
                    <span>Mode</span>
                    <strong>{titleCase(swarmPlan.mode)}</strong>
                  </div>
                  <div>
                    <span>Recommended</span>
                    <strong>{swarmPlan.recommended_agent_count} agents</strong>
                  </div>
                  <div>
                    <span>Coordination risk</span>
                    <strong>{titleCase(swarmPlan.coordination_risk)}</strong>
                  </div>
                  <div>
                    <span>Path conflict</span>
                    <strong>{titleCase(swarmPlan.path_conflict_risk)}</strong>
                  </div>
                </div>
                <p className="workspace-swarm-panel__summary">{swarmPlan.strategy_summary}</p>
                {swarmPlan.usage_warning ? <p className="workspace-swarm-panel__warning">{swarmPlan.usage_warning}</p> : null}
                {swarmPlan.approval_required && !swarmPlan.approved_by_user ? (
                  <p className="workspace-swarm-panel__warning">This swarm size needs explicit approval before the Manager can launch the full worker set.</p>
                ) : null}

                <div className="workspace-swarm-drawer__section">
                  <div className="workspace-swarm-drawer__header">
                    <h3>Agent roster</h3>
                    <span className="count-badge">{swarmPlan.specs.length}</span>
                  </div>
                  <div className="workspace-swarm-spec-list">
                    {swarmPlan.specs.map((spec) => (
                      <article key={spec.id} className="workspace-swarm-spec-card">
                        <div className="workspace-swarm-spec-card__top">
                          <div>
                            <strong>{spec.name}</strong>
                            <p>{titleCase(spec.archetype)} specialist</p>
                          </div>
                          <span className="status-pill status-info">{titleCase(spec.status)}</span>
                        </div>
                        <p className="workspace-swarm-spec-card__mission">{spec.mission}</p>
                        <div className="workspace-swarm-spec-card__meta">
                          <span>Spawn phase: {titleCase(spec.spawn_phase.replace(/_/g, " "))}</span>
                          <span>Allowed paths: {spec.allowed_paths_json.slice(0, 3).join(", ") || "None assigned"}</span>
                          <span>Retire when: {spec.retire_when}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                </div>

                <div className="workspace-swarm-drawer__section">
                  <div className="workspace-swarm-drawer__header">
                    <h3>Expected bottlenecks</h3>
                    <span className="count-badge">{swarmPlan.expected_bottlenecks_json.length}</span>
                  </div>
                  {swarmPlan.expected_bottlenecks_json.length ? (
                    <ul className="workspace-swarm-drawer__list">
                      {swarmPlan.expected_bottlenecks_json.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="section-footnote">No major bottlenecks recorded.</p>
                  )}
                </div>

                <div className="workspace-swarm-drawer__section">
                  <div className="workspace-swarm-drawer__header">
                    <h3>Validation strategy</h3>
                    <span className="count-badge">{swarmPlan.validation_strategy_json.length}</span>
                  </div>
                  {swarmPlan.validation_strategy_json.length ? (
                    <ul className="workspace-swarm-drawer__list">
                      {swarmPlan.validation_strategy_json.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="section-footnote">No validation strategy recorded yet.</p>
                  )}
                </div>

                <div className="button-row">
                  <button type="button" className="button-ghost" disabled={working} onClick={() => void reviseSwarmStrategy()}>
                    {working ? "Working..." : "Revise Swarm Strategy"}
                  </button>
                  <button type="button" disabled={working || swarmPlan.approved_by_user} onClick={() => void approveSwarmStrategy()}>
                    {working ? "Working..." : swarmPlan.approved_by_user ? "Swarm Approved" : "Approve Swarm Plan"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="workspace-swarm-panel">
                <p className="section-footnote">No swarm preview exists yet. Generate one so the Manager has to justify the worker lineup instead of smuggling in a template roster.</p>
                <button type="button" disabled={working} onClick={() => void reviseSwarmStrategy()}>
                  {working ? "Working..." : "Generate swarm preview"}
                </button>
              </div>
            )}
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

          <SectionCard title="Task routing preview" subtitle="A quick look at what the current plan wants workers to own.">
            {taskBreakdown.length ? (
              <div className="workspace-swarm-spec-list">
                {taskBreakdown.map((item, index) => (
                  <article key={`${String(item.title ?? "task")}-${index}`} className="workspace-swarm-spec-card">
                    <div className="workspace-swarm-spec-card__top">
                      <div>
                        <strong>{String(item.title ?? "Untitled task")}</strong>
                        <p>{String(item.agent_role ?? "Manager-routed task")}</p>
                      </div>
                      <span className="status-pill status-info">{String(item.milestone ?? "Milestone")}</span>
                    </div>
                    <p className="workspace-swarm-spec-card__mission">{String(item.goal ?? item.scope ?? "No task goal recorded.")}</p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="section-footnote">The current plan does not expose task breakdown metadata yet.</p>
            )}
          </SectionCard>
        </div>
      ) : (
        <SectionCard title="No plan yet" subtitle="Finish the interview first.">
          <button onClick={() => navigate(`/projects/${numericProjectId}/interview`)}>Go to interview</button>
        </SectionCard>
      )}
    </ProjectShell>
  );
}
