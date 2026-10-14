"""Configure the full dashboard's Vercel proxy and direct live-update endpoint."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-origin", required=True)
    args = parser.parse_args()
    origin = args.backend_origin.rstrip("/")
    url = urlsplit(origin)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.port
        or url.path
        or url.query
        or url.fragment
    ):
        parser.error(
            "Supply one HTTPS backend origin, without credentials, port, or path"
        )
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    csp = (
        "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; img-src 'self' data: blob:; "
        f"connect-src 'self' wss://{url.hostname}; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    config = {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "framework": "vite",
        "buildCommand": "npm run build",
        "outputDirectory": "dist",
        "rewrites": [
            {"source": "/api/:path*", "destination": f"{origin}/api/:path*"},
            {"source": "/health/:path*", "destination": f"{origin}/health/:path*"},
            {"source": "/:path*", "destination": "/index.html"},
        ],
        "headers": [
            {
                "source": "/(.*)",
                "headers": [
                    {"key": "Content-Security-Policy", "value": csp},
                    {"key": "Referrer-Policy", "value": "no-referrer"},
                    {"key": "X-Content-Type-Options", "value": "nosniff"},
                    {"key": "X-Frame-Options", "value": "DENY"},
                    {
                        "key": "Permissions-Policy",
                        "value": "camera=(), microphone=(), geolocation=()",
                    },
                    {"key": "Strict-Transport-Security", "value": "max-age=31536000"},
                ],
            },
            {
                "source": "/api/:path*",
                "headers": [
                    {"key": "Cache-Control", "value": "no-store"},
                    {"key": "CDN-Cache-Control", "value": "no-store"},
                    {"key": "x-vercel-enable-rewrite-caching", "value": "0"},
                ],
            },
        ],
    }
    (frontend / "vercel.json").write_text(json.dumps(config, indent=2) + "\n")
    envfile = frontend / ".env.production"
    lines = envfile.read_text().splitlines() if envfile.exists() else []
    lines = [line for line in lines if not line.startswith("VITE_BACKEND_ORIGIN=")]
    envfile.write_text("\n".join([*lines, f"VITE_BACKEND_ORIGIN={origin}"]) + "\n")
    print("Vercel proxy, security headers, and live-update origin configured.")


if __name__ == "__main__":
    main()
