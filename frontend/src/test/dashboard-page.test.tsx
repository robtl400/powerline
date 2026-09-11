/**
 * Page tests for Dashboard: the live-campaigns table and the mobile card layout
 * that renders alongside it.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const mocks = vi.hoisted(() => ({
  client: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@/api/client", () => ({ default: mocks.client }));

globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

import Dashboard from "@/pages/Dashboard";

const DASHBOARD = {
  calls_today: 4,
  calls_this_week: 9,
  calls_this_month: 22,
  active_campaigns: 2,
  webrtc_count: 6,
  phone_count: 3,
  calls_last_7_days: [{ date: "2026-01-01", count: 4 }],
};

const LIVE = {
  id: "camp-live",
  name: "Live Drive",
  status: "live",
  campaign_type: "call",
  target_count: 12,
  session_count: 12,
  completed_session_count: 6,
  created_at: "2026-01-02T00:00:00Z",
};

const FRESH = {
  id: "camp-fresh",
  name: "Fresh Drive",
  status: "live",
  campaign_type: "call",
  target_count: 0,
  session_count: 0,
  completed_session_count: 0,
  created_at: "2026-01-03T00:00:00Z",
};

/**
 * Both layouts render — the table is hidden below `sm` and the card list from
 * `sm` up — so every row assertion scopes itself to one of them.
 */
function table() {
  return within(screen.getByRole("table"));
}

function cards() {
  return within(screen.getByRole("list", { name: "Campaigns" }));
}

function card(name: string) {
  return within(cards().getByRole("link", { name: new RegExp(name) }));
}

function mockCampaigns(items: unknown[]) {
  mocks.client.get.mockImplementation((url: string) =>
    url.startsWith("/campaigns")
      ? Promise.resolve({ data: { total: items.length, items } })
      : Promise.resolve({ data: DASHBOARD })
  );
}

async function renderDashboard() {
  render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>
  );
  await screen.findAllByText("Live Campaigns");
}

beforeEach(() => {
  vi.clearAllMocks();
  mockCampaigns([LIVE, FRESH]);
});

describe("Dashboard — live campaigns", () => {
  it("renders the same campaigns as cards and as table rows", async () => {
    await renderDashboard();

    expect(cards().getAllByRole("listitem")).toHaveLength(2);
    expect(table().getAllByRole("row")).toHaveLength(3);
    expect(cards().getByText("Live Drive")).toBeInTheDocument();
    expect(table().getByText("Live Drive")).toBeInTheDocument();
  });

  it("points each card at the campaign's edit page", async () => {
    await renderDashboard();

    expect(cards().getByRole("link", { name: /Live Drive/ })).toHaveAttribute(
      "href",
      "/campaigns/camp-live/edit"
    );
  });

  it("fills the progress bar orange for a live campaign", async () => {
    await renderDashboard();

    expect(card("Live Drive").getByRole("progressbar").className).toContain("bg-brand-orange");
    expect(card("Live Drive").getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
  });

  it("renders zeroes rather than hiding an untouched campaign", async () => {
    await renderDashboard();

    expect(card("Live Drive").getByText("12 calls")).toBeInTheDocument();
    expect(card("Live Drive").getByText("50% completed")).toBeInTheDocument();
    expect(card("Fresh Drive").getByText("0 calls")).toBeInTheDocument();
    expect(card("Fresh Drive").getByText("0% completed")).toBeInTheDocument();
  });

  it("shows the empty state in both layouts when nothing is live", async () => {
    mockCampaigns([]);
    await renderDashboard();

    expect(cards().getByText("No live campaigns")).toBeInTheDocument();
    expect(table().getByText("No live campaigns")).toBeInTheDocument();
  });
});
