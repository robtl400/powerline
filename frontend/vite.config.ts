import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 3000,
    allowedHosts: ["caylee-implacable-lostly.ngrok-free.dev"],
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
