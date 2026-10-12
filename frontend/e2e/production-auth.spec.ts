import { expect, test } from "@playwright/test";

// This test admits/mutates only disposable fixtures, never the existing installation.
test.skip(
  process.env.SENTINELX_RELEASE_E2E !== "true" ||
  process.env.SENTINELX_E2E_URL !== "https://localhost:18443" ||
  !process.env.SENTINELX_E2E_PASSWORD || !process.env.SENTINELX_E2E_OTP,
  "Requires the isolated production release fixture and private test credentials.",
);

test("production sign-in and first-login security gates", async ({ page, browser }) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@sentinelx.dev");
  await page.getByLabel("Password", { exact: true }).fill(process.env.SENTINELX_E2E_PASSWORD!);
  await page.getByLabel("Authenticator or recovery code").fill(process.env.SENTINELX_E2E_OTP!);
  const signedIn = page.waitForResponse((response) => response.url().endsWith("/api/v1/auth/login") && response.status() === 200);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const session = await (await signedIn).json();
  if (process.env.GITHUB_ACTIONS === "true") console.log(`::add-mask::${session.access_token}`);
  await expect(page.getByRole("heading", { name: "Your security overview" })).toBeVisible();
  const refreshCookie = (await page.context().cookies()).find((cookie) => cookie.name === "sentinelx_refresh");
  expect(refreshCookie?.secure).toBe(true);
  expect(refreshCookie?.httpOnly).toBe(true);
  const email = `fixture-${Date.now()}@example.com`;
  const password = "Disposable-starter-password-123!";
  const created = await page.request.post("/api/v1/users", {
    headers: { Authorization: `Bearer ${session.access_token}`, Origin: "https://localhost:18443" },
    data: { name: "Disposable teammate", email, password },
  });
  expect(created.status()).toBe(201);
  const context = await browser.newContext({ baseURL: "https://localhost:18443", viewport: { width: 390, height: 844 } });
  try {
    const teammate = await context.newPage();
    await teammate.goto("/login");
    await teammate.getByLabel("Email address").fill(email);
    await teammate.getByLabel("Password", { exact: true }).fill(password);
    await teammate.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(teammate.getByRole("heading", { name: "Secure your account" })).toBeVisible();
    await expect(teammate.getByRole("navigation")).toHaveCount(0);
    await teammate.getByLabel("Starter password").fill(password);
    await teammate.getByLabel("New password").fill("Disposable-own-password-456!");
    await teammate.getByRole("button", { name: "Change password and sign out" }).click();
    await expect(teammate.getByRole("heading", { name: "Welcome to SentinelX" })).toBeVisible();
    await teammate.getByLabel("Email address").fill(email);
    await teammate.getByLabel("Password", { exact: true }).fill("Disposable-own-password-456!");
    await teammate.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(teammate.getByRole("heading", { name: "Add an authenticator" })).toBeVisible();
    const cdp = await context.newCDPSession(teammate);
    await cdp.send("WebAuthn.enable");
    await cdp.send("WebAuthn.addVirtualAuthenticator", { options: {
      protocol: "ctap2", transport: "internal", hasResidentKey: true,
      hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true,
    } });
    await teammate.getByLabel("Sign-in protection").selectOption("passkey");
    await teammate.getByLabel("Current password for passkey").fill("Disposable-own-password-456!");
    await teammate.getByRole("button", { name: "Add passkey", exact: true }).click();
    await expect(teammate.getByRole("heading", { name: "Passkey added" })).toBeVisible();
    await expect(teammate.getByLabel("Recovery codes", { exact: true })).toBeVisible();
    await expect(teammate.getByRole("button", { name: "Continue to sign in" })).toBeDisabled();
    await teammate.getByLabel("I saved my recovery codes privately.").check();
    await teammate.getByRole("button", { name: "Continue to sign in" }).click();
    await teammate.getByLabel("Email address").fill(email);
    await teammate.getByLabel("Password", { exact: true }).fill("Disposable-own-password-456!");
    await teammate.getByRole("button", { name: "Sign in with passkey", exact: true }).click();
    await expect(teammate.getByRole("heading", { name: "Your security overview" })).toBeVisible();
    expect(await teammate.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  } finally {
    await context.close();
  }
});
