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
import { fetchCampaign, fetchReps } from "./api.js";
import { WebRTCClient } from "./webrtc.js";
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

vi.mock("./webrtc.js", () => ({
  WebRTCClient: vi.fn().mockImplementation(() => ({
    start: vi.fn(async () => {}),
    destroy: vi.fn(),
    cancelAudioCheck: vi.fn(),
    skip: vi.fn(),
    end: vi.fn(),
  })),
}));

const mockFetchCampaign = vi.mocked(fetchCampaign);
const mockFetchReps = vi.mocked(fetchReps);
const MockWebRTCClient = vi.mocked(WebRTCClient);

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
    mockFetchCampaign.mockResolvedValue(fakeCampaign);

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

describe("PowerlineWidget connected screen", () => {
  let container: HTMLElement;
  let onStateChange: StateDriver;

  beforeEach(async () => {
    document.body.innerHTML = "";
    container = document.createElement("div");
    document.body.appendChild(container);
    mockFetchCampaign.mockResolvedValue(fakeCampaign);

    const widget = new PowerlineWidget({
      campaignId: "campaign-1",
      container,
    });
    await widget.init();
    onStateChange = driverFor(widget);
  });

  it("shows the selected rep and their position in the dial order", () => {
    onStateChange("connected", {
      target: {
        id: "rep",
        name: "Rep Example",
        title: "U.S. Representative",
        location: "",
      },
      targetIndex: 0,
      totalTargets: 2,
    } satisfies ConnectedData);

    expect(container.innerHTML).toContain("Rep Example");
    expect(container.innerHTML).toContain("U.S. Representative");
    expect(container.innerHTML).toContain("Call 1 of 2");
  });

  it("replaces the mic screen with a generic card when the target is unknown", () => {
    onStateChange("mic_permission");
    expect(container.innerHTML).toContain("Microphone Access");

    onStateChange("connected");

    expect(container.innerHTML).not.toContain("Microphone Access");
    expect(container.innerHTML).toContain("Connected");
    expect(container.innerHTML).toContain("00:00");
    expect(container.querySelector('[data-pl-action="end"]')).not.toBeNull();
  });
});

describe("PowerlineWidget rep selection", () => {
  const repCampaign: CampaignPublic = {
    ...fakeCampaign,
    target_levels: ["federal"],
  };

  let container: HTMLElement;

  beforeEach(async () => {
    document.body.innerHTML = "";
    container = document.createElement("div");
    document.body.appendChild(container);

    // jsdom has no WebRTC — the widget only reaches WebRTCClient if it sees one.
    vi.stubGlobal("RTCPeerConnection", vi.fn());
    MockWebRTCClient.mockClear();
    mockFetchCampaign.mockResolvedValue(repCampaign);
    mockFetchReps.mockResolvedValue({
      reps: [
        {
          name: "Rep Example",
          title: "U.S. Representative",
          level: "federal",
          rep_token: "tok-1",
        },
      ],
      message: null,
    });

    const widget = new PowerlineWidget({
      campaignId: "campaign-1",
      container,
    });
    await widget.init();

    const zip = container.querySelector<HTMLInputElement>("#pl-zip-input");
    zip!.value = "94103";
    container
      .querySelector<HTMLElement>('[data-pl-action="call-now"]')!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    await vi.waitFor(() =>
      expect(
        container.querySelector('[data-pl-action="select-rep"]')
      ).not.toBeNull()
    );
  });

  it("carries the rep's display name and title on the choice button", () => {
    const button = container.querySelector<HTMLElement>(
      '[data-pl-action="select-rep"]'
    );

    expect(button!.dataset.plRepToken).toBe("tok-1");
    expect(button!.dataset.plName).toBe("Rep Example");
    expect(button!.dataset.plTitle).toBe("U.S. Representative");
  });

  it("hands the rep token and display info to the WebRTC client", () => {
    container
      .querySelector<HTMLElement>('[data-pl-action="select-rep"]')!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    expect(MockWebRTCClient).toHaveBeenCalledTimes(1);
    const args = MockWebRTCClient.mock.calls[0];
    expect(args[4]).toBe("tok-1");
    expect(args[5]).toEqual({
      name: "Rep Example",
      title: "U.S. Representative",
    });
  });
});
