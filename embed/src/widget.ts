/**
 * PowerlineWidget — root state machine that owns the DOM and orchestrates
 * WebRTCClient / submitPhoneFallback.
 */
import {
  fetchCallCount,
  fetchCampaign,
  fetchReps,
  isRepsError,
  parseDetail,
} from "./api.js";
import { submitPhoneFallback } from "./phone-fallback.js";
import { injectStyles } from "./ui/styles.js";
import {
  formatElapsed,
  renderAudioCheck,
  renderComplete,
  renderConnected,
  renderConnectedGeneric,
  renderError,
  renderIdle,
  renderLoading,
  renderLookingUpReps,
  renderMicPermission,
  renderPhoneInput,
  renderPhonePending,
  renderRepSelection,
} from "./ui/templates.js";
import {
  loadWebRTCClient,
  type WebRTCClientConstructor,
} from "./webrtc-loader.js";
import type { WebRTCClient } from "./webrtc.js";
import type {
  CampaignPublic,
  ConnectedData,
  RepInfo,
  WidgetState,
} from "./types.js";

/** Backend error code returned when a rep_token has expired between lookup and call. */
const REP_TOKEN_INVALID = "rep_token_invalid";

/** Shown while the campaign bootstrap is in flight, before any call exists. */
const BOOTSTRAP_LOADING = "Loading…";

const BOOTSTRAP_FAILED = "Failed to load campaign.";

const BOOTSTRAP_RATE_LIMITED =
  "Too many requests from your network. Please wait a moment and try again.";

/** Message for a failed bootstrap, which is rate limited often enough to name. */
function bootstrapErrorMessage(err: unknown): string {
  if (
    typeof err === "object" &&
    err !== null &&
    (err as { status?: unknown }).status === 429
  ) {
    return BOOTSTRAP_RATE_LIMITED;
  }
  return err instanceof Error && err.message ? err.message : BOOTSTRAP_FAILED;
}

const UNKNOWN_ERROR = "Unknown error";

/** Shown under the phone field when the visitor submits it empty. */
const PHONE_REQUIRED = "Please enter a phone number.";

/** Deadline for the idle prefetch of the WebRTC bundle. */
const PREFETCH_IDLE_TIMEOUT_MS = 3_000;

/** Delay used where requestIdleCallback is unavailable. */
const PREFETCH_FALLBACK_DELAY_MS = 1_500;

type IdleScheduler = (
  callback: () => void,
  options?: { timeout: number }
) => unknown;

export interface WidgetOptions {
  campaignId: string;
  container: Element;
  /** Base URL of the Powerline backend (no trailing slash). */
  apiUrl?: string;
}

export class PowerlineWidget {
  private readonly campaignId: string;
  private readonly container: Element;
  private readonly baseUrl: string;

  private state: WidgetState = "idle";
  private campaign: CampaignPublic | null = null;
  private webrtc: WebRTCClient | null = null;

  // Track connected state for timer re-renders
  private connectedData: ConnectedData | null = null;
  private elapsed = 0;
  private callsCompleted = 0;
  // Message to show on the phone input screen (e.g. after mic denial).
  private phoneFallbackMsg: string | undefined = undefined;
  // Rep-lookup state
  private repSelectionReps: RepInfo[] = [];
  private repSelectionMessage: string | null | undefined = undefined;
  private selectedRepToken: string | null = null;
  private selectedRepName: string | null = null;
  private selectedRepTitle: string | null = null;
  private prefetchScheduled = false;

  constructor({ campaignId, container, apiUrl = "" }: WidgetOptions) {
    this.campaignId = campaignId;
    this.container = container;
    this.baseUrl = apiUrl.replace(/\/$/, "");
  }

  async init(): Promise<void> {
    injectStyles();
    this.state = "loading";
    this._render("loading", BOOTSTRAP_LOADING);

    try {
      this.campaign = await fetchCampaign(this.baseUrl, this.campaignId);
    } catch (err) {
      this.state = "error";
      this._render("error", bootstrapErrorMessage(err));
      return;
    }

    this.state = "idle";
    this._render("idle");
    this._bindEvents();
    this._schedulePrefetch();
  }

