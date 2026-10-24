import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// vite.config.ts is type-checked with src/ and @types/node is not installed.
declare const process: { env: Record<string, string | undefined> };

// In development the Python server runs on :8000 and Vite proxies API and WebSocket calls to it.
// Under Docker Compose, API_TARGET points at the sim container instead.
const apiTarget = process.env.API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  // The lazily loaded 3D viewer chunk (three.js) is ~860 kB on its own.
  build: { chunkSizeWarningLimit: 1000 },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/ws": { target: apiTarget, ws: true },
    },
  },
});
