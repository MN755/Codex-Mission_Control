import { WidgetSizeControl } from "./WidgetSizeControl";
import type { WidgetSize } from "../types";

export function WidgetSettingsMenu({
  size,
  canMoveUp,
  canMoveDown,
  onSizeChange,
  onMoveUp,
  onMoveDown,
  onRemove,
}: {
  size: WidgetSize;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onSizeChange: (size: WidgetSize) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
}) {
  return (
    <details className="widget-settings-menu">
      <summary className="workspace-icon-button" aria-label="Widget settings">
        ...
      </summary>
      <div className="widget-settings-menu__panel">
        <WidgetSizeControl value={size} onChange={onSizeChange} />
        <div className="widget-settings-menu__row">
          <button type="button" className="button-ghost" disabled={!canMoveUp} onClick={onMoveUp}>
            Move up
          </button>
          <button type="button" className="button-ghost" disabled={!canMoveDown} onClick={onMoveDown}>
            Move down
          </button>
        </div>
        <button type="button" className="button-ghost widget-settings-menu__danger" onClick={onRemove}>
          Remove widget
        </button>
      </div>
    </details>
  );
}
