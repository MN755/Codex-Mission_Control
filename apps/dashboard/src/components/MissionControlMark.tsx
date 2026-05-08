export function MissionControlMark({ className = "brand-mark", alt = "Codex Mission Control" }: { className?: string; alt?: string }) {
  return <img className={className} src="/mission-control-mark.svg" alt={alt} />;
}
