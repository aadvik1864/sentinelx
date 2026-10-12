"""Validate production gates, 10 EPS, failure recovery, and encrypted restoration.

Creates a uniquely named disposable Compose project. NEVER selects the live .env,
database, collector state, or ports. Requires Python httpx/pyotp, openssl, age,
age-keygen, and Docker Compose 2.24.4+. Private test artifacts stay in --output-dir.
"""

import argparse
import base64
import hashlib
import json
import math
import os
import secrets
import ssl
import statistics
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pyotp

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "docker-compose.yml",
    "docker-compose.https.yml",
    "docker-compose.production.yml",
    "docker-compose.release-test.yml",
]


def p95(values):
    if not values:
        raise ValueError("A percentile requires at least one observation")
    return sorted(values)[math.ceil(len(values) * 0.95) - 1]


def scheduled_offset(index, burst=False):
    if type(index) is not int or index < 0:
        raise ValueError("Expected a nonnegative delivery index")
    minute, position = divmod(index, 600)
    # Fifty deliveries at 20 EPS, then idle, preserving the ten-EPS minute budget.
    return minute * 60 + (
        position * 0.05 if burst and position < 50 else position * 0.1
    )


def history_seed_sql(events: int, source_id: int):
    """Synthetic fixture only: prior-day volume, not historical ingestion/detection testing."""
    if type(events) is not int or not 1 <= events <= 6048000:
        raise ValueError("Historical fixture size must be 1–6048000 records")
    if type(source_id) is not int or source_id <= 0:
        raise ValueError("Expected a positive fixture source ID")
    return f"""
    BEGIN;
    INSERT INTO events (timestamp, source, event_type, severity, source_ip, username,
                        hostname, message, metadata, created_at)
    SELECT stamp, 'linux', 'authentication_success', 'low',
           '203.0.113.' || (10 + n % 8), 'fixture', 'release-test',
           'Synthetic historical authentication fixture',
           '{{"fixture": true, "preloaded": true}}'::json, stamp
    FROM generate_series(1, {events}) AS n,
         LATERAL (SELECT CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
                         - n * INTERVAL '0.1 seconds' AS stamp) AS timing;
    INSERT INTO source_receipts (source_id, record_key, payload_hash, event_id)
    SELECT {source_id}, 'history-fixture-' || lpad(id::text, 16, '0'),
           repeat('0', 64), id FROM events;
    UPDATE log_sources SET total_events = {events} WHERE id = {source_id};
    COMMIT;
    ANALYZE events;
    ANALYZE source_receipts;
    """


def database_fingerprints(compose, environment, database):
    """Hash ordered COPY streams without materializing a whole table or plaintext file."""
    if database not in {"sentinelx_release_test", "sentinelx_restore_release"}:
        raise ValueError("Only disposable fixture databases may be fingerprinted")
    tables = {
        "users": "id",
        "events": "id",
        "log_sources": "id",
        "source_receipts": "source_id,record_key",
        "alerts": "id",
        "incidents": "id",
        "incident_events": "incident_id,event_id",
        "audit_logs": "id",
        "refresh_sessions": "id",
        "detection_rules": "id",
        "incident_notes": "id",
        "assets": "id",
        "iocs": "id",
        "incident_iocs": "incident_id,ioc_id",
        "notification_outbox": "id",
        "webauthn_credentials": "id",
        "webauthn_challenges": "id",
    }
    fingerprints = {}
    for table, order in tables.items():
        process = subprocess.Popen(
            compose
            + [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "sentinelx",
                "-d",
                database,
                "-q",
                "-c",
                f"COPY (SELECT row_to_json(t)::text FROM {table} t ORDER BY {order}) TO STDOUT;",
            ],
            env=environment,
            stdout=subprocess.PIPE,
        )
        digest = hashlib.sha256()
        try:
            for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
                digest.update(block)
        except BaseException:
            process.terminate()
            process.wait()
            raise
        finally:
            process.stdout.close()
        if process.wait() != 0:
            raise RuntimeError("Disposable fixture fingerprint query failed")
        fingerprints[table] = digest.hexdigest()
    return fingerprints


