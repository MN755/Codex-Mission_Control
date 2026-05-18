import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { HomeShell } from "../components/HomeShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import { useHomeState } from "../state/useHomeState";

export function ModelsRunnersLandingPage() {
  const navigate = useNavigate();
  const { summary, systemStatus, profile, loading, toggleProjectPin } = useHomeState();

  useEffect(() => {
    const target = summary?.sidebar_projects[0] ?? summary?.recent_projects[0] ?? null;
    if (target) {
      navigate(target.slug ? `/projects/${target.id}/${target.slug}/models-runners` : `/projects/${target.id}/models-runners`, {
        replace: true,
      });
    }
  }, [navigate, summary]);

  return (
    <HomeShell
      title="Models & Runners"
      subtitle="Models and runner settings stay project-scoped. Select a project context before editing them."
      summary={summary}
      systemStatus={systemStatus}
      profile={profile}
      onProjectPinToggle={toggleProjectPin}
    >
      {loading ? (
        <LoadingBlock label="Selecting a project for Models & Runners..." />
      ) : (
        <SectionCard title="Choose a project" subtitle="Models & Runners is project-specific by design.">
          {summary?.recent_projects.length ? (
            <div className="archive-list">
              {summary.recent_projects.map((project) => (
                <button
                  key={project.id}
                  type="button"
                  className="resume-item"
                  onClick={() =>
                    navigate(project.slug ? `/projects/${project.id}/${project.slug}/models-runners` : `/projects/${project.id}/models-runners`)
                  }
                >
                  <strong>{project.name}</strong>
                  <span>{project.display_status}</span>
                  <small>{project.latest_activity ?? "Open this project to edit model and runner defaults."}</small>
                </button>
              ))}
            </div>
          ) : (
            <p className="section-footnote">Create a project first, then open Models & Runners from that project context.</p>
          )}
        </SectionCard>
      )}
    </HomeShell>
  );
}
