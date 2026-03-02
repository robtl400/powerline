import { createCall } from "./api.js";
import type { WidgetState } from "./types.js";

type StateCallback = (state: WidgetState, data?: unknown) => void;

/** Handles the phone-callback path: collects a phone number and POSTs to /calls/create. */
export class PhoneFallbackClient {
  constructor(
    private readonly baseUrl: string,
    private readonly campaignId: string,
    private readonly onStateChange: StateCallback
  ) {}

  /** Submit a phone number and request a callback. */
  async submit(phoneNumber: string): Promise<void> {
    const cleaned = phoneNumber.trim();
    if (!cleaned) {
      this.onStateChange("error", "Please enter a phone number.");
      return;
    }

    this.onStateChange("loading");

    try {
      await createCall(this.baseUrl, this.campaignId, cleaned);
      this.onStateChange("phone_pending");
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : "Could not place the call. Please try again.";
      this.onStateChange("error", msg);
    }
  }
}
