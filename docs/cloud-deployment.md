# Full SentinelX dashboard on Vercel and Render

The Vercel frontend sends `/api/*` requests through an external rewrite to the
Render API. Refresh cookies remain Secure, HttpOnly, SameSite=Strict cookies on
the frontend origin. Live updates connect directly to the API's WSS endpoint;
`VITE_BACKEND_ORIGIN` is the public HTTPS backend origin, never a credential.

The Render API uses externally hosted Neon PostgreSQL and Upstash Redis in
Singapore. All three are explicitly on free plans. The existing Paperloom
services and the local SentinelX installation remain separate.

Neon's free quota is currently 1 GB of storage and 100 CU-hours per month per
project. Upstash's free quota is currently 256 MB and 500,000 commands per month;
automatic paid upgrades are disabled. The Render API sleeps after 15 idle
minutes and shares the workspace's 750 free service-hours per calendar month.
These limits suit intermittent small deployments, not guaranteed continuous
monitoring. Quotas may change; check the providers' current pricing pages.

The created service uses Render's default TCP health checks, which do not query
either external datastore. The reference Blueprint uses `/health/live`, and
deployment verification checks `/health/ready` manually. This avoids
using database compute and Redis commands for every automatic health probe.

## Deployment sequence

1. Provision Neon `free_v3` and Upstash `free` through the Vercel Marketplace,
   disabling Upstash auto-upgrade. The provider terms require acceptance by
   the account owner.
2. Commit and push the cloud deployment code to the existing GitHub repository.
   Create only the free Render API through MCP. `render.yaml` is a reference
   for reproducing that service; do not apply a duplicate Blueprint.
3. Generate separate JWT, Fernet MFA, database-migration and runtime secrets.
   Save them in a private ignored deployment directory outside hosted artifacts.
4. Initialize only the newly created dedicated database from a local one-shot
   job using its external TLS URL. Do not supply the database owner, migration
   credential, or administrator starter password to the API service.
5. Supply the API with its restricted runtime password, database host/port/name,
   Redis URL, JWT secret, MFA key, exact Vercel production origin and trusted
   frontend/backend hostnames. Set `WEBAUTHN_RP_ID` to the frontend hostname.
6. Run `python scripts/prepare_vercel.py --backend-origin https://ACTUAL_API_HOST`
   from the repository root. This writes the proxy/CSP config and the ignored
   frontend `.env.production` containing only the public backend origin.
7. Build and deploy the full frontend from `frontend/` to the linked Vercel
   `sentinelx` project. Set `VITE_BACKEND_ORIGIN` in Vercel production build
   environment variables if using remote builds or Git deployments.
8. Verify backend readiness, Vercel API proxying, cookie refresh, first-login
   security setup, CSP, mobile navigation, and authenticated WSS updates.

## One-shot cloud bootstrap

Run from `backend/` with the repository's Python dependencies available.
Supply environment variables privately rather than placing secrets in commands:

- `CLOUD_ADMIN_DATABASE_URL`: external URL of the new database, with
  `sslmode=require`.
- `POSTGRES_MIGRATION_PASSWORD`, `POSTGRES_RUNTIME_PASSWORD`: distinct random
  values with at least 24 characters each.
- `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD`: the intended owner and a
  privately generated starter password with at least 12 characters.
- Production configuration: `ENVIRONMENT=production`, `COOKIE_SECURE=true`,
  `DEMO_MODE=false`, `SEED_DEMO=false`, `API_DOCS_ENABLED=false`,
  `LIVE_MONITORING=true`, `LLM_PROVIDER=offline`, `JWT_SECRET`,
  `MFA_ENCRYPTION_KEY`, `REDIS_URL`, `ALLOWED_ORIGINS`, `ALLOWED_HOSTS`,
  `WEBAUTHN_RP_ID`.

```bash
python -m app.cloud_bootstrap \
  --confirm-host ACTUAL_EXTERNAL_DATABASE_HOST \
  --confirm-database ACTUAL_NEW_DATABASE_NAME
```

The initializer refuses a populated database, mismatched host/database, or a
cluster with existing SentinelX roles. It migrates and bootstraps a new database
and grants the runtime only the application's permitted operations. It does not
copy local accounts, monitoring evidence, collectors, or database contents.

The service starts with `python -m app.cloud_runtime`; it performs no schema
migration or account bootstrap. Future migrations must run separately with the
migrator credential before the runtime is redeployed.

The first administrator must change the starter password and enroll an
authenticator or passkey. The hosted dashboard starts without monitoring data;
connect real systems through Settings after signing in. Offline evidence
summaries work without an external AI account; optional external providers need
the existing controlled-egress arrangement before activation.

## Verification completed during preparation

- Full frontend TypeScript/Vite build passed.
- Hosted-backend connection tests passed (3 tests).
- ESLint and Python lint checks passed for the deployment changes.
- Render Blueprint matched Render's official JSON Schema.
- An isolated PostgreSQL cluster with a non-superuser managed-style owner passed
  role provisioning, all migrations, administrator first-login gating, no demo
  seeding, and runtime checks denying schema creation and event deletion.

Hosted checks are recorded in the current deployment section below.

## Current deployment

- Frontend: https://sentinelx-fawn.vercel.app
- Backend: https://sentinelx-api-mn68.onrender.com
- Render service: `srv-db7eo5m7bikc73ak6v80`, free plan, Singapore.
- Neon project: `long-butterfly-04047585`, free plan, Singapore.
- Upstash database: `cbe4d499-baea-4689-bfdd-22d8d26391ee`, free plan, Singapore.
- Application/provider credentials are kept in the private ignored
  `.release/cloud/` directory. Owner credentials are not supplied to the API.
- Vercel and Render automatically deploy pushes to `main` from
  `aadvik1864/sentinelx`. Vercel builds from `frontend/`; Render builds
  `backend/Dockerfile` with the repository root as its Docker context.
- Database migrations still run separately with the migrator identity before
  pushing backend changes that require a new schema.

Hosted verification passed readiness through the proxy and directly on the API,
browser sign-in, Secure/HttpOnly/SameSite=Strict refresh cookies, account-setup
gating, session refresh, logout, and mobile layout. Authenticated live updates
become available after the administrator completes their password/MFA setup.

GitHub Pages remains a separate browser-only showcase built with
`npm run build:showcase`. It publishes fictional records from `dist-showcase`,
with no connection to the hosted application accounts or databases.
