import type { WidgetSize } from "../types";

const SIZE_OPTIONS: Array<{ value: WidgetSize; label: string }> = [
  { value: "small", label: "Small" },
  { value: "medium", label: "Medium" },
  { value: "large", label: "Large" },
  { value: "full", label: "Full" },
];

export function WidgetSizeControl({
  value,
  onChange,
}: {
  value: WidgetSize;
  onChange: (size: WidgetSize) => void;
}) {
  return (
    <label className="widget-settings-menu__field">
      <span>Size</span>
      <select value={value} onChange={(event) => onChange(event.target.value as WidgetSize)}>
        {SIZE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
