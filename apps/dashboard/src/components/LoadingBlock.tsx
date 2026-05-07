export function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="loading-block">
      <div className="loading-block__dot" />
      <span>{label}</span>
    </div>
  );
}

