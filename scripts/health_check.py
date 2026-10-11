"""Exit nonzero when a verified SentinelX readiness endpoint is unavailable."""

import argparse
import ipaddress
import ssl
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
    args = parser.parse_args()
    context = ssl.create_default_context(cafile=args.ca_file)
    try:
        with httpx.Client(
            verify=context, trust_env=False, timeout=10, follow_redirects=False
        ) as client:
            response = client.get(args.origin + "/health/ready")
            response.raise_for_status()
            if response.json() != {"status": "ok"}:
                raise ValueError("Invalid readiness response")
    except (httpx.HTTPError, ValueError):
        raise SystemExit(
            "SentinelX unavailable: check service health and notify the operator"
        ) from None
    print(
        "SentinelX ready (database and Redis reachable; not proof of complete log coverage)"
    )


if __name__ == "__main__":
    main()
