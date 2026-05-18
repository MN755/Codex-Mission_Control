import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { HomeShell } from "../components/HomeShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import { useHomeState } from "../state/useHomeState";
import type { HandoffListItem } from "../types";

function projectPath(projectId: number, slug?: string | null): string {
  return slug ? `/projects/${projectId}/${slug}` : `/projects/${projectId}`;
}

export function HandoffsPage() {
  const navigate = useNavigate();
  const { summary, systemStatus, profile, toggleProjectPin } = useHomeState();
  const [handoffs, setHandoffs] = useState<HandoffListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setHandoffs(await api.listHandoffs());
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  async function copyInstructions(handoff: HandoffListItem) {
    await navigator.clipboard.writeText(handoff.run_instructions.join("\n"));
    setNotice(`Copied run instructions for ${handoff.project_name}.`);
  }

  return (
    <HomeShell
      title="Handoffs"
      subtitle="Completed handoffs across projects stay visible here with artifacts, run instructions, and known limitations."
      summary={summary}
      systemStatus={systemStatus}
      profile={profile}
      onProjectPinToggle={toggleProjectPin}
    >
      {loading ? (
        <LoadingBlock label="Loading handoffs..." />
      ) : (
        <SectionCard title="Completed handoffs" subtitle="Handoffs are derived from real final reports, not a separate fake tracker.">
          {handoffs.length ? (
            <div className="archive-list">
              {handoffs.map((handoff) => (
                <article key={`${handoff.project_id}-${handoff.created_at}`} className="archive-card">
                  <div className="archive-card__top">
                    <div>
                      <strong>{handoff.project_name}</strong>
                      <p>{handoff.status}</p>
                    </div>
                    <span>{new Date(handoff.created_at).toLocaleString()}</span>
                  </div>
                  <p>{handoff.summary}</p>
                  <div className="archive-card__meta">
                    <span>Artifacts: {handoff.artifacts_path ?? "Not recorded"}</span>
                    <span>Tests: {handoff.tests_count}</span>
                  </div>
                  {handoff.known_limitations.length ? (
                    <ul className="flat-list">
                      {handoff.known_limitations.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : null}
                  <div className="button-row">
                    <button type="button" onClick={() => navigate(projectPath(handoff.project_id, handoff.project_slug))}>
                      Open project
                    </button>
                    <button type="button" className="button-ghost" onClick={() => navigate(`/projects/${handoff.project_id}/handoff`)}>
                      Open handoff
                    </button>
                    <button type="button" className="button-ghost" onClick={() => void copyInstructions(handoff)} disabled={!handoff.run_instructions.length}>
                      Copy run instructions
                    </button>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <p className="section-footnote">No completed handoffs are recorded yet. Finish a project build to populate this view.</p>
          )}
          {notice ? <p className="section-footnote">{notice}</p> : null}
        </SectionCard>
      )}
    </HomeShell>
  );
}
