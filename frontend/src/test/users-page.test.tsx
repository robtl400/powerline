/**
 * Page tests for Users: role-gated controls and the PATCH /users/{id} row actions.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

interface AuthUser {
  id: string;
  email: string;
  name: string;
  phone: string;
  role: string;
  is_active: boolean;
}

const mocks = vi.hoisted(() => ({
  client: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  auth: { user: null as unknown },
  toast: Object.assign(vi.fn(), { warning: vi.fn() }),
}));

const mockClient = mocks.client;
const mockToast = mocks.toast;

vi.mock("@/api/client", () => ({ default: mocks.client }));
vi.mock("sonner", () => ({ toast: mocks.toast }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.auth.user, isLoading: false, login: vi.fn(), logout: vi.fn() }),
}));

function setCurrentUser(u: AuthUser) {
  mocks.auth.user = u;
}

import Users from "@/pages/Users";

const ADMIN = {
  id: "admin-1",
  email: "admin@example.com",
  name: "Ada Admin",
  phone: "+12025550001",
  role: "admin",
  is_active: true,
};

const STAFF = {
  id: "staff-1",
  email: "sam@example.com",
  name: "Sam Staff",
  phone: "+12025550002",
  role: "staff",
  is_active: true,
};

const USER_ROWS = [
  { ...ADMIN, created_at: "2026-01-01T00:00:00Z" },
  { ...STAFF, created_at: "2026-01-02T00:00:00Z" },
];

function axiosError(status: number, detail: string) {
  return Object.assign(new Error("Request failed"), {
    isAxiosError: true,
    response: { status, data: { detail } },
  });
}

async function renderUsers() {
  const result = render(
    <MemoryRouter>
      <Users />
    </MemoryRouter>
  );
  await screen.findByText("Sam Staff");
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockClient.get.mockResolvedValue({ data: { total: USER_ROWS.length, items: USER_ROWS } });
});

describe("Users — admin", () => {
  beforeEach(() => {
    setCurrentUser(ADMIN);
  });

  it("shows the Invite button", async () => {
    await renderUsers();
    expect(screen.getByRole("button", { name: "Invite User" })).toBeInTheDocument();
  });

  it("shows a role select and an activation button on each row", async () => {
    await renderUsers();
    expect(screen.getByLabelText("Role for Sam Staff")).toBeInTheDocument();
    expect(screen.getByLabelText("Role for Ada Admin")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Deactivate" })).toHaveLength(2);
  });

  it("disables Deactivate on the current user's own row", async () => {
    await renderUsers();
    const buttons = screen.getAllByRole("button", { name: "Deactivate" });
    expect(buttons[0]).toBeDisabled();
    expect(buttons[1]).toBeEnabled();
  });

  it("patches is_active: false when Deactivate is clicked", async () => {
    mockClient.patch.mockResolvedValue({ data: { ...USER_ROWS[1], is_active: false } });
    await renderUsers();

    fireEvent.click(screen.getAllByRole("button", { name: "Deactivate" })[1]);

    await waitFor(() =>
      expect(mockClient.patch).toHaveBeenCalledWith("/users/staff-1", { is_active: false })
    );
    expect(await screen.findByRole("button", { name: "Activate" })).toBeInTheDocument();
  });

  it("patches the new role when the role select changes", async () => {
    mockClient.patch.mockResolvedValue({ data: { ...USER_ROWS[1], role: "admin" } });
    await renderUsers();

    fireEvent.change(screen.getByLabelText("Role for Sam Staff"), { target: { value: "admin" } });

    await waitFor(() =>
      expect(mockClient.patch).toHaveBeenCalledWith("/users/staff-1", { role: "admin" })
    );
  });

  it("shows the 409 detail inline when the last active admin is protected", async () => {
    mockClient.patch.mockRejectedValue(
      axiosError(409, "Cannot deactivate or demote the last active admin")
    );
    await renderUsers();

    fireEvent.click(screen.getAllByRole("button", { name: "Deactivate" })[1]);

    expect(
      await screen.findByText("Cannot deactivate or demote the last active admin")
    ).toBeInTheDocument();
  });
});

describe("Users — invite result", () => {
  const NEW_USER = {
    id: "new-1",
    email: "new@example.com",
    name: "Nia New",
    phone: "+12025550003",
    role: "staff",
    is_active: true,
    created_at: "2026-01-03T00:00:00Z",
  };

  beforeEach(() => {
    setCurrentUser(ADMIN);
  });

  async function submitInvite() {
    await renderUsers();
    fireEvent.click(screen.getByRole("button", { name: "Invite User" }));
    fireEvent.change(screen.getByPlaceholderText("Full name"), {
      target: { value: "Nia New" },
    });
    fireEvent.change(screen.getByPlaceholderText("user@example.com"), {
      target: { value: "new@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("(555) 555-5555"), {
      target: { value: "2025550003" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send Invite" }));
  }

  it("confirms the invite when the SMS went out", async () => {
    mockClient.post.mockResolvedValue({ data: { ...NEW_USER, invite_sent: true } });
    await submitInvite();

    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith("Invite sent to new@example.com")
    );
    expect(mockToast.warning).not.toHaveBeenCalled();
  });

  it("warns when the account was created but the invite SMS failed", async () => {
    mockClient.post.mockResolvedValue({ data: { ...NEW_USER, invite_sent: false } });
    await submitInvite();

    await waitFor(() =>
      expect(mockToast.warning).toHaveBeenCalledWith(
        "Account created, but the invite SMS could not be sent. Share the reset flow with the user."
      )
    );
    expect(await screen.findByText("Nia New")).toBeInTheDocument();
  });
});

describe("Users — paging", () => {
  beforeEach(() => {
    setCurrentUser(ADMIN);
  });

  it("appends the next page from the Load more control", async () => {
    const THIRD = {
      id: "staff-2",
      email: "kit@example.com",
      name: "Kit Staff",
      phone: "+12025550004",
      role: "staff",
      is_active: true,
      created_at: "2026-01-04T00:00:00Z",
    };
    mockClient.get.mockResolvedValueOnce({ data: { total: 3, items: USER_ROWS } });
    mockClient.get.mockResolvedValueOnce({ data: { total: 3, items: [THIRD] } });

    await renderUsers();
    expect(screen.getByText("Showing 2 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    await waitFor(() => expect(mockClient.get).toHaveBeenLastCalledWith("/users?skip=2"));
    expect(await screen.findByText("Kit Staff")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });
});

describe("Users — staff", () => {
  beforeEach(() => {
    setCurrentUser(STAFF);
  });

  it("hides the Invite button and the row controls", async () => {
    await renderUsers();
    expect(screen.queryByRole("button", { name: "Invite User" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Role for Sam Staff")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Activate" })).not.toBeInTheDocument();
  });
});

describe("Users — narrow viewport", () => {
  function mockNarrowViewport(narrow: boolean) {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: narrow,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }))
    );
  }

  beforeEach(() => {
    setCurrentUser(ADMIN);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a card per user instead of the table", async () => {
    mockNarrowViewport(true);
    await renderUsers();

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("sam@example.com")).toBeInTheDocument();
    expect(screen.getByLabelText("Role for Sam Staff")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Deactivate" })).toHaveLength(2);
  });

  it("keeps the table from sm up", async () => {
    mockNarrowViewport(false);
    await renderUsers();

    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});

describe("Users — invite modal accessibility", () => {
  beforeEach(() => {
    setCurrentUser(ADMIN);
  });

  it("is a labelled modal dialog that focuses the first field", async () => {
    await renderUsers();
    fireEvent.click(screen.getByRole("button", { name: "Invite User" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Invite User");
    await waitFor(() => expect(screen.getByPlaceholderText("Full name")).toHaveFocus());
  });

  it("closes on Escape", async () => {
    await renderUsers();
    fireEvent.click(screen.getByRole("button", { name: "Invite User" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
