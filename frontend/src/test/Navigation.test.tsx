import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConsoleLayout } from "../layouts/ConsoleLayout";
import { SegmentedControl } from "../components/SegmentedControl";

const mocks = vi.hoisted(() => ({ role: "ADMIN" }));
vi.mock("../store/AuthContext", () => ({
  useAuth: () => ({ user: { name: "Interface tester", role: mocks.role }, logout: vi.fn() }),
}));
vi.mock("../store/LiveContext", () => ({ useLive: () => true }));
vi.mock("../hooks/useResource", () => ({
  useResource: () => ({ data: { demo_mode: false, live_monitoring: true } }),
}));

function workspace() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route element={<ConsoleLayout />}>
          <Route path="/dashboard" element={<h1>Overview content</h1>} />
          <Route path="/alerts" element={<h1>Alert content</h1>} />
          <Route path="/settings" element={<h1>Settings content</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("quick page navigation", () => {
  beforeEach(() => { mocks.role = "ADMIN"; });

  it("opens with the keyboard, focuses search, and navigates on Enter", () => {
    workspace();
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    const dialog = screen.getByRole("dialog", { name: "Go to a page" });
    const search = within(dialog).getByRole("textbox", { name: "Find a page" });
    expect(search).toHaveFocus();
    fireEvent.change(search, { target: { value: "alerts" } });
    expect(within(dialog).getByRole("button", { name: "Alerts" })).toBeVisible();
    fireEvent.submit(search.closest("form")!);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("heading", { name: "Alert content" })).toBeVisible();
  });

  it("limits read-only navigation to pages that role can open", () => {
    mocks.role = "VIEWER";
    workspace();
    fireEvent.click(screen.getByRole("button", { name: "Go to a page" }));
    const dialog = screen.getByRole("dialog");
    for (const name of ["Overview", "Alerts", "Investigations", "Settings"]) {
      expect(within(dialog).getByRole("button", { name })).toBeVisible();
    }
    for (const name of ["Activity", "Connected systems", "Assistant", "Alert rules", "Device list"]) {
      expect(within(dialog).queryByRole("button", { name })).toBeNull();
    }
  });

  it("handles no matches and arrow-key choices without submitting an action", () => {
    workspace();
    fireEvent.click(screen.getByRole("button", { name: "Go to a page" }));
    const search = screen.getByRole("textbox", { name: "Find a page" });
    fireEvent.change(search, { target: { value: "no matching page" } });
    expect(screen.getByText("No matching pages. Try a different name.")).toBeVisible();
    fireEvent.submit(search.closest("form")!);
    expect(screen.getByRole("dialog")).toBeVisible();
    fireEvent.change(search, { target: { value: "" } });
    fireEvent.keyDown(search, { key: "ArrowDown" });
    expect(screen.getByRole("button", { name: "Overview" })).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    expect(screen.getByRole("button", { name: "Alerts" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does not open over an existing dialog", () => {
    workspace();
    fireEvent.click(screen.getByRole("button", { name: "How to use SentinelX" }));
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getByRole("dialog", { name: "A simple guide to SentinelX" })).toBeVisible();
  });
});

it("uses named native radio controls without including decorative counts in their names", () => {
  const changed = vi.fn();
  render(<SegmentedControl label="Filter systems" value="all" onChange={changed} options={[
    { value: "all", label: "All systems", count: 3 },
    { value: "attention", label: "Needs attention", count: 1 },
  ]} />);
  expect(screen.getByRole("group", { name: "Filter systems" })).toBeVisible();
  expect(screen.getByRole("radio", { name: "All systems" })).toBeChecked();
  fireEvent.click(screen.getByRole("radio", { name: "Needs attention" }));
  expect(changed).toHaveBeenCalledWith("attention");
});
