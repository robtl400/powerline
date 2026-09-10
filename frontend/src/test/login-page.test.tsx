import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    isLoading: false,
    login: mocks.login,
    logout: vi.fn(),
  }),
}));

import Login from "@/pages/Login";

beforeEach(() => {
  mocks.login.mockReset();
});

describe("Login", () => {
  it("submits email and password to login()", async () => {
    mocks.login.mockResolvedValueOnce(undefined);

    render(<Login />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "ada@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "hunter2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(mocks.login).toHaveBeenCalledWith("ada@example.com", "hunter2");
    });
  });

  it("shows an error message when login is rejected", async () => {
    mocks.login.mockRejectedValueOnce(new Error("nope"));

    render(<Login />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "ada@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByText("Invalid email or password.")
    ).toBeInTheDocument();
  });

  it("disables the submit button while submitting", async () => {
    let resolveLogin: () => void;
    mocks.login.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        resolveLogin = resolve;
      })
    );

    render(<Login />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "ada@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "hunter2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const button = await screen.findByRole("button", { name: "Signing in…" });
    expect(button).toBeDisabled();

    resolveLogin!();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Sign in" })).not.toBeDisabled();
    });
  });
});
