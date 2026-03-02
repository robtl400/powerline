import type {
  CallCountResponse,
  CallCreateResponse,
  CampaignPublic,
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
  phoneNumber: string
): Promise<CallCreateResponse> {
  return apiFetch<CallCreateResponse>(`${baseUrl}/api/v1/calls/create`, {
    method: "POST",
    body: JSON.stringify({ campaign_id: campaignId, phone_number: phoneNumber }),
  });
}
