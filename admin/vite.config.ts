/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: the console runs on :5173 and forwards /v1 to the McXus API on :8000 (same origin, no CORS).
const api = process.env.MCXUS_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": "/src" } },
  server: { port: 5173, proxy: { "/v1": api, "/health": api } },
  preview: { port: 4173, proxy: { "/v1": api, "/health": api } },
  test: { globals: true, environment: "jsdom", setupFiles: ["./src/test-setup.ts"], css: false },
});
