import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import { HomeShell } from "../components/HomeShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import { useHomeState } from "../state/useHomeState";
import type { SkillEntry, ToolCatalogItem, ToolPermissionPolicy } from "../types";

export function SkillsToolsPage() {
  const { summary, systemStatus, profile, toggleProjectPin } = useHomeState();
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [skills, setSkills] = useState<SkillEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    const [nextTools, nextSkills] = await Promise.all([api.getTools(), api.getSkills()]);
    setTools(nextTools);
    setSkills(nextSkills);
    setLoading(false);
  }

  useEffect(() => {
    void load();
  }, []);

  const groupedTools = useMemo(() => {
    return tools.reduce<Record<string, ToolCatalogItem[]>>((accumulator, tool) => {
      accumulator[tool.category] = accumulator[tool.category] ?? [];
      accumulator[tool.category].push(tool);
      return accumulator;
    }, {});
  }, [tools]);

  async function updatePermission(toolId: string, permissionPolicy: ToolPermissionPolicy) {
    await api.updateToolPermission(toolId, permissionPolicy);
    await load();
  }

  return (
    <HomeShell
      title="Skills & Tools"
      subtitle="Tool availability, risk, and permissions stay honest here. Unsupported environments are marked instead of faked."
      summary={summary}
      systemStatus={systemStatus}
      profile={profile}
      onProjectPinToggle={toggleProjectPin}
    >
      {loading ? (
        <LoadingBlock label="Loading skills and tools..." />
      ) : (
        <div className="intake-grid">
          <SectionCard title="Tool catalog" subtitle="Permission changes are persisted locally at the app level.">
            <div className="tool-groups">
              {Object.entries(groupedTools).map(([category, items]) => (
                <div key={category} className="tool-group">
                  <h3>{category}</h3>
                  <div className="archive-list">
                    {items.map((tool) => (
                      <article key={tool.id} className="archive-card">
                        <div className="archive-card__top">
                          <div>
                            <strong>{tool.name}</strong>
                            <p>{tool.summary}</p>
                          </div>
                          <span className={`status-pill status-${tool.risk_level}`}>{tool.risk_level}</span>
                        </div>
                        <div className="archive-card__meta">
                          <span>Availability: {tool.availability}</span>
                        </div>
                        {tool.notes.length ? (
                          <ul className="flat-list">
                            {tool.notes.map((note) => (
                              <li key={note}>{note}</li>
                            ))}
                          </ul>
                        ) : null}
                        <label>
                          Permission policy
                          <select
                            value={tool.permission_policy}
                            onChange={(event) => void updatePermission(tool.id, event.target.value as ToolPermissionPolicy)}
                          >
                            <option value="ask_every_time">ask_every_time</option>
                            <option value="ask_once_per_project">ask_once_per_project</option>
                            <option value="allow_for_project">allow_for_project</option>
                            <option value="never_allow">never_allow</option>
                          </select>
                        </label>
                      </article>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Local skills" subtitle="Mission Control skills are listed directly. External Codex skills still depend on local Codex configuration.">
            {skills.length ? (
              <div className="archive-list">
                {skills.map((skill) => (
                  <article key={skill.name} className="archive-card">
                    <div className="archive-card__top">
                      <strong>{skill.name}</strong>
                      <span>{skill.source}</span>
                    </div>
                    <p>{skill.summary ?? "Available through local skill configuration."}</p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="section-footnote">No local skills were reported by the current runtime.</p>
            )}
          </SectionCard>
        </div>
      )}
    </HomeShell>
  );
}
