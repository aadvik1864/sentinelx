# Deployment

## Development Compose

```bash
python3 scripts/init_env.py
docker compose up --build --wait
docker compose ps
```

Services: frontend static Nginx, FastAPI backend, PostgreSQL 17, Redis 8, and an unprivileged Nginx gateway. Gateway port 8080 binds to `127.0.0.1`; databases/backend have no published ports. Named volumes preserve PostgreSQL/Redis state. `docker compose down` stops containers without removing data volumes.

Generated `.env` permissions are 0600; `.env`, local database files, and dependency/build artifacts are ignored. Never commit credentials, JWT secrets, provider keys, production logs, or backups.

There is no public sign-up. Use **Settings → Add a person** only after verifying a trusted teammate. Deliver starter passwords privately; newly admitted people must replace them before reading workspace evidence. New production bootstrap accounts must also replace their starter password. Production requires authenticator enrollment, and Settings provides enrollment for development installations with an encryption key. Existing passwords/roles are not replaced by migration. Administrators can disable another account to revoke access.

`ALLOWED_HOSTS=localhost,127.0.0.1` restricts backend Host headers; add a deliberate hostname if using another address. API docs are disabled by default (`API_DOCS_ENABLED=false`); enable them only for private development. Production forbids the opt-in.

Backend startup runs Alembic migrations before Uvicorn. Health endpoints:

- `/health/live`: process responds.
- `/health/ready`: database and configured Redis respond.

For timestamp-preserving real monitoring and a separate database, follow [Connect and monitor real systems](monitoring.md). `POSTGRES_DATABASE` controls Compose's backend connection; changing it does not create a database inside an already initialized PostgreSQL volume. No data volumes need to be deleted.

The backend trusts forwarded headers because it is reachable only through the internal Docker network. Nginx overwrites incoming forwarded IP headers with the observed client IP. Do not publish the backend directly or reuse wildcard proxy trust outside this topology.

## Optional HTTPS listener

`docker-compose.https.yml` adds TLS on a **loopback-only** port and sets backend production gates. It does not obtain certificates, alter your machine's trust store, publish the service publicly, or select a new database. Keep the existing live database, source keys, and collector checkpoints. The HTTP listener remains on `127.0.0.1:8080` for local collection/health; use only the HTTPS origin for browser sign-in once Secure cookies are enabled.

Supply a valid certificate/full chain matching your chosen hostname and a dedicated private key. The mounted files must be readable by Nginx UID/GID 101; use a restricted directory and reviewed ownership/group permissions, **not a world-readable private key**. Keep certificate/key files outside the repository/build context. Define these settings privately in `.env`:

```dotenv
HTTPS_HOST=sentinelx.example
HTTPS_ORIGIN=https://sentinelx.example:8443
HTTPS_PORT=8443
TLS_CERT_FILE=/secure/sentinelx/fullchain.pem
TLS_KEY_FILE=/secure/sentinelx/privkey.pem
# Generate with Fernet.generate_key(); preserve it privately alongside recovery documentation.
MFA_ENCRYPTION_KEY=<privately-generated-key>
```

