# Security boundaries

SentinelX is a single-workspace educational MVP. It requires a separate security review, capacity tests, operational controls, and deployment-specific hardening before use with sensitive logs.

## Included controls

- Argon2id hashes; minimum 12-character provisioned/bootstrap/new passwords; no plaintext password storage.
- JWT HS256 algorithm allowlist, required issuer/audience/expiration/session/version claims, and 15-minute access lifetime.
- Random refresh tokens stored only as SHA-256 digests. Single-use rotation, session-family replay revocation, seven-day expiration, immediate logout/password-change access revocation. Consuming a refresh token does not invalidate still-valid access tokens in other tabs.
- In-memory browser access tokens; HTTP-only, SameSite Strict refresh cookies. Cross-tab Web Locks serialize rotation where supported. Secure cookies mandatory in production.
- Explicit Origin checks on cookie-backed mutations, allowlisted CORS and WebSocket origins, and first-frame socket authentication. WebSocket tokens never enter URLs/access logs.
- Server-side RBAC on REST **and** sockets. Only administrators can create people through `/users` or the compatibility `/auth/register` route; anonymous requests receive 401 and other roles 403. New accounts are always VIEWER; submitted role fields are rejected. Role updates invalidate existing access versions. Administrators must verify the recipient and share starter passwords privately; there is no emailed invite or forced first-login password change.
- Explicit backend Host allowlist without wildcards; development API docs require opt-in and are forbidden in production. The gateway denies dotfiles/source/config paths rather than returning the SPA, and Docker build contexts exclude private collector state, SQLite state, and certificate/key files.
- Pydantic validation, parameterized SQLAlchemy queries, escaped substring search, metadata/log/body limits, bounded list sizes, and plain React text rendering (no raw HTML injection).
- Redis-backed rate limits when configured; bounded in-memory fallback for development only. Production fails closed if rate limiting Redis is unavailable.
- Audit logging of login, account creation, rule/asset/role changes, incident/alert changes, enrichment, simulation, and analysis. Passwords, JWTs, refresh tokens, and API keys are never included in audit change metadata.
- Non-root application/Redis/Nginx containers, read-only application/proxy root filesystems, dropped capabilities, no-new-privileges, internal database network, authenticated Redis, and loopback-only gateway publication.
- Fixed external threat-provider endpoints and validated indicators; no user-controlled URL fetch or real scan function.
- Source-scoped hashed collector keys, one-time issuance and explicit replacement/pause revocation, admin-only provisioning, and allowlisted health errors. These keys cannot access dashboard/event reads. The monitoring agent requires verified HTTPS or loopback HTTP, does not follow redirects/use environment proxies, and redacts common credentials before transmission.

## Assistant trust boundary

Logs, event names, case text, and enrichment are untrusted input. The LLM receives a system instruction separating data from instructions and a bounded JSON context. Its response must match the output schema and supplied asset/technique/reference allowlists. Prompt instructions and schema validation cannot guarantee truth or completely prevent prompt injection.

The assistant has **no tools or action executor**. It cannot delete files, block IPs, change firewalls, kill processes, disable accounts, or modify assets. Analysis is advisory; operational containment remains external, manually verified and approved. The UI explicitly labels deterministic offline, local LLM, and external LLM output and highlights uncertainty/false positives. The optional Ollama service has no published port, Docker socket, or host mounts; cloud features are disabled, though outbound access remains available for model downloads. Explicit local/offline selection never falls back to an external provider. Schema and reference checks do not establish factual accuracy or immunity to prompt injection. See [local AI boundaries](local-ai.md).

Enabling an external LLM sends a sample of log messages, selected investigation fields, names, indicators, assets, and intelligence to that provider. The bundled local Ollama mode keeps inference inside this installation. Ensure lawful authorization, redact confidential data, and review external-provider retention/region policies before enabling. The MVP does not implement a general PII-redaction service.

## Production gates and remaining work

`ENVIRONMENT=production` requires PostgreSQL, Redis, secure cookies, a 32+ character JWT secret, exact HTTPS origins with explicitly allowed hostnames, and disabled demo/docs flags. These are configuration gates, not a production-readiness certification. The optional [HTTPS override](deployment.md#optional-https-listener) needs an operator-provided trusted certificate; the normal local installation remains HTTP on loopback, without Secure cookies or HSTS.

Still needed for a hardened public service: deployment-specific trusted TLS setup/renewal and verification, stronger invitation/identity verification and forced starter-password changes, MFA/SSO, organization/resource isolation, collector key expiration/managed secret distribution, robust cross-tab fallback for unsupported browsers, refresh-record cleanup, retention policies, encrypted backups with restore drills, external availability monitoring/alerts, secret manager integration, tamper-resistant audit exports, durable publication/outbox, upstream request egress restrictions, and independent penetration testing.

The local collector runs as the operator's existing user, with that user's log and Docker access; Docker socket access is effectively privileged. It is not a sandboxed host intrusion agent. Redaction is best-effort, and evidence can contain usernames, addresses, command paths, or other sensitive information. Use deliberately safe logging and reviewed permissions. Source health/record counters show collection, not complete coverage or a verdict that the system is secure.

Threat intelligence is incomplete by design: one optional IP provider, no external domain/hash providers. Unknown/no-known-reports does not imply benign behavior. Cache timestamps describe local observations, not the indicator's real first/last appearance on the internet.

No hostile activity is authorized by this project. Collect and simulate only in environments you own or have permission to monitor.
