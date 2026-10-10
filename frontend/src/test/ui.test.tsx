import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalysisPanel } from "../components/AnalysisPanel";
import { Badge, Empty, Modal, Pagination } from "../components/ui";
import type { Analysis } from "../types";

describe("SOC interface primitives", () => {
  it("uses human-readable severity and status labels", () => {
    render(
      <>
        <Badge value="critical" severity />
        <Badge value="false_positive" />
      </>,
    );
    expect(screen.getByText("Urgent")).toHaveClass("severity-critical");
    expect(screen.getByText("Not an issue")).toBeInTheDocument();
  });
  it("paginates without crossing the beginning or end", () => {
    const change = vi.fn();
    render(<Pagination total={28} offset={25} setOffset={change} />);
    expect(screen.getByText("26–28 of 28")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(change).toHaveBeenCalledWith(0);
  });
  it("closes dialogs with Escape and exposes accessible semantics", () => {
    const close = vi.fn();
    render(
      <Modal title="Alert details" onClose={close}>
        <button>Investigate</button>
      </Modal>,
    );
    expect(
      screen.getByRole("dialog", { name: "Alert details" }),
    ).toHaveAttribute("aria-modal", "true");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(close).toHaveBeenCalledOnce();
  });
  it("renders unsafe log strings as text, not executable markup", () => {
    const text = "<script>window.compromised=true</script>";
    render(<Empty title="No matching events" description={text} />);
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });
  it("labels offline analysis and makes manual review explicit", () => {
    const analysis: Analysis = {
      summary: "Repeated failures.",
      likely_attack: "Possible brute-force activity.",
      evidence: ["EVT-00001: failed login"],
      affected_assets: ["lab"],
      mitre_techniques: ["T1110"],
      confidence: "low",
      recommended_investigation: ["Verify login ownership."],
      recommended_containment: ["Consider restrictions after approval."],
      false_positive_indicators: ["Lab simulation."],
      mode: "offline",
      model: null,
      notice: "No actions were executed.",
    };
    render(<AnalysisPanel analysis={analysis} />);
    expect(screen.getByText("Offline review · no online AI")).toBeInTheDocument();
    expect(
      screen.getByText("Protective steps to consider"),
    ).toBeInTheDocument();
    expect(screen.getByText(/authorized person/)).toBeInTheDocument();
  });
});
