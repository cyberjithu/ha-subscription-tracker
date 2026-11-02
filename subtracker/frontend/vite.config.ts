import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./", // Ingress serves the app under a per-session path prefix
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { proxy: { "/api": "http://localhost:8099" } },
  build: { outDir: "../app/static", emptyOutDir: true, chunkSizeWarningLimit: 800 }, // served by FastAPI
});
