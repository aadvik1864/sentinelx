# Connect a website, app, or Linux server

SentinelX watches **logs you have permission to read**. Entering a website URL alone does not give it access to that website's security activity. It does not scan sites, install itself remotely, or execute response actions.

## From the console

1. Sign in as an administrator. Open **Connected systems → Connect a system**.
2. Choose **Linux computer**, **Website**, or **Web app**, and give it a recognizable name.
3. In **Details**, enter the computer name and activity file location. Websites also let you choose Nginx or Apache. Ask the server administrator for these details if you are unsure.
4. Review and save the connection. This does not install anything on the server.
5. Follow the **Download → Run on server → Check** steps. Save the helper and private connection settings before leaving; the private key is shown only once. Run the helper on the computer holding the files, not on your laptop unless the logs are there.
6. Return to **Connected systems**. Click **View activity** to see only that connection's records. Expand **Connection details and settings** for setup instructions, counts, or administrator controls.

Administrators can pause/resume collection or replace a lost/leaked source key. Analysts can view status, logs, and setup instructions. Viewers cannot access raw logs or collector setup.

The file path is a setting for the collector; the backend never opens arbitrary user-entered paths. To move collection to a different system or log format, create a new connection and pause the old one. For a changed file path on the same system, update `path` in its private collector configuration and restart the collector. Keep its existing checkpoint database.

### Pick the right logs

| What you want to watch | What to connect |
|---|---|
| A Linux server's SSH/sudo activity | `/var/log/auth.log` on many Debian/Ubuntu systems; `/var/log/secure` on many RHEL systems |
| One particular website | That site's own Nginx or Apache access log, not a shared log for every virtual host |
| A web app's sign-ins/security activity | A JSON-lines security log emitted by your application |

For one Nginx site, configure a separate access log in its existing `server` block, such as `access_log /var/log/nginx/mysite-access.log combined;`, and use that file's path when connecting it. For Apache, use a per-virtual-host `CustomLog /var/log/apache2/mysite-access.log combined`. Have the server operator validate and reload configuration normally; SentinelX does not change it automatically. Access logs show requests and HTTP status, **not whether an application password was correct**.

An app needs to write real security events itself. Example format (replace the timestamp, address, and username with actual values):

```json
{"timestamp":"2026-10-08T10:00:00Z","event_type":"authentication_failure","message":"Sign-in rejected","ip":"203.0.113.10","username":"alice","level":"WARNING"}
```

Use `authentication_success` for successful sign-ins, and `application_error` for failures you want covered by an error-burst rule. Do not write passwords, tokens, cookies, or full request bodies. Do not guess client IPs from untrusted forwarded headers.

### Another server

The default development gateway is accessible only on its own machine. On the monitored server, keep an authorized SSH tunnel running:

```bash
ssh -N -L 8080:127.0.0.1:8080 your-user@sentinelx-host
```

Then use `http://localhost:8080` in the collector configuration. If port 8080 is already used on the monitored server, choose another local port and change the configuration accordingly. A managed deployment can instead use its verified HTTPS origin. The agent rejects remote plain HTTP, URL credentials, redirects, and URLs containing paths/query strings. TLS verification remains enabled; environment HTTP proxies are not used.

Install Python 3.12+ and run beside the downloaded files:

```bash
python3 -m venv .venv
.venv/bin/pip install httpx==0.28.1
chmod 600 sentinelx-source.json
.venv/bin/python sentinelx-agent.py --config sentinelx-source.json
```

Use a read-only log account or appropriate ACL/group permissions, including on newly rotated files. Do not make logs world-readable or give the agent unrestricted sudo merely to connect a source. Supervise the collector and SSH tunnel for long-running use; the wizard does not remotely install a system service.

## What the status means

| Status | Meaning / next step |
|---|---|
| Setup needed | No collector heartbeat received yet. Run its setup steps. |
| Connected | Collector is responding, but no record arrived in the last 90 seconds. Quiet is normal. |
| Receiving activity | A record arrived in the last 90 seconds and the collector heartbeat is current. |
| Needs attention | Read the displayed error: check permissions, container availability, record format, or collection gaps. |
| Disconnected | No heartbeat for over 90 seconds. Check the service, tunnel, and API reachability. |
| Paused | Administrator disabled delivery. Resume when ready. |

Status is reconciled about every 30 seconds. The top-bar **Live updates** indicator means the browser's notification connection works; it does not prove a system's helper is connected. **Auto refresh** means the browser is falling back to periodic refresh. Source totals count accepted records, not heartbeats or rejected records. The last receipt time and original occurrence timestamp are separate. Technical error messages remain available under connection details.

## Enable the three local sources without mixing demo history

This setup connects **this Linux host**, **SentinelX's Nginx gateway**, and **SentinelX's FastAPI application**. It does not connect an unspecified external website.

For an existing default Compose installation:

1. Create an additional database; leave `sentinelx` and all volumes untouched. Run once (if it exists, skip this command):

   ```bash
   docker compose exec -T postgres createdb -U sentinelx sentinelx_live
   ```

2. Change only these settings in the private `.env`:

   ```dotenv
   DEMO_MODE=false
   SEED_DEMO=false
   LIVE_MONITORING=true
   POSTGRES_DATABASE=sentinelx_live
   ```

   Changing `DATABASE_URL` alone does not change the Compose database. The live flag refuses demo seeding/simulation settings, but does not cleanse an existing database: use the separate database above. A fresh PostgreSQL volume initializes the chosen database automatically.

3. Recreate the application/proxy (brief downtime); the proxy must resolve the recreated containers:

   ```bash
   docker compose up --build --wait backend frontend
   docker compose up --build --wait --force-recreate nginx
   ```

4. With the repository's Python environment installed, register the local sources and supervise the collector:

   ```bash
   .venv/bin/python scripts/setup_monitoring.py --install-service
   systemctl --user status sentinelx-collector
   ```

   Source-only keys are saved to ignored `.state/collector.json` (0600); checkpoints/quarantine are in `.state/collector.sqlite3`. The script uses the bootstrap administrator only to provision sources/assets/rules, logs that session out, and never gives the agent dashboard credentials. Existing saved keys are reused, not silently rotated. It assumes the existing bootstrap password still matches the account; if it was changed, provision from the console instead.

5. Open the console, sign in again if needed, and check **Connected systems**. New file collection begins at the end, so old history is not presented as current activity. Regular sign-ins/site visits generate web/app records; SSH/sudo activity generates Linux records. A benign `logger -p auth.info -t sentinelx 'Local collector connectivity check'` can verify Linux delivery where a syslog daemon routes auth messages to that file. This produces an explicitly operator-generated connectivity record, not a fake attack.

The user service runs with your user's existing permissions and Docker access. Docker socket access is powerful; prefer separately exported read-only log files in a hardened deployment. A user service runs only while its user manager is active. If it must start at boot and survive logout, ask your administrator to enable lingering for that user; the setup script does not change that policy.

For a collector restart, use `systemctl --user restart sentinelx-collector`. For diagnostic output, use `journalctl --user -u sentinelx-collector`; do not share raw host/container logs without review.

To revisit the demo, stop the local collector, set `POSTGRES_DATABASE=sentinelx`, `LIVE_MONITORING=false`, and restore your previous demo flags. Recreate backend/frontend and then Nginx as above. Never use `docker compose down -v` to switch modes. Browser investigation tests that insert simulations belong in demo mode, not the real database.

See [collector delivery details and limitations](collectors.md) before treating collection as a security control.
