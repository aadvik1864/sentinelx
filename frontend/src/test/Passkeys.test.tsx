import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AddPasskey } from "../components/Passkeys";

const mocks = vi.hoisted(() => ({ post: vi.fn(), apply: vi.fn(), register: vi.fn() }));
vi.mock("../services/api", () => ({ api: { post: mocks.post }, applySession: mocks.apply, errorMessage: () => "Passkey request failed" }));
vi.mock("@simplewebauthn/browser", () => ({ startRegistration: mocks.register }));

describe("passkey enrollment", () => {
  beforeEach(() => { mocks.post.mockReset(); mocks.apply.mockReset(); mocks.register.mockReset(); });
  it("requires browser verification and acknowledges first-factor recovery codes", async () => {
    mocks.post.mockResolvedValueOnce({ data: { challenge_id: "fixture", options: { challenge: "fixture-challenge" } } }).mockResolvedValueOnce({ data: { recovery_codes: ["test-only-recovery-code"] } });
    mocks.register.mockResolvedValue({ id: "fixture-credential" });
    render(<AddPasskey />);
    fireEvent.change(screen.getByLabelText("Current password for passkey"), { target: { value: "Fixture-password-123!" } });
    fireEvent.click(screen.getByRole("button", { name: "Add passkey" }));
    await screen.findByRole("heading", { name: "Passkey added" });
    expect(mocks.register).toHaveBeenCalledWith({ optionsJSON: { challenge: "fixture-challenge" } });
    expect(mocks.post).toHaveBeenCalledWith("/auth/passkeys/register/verify", { challenge_id: "fixture", credential: { id: "fixture-credential" }, name: "My passkey" });
    expect(screen.getByRole("button", { name: "Continue to sign in" })).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Continue to sign in" }));
    expect(mocks.apply).toHaveBeenCalledWith(null);
  });
  it("does not submit verification or unlock the workspace when the browser cancels", async () => {
    mocks.post.mockResolvedValue({ data: { challenge_id: "fixture", options: {} } });
    mocks.register.mockRejectedValue(new Error("User cancelled"));
    render(<AddPasskey />);
    fireEvent.change(screen.getByLabelText("Current password for passkey"), { target: { value: "Fixture-password-123!" } });
    fireEvent.click(screen.getByRole("button", { name: "Add passkey" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Passkey request failed"));
    expect(mocks.post).toHaveBeenCalledTimes(1);
    expect(mocks.apply).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Current password for passkey")).toHaveValue("");
  });
});
