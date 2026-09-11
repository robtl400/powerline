/**
 * Page tests for Campaigns: per-row actions, the debounced name search, and the
 * mobile card layout that renders alongside the table.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
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
  session_count: 4,
  completed_session_count: 1,
  created_at: "2026-01-01T00:00:00Z",
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

const MORE = {
  id: "camp-more",
  name: "Later Drive",
  status: "live",
  campaign_type: "call",
  target_count: 4,
  session_count: 5,
  completed_session_count: 5,
  created_at: "2026-01-03T00:00:00Z",
};

const EMPTY_COUNTS = {
  id: "camp-fresh",
  name: "Fresh Drive",
  status: "paused",
  campaign_type: "call",
  target_count: 0,
  session_count: 0,
  completed_session_count: 0,
  created_at: "2026-01-04T00:00:00Z",
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

async function renderCampaigns() {
  render(
    <MemoryRouter>
      <Campaigns />
    </MemoryRouter>
  );
  await screen.findAllByText("Live Drive");
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.client.get.mockResolvedValue({ data: { total: 2, items: [DRAFT, LIVE] } });
});

describe("Campaigns — row actions", () => {
  it("offers Resume wizard on a draft row and Edit on a live row", async () => {
    await renderCampaigns();

    expect(screen.getByRole("button", { name: "Resume wizard" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Resume wizard" })).toHaveLength(1);
  });

  it("keeps draft rows at full contrast — the status chip carries the state", async () => {
    await renderCampaigns();

    const draftRow = table().getByRole("link", { name: "Draft Drive" }).closest("tr");
    expect(draftRow?.className).not.toContain("opacity-50");
  });

  it("marks the active status filter with the shared orange underline", async () => {
    await renderCampaigns();

    const allTab = screen.getByRole("button", { name: "all" });
    expect(allTab.className).toContain("border-brand-orange");
    expect(allTab.className).toContain("text-brand-black");
  });

  it("links the campaign name to its edit page", async () => {
    await renderCampaigns();

    expect(table().getByRole("link", { name: "Live Drive" })).toHaveAttribute(
      "href",
      "/campaigns/camp-live/edit"
    );
  });
});

describe("Campaigns — mobile cards", () => {
  it("renders one card per campaign alongside the table", async () => {
    await renderCampaigns();

    expect(cards().getAllByRole("listitem")).toHaveLength(2);
    expect(table().getAllByRole("row")).toHaveLength(3);
    expect(cards().getByText("Draft Drive")).toBeInTheDocument();
    expect(cards().getByText("Live Drive")).toBeInTheDocument();
  });

  it("points each card at the same route as the table link", async () => {
    await renderCampaigns();

    const tableHref = table().getByRole("link", { name: "Live Drive" }).getAttribute("href");
    expect(cards().getByRole("link", { name: /Live Drive/ })).toHaveAttribute("href", tableHref);
  });

  it("fills the progress bar orange only while the campaign is live", async () => {
    await renderCampaigns();

    expect(card("Live Drive").getByRole("progressbar").className).toContain("bg-brand-orange");
    expect(card("Draft Drive").getByRole("progressbar").className).toContain("bg-brand-grey-mid");
  });

  it("shows the call count and completion share on each card", async () => {
    await renderCampaigns();

    expect(card("Live Drive").getByText("12 calls")).toBeInTheDocument();
    expect(card("Live Drive").getByText("50% completed")).toBeInTheDocument();
    expect(card("Live Drive").getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
  });

  it("renders zeroes rather than hiding an untouched campaign", async () => {
    mocks.client.get.mockResolvedValue({ data: { total: 2, items: [LIVE, EMPTY_COUNTS] } });
    await renderCampaigns();

    expect(card("Fresh Drive").getByText("0 calls")).toBeInTheDocument();
    expect(card("Fresh Drive").getByText("0% completed")).toBeInTheDocument();
    expect(card("Fresh Drive").getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
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

describe("Campaigns — paging", () => {
  it("hides the Load more control once every row is shown", async () => {
    await renderCampaigns();

    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("reports the shown count and appends the next page", async () => {
    mocks.client.get.mockResolvedValueOnce({ data: { total: 3, items: [DRAFT, LIVE] } });
    mocks.client.get.mockResolvedValueOnce({ data: { total: 3, items: [MORE] } });

    await renderCampaigns();
    expect(screen.getByText("Showing 2 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    await waitFor(() =>
      expect(mocks.client.get).toHaveBeenLastCalledWith("/campaigns?skip=2")
    );
    expect(await screen.findAllByText("Later Drive")).toHaveLength(2);
    expect(cards().getAllByRole("listitem")).toHaveLength(3);
    expect(table().getAllByRole("row")).toHaveLength(4);
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("starts the next search back at the first page", async () => {
    mocks.client.get.mockResolvedValueOnce({ data: { total: 3, items: [DRAFT, LIVE] } });
    mocks.client.get.mockResolvedValueOnce({ data: { total: 3, items: [MORE] } });
    mocks.client.get.mockResolvedValueOnce({ data: { total: 1, items: [LIVE] } });
    await renderCampaigns();

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() =>
      expect(mocks.client.get).toHaveBeenLastCalledWith("/campaigns?skip=2")
    );

    fireEvent.change(screen.getByLabelText("Search campaigns"), {
      target: { value: "live" },
    });

    await waitFor(() =>
      expect(mocks.client.get).toHaveBeenLastCalledWith("/campaigns?q=live")
    );
  });
});
