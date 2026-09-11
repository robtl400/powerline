import { createCall, errorDetail } from "./api.js";
import type { WidgetState } from "./types.js";

type StateCallback = (state: WidgetState, data?: unknown) => void;

export interface SubmitPhoneFallbackOptions {
  baseUrl: string;
  campaignId: string;
  phoneNumber: string;
  repToken?: string;
  onStateChange: StateCallback;
}

/** Submit a phone number and request a callback. */
export async function submitPhoneFallback({
  baseUrl,
  campaignId,
  phoneNumber,
  repToken,
  onStateChange,
}: SubmitPhoneFallbackOptions): Promise<void> {
  const cleaned = phoneNumber.trim();
  if (!cleaned) {
    onStateChange("error", "Please enter a phone number.");
    return;
  }

  onStateChange("loading");

  try {
    await createCall(baseUrl, campaignId, cleaned, repToken);
    onStateChange("phone_pending");
  } catch (err) {
    onStateChange(
      "error",
      errorDetail(err, "Could not place the call. Please try again.")
    );
  }
}
