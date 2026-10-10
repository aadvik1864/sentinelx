import { expect, test } from "@playwright/test";
import type { Page, Route } from "@playwright/test";

// Browser-only fixtures: no credentials, simulations, or writes reach the live backend.
const timestamp = "2026-10-09T10:00:00Z";
const event = {
  id: 1, reference: "EVT-00001", timestamp, source: "linux",
  event_type: "authentication_failure", severity: "medium",
  source_ip: "203.0.113.42", destination_ip: null, hostname: "test-server",
  username: "alice", message: "Sign-in rejected", metadata: {},
};
const alert = {
  id: 1, reference: "ALT-00001", title: "Repeated sign-in attempts",
  description: "Several attempts need checking.", severity: "high", status: "open",
  source_ip: event.source_ip, hostname: event.hostname, event_count: 1,
  detected_at: timestamp, created_at: timestamp, incident_id: 1,
  mitre_techniques: ["T1110"], event, rule: { name: "Repeated sign-ins" },
};
const investigation = {
  id: 1, reference: "INC-00001", title: "Review sign-ins on test-server",
  description: "Browser-only interface fixture, not a real incident.", severity: "high",
  status: "open", hostname: event.hostname, source_ip: event.source_ip,
  assigned_to: null, assigned_name: null, created_at: timestamp, updated_at: timestamp,
  resolved_at: null, mitre_techniques: ["T1110"], events: [event], event_total: 1,
  evidence_truncated: false, alerts: [alert], notes: [], iocs: [],
};
const analysis = {
  mode: "offline", model: null, confidence: "low", summary: "One rejected sign-in.",
  likely_attack: "There is not enough information to confirm an attack.",
  evidence: ["EVT-00001: one unsuccessful sign-in"], affected_assets: ["test-server"],
  mitre_techniques: ["T1110"], recommended_investigation: ["Ask whether Alice tried to sign in."],
  recommended_containment: ["Ask an authorized administrator before restricting access."],
  false_positive_indicators: ["A mistyped password could explain this."],
  notice: "No actions were executed.",
};

async function mockWorkspace(page: Page, extra?: (route: Route, path: string) => Promise<boolean>) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.routeWebSocket(/\/ws\/(events|alerts|incidents)$/, (socket) => {
    socket.onMessage(() => socket.send(JSON.stringify({ type: "connected" })));
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    if (extra && await extra(route, path)) return;
    let json: unknown;
    switch (path) {
      case "/auth/refresh":
        json = { access_token: "browser-fixture-only", user: {
          id: 1, name: "Interface tester", email: "tester@example.test", role: "ADMIN",
        } }; break;
      case "/system":
        json = { version: "test", environment: "browser-fixture", demo_mode: true,
          live_monitoring: false, ai_provider: "offline", threat_intel_provider: "unconfigured" }; break;
      case "/dashboard":
        json = { total_events: 1, active_alerts: 1, critical_alerts: 0, open_incidents: 1,
          monitored_assets: 1, unique_source_ips: 1, events_per_second: 0,
          severity_counts: { critical: 0, high: 1, medium: 0, low: 0 },
          activity: [{ timestamp, events: 1 }], top_ips: [] }; break;
      case "/events": json = { items: [event], total: 1 }; break;
      case "/alerts": json = { items: [alert], total: 1 }; break;
      case "/alerts/1": json = alert; break;
      case "/incidents": json = { items: [investigation], total: 1 }; break;
      case "/incidents/1": json = investigation; break;
      case "/ai/analyze-incident": case "/ai/explain-alert": json = analysis; break;
      case "/sources": case "/users/assignees": case "/assets":
      case "/rules": case "/users": case "/audit-logs": json = { items: [], total: 0 }; break;
      default:
        await route.fulfill({ status: 500, json: { detail: `Unmocked interface request: ${path}` } });
        return;
    }
    await route.fulfill({ json });
  });
  return errors;
}

