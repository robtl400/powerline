/**
 * @vitest-environment jsdom
 */
/**
 * Auto-init container resolution and configuration guards.
 *
 * document.currentScript is only readable while a script is executing, so
 * autoInit/resolveContainer take the script element as an argument and the
 * module-level bootstrap passes the captured currentScript.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { autoInit, resolveContainer } from "./index.js";

vi.mock("@twilio/voice-sdk", () => ({
  Device: vi.fn(),
  Call: { Codec: { Opus: "opus", PCMU: "PCMU" } },
}));

vi.mock("./api.js", () => ({
  fetchCampaign: vi.fn(async () => {
    throw new Error("fetchCampaign should not run without an api url");
  }),
  fetchCallCount: vi.fn(),
  fetchReps: vi.fn(),
  isRepsError: vi.fn(() => false),
}));

function scriptWith(data: Record<string, string>): HTMLScriptElement {
  const script = document.createElement("script");
  for (const [key, value] of Object.entries(data)) {
    script.dataset[key] = value;
  }
  return script;
}

describe("resolveContainer", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("uses #powerline-widget when the page provides it", () => {
    const host = document.createElement("div");
    host.id = "powerline-widget";
    document.body.appendChild(host);

    expect(resolveContainer(scriptWith({}))).toBe(host);
    expect(document.body.children).toHaveLength(1);
  });

  it("uses the element named by data-container", () => {
    const host = document.createElement("section");
    host.id = "call-here";
    document.body.appendChild(host);

    expect(resolveContainer(scriptWith({ container: "call-here" }))).toBe(host);
  });

  it("appends its own div when no container exists", () => {
    const container = resolveContainer(scriptWith({}));

    expect(container.tagName).toBe("DIV");
    expect(container.parentElement).toBe(document.body);
  });

  it("appends its own div when data-container names a missing element", () => {
    const container = resolveContainer(scriptWith({ container: "nope" }));

    expect(container.parentElement).toBe(document.body);
  });
});

describe("autoInit", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("renders into #powerline-widget", () => {
    const host = document.createElement("div");
    host.id = "powerline-widget";
    document.body.appendChild(host);

    autoInit(
      scriptWith({ campaign: "campaign-1", apiUrl: "https://api.example.com" })
    );

    expect(host.getAttribute("data-pl-root")).toBe("campaign-1");
    expect(document.body.children).toHaveLength(1);
  });

  it("renders a configuration error when data-api-url is missing", () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const host = document.createElement("div");
    host.id = "powerline-widget";
    document.body.appendChild(host);

    autoInit(scriptWith({ campaign: "campaign-1" }));

    expect(error).toHaveBeenCalledWith("[Powerline] data-api-url is required");
    expect(host.innerHTML).toContain("data-api-url");
    expect(host.innerHTML).not.toContain("Call Now");
  });

  it("does nothing without a campaign id", () => {
    autoInit(scriptWith({ apiUrl: "https://api.example.com" }));

    expect(document.body.innerHTML).toBe("");
  });
});