  /**
   * Warm the companion WebRTC bundle while the visitor reads the idle screen,
   * so pressing Call Now does not wait on the download. loadWebRTCClient reuses
   * the in-flight promise, so the click path shares this one fetch.
   */
  private _schedulePrefetch(): void {
    if (this.prefetchScheduled) return;
    if (!this.campaign?.allow_webrtc) return;
    if (typeof RTCPeerConnection === "undefined") return;

    this.prefetchScheduled = true;
    const prefetch = (): void => {
      void loadWebRTCClient(this.baseUrl).catch(() => {
        // A failed prefetch clears the loader's cache; the click path retries.
      });
    };

    const idle = (globalThis as { requestIdleCallback?: IdleScheduler })
      .requestIdleCallback;
    if (typeof idle === "function") {
      idle(prefetch, { timeout: PREFETCH_IDLE_TIMEOUT_MS });
    } else {
      setTimeout(prefetch, PREFETCH_FALLBACK_DELAY_MS);
    }
  }

  // ── State transitions ────────────────────────────────────────────────────

  private _onStateChange = (state: WidgetState, data?: unknown): void => {
    const prev = this.state;
    this.state = state;

    const detail =
      state === "error" ? parseDetail(data, UNKNOWN_ERROR) : undefined;

    if (detail?.code === REP_TOKEN_INVALID) {
      this._destroyClients();
      this._resetRepSelection();
      this.state = "idle";
      this._render("idle");
      const errorEl = this.container.querySelector<HTMLElement>("#pl-zip-error");
      if (errorEl) errorEl.textContent = detail.message;
      return;
    }

    if (state === "connected") {
      this.connectedData = (data as ConnectedData) ?? null;
      this.elapsed = 0;
      this.callsCompleted = 0;
      this._renderConnected();
      return;
    }

    if (state === "complete") {
      this.callsCompleted =
        this.connectedData?.totalTargets ??
        this.campaign?.targets.length ??
        this.callsCompleted;
      this._render(state);
      this._destroyClients();
      // Fetch campaign-wide caller count and update the completion screen.
      void fetchCallCount(this.baseUrl, this.campaignId)
        .then((counts) => {
          if (this.state === "complete") {
            this.container.innerHTML = renderComplete(
              this.callsCompleted,
              counts.total
            );
            this._bindEvents();
          }
        })
        .catch(() => {
          // Non-fatal — the screen already shows the session count.
        });
      return;
    }

    if (state === "audio_check") {
      // Only switch to audio_check from a live call — don't override a
      // disconnect/complete that may have raced with the timer.
      if (prev === "connected") {
        this._render("audio_check");
      } else {
        this.state = prev;
      }
      return;
    }

    if (state === "phone_input") {
      // Capture optional message (e.g. "mic_denied") from the data payload.
      this.phoneFallbackMsg =
        typeof data === "string" ? data : undefined;
      this._render("phone_input");
      return;
    }

    this._render(
      state,
      detail?.message ?? (typeof data === "string" ? data : undefined)
    );
  };

  private _onTimerTick = (elapsed: number): void => {
    this.elapsed = elapsed;
    if (this.state !== "connected") return;
    const timerEl = this.container.querySelector<HTMLElement>("[data-pl-timer]");
    if (timerEl) {
      timerEl.textContent = formatElapsed(elapsed);
    } else {
      this._renderConnected();
    }
  };

  // ── Rendering ────────────────────────────────────────────────────────────

  private _render(state: WidgetState, message?: string): void {
    if (!this.campaign) {
      if (state === "loading") {
        this.container.innerHTML = renderLoading(message ?? BOOTSTRAP_LOADING);
      } else if (state === "error") {
        this.container.innerHTML = renderError(message ?? UNKNOWN_ERROR);
      }
      this._bindEvents();
      return;
    }

    switch (state) {
      case "idle":
        this.container.innerHTML = renderIdle(this.campaign);
        break;
      case "loading":
        this.container.innerHTML = renderLoading(message);
        break;
      case "mic_permission":
        this.container.innerHTML = renderMicPermission();
        break;
      case "audio_check":
        this.container.innerHTML = renderAudioCheck();
        break;
      case "complete":
        this.container.innerHTML = renderComplete(this.callsCompleted);
        break;
      case "error":
        this.container.innerHTML = renderError(message ?? UNKNOWN_ERROR);
        break;
      case "phone_input":
        this.container.innerHTML = renderPhoneInput(
          this.campaign,
          this.phoneFallbackMsg
        );
        break;
      case "phone_pending":
        this.container.innerHTML = renderPhonePending();
        break;
      case "lookingUpReps":
        this.container.innerHTML = renderLookingUpReps();
        break;
      case "repSelection":
        this.container.innerHTML = renderRepSelection(this.repSelectionReps, this.repSelectionMessage);
        break;
      default:
        break;
    }

    this._bindEvents();
  }

