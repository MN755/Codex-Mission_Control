import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api } from "../api/client";
import { LoadingBlock } from "../components/LoadingBlock";
import { ProjectShell } from "../components/ProjectShell";
import { SectionCard } from "../components/SectionCard";
import { providerDefaultLabel, providerLabel } from "../lib/providers";
import type { Plan, Project, ProjectSettings, Task } from "../types";

export function HandoffPage() {
  const { projectId } = useParams();
  const numericProjectId = Number(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [changeRequest, setChangeRequest] = useState("");
  const [managerReply, setManagerReply] = useState("");

  useEffect(() => {
    async function load() {
      const [loadedProject, loadedPlan, loadedTasks, loadedSettings] = await Promise.all([
        api.getProject(numericProjectId),
        api.getPlan(numericProjectId),
        api.getTasks(numericProjectId),
        api.getSettings(numericProjectId),
      ]);
      setProject(loadedProject);
      setPlan(loadedPlan);
      setTasks(loadedTasks);
      setSettings(loadedSettings);
      setLoading(false);
    }
    void load();
  }, [numericProjectId]);

  async function submitChangeRequest() {
    const response = await api.sendManagerMessage(numericProjectId, changeRequest);
    setManagerReply(response.reply);
    setChangeRequest("");
  }

  const testsRun = (project?.final_report_json?.tests_run as string[] | undefined) ?? [];
  const handoff = project?.final_report_json ?? {};
  const whatWasBuilt = (handoff.what_was_built as string[] | undefined) ?? [];
  const howToRun = (handoff.how_to_run as string[] | undefined) ?? [];
  const howToUse = (handoff.how_to_use as string[] | undefined) ?? [];
  const knownLimitations = (handoff.known_limitations as string[] | undefined) ?? ["Runner depth depends on the selected local provider environment."];
  const remainingRisks = (handoff.remaining_risks as string[] | undefined) ?? [];
  const nextImprovements = (handoff.suggested_next_improvements as string[] | undefined) ?? [];
  const executedChecks = (handoff.tests_builds_run as string[] | undefined) ?? testsRun;
  const modelsUsed = (handoff.models_used as Record<string, unknown> | undefined) ?? {};
  const providerUsed = String(modelsUsed.provider ?? settings?.provider ?? "codex");
  const roleModelOverrides = (modelsUsed.role_model_overrides as Record<string, string> | undefined) ?? settings?.per_role_model_overrides_json ?? {};

  return (
    <ProjectShell
      project={project}
      title="Final Handoff"
      subtitle="The manager only declares completion after the project reaches a real terminal state."
      rightRail={project ? <span className="header-chip">{project.status}</span> : null}
    >
      {loading ? (
        <LoadingBlock label="Loading handoff..." />
      ) : (
        <div className="handoff-grid">
          <SectionCard title="What was built" subtitle="Summarize the delivered slice and the artifacts left in the workspace.">
            <ul className="flat-list">
              {whatWasBuilt.map((item) => (
                <li key={item}>{item}</li>
              ))}
              <li>Project docs path: {project?.docs_path ?? "Not generated"}</li>
              <li>Provider used: {providerLabel(providerUsed)}</li>
              <li>Runner mode used: {project?.runner_mode}</li>
              <li>Manager model: {String(modelsUsed.manager_model ?? settings?.manager_model ?? providerDefaultLabel(providerUsed))}</li>
              <li>Default worker model: {String(modelsUsed.default_worker_model ?? settings?.default_worker_model ?? providerDefaultLabel(providerUsed))}</li>
              <li>Latest plan version: {plan?.version ?? "None"}</li>
              <li>Completed tasks: {tasks.filter((task) => task.status === "done").length}</li>
            </ul>
          </SectionCard>

          <SectionCard title="How to run it" subtitle="The MVP favors accurate instructions over fake automation claims.">
            <ul className="flat-list">
              {howToRun.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </SectionCard>

          <SectionCard title="How to use it" subtitle="Operational guidance from the manager.">
            <ul className="flat-list">
              {howToUse.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </SectionCard>

          <SectionCard title="Tests performed" subtitle="Record only what was actually run.">
            <ul className="flat-list">
              {executedChecks.length ? executedChecks.map((item) => <li key={item}>{item}</li>) : <li>No tests recorded by the backend yet.</li>}
            </ul>
          </SectionCard>

          <SectionCard title="Known limitations" subtitle="Be explicit about environment-dependent behavior.">
            <ul className="flat-list">
              {knownLimitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </SectionCard>

          <SectionCard title="Remaining risks" subtitle="Open issues that still matter after handoff.">
            <ul className="flat-list">
              {remainingRisks.length ? remainingRisks.map((item) => <li key={item}>{item}</li>) : <li>No additional risks were recorded.</li>}
            </ul>
          </SectionCard>

          <SectionCard title="Next improvements" subtitle="Default next steps after the MVP vertical slice.">
            <ul className="flat-list">
              {nextImprovements.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </SectionCard>

          <SectionCard title="Models used" subtitle="These are the project-scoped model settings that were active for the build.">
            <ul className="flat-list">
              <li>Provider: {providerLabel(providerUsed)}</li>
              <li>Manager model: {String(modelsUsed.manager_model ?? settings?.manager_model ?? providerDefaultLabel(providerUsed))}</li>
              <li>Manager reasoning: {String(modelsUsed.manager_reasoning_effort ?? settings?.manager_reasoning_effort ?? providerDefaultLabel(providerUsed))}</li>
              <li>Default worker model: {String(modelsUsed.default_worker_model ?? settings?.default_worker_model ?? providerDefaultLabel(providerUsed))}</li>
              <li>Default worker reasoning: {String(modelsUsed.default_worker_reasoning_effort ?? settings?.default_worker_reasoning_effort ?? providerDefaultLabel(providerUsed))}</li>
              <li>Role overrides: {Object.keys(roleModelOverrides).length ? Object.entries(roleModelOverrides).map(([role, model]) => `${role}: ${model}`).join(", ") : "None"}</li>
            </ul>
          </SectionCard>

          <SectionCard title="Route a change request" subtitle="The user still talks only to the manager.">
            <div className="stack-form">
              <textarea value={changeRequest} onChange={(event) => setChangeRequest(event.target.value)} placeholder="Describe a follow-up change or fix." />
              <button onClick={() => void submitChangeRequest()}>Send change request</button>
              {managerReply ? <p>{managerReply}</p> : null}
            </div>
          </SectionCard>
        </div>
      )}
    </ProjectShell>
  );
}
