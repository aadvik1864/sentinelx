import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

const root = fileURLToPath(new URL(".", import.meta.url));
const file = (path: string) => fileURLToPath(new URL(path, import.meta.url));

// Keep Motion's bundled diagnostic consistent with the project's copy.
const publicationPunctuation: Plugin = {
  name: "publication-punctuation",
  apply: "build",
  renderChunk(code) {
    const normalized = code.replaceAll(
      ` times ${String.fromCodePoint(0x2014)} ignoring repeat option.`,
      " times, ignoring repeat option.",
    );
    return normalized === code ? null : { code: normalized, map: null };
  },
};

export default defineConfig({
  root,
  base: "/",
  publicDir: file("./public"),
  envPrefix: "VITE_",
  plugins: [react(), tailwindcss(), publicationPunctuation],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["e2e/**", "node_modules/**"],
  },
  build: {
    outDir: file("./dist"),
    emptyOutDir: true,
    modulePreload: { polyfill: true },
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("recharts")) return "charts";
          if (id.includes("@xyflow/react")) return "graph";
        },
      },
    },
  },
});
