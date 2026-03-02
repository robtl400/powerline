import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: {
      entry: "src/index.ts",
      name: "Powerline",
      // Vite appends the format suffix: powerline-embed.iife.js
      fileName: "powerline-embed",
      formats: ["iife"],
    },
    outDir: "dist",
    // Bundle everything — the widget must be self-contained on third-party sites.
    rollupOptions: {
      external: [],
    },
    // Keep the bundle readable enough for debugging in dev.
    minify: false,
  },
});
