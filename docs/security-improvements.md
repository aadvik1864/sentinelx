# Security and reliability follow-up

This follow-up is code-level release preparation, not an upgrade of the existing installation. The earlier passing release/CI evidence applies to its named commits, not automatically to these changes. Deployment, secrets, clocks, off-host destinations, alert channels, repository-policy activation and independent review still need explicit operator approval.

## Database identities

The production overlay uses four separate identities:

| Identity | Purpose |
|---|---|
| `sentinelx` | Existing PostgreSQL bootstrap administrator; delivered only to the one-shot role setup job |
| `sentinelx_migrator` | Selected database schema ownership, migrations and initial account/rule bootstrap; not an API credential |
| `sentinelx_runtime` | Explicit application DML grants; cannot create objects/roles, alter version state, modify/delete raw evidence or receipts, or rewrite audit rows |
| `sentinelx_notifier` | Optional outbox SELECT/UPDATE only; no account/evidence reads and no JWT/MFA/bootstrap credentials |

Fresh generated configurations include independent credentials. **Do not overwrite or regenerate the live `.env`.** Production requires a dedicated PostgreSQL cluster because role names/passwords are cluster-wide; setup refuses existing production-role dependencies in another database. Existing environments require deliberate secret delivery, a reviewed backup, selected-database ownership/grant rehearsal, and deployment approval. The role setup command requires `--apply --confirm-database <exact-name>`; its Compose job is invoked only when deliberately starting the production stack. API startup verifies its role. Restoration omits owners/ACLs: rehearse it in a separate cluster, then reapply selected-database role provisioning/grants before activation.

Run retention or operator account recovery with separately controlled maintenance credentials, not the API runtime identity. Existing installation passwords, roles, source keys and checkpoints are not replaced by preparing these files.

## Account and collector protection

Settings supports user-verified WebAuthn passkeys as a second factor alongside passwords. Registration requires the current password and account setup gates. Every challenge is five-minute, single-use, origin/account/version-bound; verification checks RP ID, presence/verification, signature and counters. Credential private keys stay with the authenticator. Registration/removal revokes sessions; removing the last factor is blocked. TOTP and recovery-code alternatives remain available and are **not phishing-resistant**. Losing every factor still requires independently verified operator recovery; `reset-mfa --include-passkeys` is a deliberate, separately confirmed operation.

After factor enrollment, the browser immediately clears its session and displays a blocking recovery-code confirmation outside the revoked session's route tree. Codes remain only in React memory until acknowledged; socket/refresh failures cannot silently remove that screen. Reloading still clears it, so save codes privately before continuing. Passkey sign-in/security changes emit redacted genuine-activity telemetry as well as audit entries.

New collector keys expire after 90 days. Planned rotation can overlap for at most ten minutes; the UI offers five minutes and defaults to immediate revocation. Never use overlap for a suspected leak. Update only the private key, preserving the original checkpoint/quarantine state. Migrated legacy keys retain their old lifetime until reviewed/rotated, so an upgrade does not silently break existing collection.

The collector, server ingestion and provider-context preparation perform best-effort credential redaction, including structured secret fields, common token formats, private-key blocks and URL credentials/queries. They do not guarantee removal of arbitrary sensitive data, rewrite already-stored evidence, or implement universal PII redaction.

## Network and alert delivery

The production API belongs only to the internal network. External providers require explicit `docker-compose.egress.yml` opt-in, a separate proxy credential and exact approved `EGRESS_ALLOWED_HOSTS`. The proxy supports authenticated CONNECT to port 443 only, rejects private/mixed DNS answers, pins checked literal addresses, and bounds concurrent tunnels/time/bytes. Provider TLS verification stays enabled; no ambient proxy or redirect inheritance is permitted. Optional Ollama/host workloads have separate network boundaries and require their own review.

Approved destinations can still receive the supplied evidence, and Docker/host DNS is not a universal exfiltration firewall. Review DNS and host-network policy separately; this proxy is not content inspection or protection from a compromised host.

New alert records and minimal outbox payloads commit atomically. `python -m app.notifications` previews pending IDs/counts without sending. Actual delivery requires `--apply --confirm-database <exact-name>`, the notifier-only identity, an approved HTTPS receiver/host and the controlled-egress proxy. `docker-compose.notifications.yml` is a deliberate opt-in with the production and egress overlays, not a scheduled default.

The worker uses 60-second leases, bounded retry backoff and stable `Idempotency-Key` IDs. A worker crash does not discard pending rows. Delivery is **at-least-once**: an accepted HTTP response is not proof of human receipt, and receivers must deduplicate/reject replay according to their policy. Pending/delivered outbox rows are not erased automatically; approve their storage/lifecycle and alert on backlog. Websocket broadcasts remain best-effort with REST reconciliation. No notification executes containment or assistant recommendations.

## Clocks, capacity and governance

Production observes local wall time against monotonic progress. An observed step of 50 ms or more latches readiness and workspace access failure until an operator investigates and deliberately restarts the approved target. It never changes the host clock or relaxes JWT/TOTP checks. It does not measure absolute NTP accuracy; synchronization/skew alerts are still required. `scripts/health_check.py` now also verifies trusted TLS and warns before certificate expiry (14 days by default).

The release helper accepts seven days of quiet synthetic history (**6,048,000 events/receipts**) and bounded 20-EPS bursts within a sustained ten-EPS minute budget. The receipt-time metric index avoids rescanning all older history for the one-minute rate. `.github/workflows/capacity.yml` prepares a manually approved, isolated extended run with storage preflight; merely adding that workflow does **not** validate the seven-day footprint, mixed workloads or long-term evidence/receipt growth.

