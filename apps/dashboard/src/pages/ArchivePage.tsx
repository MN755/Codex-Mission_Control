import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { HomeShell } from "../components/HomeShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import { useHomeState } from "../state/useHomeState";
import type { Project } from "../types";

function projectPath(project: Project): string {
  return project.slug ? `/projects/${project.id}/${project.slug}` : `/projects/${project.id}`;
}

export function ArchivePage() {
  const navigate = useNavigate();
  const { summary, systemStatus, profile, toggleProjectPin } = useHomeState();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("last_opened");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    async function load() {
      try {
        setProjects(await api.listProjects(true));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  const filtered = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return projects
      .filter((project) => project.archived_at || !summary?.sidebar_projects.some((item) => item.id === project.id))
      .filter((project) => (statusFilter === "all" ? true : project.display_status === statusFilter))
      .filter((project) =>
        normalizedSearch ? `${project.name} ${project.latest_activity ?? ""}`.toLowerCase().includes(normalizedSearch) : true,
      )
      .sort((left, right) => {
        if (sortBy === "name") {
          return left.name.localeCompare(right.name);
        }
        if (sortBy === "status") {
          return left.display_status.localeCompare(right.display_status);
        }
        if (sortBy === "created") {
          return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
        }
        return new Date(right.last_opened_at ?? right.updated_at).getTime() - new Date(left.last_opened_at ?? left.updated_at).getTime();
      });
  }, [projects, search, sortBy, statusFilter, summary?.sidebar_projects]);

  async function refresh() {
    setProjects(await api.listProjects(true));
  }

  async function toggleArchive(project: Project) {
    if (project.archived_at) {
      await api.unarchiveProject(project.id);
    } else {
      await api.archiveProject(project.id);
    }
    await refresh();
  }

  async function togglePin(project: Project) {
    if (project.pinned) {
      await api.unpinProject(project.id);
    } else {
      await api.pinProject(project.id);
    }
    await refresh();
  }

  return (
    <HomeShell
      title="Archive"
      subtitle="Overflow projects and archived workspaces live here so the main sidebar stays focused on at most three active entries."
      summary={summary}
      systemStatus={systemStatus}
      profile={profile}
      onProjectPinToggle={toggleProjectPin}
    >
      {loading ? (
        <LoadingBlock label="Loading archive..." />
      ) : (
        <SectionCard title="Project archive" subtitle="Search, sort, filter, and restore projects without relying on names alone.">
          <div className="form-row">
            <label>
              Search
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by name or recent activity" />
            </label>
            <label>
              Sort by
              <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
                <option value="last_opened">last opened</option>
                <option value="created">created date</option>
                <option value="status">status</option>
                <option value="name">name</option>
              </select>
            </label>
            <label>
              Status
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">all</option>
                <option value="planning">planning</option>
                <option value="interviewing">interviewing</option>
                <option value="building">building</option>
                <option value="blocked">blocked</option>
                <option value="ready_for_handoff">ready_for_handoff</option>
                <option value="archived">archived</option>
              </select>
            </label>
          </div>
          <div className="archive-list">
            {filtered.length ? (
              filtered.map((project) => (
                <article key={project.id} className="archive-card">
                  <div className="archive-card__top">
                    <div>
                      <strong>{project.name}</strong>
                      <p>{project.display_status}</p>
                    </div>
                    {project.pinned ? <span className="header-chip">Pinned</span> : null}
                  </div>
                  <p>{project.latest_activity ?? project.idea}</p>
                  <div className="archive-card__meta">
                    <span>{project.latest_milestone ?? "No milestone recorded."}</span>
                    <span>{project.last_opened_at ? `Opened ${new Date(project.last_opened_at).toLocaleString()}` : "Never opened"}</span>
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={() => navigate(projectPath(project))}>
                      Open
                    </button>
                    <button type="button" className="button-ghost" onClick={() => void togglePin(project)}>
                      {project.pinned ? "Unpin" : "Restore to sidebar"}
                    </button>
                    <button type="button" className="button-ghost" onClick={() => void toggleArchive(project)}>
                      {project.archived_at ? "Unarchive" : "Archive"}
                    </button>
                  </div>
                </article>
              ))
            ) : (
              <p className="section-footnote">No archived or overflow projects match the current filters.</p>
            )}
          </div>
        </SectionCard>
      )}
    </HomeShell>
  );
}
