"""Forward an authorized local log file; never scans or attacks any host."""

import argparse
import getpass
import ipaddress
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx


def is_loopback(url):
    hostname = urlparse(url).hostname
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument(
        "--source", choices=["linux", "nginx", "apache", "application"], required=True
    )
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--follow",
        action="store_true",
        help="Follow newly appended lines; restart manually after log rotation",
    )
    args = parser.parse_args()
    if not is_loopback(args.url):
        parser.error("This MVP collector is restricted to a local SentinelX endpoint")
    password = os.environ.get("SENTINELX_COLLECTOR_PASSWORD") or getpass.getpass(
        "SentinelX password: "
    )
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=15) as client:
        login = client.post(
            "/api/v1/auth/login", json={"email": args.email, "password": password}
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        origin = f"{urlparse(args.url).scheme}://{urlparse(args.url).netloc}"
        with args.file.open() as file:
            while True:
                line = file.readline()
                if not line:
                    if not args.follow:
                        break
                    time.sleep(0.5)
                    continue
                if not line.strip():
                    continue
                # Receipt time is supplied because syslog lacks a year and timezone. See collector docs.
                payload = {
                    "source": args.source,
                    "hostname": args.hostname,
                    "line": line.strip(),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                response = client.post(
                    "/api/v1/events/raw",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Origin": origin},
                )
                if response.status_code == 401:
                    refresh = client.post(
                        "/api/v1/auth/refresh", headers={"Origin": origin}
                    )
                    refresh.raise_for_status()
                    token = refresh.json()["access_token"]
                    response = client.post(
                        "/api/v1/events/raw",
                        json=payload,
                        headers={"Authorization": f"Bearer {token}", "Origin": origin},
                    )
                if response.status_code == 429:
                    # Do not silently skip throttled evidence.
                    raise SystemExit(
                        "Collector rate limited. No retries occurred; resume from the rejected line."
                    )
                response.raise_for_status()
                print(response.json()["event"]["reference"])
        client.post(
            "/api/v1/auth/logout", headers={"Origin": origin}
        ).raise_for_status()


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, OSError) as error:
        print(
            f"Collection stopped: {type(error).__name__}. Check the file, API connection, and permissions.",
            file=sys.stderr,
        )
        sys.exit(1)
