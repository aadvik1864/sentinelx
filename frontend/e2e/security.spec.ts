import { expect, test } from "@playwright/test";

test("anonymous admission and private/documentation paths are blocked", async ({ request }) => {
  // Intentionally invalid bodies: even a regressed route cannot create a live account.
  for (const path of ["/api/v1/auth/register", "/api/v1/users"]) {
    const response = await request.post(path, { data: {} });
    expect(response.status()).toBe(401);
  }
  for (const path of ["/api/docs", "/api/openapi.json", "/.env", "/.git/config", "/.state/collector.json", "/backend/app/main.py"]) {
    expect((await request.get(path)).status()).toBe(404);
  }
  expect((await request.get("/api/v1/system", { headers: { Host: "untrusted.example" } })).status()).toBe(400);
  expect((await request.get("/health/ready")).status()).toBe(200);
});

test("the browser blocks inline scripts and the login has no public sign-up", async ({ page }) => {
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 401, json: { detail: "Anonymous browser probe" } }));
  const response = await page.goto("/login");
  expect(response?.headers()["x-frame-options"]).toBe("DENY");
  expect(response?.headers()["permissions-policy"]).toContain("camera=()");
  await expect(page.getByText(/Ask your workspace administrator/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Create an account" })).toHaveCount(0);
  const executed = await page.evaluate(() => {
    const script = document.createElement("script");
    script.textContent = "document.documentElement.dataset.inlineProbe = 'executed'";
    document.head.appendChild(script);
    return document.documentElement.dataset.inlineProbe;
  });
  expect(executed).toBeUndefined();
});
