"""Provision authorized local sources without deleting demo data, then supervise their collector."""

import argparse
import json
import os
import socket
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(content)


def find_existing_source(sources, definition):
    by_name = next((row for row in sources if row["name"] == definition["name"]), None)
    if by_name is not None:
        return by_name
    # A display-name change must not provision another collector or replace its key.
    matches = [
        row
        for row in sources
        if all(
            row.get(field) == definition[field]
            for field in ("kind", "hostname", "log_path")
        )
    ]
    if len(matches) > 1:
        raise SystemExit(
            "Several existing sources match this system. Review them before provisioning."
        )
    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-service", action="store_true")
    args = parser.parse_args()
    environment = dict(
        line.split("=", 1)
        for line in (ROOT / ".env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    if (
        environment.get("SEED_DEMO", "true").lower() != "false"
        or environment.get("DEMO_MODE", "true").lower() != "false"
    ):
        raise SystemExit(
            "Disable DEMO_MODE and SEED_DEMO before provisioning real sources."
        )
    if environment.get("POSTGRES_DATABASE") != "sentinelx_live":
        raise SystemExit(
            "Use the separate sentinelx_live database. The existing demo database must be preserved."
        )
    config_path = ROOT / ".state" / "collector.json"
    existing_config = (
        json.loads(config_path.read_text()) if config_path.exists() else None
    )
    hostname = socket.gethostname()
    auth_log = next(
        (
            path
            for path in [Path("/var/log/auth.log"), Path("/var/log/secure")]
            if path.is_file()
        ),
        Path("/var/log/auth.log"),
    )
    definitions = [
        {
            "name": f"Linux host: {hostname}",
            "kind": "linux",
            "hostname": hostname,
            "log_path": str(auth_log),
            "mode": "file",
        },
        {
            "name": "SentinelX website",
            "kind": "nginx",
            "hostname": f"{hostname}-web",
            "log_path": "docker:sentinelx/nginx",
            "mode": "docker",
            "service": "nginx",
        },
        {
            "name": "SentinelX application",
            "kind": "application",
            "hostname": f"{hostname}-app",
            "log_path": "docker:sentinelx/backend",
            "mode": "docker",
            "service": "backend",
        },
    ]
    with httpx.Client(
        base_url="http://localhost:8080",
        timeout=30,
        headers={"Origin": "http://localhost:8080"},
    ) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": environment.get(
                    "BOOTSTRAP_ADMIN_EMAIL", "admin@sentinelx.dev"
                ),
                "password": environment["BOOTSTRAP_ADMIN_PASSWORD"],
            },
        )
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        response = client.get("/api/v1/system")
        response.raise_for_status()
        if not response.json().get("live_monitoring") or response.json().get(
            "demo_mode"
        ):
            raise SystemExit(
                "The running backend must have LIVE_MONITORING=true and DEMO_MODE=false."
            )
        response = client.get("/api/v1/sources")
        response.raise_for_status()
        existing_sources = response.json()["items"]
        sources = []
        for definition in definitions:
            prior = find_existing_source(existing_sources, definition)
            known = next(
                (
                    row
                    for row in (existing_config or {}).get("sources", [])
                    if prior and row["id"] == prior["id"]
                ),
                None,
            )
            if prior and not known:
                raise SystemExit(
                    "An existing local source has no saved private configuration. Recover its configuration or explicitly replace its key in Log sources; no keys were silently rotated."
                )
            if prior:
                sources.append(known)
                continue
            response = client.post(
                "/api/v1/sources",
                json={
                    key: definition[key]
                    for key in ("name", "kind", "hostname", "log_path")
                },
            )
            response.raise_for_status()
            result = response.json()
            source = {
                "id": result["source"]["id"],
                "key": result["collector_key"],
                "kind": definition["kind"],
                "mode": definition["mode"],
                "start": "tail",
                "timezone": "local",
            }
            if definition["mode"] == "file":
                source["path"] = definition["log_path"]
            else:
                source.update(
                    {
                        "project": "sentinelx",
                        "service": definition["service"],
                        "self_monitoring": True,
                    }
                )
            sources.append(source)
            # Persist every new key immediately; a later provisioning failure must not lose it.
            saved_sources = {
                row["id"]: row for row in (existing_config or {}).get("sources", [])
            }
            saved_sources.update({row["id"]: row for row in sources})
            private_write(
                config_path,
                json.dumps(
                    {
                        "url": "http://localhost:8080",
                        "state_file": str(ROOT / ".state" / "collector.sqlite3"),
                        "sources": list(saved_sources.values()),
                    },
                    indent=2,
                ),
            )
        if sources:
            response = client.get("/api/v1/assets")
            response.raise_for_status()
            assets = {row["hostname"] for row in response.json()["items"]}
            for definition in definitions:
                if definition["hostname"] not in assets:
                    result = client.post(
                        "/api/v1/assets",
                        json={
                            "hostname": definition["hostname"],
                            "ip_address": "127.0.0.1",
                            "type": "application"
                            if definition["kind"] == "application"
                            else "endpoint"
                            if definition["kind"] == "linux"
                            else "server",
                            "environment": "local",
                            "owner": "Local operator",
                            "status": "active",
                        },
                    )
                    result.raise_for_status()
            response = client.get("/api/v1/rules")
            response.raise_for_status()
            rules = response.json()["items"]
            for rule in rules:
                if rule["name"] in {
                    "SSH brute force",
                    "Successful login after brute force",
                    "Suspicious privilege escalation",
                    "Unknown user authenticated",
                }:
                    result = client.patch(
                        f"/api/v1/rules/{rule['id']}",
                        json={"config": {**rule["config"], "sources": ["linux"]}},
                    )
                    result.raise_for_status()
            for name, pattern, event_type, threshold, severity, techniques in [
                (
                    "Application authentication failures",
                    "threshold",
                    "authentication_failure",
                    10,
                    "high",
                    ["T1110"],
                ),
                (
                    "Application login after repeated failures",
                    "successful_after_failures",
                    "authentication_success",
                    10,
                    "critical",
                    ["T1110", "T1078"],
                ),
                (
                    "Application error burst",
                    "threshold",
                    "application_error",
                    5,
                    "medium",
                    [],
                ),
            ]:
                if not any(rule["name"] == name for rule in rules):
                    result = client.post(
                        "/api/v1/rules",
                        json={
                            "name": name,
                            "description": "Real application activity; verify legitimate intent before taking action.",
                            "kind": pattern,
                            "event_type": event_type,
                            "threshold": threshold,
                            "window_seconds": 300,
                            "severity": severity,
                            "mitre_techniques": techniques,
                            "config": {"sources": ["application"]},
                        },
                    )
                    result.raise_for_status()
        saved_sources = {
            row["id"]: row for row in (existing_config or {}).get("sources", [])
        }
        saved_sources.update({row["id"]: row for row in sources})
        private_write(
            config_path,
            json.dumps(
                {
                    "url": "http://localhost:8080",
                    "state_file": str(ROOT / ".state" / "collector.sqlite3"),
                    "sources": list(saved_sources.values()),
                },
                indent=2,
            ),
        )
        client.post("/api/v1/auth/logout").raise_for_status()
    print(
        "Registered three real local sources. Private source keys are saved in .state/collector.json (0600)."
    )
    if args.install_service:
        unit = (
            Path.home() / ".config" / "systemd" / "user" / "sentinelx-collector.service"
        )
        if (
            unit.exists()
            and "Managed by SentinelX setup_monitoring.py" not in unit.read_text()
        ):
            raise SystemExit(
                "An unfamiliar collector service already exists; it was not overwritten."
            )
        command = " ".join(
            json.dumps(str(value).replace("%", "%%"))
            for value in (
                ROOT / ".venv" / "bin" / "python",
                ROOT / "collectors" / "agent.py",
                "--config",
                config_path,
            )
        )
        private_write(
            unit,
            f"# Managed by SentinelX setup_monitoring.py\n[Unit]\nDescription=SentinelX authorized local log collection\n\n[Service]\nType=simple\nWorkingDirectory={ROOT}\nExecStart={command}\nRestart=on-failure\nRestartSec=5\nUMask=0077\nNoNewPrivileges=true\n\n[Install]\nWantedBy=default.target\n",
        )
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "sentinelx-collector.service"],
            check=True,
        )
        print(
            "The collector is supervised by your user systemd manager. Check: systemctl --user status sentinelx-collector"
        )
    else:
        print(
            "Start with: .venv/bin/python collectors/agent.py --config .state/collector.json"
        )


if __name__ == "__main__":
    main()
