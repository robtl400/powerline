import { useCallback, useEffect, useRef, useState } from "react";
import client from "@/api/client";
import type { Page } from "@/types/api";

/**
 * One "Load more" list backed by a `{total, items}` endpoint.
 *
 * The offset sent as `skip` is the number of rows the server has handed over,
 * tracked apart from `items.length` so a locally inserted row never shifts the
 * next request's window. Rows already held are dropped from a later page, so a
 * row that moves into the window still appears once.
 *
 * `url` may already carry a query string; `skip` is appended with the right
 * separator. A `null` url holds the hook idle.
 */
export function usePagedList<T extends { id: string }>(
  url: string | null,
  options: { errorMessage?: string } = {}
) {
  const errorMessage = options.errorMessage ?? "Failed to load list.";

  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [loadedCount, setLoadedCount] = useState(0);
  const [loading, setLoading] = useState(url !== null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestId = useRef(0);

  const fetchPage = useCallback(
    (skip: number) => {
      if (url === null) return;
      const id = ++requestId.current;
      const separator = url.includes("?") ? "&" : "?";
      const target = skip > 0 ? `${url}${separator}skip=${skip}` : url;
      if (skip > 0) setLoadingMore(true);
      else setLoading(true);

      client
        .get<Page<T>>(target)
        .then((res) => {
          if (id !== requestId.current) return;
          const received = res.data.items ?? [];
          setTotal(res.data.total ?? 0);
          setLoadedCount(skip + received.length);
          setItems((prev) => {
            if (skip === 0) return received;
            const held = new Set(prev.map((row) => row.id));
            return [...prev, ...received.filter((row) => !held.has(row.id))];
          });
          setError(null);
        })
        .catch(() => {
          if (id !== requestId.current) return;
          setError(errorMessage);
        })
        .finally(() => {
          if (id !== requestId.current) return;
          setLoading(false);
          setLoadingMore(false);
        });
    },
    [url, errorMessage]
  );

  useEffect(() => {
    if (url === null) {
      setLoading(false);
      return;
    }
    setItems([]);
    setLoadedCount(0);
    fetchPage(0);
  }, [url, fetchPage]);

  const loadMore = useCallback(() => fetchPage(loadedCount), [fetchPage, loadedCount]);

  const reload = useCallback(() => fetchPage(0), [fetchPage]);

  /** Show a row created locally without moving the server offset. */
  const insert = useCallback((item: T, position: "start" | "end" = "end") => {
    setItems((prev) => (position === "start" ? [item, ...prev] : [...prev, item]));
    setTotal((n) => n + 1);
  }, []);

  /** Drop a row that no longer exists on the server, closing the gap it leaves. */
  const remove = useCallback((id: string) => {
    setItems((prev) => prev.filter((row) => row.id !== id));
    setTotal((n) => Math.max(0, n - 1));
    setLoadedCount((n) => Math.max(0, n - 1));
  }, []);

  /** Swap a row for the server's copy of it. */
  const replace = useCallback((item: T) => {
    setItems((prev) => prev.map((row) => (row.id === item.id ? item : row)));
  }, []);

  const hasMore = loadedCount < total && items.length < total;

  return {
    items,
    total,
    loading,
    loadingMore,
    error,
    setError,
    hasMore,
    loadMore,
    reload,
    insert,
    remove,
    replace,
  };
}
