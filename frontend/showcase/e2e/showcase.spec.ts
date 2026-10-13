import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import type { SecurityEvent } from "../../src/types";

async function guardNetwork(page: Page) {
  const unexpected: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.exposeFunction(
    "reportPolicyViolation",
    (directive: string, uri: string) => {
      unexpected.push(`${directive}: ${uri}`);
    },
  );
  await page.addInitScript(() => {
    const report = (
      window as unknown as {
        reportPolicyViolation: (
          directive: string,
          uri: string,
        ) => Promise<void>;
      }
    ).reportPolicyViolation;
    document.addEventListener("securitypolicyviolation", (event) => {
      void report(event.effectiveDirective, event.blockedURI);
    });
  });
  page.on("websocket", (socket) => unexpected.push(socket.url()));
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (
      ["xhr", "fetch", "eventsource"].includes(request.resourceType()) ||
      url.origin !== "http://127.0.0.1:4174" ||
      /\/(api|ws)(\/|$)/.test(url.pathname)
    ) {
      unexpected.push(request.url());
      await route.abort();
    } else {
      await route.continue();
    }
  });
  return { unexpected, errors };
}

test("the public workflow is interactive without any backend or external requests", async ({
  page,
}) => {
  const guard = await guardNetwork(page);
  await page.goto("./#/dashboard");
  await expect(
    page.getByText("Demo — synthetic data", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "3 alerts need a review" }),
  ).toBeVisible();
  await page.getByRole("radio", { name: "6 hours" }).check();
  await expect(page.locator(".chart-summary")).toContainText(
    "last 6 hourly buckets",
  );
  await page.getByRole("link", { name: "Activity", exact: true }).click();
  await page.getByLabel("Search activity").fill("source_ip:203.0.113.42");
  await expect(page.locator("tbody tr")).toHaveCount(14);
  await expect(
    page.getByText("Advanced: import a record manually"),
  ).toHaveCount(0);
  await page.goto("./#/incidents/1");
  await expect(
    page.getByRole("heading", { name: "What happened, in order" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Connections", exact: true }).click();
  await expect(page.locator(".react-flow")).toBeVisible();
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await page
    .getByLabel("Add to the investigation")
    .fill("Browser-only practice note");
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(
    page.getByText("Browser-only practice note", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Explain this investigation", exact: true })
    .click();
  await expect(page.getByText(/Browser-only sample summary/)).toBeVisible();
  await page
    .getByRole("button", { name: "Close investigation", exact: true })
    .click();
  await page.getByRole("button", { name: "Confirm closure" }).click();
  await expect(
    page.getByLabel("Investigation status", { exact: true }),
  ).toHaveValue("resolved");
  await page.reload();
  await expect(
    page.getByLabel("Investigation status", { exact: true }),
  ).toHaveValue("open");
  await expect(
    page.getByText("Browser-only practice note", { exact: true }),
  ).toHaveCount(0);
  expect(guard.unexpected).toEqual([]);
  expect(guard.errors).toEqual([]);
  const policy = await page
    .locator('meta[http-equiv="Content-Security-Policy"]')
    .getAttribute("content");
  expect(policy).toContain("connect-src 'none'");
});

test("visitors have independent practice state and no account management", async ({
  browser,
  baseURL,
}) => {
  const first = await browser.newContext({ baseURL });
  const second = await browser.newContext({ baseURL });
  try {
    const one = await first.newPage();
    const two = await second.newPage();
    const guards = [await guardNetwork(one), await guardNetwork(two)];
    await one.goto("./#/alerts?selected=1");
    const firstStatus = one
      .getByRole("dialog")
      .getByLabel("Alert status", { exact: true });
    await firstStatus.selectOption("acknowledged");
    await expect(firstStatus).toHaveValue("acknowledged");
    await two.goto("./#/alerts?selected=1");
    await expect(
      two.getByRole("dialog").getByLabel("Alert status", { exact: true }),
    ).toHaveValue("open");
    await two.goto("./#/settings");
    await expect(
      two.getByRole("heading", { name: "Not part of the public demo" }),
    ).toBeVisible();
    await expect(two.getByRole("textbox")).toHaveCount(0);
    await one
      .getByRole("dialog")
      .getByRole("button", { name: "Close dialog" })
      .click();
    await one.getByRole("button", { name: "Reset demo" }).click();
    await expect(one).toHaveURL(/#\/dashboard$/);
    await expect(
      one.getByRole("heading", { name: "3 alerts need a review" }),
    ).toBeVisible();
    await one.goto("./#/alerts?selected=1");
    await expect(
      one.getByRole("dialog").getByLabel("Alert status", { exact: true }),
    ).toHaveValue("open");
    expect(await first.cookies()).toEqual([]);
    expect(
      await one.evaluate(() => [localStorage.length, sessionStorage.length]),
    ).toEqual([0, 0]);
    for (const guard of guards) {
      expect(guard.unexpected).toEqual([]);
      expect(guard.errors).toEqual([]);
    }
  } finally {
    await first.close();
    await second.close();
  }
});

test("mobile navigation, direct links and keyboard exploration work", async ({
  page,
}) => {
  const guard = await guardNetwork(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("./#/dashboard");
  for (const width of [320, 390, 760, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      )
      .toBe(false);
    await expect(
      page.getByText("Demo — synthetic data", { exact: true }),
    ).toBeVisible();
  }
  await page.setViewportSize({ width: 390, height: 900 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("link", { name: "Connected systems", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Connected systems", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Show systems needing attention" })
    .click();
  await expect(page.locator(".system-row")).toHaveCount(1);
  await page.reload();
  await expect(page.locator(".system-row")).toHaveCount(1);
  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "Go to a page" });
  await expect(dialog.getByLabel("Find a page")).toBeFocused();
  await dialog.getByLabel("Find a page").fill("Assistant");
  await page.keyboard.press("Enter");
  await page.getByLabel("Investigation", { exact: true }).selectOption("1");
  await page.getByRole("button", { name: "Explain", exact: true }).click();
  await expect(page.getByText(/Browser-only sample summary/)).toBeVisible();
  expect(guard.unexpected).toEqual([]);
  expect(guard.errors).toEqual([]);
});

test("practice investigations and downloads contain only example evidence", async ({
  page,
}) => {
  const guard = await guardNetwork(page);
  await page.goto("./#/events?source_id=3");
  await expect(page.locator("tbody tr")).toHaveCount(3);
  const downloadReady = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download these records" }).click();
  const download = await downloadReady;
  const records = JSON.parse(
    await readFile((await download.path())!, "utf8"),
  ) as SecurityEvent[];
  expect(records).toHaveLength(3);
  expect(
    records.every(
      (event) =>
        event.metadata.simulated && event.hostname.endsWith(".example.test"),
    ),
  ).toBe(true);

  await page.goto("./#/incidents");
  await page
    .getByRole("button", { name: "Create investigation", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Create an investigation" });
  await dialog
    .getByLabel("Investigation title")
    .fill("Practice checkout review");
  await dialog.getByLabel("Description").fill("Fictional service evidence");
  await dialog
    .getByLabel("Link activity record IDs (optional)")
    .fill(records[0].reference);
  await dialog
    .getByRole("button", { name: "Create investigation", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole("link", { name: "Open INC-00003" }).click();
  await expect(
    page.getByRole("heading", { name: "Practice checkout review" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "App error", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText(
      "That example record does not exist. Choose one from the list.",
    ),
  ).toBeVisible();
  expect(guard.unexpected).toEqual([]);
  expect(guard.errors).toEqual([]);
});
