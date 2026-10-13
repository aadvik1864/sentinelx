import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import {
  AccountSecuritySetup,
  AuthenticatorSetup,
} from "../components/AccountSecurity";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  apply: vi.fn(),
  logout: vi.fn(),
  enroll: vi.fn(),
  user: { must_change_password: true },
}));

vi.mock("../services/api", () => ({
  api: { post: mocks.post },
  applySession: mocks.apply,
  errorMessage: () => "Request failed",
}));
vi.mock("../store/AuthContext", () => ({
  useAuth: () => ({
    user: mocks.user,
    logout: mocks.logout,
    completeEnrollment: mocks.enroll,
  }),
}));

describe("account security setup", () => {
  beforeEach(() => {
    mocks.post.mockReset();
    mocks.apply.mockReset();
    mocks.enroll.mockReset();
  });

  it("guards direct workspace URLs before mounting the console", () => {
    render(
      <MemoryRouter initialEntries={["/incidents/99"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("Secure your account")).toBeVisible();
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("replaces a starter password and ends the restricted session", async () => {
    mocks.post.mockResolvedValue({});
    render(<AccountSecuritySetup />);
    expect(screen.getByText(/Workspace activity stays locked/)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Starter password"), {
      target: { value: "Starter-password-123!" },
    });
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "Own-password-456!" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Change password and sign out" }),
    );
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledWith(null));
    expect(mocks.post).toHaveBeenCalledWith("/auth/change-password", {
      current_password: "Starter-password-123!",
      new_password: "Own-password-456!",
    });
  });

  it("confirms an authenticator and moves its codes to the session-independent completion screen", async () => {
    mocks.post
      .mockResolvedValueOnce({ data: { secret: "TESTONLYSECRET" } })
      .mockResolvedValueOnce({
        data: { recovery_codes: ["test-only-recovery-code"] },
      });
    render(<AuthenticatorSetup />);
    fireEvent.change(screen.getByLabelText("Current password"), {
      target: { value: "Own-password-456!" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Start authenticator setup" }),
    );
    expect(await screen.findByText("TESTONLYSECRET")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Six-digit code"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enable two-step sign-in" }));
    await waitFor(() =>
      expect(mocks.enroll).toHaveBeenCalledWith("totp", [
        "test-only-recovery-code",
      ]),
    );
    expect(screen.queryByText("TESTONLYSECRET")).toBeNull();
  });

  it("does not bypass a failed enrollment", async () => {
    mocks.post.mockRejectedValue(new Error("Denied"));
    render(<AuthenticatorSetup />);
    fireEvent.change(screen.getByLabelText("Current password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Start authenticator setup" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed");
    expect(mocks.apply).not.toHaveBeenCalled();
  });
});
