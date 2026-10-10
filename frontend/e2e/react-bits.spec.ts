import { expect, test } from "@playwright/test";
import type { DashboardMetrics } from "../src/types";

test("React Bits sign-in supports motion controls and mobile layouts", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute("content", "#24272d");
  await expect(page.locator(".login-story")).toHaveCSS("background-color", "rgb(36, 39, 45)");
  await expect(page.locator(".login-form-wrap")).toHaveCSS("background-color", "rgb(43, 48, 56)");
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toHaveCSS("background-color", "rgb(227, 164, 120)");
  await expect(page.locator('.shape-grid[data-rendered="true"]')).toBeVisible();
  await expect(page.getByRole("img", { name: /Computer, website, and app activity/ })).toBeVisible();
  await page.getByRole("button", { name: "Pause background animation", exact: true }).click();
  await expect(page.locator(".shape-grid")).toHaveAttribute("data-motion", "static");
  await expect(page.getByRole("button", { name: "Resume background animation", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: "../docs/screenshots/login.png", fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "Resume background animation", exact: true }).click();
  await expect(page.locator(".shape-grid")).toHaveAttribute("data-motion", "animated");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Pause background animation", exact: true }).click();
  await expect(page.getByLabel("Email address")).toBeVisible();
  await page.screenshot({ path: "../docs/screenshots/login-mobile.png", fullPage: true, animations: "disabled" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
});

test("reduced motion keeps metrics accurate and spotlight cards usable", async ({ page }) => {
  const password = process.env.SENTINELX_E2E_PASSWORD;
  test.skip(!password, "Set SENTINELX_E2E_PASSWORD to a development administrator password.");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Background motion disabled by your preference" })).toBeDisabled();
  await expect(page.locator(".shape-grid")).toHaveAttribute("data-motion", "static");
  await page.getByLabel("Email address").fill(process.env.SENTINELX_E2E_EMAIL ?? "admin@sentinelx.dev");
  await page.getByLabel("Password", { exact: true }).fill(password!);
  // Freeze one real snapshot for this rendering assertion. Collection keeps running.
  // Otherwise login activity or a heartbeat can change totals before the assertion.
  let snapshot: Promise<DashboardMetrics> | null = null;
  await page.route("**/api/v1/dashboard", async (route) => {
    snapshot ??= route.fetch().then((response) => response.json());
    await route.fulfill({ json: await snapshot });
  });
  const response = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/v1/dashboard" && response.status() === 200,
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const data = await (await response).json() as DashboardMetrics;
  await expect(page.locator(".metric")).toHaveCount(3);
  await expect(page.locator('[data-counting="true"]')).toHaveCount(0);
  const expected = await page.evaluate((values) =>
    values.map((value) => new Intl.NumberFormat().format(value)),
    [data.total_events, data.active_alerts, data.open_incidents],
  );
  const metrics = page.locator(".metric .count-up");
  for (const [index, metric] of (await metrics.all()).entries()) {
    await expect(metric.locator(".sr-only")).toHaveText(expected[index]);
    await expect(metric.locator('[aria-hidden="true"]')).toHaveText(expected[index]);
  }
  const first = page.locator(".overview-review");
  await first.hover();
  await expect.poll(() => first.evaluate((element) => getComputedStyle(element, "::before").opacity)).toBe("1");
  await expect(first).not.toHaveAttribute("tabindex");
});
