import type {
  CallCountResponse,
  CallCreateResponse,
  CampaignPublic,
  ErrorDetail,
  RepsResponse,
  VoiceTokenResponse,
} from "./types.js";

/**
 * A non-OK backend response. `code` is the machine-readable half of a
 * structured `detail` object, which the widget branches on; `message` is the
 * half shown to the visitor.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Read a FastAPI `detail`, which is either a plain string or a message/code object. */
function parseDetail(detail: unknown, fallback: string): ErrorDetail {
  if (typeof detail === "string" && detail) return { message: detail };
  if (typeof detail === "object" && detail !== null) {
    const d = detail as { message?: unknown; code?: unknown };
    return {
      message: typeof d.message === "string" && d.message ? d.message : fallback,
      code: typeof d.code === "string" ? d.code : undefined,
    };
  }
  return { message: fallback };
}

/** Narrow a thrown value into the message/code pair the widget renders and branches on. */
export function errorDetail(err: unknown, fallback: string): ErrorDetail {
  if (err instanceof ApiError) return { message: err.message, code: err.code };
  if (err instanceof Error && err.message) return { message: err.message };
  return { message: fallback };
}

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      ({ detail } = (await res.json()) as { detail?: unknown });
    } catch {
      // ignore JSON parse errors
    }
    const { message, code } = parseDetail(detail, res.statusText);
    throw new ApiError(message, res.status, code);
  }
  return res.json() as Promise<T>;
}

/** Fetch public campaign metadata (name, targets, connection modes). */
export async function fetchCampaign(
  baseUrl: string,
  campaignId: string
): Promise<CampaignPublic> {
  return apiFetch<CampaignPublic>(
    `${baseUrl}/api/v1/campaigns/${campaignId}/public`
  );
}

/** Request a Twilio Access Token + session_id for a WebRTC call. */
export async function requestToken(
  baseUrl: string,
  campaignId: string,
  repToken?: string
): Promise<VoiceTokenResponse> {
  return apiFetch<VoiceTokenResponse>(`${baseUrl}/api/v1/tokens/voice`, {
    method: "POST",
    body: JSON.stringify({
      campaign_id: campaignId,
      ...(repToken !== undefined && { rep_token: repToken }),
    }),
  });
}

/** Fetch completed-call counts for a campaign (cached 10 min server-side). */
export async function fetchCallCount(
  baseUrl: string,
  campaignId: string
): Promise<CallCountResponse> {
  return apiFetch<CallCountResponse>(
    `${baseUrl}/api/v1/campaigns/${campaignId}/count`
  );
}

/** Initiate a phone callback (phone fallback path). */
export async function createCall(
  baseUrl: string,
  campaignId: string,
  phoneNumber: string,
  repToken?: string
): Promise<CallCreateResponse> {
  return apiFetch<CallCreateResponse>(`${baseUrl}/api/v1/calls/create`, {
    method: "POST",
    body: JSON.stringify({
      campaign_id: campaignId,
      phone_number: phoneNumber,
      ...(repToken !== undefined && { rep_token: repToken }),
    }),
  });
}

/** Representative lookup error returned when the backend signals fallback: manual_entry. */
export interface RepsError {
  fallback: "manual_entry";
  message: string;
}

/** Type guard: true when result is a RepsError (503 + fallback). */
export function isRepsError(r: RepsResponse | RepsError): r is RepsError {
  return "fallback" in r;
}

/** Fetch elected representatives for a ZIP code within a campaign's configured levels. */
export async function fetchReps(
  baseUrl: string,
  campaignId: string,
  zip: string
): Promise<RepsResponse | RepsError> {
  const url = `${baseUrl}/api/v1/campaigns/${campaignId}/reps?zip=${encodeURIComponent(zip)}`;
  const res = await fetch(url, { headers: { "Content-Type": "application/json" } });

  if (!res.ok) {
    let detail: unknown;
    try {
      ({ detail } = (await res.json()) as { detail?: unknown });
    } catch { /* ignore */ }

    if (res.status === 503 && typeof detail === "object" && detail !== null) {
      const d = detail as { fallback?: string; message?: string };
      if (d.fallback === "manual_entry") {
        return {
          fallback: "manual_entry",
          message: d.message ?? "Representative lookup is temporarily unavailable.",
        };
      }
    }

    const { message, code } = parseDetail(detail, res.statusText);
    throw new ApiError(message, res.status, code);
  }

  return res.json() as Promise<RepsResponse>;
}
