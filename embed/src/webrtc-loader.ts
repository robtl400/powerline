/**
 * On-demand loader for the companion WebRTC bundle.
 *
 * The widget bundle is an IIFE, so a dynamic import would be inlined rather
 * than split. The Twilio Voice SDK therefore lives in its own IIFE, fetched by
 * injecting a script tag the first time a visitor starts a browser call.
 */
import type { WebRTCClient } from "./webrtc.js";

export type WebRTCClientConstructor = typeof WebRTCClient;

/** Sibling of the widget bundle in the same /static directory. */
const BUNDLE_FILENAME = "powerline-embed-webrtc.iife.js";

/** Global the companion bundle publishes (vite.webrtc.config.ts `lib.name`). */
const GLOBAL_NAME = "PowerlineWebRTC";

const LOAD_FAILED = "Browser calling could not be loaded.";

// currentScript is readable only while the widget bundle's own script tag runs,
// so the reference is captured here at module evaluation time.
const widgetScript = document.currentScript as HTMLScriptElement | null;

let pending: Promise<WebRTCClientConstructor> | null = null;

function readGlobal(): WebRTCClientConstructor | null {
  const published = (window as unknown as Record<string, unknown>)[GLOBAL_NAME];
  const ctor = (published as { WebRTCClient?: unknown } | undefined)
    ?.WebRTCClient;
  return typeof ctor === "function" ? (ctor as WebRTCClientConstructor) : null;
}

/**
 * URL of the companion bundle: a sibling of the widget bundle, keeping any
 * cache-busting query the host page pinned the widget to. Falls back to the
 * API origin's /static when the widget script tag cannot be identified.
 */
export function resolveWebRTCBundleUrl(apiUrl: string): string {
  const src = widgetScript?.src;
  if (src) {
    try {
      const url = new URL(src, document.baseURI);
      url.pathname = url.pathname.replace(/[^/]*$/, BUNDLE_FILENAME);
      return url.toString();
    } catch {
      // An unparseable src falls through to the API-relative form below.
    }
  }
  return `${apiUrl.replace(/\/$/, "")}/static/${BUNDLE_FILENAME}`;
}

/**
 * Resolve with the WebRTCClient constructor, fetching the companion bundle on
 * the first call and reusing it afterwards. Rejects when the script fails to
 * load so the widget can offer the phone fallback instead.
 */
export function loadWebRTCClient(
  apiUrl: string
): Promise<WebRTCClientConstructor> {
  const loaded = readGlobal();
  if (loaded) return Promise.resolve(loaded);
  if (pending) return pending;

  const request = new Promise<WebRTCClientConstructor>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = resolveWebRTCBundleUrl(apiUrl);
    script.async = true;
    script.onload = () => {
      const ctor = readGlobal();
      if (ctor) resolve(ctor);
      else reject(new Error(LOAD_FAILED));
    };
    script.onerror = () => reject(new Error(LOAD_FAILED));
    (document.head ?? document.documentElement).appendChild(script);
  });

  pending = request;
  request.catch(() => {
    if (pending === request) pending = null;
  });
  return request;
}
