/**
 * Unit tests for WebRTCClient state transitions.
 *
 * Covers the fallback/error paths and the audio-check heuristic without a real
 * Twilio SDK or backend:
 *   1. Mic permission denied (NotAllowedError) → phone_input state (phone fallback)
 *   2. Twilio Device "error" event → error state
 *   3. rep_token pass-through to the token request
 *   4. audio_check suppression once inbound audio is observed
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { WebRTCClient } from "./webrtc.js";
import { requestToken } from "./api.js";
import type { CampaignPublic } from "./types.js";

// ---------------------------------------------------------------------------
// Mock @twilio/voice-sdk
// ---------------------------------------------------------------------------

const twilio = vi.hoisted(() => {
  const mockRegister = vi.fn();
  const mockConnect = vi.fn();
  const mockDestroy = vi.fn();
  /** Captured device.on("error") handler so tests can fire it manually. */
  const captured: { deviceErrorHandler: ((err: { message?: string }) => void) | null } =
    { deviceErrorHandler: null };

  const MockDevice = vi.fn().mockImplementation(() => ({
    on: vi.fn((event: string, handler: unknown) => {
      if (event === "error") {
        captured.deviceErrorHandler = handler as (err: {
          message?: string;
        }) => void;
      }
    }),
    register: mockRegister,
    connect: mockConnect,
    destroy: mockDestroy,
  }));

  return { mockRegister, mockConnect, mockDestroy, MockDevice, captured };
});

const { mockRegister, mockConnect, mockDestroy, MockDevice } = twilio;

vi.mock("@twilio/voice-sdk", () => ({
  Device: twilio.MockDevice,
  Call: { Codec: { Opus: "opus", PCMU: "PCMU" } },
}));

// ---------------------------------------------------------------------------
// Mock ./api.js
// ---------------------------------------------------------------------------

vi.mock("./api.js", () => ({
  requestToken: vi.fn().mockResolvedValue({
    token: "test-token",
    session_id: "test-session-id",
  }),
}));

const mockRequestToken = vi.mocked(requestToken);

// ---------------------------------------------------------------------------
// Minimal campaign stub
// ---------------------------------------------------------------------------

const fakeCampaign: CampaignPublic = {
  id: "campaign-1",
  name: "Test Campaign",
  status: "live",
  targets: [
    {
      id: "target-1",
      name: "Senator Test",
      title: "Senator",
      location: "WA",
    },
  ],
  allow_phone_callback: true,
  allow_webrtc: true,
  target_ordering: "fixed",
  embed_config: null,
} as unknown as CampaignPublic;

