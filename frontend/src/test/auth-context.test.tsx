/**
 * AuthContext tests: session bootstrap from localStorage, and the login/logout
 * token lifecycle. A failed /users/me on mount must clear both tokens so a
 * revoked session cannot linger in storage.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const mocks = vi.hoisted(() => ({
  client: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  navigate: vi.fn(),
}));

const mockClient = mocks.client;

vi.mock("@/api/client", () => ({ default: mocks.client }));
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

import { AuthProvider, useAuth } from "@/contexts/AuthContext";

const ME = {
  id: "user-1",
  email: "ada@example.com",
  name: "Ada Admin",
  phone: "+12025550001",
  role: "admin",
  is_active: true,
};

function Consumer() {
  const { user, isLoading, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="user">{user ? user.email : "none"}</span>
      <button onClick={() => void login("ada@example.com", "hunter2")}>
        Log in
      </button>
      <button onClick={() => void logout()}>Log out</button>
    </div>
  );
}

async function renderAuth() {
  const result = render(
    <MemoryRouter>
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    </MemoryRouter>
  );
  await waitFor(() =>
    expect(screen.getByTestId("loading")).toHaveTextContent("false")
  );
  return result;
}

/** Minimal in-memory Storage — the runtime's own localStorage is not resettable. */
function fakeStorage() {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => void store.set(key, String(value)),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
    key: (index: number) => [...store.keys()][index] ?? null,
    get length() {
      return store.size;
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("localStorage", fakeStorage());
});

describe("AuthProvider — mount", () => {
  it("finishes loading with no user when there is no token", async () => {
    await renderAuth();

    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(mockClient.get).not.toHaveBeenCalled();
  });

  it("restores the session from a stored token", async () => {
    localStorage.setItem("access_token", "at");
    mockClient.get.mockResolvedValue({ data: ME });

    await renderAuth();

    expect(mockClient.get).toHaveBeenCalledWith("/users/me");
    expect(screen.getByTestId("user")).toHaveTextContent("ada@example.com");
  });

  it("clears both tokens when the stored session is rejected", async () => {
    localStorage.setItem("access_token", "stale");
    localStorage.setItem("refresh_token", "stale-refresh");
    mockClient.get.mockRejectedValue(new Error("401"));

    await renderAuth();

    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
  });
});

describe("AuthProvider — login", () => {
  it("stores both tokens, loads the user, and lands on the dashboard", async () => {
    mockClient.post.mockResolvedValue({
      data: { access_token: "new-at", refresh_token: "new-rt" },
    });
    mockClient.get.mockResolvedValue({ data: ME });

    await renderAuth();
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() =>
      expect(screen.getByTestId("user")).toHaveTextContent("ada@example.com")
    );

    expect(mockClient.post).toHaveBeenCalledWith("/auth/login", {
      email: "ada@example.com",
      password: "hunter2",
    });
    expect(localStorage.getItem("access_token")).toBe("new-at");
    expect(localStorage.getItem("refresh_token")).toBe("new-rt");
    expect(mockClient.get).toHaveBeenCalledWith("/users/me");
    expect(mocks.navigate).toHaveBeenCalledWith("/dashboard");
  });
});

describe("AuthProvider — logout", () => {
  it("revokes the refresh token, clears storage, and returns to login", async () => {
    localStorage.setItem("access_token", "at");
    localStorage.setItem("refresh_token", "rt");
    mockClient.get.mockResolvedValue({ data: ME });
    mockClient.post.mockResolvedValue({ data: {} });

    await renderAuth();
    await waitFor(() =>
      expect(screen.getByTestId("user")).toHaveTextContent("ada@example.com")
    );

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() =>
      expect(screen.getByTestId("user")).toHaveTextContent("none")
    );

    expect(mockClient.post).toHaveBeenCalledWith("/auth/logout", {
      refresh_token: "rt",
    });
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(mocks.navigate).toHaveBeenCalledWith("/login");
  });

  it("still clears the session when the revoke call fails", async () => {
    localStorage.setItem("access_token", "at");
    localStorage.setItem("refresh_token", "rt");
    mockClient.get.mockResolvedValue({ data: ME });
    mockClient.post.mockRejectedValue(new Error("network down"));

    await renderAuth();
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() =>
      expect(localStorage.getItem("refresh_token")).toBeNull()
    );
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(mocks.navigate).toHaveBeenCalledWith("/login");
  });

  it("skips the revoke call when no refresh token is stored", async () => {
    localStorage.setItem("access_token", "at");
    mockClient.get.mockResolvedValue({ data: ME });

    await renderAuth();
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/login"));
    expect(mockClient.post).not.toHaveBeenCalled();
    expect(localStorage.getItem("access_token")).toBeNull();
  });
});

describe("useAuth", () => {
  it("throws when used outside the provider", () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});

    expect(() => act(() => void render(<Consumer />))).toThrow(
      "useAuth must be used inside AuthProvider"
    );

    consoleError.mockRestore();
  });
});
