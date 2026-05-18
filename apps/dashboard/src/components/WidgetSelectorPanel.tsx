import { SectionCard } from "./SectionCard";
import type { WidgetDefinition, WidgetScope } from "../types";

export function WidgetSelectorPanel({
  scope,
  catalog,
  addedWidgetTypes,
  onAdd,
}: {
  scope: WidgetScope;
  catalog: WidgetDefinition[];
  addedWidgetTypes: string[];
  onAdd: (widgetType: string) => void;
}) {
  return (
    <div className="widget-selector-panel">
      <SectionCard
        title="Widget Selector"
        subtitle={
          scope === "dashboard"
            ? "Add or remove global command-center widgets without turning the dashboard into a landfill."
            : "Add project widgets without stuffing every project detail into one fixed sidebar."
        }
      >
        <div className="widget-selector-panel__grid">
          {catalog.map((definition) => {
            const added = addedWidgetTypes.includes(definition.widget_type);
            const unavailable = definition.coming_soon;
            return (
              <article key={definition.widget_type} className={`widget-selector-card${added ? " widget-selector-card--active" : ""}`}>
                <div className="widget-selector-card__top">
                  <div>
                    <strong>{definition.title}</strong>
                    <span>{definition.category}</span>
                  </div>
                  <span className={`status-pill ${unavailable ? "status-idle" : added ? "status-done" : "status-working"}`}>
                    {unavailable ? "Unavailable" : added ? "Added" : "Available"}
                  </span>
                </div>
                <p>{definition.description}</p>
                <div className="widget-selector-card__footer">
                  <small>{definition.scope}</small>
                  <button type="button" className="button-ghost" disabled={added || unavailable} onClick={() => onAdd(definition.widget_type)}>
                    {unavailable ? "Coming soon" : added ? "Added" : "Add widget"}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </SectionCard>
    </div>
  );
}
