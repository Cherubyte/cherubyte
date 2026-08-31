import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));

// Dev server proxies the API to the backend on :1001 (override with CHERUBYTE_API).
const api = process.env.CHERUBYTE_API ?? "http://localhost:1001";
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: api, changeOrigin: true },
      "/uploads": { target: api, changeOrigin: true },
    },
  },
  build: { outDir: "dist" },
});
