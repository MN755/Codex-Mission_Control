import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { AppShell } from "../components/AppShell";
import { MissionControlMark } from "../components/MissionControlMark";
import { SectionCard } from "../components/SectionCard";
import type { DiagnosticReport, StartupStatus } from "../types";

function checklistLabel(checkName: string): string {
  switch (checkName) {
    case "runtime_paths":
      return "Checking runtime";
    case "database":
      return "Preparing database";
    case "settings":
      return "Loading settings";
    case "projects":
      return "Loading projects";
    case "backend_route":
      return "Confirming backend routes";
    case "codex_cli":
      return "Checking Codex CLI";
    case "codex_login":
      return "Checking Codex login";
    case "app_server":
      return "Checking app-server";
    default:
      return checkName.replace(/_/g, " ");
  }
}

export function StartupPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<StartupStatus | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticReport | null>(null);
  const [loadingMessage, setLoadingMessage] = useState("Starting Mission Control...");
  const [error, setError] = useState<string | null>(null);
  const retryTimer = useRef<number | null>(null);
  const startedAt = useRef<number>(Date.now());

  useEffect(() => {
    async function boot() {
      try {
        const initial = await api.getStartupStatus();
        setStatus(initial);
        await advance(initial);
      } catch (bootError) {
        setError(bootError instanceof Error ? bootError.message : "Startup failed before checks could run.");
      }
    }
    void boot();
    return () => {
      if (retryTimer.current) {
        window.clearTimeout(retryTimer.current);
      }
    };
  }, []);

  async function advance(nextStatus: StartupStatus) {
    if (nextStatus.overall_status === "ready") {
      navigate(nextStatus.recommended_route, { replace: true });
      return;
    }
    if (nextStatus.overall_status === "degraded") {
      setLoadingMessage("Mission Control is ready in degraded mode.");
      return;
    }
    if (nextStatus.overall_status === "error" || nextStatus.overall_status === "retrying") {
      if (nextStatus.startup_attempt >= nextStatus.max_startup_attempts) {
        navigate("/startup-error", { replace: true });
        return;
      }
      setLoadingMessage(`Retrying startup (${nextStatus.startup_attempt + 1}/${nextStatus.max_startup_attempts})...`);
      retryTimer.current = window.setTimeout(async () => {
        const retried = await api.retryStartup({
          attempt_number: nextStatus.startup_attempt + 1,
          failed_check: nextStatus.failed_checks[0] ?? null,
          retry_mode: "targeted",
        });
        setStatus(retried);
        await advance(retried);
      }, 1200);
      return;
    }

    const checked = await api.runStartupCheck({ attempt_number: nextStatus.startup_attempt || 1, include_optional_checks: true });
    setStatus(checked);
    await advance(checked);
  }

  async function runDiagnostics() {
    try {
      const report = await api.runDiagnostics();
      setDiagnostics(report);
    } catch (diagnosticError) {
      setError(diagnosticError instanceof Error ? diagnosticError.message : "Could not generate diagnostics.");
    }
  }

  const elapsedSeconds = useMemo(() => Math.max(0, Math.floor((Date.now() - startedAt.current) / 1000)), [status, loadingMessage]);
  const checks = status?.checks ?? [];

  return (
    <AppShell title="Startup" subtitle="Mission Control is checking the local runtime before opening the dashboard shell.">
      <div className="startup-view">
        <SectionCard title="Mission Control startup" subtitle="This screen routes first-time installs into setup and regular launches into the dashboard.">
          <div className="launchpad-hero launchpad-hero--compact">
            <MissionControlMark className="launchpad-hero__mark launchpad-hero__mark--halo" />
            <div className="launchpad-hero__copy">
              <span className="eyebrow">Startup coordinator</span>
              <h2>{loadingMessage}</h2>
              <p>Mission Control checks runtime paths, database health, settings, projects, and provider readiness before routing you forward.</p>
            </div>
          </div>

          <div className="monitor-metrics">
            <article className="metric-card">
              <span>Attempt</span>
              <strong>
                {status?.startup_attempt ?? 1}/{status?.max_startup_attempts ?? 3}
              </strong>
            </article>
            <article className="metric-card">
              <span>Elapsed</span>
              <strong>{elapsedSeconds}s</strong>
            </article>
            <article className="metric-card">
              <span>Mode</span>
              <strong>{status?.mode ?? "starting"}</strong>
            </article>
            <article className="metric-card">
              <span>Overall status</span>
              <strong>{status?.overall_status ?? "starting"}</strong>
            </article>
          </div>

          <div className="startup-checklist">
            {checks.map((check) => (
              <div key={check.name} className={`startup-check startup-check--${check.status}`}>
                <div>
                  <strong>{checklistLabel(check.name)}</strong>
                  <p>{check.summary}</p>
                </div>
                <span className="header-chip">{check.status}</span>
              </div>
            ))}
          </div>

          {status?.overall_status === "degraded" ? (
            <div className="startup-banner startup-banner--warning">
              <div className="startup-indicator" />
              <div>
                <strong>Mission Control is usable in degraded mode.</strong>
                <p>{status.degraded_reasons.join(" ") || "Optional provider checks failed, but core app services are ready."}</p>
              </div>
            </div>
          ) : null}

          <div className="button-row">
            {status?.overall_status === "degraded" ? (
              <button type="button" onClick={() => navigate(status.recommended_route, { replace: true })}>
                Continue anyway
              </button>
            ) : null}
            <button type="button" className="button-ghost" onClick={() => void runDiagnostics()}>
              Run diagnostics
            </button>
            {status?.diagnostic_report_path ? (
              <button type="button" className="button-ghost" onClick={() => void api.openDiagnosticsFolder()}>
                Open diagnostics folder
              </button>
            ) : null}
          </div>

          {diagnostics ? (
            <div className="startup-note-card">
              <strong>Diagnostic report saved</strong>
              <p>{diagnostics.path}</p>
            </div>
          ) : null}

          {error ? <p className="error-text">{error}</p> : null}
        </SectionCard>
      </div>
    </AppShell>
  );
}
