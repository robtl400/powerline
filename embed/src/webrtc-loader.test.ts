/**
 * @vitest-environment jsdom
 */
/**
 * Unit tests for the on-demand WebRTC bundle loader.
 *
 * The loader reads document.currentScript when the module is evaluated, so each
 * test re-imports it with a stubbed script tag.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

type Loader = typeof import("./webrtc-loader.js");

const WIDGET_SRC = "https://cdn.example.org/static/powerline-embed.iife.js";
const COMPANION_SRC =
  "https://cdn.example.org/static/powerline-embed-webrtc.iife.js";

/** Re-import the loader with document.currentScript set to `src` (or absent). */
async function importLoader(src: string | null): Promise<Loader> {
  vi.resetModules();
  let currentScript: HTMLScriptElement | null = null;
  if (src !== null) {
    currentScript = document.createElement("script");
    currentScript.src = src;
  }
  Object.defineProperty(document, "currentScript", {
    configurable: true,
    value: currentScript,
  });
  return import("./webrtc-loader.js");
}

/** The script tag the loader appended, if any. */
function injected(): HTMLScriptElement[] {
  return Array.from(
    document.querySelectorAll<HTMLScriptElement>(
      'script[src*="powerline-embed-webrtc"]'
    )
  );
}

class FakeWebRTCClient {}

function publishGlobal(): void {
  (window as unknown as Record<string, unknown>).PowerlineWebRTC = {
    WebRTCClient: FakeWebRTCClient,
  };
}

beforeEach(() => {
  document.head.innerHTML = "";
  delete (window as unknown as Record<string, unknown>).PowerlineWebRTC;
});

afterEach(() => {
  Object.defineProperty(document, "currentScript", {
    configurable: true,
    value: null,
  });
});

describe("resolveWebRTCBundleUrl", () => {
  it("puts the companion bundle beside the widget bundle", async () => {
    const { resolveWebRTCBundleUrl } = await importLoader(WIDGET_SRC);

    expect(resolveWebRTCBundleUrl("https://api.example.org")).toBe(
      COMPANION_SRC
    );
  });

  it("keeps the cache-busting query the host page pinned", async () => {
    const { resolveWebRTCBundleUrl } = await importLoader(
      `${WIDGET_SRC}?v=2.0.4.0`
    );

    expect(resolveWebRTCBundleUrl("https://api.example.org")).toBe(
      `${COMPANION_SRC}?v=2.0.4.0`
    );
  });

  it("falls back to the API origin when there is no script tag", async () => {
    const { resolveWebRTCBundleUrl } = await importLoader(null);

    expect(resolveWebRTCBundleUrl("https://api.example.org/")).toBe(
      "https://api.example.org/static/powerline-embed-webrtc.iife.js"
    );
  });
});

describe("loadWebRTCClient", () => {
  it("injects the bundle and resolves with the published constructor", async () => {
    const { loadWebRTCClient } = await importLoader(WIDGET_SRC);

    const pending = loadWebRTCClient("https://api.example.org");
    const [script] = injected();
    expect(script.src).toBe(COMPANION_SRC);
    expect(script.async).toBe(true);

    publishGlobal();
    script.onload!(new Event("load"));

    await expect(pending).resolves.toBe(FakeWebRTCClient);
  });

  it("injects the bundle only once", async () => {
    const { loadWebRTCClient } = await importLoader(WIDGET_SRC);

    const first = loadWebRTCClient("https://api.example.org");
    const second = loadWebRTCClient("https://api.example.org");
    expect(injected()).toHaveLength(1);

    publishGlobal();
    injected()[0].onload!(new Event("load"));

    await expect(first).resolves.toBe(FakeWebRTCClient);
    await expect(second).resolves.toBe(FakeWebRTCClient);

    await expect(loadWebRTCClient("https://api.example.org")).resolves.toBe(
      FakeWebRTCClient
    );
    expect(injected()).toHaveLength(1);
  });

  it("serves an idle prefetch and a later click from one script tag", async () => {
    const { loadWebRTCClient } = await importLoader(WIDGET_SRC);

    const prefetched = loadWebRTCClient("https://api.example.org");
    expect(injected()).toHaveLength(1);

    publishGlobal();
    injected()[0].onload!(new Event("load"));
    await expect(prefetched).resolves.toBe(FakeWebRTCClient);

    const onClick = loadWebRTCClient("https://api.example.org");

    await expect(onClick).resolves.toBe(FakeWebRTCClient);
    expect(injected()).toHaveLength(1);
  });

  it("rejects when the bundle cannot be fetched", async () => {
    const { loadWebRTCClient } = await importLoader(WIDGET_SRC);

    const pending = loadWebRTCClient("https://api.example.org");
    injected()[0].onerror!(new Event("error"));

    await expect(pending).rejects.toThrow("Browser calling could not be loaded");
  });

  it("rejects when the bundle loads without publishing its global", async () => {
    const { loadWebRTCClient } = await importLoader(WIDGET_SRC);

    const pending = loadWebRTCClient("https://api.example.org");
    injected()[0].onload!(new Event("load"));

    await expect(pending).rejects.toThrow("Browser calling could not be loaded");
  });

  it("retries after a failed fetch", async () => {
    const { loadWebRTCClient } = await importLoader(WIDGET_SRC);

    const failed = loadWebRTCClient("https://api.example.org");
    injected()[0].onerror!(new Event("error"));
    await expect(failed).rejects.toThrow();

    document.head.innerHTML = "";
    const retried = loadWebRTCClient("https://api.example.org");
    expect(injected()).toHaveLength(1);

    publishGlobal();
    injected()[0].onload!(new Event("load"));
    await expect(retried).resolves.toBe(FakeWebRTCClient);
  });
});
