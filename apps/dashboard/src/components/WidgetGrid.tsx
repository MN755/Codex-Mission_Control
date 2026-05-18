import { WidgetEmptyState } from "./WidgetEmptyState";
import { WidgetSettingsMenu } from "./WidgetSettingsMenu";
import { WidgetShell } from "./WidgetShell";
import type { WidgetDataResponse, WidgetInstance, WidgetSize } from "../types";

export function WidgetGrid({
  instances,
  dataByInstance,
  onCollapseToggle,
  onMove,
  onRemove,
  onRefresh,
  onSizeChange,
  renderBody,
}: {
  instances: WidgetInstance[];
  dataByInstance: Map<number, WidgetDataResponse>;
  onCollapseToggle: (instance: WidgetInstance) => void;
  onMove: (instance: WidgetInstance, direction: "up" | "down") => void;
  onRemove: (instance: WidgetInstance) => void;
  onRefresh: (instance: WidgetInstance) => void;
  onSizeChange: (instance: WidgetInstance, size: WidgetSize) => void;
  renderBody: (instance: WidgetInstance, data: WidgetDataResponse | undefined) => JSX.Element;
}) {
  const orderedInstances = [...instances].sort((left, right) => left.order_index - right.order_index || left.id - right.id);

  if (!orderedInstances.length) {
    return <WidgetEmptyState />;
  }

  return (
    <div className="widget-grid">
      {orderedInstances.map((instance, index) => {
        const data = dataByInstance.get(instance.id);
        return (
          <WidgetShell
            key={instance.id}
            title={data?.title ?? instance.widget_type}
            status={data?.status ?? "empty"}
            size={instance.size}
            collapsed={instance.collapsed}
            actions={
              <>
                <button type="button" className="workspace-icon-button" onClick={() => onRefresh(instance)} aria-label={`Refresh ${instance.widget_type}`}>
                  ↻
                </button>
                <button type="button" className="workspace-icon-button" onClick={() => onCollapseToggle(instance)} aria-label={`${instance.collapsed ? "Expand" : "Collapse"} ${instance.widget_type}`}>
                  {instance.collapsed ? "+" : "-"}
                </button>
                <WidgetSettingsMenu
                  size={instance.size}
                  canMoveUp={index > 0}
                  canMoveDown={index < orderedInstances.length - 1}
                  onSizeChange={(size) => onSizeChange(instance, size)}
                  onMoveUp={() => onMove(instance, "up")}
                  onMoveDown={() => onMove(instance, "down")}
                  onRemove={() => onRemove(instance)}
                />
              </>
            }
          >
            {renderBody(instance, data)}
          </WidgetShell>
        );
      })}
    </div>
  );
}
