import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "../store/AuthContext";
import { SecurityEnrollmentComplete } from "../components/AccountSecurity";

const mocks = vi.hoisted(() => ({
  listener: null as ((session: unknown) => void) | null,
}));

vi.mock("../services/api", () => ({
  api: { post: vi.fn() },
  errorMessage: () => "Request failed",
  onSessionChange: (listener: typeof mocks.listener) => {
    mocks.listener = listener;
  },
  applySession: (session: unknown) => {
    mocks.listener?.(session);
  },
  refreshSession: async () => {
    mocks.listener?.({
      access_token: "test-only-session",
      user: {
        id: 1,
        name: "Fixture",
        email: "fixture@example.com",
        role: "ADMIN",
      },
    });
  },
}));

function Harness({ codes = ["test-only-recovery-code"] }: { codes?: string[] }) {
  const { user, securityCompletion, completeEnrollment } = useAuth();
  if (securityCompletion) return <SecurityEnrollmentComplete />;
  if (!user) return <p>Sign-in required</p>;
  return (
    <section aria-label="Workspace">
      <button onClick={() => completeEnrollment("passkey", codes)}>
        Finish enrollment
      </button>
    </section>
  );
}

describe("session-independent security confirmation", () => {
  beforeEach(() => {
    mocks.listener = null;
  });

  it("retains codes after revocation, blocks workspace access, and clears them on acknowledgement", async () => {
    const writes = vi.spyOn(Storage.prototype, "setItem");
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Finish enrollment" }),
    );
    expect(screen.queryByRole("region", { name: "Workspace" })).toBeNull();
    expect(screen.getByLabelText("Recovery codes")).toHaveTextContent(
      "test-only-recovery-code",
    );
    act(() => {
      mocks.listener?.(null);
    });
    expect(screen.getByLabelText("Recovery codes")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Continue to sign in" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Continue to sign in" }));
    expect(screen.getByText("Sign-in required")).toBeVisible();
    expect(screen.queryByLabelText("Recovery codes")).toBeNull();
    expect(writes).not.toHaveBeenCalled();
    writes.mockRestore();
  });

  it("does not require a code acknowledgement when an existing factor keeps its recovery codes", async () => {
    render(
      <AuthProvider>
        <Harness codes={[]} />
      </AuthProvider>,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Finish enrollment" }),
    );
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Continue to sign in" }),
    ).toBeEnabled();
  });
});
