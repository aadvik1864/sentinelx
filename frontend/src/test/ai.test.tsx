import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisPanel } from "../components/AnalysisPanel";
import { assistantModeLabel } from "../utils/ai";
import type { Analysis, SystemInfo } from "../types";

describe("assistant provider labels", () => {
  const system: SystemInfo = {
    version: "test", environment: "test", demo_mode: false,
    ai_provider: "offline", threat_intel_provider: "unconfigured",
  };
  it("does not confuse local AI, external AI, and programmed summaries", () => {
    expect(assistantModeLabel()).toBe("Checking assistant setup…");
    expect(assistantModeLabel(system)).toContain("no generative AI");
    expect(assistantModeLabel({ ...system, ai_provider: "ollama" })).toBe("Local AI configured");
    expect(assistantModeLabel({ ...system, ai_provider: "llm" })).toBe("Online AI configured");
  });
  it("clearly labels local generative output and manual action", () => {
    const analysis: Analysis = {
      summary: "One rejected sign-in.", likely_attack: "Not established.",
      evidence: ["EVT-00001: rejected sign-in."], affected_assets: ["lab"],
      mitre_techniques: [], confidence: "low", recommended_investigation: [],
      recommended_containment: [], false_positive_indicators: [],
      mode: "llm", provider: "ollama", model: "qwen3:4b",
      notice: "Selected evidence stayed on this installation. No actions were executed.",
    };
    render(<AnalysisPanel analysis={analysis} />);
    expect(screen.getByText("Local AI analysis · qwen3:4b")).toBeInTheDocument();
    expect(screen.getByText(/authorized person/)).toBeInTheDocument();
    expect(screen.queryByText(/no online AI/)).toBeNull();
  });
});
