/** Format a YYYY-MM-DD date string (e.g. from API daily stats) for display. */
export function formatDate(iso: string): string {
  try {
    // Append T00:00:00 so the date is parsed in local time, not UTC midnight.
    return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

/** Format an ISO datetime string with short time for display. */
export function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
