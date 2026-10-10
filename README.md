# SentinelX

SentinelX collects Linux, web server, and application logs, checks detection rules, and groups alerts into investigations.

## Quick start

Requires Python 3, Docker, and Docker Compose.

```bash
git clone https://github.com/aadvik1864/sentinelx.git
cd sentinelx
python3 scripts/init_env.py
docker compose up --build --wait
```

Open **http://localhost:8080** and sign in with:

- **Email:** `admin@sentinelx.dev`
- **Password:** `BOOTSTRAP_ADMIN_PASSWORD` from the generated `.env` file

Keep `.env` and collected logs private. The default setup uses practice data; follow the monitoring guide before connecting real systems.

This is an educational prototype, not a production security platform. Keep it local and review the deployment and security guides before remote access.

## Documentation

[Monitoring](docs/monitoring.md) · [Deployment](docs/deployment.md) · [Security](docs/security.md) · [Assistant](docs/local-ai.md)

## License

SentinelX code: [MIT](LICENSE). React Bits adaptations: [MIT + Commons Clause](frontend/src/components/react-bits/LICENSE.md).
