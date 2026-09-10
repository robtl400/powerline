/**
 * ProtectedRoute tests: the guard must hold the route while the session is
 * still resolving, and send anonymous visitors to /login rather than flashing
 * protected content.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const mocks = vi.hoisted(() => ({
  auth: { user: null as unknown, isLoading: false },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: mocks.auth.user,
    isLoading: mocks.auth.isLoading,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

import ProtectedRoute from "@/components/ProtectedRoute";

const USER = {
  id: "user-1",
  email: "ada@example.com",
  name: "Ada Admin",
  phone: "+12025550001",
  role: "admin",
  is_active: true,
};

function renderGuard() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<p>Dashboard content</p>} />
        </Route>
        <Route path="/login" element={<p>Login screen</p>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  mocks.auth.user = null;
  mocks.auth.isLoading = false;
});

describe("ProtectedRoute", () => {
  it("renders the nested route for a signed-in user", () => {
    mocks.auth.user = USER;

    renderGuard();

    expect(screen.getByText("Dashboard content")).toBeInTheDocument();
  });

  it("redirects to the login screen with no user", () => {
    renderGuard();

    expect(screen.getByText("Login screen")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard content")).not.toBeInTheDocument();
  });

  it("waits while the session is still loading", () => {
    mocks.auth.isLoading = true;

    renderGuard();

    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(screen.queryByText("Login screen")).not.toBeInTheDocument();
    expect(screen.queryByText("Dashboard content")).not.toBeInTheDocument();
  });

  it("does not fall through to login while a session is still loading", () => {
    mocks.auth.isLoading = true;
    mocks.auth.user = USER;

    renderGuard();

    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
});
