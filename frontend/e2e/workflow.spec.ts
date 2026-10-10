import { expect, test } from "@playwright/test";

const email = process.env.SENTINELX_E2E_EMAIL ?? "admin@sentinelx.dev";
const password = process.env.SENTINELX_E2E_PASSWORD;
test.skip(
  !password,
  "Set SENTINELX_E2E_PASSWORD to a development administrator password.",
);

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password!);
  const systemResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/system" &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const system = await (await systemResponse).json();
  test.skip(
    !system.demo_mode,
    "Investigation fixtures require demo mode; real monitoring is left untouched.",
  );
  await expect(
    page.getByRole("heading", { name: "Your security overview" }),
  ).toBeVisible();
});

test("login, live dashboard, simulation, investigation, analysis, and resolution", async ({
  page,
}) => {
  await expect(
    page.getByText("Live updates", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Activity over time", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".overview-alerts .review-list-row").first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator('[data-counting="true"]')).toHaveCount(0);
  await page.screenshot({
    path: "../docs/screenshots/dashboard.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "Try a practice example" }).click();
  await expect(page).toHaveURL(/\/incidents\/\d+/);
  await expect(
    page.getByRole("heading", {
      name: "Possible account compromise on linux-lab-01",
    }),
  ).toBeVisible();
  await expect(
    page.getByText("14 linked activity records, in chronological order."),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "12 unsuccessful sign-in attempts" }),
  ).toBeVisible();
  await page.getByText("View 12 original records", { exact: true }).click();
  await expect(page.locator(".grouped-evidence li")).toHaveCount(12);
  await page.getByText("View 12 original records", { exact: true }).click();
  await page.getByText("Address reputation checks", { exact: true }).click();
  await page.getByRole("button", { name: "Check addresses", exact: true }).click();
  await expect(
    page.getByText("local-context · No reputation score"),
  ).toBeVisible();
  await page
    .getByLabel("Add to the investigation")
    .fill(
      "Verified as an isolated lab simulation. No real asset was targeted.",
    );
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(
    page.getByText(
      "Verified as an isolated lab simulation. No real asset was targeted.",
    ),
  ).toBeVisible();
  const notifications = page.getByRole("button", {
    name: "Dismiss notification",
    exact: true,
  });
  while (await notifications.count()) {
    await notifications.first().click();
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../docs/screenshots/incident.png",
    fullPage: true,
    animations: "disabled",
  });
  await page
    .getByRole("button", { name: "Explain this investigation", exact: true })
    .click();
  await expect(
    page.getByText("Offline review · no online AI", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Protective steps to consider" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/analysis.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("tab", { name: "Connections" }).click();
  await expect(page.locator(".react-flow")).toBeVisible();
  await page
    .getByRole("button", { name: "Close investigation", exact: true })
    .click();
  await page.getByRole("button", { name: "Confirm closure" }).click();
  await expect(
    page
      .locator(".incident-summary-bar")
      .getByText("Closed", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome to SentinelX" }),
  ).toBeVisible();
});

test("alert acknowledgment and server-backed rule edits", async ({ page }) => {
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await page
    .locator("tbody tr")
    .first()
    .getByRole("button", { name: /View ALT-/ })
    .click();
  const drawer = page.getByRole("dialog");
  const status = drawer.getByRole("combobox", {
    name: "Alert status",
    exact: true,
  });
  const previousStatus = await status.inputValue();
  await drawer
    .getByRole("combobox", { name: "Alert status", exact: true })
    .selectOption("acknowledged");
  await expect(
    drawer.getByText("Seen", { exact: true }).first(),
  ).toBeVisible();
  await status.selectOption(previousStatus);
  await expect(status).toHaveValue(previousStatus);
  await drawer.getByRole("button", { name: "Close dialog" }).click();
  await page.getByText("Advanced tools", { exact: true }).click();
  await page
    .getByRole("link", { name: "Alert rules", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Edit SSH brute force", exact: true })
    .click();
  await page.getByLabel("Event threshold").fill("11");
  await page.getByRole("button", { name: "Save rule", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.locator("tr").filter({ hasText: "SSH brute force" }),
  ).toContainText("≥ 11");
  // Restore the configured starter threshold; this test must not alter subsequent demo semantics.
  await page
    .getByRole("button", { name: "Edit SSH brute force", exact: true })
    .click();
  await page.getByLabel("Event threshold").fill("10");
  await page.getByRole("button", { name: "Save rule", exact: true }).click();
  await expect(
    page.locator("tr").filter({ hasText: "SSH brute force" }),
  ).toContainText("≥ 10");
});

test("event filters, event details, refresh session, and mobile navigation", async ({
  page,
}) => {
  await page.getByRole("link", { name: "Activity", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Search activity", exact: true })
    .fill("source_ip:203.0.113.42");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await expect(page.locator("tbody")).toContainText("203.0.113.42");
  await page
    .locator("tbody tr")
    .first()
    .getByRole("button", { name: /View EVT-/ })
    .click();
  await page.getByText("Technical record (JSON)", { exact: true }).click();
  await expect(page.locator(".json-block")).toBeVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("combobox", { name: "Time range" }).selectOption("all");
  await expect(
    page.getByRole("heading", { name: "Activity", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Activity", exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your security overview" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Activity over time", exact: true }),
  ).toBeVisible();
  await expect(page.locator('[data-counting="true"]')).toHaveCount(0);
  await page.screenshot({
    path: "../docs/screenshots/mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  const overflows = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflows).toBe(false);
});
