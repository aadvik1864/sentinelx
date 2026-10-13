import { defineConfig } from "@playwright/test";
import { fileURLToPath } from "node:url";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  retries: 0,
  timeout: 45000,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4174/sentinelx/",
    viewport: { width: 1440, height: 1000 },
    trace: "off",
    video: "off",
    screenshot: "off",
  },
  webServer: {
    command:
      "npm run preview:showcase -- --port 4174 --strictPort --base /sentinelx/",
    cwd: fileURLToPath(new URL("..", import.meta.url)),
    url: "http://127.0.0.1:4174/sentinelx/",
    reuseExistingServer: false,
  },
});