def require(response, expected=200):
    if response.status_code != expected:
        # Do not put response bodies (which can contain enrollment/recovery credentials) in reports.
        raise RuntimeError(
            f"Unexpected HTTP status {response.status_code}; expected {expected}"
        )
    return response.json() if response.content else None


def wait_ready(client):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if client.get("/health/ready").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("Disposable stack did not become ready")


def main():
    if not __debug__:
        raise SystemExit(
            "Release checks require Python assertions enabled; do not use -O"
        )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument(
        "--bursts",
        action="store_true",
        help="Add bounded 20 EPS bursts without changing the ten-EPS minute budget",
    )
    parser.add_argument(
        "--history-events",
        type=int,
        choices=(0, 100000, 864000, 6048000),
        default=0,
        help="Directly seed synthetic quiet history before API throughput measurement",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/opencode"))
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Leave only the disposable stack running for further review",
    )
    args = parser.parse_args()
    if not 30 <= args.seconds <= 3600:
        parser.error("Choose a workload duration between 30 and 3600 seconds")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    directory = Path(
        tempfile.mkdtemp(prefix="sentinelx-release-", dir=args.output_dir)
    ).resolve()
    os.chmod(directory, 0o700)
    project = "sentinelx-release-" + secrets.token_hex(4)
    tls = directory / "tls"
    tls.mkdir()
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-subj",
            "/CN=SentinelX disposable test CA",
            "-keyout",
            str(tls / "ca.key"),
            "-out",
            str(tls / "ca.pem"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN=localhost",
            "-keyout",
            str(tls / "leaf.key"),
            "-out",
            str(tls / "leaf.csr"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    (tls / "extensions").write_text(
        "subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n"
    )
    subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(tls / "leaf.csr"),
            "-CA",
            str(tls / "ca.pem"),
            "-CAkey",
            str(tls / "ca.key"),
            "-CAcreateserial",
            "-days",
            "2",
            "-extfile",
            str(tls / "extensions"),
            "-out",
            str(tls / "leaf.pem"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.chmod(tls / "ca.key", 0o600)
    os.chmod(tls / "leaf.key", 0o400)
    # Only this newly created disposable key changes owner; never alter operator certificates.
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{tls}:/tls",
            "--entrypoint",
            "chown",
            "postgres:17-alpine",
            "101:101",
            "/tls/leaf.key",
        ],
        check=True,
    )
    password = secrets.token_urlsafe(24)
    new_password = secrets.token_urlsafe(24)
    values = {
        "ENVIRONMENT": "production",
        "JWT_SECRET": secrets.token_urlsafe(48),
        "MFA_ENCRYPTION_KEY": base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode(),
        "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
        "POSTGRES_MIGRATION_PASSWORD": secrets.token_urlsafe(24),
        "POSTGRES_RUNTIME_PASSWORD": secrets.token_urlsafe(24),
        "POSTGRES_NOTIFICATION_PASSWORD": secrets.token_urlsafe(24),
        "REDIS_PASSWORD": secrets.token_urlsafe(24),
        "POSTGRES_DATABASE": "sentinelx_release_test",
        "BOOTSTRAP_ADMIN_EMAIL": "admin@sentinelx.dev",
        "BOOTSTRAP_ADMIN_PASSWORD": password,
        "COOKIE_SECURE": "true",
        "DEMO_MODE": "false",
        "SEED_DEMO": "false",
        "LIVE_MONITORING": "true",
        "LLM_PROVIDER": "offline",
        "LLM_API_KEY": "",
        "ABUSEIPDB_API_KEY": "",
        "API_DOCS_ENABLED": "false",
        "ALLOWED_HOSTS": "localhost,127.0.0.1",
        "ALLOWED_ORIGINS": "https://localhost:18443",
        "HTTPS_HOST": "localhost",
        "HTTPS_ORIGIN": "https://localhost:18443",
        "HTTPS_PORT": "18443",
        "TLS_CERT_FILE": str(tls / "leaf.pem"),
        "TLS_KEY_FILE": str(tls / "leaf.key"),
        "RELEASE_ENV_FILE": str(directory / ".env"),
    }
    env_file = directory / ".env"
    with os.fdopen(
        os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as file:
        file.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(env_file),
    ]
    for file in FILES:
        compose += ["-f", str(ROOT / file)]
    # Ambient installation/provider settings must not override the generated test values.
    environment = {key: value for key, value in os.environ.items() if key not in values}
    report = {
        "project": project,
        "duration_seconds": args.seconds,
        "target_eps": 10,
        "bursts": args.bursts,
        "preloaded_events": args.history_events,
        "history_profile": "quiet Linux authentication; direct fixture seed, not replayed ingestion",
        "tls_verified": False,
        "status": "failed",
    }
    print(
        f"Isolated release validation: {project}; private artifacts: {directory}",
        flush=True,
    )
    try:
        subprocess.run(compose + ["config", "--quiet"], check=True, env=environment)
        subprocess.run(
            compose + ["up", "--build", "--wait", "--wait-timeout", "240"],
            check=True,
            env=environment,
        )
        report["images"] = {}
        privileges = subprocess.run(
            compose + ["exec", "-T", "backend", "python", "-m", "app.runtime_checks"],
            check=True,
            env=environment,
            capture_output=True,
            text=True,
        )
        report.update(json.loads(privileges.stdout))
        notifier = subprocess.run(
            compose
            + [
                "run",
                "--rm",
                "--no-deps",
                "database-setup",
                "python",
                "-m",
                "app.runtime_checks",
                "--notifier",
            ],
            check=True,
            env=environment,
            capture_output=True,
            text=True,
        )
        report.update(json.loads(notifier.stdout))
        for service in ("backend", "frontend", "nginx", "postgres", "redis"):
            container = subprocess.run(
                compose + ["ps", "-q", service],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            ).stdout.strip()
            report["images"][service] = subprocess.run(
                ["docker", "inspect", "--format", "{{.Image}}", container],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        context = ssl.create_default_context(cafile=str(tls / "ca.pem"))
        with httpx.Client(
            base_url="https://localhost:18443",
            verify=context,
            trust_env=False,
            timeout=20,
            headers={"Origin": values["HTTPS_ORIGIN"]},
        ) as client:
            wait_ready(client)
            report["tls_verified"] = True
            health_command = [
                os.sys.executable,
                str(ROOT / "scripts/health_check.py"),
                "--origin",
                values["HTTPS_ORIGIN"],
                "--ca-file",
                str(tls / "ca.pem"),
            ]
            subprocess.run(
                health_command + ["--certificate-min-days", "0"],
                check=True,
                env=environment,
                capture_output=True,
            )
            assert (
                subprocess.run(
                    health_command, env=environment, capture_output=True
                ).returncode
                != 0
            )
            report["certificate_expiry_alert_verified"] = True
            assert (
                "max-age=31536000"
                in client.get("/").headers["strict-transport-security"]
            )
            assert client.get("/api/docs").status_code == 404
            assert client.get("/.env").status_code in {403, 404}
            assert (
                client.get(
                    "/health/live", headers={"Host": "untrusted.example"}
                ).status_code
                == 400
            )
            first_response = client.post(
                "/api/v1/auth/login",
                json={"email": values["BOOTSTRAP_ADMIN_EMAIL"], "password": password},
            )
            first = require(first_response)
            assert (
                "Secure" in first_response.headers["set-cookie"]
                and "HttpOnly" in first_response.headers["set-cookie"]
            )
            headers = {"Authorization": "Bearer " + first["access_token"]}
            assert first["user"]["must_change_password"]
            assert client.get("/api/v1/dashboard", headers=headers).status_code == 403
            require(
                client.post(
                    "/api/v1/auth/change-password",
                    headers=headers,
                    json={"current_password": password, "new_password": new_password},
                ),
                204,
            )
            session = require(
                client.post(
                    "/api/v1/auth/login",
                    json={
                        "email": values["BOOTSTRAP_ADMIN_EMAIL"],
                        "password": new_password,
                    },
                )
            )
            headers = {"Authorization": "Bearer " + session["access_token"]}
            assert client.get("/api/v1/dashboard", headers=headers).status_code == 403
            setup = require(
                client.post(
                    "/api/v1/auth/mfa/setup",
                    headers=headers,
                    json={"password": new_password},
                )
            )
            codes = require(
                client.post(
                    "/api/v1/auth/mfa/enable",
                    headers=headers,
                    json={"code": pyotp.TOTP(setup["secret"]).now()},
                )
            )["recovery_codes"]
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
            session = require(
                client.post(
                    "/api/v1/auth/login",
                    json={
                        "email": values["BOOTSTRAP_ADMIN_EMAIL"],
                        "password": new_password,
                        "otp": codes[0],
                    },
                )
            )
            headers = {"Authorization": "Bearer " + session["access_token"]}
            assert (
                client.post(
                    "/api/v1/auth/login",
                    json={
                        "email": values["BOOTSTRAP_ADMIN_EMAIL"],
                        "password": new_password,
                        "otp": codes[0],
                    },
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/api/v1/auth/refresh",
                    headers={"Origin": "https://untrusted.example"},
                ).status_code
                == 403
            )
            require(client.get("/api/v1/dashboard", headers=headers))
            source = require(
                client.post(
                    "/api/v1/sources",
                    headers=headers,
                    json={
                        "name": "Disposable capacity fixture",
                        "kind": "linux",
                        "hostname": "release-test",
                        "log_path": "/fixture/auth.log",
                    },
                ),
                201,
            )
            collector = {"Authorization": "Bearer " + source["collector_key"]}
            url = f"/api/v1/sources/{source['source']['id']}/events"
            count = args.seconds * 10

            def persisted_counts():
                result = subprocess.run(
                    compose
                    + [
                        "exec",
                        "-T",
                        "postgres",
                        "psql",
                        "-v",
                        "ON_ERROR_STOP=1",
                        "-U",
                        "sentinelx",
                        "-d",
                        "sentinelx_release_test",
                        "-At",
                        "-c",
                        "SELECT json_build_object('events',(SELECT count(*) FROM events),"
                        "'receipts',(SELECT count(*) FROM source_receipts),"
                        "'database_bytes',pg_database_size(current_database()));",
                    ],
                    check=True,
                    env=environment,
                    capture_output=True,
                    text=True,
                )
                return json.loads(result.stdout)

            if args.history_events:
                assert persisted_counts()["events"] == 0
                subprocess.run(
                    compose
                    + [
                        "exec",
                        "-T",
                        "postgres",
                        "psql",
                        "-v",
                        "ON_ERROR_STOP=1",
                        "-U",
                        "sentinelx",
                        "-d",
                        "sentinelx_release_test",
                        "-q",
                        "-c",
                        history_seed_sql(args.history_events, source["source"]["id"]),
                    ],
                    check=True,
                    env=environment,
                    capture_output=True,
                )
                seeded = persisted_counts()
                assert seeded["events"] == seeded["receipts"] == args.history_events
                report["preloaded_database_bytes"] = seeded["database_bytes"]
                session = require(client.post("/api/v1/auth/refresh"))
                headers["Authorization"] = "Bearer " + session["access_token"]

            def payload(index):
                ip = f"203.0.113.{10 + index % 8}"
                line = f"sshd: Failed password for fixture from {ip} port 22 ssh2"
                if index % 20 == 18:
                    line = f"sshd: Accepted password for fixture from {ip} port 22 ssh2"
                return {
                    "record_key": f"release-fixture-{index:016d}",
                    "line": line,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            first_payload = payload(0)

            def deliver(index, scheduled):
                started = time.monotonic()
                response = client.post(
                    url,
                    headers=collector,
                    json=first_payload if index == 0 else payload(index),
                )
                result = require(response, 201)
                assert not result["duplicate"]
                finished = time.monotonic()
                return {
                    "latency": finished - scheduled,
                    "scheduling_delay": started - scheduled,
                    "request_time": finished - started,
                }

            def read_dashboard():
                started = time.monotonic()
                require(client.get("/api/v1/dashboard", headers=headers))
                return time.monotonic() - started

            futures = []
            reads = []
            start = time.monotonic()
            with ThreadPoolExecutor(max_workers=6) as executor:
                for index in range(count):
                    deadline = start + scheduled_offset(index, args.bursts)
                    time.sleep(max(0, deadline - time.monotonic()))
                    if index and index % 3000 == 0:
                        session = require(client.post("/api/v1/auth/refresh"))
                        headers["Authorization"] = "Bearer " + session["access_token"]
                    futures.append(executor.submit(deliver, index, deadline))
                    if index % 50 == 0:
                        reads.append(executor.submit(read_dashboard))
                timings = [future.result() for future in futures]
                latencies = [row["latency"] for row in timings]
                read_latencies = [future.result() for future in reads]
            elapsed = time.monotonic() - start
            report.update(
                {
                    "acknowledged": count,
                    "elapsed_seconds": round(elapsed, 3),
                    "achieved_eps": round(count / elapsed, 3),
                    "p50_seconds": round(statistics.median(latencies), 4),
                    "p95_seconds": round(p95(latencies), 4),
                    "max_seconds": round(max(latencies), 4),
                    "concurrent_dashboard_reads": len(reads),
                    "dashboard_p95_seconds": round(p95(read_latencies), 4),
                    "dashboard_max_seconds": round(max(read_latencies), 4),
                    "max_scheduling_delay_seconds": round(
                        max(row["scheduling_delay"] for row in timings), 4
                    ),
                    "p95_request_seconds": round(
                        p95([row["request_time"] for row in timings]),
                        4,
                    ),
                }
            )
            assert (
                count / elapsed >= 9.5
                and report["p95_seconds"] < 1
                and max(latencies) < 5
                and report["dashboard_p95_seconds"] < 1
                and max(read_latencies) < 5
            )
            assert require(
                client.post(url, headers=collector, json=first_payload), 201
            )["duplicate"]
            assert (
                client.post(
                    url,
                    headers=collector,
                    json={**first_payload, "line": first_payload["line"] + " changed"},
                ).status_code
                == 409
            )
            totals = require(client.get("/api/v1/dashboard", headers=headers))
            assert (
                count <= totals["total_events"] <= args.history_events + count
                and totals["active_alerts"] > 0
                and totals["open_incidents"] > 0
            )
            persisted = persisted_counts()
            assert (
                persisted["events"]
                == persisted["receipts"]
                == args.history_events + count
            )
            subprocess.run(
                compose + ["restart", "postgres"], check=True, env=environment
            )
            wait_ready(client)
            totals = require(client.get("/api/v1/dashboard", headers=headers))
            assert count <= totals["total_events"] <= args.history_events + count
            persisted = persisted_counts()
            assert (
                persisted["events"]
                == persisted["receipts"]
                == args.history_events + count
            )
            subprocess.run(compose + ["stop", "redis"], check=True, env=environment)
            assert client.get("/health/ready").status_code == 503
            retry_payload = payload(count)
            assert (
                client.post(url, headers=collector, json=retry_payload).status_code
                == 503
            )
            subprocess.run(
                compose + ["up", "-d", "--wait", "redis"], check=True, env=environment
            )
            wait_ready(client)
            require(client.post(url, headers=collector, json=retry_payload), 201)
            totals = require(client.get("/api/v1/dashboard", headers=headers))
            assert (
                count + 1 <= totals["total_events"] <= args.history_events + count + 1
            )
            persisted = persisted_counts()
            assert (
                persisted["events"]
                == persisted["receipts"]
                == args.history_events + count + 1
            )
            report["persisted_events"] = persisted["events"]
            report["database_bytes"] = persisted["database_bytes"]
            report["failure_recovery"] = True
        identity = directory / "backup.agekey"
        subprocess.run(
            ["age-keygen", "-o", str(identity)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.chmod(identity, 0o600)
        recipient = subprocess.run(
            ["age-keygen", "-y", str(identity)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        backup = [
            os.sys.executable,
            str(ROOT / "scripts/backup.py"),
            "--project",
            project,
            "--env-file",
            str(env_file),
        ]
        for file in FILES:
            backup += ["--compose-file", str(ROOT / file)]

        def fingerprints(database):
            return database_fingerprints(compose, environment, database)

        original = fingerprints("sentinelx_release_test")
        archive = directory / "backup.age"
        subprocess.run(
            backup
            + [
                "backup",
                "--database",
                "sentinelx_release_test",
                "--recipient",
                recipient,
                "--output",
                str(archive),
            ],
            check=True,
            env=environment,
        )
        restored = subprocess.run(
            backup
            + [
                "restore-drill",
                "--database",
                "sentinelx_restore_release",
                "--identity-file",
                str(identity),
                "--input",
                str(archive),
            ],
            check=True,
            env=environment,
            capture_output=True,
            text=True,
        )
        restored_counts = json.loads(restored.stdout)["counts"]
        assert (
            restored_counts["events"] == args.history_events + count + 1
            and restored_counts["receipts"] == args.history_events + count + 1
            and restored_counts["users"] == 1
            and restored_counts["revision"] == "0008_receipt_metrics"
        )
        report["encrypted_restore"] = restored_counts
        assert fingerprints("sentinelx_restore_release") == original
        # Never overwrite an existing restore database, even with a valid archive.
        refused = subprocess.run(
            backup
            + [
                "restore-drill",
                "--database",
                "sentinelx_restore_release",
                "--identity-file",
                str(identity),
                "--input",
                str(archive),
            ],
            env=environment,
            capture_output=True,
        )
        assert (
            refused.returncode != 0
            and fingerprints("sentinelx_restore_release") == original
        )
        corrupt = directory / "corrupt.age"
        damaged = bytearray(archive.read_bytes())
        damaged[-1] ^= 1
        with os.fdopen(
            os.open(corrupt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        ) as file:
            file.write(damaged)
        rejected = subprocess.run(
            backup
            + [
                "restore-drill",
                "--database",
                "sentinelx_restore_corrupt",
                "--identity-file",
                str(identity),
                "--input",
                str(corrupt),
            ],
            env=environment,
            capture_output=True,
        )
        assert rejected.returncode != 0
        report["restore_content_verified"] = sorted(original)
        report["restore_safety_checks"] = True
        report["status"] = "passed"
        # Test-only browser credentials are kept private, not printed or published.
        browser_env = directory / "browser.env"
        with os.fdopen(
            os.open(browser_env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
        ) as file:
            file.write(
                f"SENTINELX_E2E_URL=https://localhost:18443\nSENTINELX_E2E_PASSWORD={new_password}\nSENTINELX_E2E_OTP={codes[1]}\n"
            )
    finally:
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
        if not args.keep:
            # Only this process's unique disposable project is stopped; volumes/artifacts remain for review.
            subprocess.run(compose + ["down"], env=environment, check=False)


if __name__ == "__main__":
    main()
