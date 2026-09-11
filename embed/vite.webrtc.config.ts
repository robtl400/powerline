import { defineConfig } from "vite";

// Companion bundle carrying the Twilio Voice SDK. The widget injects a script
// tag for it the first time a visitor starts a browser call, so the SDK never
// loads on pages where nobody calls.
export default defineConfig({
  build: {
    lib: {
      entry: "src/webrtc-entry.ts",
      name: "PowerlineWebRTC",
      // Vite appends the format suffix: powerline-embed-webrtc.iife.js
      fileName: "powerline-embed-webrtc",
      formats: ["iife"],
    },
    outDir: "dist",
    // The widget build runs first and owns the directory.
    emptyOutDir: false,
    rollupOptions: {
      external: [],
    },
    minify: true,
    sourcemap: true,
  },
});
