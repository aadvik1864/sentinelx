# Public showcase

An interactive portfolio demo should show the workflow, not the private monitoring installation. It must use synthetic records and have no access to real accounts, logs, collectors, credentials or backups.

## Recommended approach

For a personal project, use a separate frontend-only demo on a static HTTPS host. Visitors can explore sample investigations, filter activity and inspect evidence without a shared backend account. Any editable practice state stays in that visitor's browser and resets on reload; it does not change another visitor's session. Do not ask visitors for passwords or personal log files.

Keep a visible **Demo — synthetic data** label. Use fictional hostnames and reserved example addresses. Assistant explanations must be labeled as sample content or deterministic offline analysis, not responses from a live model. The demo should not call the monitoring API, open its WebSockets, accept collector events, or send data to external providers.

This browser-only public demo is a proposed addition, **not an existing build mode**. The current application still requires a backend and authenticated sessions. The practice screenshots in [Frontend interactions](frontend.md) were created with isolated browser fixtures; they are not proof that a deployable public demo exists.

## What to show

- An overview with synthetic activity and connection health.
- Search and time/priority filters.
- An investigation with linked events, notes and an evidence graph.
- An advisory assistant example with evidence references and uncertainty.
- Keyboard navigation and the mobile layout.

Preserve the graphite-and-copper interface, feature-only README, license and [third-party notices](frontend.md). Keep the [architecture](architecture.md) and [security boundaries](security.md) available for reviewers. Describe the project as a monitoring prototype rather than a production security guarantee.

## Before publishing an interactive build

1. Implement and test the separate demo entry point. Normal monitoring builds must keep their existing authentication and data paths.
2. Confirm that demo navigation, refresh, filters and practice edits work without a backend, API secrets or shared sessions.
3. Check the built files and browser requests for real data, private identifiers, credentials and monitoring endpoints. Reject unexpected API/WebSocket/provider traffic in browser tests.
4. Test mobile widths, keyboard use, direct page links and reload/reset behavior. Keep demo build and browser checks in CI.
5. Choose the hosting account and hostname, publish only the inspected static build, and verify trusted HTTPS and security headers. Apply the appropriate restrictive CSP rather than inheriting an unreviewed host default.

Do not expose the existing installation or publish shared administrator credentials. `DEMO_MODE` is an authenticated development-lab switch, not a public-demo security boundary; production deliberately rejects it. If demonstrating the real API is necessary, use a separately reviewed deployment with throwaway synthetic data and access restrictions instead of weakening production validation.
