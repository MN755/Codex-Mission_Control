import type { SVGProps } from "react";

type IconName =
  | "dashboard"
  | "handoffs"
  | "models"
  | "tools"
  | "diagnostics"
  | "settings"
  | "archive"
  | "project"
  | "health"
  | "runner"
  | "builds"
  | "accounts"
  | "attention"
  | "plus"
  | "pin"
  | "pinOff"
  | "share"
  | "more"
  | "check"
  | "review"
  | "pause"
  | "play"
  | "attach"
  | "sparkle"
  | "send"
  | "copy";

function StrokeIcon({
  children,
  className,
  ...props
}: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      {...props}
    >
      {children}
    </svg>
  );
}

export function CommandIcon({ name, className }: { name: IconName; className?: string }) {
  switch (name) {
    case "dashboard":
      return (
        <StrokeIcon className={className}>
          <path d="M4 12.5 12 5l8 7.5" />
          <path d="M6.5 10.5V19h11v-8.5" />
          <path d="M10 19v-5h4v5" />
        </StrokeIcon>
      );
    case "handoffs":
      return (
        <StrokeIcon className={className}>
          <path d="M6 8h9" />
          <path d="m12 4 4 4-4 4" />
          <path d="M18 16H9" />
          <path d="m12 12-4 4 4 4" />
        </StrokeIcon>
      );
    case "models":
      return (
        <StrokeIcon className={className}>
          <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" />
          <path d="m4 7.5 8 4.5 8-4.5" />
          <path d="M12 12v9" />
        </StrokeIcon>
      );
    case "tools":
      return (
        <StrokeIcon className={className}>
          <path d="m14.5 6.5 3 3" />
          <path d="m12 9 5.5-5.5a2.12 2.12 0 0 1 3 3L15 12" />
          <path d="m11 13-7.5 7.5" />
          <path d="M5 10 3.5 8.5a2.12 2.12 0 0 1 3-3L8 7" />
          <path d="m10 5 9 9" />
        </StrokeIcon>
      );
    case "diagnostics":
      return (
        <StrokeIcon className={className}>
          <path d="M3 12h4l2-5 4 10 2-5h6" />
        </StrokeIcon>
      );
    case "settings":
      return (
        <StrokeIcon className={className}>
          <circle cx="12" cy="12" r="3.2" />
          <path d="M19.4 15a1 1 0 0 0 .2 1.1l.1.1a1 1 0 0 1 0 1.4l-1.3 1.3a1 1 0 0 1-1.4 0l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9V20a1 1 0 0 1-1 1h-1.8a1 1 0 0 1-1-1v-.2a1 1 0 0 0-.6-.9 1 1 0 0 0-1.1.2l-.1.1a1 1 0 0 1-1.4 0l-1.3-1.3a1 1 0 0 1 0-1.4l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6H4a1 1 0 0 1-1-1v-1.8a1 1 0 0 1 1-1h.2a1 1 0 0 0 .9-.6 1 1 0 0 0-.2-1.1l-.1-.1a1 1 0 0 1 0-1.4l1.3-1.3a1 1 0 0 1 1.4 0l.1.1a1 1 0 0 0 1.1.2 1 1 0 0 0 .6-.9V4a1 1 0 0 1 1-1h1.8a1 1 0 0 1 1 1v.2a1 1 0 0 0 .6.9 1 1 0 0 0 1.1-.2l.1-.1a1 1 0 0 1 1.4 0l1.3 1.3a1 1 0 0 1 0 1.4l-.1.1a1 1 0 0 0-.2 1.1 1 1 0 0 0 .9.6h.2a1 1 0 0 1 1 1v1.8a1 1 0 0 1-1 1h-.2a1 1 0 0 0-.9.6Z" />
        </StrokeIcon>
      );
    case "archive":
      return (
        <StrokeIcon className={className}>
          <path d="M4 7h16v3H4z" />
          <path d="M6 10h12v9H6z" />
          <path d="M10 14h4" />
        </StrokeIcon>
      );
    case "project":
      return (
        <StrokeIcon className={className}>
          <rect x="4" y="5" width="16" height="14" rx="3" />
          <path d="M8 9h8" />
          <path d="M8 13h5" />
        </StrokeIcon>
      );
    case "health":
      return (
        <StrokeIcon className={className}>
          <path d="M3 12h4l2-4 3 8 2-4h7" />
        </StrokeIcon>
      );
    case "runner":
      return (
        <StrokeIcon className={className}>
          <rect x="4" y="5" width="16" height="14" rx="2.5" />
          <path d="M8 10h3" />
          <path d="m8 14 2-2-2-2" />
          <path d="M13 14h3" />
        </StrokeIcon>
      );
    case "builds":
      return (
        <StrokeIcon className={className}>
          <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" />
          <path d="m4 7.5 8 4.5 8-4.5" />
        </StrokeIcon>
      );
    case "accounts":
      return (
        <StrokeIcon className={className}>
          <circle cx="9" cy="9" r="2.5" />
          <circle cx="16" cy="10" r="2" />
          <path d="M5 18a4 4 0 0 1 8 0" />
          <path d="M14 18a3 3 0 0 1 5 0" />
        </StrokeIcon>
      );
    case "attention":
      return (
        <StrokeIcon className={className}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8v5" />
          <path d="M12 16.5h.01" />
        </StrokeIcon>
      );
    case "plus":
      return (
        <StrokeIcon className={className}>
          <path d="M12 5v14" />
          <path d="M5 12h14" />
        </StrokeIcon>
      );
    case "pin":
      return (
        <StrokeIcon className={className}>
          <path d="M15 4c0 1.6.8 3 2 4l-3 3v5l-2-2-2 2v-5L7 8c1.2-1 2-2.4 2-4" />
        </StrokeIcon>
      );
    case "pinOff":
      return (
        <StrokeIcon className={className}>
          <path d="M5 5 19 19" />
          <path d="m15 4-.1.7A6.1 6.1 0 0 0 17 8l-3 3v5l-2-2-2 2v-5L8 9.9" />
        </StrokeIcon>
      );
    case "share":
      return (
        <StrokeIcon className={className}>
          <circle cx="18" cy="5" r="2" />
          <circle cx="6" cy="12" r="2" />
          <circle cx="18" cy="19" r="2" />
          <path d="m8 12 8-6" />
          <path d="m8 12 8 6" />
        </StrokeIcon>
      );
    case "more":
      return (
        <StrokeIcon className={className}>
          <circle cx="6" cy="12" r="1.2" fill="currentColor" stroke="none" />
          <circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none" />
          <circle cx="18" cy="12" r="1.2" fill="currentColor" stroke="none" />
        </StrokeIcon>
      );
    case "check":
      return (
        <StrokeIcon className={className}>
          <path d="m5 12 4 4 10-10" />
        </StrokeIcon>
      );
    case "review":
      return (
        <StrokeIcon className={className}>
          <path d="M3 12h4l2-5 4 10 2-5h6" />
          <path d="m19 5-2 2-1-1" />
        </StrokeIcon>
      );
    case "pause":
      return (
        <StrokeIcon className={className}>
          <rect x="6.5" y="5" width="3.5" height="14" rx="1" />
          <rect x="14" y="5" width="3.5" height="14" rx="1" />
        </StrokeIcon>
      );
    case "play":
      return (
        <StrokeIcon className={className}>
          <path d="m8 6 10 6-10 6V6Z" />
        </StrokeIcon>
      );
    case "attach":
      return (
        <StrokeIcon className={className}>
          <path d="m9 12 5.5-5.5a3 3 0 1 1 4.2 4.2L10 19.4a5 5 0 1 1-7.1-7.1L12 3.2" />
        </StrokeIcon>
      );
    case "sparkle":
      return (
        <StrokeIcon className={className}>
          <path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3Z" />
          <path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" />
        </StrokeIcon>
      );
    case "send":
      return (
        <StrokeIcon className={className}>
          <path d="M4 12 20 4l-4 16-4.5-6L4 12Z" />
          <path d="M11.5 14 20 4" />
        </StrokeIcon>
      );
    case "copy":
      return (
        <StrokeIcon className={className}>
          <rect x="9" y="7" width="10" height="12" rx="2" />
          <path d="M6 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" />
        </StrokeIcon>
      );
    default:
      return null;
  }
}
