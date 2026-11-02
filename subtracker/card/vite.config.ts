import { defineConfig } from "vite";

// one self-contained ES module that Home Assistant loads as a dashboard resource
export default defineConfig({
  build: {
    lib: { entry: "src/subtracker-card.ts", formats: ["es"], fileName: () => "subtracker-card.js" },
    outDir: "dist",
    emptyOutDir: true,
  },
});