test("the overview and advanced tools stay usable on small screens", async ({ page }) => {
  const errors = await mockWorkspace(page);
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "1 alert needs a review" })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: "../docs/screenshots/overview-practice.png", fullPage: true, animations: "disabled" });
  await expect(page.getByRole("link", { name: "Alert rules", exact: true })).not.toBeVisible();
  await page.getByText("Advanced tools", { exact: true }).click();
  await expect(page.getByRole("link", { name: "Alert rules", exact: true })).toBeVisible();
  await page.getByText("Advanced tools", { exact: true }).click();
  for (const width of [320, 390, 760, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    if (width === 390) {
      await page.screenshot({ path: "../docs/screenshots/overview-mobile.png", fullPage: true, animations: "disabled" });
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "How to use SentinelX" }).click();
  await expect(page.getByRole("dialog", { name: "A simple guide to SentinelX" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.goto("/events");
  await page.getByRole("button", { name: "View EVT-00001" }).click();
  await expect(page.locator(".json-block")).not.toBeVisible();
  await page.getByText("Technical record (JSON)", { exact: true }).click();
  await expect(page.locator(".json-block")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  expect(errors).toEqual([]);
});

test("private setup downloads and connection checks work with a browser-only source", async ({ page }) => {
  const source = {
    id: 7, name: "Test connection", kind: "nginx", hostname: "test-server",
    log_path: "/var/log/nginx/access.log", enabled: true, status: "not_connected",
    last_heartbeat_at: null as string | null, last_event_at: null,
    last_event_timestamp: null, last_error: "", total_events: 0,
  };
  let created = false;
  const errors = await mockWorkspace(page, async (route, path) => {
    if (path !== "/sources") return false;
    if (route.request().method() === "POST") {
      Object.assign(source, route.request().postDataJSON());
      created = true;
      await route.fulfill({ status: 201, json: { source, collector_key: "browser-fixture-key-only" } });
    } else {
      await route.fulfill({ json: { items: created ? [source] : [] } });
    }
    return true;
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/sources");
  await page.getByRole("button", { name: "Connect a system" }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.locator(".rb-stepper")).toHaveAttribute("data-motion", "static");
  await dialog.getByRole("radio", { name: /Website/ }).check();
  await dialog.getByLabel("Name for this system").fill("Test connection");
  await dialog.getByRole("button", { name: "Continue" }).click();
  await dialog.getByLabel("Computer name", { exact: true }).fill("test-server");
  await dialog.getByRole("button", { name: "Continue" }).click();
  await dialog.getByRole("button", { name: "Save connection" }).click();
  await expect(dialog.getByRole("button", { name: "Continue" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog.getByRole("heading", { name: "Have you saved the private settings?" })).toBeVisible();
  await expect(dialog.locator(".source-close-warning")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Go back and save settings" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Close dialog" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Close without saving" })).toBeFocused();
  await dialog.getByRole("button", { name: "Go back and save settings" }).click();
  const download = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "Download connection settings" }).click();
  expect((await download).suggestedFilename()).toBe("sentinelx-source.json");
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(dialog.getByRole("heading", { name: "Start the helper on the server" })).toBeVisible();
  await dialog.getByRole("button", { name: "Continue" }).click();
  source.status = "waiting";
  source.last_heartbeat_at = timestamp;
  await dialog.getByRole("button", { name: "Check connection" }).click();
  await expect(dialog.getByText("Connected", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Return to systems" }).click();
  await expect(dialog).not.toBeVisible();
  expect(errors).toEqual([]);
});

test("investigations and assistant explanations use the same plain-language labels", async ({ page }) => {
  const errors = await mockWorkspace(page);
  await page.goto("/incidents/1");
  await expect(page.getByRole("heading", { name: "What happened, in order" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Successful sign-in", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Unsuccessful sign-in" })).toBeVisible();
  await expect(page.getByRole("link", { name: /T1110/ })).not.toBeVisible();
  await page.getByRole("button", { name: "Explain this investigation", exact: true }).click();
  await expect(page.getByText("Offline review · no online AI", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What to check next" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Protective steps to consider" })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: "../docs/screenshots/plain-language-investigation.png", fullPage: true, animations: "disabled" });
  await page.setViewportSize({ width: 390, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await page.getByRole("button", { name: "Close investigation" }).click();
  await expect(page.getByRole("dialog")).toContainText("It does not fix the underlying issue");
  await page.keyboard.press("Escape");
  await page.goto("/alerts?selected=1");
  await expect(page.getByRole("dialog").getByText("Important", { exact: true })).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Explain this alert" }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "What happened", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("local AI labels and privacy guidance remain readable on small screens", async ({ page }) => {
  const model = "qwen3:4b-instruct-2507-q4_K_M";
  const errors = await mockWorkspace(page, async (route, path) => {
    if (path === "/system") {
      await route.fulfill({ json: {
        version: "test", environment: "browser-fixture", demo_mode: true,
        live_monitoring: false, ai_provider: "ollama", ai_model: model,
        threat_intel_provider: "unconfigured",
      } });
      return true;
    }
    if (path === "/ai/analyze-incident") {
      await route.fulfill({ json: {
        ...analysis, mode: "llm", provider: "ollama", model,
        notice: "Browser-only practice fixture; no real AI was called. No actions were executed.",
      } });
      return true;
    }
    return false;
  });
  await page.goto("/ai-assistant");
  await expect(page.getByText("Local AI configured", { exact: true })).toBeVisible();
  await expect(page.getByText(/no cloud AI receives them/)).toBeVisible();
  await page.getByLabel("Investigation", { exact: true }).selectOption("1");
  await page.getByRole("button", { name: "Explain", exact: true }).click();
  await expect(page.getByText(`Local AI analysis · ${model}`, { exact: true })).toBeVisible();
  await expect(page.getByText(/Browser-only practice fixture/)).toBeVisible();
  for (const width of [320, 390, 760, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  }
  await page.goto("/settings");
  await expect(page.getByRole("definition").filter({ hasText: "Local AI configured" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("administrator admission explains shared access and works on small screens", async ({ page }) => {
  let created: Record<string, unknown> | null = null;
  const errors = await mockWorkspace(page, async (route, path) => {
    if (path !== "/users") return false;
    if (route.request().method() === "POST") {
      created = route.request().postDataJSON();
      await route.fulfill({ status: 201, json: { id: 2, role: "VIEWER" } });
    } else {
      await route.fulfill({ json: { items: [] } });
    }
    return true;
  });
  await page.goto("/settings");
  const add = page.getByRole("button", { name: "Add a person" });
  await add.click();
  const dialog = page.getByRole("dialog", { name: "Add a person" });
  await expect(dialog).toContainText("not a private personal workspace");
  const submit = dialog.getByRole("button", { name: "Create read-only account" });
  await expect(submit).toBeDisabled();
  for (const width of [320, 390, 760, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(add).toBeFocused();
  await add.click();
  await dialog.getByLabel("Full name").fill("Browser-only teammate");
  await dialog.getByLabel("Email address").fill("teammate@example.test");
  await dialog.getByLabel("Starter password").fill("Browser-only-password-123!");
  await dialog.getByRole("checkbox").check();
  await submit.click();
  await expect(dialog).not.toBeVisible();
  expect(created).toEqual({
    name: "Browser-only teammate", email: "teammate@example.test", password: "Browser-only-password-123!",
  });
  expect(errors).toEqual([]);
});

test("chart windows and quick navigation support keyboard exploration", async ({ page }) => {
  const errors = await mockWorkspace(page, async (route, path) => {
    if (path !== "/dashboard") return false;
    await route.fulfill({ json: {
      total_events: 300, active_alerts: 1, critical_alerts: 0, open_incidents: 1,
      monitored_assets: 0, unique_source_ips: 0, events_per_second: 0,
      severity_counts: { critical: 0, high: 1, medium: 0, low: 0 }, top_ips: [],
      activity: Array.from({ length: 24 }, (_, hour) => ({
        timestamp: new Date(Date.UTC(2026, 9, 10, hour)).toISOString(), events: hour + 1,
      })),
    } });
    return true;
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/dashboard");
  await expect(page.locator(".chart-summary")).toContainText("300 records");
  await page.getByRole("radio", { name: "6 hours" }).check();
  await expect(page.locator(".chart-summary")).toContainText("129 records");
  await page.getByRole("radio", { name: "6 hours" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "12 hours" })).toBeChecked();
  await expect(page.locator(".chart-summary")).toContainText("222 records");
  await expect(page.getByRole("link", { name: "View alerts to review" })).toHaveAttribute("href", "/alerts");
  for (const width of [320, 390, 760, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  }
  await page.getByRole("button", { name: "Go to a page" }).click();
  const dialog = page.getByRole("dialog", { name: "Go to a page" });
  await expect(dialog.getByLabel("Find a page")).toBeFocused();
  await dialog.getByLabel("Find a page").fill("Settings");
  await page.keyboard.press("ArrowDown");
  await expect(dialog.getByRole("button", { name: "Settings" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/settings$/);
  await page.keyboard.press("Control+k");
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  const trigger = page.getByRole("button", { name: "Go to a page" });
  await trigger.click();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Close dialog" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Settings" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Close dialog" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  expect(errors).toEqual([]);
});

test("connection filters are read-only and keep their state in the URL", async ({ page }) => {
  const errors = await mockWorkspace(page, async (route, path) => {
    if (path !== "/sources") return false;
    expect(route.request().method()).toBe("GET");
    await route.fulfill({ json: { items: [
      { id: 1, name: "Practice Linux", kind: "linux", hostname: "practice-linux", enabled: true, status: "receiving", last_error: "", total_events: 10 },
      { id: 2, name: "Practice website", kind: "nginx", hostname: "practice-web", enabled: true, status: "offline", last_error: "", total_events: 5 },
    ] } });
    return true;
  });
  await page.goto("/sources?filter=attention");
  await expect(page.getByRole("radio", { name: "Needs attention" })).toBeChecked();
  await expect(page.getByRole("heading", { name: "Practice website" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Practice Linux" })).toHaveCount(0);
  // URL updates commit through the router's transition, not synchronously with the click.
  await page.getByRole("radio", { name: "All systems" }).click();
  await expect(page.getByRole("radio", { name: "All systems" })).toBeChecked();
  await page.getByLabel("Find a system").pressSequentially("practice-linux");
  await expect(page).toHaveURL(/q=practice-linux/);
  await expect(page.getByLabel("Find a system")).toHaveValue("practice-linux");
  await expect(page.getByRole("heading", { name: "Practice Linux" })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Find a system")).toHaveValue("practice-linux");
  await expect(page.getByRole("heading", { name: "Practice Linux" })).toBeVisible();
  await page.getByRole("radio", { name: "Paused" }).click();
  await expect(page.getByRole("radio", { name: "Paused" })).toBeChecked();
  await expect(page.getByRole("heading", { name: "No systems match these filters" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByRole("status")).toHaveText("Showing 2 of 2 systems");
  for (const width of [320, 390, 760, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  }
  expect(errors).toEqual([]);
});

test("activity filters are distinct from the header's navigation search", async ({ page }) => {
  const errors = await mockWorkspace(page);
  await page.goto("/events");
  await expect(page.getByRole("textbox", { name: "Search activity", exact: true })).toHaveCount(2);
  const search = page.getByRole("main").getByRole("textbox", { name: "Search activity", exact: true });
  const filtered = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === "/api/v1/events" && url.searchParams.get("q") === "source_ip:203.0.113.42";
  });
  await search.fill("source_ip:203.0.113.42");
  await filtered;
  await expect(search).toHaveValue("source_ip:203.0.113.42");
  await expect(page.getByRole("banner").getByRole("textbox", { name: "Search activity", exact: true })).toHaveValue("");
  await expect(page.locator("tbody")).toContainText("203.0.113.42");
  expect(errors).toEqual([]);
});
