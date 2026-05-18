import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { AppProfile, CodexStatus, DashboardSummary } from "../types";

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function retryRequest<T>(run: () => Promise<T>, attempts = 2, delayMs = 200): Promise<T> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await run();
    } catch (error) {
      lastError = error;
      if (attempt < attempts) {
        await sleep(delayMs);
      }
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Request failed.");
}

export function useHomeState() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [systemStatus, setSystemStatus] = useState<CodexStatus | null>(null);
  const [profile, setProfile] = useState<AppProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(summary === null && systemStatus === null && profile === null);
    setError(null);
    try {
      const [nextSummary, nextStatus, nextProfile] = await Promise.allSettled([
        retryRequest(() => api.getDashboardSummary(), 3, 250),
        retryRequest(() => api.getSystemStatus(), 2, 200),
        retryRequest(() => api.getProfile(), 2, 200),
      ]);
      const nextErrors: string[] = [];

      if (nextSummary.status === "fulfilled") {
        setSummary(nextSummary.value);
      } else {
        nextErrors.push(`Home summary: ${nextSummary.reason instanceof Error ? nextSummary.reason.message : "Failed to fetch"}`);
      }

      if (nextStatus.status === "fulfilled") {
        setSystemStatus(nextStatus.value);
      } else {
        nextErrors.push(`System status: ${nextStatus.reason instanceof Error ? nextStatus.reason.message : "Failed to fetch"}`);
      }

      if (nextProfile.status === "fulfilled") {
        setProfile(nextProfile.value);
      } else {
        nextErrors.push(`Profile: ${nextProfile.reason instanceof Error ? nextProfile.reason.message : "Failed to fetch"}`);
      }

      setError(nextErrors.length ? nextErrors.join(" ") : null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load Mission Control home state.");
    } finally {
      setLoading(false);
    }
  }, [profile, summary, systemStatus]);

  useEffect(() => {
    void reload();
  }, []);

  async function toggleProjectPin(projectId: number, pinned: boolean) {
    if (pinned) {
      await api.unpinProject(projectId);
    } else {
      await api.pinProject(projectId);
    }
    await reload();
  }

  return { summary, systemStatus, profile, loading, error, reload, toggleProjectPin };
}
