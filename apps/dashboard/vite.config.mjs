import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backendBaseUrl = process.env.MISSION_CONTROL_API_BASE_URL || process.env.MISSION_CONTROL_BACKEND_URL || "http://127.0.0.1:8010";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: backendBaseUrl,
        changeOrigin: true,
      },
    },
  },
});
