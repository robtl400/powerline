import type {
  CallCountResponse,
  CallCreateResponse,
  CampaignPublic,
  RepsResponse,
  VoiceTokenResponse,
} from "./types.js";

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // ignore JSON parse errors
    }
    throw new Error(detail);
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
  campaignId: string
): Promise<VoiceTokenResponse> {
  return apiFetch<VoiceTokenResponse>(`${baseUrl}/api/v1/tokens/voice`, {
    method: "POST",
    body: JSON.stringify({ campaign_id: campaignId }),
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
  targetPhoneOverride?: string,
  targetRepName?: string,
  targetRepTitle?: string
): Promise<CallCreateResponse> {
  return apiFetch<CallCreateResponse>(`${baseUrl}/api/v1/calls/create`, {
    method: "POST",
    body: JSON.stringify({
      campaign_id: campaignId,
      phone_number: phoneNumber,
      ...(targetPhoneOverride && {
        target_phone_override: targetPhoneOverride,
        target_rep_name: targetRepName,
        target_rep_title: targetRepTitle,
      }),
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

  if (res.status === 503) {
    let fallback: "manual_entry" | undefined;
    let message = "Representative lookup is temporarily unavailable.";
    try {
      const body = (await res.json()) as { detail?: { fallback?: string; message?: string } };
      if (body.detail?.fallback === "manual_entry") fallback = "manual_entry";
      if (body.detail?.message) message = body.detail.message;
    } catch { /* ignore */ }
    if (fallback === "manual_entry") return { fallback: "manual_entry", message };
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  return res.json() as Promise<RepsResponse>;
}

/** Request a Twilio Access Token for a WebRTC call, optionally with a rep phone override. */
export async function requestTokenWithOverride(
  baseUrl: string,
  campaignId: string,
  targetPhoneOverride?: string,
  targetRepName?: string,
  targetRepTitle?: string
): Promise<VoiceTokenResponse> {
  return apiFetch<VoiceTokenResponse>(`${baseUrl}/api/v1/tokens/voice`, {
    method: "POST",
    body: JSON.stringify({
      campaign_id: campaignId,
      ...(targetPhoneOverride && {
        target_phone_override: targetPhoneOverride,
        target_rep_name: targetRepName,
        target_rep_title: targetRepTitle,
      }),
    }),
  });
}
