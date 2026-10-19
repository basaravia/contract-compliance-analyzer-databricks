/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
    // La CSP del backend no permite scripts ni estilos en línea: nada de inlining de assets.
    assetsInlineLimit: 0,
    cssCodeSplit: false,
  },
  server: {
    port: 5173,
    // En desarrollo (`npm run dev`) el backend FastAPI corre aparte (AUTH_MODE=local).
    proxy: { "/api": backend, "/auth": backend, "/healthz": backend },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
