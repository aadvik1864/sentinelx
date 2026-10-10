import { expect, test } from "@playwright/test";

test("connection setup is clear and responsive without changing real sources", async ({ page }) => {
  const password = process.env.SENTINELX_E2E_PASSWORD;
  test.skip(!password, "Set SENTINELX_E2E_PASSWORD to an authorized administrator password.");
  const errors: string[] = [];
  const writes: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.method() !== "GET" && new URL(request.url()).pathname.startsWith("/api/v1/sources")) {
      writes.push(request.url());
    }
  });
  await page.goto("/login");
  await page.getByLabel("Email address").fill(process.env.SENTINELX_E2E_EMAIL ?? "admin@sentinelx.dev");
  await page.getByLabel("Password", { exact: true }).fill(password!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your security overview" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Connected systems", exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: "../docs/screenshots/overview-live.png", fullPage: true, animations: "disabled" });
  const sourceResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/sources" && response.status() === 200);
  await page.getByRole("link", { name: "Connected systems", exact: true }).click();
  const sources = (await (await sourceResponse).json()).items;
  await expect(page.getByRole("heading", { name: "Connected systems", exact: true })).toBeVisible();
  await page.getByText("How does connecting a system work?", { exact: true }).click();
  await expect(page.getByText(/A website address alone is not enough/)).toBeVisible();
  await page.getByText("How does connecting a system work?", { exact: true }).click();
  await page.screenshot({ path: "../docs/screenshots/sources.png", fullPage: true, animations: "disabled" });

  await page.getByRole("button", { name: "Connect a system" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("radio", { name: /Website/ }).check();
  await dialog.getByLabel("Name for this system").fill("My website");
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(dialog.getByLabel("Activity file location", { exact: true })).toHaveValue("/var/log/nginx/access.log");
  await expect(dialog.getByText(/Use the access log for this particular website/)).toBeVisible();
  await dialog.getByRole("button", { name: "Back", exact: true }).click();
  await dialog.getByRole("radio", { name: /Web app/ }).check();
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(dialog.getByLabel("Activity file location", { exact: true })).toHaveValue("/var/log/myapp/security.jsonl");
  await page.keyboard.press("Escape");

  if (sources.length) {
    await page.getByText("Connection details and settings", { exact: true }).first().click();
    await page.getByRole("button", { name: "Setup instructions" }).first().click();
    await expect(dialog.getByRole("button", { name: "Download connection settings" })).toHaveCount(0);
    const download = page.waitForEvent("download");
    await dialog.getByRole("button", { name: "Download helper" }).click();
    expect((await download).suggestedFilename()).toBe("sentinelx-agent.py");
    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(dialog.getByRole("heading", { name: "Start the helper on the server" })).toBeVisible();
    await dialog.getByText("The monitored system is on another computer", { exact: true }).click();
    await expect(dialog.getByText(/ssh -N -L/)).toBeVisible();
    await expect(dialog.getByText(/Never send private settings/)).toBeVisible();
    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(dialog.getByRole("heading", { name: "Check that the connection responds" })).toBeVisible();
    await dialog.getByRole("button", { name: "Return to systems" }).click();
    await page.getByText("Connection details and settings", { exact: true }).first().click();
  }

  for (const width of [320, 390, 760, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    if (width === 390) {
      await page.screenshot({ path: "../docs/screenshots/sources-mobile.png", fullPage: true, animations: "disabled" });
    }
    await page.getByRole("button", { name: "Connect a system" }).first().click();
    await dialog.getByLabel("Name for this system").fill("My server");
    await expect(dialog.getByRole("button", { name: "Step 3: Review" })).toBeDisabled();
    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(dialog.getByLabel("Computer name", { exact: true })).toBeVisible();
    await expect(page.locator(".setup-step-content")).toBeFocused();
    await dialog.getByLabel("Computer name", { exact: true }).fill("my-server");
    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(dialog.getByRole("heading", { name: "Check your connection details" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    if (width === 390) {
      await dialog.screenshot({ path: "../docs/screenshots/connect-system-mobile.png", animations: "disabled" });
    }
    // Leave before Save connection: this test never creates or alters a real source.
    await page.keyboard.press("Escape");
  }
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
});
