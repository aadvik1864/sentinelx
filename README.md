# SentinelX

SentinelX is a security monitoring prototype for reviewing activity from Linux computers, websites, and apps. It brings recorded activity, alerts, and investigations into one shared workspace.

## Open SentinelX

| Version | Link | Access and data |
|---|---|---|
| Full hosted application | [Open the live dashboard](https://sentinelx-fawn.vercel.app) | Sign-in required. Persistent accounts, activity, alerts, and investigations; real monitoring requires connected collectors. |
| Interactive demo | [Open the GitHub Pages demo](https://aadvik1864.github.io/sentinelx/) | No sign-in or setup. Fictional records, browser-only practice, and no connected systems. |

The hosted application uses a Vercel frontend, a Render API, Neon PostgreSQL, and Upstash Redis. It has a separate database from any local installation. There is no public sign-up: an administrator admits trusted teammates and shares their starter credentials privately. First sign-in requires replacing the starter password and setting up an authenticator or passkey.

To receive real activity, open **Connected systems → Connect a system** after account setup and run the provided collector on the computer holding the logs. A website URL alone does not provide its logs. See [connect and monitor real systems](docs/monitoring.md) and [collector behavior](docs/collectors.md).

The hosted assistant currently provides offline evidence summaries; no external AI provider is enabled. The services use free plans. Render sleeps after 15 idle minutes, so the first request can take time to wake the API. This hosting suits a small intermittent deployment and does not guarantee continuous monitoring. See the [cloud deployment guide](docs/cloud-deployment.md) for quotas, configuration, and operational limits.

## Explore the demo

Search activity, review an alert, and open an investigation to explore its timeline and evidence graph. You can add practice notes or change a status. Choose **Reset demo** to start again.

All demo records are fictional. Changes stay in your browser tab and disappear on reload. The assistant provides offline sample explanations and never takes actions. No real systems, accounts, or hosted databases are connected to the demo.

## Features

The full monitoring application supports:

- Live overview with activity totals, alert priorities, and 6/12/24-hour charts.
- Searchable activity with time, system, and priority filters.
- Rule-based alerts and customizable detection rules.
- Investigations with timelines, linked evidence, relationship graphs, notes, and assignments.
- Connection-health indicators and searchable connected-system lists.
- Optional assistant that explains evidence and suggests investigation steps without executing actions.
- Administrator, investigator, and read-only access, with two-step sign-in, passkeys, and account security setup.
- Responsive graphite-and-copper interface with keyboard navigation and reduced-motion support.
- Browser-only interactive showcase with fictional activity and resettable investigation practice.

## Run locally

For a fresh checkout, install Docker with Compose and Python 3, then run from the repository root:

```bash
git clone https://github.com/aadvik1864/sentinelx.git
cd sentinelx
python3 scripts/init_env.py
docker compose up --build --wait
```

Open [localhost:8080](http://localhost:8080). The initialization script creates a private `.env` with random development credentials and refuses to overwrite an existing file. Use its configured administrator email and `BOOTSTRAP_ADMIN_PASSWORD` to sign in. Keep that file private. Local accounts and records remain separate from the hosted application.

For the static demo alone, use Node.js 22 and run from `frontend/`:

```bash
npm ci
npm run build:showcase
npm run preview:showcase
```

See [local deployment](docs/deployment.md), [the showcase guide](docs/showcase.md), and [optional local AI](docs/local-ai.md) for further setup.

## Hosting and automatic deployment

| Component | Hosting and build |
|---|---|
| Full frontend | Vercel builds `frontend/` with `npm run build` and publishes `dist/`. |
| API and live updates | [Render backend](https://sentinelx-api-mn68.onrender.com/health/live) builds `backend/Dockerfile` from the repository root. |
| Persistent storage | Separate Neon PostgreSQL and Upstash Redis resources. |
| Public demo | GitHub Pages publishes only `frontend/dist-showcase/`, built with `npm run build:showcase`. |

Push or merge changes to `main` to automatically deploy the Vercel frontend and Render backend. Both Git integrations have been verified with an actual push. The separate [GitHub Pages workflow](.github/workflows/showcase-pages.yml) rebuilds the demo when frontend files or its workflow change on `main`.

Database schema changes require a separate migration with the migrator identity before releasing code that depends on the new schema. Automatic code deployment does not run migrations. Follow the [cloud deployment guide](docs/cloud-deployment.md); keep database owner credentials, migration credentials, starter passwords, and provider secrets out of Git and public build artifacts.

## A few useful terms

- **Log:** a record of something that happened on a computer, website, or app.
- **Collector:** a small helper that sends logs from a system you have permission to monitor.
- **Detection rule:** a check for patterns in those records that should raise an alert.
- **Investigation:** related alerts, activity, and notes grouped together for review.

An alert means something needs checking; it does not prove an attack. This project is a prototype, not a guarantee that a system is safe. Review the [architecture](docs/architecture.md) and [security boundaries](docs/security.md) before connecting systems.

SentinelX's own code is [MIT licensed](LICENSE); adapted components retain their [original licenses and credits](frontend/public/third-party-notices.txt).
