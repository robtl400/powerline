/**
 * WebRTC client wrapper around the Twilio Voice JS SDK.
 *
 * Flow:
 *   start() → request AccessToken → create Device → register
 *           → connect with session_id param → voice-app webhook fires
 *           → TwiML chain plays intro, dials targets
 *
 * The widget drives state changes; this class emits state events upward.
 */
import { Call, Device } from "@twilio/voice-sdk";
import { requestToken } from "./api.js";
import type { CampaignPublic, ConnectedData, WidgetState } from "./types.js";

type StateCallback = (state: WidgetState, data?: unknown) => void;

/** How long after "accept" to wait before flagging a possible audio issue. */
const AUDIO_CHECK_DELAY_MS = 3_000;

export class WebRTCClient {
  private device: Device | null = null;
  private call: Call | null = null;
  private sessionId: string | null = null;
  private timerHandle: ReturnType<typeof setInterval> | null = null;
  private elapsed = 0;
  private audioCheckHandle: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly baseUrl: string,
    private readonly campaign: CampaignPublic,
    private readonly onStateChange: StateCallback,
    private readonly onTimerTick: (elapsed: number) => void
  ) {}

  /** Request a token, create the Twilio Device, and register it. */
  async start(): Promise<void> {
    this.onStateChange("loading");

    let token: string;
    let sessionId: string;
    try {
      const res = await requestToken(this.baseUrl, this.campaign.id);
      token = res.token;
      sessionId = res.session_id;
    } catch (err) {
      this.onStateChange(
        "error",
        err instanceof Error ? err.message : "Failed to get calling token."
      );
      return;
    }

    this.sessionId = sessionId;

    // Signal the user to grant mic permission before the Device prompts.
    this.onStateChange("mic_permission");

    try {
      this.device = new Device(token, {
        // Opus is preferred for voice quality; fall back to PCMU.
        codecPreferences: [Call.Codec.Opus, Call.Codec.PCMU],
        closeProtection: true,
      });

      this.device.on("error", (twilioError) => {
        this.onStateChange("error", twilioError.message ?? "Device error");
        this._cleanup();
      });

      await this.device.register();
    } catch (err) {
      // Browser mic permission denied — offer phone fallback instead of a dead error.
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        this.onStateChange("phone_input", "mic_denied");
        return;
      }
      this.onStateChange(
        "error",
        err instanceof Error ? err.message : "Could not initialize audio device."
      );
      return;
    }

    await this._connect();
  }

  private async _connect(): Promise<void> {
    if (!this.device || !this.sessionId) return;

    try {
      // Pass session_id so the voice-app webhook can look up Redis call state.
      this.call = await this.device.connect({
        params: { session_id: this.sessionId },
      });
    } catch (err) {
      this.onStateChange(
        "error",
        err instanceof Error ? err.message : "Could not connect call."
      );
      return;
    }

    this.call.on("accept", () => {
      const target = this.campaign.targets[0] ?? null;
      if (target) {
        const connectedData: ConnectedData = {
          target,
          targetIndex: 0,
          totalTargets: this.campaign.targets.length,
        };
        this.onStateChange("connected", connectedData);
      } else {
        this.onStateChange("connected");
      }

      this._startTimer();
      this._scheduleAudioCheck();
    });

    this.call.on("disconnect", () => {
      this._cleanup();
      this.onStateChange("complete");
    });

    this.call.on("cancel", () => {
      this._cleanup();
      this.onStateChange("idle");
    });

    this.call.on("error", (err: { message?: string }) => {
      this._cleanup();
      this.onStateChange("error", err.message ?? "Call error");
    });
  }

  /** Send DTMF `*` to skip the current target. Requires TwiML to handle the digit. */
  skip(): void {
    this.call?.sendDigits("*");
  }

  /** Hang up the call entirely. */
  end(): void {
    this.call?.disconnect();
  }

  /** Clean up device, timers, and handles. */
  destroy(): void {
    this._cleanup();
    this.device?.destroy();
    this.device = null;
  }

  private _startTimer(): void {
    this.elapsed = 0;
    this.timerHandle = setInterval(() => {
      this.elapsed += 1;
      this.onTimerTick(this.elapsed);
    }, 1_000);
  }

  private _scheduleAudioCheck(): void {
    // If the call is still "accepted" after the delay with no user interaction,
    // surface an audio troubleshooting screen. The user can dismiss it once
    // they hear audio or switch to phone fallback.
    this.audioCheckHandle = setTimeout(() => {
      // Only show if we're still connected (not already complete/error).
      // Widget state is managed by the caller; we just emit the suggestion.
      // The widget decides whether to show it based on current state.
      this.onStateChange("audio_check");
    }, AUDIO_CHECK_DELAY_MS);
  }

  /** Cancel the audio check if the user interacts (indicating audio works). */
  cancelAudioCheck(): void {
    if (this.audioCheckHandle !== null) {
      clearTimeout(this.audioCheckHandle);
      this.audioCheckHandle = null;
    }
  }

  private _cleanup(): void {
    if (this.timerHandle !== null) {
      clearInterval(this.timerHandle);
      this.timerHandle = null;
    }
    if (this.audioCheckHandle !== null) {
      clearTimeout(this.audioCheckHandle);
      this.audioCheckHandle = null;
    }
    this.call = null;
    this.elapsed = 0;
  }
}
