import type { SystemInfo } from "../types";

export function assistantModeLabel(system?: SystemInfo | null): string {
  if (!system) return "Checking assistant setup…";
  if (system.ai_provider === "ollama") return "Local AI configured";
  if (system.ai_provider === "llm") return "Online AI configured";
  return "Offline review · no generative AI";
}
