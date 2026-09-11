/**
 * Hook tests for usePagedList: the server offset is tracked apart from the
 * rows on screen, so a local insert never shifts the next page's window.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  client: { get: vi.fn() },
}));

vi.mock("@/api/client", () => ({ default: mocks.client }));

import { usePagedList } from "@/hooks/usePagedList";

const mockClient = mocks.client;

interface Row {
  id: string;
}

const rows = (...ids: string[]): Row[] => ids.map((id) => ({ id }));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("usePagedList", () => {
  it("loads the first page and reports what is left", async () => {
    mockClient.get.mockResolvedValue({ data: { total: 5, items: rows("a", "b") } });

    const { result } = renderHook(() => usePagedList<Row>("/things"));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockClient.get).toHaveBeenCalledWith("/things");
    expect(result.current.items).toHaveLength(2);
    expect(result.current.total).toBe(5);
    expect(result.current.hasMore).toBe(true);
  });

  it("appends the next page from the loaded offset", async () => {
    mockClient.get.mockResolvedValueOnce({ data: { total: 4, items: rows("a", "b") } });
    mockClient.get.mockResolvedValueOnce({ data: { total: 4, items: rows("c", "d") } });

    const { result } = renderHook(() => usePagedList<Row>("/things"));
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    act(() => result.current.loadMore());

    await waitFor(() => expect(result.current.items).toHaveLength(4));
    expect(mockClient.get).toHaveBeenLastCalledWith("/things?skip=2");
    expect(result.current.hasMore).toBe(false);
  });

  it("keeps the offset on the server's own count when a row is inserted locally", async () => {
    mockClient.get.mockResolvedValueOnce({ data: { total: 4, items: rows("a", "b") } });
    mockClient.get.mockResolvedValueOnce({ data: { total: 5, items: rows("c", "d") } });

    const { result } = renderHook(() => usePagedList<Row>("/things"));
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    act(() => result.current.insert({ id: "local" }));
    expect(result.current.items).toHaveLength(3);
    expect(result.current.total).toBe(5);

    act(() => result.current.loadMore());

    await waitFor(() => expect(mockClient.get).toHaveBeenLastCalledWith("/things?skip=2"));
    await waitFor(() => expect(result.current.items.map((r) => r.id)).toEqual([
      "a",
      "b",
      "local",
      "c",
      "d",
    ]));
  });

  it("shows a row the server repeats only once", async () => {
    mockClient.get.mockResolvedValueOnce({ data: { total: 3, items: rows("a", "b") } });
    mockClient.get.mockResolvedValueOnce({ data: { total: 3, items: rows("b", "c") } });

    const { result } = renderHook(() => usePagedList<Row>("/things"));
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    act(() => result.current.loadMore());

    await waitFor(() => expect(result.current.items.map((r) => r.id)).toEqual(["a", "b", "c"]));
  });

  it("closes the gap a removed row leaves in the window", async () => {
    mockClient.get.mockResolvedValueOnce({ data: { total: 4, items: rows("a", "b") } });
    mockClient.get.mockResolvedValueOnce({ data: { total: 3, items: rows("c") } });

    const { result } = renderHook(() => usePagedList<Row>("/things"));
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    act(() => result.current.remove("a"));
    expect(result.current.total).toBe(3);

    act(() => result.current.loadMore());

    await waitFor(() => expect(mockClient.get).toHaveBeenLastCalledWith("/things?skip=1"));
  });

  it("joins skip onto a url that already carries a query", async () => {
    mockClient.get.mockResolvedValue({ data: { total: 4, items: rows("a") } });

    const { result } = renderHook(() => usePagedList<Row>("/things?status=live"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    act(() => result.current.loadMore());

    await waitFor(() =>
      expect(mockClient.get).toHaveBeenLastCalledWith("/things?status=live&skip=1")
    );
  });

  it("restarts at the first page when the url changes", async () => {
    mockClient.get.mockResolvedValue({ data: { total: 2, items: rows("a") } });

    const { result, rerender } = renderHook(({ url }) => usePagedList<Row>(url), {
      initialProps: { url: "/things?status=live" },
    });
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    rerender({ url: "/things?status=paused" });

    await waitFor(() => expect(mockClient.get).toHaveBeenLastCalledWith("/things?status=paused"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });

  it("reports the caller's message when the request fails", async () => {
    mockClient.get.mockRejectedValue(new Error("network"));

    const { result } = renderHook(() =>
      usePagedList<Row>("/things", { errorMessage: "Failed to load things." })
    );

    await waitFor(() => expect(result.current.error).toBe("Failed to load things."));
    expect(result.current.loading).toBe(false);
  });

  it("swaps a row for the server's copy of it", async () => {
    mockClient.get.mockResolvedValue({
      data: { total: 2, items: [{ id: "a", name: "old" }, { id: "b", name: "b" }] },
    });

    const { result } = renderHook(() => usePagedList<Row & { name: string }>("/things"));
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    act(() => result.current.replace({ id: "a", name: "new" }));

    expect(result.current.items[0].name).toBe("new");
  });
});
