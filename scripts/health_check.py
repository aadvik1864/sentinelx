"""Exit nonzero when a verified SentinelX readiness endpoint is unavailable."""

import argparse
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit

import httpx


def health_origin(value):
    url = urlsplit(value)
    loopback = url.hostname == "localhost"
    try:
        loopback = loopback or ipaddress.ip_address(url.hostname).is_loopback
    except (ValueError, TypeError):
        pass
    if (
        not url.hostname
        or url.username is not None
        or url.password is not None
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
        or (url.scheme != "https" and not (url.scheme == "http" and loopback))
    ):
        raise argparse.ArgumentTypeError(
            "Use an exact HTTPS origin, or loopback HTTP, without credentials"
        )
    return value.rstrip("/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", type=health_origin, required=True)
    parser.add_argument(
        "--ca-file", help="Optional private CA; never disables certificate verification"
    )
    parser.add_argument("--certificate-min-days", type=int, default=14)
    args = parser.parse_args()
    context = ssl.create_default_context(cafile=args.ca_file)
    if not 0 <= args.certificate_min_days <= 365:
        parser.error("Certificate warning threshold must be 0–365 days")
    try:
        origin = urlsplit(args.origin)
        if origin.scheme == "https":
            with socket.create_connection(
                (origin.hostname, origin.port or 443), timeout=10
            ) as tcp:
                with context.wrap_socket(tcp, server_hostname=origin.hostname) as tls:
                    expiry = ssl.cert_time_to_seconds(tls.getpeercert()["notAfter"])
                    if expiry - time.time() < args.certificate_min_days * 86400:
                        raise ValueError(
                            "Certificate renewal requires operator attention"
                        )
        with httpx.Client(
            verify=context, trust_env=False, timeout=10, follow_redirects=False
        ) as client:
            response = client.get(args.origin + "/health/ready")
            response.raise_for_status()
            if response.json() != {"status": "ok"}:
                raise ValueError("Invalid readiness response")
    except (httpx.HTTPError, ValueError, OSError, KeyError):
        raise SystemExit(
            "SentinelX readiness/TLS check failed: notify the operator"
        ) from None
    print(
        "SentinelX ready (database and Redis reachable; not proof of complete log coverage)"
    )


if __name__ == "__main__":
    main()
