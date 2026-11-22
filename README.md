# SentinelX

SentinelX helps you review activity from computers, websites, and apps. It brings logs, alerts, and investigations into one place so you can see what happened and what to check next.

## Live application

**[Open the live dashboard](https://sentinelx-fawn.vercel.app)**. Sign in and connect your systems to receive real activity.

The live app stores your workspace's records in a database. There is no public sign-up. Ask the workspace administrator for access. On your first sign-in, choose your own password and set up an authenticator or passkey.

## What you can do

- See recent activity and alerts that need a closer look.
- Search records by time, system, or priority.
- Set detection rules to flag patterns worth checking.
- Review investigations with timelines, linked evidence, and notes.
- Check whether your connected systems are sending activity.
- Use the assistant to explain records and suggest checks. It never changes your systems.

A **log** is a record of something that happened. An **alert** flags activity worth reviewing. An **investigation** brings related records and notes together. An alert does not prove an attack.

## Connect your systems

Open **Connected systems → Connect a system** in the live app. Follow the steps to run a **collector**, a small helper that sends logs, on the computer holding those logs.

Adding a website URL alone does not give SentinelX access to its activity. See the [connection guide](docs/monitoring.md) for setup steps.

## Built with

React handles the interface. FastAPI handles requests, PostgreSQL stores records, and Redis helps deliver live updates. The full app runs on Vercel and Render.

## Run on your computer

Install Docker with Compose and Python 3. For a fresh checkout, run:

```bash
git clone https://github.com/aadvik1864/sentinelx.git
cd sentinelx
python3 scripts/init_env.py
docker compose up --build --wait
```

Open [localhost:8080](http://localhost:8080). The setup script saves local sign-in details in a private `.env` file. Use its configured email and `BOOTSTRAP_ADMIN_PASSWORD`. Keep the file private. Your local accounts and records are separate from the live app.

## Updates and limits

Pushing code to `main` automatically updates the live app. Changes to the database structure need a separate migration before releasing code that uses them. See the [hosting guide](docs/cloud-deployment.md) for details.

The free backend pauses when idle, so opening the live app can take a little time. The hosted assistant currently uses offline summaries. This is a monitoring prototype for learning and investigation, with no guarantee of continuous monitoring or system safety.

For more details, see [local setup](docs/deployment.md) and [security](docs/security.md).

SentinelX's own code uses the [MIT license](LICENSE). Adapted components keep their [original licenses and credits](frontend/public/third-party-notices.txt).
