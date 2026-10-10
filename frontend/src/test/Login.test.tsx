import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "../pages/Login";

const login = vi.fn();
vi.mock("../store/AuthContext", () => ({
  useAuth: () => ({ user: null, login }),
}));

describe("login workflow", () => {
  beforeEach(() => {
    login.mockReset();
  });
  it("directs new people to an administrator instead of public sign-up", () => {
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    expect(screen.getByText(/Ask your workspace administrator/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Create an account/ })).toBeNull();
    expect(screen.queryByLabelText("Full name")).toBeNull();
  });
  it("submits user credentials to the authentication service", async () => {
    login.mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "analyst@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "A-strong-password-123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() =>
      expect(login).toHaveBeenCalledWith(
        "analyst@example.com",
        "A-strong-password-123",
      ),
    );
  });
  it("does not silently bypass a failed login", async () => {
    login.mockRejectedValue(new Error("Denied"));
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "analyst@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The request could not be completed",
    );
  });
});
