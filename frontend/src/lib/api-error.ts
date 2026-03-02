import axios from "axios";

/** Extract the FastAPI `detail` string from an Axios error response, or fall back to a default message.
 *
 * Handles three common FastAPI error shapes:
 *   - string detail   → returned as-is
 *   - array detail    → Pydantic validation errors; joined as "field: msg, ..."
 *   - object detail   → JSON-stringified
 */
export function getErrorDetail(error: unknown, fallback = "An unexpected error occurred."): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const msgs = detail.map((d: { msg?: string }) => d.msg).filter(Boolean);
      return msgs.length > 0 ? msgs.join(", ") : JSON.stringify(detail);
    }
    if (typeof detail === "object" && detail !== null) return JSON.stringify(detail);
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}
