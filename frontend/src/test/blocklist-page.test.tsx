/**
 * Page tests for Blocklist: the add form submits an E.164 phone_number and the
 * sha256 hash field stays behind the Advanced disclosure.
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
  auth: { user: null as unknown },
}));

const mockClient = mocks.client;

vi.mock("@/api/client", () => ({ default: mocks.client }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.auth.user, isLoading: false, login: vi.fn(), logout: vi.fn() }),
}));

const ADMIN = {
  id: "admin-1",
  email: "admin@example.com",
  name: "Ada Admin",
  phone: "+12025550001",
  role: "admin",
  is_active: true,
};

function setCurrentUser(u: typeof ADMIN | { role: string }) {
  mocks.auth.user = u;
}

import Blocklist from "@/pages/Blocklist";

async function renderBlocklist() {
  const result = render(
    <MemoryRouter>
      <Blocklist />
    </MemoryRouter>
  );
  await screen.findByRole("heading", { name: "Blocklist" });
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  setCurrentUser(ADMIN);
  mockClient.get.mockResolvedValue({ data: { total: 0, items: [] } });
});

describe("Blocklist — add form", () => {
  it("shows the phone input and hides the hash field by default", async () => {
    await renderBlocklist();
    fireEvent.click(screen.getByRole("button", { name: "+ Add Entry" }));

    expect(screen.getByPlaceholderText("(555) 555-5555")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("64-char hex")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Advanced: paste a sha256 hash instead" })
    ).toBeInTheDocument();
  });

  it("reveals the hash field from the Advanced disclosure", async () => {
    await renderBlocklist();
    fireEvent.click(screen.getByRole("button", { name: "+ Add Entry" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Advanced: paste a sha256 hash instead" })
    );

    expect(screen.getByPlaceholderText("64-char hex")).toBeInTheDocument();
  });

  it("submits phone_number in E.164 form", async () => {
    mockClient.post.mockResolvedValue({
      data: {
        id: "b1",
        created_at: "2026-01-01T00:00:00Z",
        phone_hash: "a".repeat(64),
        ip_address: null,
        reason: "spam",
        created_by_id: "admin-1",
      },
    });
    await renderBlocklist();
    fireEvent.click(screen.getByRole("button", { name: "+ Add Entry" }));

    fireEvent.change(screen.getByPlaceholderText("(555) 555-5555"), {
      target: { value: "2025551234" },
    });
    fireEvent.change(screen.getByPlaceholderText("e.g. spam, abuse"), {
      target: { value: "spam" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(mockClient.post).toHaveBeenCalled());
    const [url, body] = mockClient.post.mock.calls[0];
    expect(url).toBe("/admin/blocklist");
    expect(body).toMatchObject({ phone_number: "+12025551234", reason: "spam" });
    expect(body).not.toHaveProperty("phone_hash");
  });

  it("rejects an incomplete phone number without calling the API", async () => {
    await renderBlocklist();
    fireEvent.click(screen.getByRole("button", { name: "+ Add Entry" }));

    fireEvent.change(screen.getByPlaceholderText("(555) 555-5555"), {
      target: { value: "202555" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByText("Enter a 10-digit US phone number")).toBeInTheDocument();
    expect(mockClient.post).not.toHaveBeenCalled();
  });

  it("shows the corrected empty state copy", async () => {
    await renderBlocklist();
    expect(screen.getByText("No blocked numbers or IP addresses")).toBeInTheDocument();
  });
});

describe("Blocklist — paging", () => {
  const entry = (id: string, ip: string) => ({
    id,
    created_at: "2026-01-01T00:00:00Z",
    phone_hash: null,
    ip_address: ip,
    reason: null,
    created_by_id: "admin-1",
  });

  it("appends the next page from the Load more control", async () => {
    mockClient.get.mockResolvedValueOnce({
      data: { total: 2, items: [entry("b1", "10.0.0.1")] },
    });
    mockClient.get.mockResolvedValueOnce({
      data: { total: 2, items: [entry("b2", "10.0.0.2")] },
    });

    await renderBlocklist();
    expect(screen.getByText("Showing 1 of 2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    await waitFor(() =>
      expect(mockClient.get).toHaveBeenLastCalledWith("/admin/blocklist?skip=1")
    );
    expect(await screen.findByText("IP: 10.0.0.2")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });
});

describe("Blocklist — staff", () => {
  it("hides the Add action", async () => {
    setCurrentUser({ role: "staff" });
    await renderBlocklist();
    expect(screen.queryByRole("button", { name: "+ Add Entry" })).not.toBeInTheDocument();
  });
});
