/**
 * Unit tests for WebRTCClient state transitions.
 *
 * Tests the two key fallback/error paths without a real Twilio SDK or backend:
 *   1. Mic permission denied (NotAllowedError) → phone_input state (phone fallback)
 *   2. Twilio Device "error" event → error state
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WebRTCClient } from "./webrtc.js";
import type { CampaignPublic } from "./types.js";

// ---------------------------------------------------------------------------
// Mock @twilio/voice-sdk
// ---------------------------------------------------------------------------

/** Captured device.on("error") handler so tests can fire it manually. */
let capturedDeviceErrorHandler: ((err: { message?: string }) => void) | null =
  null;

const mockRegister = vi.fn();
const mockConnect = vi.fn();
const mockDestroy = vi.fn();

const MockDevice = vi.fn().mockImplementation(() => ({
  on: vi.fn((event: string, handler: unknown) => {
    if (event === "error") {
      capturedDeviceErrorHandler = handler as (err: {
        message?: string;
      }) => void;
    }
  }),
  register: mockRegister,
  connect: mockConnect,
  destroy: mockDestroy,
}));

vi.mock("@twilio/voice-sdk", () => ({
  Device: MockDevice,
  Call: { Codec: { Opus: "opus", PCMU: "PCMU" } },
}));

// ---------------------------------------------------------------------------
// Mock ./api.js
// ---------------------------------------------------------------------------

vi.mock("./api.js", () => ({
  requestTokenWithOverride: vi.fn().mockResolvedValue({
    token: "test-token",
    session_id: "test-session-id",
  }),
}));

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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("WebRTCClient", () => {
  let onStateChange: ReturnType<typeof vi.fn>;
  let onTimerTick: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onStateChange = vi.fn();
    onTimerTick = vi.fn();
    capturedDeviceErrorHandler = null;

    mockRegister.mockReset();
    mockConnect.mockReset();
    mockDestroy.mockReset();
    MockDevice.mockClear();
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
    mockConnect.mockResolvedValueOnce({
      on: vi.fn(),
    });

    const client = new WebRTCClient(
      "http://localhost",
      fakeCampaign,
      onStateChange,
      onTimerTick
    );

    await client.start();

    // The device error handler is registered synchronously inside start().
    // Fire it now to simulate a Twilio SDK device-level error.
    expect(capturedDeviceErrorHandler).not.toBeNull();
    capturedDeviceErrorHandler!({ message: "Network error" });

    expect(onStateChange).toHaveBeenCalledWith("error", "Network error");
  });
});
