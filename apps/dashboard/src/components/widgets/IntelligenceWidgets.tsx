function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "Unknown";
  }
  return `${value}`;
}

function titleCase(value: string | null | undefined): string {
  return String(value ?? "")
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

function ListWidget({ items }: { items: Array<{ title?: unknown; detail?: unknown }> }) {
  return (
    <div className="mission-widget-list">
      {items.map((item, index) => (
        <article key={`${String(item.title)}-${index}`} className="mission-widget-list__item">
          <strong>{String(item.title ?? "Item")}</strong>
          <span>{String(item.detail ?? "")}</span>
        </article>
      ))}
    </div>
  );
}

function FactRows({ rows }: { rows: Array<{ label: string; value: string }> }) {
  return (
    <div className="mission-widget-facts">
      {rows.map((row) => (
        <div key={row.label} className="mission-widget-facts__row">
          <span>{row.label}</span>
          <strong>{row.value}</strong>
        </div>
      ))}
    </div>
  );
}

export function ModelCapabilityMatrixWidget({
  payload,
}: {
  payload: Record<string, unknown>;
}) {
  const categories = Array.isArray(payload.categories) ? (payload.categories as string[]) : [];
  const rows = Array.isArray(payload.rows) ? (payload.rows as Array<Record<string, unknown>>) : [];
  const recommendationNote = String(payload.recommendation_note ?? "");

  return (
    <>
      <div className="mission-widget-list">
        {rows.map((row, index) => {
          const scores = (row.scores as Record<string, number | null> | undefined) ?? {};
          return (
            <article key={`${String(row.provider)}-${String(row.model)}-${index}`} className="mission-widget-list__item">
              <strong>
                {String(row.provider)} / {String(row.model)}
              </strong>
              <span>
                {String(row.runner_mode)} • {categories.map((category) => `${titleCase(category)}: ${formatScore(scores[category])}`).join(" • ")}
              </span>
            </article>
          );
        })}
      </div>
      {recommendationNote ? <p className="section-footnote">{recommendationNote}</p> : null}
    </>
  );
}

export function AgentReputationWidget({
  payload,
}: {
  payload: Record<string, unknown>;
}) {
  const items = Array.isArray(payload.items) ? (payload.items as Array<{ title?: unknown; detail?: unknown }>) : [];
  const weakSpots = Array.isArray(payload.weak_spots) ? (payload.weak_spots as unknown[]) : [];
  return (
    <>
      <ListWidget items={items} />
      {weakSpots.length ? <p className="section-footnote">Weak spots: {weakSpots.map((item) => String(item)).join(", ")}</p> : null}
    </>
  );
}

export function ProjectPlaybookWidget({
  payload,
  onRevise,
}: {
  payload: Record<string, unknown>;
  onRevise?: () => void;
}) {
  const risks = Array.isArray(payload.common_risks) ? (payload.common_risks as unknown[]) : [];
  const validation = Array.isArray(payload.validation) ? (payload.validation as Array<Record<string, unknown>>) : [];
  return (
    <>
      <FactRows
        rows={[
          { label: "Playbook", value: String(payload.playbook_name ?? payload.playbook_key ?? "Unknown") },
          { label: "Status", value: titleCase(String(payload.status ?? "suggested")) },
          { label: "Validation recipe", value: `${validation.length}` },
        ]}
      />
      <p className="section-footnote">{String(payload.why ?? "No playbook rationale recorded yet.")}</p>
      {risks.length ? <p className="section-footnote">Common risks: {risks.map((item) => String(item)).join(", ")}</p> : null}
      {onRevise ? (
        <div className="mission-widget-actions">
          <button type="button" className="button-ghost" onClick={onRevise}>
            Ask Manager to revise
          </button>
        </div>
      ) : null}
    </>
  );
}

export function ContextPacksWidget({
  payload,
}: {
  payload: Record<string, unknown>;
}) {
  const items = Array.isArray(payload.items) ? (payload.items as Array<{ title?: unknown; detail?: unknown }>) : [];
  return <ListWidget items={items} />;
}

export function RiskRegisterWidget({
  payload,
  onMitigation,
}: {
  payload: Record<string, unknown>;
  onMitigation?: () => void;
}) {
  const items = Array.isArray(payload.items) ? (payload.items as Array<{ title?: unknown; detail?: unknown }>) : [];
  return (
    <>
      <ListWidget items={items} />
      {onMitigation ? (
        <div className="mission-widget-actions">
          <button type="button" className="button-ghost" onClick={onMitigation}>
            Ask Manager for mitigation plan
          </button>
        </div>
      ) : null}
    </>
  );
}

export function ScopeCreepWidget({
  payload,
}: {
  payload: Record<string, unknown>;
}) {
  const items = Array.isArray(payload.items) ? (payload.items as Array<{ title?: unknown; detail?: unknown }>) : [];
  return <ListWidget items={items} />;
}

export function LaunchSimulationWidget({
  payload,
  onRevise,
}: {
  payload: Record<string, unknown>;
  onRevise?: () => void;
}) {
  const conflicts = Array.isArray(payload.conflicts) ? (payload.conflicts as unknown[]) : [];
  const bottlenecks = Array.isArray(payload.bottlenecks) ? (payload.bottlenecks as unknown[]) : [];
  const order = Array.isArray(payload.recommended_launch_order) ? (payload.recommended_launch_order as Array<Record<string, unknown>>) : [];
  return (
    <>
      <FactRows
        rows={[
          { label: "Safe to launch", value: String(payload.safe_to_launch_count ?? 0) },
          { label: "Should wait", value: String(payload.should_wait_count ?? 0) },
          { label: "Approvals needed", value: String(payload.needs_user_approval_count ?? 0) },
        ]}
      />
      {conflicts.length ? <p className="section-footnote">Conflicts: {conflicts.map((item) => String(item)).join(", ")}</p> : null}
      {bottlenecks.length ? <p className="section-footnote">Bottlenecks: {bottlenecks.map((item) => String(item)).join(", ")}</p> : null}
      {order.length ? (
        <ListWidget
          items={order.map((item) => ({
            title: item.name,
            detail: `${titleCase(String(item.spawn_phase ?? "unknown"))} • ${titleCase(String(item.status ?? "launch"))}`,
          }))}
        />
      ) : null}
      {onRevise ? (
        <div className="mission-widget-actions">
          <button type="button" className="button-ghost" onClick={onRevise}>
            Ask Manager to revise swarm
          </button>
        </div>
      ) : null}
    </>
  );
}

export function ValidationCoverageWidget({
  payload,
  onImprove,
}: {
  payload: Record<string, unknown>;
  onImprove?: () => void;
}) {
  const items = Array.isArray(payload.items) ? (payload.items as Array<{ title?: unknown; detail?: unknown }>) : [];
  const gaps = Array.isArray(payload.gaps) ? (payload.gaps as unknown[]) : [];
  return (
    <>
      <ListWidget items={items} />
      {gaps.length ? <p className="section-footnote">Gaps: {gaps.map((item) => String(item)).join(", ")}</p> : null}
      {onImprove ? (
        <div className="mission-widget-actions">
          <button type="button" className="button-ghost" onClick={onImprove}>
            Ask Manager to improve validation
          </button>
        </div>
      ) : null}
    </>
  );
}

export function PreferenceMemoryWidget({
  payload,
}: {
  payload: Record<string, unknown>;
}) {
  const items = Array.isArray(payload.items) ? (payload.items as Array<{ title?: unknown; detail?: unknown }>) : [];
  return <ListWidget items={items} />;
}

export function IntelligenceListWidget({
  payload,
}: {
  payload: Record<string, unknown>;
}) {
  const items = Array.isArray(payload.items) ? (payload.items as Array<{ title?: unknown; detail?: unknown }>) : [];
  return <ListWidget items={items} />;
}