/** Twilio Call stub that records handlers so tests can fire call events. */
function makeCallStub(): {
  on: ReturnType<typeof vi.fn>;
  fire: (event: string, ...args: unknown[]) => void;
} {
  const handlers: Record<string, ((...args: unknown[]) => void)[]> = {};
  return {
    on: vi.fn((event: string, handler: (...args: unknown[]) => void) => {
      (handlers[event] ??= []).push(handler);
    }),
    fire: (event: string, ...args: unknown[]) => {
      for (const h of handlers[event] ?? []) h(...args);
    },
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("WebRTCClient", () => {
  let onStateChange: ReturnType<typeof vi.fn>;
  let onTimerTick: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onStateChange = vi.fn();
    onTimerTick = vi.fn();
    twilio.captured.deviceErrorHandler = null;

    mockRegister.mockReset();
    mockConnect.mockReset();
    mockDestroy.mockReset();
    MockDevice.mockClear();
    mockRequestToken.mockReset();
    mockRequestToken.mockResolvedValue({
      token: "test-token",
      session_id: "test-session-id",
    });
  });

  it("mic permission denied → transitions to phone_input state", async () => {
    // Simulate browser denying mic access during device.register().
    mockRegister.mockRejectedValueOnce(
      new DOMException("Permission denied", "NotAllowedError")
    );

    const client = new WebRTCClient(
      "http://localhost",
      fakeCampaign,
      onStateChange,
      onTimerTick
    );

    await client.start();

    expect(onStateChange).toHaveBeenCalledWith("phone_input", "mic_denied");
    // Should NOT have gone to "error" — mic denial is a known recoverable path.
    const errorCalls = onStateChange.mock.calls.filter(
      ([state]) => state === "error"
    );
    expect(errorCalls).toHaveLength(0);
  });

  it("Twilio Device error event → transitions to error state", async () => {
    // register() succeeds, connect() returns a call stub that never fires events.
    mockRegister.mockResolvedValueOnce(undefined);
    mockConnect.mockResolvedValueOnce({ on: vi.fn() });

    const client = new WebRTCClient(
      "http://localhost",
      fakeCampaign,
      onStateChange,
      onTimerTick
    );

    await client.start();

    // The device error handler is registered synchronously inside start().
    // Fire it now to simulate a Twilio SDK device-level error.
    expect(twilio.captured.deviceErrorHandler).not.toBeNull();
    twilio.captured.deviceErrorHandler!({ message: "Network error" });

    expect(onStateChange).toHaveBeenCalledWith("error", "Network error");
  });

  it("passes the selected rep token to the token request", async () => {
    mockRegister.mockResolvedValueOnce(undefined);
    mockConnect.mockResolvedValueOnce({ on: vi.fn() });

    const client = new WebRTCClient(
      "http://localhost",
      fakeCampaign,
      onStateChange,
      onTimerTick,
      "rep-token-abc"
    );

    await client.start();

    expect(mockRequestToken).toHaveBeenCalledWith(
      "http://localhost",
      "campaign-1",
      "rep-token-abc"
    );
  });

  it("omits the rep token when none was selected", async () => {
    mockRegister.mockResolvedValueOnce(undefined);
    mockConnect.mockResolvedValueOnce({ on: vi.fn() });

    const client = new WebRTCClient(
      "http://localhost",
      fakeCampaign,
      onStateChange,
      onTimerTick
    );

    await client.start();

    expect(mockRequestToken).toHaveBeenCalledWith(
      "http://localhost",
      "campaign-1",
      undefined
    );
  });

  describe("audio check", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("emits audio_check when no inbound audio is heard", async () => {
      mockRegister.mockResolvedValueOnce(undefined);
      const call = makeCallStub();
      mockConnect.mockResolvedValueOnce(call);

      const client = new WebRTCClient(
        "http://localhost",
        fakeCampaign,
        onStateChange,
        onTimerTick
      );

      await client.start();
      call.fire("accept");

      await vi.advanceTimersByTimeAsync(10_000);

      const audioChecks = onStateChange.mock.calls.filter(
        ([state]) => state === "audio_check"
      );
      expect(audioChecks).toHaveLength(1);
    });

    it("suppresses audio_check after a volume event with output audio", async () => {
      mockRegister.mockResolvedValueOnce(undefined);
      const call = makeCallStub();
      mockConnect.mockResolvedValueOnce(call);

      const client = new WebRTCClient(
        "http://localhost",
        fakeCampaign,
        onStateChange,
        onTimerTick
      );

      await client.start();
      call.fire("accept");
      call.fire("volume", 0, 0.4);

      await vi.advanceTimersByTimeAsync(10_000);

      const audioChecks = onStateChange.mock.calls.filter(
        ([state]) => state === "audio_check"
      );
      expect(audioChecks).toHaveLength(0);
    });

    it("still emits audio_check when output volume stays at silence", async () => {
      mockRegister.mockResolvedValueOnce(undefined);
      const call = makeCallStub();
      mockConnect.mockResolvedValueOnce(call);

      const client = new WebRTCClient(
        "http://localhost",
        fakeCampaign,
        onStateChange,
        onTimerTick
      );

      await client.start();
      call.fire("accept");
      call.fire("volume", 0.6, 0);

      await vi.advanceTimersByTimeAsync(10_000);

      const audioChecks = onStateChange.mock.calls.filter(
        ([state]) => state === "audio_check"
      );
      expect(audioChecks).toHaveLength(1);
    });
  });
});
