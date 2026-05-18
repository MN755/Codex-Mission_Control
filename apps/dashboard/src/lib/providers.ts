import type { ProviderId } from "../types";

export function providerLabel(provider: ProviderId | string | null | undefined): string {
  const normalized = String(provider ?? "").toLowerCase();
  if (normalized.includes("claude")) {
    return "Claude Code";
  }
  if (normalized.includes("ollama")) {
    return "Ollama / Local Models";
  }
  if (normalized.includes("anthropic")) {
    return "Anthropic API";
  }
  if (normalized.includes("openai")) {
    return "OpenAI API";
  }
  if (normalized.includes("xai")) {
    return "xAI API";
  }
  if (normalized.includes("custom") || normalized.includes("adapter")) {
    return "Other / Custom";
  }
  switch (provider) {
    case "codex":
      return "Codex via ChatGPT Login";
    case "ollama":
      return "Ollama / Local Models";
    case "openai_api":
      return "OpenAI API";
    case "anthropic_api":
      return "Anthropic API";
    case "xai_api":
      return "xAI API";
    case "claude_code":
      return "Claude Code";
    case "custom":
      return "Other / Custom";
    default:
      return "Codex via ChatGPT Login";
  }
}

export function providerDefaultLabel(provider: ProviderId | string | null | undefined): string {
  return `${providerLabel(provider)} default`;
}

export function providerUsesAdapter(provider: ProviderId | string | null | undefined): boolean {
  return !["codex", "claude_code"].includes(String(provider ?? ""));
}

export const PROVIDER_OPTIONS: Array<{ value: ProviderId; label: string; description: string; recommended?: boolean }> = [
  {
    value: "codex",
    label: "Codex via ChatGPT Login",
    description: "Recommended. Uses the local Codex or ChatGPT sign-in flow when supported.",
    recommended: true,
  },
  {
    value: "ollama",
    label: "Ollama / Local Models",
    description: "Local-first. Use a local Ollama endpoint and adapter workflow.",
  },
  {
    value: "openai_api",
    label: "OpenAI API",
    description: "API-key based provider path. Keys are not stored in Mission Control.",
  },
  {
    value: "anthropic_api",
    label: "Anthropic API",
    description: "API-key based provider path. Configure credentials outside the app.",
  },
  {
    value: "xai_api",
    label: "xAI API",
    description: "API-key based provider path. Configure credentials outside the app.",
  },
  {
    value: "claude_code",
    label: "Claude Code",
    description: "Use the local Claude Code CLI and its own login flow.",
  },
  {
    value: "custom",
    label: "Other / Custom",
    description: "Use a local wrapper command or adapter for another provider.",
  },
];