  private _renderConnected(): void {
    if (!this.connectedData) {
      this.container.innerHTML = renderConnectedGeneric(this.elapsed);
      this._bindEvents();
      return;
    }
    this.container.innerHTML = renderConnected(
      this.connectedData.target,
      this.connectedData.targetIndex,
      this.connectedData.totalTargets,
      this.elapsed,
      this.campaign?.talking_points ?? null
    );
    this._bindEvents();
  }

  // ── Event delegation ─────────────────────────────────────────────────────

  private _boundClickHandler: ((e: Event) => void) | null = null;

  private _bindEvents(): void {
    // Remove previous listener to avoid duplicate handlers.
    if (this._boundClickHandler) {
      this.container.removeEventListener("click", this._boundClickHandler);
    }
    this._boundClickHandler = (e: Event) => {
      const target = (e.target as HTMLElement).closest("[data-pl-action]");
      if (!target) return;
      const el = target as HTMLElement;
      this._handleAction(el.dataset.plAction ?? "", el);
    };
    this.container.addEventListener("click", this._boundClickHandler);
  }

  private _handleAction(action: string, el?: HTMLElement): void {
    switch (action) {
      case "call-now":
        if ((this.campaign?.target_levels?.length ?? 0) > 0) {
          this._startRepLookup();
        } else {
          this._startCall();
        }
        break;

      case "select-rep": {
        const repToken = el?.dataset.plRepToken ?? "";
        if (repToken) {
          this.selectedRepToken = repToken;
          this.selectedRepName = el?.dataset.plName ?? null;
          this.selectedRepTitle = el?.dataset.plTitle ?? null;
          this._startCall();
        }
        break;
      }

      case "show-phone":
        this._destroyClients();
        this.state = "phone_input";
        this._render("phone_input");
        break;

      case "dismiss-audio-check":
        this.webrtc?.cancelAudioCheck();
        this.state = "connected";
        this._renderConnected();
        break;

      case "back-to-idle":
        this.phoneFallbackMsg = undefined;
        this._resetRepSelection();
        this.state = "idle";
        this._render("idle");
        break;

      case "submit-phone": {
        const input = this.container.querySelector<HTMLInputElement>(
          "#pl-phone-input"
        );
        const phone = input?.value.trim() ?? "";
        this._submitPhone(phone);
        break;
      }

      case "retry":
      case "retry-webrtc":
        this._destroyClients();
        this.phoneFallbackMsg = undefined;
        this._resetRepSelection();
        if (!this.campaign) {
          void this.init();
          break;
        }
        this.state = "idle";
        this._render("idle");
        break;

      case "skip":
        // Cancel audio check if user is actively interacting.
        this.webrtc?.cancelAudioCheck();
        void this.webrtc?.skip();
        break;

      case "end":
        this.webrtc?.end();
        break;

      case "copy-link": {
        if (!el) break;
        const button = el;
        void navigator.clipboard
          ?.writeText(globalThis.location?.href ?? "")
          .catch(() => {});
        button.textContent = "Copied!";
        setTimeout(() => {
          button.textContent = "Copy Link";
        }, 2000);
        break;
      }

      default:
        break;
    }
  }

  // ── Call initiation ──────────────────────────────────────────────────────

