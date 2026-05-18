import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { LoadingBlock } from "../components/LoadingBlock";
import { ProjectShell } from "../components/ProjectShell";
import { SectionCard } from "../components/SectionCard";
import type { AgentInstructionsStatus, CodebaseMap, CodebaseUnderstanding, ImportedCodebaseSafety, ImportInterviewChoice, Project } from "../types";

function asList(value: string[] | undefined, empty = "None detected"): string {
  return value && value.length ? value.join(", ") : empty;
}

export function ImportReviewPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const numericProjectId = Number(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [codebaseMap, setCodebaseMap] = useState<CodebaseMap | null>(null);
  const [understanding, setUnderstanding] = useState<CodebaseUnderstanding | null>(null);
  const [safety, setSafety] = useState<ImportedCodebaseSafety | null>(null);
  const [agentsStatus, setAgentsStatus] = useState<AgentInstructionsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [loadedProject, loadedMap, loadedUnderstanding, loadedSafety, loadedAgents] = await Promise.all([
          api.getProject(numericProjectId),
          api.getCodebaseMap(numericProjectId),
          api.getCodebaseUnderstanding(numericProjectId),
          api.getImportSafety(numericProjectId),
          api.getAgentsMdStatus(numericProjectId),
        ]);
        setProject(loadedProject);
        setCodebaseMap(loadedMap);
        setUnderstanding(loadedUnderstanding);
        setSafety(loadedSafety);
        setAgentsStatus(loadedAgents);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load imported codebase review.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [numericProjectId]);

  async function chooseInterview(choice: ImportInterviewChoice) {
    setWorking(choice);
    setError(null);
    try {
      const response = await api.chooseImportInterview(numericProjectId, choice);
      navigate(response.next_route);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to apply import interview choice.");
    } finally {
      setWorking(null);
    }
  }

  async function rescan() {
    setWorking("rescan");
    setError(null);
    try {
      await api.scanCodebase(numericProjectId);
      const [loadedMap, loadedUnderstanding, loadedSafety, loadedAgents, loadedProject] = await Promise.all([
        api.getCodebaseMap(numericProjectId),
        api.getCodebaseUnderstanding(numericProjectId),
        api.getImportSafety(numericProjectId),
        api.getAgentsMdStatus(numericProjectId),
        api.getProject(numericProjectId),
      ]);
      setCodebaseMap(loadedMap);
      setUnderstanding(loadedUnderstanding);
      setSafety(loadedSafety);
      setAgentsStatus(loadedAgents);
      setProject(loadedProject);
    } catch (rescanError) {
      setError(rescanError instanceof Error ? rescanError.message : "Failed to rescan codebase.");
    } finally {
      setWorking(null);
    }
  }

  return (
    <ProjectShell
      project={project}
      title="Imported Codebase Review"
      subtitle="The initial import scan is read-only. No commands are run, no files are edited, and nothing gets copied unless you say otherwise."
      rightRail={project ? <span className="header-chip">{project.name}</span> : null}
    >
      {loading ? (
        <LoadingBlock label="Loading imported codebase report..." />
      ) : (
        <div className="interview-grid">
          <SectionCard title="Codebase Map" subtitle="What the scanner can defend without running commands.">
            {codebaseMap ? (
              <div className="status-grid">
                <div className="metric-card">
                  <span>Languages</span>
                  <strong>{asList(codebaseMap.languages_json)}</strong>
                </div>
                <div className="metric-card">
                  <span>Frameworks</span>
                  <strong>{asList(codebaseMap.frameworks_json)}</strong>
                </div>
                <div className="metric-card">
                  <span>Scan depth</span>
                  <strong>{codebaseMap.scan_depth}</strong>
                </div>
                <div className="metric-card">
                  <span>Codebase size</span>
                  <strong>{codebaseMap.codebase_size}</strong>
                </div>
                <div className="status-list">
                  <h3>Commands</h3>
                  <ul>
                    <li>Build: {asList(codebaseMap.build_commands_json, "None detected")}</li>
                    <li>Test: {asList(codebaseMap.test_commands_json, "None detected")}</li>
                    <li>Important folders: {asList(codebaseMap.important_folders_json, "None detected")}</li>
                  </ul>
                </div>
                <div className="status-list">
                  <h3>Coverage</h3>
                  <ul>
                    <li>Indexed: {asList(codebaseMap.indexed_areas_json, "Nothing yet")}</li>
                    <li>Unindexed: {asList(codebaseMap.unindexed_areas_json, "None")}</li>
                    <li>Risk flags: {asList(codebaseMap.risk_flags_json, "None detected")}</li>
                  </ul>
                </div>
              </div>
            ) : (
              <p>Codebase map is not available yet.</p>
            )}
            <div className="button-row">
              <button type="button" className="button-ghost" onClick={() => void rescan()} disabled={working === "rescan"}>
                {working === "rescan" ? "Rescanning..." : "Run read-only rescan"}
              </button>
            </div>
          </SectionCard>

          <SectionCard title="Understanding Report" subtitle="Deterministic when Manager AI is unavailable, and explicitly labeled that way instead of faking confidence.">
            {understanding ? (
              <>
                <p>{understanding.summary}</p>
                <p className="section-footnote">{understanding.architecture_summary}</p>
                <div className="status-list">
                  <h3>Next steps</h3>
                  <ul>
                    {understanding.suggested_next_steps_json.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ul>
                </div>
                <div className="status-list">
                  <h3>Missing context</h3>
                  <ul>
                    {understanding.missing_context_json.length ? understanding.missing_context_json.map((item) => <li key={item}>{item}</li>) : <li>No major gaps detected.</li>}
                  </ul>
                </div>
              </>
            ) : (
              <p>Understanding report is not available yet.</p>
            )}
          </SectionCard>

          <SectionCard title="Safety Mode" subtitle="Imported repos default to stricter controls because the app should not act like your local code is a sandbox toy.">
            {safety ? (
              <div className="status-grid">
                <div className="metric-card">
                  <span>Write mode</span>
                  <strong>{safety.write_permission_status}</strong>
                </div>
                <div className="metric-card">
                  <span>Snapshot first</span>
                  <strong>{safety.require_snapshot_before_edits ? "Recommended" : "Optional"}</strong>
                </div>
                <div className="metric-card">
                  <span>Test approval</span>
                  <strong>{safety.require_approval_for_test_commands ? "Required" : "Relaxed"}</strong>
                </div>
                <div className="metric-card">
                  <span>Build approval</span>
                  <strong>{safety.require_approval_for_build_commands ? "Required" : "Relaxed"}</strong>
                </div>
              </div>
            ) : (
              <p>Safety mode is not available yet.</p>
            )}
            {agentsStatus ? (
              <p className="section-footnote">
                AGENTS.md: {agentsStatus.has_agents_md ? `present at ${agentsStatus.agents_md_path}` : "missing"}.
                {" "}
                Recommended action: {agentsStatus.recommended_action}.
              </p>
            ) : null}
          </SectionCard>

          <SectionCard title="Interview Choice" subtitle="You can skip the interview, ask for a short clarification loop, run the full flow, or let the Manager pick based on confidence.">
            <div className="button-row">
              <button type="button" onClick={() => void chooseInterview("skip")} disabled={Boolean(working)}>
                {working === "skip" ? "Opening..." : "Skip interview and open Manager Chat"}
              </button>
              <button type="button" className="button-ghost" onClick={() => void chooseInterview("quick")} disabled={Boolean(working)}>
                {working === "quick" ? "Starting..." : "Quick clarification"}
              </button>
              <button type="button" className="button-ghost" onClick={() => void chooseInterview("full")} disabled={Boolean(working)}>
                {working === "full" ? "Starting..." : "Full interview"}
              </button>
              <button type="button" className="button-ghost" onClick={() => void chooseInterview("manager_decides")} disabled={Boolean(working)}>
                {working === "manager_decides" ? "Deciding..." : "Let Manager decide"}
              </button>
            </div>
            {understanding ? <p className="section-footnote">Recommended: {understanding.recommended_interview_mode}</p> : null}
            {error ? <p className="error-text">{error}</p> : null}
          </SectionCard>
        </div>
      )}
    </ProjectShell>
  );
}
