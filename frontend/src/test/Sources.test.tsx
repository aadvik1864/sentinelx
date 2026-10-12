import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Link, MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SourceHealth } from "../components/SourceHealth";
import { SourcesPage } from "../pages/Sources";
import type { LogSource } from "../types";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
  role: "ADMIN",
  sources: [] as LogSource[],
}));
vi.mock("../store/AuthContext", () => ({
  useAuth: () => ({ user: { role: mocks.role } }),
}));
vi.mock("../hooks/useResource", () => ({
  useResource: () => ({
    data: { items: mocks.sources }, error: null, loading: false, reload: vi.fn(),
  }),
}));
vi.mock("../services/api", () => ({
  api: { post: mocks.post, patch: mocks.patch },
  reconcile: vi.fn(),
  errorMessage: () => "Request failed",
}));
vi.mock("motion/react", async (importOriginal) => ({
  ...await importOriginal<typeof import("motion/react")>(),
  useReducedMotion: () => true,
}));

const source: LogSource = {
  id: 7, name: "My site", kind: "nginx", hostname: "web-server",
  log_path: "/var/log/nginx/mysite.log", enabled: true, status: "waiting",
  last_heartbeat_at: "2026-10-08T10:00:00Z", last_event_at: null,
  last_event_timestamp: null, last_error: "", total_events: 0,
};
function page() {
  return render(<MemoryRouter><SourcesPage /></MemoryRouter>);
}
async function fillConnection() {
  fireEvent.click(screen.getAllByRole("button", { name: "Connect a system" })[0]);
  fireEvent.click(screen.getByRole("radio", { name: /Web app/ }));
  fireEvent.change(screen.getByLabelText("Name for this system"), {
    target: { value: "My app" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  const computer = await screen.findByLabelText("Computer name");
  fireEvent.change(computer, { target: { value: "app-server" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Check your connection details" });
}

describe("guided source onboarding", () => {
  beforeEach(() => {
    mocks.role = "ADMIN";
    mocks.sources = [];
    mocks.post.mockReset();
    mocks.patch.mockReset();
  });

  it("explains the need for activity files and server access", () => {
    page();
    fireEvent.click(screen.getByText("How does connecting a system work?"));
    expect(screen.getByText(/A website address alone is not enough/)).toBeVisible();
    expect(screen.getByText(/you have permission to monitor/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Connect your first system" })).toBeVisible();
  });

  it("gates steps and does not create a connection before review", async () => {
    page();
    fireEvent.click(screen.getAllByRole("button", { name: "Connect a system" })[0]);
    expect(screen.getByRole("button", { name: "Step 3: Review" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/at least two characters/);
    fireEvent.change(screen.getByLabelText("Name for this system"), {
      target: { value: "My server" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByLabelText("Computer name");
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Enter the computer name/);
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("preserves the app format and requires saving one-time private settings", async () => {
    mocks.post.mockResolvedValue({
      data: {
        source: { ...source, kind: "application", name: "My app" },
        collector_key: "test-only-source-key",
      },
    });
    page();
    await fillConnection();
    expect(mocks.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/sources", {
      name: "My app", kind: "application", hostname: "app-server",
      log_path: "/var/log/myapp/security.jsonl",
    }));
    expect(await screen.findByRole("button", { name: "Download connection settings" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    expect(screen.getByText(/cannot be downloaded again/)).toBeVisible();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("heading", { name: "Have you saved the private settings?" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Go back and save settings" }));
    expect(screen.getByRole("button", { name: "Download connection settings" })).toBeVisible();
  });

  it("preserves details when going back and displays errors without leaving review", async () => {
    mocks.post.mockRejectedValue(new Error("Server unavailable"));
    page();
    await fillConnection();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByLabelText("Computer name")).toHaveValue("app-server");
    expect(screen.getByLabelText("Activity file location")).toHaveValue("/var/log/myapp/security.jsonl");
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(await screen.findByRole("button", { name: "Save connection" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed");
    expect(screen.getByRole("heading", { name: "Check your connection details" })).toBeVisible();
  });

  it("requires confirmation before disabling an existing connection key", async () => {
    mocks.sources = [source];
    mocks.post.mockResolvedValue({ data: { source, collector_key: "replacement-test-key" } });
    page();
    expect(screen.getByRole("link", { name: "View activity" })).toHaveAttribute("href", "/events?source_id=7");
    fireEvent.click(screen.getByText("Connection details and settings"));
    fireEvent.click(screen.getByRole("button", { name: "Replace connection key" }));
    expect(mocks.post).not.toHaveBeenCalled();
    expect(screen.getByText(/old key for My site stops working immediately/)).toBeVisible();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Replace connection key" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/sources/7/rotate-key", { overlap_seconds: 0 }));
  });

  it("lets investigators view connection instructions without managing collection", () => {
    mocks.role = "ANALYST";
    mocks.sources = [source];
    page();
    expect(screen.getByText("Connected", { exact: true })).toBeVisible();
    fireEvent.click(screen.getByText("Connection details and settings"));
    expect(screen.getByRole("button", { name: "Setup instructions" })).toBeVisible();
    for (const name of ["Connect a system", "Replace connection key", "Pause collection"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("shows an outage instead of describing a disconnected system as quiet", () => {
    render(<MemoryRouter><SourceHealth sources={[{ ...source, status: "offline" }]} /></MemoryRouter>);
    expect(screen.getByText("Disconnected")).toBeVisible();
    expect(screen.getByText("No activity received yet")).toBeVisible();
  });

  it("filters connection issues and searches names without changing any source", () => {
    mocks.sources = [
      source,
      { ...source, id: 8, name: "Disconnected app", kind: "application", hostname: "app-server", status: "offline" },
      { ...source, id: 9, name: "Busy computer", kind: "linux", hostname: "linux-server", status: "receiving" },
    ];
    page();
    fireEvent.click(screen.getByRole("radio", { name: "Needs attention" }));
    expect(screen.getByRole("heading", { name: "Disconnected app" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "My site" })).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Showing 1 of 3 systems");
    fireEvent.click(screen.getByRole("radio", { name: "All systems" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Find a system" }), { target: { value: "linux-server" } });
    expect(screen.getByRole("heading", { name: "Busy computer" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Disconnected app" })).toBeNull();
    expect(mocks.patch).not.toHaveBeenCalled();
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("clears an empty filter without pretending the workspace has no systems", () => {
    mocks.sources = [source];
    page();
    fireEvent.click(screen.getByRole("radio", { name: "Paused" }));
    expect(screen.getByRole("heading", { name: "No systems match these filters" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Connect your first system" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByRole("heading", { name: "My site" })).toBeVisible();
    expect(screen.getByRole("radio", { name: "All systems" })).toBeChecked();
  });

  it("updates search from an external page link and clears its local text", () => {
    mocks.sources = [source];
    render(<MemoryRouter initialEntries={["/sources?q=missing"]}>
      <Link to="/sources?q=web-server">Open linked system</Link>
      <SourcesPage />
    </MemoryRouter>);
    expect(screen.getByRole("textbox", { name: "Find a system" })).toHaveValue("missing");
    fireEvent.click(screen.getByRole("link", { name: "Open linked system" }));
    expect(screen.getByRole("textbox", { name: "Find a system" })).toHaveValue("web-server");
    expect(screen.getByRole("heading", { name: "My site" })).toBeVisible();
    fireEvent.click(screen.getByRole("radio", { name: "Paused" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByRole("textbox", { name: "Find a system" })).toHaveValue("");
    expect(screen.getByRole("heading", { name: "My site" })).toBeVisible();
  });
});
