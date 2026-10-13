# Public showcase

An interactive portfolio demo should show the workflow, not the private monitoring installation. It must use synthetic records and have no access to real accounts, logs, collectors, credentials or backups.

## Static demo build

The showcase is a separate frontend entry point in `frontend/showcase/`. It reuses the overview, activity, alerts, investigation and assistant pages with a small in-memory dataset. No account or password is needed. Hostnames end in `.example.test`; addresses use reserved example ranges. A **Demo — synthetic data** label remains visible on mobile and desktop.

Visitors can filter activity, inspect the evidence graph, create practice investigations, add notes and change statuses. Those edits stay in one tab, with no cookies or browser-storage persistence. Reloading or choosing **Reset demo** discards them. Explanations are labeled browser-only sample summaries; no model, reputation provider or action executor is connected. Real record imports and account/collector setup are unavailable.

From `frontend/`:

```bash
npm ci
npm run build:showcase
npm run test:showcase
npm run preview:showcase
```

The output is `frontend/dist-showcase/`. The normal `npm run build` still produces the authenticated monitoring frontend in `frontend/dist/`; neither build changes an installation. Showcase-only aliases replace the backend client and session hook at build time. A build check rejects imports of the real API/session/socket modules and account/collector setup pages. The showcase has no API proxy and does not expose `VITE_*` settings.

## What to show

- An overview with synthetic activity and connection health.
- Search and time/priority filters.
- An investigation with linked events, notes and an evidence graph.
- An advisory assistant example with evidence references and uncertainty.
- Keyboard navigation and the mobile layout.

Preserve the graphite-and-copper interface, feature-only README, license and [third-party notices](frontend.md). Keep the [architecture](architecture.md) and [security boundaries](security.md) available for reviewers. Describe the project as a monitoring prototype rather than a production security guarantee.

## Publishing

Choose a static HTTPS host, such as Cloudflare Pages or GitHub Pages, and publish **only `frontend/dist-showcase/`**. There is no server, database, collector or secret to provision. Routing uses URL hashes, so direct links and refresh work without server-side SPA rewrites, including under a project subdirectory.

The HTML has a restrictive CSP with `connect-src 'none'`. The build also emits `_headers` for hosts that support that format, adding frame restrictions, no-referrer and nosniff policies. Hosts such as GitHub Pages do not honor `_headers`; the HTML CSP still restricts connections, but response-only controls need a compatible host or proxy. Inspect the actual HTTPS response before publishing. Avoid analytics, external fonts and scripts that would contradict the demo's network boundary.

CI checks the unit tests, both builds, mobile/keyboard workflows, independent visitor state and reload/reset behavior. Browser tests reject API requests, sockets and automatic external traffic. Run publication/secret checks on the exact files to be hosted and retain the license notices. No hosting account, DNS record or deployment is created by these commands.

Do not expose the existing installation or publish shared administrator credentials. `DEMO_MODE` is an authenticated development-lab switch, not a public-demo security boundary; production deliberately rejects it. If demonstrating the real API is necessary, use a separately reviewed deployment with throwaway synthetic data and access restrictions instead of weakening production validation.
