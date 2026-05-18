import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { AppShell } from "../components/AppShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import type { DiagnosticReport, StartupStatus } from "../types";

export function StartupErrorPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<StartupStatus | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const startupStatus = await api.getStartupStatus();
        setStatus(startupStatus);
        if (startupStatus.diagnostic_report_path) {
          setDiagnostics({
            path: startupStatus.diagnostic_report_path,
            summary: startupStatus.error_summary ?? "Diagnostic report already exists.",
            error_code: startupStatus.error_code,
            recommended_fixes: [],
          });
        }
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load startup error state.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  async function retry() {
    if (!status) {
      return;
    }
    const retried = await api.retryStartup({
      attempt_number: Math.min(status.startup_attempt + 1, status.max_startup_attempts),
      failed_check: status.failed_checks[0] ?? null,
      retry_mode: "full",
    });
    setStatus(retried);
    if (retried.overall_status === "ready" || retried.overall_status === "degraded") {
      navigate(retried.recommended_route, { replace: true });
    }
  }

  async function runDiagnostics() {
    try {
      const report = await api.runDiagnostics();
      setDiagnostics(report);
      setNotice(`Diagnostic report saved to ${report.path}`);
    } catch (diagnosticError) {
      setError(diagnosticError instanceof Error ? diagnosticError.message : "Could not run diagnostics.");
    }
  }

  async function openDiagnosticsFolder() {
    try {
      const result = await api.openDiagnosticsFolder();
      setNotice(result.message);
    } catch (openError) {
      setError(openError instanceof Error ? openError.message : "Could not open diagnostics folder.");
    }
  }

  async function copySummary() {
    if (!status) {
      return;
    }
    const lines = [
      `Error code: ${status.error_code ?? "None"}`,
      `Summary: ${status.error_summary ?? "Unknown startup failure"}`,
      `Failed checks: ${status.failed_checks.join(", ") || "None"}`,
      diagnostics?.path ? `Diagnostic report: ${diagnostics.path}` : null,
    ].filter(Boolean);
    await navigator.clipboard.writeText(lines.join("\n"));
    setNotice("Diagnostic summary copied.");
  }

  return (
    <AppShell title="Startup Error" subtitle="Mission Control could not start correctly after retrying the required checks.">
      {loading ? (
        <LoadingBlock label="Loading startup failure details..." />
      ) : status ? (
        <div className="startup-view">
          <SectionCard title="Mission Control could not start correctly." subtitle="Use diagnostics and retry controls below.">
            <div className="startup-note-card startup-note-card--danger">
              <strong>{status.error_code ?? "MC-BOOT-009"}</strong>
              <p>{status.error_summary ?? "Startup failed before Mission Control could reach the dashboard."}</p>
            </div>

            <div className="status-grid">
              <article className="metric-card">
                <span>Attempt</span>
                <strong>
                  {status.startup_attempt}/{status.max_startup_attempts}
                </strong>
              </article>
              <article className="metric-card">
                <span>Recommended route</span>
                <strong>{status.recommended_route}</strong>
              </article>
            </div>

            <div className="status-list">
              <h3>Failed checks</h3>
              <ul>
                {status.checks
                  .filter((check) => check.status === "failed")
                  .map((check) => (
                    <li key={check.name}>
                      {check.name}: {check.summary}
                    </li>
                  ))}
              </ul>
            </div>

            <div className="button-row">
              <button type="button" onClick={() => void retry()}>
                Retry startup
              </button>
              <button type="button" className="button-ghost" onClick={() => void runDiagnostics()}>
                Run diagnostics
              </button>
              <button type="button" className="button-ghost" onClick={() => void copySummary()}>
                Copy diagnostic summary
              </button>
              <button type="button" className="button-ghost" onClick={() => void openDiagnosticsFolder()}>
                Open diagnostics folder
              </button>
              {status.degraded_reasons.length ? (
                <button type="button" className="button-ghost" onClick={() => navigate("/dashboard")}>
                  Continue in degraded mode
                </button>
              ) : null}
            </div>

            {diagnostics ? (
              <div className="startup-note-card">
                <strong>Diagnostic report path</strong>
                <p>{diagnostics.path}</p>
                {diagnostics.recommended_fixes.length ? (
                  <ul className="flat-list">
                    {diagnostics.recommended_fixes.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            {notice ? <p className="section-footnote">{notice}</p> : null}
            {error ? <p className="error-text">{error}</p> : null}
          </SectionCard>
        </div>
      ) : (
        <p className="error-text">Startup error state is unavailable.</p>
      )}
    </AppShell>
  );
}
