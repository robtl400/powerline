/**
 * Entry point for the companion WebRTC bundle.
 *
 * Built separately from the main widget (see vite.webrtc.config.ts) so the
 * Twilio Voice SDK is downloaded only by visitors who start a browser call.
 * The IIFE publishes `window.PowerlineWebRTC.WebRTCClient`, which
 * ./webrtc-loader.ts reads once the script has loaded.
 */
export { WebRTCClient } from "./webrtc.js";
