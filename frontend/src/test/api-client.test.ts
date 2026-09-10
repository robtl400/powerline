/**
 * Tests for the 401 refresh/retry interceptor in src/api/client.ts.
 *
 * axios is mocked so the interceptor handlers can be driven directly with
 * synthetic 401 errors.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";

type ErrorHandler = (error: unknown) => Promise<unknown>;

const hooks = vi.hoisted(() => ({
  responseError: null as ErrorHandler | null,
  instance: null as ReturnType<typeof vi.fn> | null,
  post: vi.fn(),
}));

vi.mock("axios", () => {
  const create = () => {
    const instance = vi.fn((config: unknown) => Promise.resolve({ replayed: config }));
    Object.assign(instance, {
      interceptors: {
        request: { use: () => {} },
        response: {
          use: (_ok: unknown, err: ErrorHandler) => {
            hooks.responseError = err;
          },
        },
      },
    });
    hooks.instance = instance;
    return instance;
  };
  return { default: { create, post: hooks.post } };
});

function unauthorized() {
  return {
    response: { status: 401 },
    config: { url: "/campaigns", headers: {} as Record<string, string> },
  };
}

async function loadClient(): Promise<ErrorHandler> {
  vi.resetModules();
  hooks.responseError = null;
  await import("@/api/client");
  const handler: ErrorHandler | null = hooks.responseError;
  if (!handler) throw new Error("response interceptor was not registered");
  return handler;
}

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

describe("client 401 handling", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", fakeStorage());
    hooks.post.mockReset();
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: { href: "" },
    });
  });

  it("stores the rotated refresh token and replays the request", async () => {
    localStorage.setItem("access_token", "old-access");
    localStorage.setItem("refresh_token", "old-refresh");
    hooks.post.mockResolvedValue({
      data: { access_token: "new-access", refresh_token: "new-refresh" },
    });

    const onError = await loadClient();
    const error = unauthorized();
    await onError(error);

    expect(localStorage.getItem("access_token")).toBe("new-access");
    expect(localStorage.getItem("refresh_token")).toBe("new-refresh");
    expect(error.config.headers.Authorization).toBe("Bearer new-access");
    expect(hooks.instance).toHaveBeenCalledWith(error.config);
  });

  it("marks queued requests as retried before replaying them", async () => {
    localStorage.setItem("access_token", "old-access");
    localStorage.setItem("refresh_token", "old-refresh");
    let releaseRefresh: (v: unknown) => void = () => {};
    hooks.post.mockReturnValue(
      new Promise((resolve) => {
        releaseRefresh = resolve;
      })
    );

    const onError = await loadClient();
    const first = unauthorized();
    const second = unauthorized();
    const firstResult = onError(first);
    const secondResult = onError(second);

    expect((second.config as { _retry?: boolean })._retry).toBe(true);

    releaseRefresh({ data: { access_token: "new-access", refresh_token: "new-refresh" } });
    await Promise.all([firstResult, secondResult]);

    expect(second.config.headers.Authorization).toBe("Bearer new-access");
    expect(hooks.instance).toHaveBeenCalledWith(second.config);
  });

  it("rejects a second 401 on an already-retried request instead of looping", async () => {
    localStorage.setItem("refresh_token", "old-refresh");

    const onError = await loadClient();
    const error = unauthorized();
    (error.config as { _retry?: boolean })._retry = true;

    await expect(onError(error)).rejects.toBe(error);
    expect(hooks.post).not.toHaveBeenCalled();
  });

  it("clears both tokens and redirects when the refresh fails", async () => {
    localStorage.setItem("access_token", "old-access");
    localStorage.setItem("refresh_token", "old-refresh");
    hooks.post.mockRejectedValue(new Error("refresh rejected"));

    const onError = await loadClient();
    await expect(onError(unauthorized())).rejects.toThrow("refresh rejected");

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(window.location.href).toBe("/login");
  });

  it("clears both tokens and redirects when there is no refresh token", async () => {
    localStorage.setItem("access_token", "old-access");

    const onError = await loadClient();
    const error = unauthorized();
    await expect(onError(error)).rejects.toBe(error);

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(window.location.href).toBe("/login");
    expect(hooks.post).not.toHaveBeenCalled();
  });
});
