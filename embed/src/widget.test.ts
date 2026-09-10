/**
 * @vitest-environment jsdom
 */
/**
 * Unit tests for PowerlineWidget rendering decisions, driven through the DOM.
 *
 * The audio-check screen must only ever replace a live call — a stray timer
 * firing after a disconnect must not clobber the completion or idle screen.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PowerlineWidget } from "./widget.js";
import type { CampaignPublic, ConnectedData, WidgetState } from "./types.js";

vi.mock("@twilio/voice-sdk", () => ({
  Device: vi.fn(),
  Call: { Codec: { Opus: "opus", PCMU: "PCMU" } },
}));

const fakeCampaign: CampaignPublic = {
  id: "campaign-1",
  name: "Test Campaign",
  description: null,
  talking_points: null,
  allow_webrtc: true,
  allow_phone_callback: true,
  targets: [
    { id: "target-1", name: "Senator Test", title: "Senator", location: "WA" },
  ],
};

vi.mock("./api.js", () => ({
  fetchCampaign: vi.fn(async () => fakeCampaign),
  fetchCallCount: vi.fn(async () => ({ total: 0, last_24h: 0, last_7d: 0 })),
  fetchReps: vi.fn(async () => ({ reps: [], message: null })),
  isRepsError: vi.fn(() => false),
}));

type StateDriver = (state: WidgetState, data?: unknown) => void;

/** Reach the widget's internal state callback the way its clients do. */
function driverFor(widget: PowerlineWidget): StateDriver {
  return (widget as unknown as { _onStateChange: StateDriver })._onStateChange;
}

const connectedData: ConnectedData = {
  target: fakeCampaign.targets[0],
  targetIndex: 0,
  totalTargets: 1,
};

describe("PowerlineWidget audio check", () => {
  let container: HTMLElement;
  let widget: PowerlineWidget;
  let onStateChange: StateDriver;

  beforeEach(async () => {
    document.body.innerHTML = "";
    container = document.createElement("div");
    document.body.appendChild(container);

    widget = new PowerlineWidget({ campaignId: "campaign-1", container });
    await widget.init();
    onStateChange = driverFor(widget);
  });

  it("ignores audio_check while idle", () => {
    onStateChange("audio_check");

    expect(container.innerHTML).not.toContain("hear anything");
    expect(container.innerHTML).toContain("Call Now");
  });

  it("ignores audio_check after the call has completed", () => {
    onStateChange("connected", connectedData);
    onStateChange("complete");

    onStateChange("audio_check");

    expect(container.innerHTML).not.toContain("hear anything");
    expect(container.innerHTML).toContain("Thank you!");
  });

  it("shows the audio check while connected", () => {
    onStateChange("connected", connectedData);

    onStateChange("audio_check");

    expect(container.innerHTML).toContain("hear anything");
  });

  it("returns to the call when the audio check is dismissed", () => {
    onStateChange("connected", connectedData);
    onStateChange("audio_check");

    const dismiss = container.querySelector<HTMLElement>(
      '[data-pl-action="dismiss-audio-check"]'
    );
    expect(dismiss).not.toBeNull();
    dismiss!.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    expect(container.innerHTML).not.toContain("hear anything");
    expect(container.innerHTML).toContain("Senator Test");
  });
});
