# Full SentinelX dashboard on Vercel and Render

The Vercel frontend sends `/api/*` requests through an external rewrite to the
Render API. Refresh cookies remain Secure, HttpOnly, SameSite=Strict cookies on
the frontend origin. Live updates connect directly to the API's WSS endpoint;
`VITE_BACKEND_ORIGIN` is the public HTTPS backend origin, never a credential.

The Render API uses PostgreSQL and Redis in Singapore. The Blueprint defaults to
free plans. My Workspace already uses its one free PostgreSQL and Key Value
slots for Paperloom, so deploying a separate SentinelX stack there requires
approval for paid datastore plans. An always-on API also requires a paid plan.
Keep the existing Paperloom services and the local SentinelX installation intact.

## Deployment sequence

1. Approve the proposed backend plans. For the existing workspace, select
   PostgreSQL `0.1c-256mb`, Key Value `256mb`, and either a free API or
   `0.5c-512mb` for an always-on API. Set database storage to 1 GB initially.
2. Commit and push the cloud deployment code and `render.yaml` to the existing
   GitHub repository. Apply the Blueprint only once; do not create duplicate
   resources through both a Blueprint and direct creation.
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

Hosted checks remain pending resource creation and deployment.
