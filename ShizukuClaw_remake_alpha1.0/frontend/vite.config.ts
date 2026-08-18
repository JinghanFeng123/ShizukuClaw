import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

function backendTarget(): string {
  const portFile = resolve(__dirname, "../data/dev_port.txt");
  if (existsSync(portFile)) {
    const port = readFileSync(portFile, "utf8").trim();
    if (/^\d+$/.test(port)) {
      return `http://127.0.0.1:${port}`;
    }
  }
  return "http://127.0.0.1:8888";
}

const target = backendTarget();

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": target,
      "/v1": target,
      "/health": target,
      "/docs": target,
      "/stream_logs": {
        target,
        changeOrigin: true
      }
    }
  }
});
