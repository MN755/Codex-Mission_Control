const DEFAULT_EMPTY_MESSAGE = "Select the plus symbol in the bottom-right corner to add customizable widgets!";

export function WidgetEmptyState({ message = DEFAULT_EMPTY_MESSAGE }: { message?: string }) {
  return (
    <div className="widget-empty-state">
      <p>{message}</p>
    </div>
  );
}
