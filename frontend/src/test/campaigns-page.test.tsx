/**
 * Page tests for Campaigns: per-row actions and the debounced name search.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const mocks = vi.hoisted(() => ({
  client: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@/api/client", () => ({ default: mocks.client }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "admin-1", email: "admin@example.com", name: "Ada", role: "admin" },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

import Campaigns from "@/pages/Campaigns";

const DRAFT = {
  id: "camp-draft",
  name: "Draft Drive",
  status: "draft",
  campaign_type: "call",
  target_count: 3,
  created_at: "2026-01-01T00:00:00Z",
};

const LIVE = {
  id: "camp-live",
  name: "Live Drive",
  status: "live",
  campaign_type: "call",
  target_count: 12,
  created_at: "2026-01-02T00:00:00Z",
};

async function renderCampaigns() {
  render(
    <MemoryRouter>
      <Campaigns />
    </MemoryRouter>
  );
  await screen.findByText("Live Drive");
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.client.get.mockResolvedValue({ data: [DRAFT, LIVE] });
});

describe("Campaigns — row actions", () => {
  it("offers Resume wizard on a draft row and Edit on a live row", async () => {
    await renderCampaigns();

    expect(screen.getByRole("button", { name: "Resume wizard" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Resume wizard" })).toHaveLength(1);
  });

  it("links the campaign name to its edit page", async () => {
    await renderCampaigns();

    expect(screen.getByRole("link", { name: "Live Drive" })).toHaveAttribute(
      "href",
      "/campaigns/camp-live/edit"
    );
  });
});

describe("Campaigns — search", () => {
  it("passes the typed term as the q param after the debounce", async () => {
    await renderCampaigns();

    fireEvent.change(screen.getByLabelText("Search campaigns"), {
      target: { value: "live" },
    });

    await waitFor(() => expect(mocks.client.get).toHaveBeenCalledWith("/campaigns?q=live"));
  });

  it("clears the field on Escape", async () => {
    await renderCampaigns();

    const input = screen.getByLabelText("Search campaigns") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "live" } });
    fireEvent.keyDown(input, { key: "Escape" });

    expect(input.value).toBe("");
  });
});
