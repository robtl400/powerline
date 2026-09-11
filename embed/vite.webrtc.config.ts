import { defineConfig } from "vite";
import { BUNDLE_BASENAME, GLOBAL_NAME } from "./src/bundle-names.js";

// Companion bundle carrying the Twilio Voice SDK. The widget injects a script
// tag for it the first time a visitor starts a browser call, so the SDK never
// loads on pages where nobody calls.
export default defineConfig({
  build: {
    lib: {
      entry: "src/webrtc-entry.ts",
      name: GLOBAL_NAME,
      // Vite appends the format suffix: powerline-embed-webrtc.iife.js
      fileName: BUNDLE_BASENAME,
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
