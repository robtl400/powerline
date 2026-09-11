/**
 * Page tests for Phone Numbers: the paged `{total, items}` envelope, the
 * Twilio sync refresh, and the labelled assign control.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  client: { get: vi.fn(), post: vi.fn() },
}));

vi.mock("@/api/client", () => ({ default: mocks.client }));

import PhoneNumbers from "@/pages/PhoneNumbers";

const mockClient = mocks.client;

function number(id: string, digits: string) {
  return {
    id,
    number: digits,
    label: `Line ${id}`,
    provider: "twilio",
    capabilities: { voice: true, sms: false },
    trust_status: "unknown",
    trust_product_sid: null,
    created_at: "2026-01-01T00:00:00Z",
  };
}

const FIRST = number("pn-1", "+12025550001");
const SECOND = number("pn-2", "+12025550002");
const THIRD = number("pn-3", "+12025550003");

const CAMPAIGNS = { total: 1, items: [{ id: "camp-1", name: "Call Your Senator" }] };

function respond(page: { total: number; items: unknown[] }) {
  mockClient.get.mockImplementation((url: string) =>
    url.startsWith("/campaigns")
      ? Promise.resolve({ data: CAMPAIGNS })
      : Promise.resolve({ data: page })
  );
}

async function renderPage() {
  const result = render(<PhoneNumbers />);
  await screen.findByText("+12025550001");
  return result;
}

function table() {
  return within(screen.getByRole("table"));
}

beforeEach(() => {
  vi.clearAllMocks();
  respond({ total: 2, items: [FIRST, SECOND] });
});

describe("PhoneNumbers", () => {
  it("renders the rows from the paged envelope", async () => {
    await renderPage();
    expect(mockClient.get).toHaveBeenCalledWith("/phone-numbers");
    expect(table().getByText("+12025550002")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("appends the next page from the Load more control", async () => {
    mockClient.get.mockImplementation((url: string) => {
      if (url.startsWith("/campaigns")) return Promise.resolve({ data: CAMPAIGNS });
      if (url === "/phone-numbers?skip=2")
        return Promise.resolve({ data: { total: 3, items: [THIRD] } });
      return Promise.resolve({ data: { total: 3, items: [FIRST, SECOND] } });
    });

    await renderPage();
    expect(screen.getByText("Showing 2 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await table().findByText("+12025550003")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("reloads the first page after a Twilio sync", async () => {
    await renderPage();
    mockClient.post.mockResolvedValue({ data: { total: 1, items: [THIRD] } });
    respond({ total: 1, items: [THIRD] });

    fireEvent.click(screen.getAllByRole("button", { name: "Sync from Twilio" })[0]);

    await waitFor(() => expect(mockClient.post).toHaveBeenCalledWith("/phone-numbers/sync"));
    expect(await table().findByText("+12025550003")).toBeInTheDocument();
  });

  it("surfaces the server's detail when the sync fails", async () => {
    await renderPage();
    mockClient.post.mockRejectedValue(
      Object.assign(new Error("Request failed"), {
        isAxiosError: true,
        response: { status: 502, data: { detail: "Failed to fetch numbers from Twilio" } },
      })
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Sync from Twilio" })[0]);

    expect(
      await screen.findByText("Failed to fetch numbers from Twilio")
    ).toBeInTheDocument();
  });

  it("labels the assign campaign select", async () => {
    await renderPage();
    fireEvent.click(table().getAllByRole("button", { name: "Assign" })[0]);

    const select = screen.getByLabelText("Campaign");
    expect(select).toBeInTheDocument();
    expect(within(select).getByText("Call Your Senator")).toBeInTheDocument();
  });

  it("shows the empty state with a sync action when no numbers exist", async () => {
    respond({ total: 0, items: [] });
    render(<PhoneNumbers />);

    expect(await screen.findByText("No phone numbers configured")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Sync from Twilio" })).toHaveLength(2);
  });
});
