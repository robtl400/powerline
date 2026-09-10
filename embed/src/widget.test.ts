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
import { fetchCallCount, fetchCampaign, fetchReps, isRepsError } from "./api.js";
import { renderIdle } from "./ui/templates.js";
import { injectStyles } from "./ui/styles.js";
import { WebRTCClient } from "./webrtc.js";
import { PowerlineWidget } from "./widget.js";
import type { CampaignPublic, ConnectedData, WidgetState } from "./types.js";

/** Matches any emoji / pictographic character, so the widget never renders one. */
const EMOJI_RE = /\p{Extended_Pictographic}/u;

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
const mockFetchCallCount = vi.mocked(fetchCallCount);
const mockIsRepsError = vi.mocked(isRepsError);
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

  it("renders the End Call button with an icon instead of a red fill", () => {
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

    const endButton = container.querySelector('[data-pl-action="end"]');
    expect(endButton).not.toBeNull();
    expect(endButton?.innerHTML).toContain("<svg");
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

describe("PowerlineWidget rep lookup", () => {
  const repCampaign: CampaignPublic = {
    ...fakeCampaign,
    target_levels: ["federal"],
  };

  let container: HTMLElement;
  let widget: PowerlineWidget;

  /** Type a ZIP into the idle screen and press Call Now. */
  function callNowWithZip(zip: string): void {
    container.querySelector<HTMLInputElement>("#pl-zip-input")!.value = zip;
    container
      .querySelector<HTMLElement>('[data-pl-action="call-now"]')!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }

  beforeEach(async () => {
    document.body.innerHTML = "";
    container = document.createElement("div");
    document.body.appendChild(container);

    MockWebRTCClient.mockClear();
    mockFetchReps.mockReset();
    mockIsRepsError.mockReset();
    mockIsRepsError.mockReturnValue(false);
    mockFetchCampaign.mockResolvedValue(repCampaign);

    widget = new PowerlineWidget({ campaignId: "campaign-1", container });
    await widget.init();
  });

  it("rejects a malformed ZIP without hitting the reps endpoint", () => {
    callNowWithZip("9410");

    expect(
      container.querySelector<HTMLElement>("#pl-zip-error")!.textContent
    ).toBe("Please enter a valid 5-digit ZIP code.");
    expect(
      container
        .querySelector<HTMLInputElement>("#pl-zip-input")!
        .getAttribute("aria-invalid")
    ).toBe("true");
    expect(mockFetchReps).not.toHaveBeenCalled();
  });

  it("shows the lookup spinner, then the rep buttons", async () => {
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

    callNowWithZip("94103");

    expect(container.innerHTML).toContain("Finding your representatives");
    expect(mockFetchReps).toHaveBeenCalledWith("", "campaign-1", "94103");

    await vi.waitFor(() =>
      expect(
        container.querySelector('[data-pl-action="select-rep"]')
      ).not.toBeNull()
    );

    const button = container.querySelector<HTMLElement>(
      '[data-pl-action="select-rep"]'
    )!;
    expect(button.dataset.plRepToken).toBe("tok-1");
    expect(container.innerHTML).toContain("Choose who to call");
  });

  it("falls back to phone entry with the backend's message on a lookup outage", async () => {
    mockFetchReps.mockResolvedValue({
      fallback: "manual_entry",
      message: "Lookup is down — leave us your number.",
    });
    mockIsRepsError.mockReturnValue(true);

    callNowWithZip("94103");

    await vi.waitFor(() =>
      expect(
        container.querySelector('[data-pl-action="submit-phone"]')
      ).not.toBeNull()
    );

    expect(container.innerHTML).toContain("Lookup is down — leave us your number.");
  });

  it("surfaces a lookup failure as an error screen", async () => {
    mockFetchReps.mockRejectedValue(new Error("ZIP service unavailable"));

    callNowWithZip("94103");

    await vi.waitFor(() =>
      expect(container.innerHTML).toContain("ZIP service unavailable")
    );
    expect(container.innerHTML).toContain("Something went wrong");
  });

  it("returns to the ZIP form when the rep selection has expired", async () => {
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

    callNowWithZip("94103");
    await vi.waitFor(() =>
      expect(
        container.querySelector('[data-pl-action="select-rep"]')
      ).not.toBeNull()
    );
    container
      .querySelector<HTMLElement>('[data-pl-action="select-rep"]')!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    driverFor(widget)("error", "Invalid or expired representative selection");

    expect(container.querySelector("#pl-zip-input")).not.toBeNull();
    expect(
      container.querySelector<HTMLElement>("#pl-zip-error")!.textContent
    ).toBe("Invalid or expired representative selection");
    expect(container.innerHTML).not.toContain("Something went wrong");
  });
});

describe("injected styles", () => {
  it("contains no red hex values", () => {
    document.getElementById("pl-widget-styles")?.remove();
    injectStyles();

    const styleEl = document.getElementById("pl-widget-styles");
    expect(styleEl?.textContent ?? "").not.toMatch(/#(dc2626|ef4444|b91c1c|f87171)/i);
  });
});

describe("renderIdle icons", () => {
  it("uses inline SVG instead of emoji for the call-to-action", () => {
    const html = renderIdle(fakeCampaign);

    expect(EMOJI_RE.test(html)).toBe(false);
    expect(html).toContain("<svg");
  });
});

describe("PowerlineWidget completion screen", () => {
  let container: HTMLElement;
  let widget: PowerlineWidget;

  beforeEach(async () => {
    document.body.innerHTML = "";
    container = document.createElement("div");
    document.body.appendChild(container);

    mockFetchCallCount.mockReset();
    mockFetchCampaign.mockResolvedValue(fakeCampaign);

    widget = new PowerlineWidget({ campaignId: "campaign-1", container });
    await widget.init();
  });

  it("adds the campaign-wide caller count once it arrives", async () => {
    mockFetchCallCount.mockResolvedValue({
      total: 1234,
      last_24h: 12,
      last_7d: 90,
    });

    driverFor(widget)("connected", connectedData);
    driverFor(widget)("complete");

    expect(mockFetchCallCount).toHaveBeenCalledWith("", "campaign-1");

    await vi.waitFor(() =>
      expect(container.innerHTML).toContain("You're among")
    );
    expect(container.innerHTML).toContain("1,234");
    expect(container.innerHTML).toContain("You made 1 call.");
  });

  it("keeps the session count when no callers are reported", async () => {
    mockFetchCallCount.mockResolvedValue({ total: 0, last_24h: 0, last_7d: 0 });

    driverFor(widget)("connected", connectedData);
    driverFor(widget)("complete");

    await vi.waitFor(() => expect(mockFetchCallCount).toHaveBeenCalled());

    expect(container.innerHTML).toContain("Thank you!");
    expect(container.innerHTML).not.toContain("You're among");
  });

  it("flashes 'Copied!' on the copy-link button for two seconds", async () => {
    // The count fetch failing keeps the completion screen from re-rendering
    // underneath the button while the label is swapped.
    mockFetchCallCount.mockRejectedValue(new Error("counts unavailable"));
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    vi.useFakeTimers();
    try {
      driverFor(widget)("connected", connectedData);
      driverFor(widget)("complete");

      const button = container.querySelector<HTMLElement>(
        '[data-pl-action="copy-link"]'
      )!;
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));

      expect(writeText).toHaveBeenCalledTimes(1);
      expect(button.textContent).toBe("Copied!");

      await vi.advanceTimersByTimeAsync(2_000);

      expect(button.textContent).toBe("Copy Link");
    } finally {
      vi.useRealTimers();
    }
  });
});