  private _startRepLookup(): void {
    const input = this.container.querySelector<HTMLInputElement>("#pl-zip-input");
    const zip = input?.value.trim() ?? "";

    if (!/^\d{5}$/.test(zip)) {
      input?.setAttribute("aria-invalid", "true");
      const errorEl = this.container.querySelector<HTMLElement>("#pl-zip-error");
      if (errorEl) errorEl.textContent = "Please enter a valid 5-digit ZIP code.";
      return;
    }

    input?.removeAttribute("aria-invalid");
    const errorEl = this.container.querySelector<HTMLElement>("#pl-zip-error");
    if (errorEl) errorEl.textContent = "";

    this.state = "lookingUpReps";
    this.container.innerHTML = renderLookingUpReps();
    this._bindEvents();

    void this._fetchAndShowReps(zip);
  }

  private async _fetchAndShowReps(zip: string): Promise<void> {
    if (!this.campaign) return;

    try {
      const result = await fetchReps(this.baseUrl, this.campaignId, zip);

      if (isRepsError(result)) {
        // 503 with manual_entry fallback → show phone input with a message
        this.phoneFallbackMsg = result.message;
        this.state = "phone_input";
        this._render("phone_input");
        return;
      }

      this.repSelectionReps = result.reps;
      this.repSelectionMessage = result.message;
      this.state = "repSelection";
      this.container.innerHTML = renderRepSelection(result.reps, result.message);
      this._bindEvents();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not look up representatives.";
      this._render("error", msg);
    }
  }

  private _startCall(): void {
    if (!this.campaign) return;

    const supportsWebRTC = typeof RTCPeerConnection !== "undefined";
    const useWebRTC = supportsWebRTC && this.campaign.allow_webrtc;

    if (useWebRTC) {
      void this._startWebRTCCall();
    } else if (this.campaign.allow_phone_callback) {
      // No WebRTC support — jump straight to phone input.
      this.state = "phone_input";
      this._render("phone_input");
    } else {
      this._render(
        "error",
        "Browser calling is not supported on this device and phone callback is disabled."
      );
    }
  }

  /**
   * Fetch the companion WebRTC bundle, then hand the call to it. A bundle that
   * will not load is treated like a browser without WebRTC support.
   */
  private async _startWebRTCCall(): Promise<void> {
    const campaign = this.campaign;
    if (!campaign) return;

    this._onStateChange("loading");

    let WebRTCClientCtor: WebRTCClientConstructor;
    try {
      WebRTCClientCtor = await loadWebRTCClient(this.baseUrl);
    } catch {
      if (campaign.allow_phone_callback) {
        this._onStateChange("phone_input");
      } else {
        this._onStateChange(
          "error",
          "Browser calling could not be loaded. Please reload the page and try again."
        );
      }
      return;
    }

    // The visitor may have navigated the widget elsewhere while it downloaded.
    if (this.campaign !== campaign || this.state !== "loading") return;

    this.webrtc = new WebRTCClientCtor(
      this.baseUrl,
      campaign,
      this._onStateChange,
      this._onTimerTick,
      this.selectedRepToken ?? undefined,
      this.selectedRepName
        ? { name: this.selectedRepName, title: this.selectedRepTitle ?? "" }
        : undefined
    );
    void this.webrtc.start();
  }

  private _submitPhone(phone: string): void {
    if (!this.campaign) return;

    const input = this.container.querySelector<HTMLInputElement>(
      "#pl-phone-input"
    );
    const errorEl =
      this.container.querySelector<HTMLElement>("#pl-phone-error");

    if (!phone) {
      input?.setAttribute("aria-invalid", "true");
      if (errorEl) errorEl.textContent = PHONE_REQUIRED;
      return;
    }

    input?.removeAttribute("aria-invalid");
    if (errorEl) errorEl.textContent = "";

    void submitPhoneFallback({
      baseUrl: this.baseUrl,
      campaignId: this.campaignId,
      phoneNumber: phone,
      repToken: this.selectedRepToken ?? undefined,
      onStateChange: this._onStateChange,
    });
  }

  private _resetRepSelection(): void {
    this.selectedRepToken = null;
    this.selectedRepName = null;
    this.selectedRepTitle = null;
    this.repSelectionReps = [];
    this.repSelectionMessage = undefined;
  }

  private _destroyClients(): void {
    this.webrtc?.destroy();
    this.webrtc = null;
    this.connectedData = null;
  }
}