`HTTPS_ORIGIN` is an exact origin, with no trailing slash, path, credentials, query, or fragment. Ensure DNS (or an operator-managed hosts entry) resolves the hostname to this installation and that clients trust the certificate. The example hostname/paths are placeholders, not provisioned infrastructure.

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --no-deps --build --wait backend nginx
docker compose -f docker-compose.yml -f docker-compose.https.yml restart nginx
```

Use both Compose files for subsequent backend/gateway operations; the base file alone removes the override. If starting the entire stack with local AI, include `--profile local-ai`. After renewal, restart Nginx to reload the mounted files. Verify HTTPS, Secure refresh cookies, HTTPS/WSS connections, HSTS, and host/origin rejection before any remote exposure. HSTS is sent only on the TLS listener (`max-age=31536000`, without `includeSubDomains`); it applies to the hostname, not just this port. Do not enable it on a shared hostname unintentionally. The collector is not automatically moved to HTTPS; local loopback HTTP remains authorized.

## Production adaptation (not turnkey cloud provisioning)

1. Provision an isolated VM/network and DNS; configure trusted TLS and renewal using the optional listener or a maintained outer reverse proxy/load balancer. Keep PostgreSQL/Redis/backend/Ollama unreachable from the public internet. Both bundled gateway listeners remain loopback-only.
2. Use a secret manager and strong unique credentials, including a separately backed-up `MFA_ENCRYPTION_KEY`. Set `ENVIRONMENT=production`, `DEMO_MODE=false`, `SEED_DEMO=false`, `COOKIE_SECURE=true`, `API_DOCS_ENABLED=false`, exact HTTPS `ALLOWED_ORIGINS`, and explicit `ALLOWED_HOSTS`.
3. The bundled listener's CSP derives the WebSocket authority from the request and uses WSS for TLS. If terminating TLS at an outer proxy instead, deliberately configure trusted forwarded protocol, client IP handling, exact CSP origins, and HSTS there; incoming forwarded headers are overwritten by the bundled gateway. Do not assume an outer HTTPS connection changes the inner HTTP listener's policy.
4. Use pinned/scanned images, tested database migration releases, resource limits, log rotation, and backups. Scale only after capacity/correlation concurrency tests.
5. Review existing accounts and admit only verified trusted people. Production MFA gates apply to existing accounts as well. This is a shared workspace, not customer isolation; email ownership is not automatically verified.
6. Enable optional integrations only after reviewing lawful log handling, provider permissions, retention, egress, and costs.

Do not assume changing the environment flag configures TLS, firewall rules, cloud secrets, monitoring, or storage encryption. CI validates/builds locally; it does not deploy to a cloud account.

## Prepared production release

Use the base, HTTPS, and `docker-compose.production.yml` files together. The production overlay adds explicit memory/CPU/process limits and log rotation; it does not expose a public listener, provision infrastructure, schedule maintenance, or select/create a replacement database. Read the [production release checklist and operational commands](production-release.md) before applying it to an existing installation.

## Encrypted backup and restoration

`scripts/backup.py` streams a custom-format `pg_dump` through **age** without writing a plaintext dump. It requires an explicit project, private environment file, Compose files, and database; the output is created exclusively with permissions 0600. Only a successful `status=encrypted` report indicates completion; failed files are retained for review and must not be treated as backups.

`restore-drill` accepts only a **new** database named `sentinelx_restore_<label>`, refuses an existing database, and restores in one transaction. It never replaces or drops existing databases. Counts/schema are reported for review; validate passwords, role/source configuration, evidence, and MFA using isolated application checks before approving recovery. See the [commands](production-release.md#backups-and-recovery).

Separately encrypt and protect configuration, the MFA key, and collector configuration/checkpoints. A database dump alone cannot restore collector positions, TLS/secrets, or encrypted MFA without the matching key. Off-host storage, schedules, retention, and key custody remain operator responsibilities.

## Troubleshooting

- Initial sign-in: use the exact email/password in `.env`, not a shared demo password. Passwords are applied only when creating an absent administrator; changing the environment variable does not reset an existing account.
- Missing tables: run `alembic upgrade head` for the local SQLite backend.
- Empty dashboard: either ingest data or set `SEED_DEMO=true` for first-run sample seeding in development. Seeding does not replace existing events.
- “Polling” instead of “Live”: check the WebSocket upgrade path, exact allowed origin, session validity, and Redis. REST refresh remains active every 30 seconds.
- Port conflict: stop the conflicting service or deliberately change port, allowed origin, and CSP together.
- Provider errors: verify authorized keys/network access. SentinelX returns an upstream error rather than inventing an assessment.
- Viewers cannot investigate/write: an administrator must promote the admitted account in Settings.
