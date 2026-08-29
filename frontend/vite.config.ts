import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies the API to the backend on :1001.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:1001", changeOrigin: true },
      "/uploads": { target: "http://localhost:1001", changeOrigin: true },
    },
  },
  build: { outDir: "dist" },
});
