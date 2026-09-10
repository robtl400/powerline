import { useEffect, useState } from "react";

/**
 * Tracks a CSS media query. Falls back to `false` wherever `matchMedia` is
 * unavailable (jsdom, SSR), so callers render their wide-viewport layout.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    setMatches(list.matches);
    if (typeof list.addEventListener === "function") {
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    }
    list.addListener(onChange);
    return () => list.removeListener(onChange);
  }, [query]);

  return matches;
}

/** True below Tailwind's `sm` breakpoint (640px). */
export function useIsNarrow(): boolean {
  return useMediaQuery("(max-width: 639px)");
}
