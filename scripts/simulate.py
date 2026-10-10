"""Invoke the explicitly enabled development simulator on loopback only."""

import argparse
import getpass
import ipaddress
import os
from urllib.parse import urlparse

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://localhost:8080")
parser.add_argument("--email", default="admin@sentinelx.dev")
args = parser.parse_args()
host = urlparse(args.url).hostname
try:
    local = host == "localhost" or ipaddress.ip_address(host).is_loopback
except ValueError:
    local = False
if not local:
    parser.error("Simulation is restricted to a loopback SentinelX endpoint")
password = os.environ.get("SENTINELX_SIMULATOR_PASSWORD") or getpass.getpass(
    "Administrator password: "
)
origin = f"{urlparse(args.url).scheme}://{urlparse(args.url).netloc}"
with httpx.Client(base_url=args.url.rstrip("/"), timeout=30) as client:
    login = client.post(
        "/api/v1/auth/login", json={"email": args.email, "password": password}
    )
    login.raise_for_status()
    response = client.post(
        "/api/v1/demo/simulate",
        headers={
            "Authorization": f"Bearer {login.json()['access_token']}",
            "Origin": origin,
        },
    )
    response.raise_for_status()
    result = response.json()
    print(
        f"Inserted {len(result['event_ids'])} synthetic events, {len(result['alert_ids'])} alerts. Incident: {result['incident_id']}"
    )
    client.post("/api/v1/auth/logout", headers={"Origin": origin}).raise_for_status()
