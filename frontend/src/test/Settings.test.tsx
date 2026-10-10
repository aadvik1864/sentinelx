import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "../pages/Settings";

const mocks = vi.hoisted(() => ({ post: vi.fn(), role: "ADMIN", reload: vi.fn() }));
vi.mock("../store/AuthContext", () => ({ useAuth: () => ({ user: { id: 1, name: "Administrator", role: mocks.role } }) }));
vi.mock("../hooks/useResource", () => ({ useResource: () => ({ data: { items: [] }, error: null, reload: mocks.reload }) }));
vi.mock("../services/api", () => ({ api: { post: mocks.post }, applySession: vi.fn(), reconcile: vi.fn(), errorMessage: () => "Request failed" }));

describe("administrator account admission", () => {
  beforeEach(() => { mocks.role = "ADMIN"; mocks.post.mockReset(); mocks.reload.mockReset(); });
  it("does not expose account creation to other roles", () => {
    mocks.role = "ANALYST";
    render(<SettingsPage />);
    expect(screen.queryByRole("button", { name: "Add a person" })).toBeNull();
  });
  it("requires an explicit trust acknowledgement and creates only read-only access", async () => {
    mocks.post.mockResolvedValue({ data: { id: 4, role: "VIEWER" } });
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Add a person" }));
    expect(screen.getByText(/not a private personal workspace/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Create read-only account" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Trusted teammate" } });
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "teammate@example.com" } });
    fireEvent.change(screen.getByLabelText("Starter password"), { target: { value: "Test-only-password-123!" } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Create read-only account" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/users", { name: "Trusted teammate", email: "teammate@example.com", password: "Test-only-password-123!" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mocks.reload).toHaveBeenCalled();
  });
  it("keeps errors actionable and clears the starter password", async () => {
    mocks.post.mockRejectedValue(new Error("Denied"));
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Add a person" }));
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Trusted teammate" } });
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "teammate@example.com" } });
    fireEvent.change(screen.getByLabelText("Starter password"), { target: { value: "Test-only-password-123!" } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Create read-only account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed");
    expect(screen.getByLabelText("Starter password")).toHaveValue("");
  });
});
