import { expect, test } from "@playwright/test";

test("free local AI explains existing evidence without changing monitored systems", async ({ page }) => {
  test.skip(process.env.SENTINELX_E2E_LOCAL_AI !== "1", "Opt in with SENTINELX_E2E_LOCAL_AI=1; requires a downloaded local model.");
  const password = process.env.SENTINELX_E2E_PASSWORD;
  test.skip(!password, "Set SENTINELX_E2E_PASSWORD to an authorized administrator password.");
  test.setTimeout(240000);
  const errors: string[] = [];
  const unexpectedWrites: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET" && path.startsWith("/api/v1/") &&
        !path.startsWith("/api/v1/auth/") && path !== "/api/v1/ai/analyze-incident") {
      unexpectedWrites.push(path);
    }
  });

  await page.goto("/login");
  await page.getByLabel("Email address").fill(process.env.SENTINELX_E2E_EMAIL ?? "admin@sentinelx.dev");
  await page.getByLabel("Password", { exact: true }).fill(password!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your security overview" })).toBeVisible();

  const incidentsResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/v1/incidents" && response.status() === 200);
  await page.goto("/ai-assistant");
  await expect(page.getByText("Local AI configured", { exact: true })).toBeVisible();
  await expect(page.getByText(/no cloud AI receives them/)).toBeVisible();
  const incidents = (await (await incidentsResponse).json()).items;
  test.skip(!incidents.length, "No existing investigations; this test does not insert simulated records.");
  await page.getByLabel("Investigation", { exact: true }).selectOption(String(incidents[0].id));
  const responsePromise = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/v1/ai/analyze-incident", { timeout: 200000 });
  const started = Date.now();
  await page.getByRole("button", { name: "Explain", exact: true }).click();
  await expect(page.getByRole("button", { name: "Explain", exact: true })).toBeDisabled();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const analysis = await response.json();
  expect(analysis.mode).toBe("llm");
  expect(analysis.provider).toBe("ollama");
  expect(analysis.evidence.length).toBeGreaterThan(0);
  expect(analysis.evidence.every((item: string) => /EVT-\d+/.test(item))).toBe(true);
  await expect(page.getByText(`Local AI analysis · ${analysis.model}`, { exact: true })).toBeVisible();
  await expect(page.getByText(/No actions were executed/)).toBeVisible();
  console.log(`Local AI explanation verified in ${Math.round((Date.now() - started) / 1000)}s.`);

  for (const width of [390, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  }
  await page.goto("/settings");
  await expect(page.getByRole("definition").filter({ hasText: "Local AI configured" })).toBeVisible();
  expect(unexpectedWrites).toEqual([]);
  expect(errors).toEqual([]);
});
