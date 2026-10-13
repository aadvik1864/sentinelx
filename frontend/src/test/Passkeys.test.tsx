import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AddPasskey } from "../components/Passkeys";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  apply: vi.fn(),
  register: vi.fn(),
  enroll: vi.fn(),
}));

vi.mock("../services/api", () => ({
  api: { post: mocks.post },
  applySession: mocks.apply,
  errorMessage: () => "Passkey request failed",
}));
vi.mock("@simplewebauthn/browser", () => ({ startRegistration: mocks.register }));
vi.mock("../store/AuthContext", () => ({
  useAuth: () => ({ completeEnrollment: mocks.enroll }),
}));

describe("passkey enrollment", () => {
  beforeEach(() => {
    mocks.post.mockReset();
    mocks.apply.mockReset();
    mocks.register.mockReset();
    mocks.enroll.mockReset();
  });

  it("passes recovery codes to the completion screen after browser verification", async () => {
    mocks.post
      .mockResolvedValueOnce({
        data: {
          challenge_id: "fixture",
          options: { challenge: "fixture-challenge" },
        },
      })
      .mockResolvedValueOnce({
        data: { recovery_codes: ["test-only-recovery-code"] },
      });
    mocks.register.mockResolvedValue({ id: "fixture-credential" });
    render(<AddPasskey />);
    fireEvent.change(screen.getByLabelText("Current password for passkey"), {
      target: { value: "Fixture-password-123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add passkey" }));
    await waitFor(() =>
      expect(mocks.enroll).toHaveBeenCalledWith("passkey", [
        "test-only-recovery-code",
      ]),
    );
    expect(mocks.register).toHaveBeenCalledWith({
      optionsJSON: { challenge: "fixture-challenge" },
    });
    expect(mocks.post).toHaveBeenCalledWith("/auth/passkeys/register/verify", {
      challenge_id: "fixture",
      credential: { id: "fixture-credential" },
      name: "My passkey",
    });
  });

  it("does not submit verification or unlock the workspace when the browser cancels", async () => {
    mocks.post.mockResolvedValue({
      data: { challenge_id: "fixture", options: {} },
    });
    mocks.register.mockRejectedValue(new Error("User cancelled"));
    render(<AddPasskey />);
    fireEvent.change(screen.getByLabelText("Current password for passkey"), {
      target: { value: "Fixture-password-123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add passkey" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Passkey request failed"),
    );
    expect(mocks.post).toHaveBeenCalledTimes(1);
    expect(mocks.apply).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Current password for passkey")).toHaveValue("");
  });
});
