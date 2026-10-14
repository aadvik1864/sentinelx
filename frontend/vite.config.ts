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

const showcaseBoundary: Plugin = {
  name: "showcase-boundary",
  generateBundle() {
    const forbidden = [
      "src/services/api.ts",
      "src/services/connection.ts",
      "src/store/AuthContext.tsx",
      "src/store/LiveContext.tsx",
      "src/pages/Login.tsx",
      "src/pages/Settings.tsx",
      "src/pages/Sources.tsx",
    ];
    for (const id of this.getModuleIds()) {
      if (forbidden.some((path) => id.split("?")[0] === file(path))) {
        this.error(`The public showcase must not include ${id}.`);
      }
    }
    this.emitFile({
      type: "asset",
      fileName: "_headers",
      source:
        "/*\n  Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'\n  Referrer-Policy: no-referrer\n  X-Content-Type-Options: nosniff\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n",
    });
  },
};

export default defineConfig(({ mode }) => {
  const showcase = mode === "showcase";
  return {
    root: showcase ? file("./showcase") : root,
    base: showcase ? "./" : "/",
    publicDir: file("./public"),
    envPrefix: showcase ? [] : "VITE_",
    plugins: [react(), tailwindcss(), publicationPunctuation, ...(showcase ? [showcaseBoundary] : [])],
    resolve: {
      alias: showcase
        ? [
            {
              find: /^(?:\.\.?\/)+services\/api$/,
              replacement: file("./showcase/api.ts"),
            },
            {
              find: /^(?:\.\.?\/)+store\/AuthContext$/,
              replacement: file("./showcase/auth.ts"),
            },
          ]
        : [],
    },
    server: showcase
      ? { host: "127.0.0.1" }
      : {
          proxy: {
            "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
            "/ws": { target: "ws://127.0.0.1:8000", ws: true },
          },
        },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      exclude: ["e2e/**", "showcase/e2e/**", "node_modules/**"],
    },
    build: {
      outDir: file(showcase ? "./dist-showcase" : "./dist"),
      emptyOutDir: true,
      modulePreload: { polyfill: !showcase },
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("recharts")) return "charts";
            if (id.includes("@xyflow/react")) return "graph";
          },
        },
      },
    },
  };
});
