/**
 * ResetPassword: the two-step reset flow — request a code, then confirm it with a
 * new password — and the backend error shapes surfaced at each step.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const mocks = vi.hoisted(() => ({
  client: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/api/client", () => ({ default: mocks.client }));

import ResetPassword from "@/pages/ResetPassword";

/** An error shaped like the ones axios raises for a failed response. */
function axiosError(status: number, data: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data },
  });
}

function renderPage() {
  render(
    <MemoryRouter>
      <ResetPassword />
    </MemoryRouter>
  );
}

/** Complete step 1 so the code + password form is on screen. */
async function reachStepTwo() {
  mocks.client.post.mockResolvedValueOnce({ status: 204, data: null });
  renderPage();
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "ada@example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send code" }));
  await screen.findByLabelText("Code");
}

/** Fill and submit the step 2 form. */
function submitStepTwo() {
  fireEvent.change(screen.getByLabelText("Code"), { target: { value: "12345678" } });
  fireEvent.change(screen.getByLabelText("New password"), {
    target: { value: "correcthorse1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
}

beforeEach(() => {
  mocks.client.post.mockReset();
});

describe("ResetPassword", () => {
  it("posts the email and advances to the code step", async () => {
    mocks.client.post.mockResolvedValueOnce({ status: 204, data: null });

    renderPage();

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "ada@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));

    await waitFor(() => {
      expect(mocks.client.post).toHaveBeenCalledWith("/auth/reset-request", {
        email: "ada@example.com",
      });
    });
    expect(
      await screen.findByText("If that email has an account, we sent a code to its phone.")
    ).toBeInTheDocument();
  });

  it("posts the code and the new password", async () => {
    await reachStepTwo();
    mocks.client.post.mockResolvedValueOnce({ status: 204, data: null });

    submitStepTwo();

    await waitFor(() => {
      expect(mocks.client.post).toHaveBeenLastCalledWith("/auth/reset-confirm", {
        email: "ada@example.com",
        code: "12345678",
        new_password: "correcthorse1",
      });
    });
  });

  it("shows the detail of a 400 response", async () => {
    await reachStepTwo();
    mocks.client.post.mockRejectedValueOnce(
      axiosError(400, { detail: "Invalid or expired code" })
    );

    submitStepTwo();

    expect(await screen.findByText("Invalid or expired code")).toBeInTheDocument();
  });

  it("shows the policy message from a 422 response", async () => {
    await reachStepTwo();
    mocks.client.post.mockRejectedValueOnce(
      axiosError(422, {
        detail: [
          {
            loc: ["body", "new_password"],
            msg: "Password must contain a letter and a digit",
            type: "value_error",
          },
        ],
      })
    );

    submitStepTwo();

    expect(
      await screen.findByText("Password must contain a letter and a digit")
    ).toBeInTheDocument();
  });

  it("shows a rate-limit message on 429", async () => {
    await reachStepTwo();
    mocks.client.post.mockRejectedValueOnce(axiosError(429, { detail: "Too many requests" }));

    submitStepTwo();

    expect(
      await screen.findByText("Too many attempts. Try again in an hour.")
    ).toBeInTheDocument();
  });

  it("offers a sign-in link once the password is reset", async () => {
    await reachStepTwo();
    mocks.client.post.mockResolvedValueOnce({ status: 204, data: null });

    submitStepTwo();

    const link = await screen.findByRole("link", { name: "Sign in" });
    expect(link).toHaveAttribute("href", "/login");
  });
});
