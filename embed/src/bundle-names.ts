/**
 * Names the companion WebRTC bundle is built with and loaded by. Shared by
 * vite.webrtc.config.ts (which emits it) and webrtc-loader.ts (which fetches
 * it), so the two can never drift apart.
 */

/** Vite `lib.fileName` — the format suffix is appended by the build. */
export const BUNDLE_BASENAME = "powerline-embed-webrtc";

/** Emitted filename, a sibling of the widget bundle in /static. */
export const BUNDLE_FILENAME = `${BUNDLE_BASENAME}.iife.js`;

/** Global the companion bundle publishes (Vite `lib.name`). */
export const GLOBAL_NAME = "PowerlineWebRTC";
