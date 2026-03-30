import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/awarenet/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/assistant": "http://localhost:8000",
      "/v1": "http://localhost:8000",
    },
  },
});
