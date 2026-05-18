import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import { HomeShell } from "../components/HomeShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import { useHomeState } from "../state/useHomeState";
import type { DiagnosticReport, DiagnosticReportListItem, StartupStatus } from "../types";

export function DiagnosticsPage() {
  const { summary, systemStatus, profile, reload, toggleProjectPin } = useHomeState();
  const [startupStatus, setStartupStatus] = useState<StartupStatus | null>(null);
  const [reports, setReports] = useState<DiagnosticReportListItem[]>([]);
  const [lastReport, setLastReport] = useState<DiagnosticReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  async function load() {
    const [startup, nextReports] = await Promise.all([api.getStartupStatus(), api.listDiagnosticReports()]);
    setStartupStatus(startup);
    setReports(nextReports);
    setLoading(false);
  }

  useEffect(() => {
    void load();
  }, []);

  const latestSummary = useMemo(() => lastReport?.summary ?? reports[0]?.summary ?? startupStatus?.error_summary ?? "No diagnostics run yet.", [lastReport?.summary, reports, startupStatus?.error_summary]);

  async function runDiagnostics() {
    const report = await api.runDiagnostics();
    setLastReport(report);
    await reload();
    await load();
    setNotice("Diagnostic report generated.");
  }

  async function retryStartupChecks() {
    if (!startupStatus) {
      return;
    }
    const nextStatus = await api.retryStartup({
      attempt_number: Math.min(startupStatus.startup_attempt + 1, startupStatus.max_startup_attempts),
      retry_mode: "targeted",
      failed_check: startupStatus.failed_checks[0] ?? null,
    });
    setStartupStatus(nextStatus);
    setNotice("Startup checks retried.");
  }

  async function openFolder() {
    const result = await api.openDiagnosticsFolder();
    setNotice(result.message);
  }

  async function copySummary() {
    await navigator.clipboard.writeText(latestSummary);
    setNotice("Latest diagnostic summary copied.");
  }

  return (
    <HomeShell
      title="Diagnostics"
      subtitle="Startup health, provider runtime checks, and saved diagnostic reports stay visible here without exposing secrets."
      summary={summary}
      systemStatus={systemStatus}
      profile={profile}
      onProjectPinToggle={toggleProjectPin}
    >
      {loading || !startupStatus ? (
        <LoadingBlock label="Loading diagnostics..." />
      ) : (
        <div className="intake-grid">
          <SectionCard title="Startup status" subtitle="Required checks must pass. Optional provider checks can degrade the app without blocking the dashboard.">
            <div className="startup-checklist">
              {startupStatus.checks.map((check) => (
                <div key={check.name} className={`startup-check startup-check--${check.status}`}>
                  <div>
                    <strong>{check.name}</strong>
                    <p>{check.summary}</p>
                  </div>
                  <span className="header-chip">{check.status}</span>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Runtime summary" subtitle="Provider and local runtime details.">
            <div className="status-grid">
              <div className="metric-card">
                <span>Backend</span>
                <strong>{systemStatus?.backend_port ?? "?"}</strong>
              </div>
              <div className="metric-card">
                <span>Frontend</span>
                <strong>{systemStatus?.frontend_port ?? "?"}</strong>
              </div>
              <div className="metric-card">
                <span>Codex CLI</span>
                <strong>{systemStatus?.cli_detected ? systemStatus.cli_version ?? "Detected" : "Unavailable"}</strong>
              </div>
              <div className="metric-card">
                <span>App-server</span>
                <strong>{systemStatus?.app_server_handshake_status ?? "Unknown"}</strong>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Saved reports" subtitle="Recent human-readable diagnostic reports from the runtime diagnostics folder.">
            {reports.length ? (
              <div className="archive-list">
                {reports.map((report) => (
                  <article key={report.path} className="archive-card">
                    <div className="archive-card__top">
                      <strong>{report.error_code ?? "Diagnostic report"}</strong>
                      <span>{new Date(report.created_at).toLocaleString()}</span>
                    </div>
                    <p>{report.summary}</p>
                    <div className="archive-card__meta">
                      <span>{report.path}</span>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="section-footnote">No diagnostic reports have been saved yet.</p>
            )}
          </SectionCard>

          <SectionCard title="Actions" subtitle="Run diagnostics, open the diagnostics folder, or retry startup checks in place.">
            <div className="button-row">
              <button type="button" onClick={() => void runDiagnostics()}>
                Run diagnostics
              </button>
              <button type="button" className="button-ghost" onClick={() => void openFolder()}>
                Open diagnostics folder
              </button>
              <button type="button" className="button-ghost" onClick={() => void copySummary()}>
                Copy latest diagnostic summary
              </button>
              <button type="button" className="button-ghost" onClick={() => void retryStartupChecks()}>
                Retry startup checks
              </button>
            </div>
            {notice ? <p className="section-footnote">{notice}</p> : null}
          </SectionCard>
        </div>
      )}
    </HomeShell>
  );
}
