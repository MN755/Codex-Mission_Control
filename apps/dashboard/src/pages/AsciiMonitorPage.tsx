import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { LoadingBlock } from "../components/LoadingBlock";
import { ProjectShell } from "../components/ProjectShell";
import { SectionCard } from "../components/SectionCard";
import { useProjectStream } from "../state/useProjectStream";
import type { AsciiMonitorFrame, Project } from "../types";

function projectPath(projectId: number, slug?: string | null): string {
  return slug ? `/projects/${projectId}/${slug}` : `/projects/${projectId}`;
}

function asciiMonitorPath(projectId: number, slug?: string | null): string {
  return slug ? `/projects/${projectId}/${slug}/ascii-monitor` : `/projects/${projectId}/ascii-monitor`;
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "Waiting";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function AsciiMonitorPage() {
  const { projectId, projectSlug } = useParams();
  const navigate = useNavigate();
  const numericProjectId = Number(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [monitor, setMonitor] = useState<AsciiMonitorFrame | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedNotice, setCopiedNotice] = useState<string | null>(null);
  const inFlightRef = useRef(false);

  const load = useCallback(
    async (background = false) => {
      if (!Number.isFinite(numericProjectId) || inFlightRef.current) {
        return;
      }
      inFlightRef.current = true;
      try {
        const [nextProject, nextMonitor] = await Promise.all([
          api.getProject(numericProjectId),
          api.getAsciiMonitor(numericProjectId),
        ]);
        setProject(nextProject);
        setMonitor(nextMonitor);
        setError(null);
        const canonicalPath = asciiMonitorPath(nextProject.id, nextProject.slug);
        const requestedPath = asciiMonitorPath(nextProject.id, projectSlug);
        if (canonicalPath !== requestedPath) {
          navigate(canonicalPath, { replace: true });
        }
      } catch (loadError) {
        const message = loadError instanceof Error ? loadError.message : "Failed to load the browser ASCII monitor.";
        setError(message);
      } finally {
        inFlightRef.current = false;
        if (!background) {
          setLoading(false);
        }
      }
    },
    [navigate, numericProjectId, projectSlug],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!Number.isFinite(numericProjectId)) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void load(true);
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, [load, numericProjectId]);

  useProjectStream(Number.isFinite(numericProjectId) ? numericProjectId : null, () => {
    void load(true);
  });

  useEffect(() => {
    if (!copiedNotice) {
      return;
    }
    const timeoutId = window.setTimeout(() => setCopiedNotice(null), 2200);
    return () => window.clearTimeout(timeoutId);
  }, [copiedNotice]);

  const rightRail = useMemo(() => {
    if (!monitor) {
      return null;
    }
    return (
      <div className="header-stack">
        <span className="header-chip">Status: {monitor.orchestration_status}</span>
        <span className="header-chip">Agents: {monitor.active_agents_count}</span>
        <span className="header-chip">Pending: {monitor.pending_decisions_count}</span>
        <span className="header-chip">Refresh: {monitor.refresh_seconds.toFixed(1)}s</span>
      </div>
    );
  }, [monitor]);

  return (
    <ProjectShell
      project={project}
      title="ASCII Live Monitor"
      subtitle="Browser-hosted version of the CLI ASCII viewer. Same live orchestration pulse, just easier to keep open on localhost."
      rightRail={rightRail}
    >
      {loading && !monitor ? (
        <LoadingBlock label="Loading ASCII live monitor..." />
      ) : (
        <div className="ascii-monitor-layout">
          <SectionCard
            title="Live ASCII Frame"
            subtitle="Refreshes every second and also updates when project events land."
            actions={
              <div className="button-row">
                <button type="button" className="button-ghost" onClick={() => void load()}>
                  Refresh now
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  disabled={!monitor?.viewer_command}
                  onClick={() => {
                    if (!monitor?.viewer_command || !navigator.clipboard?.writeText) {
                      return;
                    }
                    void navigator.clipboard.writeText(monitor.viewer_command);
                    setCopiedNotice("Copied the CLI viewer command.");
                  }}
                >
                  Copy CLI command
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => {
                    if (!project) {
                      return;
                    }
                    navigate(projectPath(project.id, project.slug));
                  }}
                >
                  Open workspace
                </button>
              </div>
            }
          >
            <div className="ascii-monitor-meta">
              <span>Project: {monitor?.project_name ?? project?.name ?? "Unknown project"}</span>
              <span>Orchestration: {monitor?.orchestration_id ?? "none"}</span>
              <span>Checked: {formatTimestamp(monitor?.checked_at)}</span>
            </div>
            <div className="ascii-monitor-frame-wrap">
              <pre className="ascii-monitor-frame">{monitor?.frame ?? "No ASCII frame is available yet."}</pre>
            </div>
            {copiedNotice ? <p className="success-text">{copiedNotice}</p> : null}
            {error ? <p className="error-text">{error}</p> : null}
          </SectionCard>
        </div>
      )}
    </ProjectShell>
  );
}
