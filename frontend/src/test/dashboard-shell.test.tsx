/**
 * DashboardShell: the mobile nav drawer behaves as a modal dialog — it takes
 * focus on open, closes on Escape and on navigation, and hands focus back to
 * the hamburger button.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "u1",
      email: "ada@example.com",
      name: "Ada",
      phone: "+12025550142",
      role: "admin",
      is_active: true,
    },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

import DashboardShell from "@/components/DashboardShell";

function renderShell() {
  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route element={<DashboardShell />}>
          <Route path="/dashboard" element={<p>Dashboard page</p>} />
          <Route path="/campaigns" element={<p>Campaigns page</p>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
  return screen.getByRole("button", { name: "Open menu" });
}

describe("DashboardShell mobile drawer", () => {
  it("is not a dialog until it is opened", () => {
    const button = renderShell();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("opens as a labelled dialog and focuses the first nav link", async () => {
    const button = renderShell();

    fireEvent.click(button);

    const drawer = await screen.findByRole("dialog", { name: "Navigation" });
    expect(drawer).toHaveAttribute("aria-modal", "true");
    expect(button).toHaveAttribute("aria-expanded", "true");
    await waitFor(() => {
      expect(within(drawer).getByRole("link", { name: /Dashboard/ })).toHaveFocus();
    });
  });

  it("closes on Escape and returns focus to the hamburger", async () => {
    const button = renderShell();

    fireEvent.click(button);
    await screen.findByRole("dialog");

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(button).toHaveFocus();
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("closes when a nav link is activated", async () => {
    const button = renderShell();

    fireEvent.click(button);
    const drawer = await screen.findByRole("dialog");

    fireEvent.click(within(drawer).getByRole("link", { name: /Campaigns/ }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Campaigns page")).toBeInTheDocument();
  });
});
