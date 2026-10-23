import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the Python server runs on :8000 and Vite proxies API and WebSocket calls to it.
export default defineConfig({
  plugins: [react()],
  // The lazily loaded 3D viewer chunk (three.js) is ~860 kB on its own.
  build: { chunkSizeWarningLimit: 1000 },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
