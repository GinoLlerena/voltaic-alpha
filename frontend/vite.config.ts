import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // The API is same-origin in production. In development it runs on loopback
    // 8600, so the dev server proxies rather than the browser learning a second
    // origin -- which would need CORS the API deliberately does not enable.
    proxy: { "/api": { target: "http://127.0.0.1:8600", changeOrigin: false } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