All GitHub Actions are commit-pinned; Dependabot proposes dependency/action/image updates for review. `.github/rulesets/main.json` is a **not-yet-applied** policy template requiring the five CI job checks, one independent approving reviewer, resolved discussions and no bypass/force-push/deletion. Identify an available second reviewer and review existing repository rules before activating it; importing this template can intentionally block a solo maintainer's merges. No GitHub repository settings are changed by adding the file.

Frontend pages are lazy-loaded while retaining the existing graphite/copper interface. Initial JavaScript is approximately 354 kB in the local build, with graphs/charts/pages loaded separately; build warnings have not been hidden by raising chunk thresholds.

## Validation status

- Existing SQLite regressions initially passed **139 tests** (eight PostgreSQL-only skips), but the clock observer rejected that run after a **1.180234-second** forward step. That is not stable-runner acceptance.
- **37 targeted** passkey, delivery, collector and egress tests passed, including real ES256 registration/assertion verification and invalid origin/RP/user-verification/signature/counter checks.
- Frontend: **47 tests passed**; lint/build passed. Release-helper tests: **21 passed**. These observations precede final-source regression/CI validation.
- The subsequent full SQLite run passed **190 tests** (11 PostgreSQL-only skips), but its clock gate rejected a **1.066291-second** step. Source lint/format, dependency audits and workflow lint passed. PostgreSQL migration/grant and concurrency tests still require the stable CI database job.
- The session-independent recovery-code confirmation follow-up passed **49 frontend tests**, including late-session-failure preservation and memory-only acknowledgement, plus frontend lint/build. Targeted passkey regressions passed **17 tests** with one PostgreSQL-only skip; these are not a substitute for exact-commit CI.
- The first disposable production pilot completed role setup/migrations and demonstrated **seven privilege denials** with privileged API credentials absent, then failed readiness after a **1.509153-second** clock step. The failure and private diagnostics are retained; no clock/token gate was weakened and no live service was restarted.

Those local observations were not release acceptance. The following CI records distinguish failed candidates from the final passing application checks. The independent [operator acceptance record](operator-acceptance.md) remains NO-GO for deployment.

The [first follow-up CI run](https://github.com/aadvik1864/sentinelx/actions/runs/38249689482), commit `aedc66b489be9790011a66f30ccd1b80b05f92c9`, passed both database jobs, the frontend/development-browser jobs, production capacity/restore checks and exact-image scans, but failed the final browser assertion: its non-exact “Recovery codes” label selector matched both the code block and the acknowledgement checkbox. The selector is now exact; the failed run remains evidence and no application, clock, latency or security gate was relaxed.

Its one-day/ten-minute fixture reached **10.001 EPS**, ingestion p95 **0.0525 s** and dashboard p95 **0.7050 s**, with 120 reads. It verified 11 runtime and six notifier privilege denials, restored **870,001 events/receipts**, compared 17 tables, and recorded zero HIGH/CRITICAL findings across five matching runtime image IDs. Those passing sub-gates do not make its failed overall run an accepted release.

Production browser stdout/stderr now go to exclusive-create 0600 private fixture logs, including assertion diagnostics that could contain newly enrolled recovery codes. Those logs and browser captures are not uploaded. Pass/fail remains an unchanged blocking CI gate; the public output provides only its result.

The [recovery-confirmation candidate run](https://github.com/aadvik1864/sentinelx/actions/runs/38250791574), commit `b953184558862de078f45fb89a5b5ce6cbdfb3fd`, also passed its other jobs/capacity/restore/scanning sub-gates but reproduced the same non-exact browser-selector failure. It is retained as a failed overall run, not accepted by a retry alone.

### Validated follow-up application (2026-10-12)

[Run 38252160341](https://github.com/aadvik1864/sentinelx/actions/runs/38252160341) passed all five jobs for exact application/tooling commit `a60b67088061339f9d73c19cbcca17da674d8b62`:

- SQLite: **190 passed, 11 PostgreSQL-only skips**. PostgreSQL: **201 passed**, including populated upgrade/ownership/grants and concurrent passkey/outbox tests. Release-tool tests: **23 passed** per database job. All observed runner clocks were stable.
- Frontend: **49 unit tests passed**, lint/build/audits passed. The development investigation browser suite passed **16 tests**; the trusted-CA production password/MFA/passkey workflow also passed.
- Capacity: **864,000** quiet preloaded synthetic events/receipts plus **6,000** new API deliveries over 600 seconds, **10.001 EPS**, ingestion p95/max **0.0378/0.7822 s**, dashboard p95/max **0.6805/0.8237 s**, with 120 reads. The original latency and clock gates were unchanged.
- Verified **11 runtime** and **six notifier** privilege denials, privileged API credentials absent, and certificate-expiry warning behavior.
- PostgreSQL restart and Redis failure/retry passed. Encrypted restoration preserved **870,001 events/receipts**, schema `0008_receipt_metrics`, SHA-256 content across **17 tables**, corrupt-archive rejection and existing-database refusal.
- All **five exact runtime image IDs** matched the scan summaries, with **zero reported HIGH/CRITICAL findings**. Optional Ollama, proxy deployment and real notification receivers remain separately reviewed operator choices.

This validates only the documented one-day fixture and release profile, not seven-day retention, mixed workloads/bursts, absolute time synchronization, real notification receipt, operational sign-offs or security certification. No live installation was upgraded, migrated, exposed or restarted.
