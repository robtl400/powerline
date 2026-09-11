import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("/recharts/") || id.includes("/victory-vendor/")) return "recharts";
          if (id.includes("/@dnd-kit/")) return "dnd-kit";
          if (
            id.includes("/react/") ||
            id.includes("/react-dom/") ||
            id.includes("/react-router/") ||
            id.includes("/react-router-dom/") ||
            id.includes("/scheduler/")
          ) {
            return "vendor";
          }
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
  server: {
    host: "0.0.0.0",
    port: 3000,
    // Comma-separated hostnames allowed to reach the dev server, e.g. a tunnel domain.
    allowedHosts: (process.env.VITE_ALLOWED_HOSTS ?? "")
      .split(",")
      .map((h) => h.trim())
      .filter(Boolean),
    proxy: {
      "/api": {
        // Inside Docker: backend resolves via service name.
        // Running locally: set VITE_BACKEND_URL=http://localhost:8000
        target: process.env.VITE_BACKEND_URL ?? "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
});
